"""Per-game calibration + pricing with simulator v1.

solve_rates(): find home/away goalie-present rates so the simulated mean total and P(home win) match the
de-vigged market (total mean, home ML). Player inputs from props_all.csv (market-implied means):
  goal share = mkt_mean(G)/team goals, assist share = mkt_mean(A)/team goals, SOG share = mkt_mean(SOG)/team SOG.
Usage: python src/sim/price.py "NYI@TOR"
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from sim import engine as E  # noqa: E402


def solve_rates(total_mean, p_home, n=16384, key="solve", iters=8):
    """Fixed-point: scale overall rate to hit the total, shift the home/away log-ratio to hit P(home)."""
    base, lr = total_mean / 2.05, 0.04
    for _ in range(iters):
        h = dict(rate60=base * np.exp(lr), sog=29, players={})
        a = dict(rate60=base * np.exp(-lr), sog=29, players={})
        r = E.simulate(h, a, n=n, game_key=key)
        base *= total_mean / r["total"].mean()
        ph = np.clip(r["home_win"].mean(), 0.05, 0.95)
        lr += 0.25 * (np.log(p_home / (1 - p_home)) - np.log(ph / (1 - ph)))
        lr = float(np.clip(lr, -0.8, 0.8))
    return base * np.exp(lr), base * np.exp(-lr)


def team_inputs(pr, game, team, rate60, sog_team):
    t = pr[(pr.game == game) & (pr.team == team)]
    tt = t.drop_duplicates(["player", "market"]).copy()
    tt["mean"] = tt.mkt_mean.fillna(tt.model_mean)       # fall back to our model when no market line
    means = tt.pivot_table(index="player", columns="market", values="mean")
    goals_team = rate60 * 1.03
    players = {}
    for p, r in means.iterrows():
        players[p] = dict(g=float(np.nan_to_num(r.get("G", 0)) / goals_team),
                          a=float(np.nan_to_num(r.get("A", 0)) / goals_team),
                          s=float(np.nan_to_num(r.get("SOG", 0)) / sog_team))
    gs = sum(v["g"] for v in players.values())
    if gs > 0.95:
        for v in players.values():
            v["g"] *= 0.95 / gs
    ss = sum(v["s"] for v in players.values())
    if ss > 0.97:
        for v in players.values():
            v["s"] *= 0.97 / ss
    # v2: forward lines / D pairs from the latest DailyFaceoff snapshot
    units = {}
    try:
        sys.path.insert(0, "src")
        import model as M
        import slate as SL
        slug = {v: k for k, v in SL.SLUG.items()}.get(team)
        for pl in (M.load_lines().get(slug) or []):
            g = pl.get("group") or ""
            if g[:1] in ("f", "d") and g[1:].isdigit() and pl["name"] in players:
                units.setdefault(g, []).append(pl["name"])
    except Exception:  # noqa: BLE001
        units = {}
    return dict(rate60=rate60, sog=sog_team, players=players, units=units)


if __name__ == "__main__":
    game = sys.argv[1] if len(sys.argv) > 1 else "NYI@TOR"
    pr = pd.read_csv("cards/2026-09-30/props_all.csv")
    gm = pd.read_csv("cards/2026-09-30/game_model.csv").set_index("game")
    away, home = game.split("@")
    tm = {"NYI@TOR": (6.19, 0.542), "PIT@PHI": (6.26, 0.565), "LAK@COL": (6.29, 0.635)}[game]
    rh, ra = solve_rates(*tm)
    H = team_inputs(pr, game, home, rh, 29.5)
    A = team_inputs(pr, game, away, ra, 28.5)
    r = E.simulate(H, A, n=65536, game_key=game)
    print(f"{game}: rates {rh:.2f}/{ra:.2f}; total {r['total'].mean():.2f}; P(home) {r['home_win'].mean():.3f}")
    for side, T in (("home", H), ("away", A)):
        for p in sorted(T["players"], key=lambda x: -T["players"][x]["g"])[:5]:
            mk = pr[(pr.player == p) & (pr.market == "G") & (pr.line == 0.5) & (pr.side == "over")].mkt_p
            print(f"  {p:20s} AG sim {(r['G|' + p] >= 1).mean():.3f} mkt {mk.iloc[0] if len(mk) else float('nan'):.3f} | "
                  f"1+pt {((r['G|' + p] + r['A|' + p]) >= 1).mean():.3f} | 3+SOG {(r['S|' + p] >= 3).mean():.3f}")
