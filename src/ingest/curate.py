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
    df.columns = [c.replace("details.", "").replace("periodDescriptor.", "period_") for c in df.columns]
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
    return df


def _rail(f):
    b = load_json_gz(f)
    gi = b.get("gameInfo", {})
    gid = int(os.path.basename(f).split(".")[0])
    refs = [x.get("default") for x in gi.get("referees", [])]
    lines = [x.get("default") for x in gi.get("linesmen", [])]
    return dict(game_id=gid, referee1=refs[0] if refs else None, referee2=refs[1] if len(refs) > 1 else None,
                linesman1=lines[0] if lines else None, linesman2=lines[1] if len(lines) > 1 else None)


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


def curate_nhl():
    files = sorted(glob.glob(f"{NHL}/boxscore/*/*.json.gz"))
    with ProcessPoolExecutor(6) as ex:
        res = list(ex.map(_box, files, chunksize=50))
    write(pd.DataFrame([r[0] for r in res]), "nhl_games")
    write(pd.DataFrame([x for r in res for x in r[1]]), "nhl_skater_game")
    write(pd.DataFrame([x for r in res for x in r[2]]), "nhl_goalie_game")

    for season_dir in sorted(glob.glob(f"{NHL}/play-by-play/*")):
        s = os.path.basename(season_dir)
        fs = sorted(glob.glob(f"{season_dir}/*.json.gz"))
        with ProcessPoolExecutor(6) as ex:
            dfs = list(ex.map(_pbp, fs, chunksize=25))
        df = pd.concat(dfs, ignore_index=True)
        df = df.astype({c: "string" for c in df.columns if df[c].dtype == object})
        write(df, f"nhl_pbp_{s}")
    for season_dir in sorted(glob.glob(f"{NHL}/shifts/*")):
        s = os.path.basename(season_dir)
        fs = sorted(glob.glob(f"{season_dir}/*.json.gz"))
        with ProcessPoolExecutor(6) as ex:
            dfs = list(ex.map(_shifts, fs, chunksize=25))
        write(pd.concat(dfs, ignore_index=True), f"nhl_shifts_{s}")
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
                                     updated=ln.get("lastUpdatedAt"), available=ln.get("available")))
        for per, ents in (e.get("results") or {}).items():
            for ent, stats in (ents or {}).items():
                for k, v in (stats or {}).items():
                    res.append(dict(eventID=eid, period=per, entity=ent, stat=k, value=v))
        for pid, p in players.items():
            res.append(dict(eventID=eid, period="_meta", entity=pid, stat="teamID", value=p.get("teamID")))
    return ev, odds, res


def curate_sgo():
    fs = sorted(glob.glob("data/raw/sgo_history/*.json.gz"))
    with ProcessPoolExecutor(4) as ex:
        res = list(ex.map(_sgo, fs))
    ev = pd.DataFrame([x for r in res for x in r[0]]).drop_duplicates("eventID", keep="last")
    write(ev, "sgo_events")
    od = pd.DataFrame([x for r in res for x in r[1]])
    od = od.drop_duplicates(["eventID", "oddID", "book", "alt", "line"], keep="last")
    od["odds"] = pd.to_numeric(od.odds, errors="coerce")
    od["line"] = pd.to_numeric(od.line, errors="coerce")
    od = od.merge(ev[["eventID", "startsAt"]], on="eventID", how="left")
    od["pregame"] = pd.to_datetime(od.updated, utc=True, errors="coerce") < pd.to_datetime(od.startsAt, utc=True)
    od = od.astype({c: "string" for c in od.columns if od[c].dtype == object})
    write(od, "sgo_odds")
    rs = pd.DataFrame([x for r in res for x in r[2]]).drop_duplicates(["eventID", "period", "entity", "stat"], keep="last")
    rs["value"] = rs["value"].astype("string")
    write(rs, "sgo_results")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("mp", "all"):
        curate_mp()
    if what in ("nhl", "all"):
        curate_nhl()
    if what in ("sgo", "all"):
        curate_sgo()
