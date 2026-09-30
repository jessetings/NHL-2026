"""Quick same-game simulator for one game (v0): prices correlated goal-scorer / ML / total parlays.

Team regulation goals ~ Poisson(lambda) with a small shared Gamma pace factor; tied -> 3-on-3 OT (sudden death,
home wins 52%, ~70% decided in OT else shootout coin flip; OT goal credited to a scorer). Each goal is
assigned to a scorer multinomially using market-implied AG rates (de-vigged). Team lambdas solved so that
the de-vigged market total mean and P(home win) are matched.
Usage: python src/sgp_sim.py
"""
import numpy as np
import pandas as pd
from scipy import optimize

RNG = np.random.default_rng(20260930)
N = 400_000


def solve_lams(total_mean, p_home):
    def sim_phome(lh, la, n=200_000):
        r = np.random.default_rng(1)
        h, a = r.poisson(lh * 0.97, n), r.poisson(la * 0.97, n)
        tie = h == a
        return ((h > a) | (tie & (r.random(n) < 0.52))).mean()
    f = lambda d: sim_phome(total_mean / 2 + d, total_mean / 2 - d) - p_home  # noqa: E731
    d = optimize.brentq(f, -1.5, 1.5, xtol=1e-3)
    return total_mean / 2 + d, total_mean / 2 - d


def simulate(lam_home, lam_away, home_shares, pace_cv=0.08):
    """home_shares: dict player -> share of home goals (remainder = other). Returns dict of outcome arrays."""
    k = 1 / pace_cv ** 2
    pace = RNG.gamma(k, 1 / k, N)
    h = RNG.poisson(lam_home * 0.97 * pace)
    a = RNG.poisson(lam_away * 0.97 * pace)
    tie = h == a
    ot_goal = tie & (RNG.random(N) < 0.70)
    home_ot = ot_goal & (RNG.random(N) < 0.52)
    so_home = tie & ~ot_goal & (RNG.random(N) < 0.5)
    h_goals = h + home_ot
    names = list(home_shares)
    p = np.array([home_shares[n] for n in names] + [1 - sum(home_shares.values())])
    alloc = RNG.multinomial(1, p, size=(N,))  # placeholder shape for dtype
    counts = np.zeros((N, len(p)), dtype=np.int16)
    maxg = int(h_goals.max())
    for g in range(1, maxg + 1):
        idx = h_goals >= g
        pick = RNG.choice(len(p), size=idx.sum(), p=p)
        counts[np.where(idx)[0], pick] += 1
    out = {f"G_{n}": counts[:, i] for i, n in enumerate(names)}
    out["home_win"] = (h > a) | home_ot | so_home
    out["home_goals"] = h_goals
    out["total"] = h + a + ot_goal.astype(int) + (tie & ~ot_goal)  # shootout winner counts as a goal in totals
    del alloc
    return out


if __name__ == "__main__":
    pr = pd.read_csv("cards/2026-09-30/props_all.csv")
    g = pr[(pr.game == "NYI@TOR") & (pr.market == "G") & (pr.line == 0.5)].drop_duplicates("player")
    tor = g[g.team == "TOR"].set_index("player")
    total_mean, p_home = 6.19, 0.542   # de-vigged Pinnacle/consensus total mean; TOR ML no-vig
    lh, la = solve_lams(total_mean, p_home)
    shares = (tor.mkt_mean / lh).to_dict()
    s = sum(shares.values())
    if s > 0.95:
        shares = {k: v * 0.95 / s for k, v in shares.items()}
    out = simulate(lh, la, shares)
    print(f"lambda TOR {lh:.2f} NYI {la:.2f}; sim P(TOR win) {out['home_win'].mean():.3f}; "
          f"mean total {out['total'].mean():.2f}")
    for n in sorted(shares, key=shares.get, reverse=True)[:8]:
        print(f"  {n:20s} share {shares[n]:.3f}  P(AG) {(out['G_' + n] >= 1).mean():.3f}")
    np.save("/tmp/claude-0/-home-user-NHL-2026/c37923ec-3224-5428-bf6c-1d9bb89b0975/scratchpad/sim_ok.npy", [1])
