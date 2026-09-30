"""Grade a slate: results from NHL boxscores (+ play-by-play for first goal), CLV vs our last pregame snapshot.

Usage: python src/grade.py 2026-09-30
Outputs cards/<date>/graded_candidates.csv, graded_pyramid.csv, GRADE.md
"""
import glob
import os
import re
import sys
import unicodedata

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(__file__))
import odds as O  # noqa: E402

WEB = "https://api-web.nhle.com/v1"
MK = {"SOG": "sog", "G": "goals", "PTS": "points", "A": "assists"}
SGO_STAT = {"SOG": "shots_onGoal", "G": "points", "PTS": "goals+assists", "A": "assists"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def results(date):
    sched = requests.get(f"{WEB}/schedule/{date}", timeout=30).json()
    games = [g for g in sched["gameWeek"][0]["games"] if g["gameType"] == 2]
    rows, first_goal, status = [], {}, {}
    for g in games:
        gid = g["id"]
        box = requests.get(f"{WEB}/gamecenter/{gid}/boxscore", timeout=30).json()
        status[gid] = box["gameState"]
        game = f"{box['awayTeam']['abbrev']}@{box['homeTeam']['abbrev']}"
        roster = {}
        for side in ("awayTeam", "homeTeam"):
            team = box[side]["abbrev"]
            for grp in ("forwards", "defense"):
                for p in box.get("playerByGameStats", {}).get(side, {}).get(grp, []):
                    rows.append(dict(game=game, team=team, pid=p["playerId"], short=p["name"]["default"],
                                     sog=p.get("sog", 0), goals=p.get("goals", 0), assists=p.get("assists", 0),
                                     points=p.get("points", 0), toi=p.get("toi")))
                    roster[p["playerId"]] = p["name"]["default"]
        pbp = requests.get(f"{WEB}/gamecenter/{gid}/play-by-play", timeout=30).json()
        full = {}
        for sp in pbp.get("rosterSpots", []):
            full[sp["playerId"]] = f"{sp['firstName']['default']} {sp['lastName']['default']}"
        for pl in pbp.get("plays", []):
            if pl.get("typeDescKey") == "goal":
                first_goal[game] = full.get(pl["details"].get("scoringPlayerId"))
                break
        for r in rows:
            if r["game"] == game:
                r["name"] = full.get(r["pid"], r["short"])
    df = pd.DataFrame(rows)
    if df.empty:
        return df, first_goal, status
    df["key"] = df.name.map(norm)
    return df, first_goal, status


def closing(date):
    """Last pregame snapshot price per exact contract (book, oddID, line)."""
    fs = sorted(glob.glob(f"data/raw/snapshots/compact/*/*.parquet"))
    if not fs:
        return pd.DataFrame()
    s = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    s = s[pd.to_datetime(s.snap_ts) < pd.to_datetime(s.startsAt)]
    s["line"] = pd.to_numeric(s.line, errors="coerce")
    s["odds"] = pd.to_numeric(s.odds, errors="coerce")
    s = s.sort_values("snap_ts").drop_duplicates(["eventID", "oddID", "book", "line"], keep="last")
    return s


def main(date):
    out = f"cards/{date}"
    res, first_goal, status = results(date)
    done = {k for k, v in status.items() if v in ("OFF", "FINAL")}
    print("game states:", status)
    if res.empty:
        print("no boxscore data yet")
        return
    cand = pd.read_csv(f"{out}/props_all.csv")
    cand["key"] = cand.player.map(norm)
    cand = cand.merge(res[["key", "team", "sog", "goals", "assists", "points", "toi"]], on=["key", "team"], how="left")
    cand["actual"] = [getattr(r, MK[r.market]) if not pd.isna(getattr(r, MK[r.market])) else np.nan
                      for r in cand.itertuples()]
    finished_games = {g for g in res.game.unique()}
    cand["settled"] = cand.actual.notna()
    over = cand.actual > cand.line
    cand["win"] = np.where(cand.side == "over", over, ~over).astype(float)
    cand.loc[~cand.settled, "win"] = np.nan
    cand["dec"] = cand.odds.map(lambda o: 1 + (o / 100 if o > 0 else 100 / -o))
    cand["pnl_per_unit"] = np.where(cand.win == 1, cand.dec - 1, -1.0)
    cand.loc[~cand.settled, "pnl_per_unit"] = np.nan

    # CLV vs last pregame snapshot at same book/line/side
    cl = closing(date)
    if not cl.empty:
        cand["oddID"] = [f"{SGO_STAT[m]}-{e}-game-ou-{s}" for m, e, s in
                         zip(cand.market, cand.player.map(lambda p: p), cand.side)]
        # map player name -> SGO entity via the odds snapshot used for the card
        snap = sorted(glob.glob("data/raw/odds/sgo_slate_alt_*.json"))[-1]
        f = O.flatten(snap)[["player", "entity"]].dropna().drop_duplicates()
        cand = cand.drop(columns="oddID").merge(f, on="player", how="left")
        cand["oddID"] = [f"{SGO_STAT[m]}-{e}-game-ou-{s}" for m, e, s in zip(cand.market, cand.entity, cand.side)]
        cl = cl.rename(columns={"odds": "close_odds"})[["oddID", "book", "line", "close_odds"]]
        cand = cand.merge(cl, on=["oddID", "book", "line"], how="left")
        cand["clv_prob"] = cand.close_odds.map(lambda o: O.american_to_prob(o) if pd.notna(o) else np.nan) - \
            cand.implied
    cand.to_csv(f"{out}/graded_candidates.csv", index=False)

    s = cand[cand.settled]
    L = [f"# Grade — {date}", "", f"Game states: {status}", ""]
    if not s.empty:
        # proper scores on unique contracts (best-price row per player/market/line/side)
        u = s.sort_values("ev", ascending=False).drop_duplicates(["player", "market", "line", "side"])
        u = u[u.side == "over"]
        L += ["## Forecast quality (all over-contracts offered, not just bets)", "",
              "| Forecast | Brier | Log-loss | n |", "|---|---|---|---|"]
        for col in ("model_p", "mkt_p", "blend_p", "implied"):
            p = u[col].clip(1e-4, 1 - 1e-4)
            y = u.win
            L.append(f"| {col} | {((p - y) ** 2).mean():.4f} | {-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean():.4f} | {len(u)} |")
        L.append("")

    # pyramid picks
    pq = pd.read_csv(f"{out}/quarry_inspected.csv") if os.path.exists(f"{out}/quarry_inspected.csv") else None
    py = []
    for fname, col in (("pyramid_singles.csv", "stake"),):
        if os.path.exists(f"{out}/{fname}"):
            p = pd.read_csv(f"{out}/{fname}")
            p["key"] = p.player.map(norm)
            p = p.merge(cand[["player", "market", "line", "side", "actual", "win", "settled"]].drop_duplicates(
                ["player", "market", "line", "side"]), on=["player", "market", "line", "side"], how="left")
            p["pnl"] = np.where(p.win == 1, p[col] * (p.dec - 1), -p[col])
            p.loc[p.settled != True, "pnl"] = np.nan  # noqa: E712
            py.append(p)
    if py:
        p = pd.concat(py)
        p.to_csv(f"{out}/graded_quarry.csv", index=False)
        L += ["## Quarry (raw materials) results", "", "| Tier | Pick | Price | Actual | Result | Stake | P&L |",
              "|---|---|---|---|---|---|---|"]
        for r in p.itertuples():
            res_txt = "pending" if pd.isna(r.win) else ("WIN" if r.win == 1 else "loss")
            act = "" if pd.isna(r.actual) else int(r.actual)
            pnl = "" if pd.isna(r.pnl) else f"{r.pnl:+.2%}"
            L.append(f"| {r.tier} | {r.pick} | {r.book[:2].upper()} {r.odds:+d} | {act} | {res_txt} | {r.stake:.2%} | {pnl} |")
        settled = p[p.pnl.notna()]
        L += ["", f"**Quarry singles settled:** {len(settled)}, P&L {settled.pnl.sum():+.2%} of bankroll on "
              f"{settled.stake.sum():.2%} staked (ROI {settled.pnl.sum() / max(settled.stake.sum(), 1e-9):+.1%}).", ""]
    L += ["## First goal scorers", "", *(f"- {g}: {n}" for g, n in first_goal.items()), ""]
    open(f"{out}/GRADE.md", "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2026-09-30")
