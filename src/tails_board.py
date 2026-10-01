"""Tails board: alt game totals, team totals and alt puck lines priced by simulator v2 vs live DK/FD/Pinnacle.

Research (digest 04 + our data): books' margin concentrates on the YES/over side of rare outcomes; hockey totals are
underdispersed vs Poisson; OT/SO winner adds +1 (odd-total spike); empty-net goals pile margins at exactly 3.
The simulator reproduces those shapes (docs/findings/2026-09-30_simulator_v1_validation.md).
Usage: python src/tails_board.py [--date YYYY-MM-DD]
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import odds as O  # noqa: E402
import slate as SL  # noqa: E402
from sim import engine as E  # noqa: E402
from sim.price import solve_rates  # noqa: E402

BOOKS = ("draftkings", "fanduel")


def dec(o):
    return 1 + (o / 100 if o > 0 else 100 / -o)


def main(date):
    snap = O.latest_snapshot()
    df = O.flatten(snap)
    markets = SL.game_markets(df)
    g = df[(df.stat == "points") & df.book.isin(BOOKS + ("pinnacle",)) & df.line.notna()]
    rows = []
    for ev_id, x in g.groupby("eventID"):
        home, away = SL.SGO_TEAM.get(x.home.iloc[0]), SL.SGO_TEAM.get(x.away.iloc[0])
        game = f"{away}@{home}"
        if game not in markets:
            continue
        tot, ph = markets[game]
        rh, ra = solve_rates(tot, ph)
        r = E.simulate(dict(rate60=rh, sog=29, players={}), dict(rate60=ra, sog=29, players={}), n=131072,
                       game_key=f"tails|{game}")
        hg, ag, tg = r["home_goals"].astype(int), r["away_goals"].astype(int), r["total"].astype(int)
        # team totals: OT/SO winner +1 to the winner's team total (DK/FD rules); our *_goals include OT goals,
        # add the shootout winner's goal
        so = r["reg_tie"] & (r["home_goals"] == r["away_goals"])
        hg_t = hg + (so & r["home_win"])
        ag_t = ag + (so & ~r["home_win"])
        margin = hg_t - ag_t
        for row in x[~x.oddID.str.contains("-reg-")].itertuples():
            if row.book not in BOOKS:
                continue
            if row.bt == "ou" and row.entity == "all":
                v, kind = tg, "Game total"
            elif row.bt == "ou" and row.entity in ("home", "away"):
                v, kind = (hg_t if row.entity == "home" else ag_t), f"{home if row.entity == 'home' else away} team total"
            elif row.bt == "sp":
                v, kind = (margin if row.side == "home" else -margin), f"{home if row.side == 'home' else away} puck line"
            else:
                continue
            ln = float(row.line)
            if row.bt == "sp":
                win, push = (v + ln > 0).mean(), (v + ln == 0).mean()
            elif row.side == "over":
                win, push = (v > ln).mean(), (v == ln).mean()
            else:
                win, push = (v < ln).mean(), (v == ln).mean()
            d = dec(row.odds)
            rows.append(dict(game=game, market=kind, side=row.side if row.bt == "ou" else f"{ln:+g}",
                             line=ln, book=row.book, odds=int(row.odds), implied=1 / d, sim_p=win, push=push,
                             ev=win * d + push - 1, tail=win < 0.25 or win > 0.75))
    t = pd.DataFrame(rows)
    out = f"cards/{date}"
    os.makedirs(out, exist_ok=True)
    t.to_csv(f"{out}/tails_all.csv", index=False)
    best = t.sort_values("ev", ascending=False).drop_duplicates(["game", "market", "side", "line"])
    L = [f"# Tails Board — {date}", "",
         f"_Snapshot {os.path.basename(snap)}. Simulator v2 (131k sims/game) calibrated to each game's de-vigged "
         "total and moneyline. EV at the best DK/FD price. **Tail longshot 'yes'/over sides are where books put the "
         "most margin** (hist. first-goal-scorer +4000: −47% ROI; alt total over 11.5 @+3600: −40% EV), so the "
         "positive-EV list is usually unders/'no' sides or mid-ladder mispricings._", "",
         "## Best EV (any side)", "", "| Game | Market | Side | Book | Price | Sim p | EV |", "|---|---|---|---|---|---|---|"]
    for r in best.head(15).itertuples():
        L.append(f"| {r.game} | {r.market} | {r.side} {'' if 'puck' in r.market else f'{r.line:g}'} | {r.book[:2].upper()} | "
                 f"{r.odds:+d} | {r.sim_p:.1%} | {r.ev:+.1%} |")
    L += ["", "## Worst EV (the tail tax — avoid)", "", "| Game | Market | Side | Book | Price | Sim p | EV |",
          "|---|---|---|---|---|---|---|"]
    for r in t.sort_values("ev").head(8).itertuples():
        L.append(f"| {r.game} | {r.market} | {r.side} {'' if 'puck' in r.market else f'{r.line:g}'} | {r.book[:2].upper()} | "
                 f"{r.odds:+d} | {r.sim_p:.1%} | {r.ev:+.1%} |")
    open(f"{out}/TAILS.md", "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=SL.DATE)
    main(ap.parse_args().date)
