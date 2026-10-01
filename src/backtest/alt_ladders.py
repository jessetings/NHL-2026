"""Alt-ladder pricing test: simulator vs a recreational book's pregame alt lines (bet365, 2026-01-17+).

Question: do books price alt totals / alt team totals / alt puck lines smoothly (Poisson-like) and so misprice
hockey's real shape (odd totals ~2x as common as even, EN goals piling margins at 3)?
Sim inputs: consensus close total + ML (clean from 2026-01-17). Book prices: last PREGAME update within
WINDOW_MIN minutes of puck drop (limits look-ahead from close info the stale price did not have).
Output: reports/alt_ladders_bets.csv, reports/alt_ladders_summary.md
Usage: python src/backtest/alt_ladders.py [book]
"""
import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from backtest.sim_games import CLEAN_FROM, ODDS, contracts, load, side_outcome, side_prob  # noqa: E402
from sim.grid import Grid  # noqa: E402

WINDOW_MIN = 90


def main(book="bet365"):
    o, res = load()
    res = res.drop_duplicates("eventID").set_index("eventID")
    G = Grid()
    c = duckdb.connect()
    b = c.execute(f"""
        select eventID, entity, bt, side, line, odds, updated, startsAt
        from '{ODDS}' where player is null and stat = 'points' and period = 'game' and alt and pregame
          and book = '{book}' and bt in ('ou', 'sp') and startsAt >= '{CLEAN_FROM}'
          and date_diff('minute', try_cast(updated as timestamp), try_cast(startsAt as timestamp)) <= {WINDOW_MIN}""").df()
    pms = {}
    for ev_id, ev in o.groupby("eventID"):
        cs = contracts(ev)
        if ev_id in res.index and "game|total" in cs and "game|ml" in cs:
            line, po = cs["game|total"]
            ph = cs["game|ml"][1]
            if 0.15 < po < 0.85 and 0.1 < ph < 0.9:
                pms[ev_id] = (G.solve(line, po, ph)[1]["final"], line)
    rows = []
    for r in b.itertuples():
        if r.eventID not in pms:
            continue
        pm, main_line = pms[r.eventID]
        g = res.loc[r.eventID]
        win, push = side_prob(pm, r.entity, r.bt, r.side, r.line)
        dec = 1 + (r.odds / 100 if r.odds > 0 else 100 / -r.odds)
        y = side_outcome(r.entity, r.bt, r.side, r.line, g.fh, g.fa)
        rows.append(dict(eventID=r.eventID, kind=("total" if r.entity == "all" else "team_total") if r.bt == "ou" else "spread",
                         entity=r.entity, side=r.side, line=r.line, odds=r.odds, implied=1 / dec, sim=win, push=push,
                         ev=win * dec + push - 1, pnl=0.0 if y is None else (dec - 1 if y == 1 else -1.0), y=y,
                         dist=(r.line - main_line) if r.entity == "all" and r.bt == "ou" else np.nan))
    X = pd.DataFrame(rows)
    X.to_csv("reports/alt_ladders_bets.csv", index=False)
    summary(X, book)


def summary(X, book):
    def roi_tbl(df, by):
        L = [f"| {by} | n prices | book ROI (all) | EV>3%: n | ROI | ±2se | EV>8%: n | ROI | ±2se |", "|---|---|---|---|---|---|---|---|---|"]
        for k, x in df.groupby(by):
            a, s8 = x[x.ev > 0.03], x[x.ev > 0.08]
            se = lambda z: 2 * z.pnl.std() / np.sqrt(len(z)) if len(z) > 1 else np.nan  # noqa: E731
            L.append(f"| {k} | {len(x)} | {x.pnl.mean():+.1%} | {len(a)} | {a.pnl.mean():+.1%} | {se(a):.1%} | "
                     f"{len(s8)} | {s8.pnl.mean():+.1%} | {se(s8):.1%} |")
        return L
    X = X.copy()
    X["price_band"] = pd.cut(X.odds, [-1e5, -300, -150, 100, 250, 600, 1e5],
                             labels=["<-300", "-300..-150", "-150..+100", "+100..+250", "+250..+600", ">+600"])
    t = X[X.kind == "total"].copy()
    t["parity"] = np.where(np.floor(t.line) % 2 == 0, "line k.5, k even (over needs odd+)", "line k.5, k odd (over needs even+)")
    L = [f"# Alt ladders: simulator vs {book} pregame (≤{WINDOW_MIN} min before puck drop, {CLEAN_FROM}+)", "",
         f"{X.eventID.nunique()} games, {len(X)} prices. Flat 1u per qualifying price, graded on final scores "
         "(OT/SO winner +1).", "", "## By market", ""] + roi_tbl(X, "kind")
    L += ["", "## By price band (all markets)", ""] + roi_tbl(X, "price_band")
    L += ["", "## By side", ""] + roi_tbl(X.assign(sd=X.kind + "/" + X.side.astype(str)), "sd")
    L += ["", "## Alt totals by line parity", ""] + roi_tbl(t, "parity")
    # calibration: does book implied or sim match outcome? (no-push rows)
    z = X[X.y.notna()]
    L += ["", "## Calibration (no-push rows)", "", "| Bucket (sim p) | n | actual | sim | book implied (with vig) |", "|---|---|---|---|---|"]
    for k, x in z.groupby(pd.cut(z.sim, [0, .05, .1, .2, .35, .5, .65, .8, .9, .95, 1])):
        L.append(f"| {k} | {len(x)} | {x.y.mean():.3f} | {x.sim.mean():.3f} | {x.implied.mean():.3f} |")
    out = "\n".join(L)
    print(out)
    open(f"reports/alt_ladders_summary_{book}.md", "w").write(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bet365")
