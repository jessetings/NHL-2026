"""Curate raw JSON/CSV into Parquet tables under data/curated/ (query with DuckDB).

Usage: python src/ingest/curate.py [nhl|mp|sgo|all]
"""
import glob
import io
import os
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from common import load_json_gz

CUR = "data/curated"
NHL = "data/raw/nhl"


def toi_sec(s):
    if not isinstance(s, str) or ":" not in s:
        return None
    m, sec = s.split(":")
    return int(m) * 60 + int(sec)


def write(df, name):
    os.makedirs(CUR, exist_ok=True)
    try:
        df.to_parquet(f"{CUR}/{name}.parquet", index=False)
    except (OverflowError, TypeError, ValueError):
        df = df.astype({c: "string" for c in df.columns if df[c].dtype == object or "lineId" in c})
        df.to_parquet(f"{CUR}/{name}.parquet", index=False)
    print(f"{name}: {len(df):,} rows", flush=True)


# ------------------------------------------------------------------ NHL
def _box(f):
    b = load_json_gz(f)
    g = dict(game_id=b["id"], season=b["season"], game_type=b["gameType"], date=b["gameDate"],
             start_utc=b.get("startTimeUTC"), home=b["homeTeam"]["abbrev"], away=b["awayTeam"]["abbrev"],
             home_score=b["homeTeam"].get("score"), away_score=b["awayTeam"].get("score"),
             home_sog=b["homeTeam"].get("sog"), away_sog=b["awayTeam"].get("sog"),
             last_period=b.get("periodDescriptor", {}).get("periodType"),
             venue=b.get("venue", {}).get("default"))
    sk, gk = [], []
    for side, opp_side in (("homeTeam", "awayTeam"), ("awayTeam", "homeTeam")):
        team, opp = b[side]["abbrev"], b[opp_side]["abbrev"]
        pg = b.get("playerByGameStats", {}).get(side, {})
        for grp in ("forwards", "defense"):
            for p in pg.get(grp, []):
                r = {k: v for k, v in p.items() if k not in ("name", "toi")}
                r.update(game_id=b["id"], team=team, opp=opp, is_home=side == "homeTeam",
                         name=p["name"]["default"], toi_sec=toi_sec(p.get("toi")))
                sk.append(r)
        for p in pg.get("goalies", []):
            r = {k: v for k, v in p.items() if k not in ("name", "toi")}
            r.update(game_id=b["id"], team=team, opp=opp, is_home=side == "homeTeam",
                     name=p["name"]["default"], toi_sec=toi_sec(p.get("toi")))
            gk.append(r)
    return g, sk, gk


def _pbp(f):
    b = load_json_gz(f)
    df = pd.json_normalize(b.get("plays", []))
    if df.empty:
        return df
    top = {c for c in df.columns if "." not in c}
    df.columns = [("d_" + c[8:] if c[8:] in top else c[8:]) if c.startswith("details.")
                  else c.replace("periodDescriptor.", "period_") for c in df.columns]
    df["game_id"] = b["id"]
    df["home_id"] = b["homeTeam"]["id"]
    df["away_id"] = b["awayTeam"]["id"]
    return df


def _shifts(f):
    d = load_json_gz(f).get("data", [])
    df = pd.DataFrame(d)
    if df.empty:
        return df
    keep = ["gameId", "playerId", "teamAbbrev", "period", "startTime", "endTime", "duration", "typeCode",
            "firstName", "lastName", "shiftNumber", "eventDescription"]
    df = df[[c for c in keep if c in df.columns]]
    for c in ("startTime", "endTime", "duration"):
        df[c + "_sec"] = df[c].map(toi_sec)
    return df.drop_duplicates(["gameId", "playerId", "period", "startTime_sec", "typeCode"])


def _rail(f):
    b = load_json_gz(f)
    gi = b.get("gameInfo", {})
    gid = int(os.path.basename(f).split(".")[0])

    def nm(x):
        return (x.get("fullName") or x.get("name") or {}).get("default") if isinstance(x, dict) else None
    refs = [nm(x) for x in gi.get("referees", [])]
    lines = [nm(x) for x in gi.get("linesmen", [])]
    out = dict(game_id=gid, referee1=refs[0] if refs else None, referee2=refs[1] if len(refs) > 1 else None,
               linesman1=lines[0] if lines else None, linesman2=lines[1] if len(lines) > 1 else None)
    for side in ("awayTeam", "homeTeam"):
        t = gi.get(side, {})
        out[f"{side[:4]}_coach"] = (t.get("headCoach") or {}).get("default")
        out[f"{side[:4]}_scratches"] = ",".join(str(x.get("id")) for x in t.get("scratches", []))
    return out


def _player(f):
    p = load_json_gz(f)
    bio = dict(player_id=p.get("playerId"), first=p.get("firstName", {}).get("default"),
               last=p.get("lastName", {}).get("default"), position=p.get("position"),
               shoots=p.get("shootsCatches"), birth_date=p.get("birthDate"),
               height_in=p.get("heightInInches"), weight_lb=p.get("weightInPounds"),
               current_team=p.get("currentTeamAbbrev"), is_active=p.get("isActive"),
               draft_year=(p.get("draftDetails") or {}).get("year"),
               draft_overall=(p.get("draftDetails") or {}).get("overallPick"))
    st = pd.json_normalize(p.get("seasonTotals", []))
    if not st.empty:
        st["player_id"] = p.get("playerId")
        st.columns = [c.replace(".default", "") for c in st.columns]
        st = st.loc[:, ~st.columns.duplicated()]
    return bio, st


KEEP_NUM = {"game_id", "eventId", "period_number", "sortOrder", "home_id", "away_id", "gameId", "playerId",
            "period", "startTime_sec", "endTime_sec", "duration_sec", "typeCode", "shiftNumber"}


def _nhl_part(job):
    """Worker: parse a chunk of games and write one parquet part (keeps parent memory flat)."""
    fn, season, i, files = job
    f = _pbp if fn == "pbp" else _shifts
    df = pd.concat([f(x) for x in files], ignore_index=True)
    if df.empty:
        return 0
    for c in df.columns:
        if c not in KEEP_NUM:
            df[c] = df[c].astype("string")
    out = f"{CUR}/nhl_{fn}/season={season}"
    os.makedirs(out, exist_ok=True)
    df.to_parquet(f"{out}/part-{i:05d}.parquet", index=False)
    return len(df)


def curate_nhl():
    files = sorted(glob.glob(f"{NHL}/boxscore/*/*.json.gz"))
    with ProcessPoolExecutor(6) as ex:
        res = list(ex.map(_box, files, chunksize=50))
    write(pd.DataFrame([r[0] for r in res]), "nhl_games")
    write(pd.DataFrame([x for r in res for x in r[1]]), "nhl_skater_game")
    write(pd.DataFrame([x for r in res for x in r[2]]), "nhl_goalie_game")

    for kind, fn in (("play-by-play", "pbp"), ("shifts", "shifts")):
        jobs = []
        for season_dir in sorted(glob.glob(f"{NHL}/{kind}/*")):
            s = os.path.basename(season_dir)
            fs = sorted(glob.glob(f"{season_dir}/*.json.gz"))
            jobs += [(fn, s, i, fs[i:i + 200]) for i in range(0, len(fs), 200)]
        with ProcessPoolExecutor(4) as ex:
            n = sum(ex.map(_nhl_part, jobs))
        print(f"nhl_{fn}: {n:,} rows in {len(jobs)} parts", flush=True)
    fs = sorted(glob.glob(f"{NHL}/right-rail/*/*.json.gz"))
    if fs:
        with ProcessPoolExecutor(6) as ex:
            write(pd.DataFrame(list(ex.map(_rail, fs, chunksize=50))), "nhl_officials")
    fs = sorted(glob.glob(f"{NHL}/players/*.json.gz"))
    if fs:
        with ProcessPoolExecutor(6) as ex:
            res = list(ex.map(_player, fs, chunksize=50))
        write(pd.DataFrame([r[0] for r in res]), "nhl_players")
        st = pd.concat([r[1] for r in res if not r[1].empty], ignore_index=True)
        st = st.astype({c: "string" for c in st.columns if st[c].dtype == object})
        write(st, "nhl_player_seasons")


# ------------------------------------------------------------------ MoneyPuck
def curate_mp():
    mp = "data/raw/moneypuck"
    for kind in ("skaters", "goalies", "teams", "lines"):
        dfs = []
        for f in sorted(glob.glob(f"{mp}/seasonSummary/*/{kind}_*.csv")):
            d = pd.read_csv(f)
            d["game_type"] = f.split("/")[-2]
            dfs.append(d)
        # top-level files from the first pull (2024-2026 regular)
        write(pd.concat(dfs, ignore_index=True), f"mp_{kind}_seasons")
    for f in sorted(glob.glob(f"{mp}/shots/shots_*.zip")):
        s = f.split("_")[-1][:4]
        with zipfile.ZipFile(f) as z:
            name = [n for n in z.namelist() if n.endswith(".csv")][0]
            d = pd.read_csv(io.BytesIO(z.read(name)), low_memory=False)
        write(d, f"mp_shots_{s}")
    if os.path.exists(f"{mp}/gameByGame/all_teams.csv"):
        d = pd.read_csv(f"{mp}/gameByGame/all_teams.csv", low_memory=False)
        write(d[d.season >= 2015], "mp_team_games")
    if os.path.exists(f"{mp}/allPlayersLookup.csv"):
        write(pd.read_csv(f"{mp}/allPlayersLookup.csv"), "mp_players")


# ------------------------------------------------------------------ SGO
def _sgo(f):
    j = load_json_gz(f)
    ev, odds, res = [], [], []
    for e in j.get("data", []):
        eid = e["eventID"]
        st = e.get("status", {})
        ev.append(dict(eventID=eid, startsAt=st.get("startsAt"), home=e["teams"]["home"]["teamID"],
                       away=e["teams"]["away"]["teamID"], ended=st.get("ended"), finalized=st.get("finalized"),
                       cancelled=st.get("cancelled"), type=e.get("type"),
                       players=len(e.get("players", {}))))
        players = e.get("players", {})
        for oid, o in e.get("odds", {}).items():
            base = dict(eventID=eid, oddID=oid, stat=o.get("statID"), entity=o.get("statEntityID"),
                        period=o.get("periodID"), bt=o.get("betTypeID"), side=o.get("sideID"),
                        player=players.get(o.get("statEntityID"), {}).get("name"),
                        fair_odds=o.get("fairOdds"), fair_line=o.get("fairOverUnder") or o.get("fairSpread"),
                        close_fair_odds=o.get("closeFairOdds"),
                        close_fair_line=o.get("closeFairOverUnder") or o.get("closeFairSpread"),
                        close_book_odds=o.get("closeBookOdds"),
                        close_book_line=o.get("closeBookOverUnder") or o.get("closeBookSpread"),
                        open_fair_odds=o.get("openFairOdds"), open_book_odds=o.get("openBookOdds"),
                        score=o.get("score"))
            for b, bo in (o.get("byBookmaker") or {}).items():
                for i, ln in enumerate([bo] + (bo.get("altLines") or [])):
                    odds.append(dict(base, book=b, alt=i > 0, odds=ln.get("odds"),
                                     line=ln.get("overUnder") or ln.get("spread"),
                                     updated=ln.get("lastUpdatedAt"), available=ln.get("available"),
                                     book_open_odds=ln.get("openOdds"), book_close_odds=ln.get("closeOdds"),
                                     book_open_line=ln.get("openOverUnder") or ln.get("openSpread"),
                                     book_close_line=ln.get("closeOverUnder") or ln.get("closeSpread")))
        for per, ents in (e.get("results") or {}).items():
            for ent, stats in (ents or {}).items():
                for k, v in (stats or {}).items():
                    res.append(dict(eventID=eid, period=per, entity=ent, stat=k, value=v))
        for pid, p in players.items():
            res.append(dict(eventID=eid, period="_meta", entity=pid, stat="teamID", value=p.get("teamID")))
    return ev, odds, res


def _sgo_part(f):
    stem = os.path.basename(f).split(".")[0]
    ev, odds, res = _sgo(f)
    if not ev:
        return 0
    ev = pd.DataFrame(ev)
    od = pd.DataFrame(odds)
    rs = pd.DataFrame(res)
    if not od.empty:
        od["odds"] = pd.to_numeric(od.odds, errors="coerce")
        od["line"] = pd.to_numeric(od.line, errors="coerce")
        for c in ("book_open_odds", "book_close_odds", "book_open_line", "book_close_line"):
            od[c] = pd.to_numeric(od[c], errors="coerce")
        od = od.merge(ev[["eventID", "startsAt"]], on="eventID", how="left")
        od["pregame"] = pd.to_datetime(od.updated, utc=True, errors="coerce") < \
            pd.to_datetime(od.startsAt, utc=True, errors="coerce")
        for c in od.columns:
            if c not in ("odds", "line", "alt", "pregame", "available", "book_open_odds", "book_close_odds",
                         "book_open_line", "book_close_line"):
                od[c] = od[c].astype("string")
        od["alt"] = od["alt"].astype(bool)
        od["available"] = od["available"].astype("boolean")
    for name, df in (("sgo_events", ev), ("sgo_odds", od), ("sgo_results", rs)):
        if df.empty:
            continue
        if name == "sgo_results":
            df["value"] = df["value"].astype("string")
        if name == "sgo_events":
            df = df.astype({c: "string" for c in df.columns if df[c].dtype == object})
        os.makedirs(f"{CUR}/{name}", exist_ok=True)
        df.to_parquet(f"{CUR}/{name}/{stem}.parquet", index=False)
    return len(od)


def curate_sgo():
    # same weekly stems in both dirs; the open/close re-pull supersedes the base pull
    by_stem = {os.path.basename(f): f for f in sorted(glob.glob("data/raw/sgo_history/*.json.gz"))}
    by_stem.update({os.path.basename(f): f for f in sorted(glob.glob("data/raw/sgo_history_oc/*.json.gz"))})
    fs = sorted(by_stem.values())
    for d in ("sgo_events", "sgo_odds", "sgo_results"):
        for p in glob.glob(f"{CUR}/{d}/*.parquet"):
            os.remove(p)
    with ProcessPoolExecutor(3) as ex:
        n = sum(ex.map(_sgo_part, fs))
    print(f"sgo_odds: {n:,} rows in {len(fs)} parts", flush=True)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("mp", "all"):
        curate_mp()
    if what in ("nhl", "all"):
        curate_nhl()
    if what in ("sgo", "all"):
        curate_sgo()
