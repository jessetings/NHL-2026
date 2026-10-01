"""Same-game parlay menu from simulator v1: correlation-aware fair prices and minimum acceptable SGP quotes.

Books' SGP quotes are not in our odds feed, so for every combo we publish:
  p_joint (simulated), p_indep (product of legs), lift = p_joint / p_indep, fair odds,
  min quote to bet = fair x (1 + cushion), and the same with a 50% profit boost.
Legs: anytime goal (top scorers), 1+/2+ points, 3+ SOG, team ML, team 4+ goals, game over 5.5 / under 6.5, FGS.
Usage: python src/sgp_card.py [--date 2026-09-30]
"""
import os
import argparse
import itertools
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from sim import engine as E  # noqa: E402
import slate as SL  # noqa: E402
from sim.price import solve_rates, team_inputs  # noqa: E402

CUSHION = 0.10


def amer(x):
    return f"+{(x - 1) * 100:.0f}" if x >= 2 else f"{-100 / (x - 1):.0f}"


def legs_for(r, H, A, home, away):
    legs = {f"{home} ML": r["home_win"], f"{away} ML": ~r["home_win"],
            f"{home} 4+ goals": r["home_goals"] >= 4, f"{away} 4+ goals": r["away_goals"] >= 4,
            "Over 5.5": r["total"] >= 6, "Under 6.5": r["total"] <= 6}
    for T in (H, A):
        top = sorted(T["players"], key=lambda k: -T["players"][k]["g"])[:4]
        for p in top:
            legs[f"{p} AG"] = r[f"G|{p}"] >= 1
            legs[f"{p} 2+ pts"] = (r[f"G|{p}"] + r[f"A|{p}"]) >= 2
        for p in sorted(T["players"], key=lambda k: -T["players"][k]["s"])[:3]:
            legs[f"{p} 3+ SOG"] = r[f"S|{p}"] >= 3
    return legs


def main(date):
    pr = pd.read_csv(f"cards/{date}/props_all.csv")
    L = [f"# Same-Game Parlay Menu — {date}", "",
         "_Simulator v3 (validated vs 3,941 games; full dressed roster, on-ice assist structure). p_joint is the simulated probability that all legs hit; lift > 1 "
         "means the legs help each other (books' naive multiplication would undervalue the combo). "
         f"**Only bet if the book's SGP quote is at or above 'Min quote'** (fair + {CUSHION:.0%} cushion)._", ""]
    import odds as O
    markets = SL.game_markets(O.flatten(O.latest_snapshot()))
    games_today = set(pr.game.unique())
    for game, (tot, ph) in markets.items():
        if game not in games_today:
            continue
        away, home = game.split("@")
        rh, ra = solve_rates(tot, ph)
        H = team_inputs(pr, game, home, rh, 29.5)
        A = team_inputs(pr, game, away, ra, 28.5)
        r = E.simulate(H, A, n=65536, game_key=game)
        legs = legs_for(r, H, A, home, away)
        rows = []
        for k in (2, 3):
            for c in itertools.combinations(legs, k):
                if sum(1 for x in c if x.endswith("ML")) > 1 or ("Over 5.5" in c and "Under 6.5" in c):
                    continue
                # no nested same-player legs (AG + own 2+ pts is mechanical; books price it)
                pl = [re.sub(r" (AG|2\+ pts|3\+ SOG)$", "", x) for x in c if x.endswith(("AG", "pts", "SOG"))]
                if len(pl) != len(set(pl)):
                    continue
                pj = np.logical_and.reduce([legs[x] for x in c]).mean()
                pi = np.prod([legs[x].mean() for x in c])
                if pj < 0.04 or pj > 0.5:
                    continue
                fair = 1 / pj
                rows.append(dict(combo=" + ".join(c), p=pj, lift=pj / pi, fair=fair,
                                 min_q=fair * (1 + CUSHION), min_q_boost=1 + (fair * (1 + CUSHION) - 1) / 1.5))
        df = pd.DataFrame(rows)
        fg = sorted(((k[3:], v.mean()) for k, v in r.items() if k.startswith("FG|")), key=lambda x: -x[1])[:5]
        L += [f"## {game} — sim total {r['total'].mean():.2f}, P({home}) {r['home_win'].mean():.1%}", "",
              "**Highest-correlation combos (biggest edge over naive pricing):**", "",
              "| Combo | Hit % | Lift | Fair | Min quote | Min quote w/ 50% boost |", "|---|---|---|---|---|---|"]
        for x in df.sort_values("lift", ascending=False).head(6).itertuples():
            L.append(f"| {x.combo} | {x.p:.1%} | {x.lift:.2f}x | {amer(x.fair)} | {amer(x.min_q)} | {amer(x.min_q_boost)} |")
        L += ["", "**Fun longshots (4-10% hit, correlated):**", "",
              "| Combo | Hit % | Lift | Fair | Min quote |", "|---|---|---|---|---|"]
        ls = df[(df.p >= 0.04) & (df.p <= 0.10) & (df.lift >= 1.3)].sort_values("lift", ascending=False).head(4)
        for x in ls.itertuples():
            L.append(f"| {x.combo} | {x.p:.1%} | {x.lift:.2f}x | {amer(x.fair)} | {amer(x.min_q)} |")
        L += ["", "First goal scorer (sim): " + ", ".join(f"{p} {v:.1%} (fair {amer(1 / v)})" for p, v in fg), ""]
    open(f"cards/{date}/SGP_MENU.md", "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=SL.DATE)
    main(ap.parse_args().date)
