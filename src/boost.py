"""Profit-boost optimizer: best single or 2-leg cross-game parlay for a given book and boost %.

EV_boosted = p * (1 + b * (d - 1)) - 1, with p = most conservative of (model, market, blend) after bias
corrections. Parlay legs must each be +EV unboosted, from different games (independent), 15%+ implied each.
Usage: python src/boost.py --book draftkings --boost 0.5 [--max-win-mult 20] [--exclude-game NYI@TOR]
"""
import argparse
import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "market"))
from calibration import adjust  # noqa: E402

OUT = "cards/2026-09-30"


def load(book):
    pr = pd.read_csv(f"{OUT}/props_all.csv")
    pr = pr[pr.mkt_p.notna() & (pr.decision != "data-check") & (pr.book == book)].copy()
    for c in ("model_p", "mkt_p", "blend_p"):
        pr[c] = [adjust(m, s, ln, p) for m, s, ln, p in zip(pr.market, pr.side, pr.line, pr[c])]
    pr["p"] = pr[["model_p", "mkt_p", "blend_p"]].min(axis=1)
    pr["dec"] = np.where(pr.odds > 0, 1 + pr.odds / 100, 1 + 100 / -pr.odds)
    pr["ev"] = pr.p * pr.dec - 1
    pr["pick"] = pr.apply(lambda r: f"{r.player} {'O' if r.side == 'over' else 'U'}{r.line:g} {r.market}", axis=1)
    return pr.sort_values("ev", ascending=False).drop_duplicates(["player", "market", "line", "side"])


def main(book, boost, max_win_mult, exclude):
    pr = load(book)
    if exclude:
        pr = pr[~pr.game.isin(exclude)]
    pr = pr[pr.implied >= 0.15]
    pr["dec_b"] = 1 + boost * (pr.dec - 1) + (pr.dec - 1)
    pr["ev_b"] = pr.p * pr.dec_b - 1
    singles = pr.sort_values("ev_b", ascending=False).head(8)
    legs = pr[pr.ev > 0].to_dict("records")
    rows = []
    for a, b in itertools.combinations(legs, 2):
        if a["game"] == b["game"]:
            continue
        d = a["dec"] * b["dec"]
        db = 1 + (1 + boost) * (d - 1)
        if max_win_mult and db - 1 > max_win_mult:
            db = 1 + max_win_mult
        p = a["p"] * b["p"]
        rows.append(dict(ticket=f"{a['pick']} ({a['odds']:+d}) + {b['pick']} ({b['odds']:+d})", p=p, dec=d,
                         dec_boost=db, ev_boost=p * db - 1))
    par = pd.DataFrame(rows).sort_values("ev_boost", ascending=False).head(8) if rows else pd.DataFrame()
    print(f"== {book} {boost:.0%} profit boost: best singles (conservative p) ==")
    print(singles[["game", "pick", "odds", "p", "ev", "ev_b"]].round(3).to_string(index=False))
    if not par.empty:
        print("\n== best 2-leg cross-game parlays (each leg +EV unboosted) ==")
        print(par.round(3).to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="draftkings")
    ap.add_argument("--boost", type=float, default=0.5)
    ap.add_argument("--max-win-mult", type=float, default=0)
    ap.add_argument("--exclude-game", nargs="*", default=[])
    a = ap.parse_args()
    main(a.book, a.boost, a.max_win_mult, a.exclude_game)
