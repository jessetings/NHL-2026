"""Rate grid: precomputed team-level score distributions for instant game-level pricing.

The simulator's team-level output depends only on (home rate60, away rate60). We simulate a grid over
base = sqrt(rh*ra) and lr = 0.5*log(rh/ra), store joint score PMFs, and price any game in milliseconds by
bilinear interpolation + a 2-parameter solve to the market (main total and moneyline).

Stored per grid point (book scoring = OT/SO winner +1):
  final[h, a]  final score PMF            reg[h, a]   regulation (60 min) score PMF
  p1/p2/p3[h, a] per-period score PMFs     first[3]   P(home scores first, away first, no goal)
Usage:
  python src/sim/grid.py build            # ~4 min on 4 cores -> data/curated/sim/grid.npz
  python src/sim/grid.py demo 6.0 -110 -110 -150 +130
"""
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy import optimize

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from sim import engine as E  # noqa: E402

PATH = "data/curated/sim/grid.npz"
BASES = np.round(np.arange(2.0, 4.45, 0.1), 3)
LRS = np.round(np.arange(-0.7, 0.701, 0.05), 3)
K, KP = 16, 8           # max goals per team (final/reg), per period
N = 131072


def _pmf2(h, a, k):
    m = np.zeros((k, k))
    np.add.at(m, (np.clip(h, 0, k - 1), np.clip(a, 0, k - 1)), 1)
    return m / len(h)


def _point(args):
    b, lr = args
    r = E.simulate(dict(rate60=b * np.exp(lr), sog=29, players={}), dict(rate60=b * np.exp(-lr), sog=29, players={}),
                   n=N, game_key="grid")      # common random numbers across the grid -> smooth surface
    out = dict(final=_pmf2(r["home_final"], r["away_final"], K), reg=_pmf2(r["home_reg"], r["away_reg"], K))
    for p in (1, 2, 3):
        out[f"p{p}"] = _pmf2(r[f"home_p{p}"], r[f"away_p{p}"], KP)
    out["first"] = np.array([(r["first_team"] == 1).mean(), (r["first_team"] == 2).mean(), (r["first_team"] == 0).mean()])
    return out


def build():
    pts = [(b, lr) for b in BASES for lr in LRS]
    with ProcessPoolExecutor(os.cpu_count()) as ex:
        res = list(ex.map(_point, pts, chunksize=4))
    arr = {k: np.stack([x[k] for x in res]).reshape(len(BASES), len(LRS), *res[0][k].shape) for k in res[0]}
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    np.savez_compressed(PATH, bases=BASES, lrs=LRS, **arr)
    print(f"grid {len(BASES)}x{len(LRS)} saved -> {PATH}")


class Grid:
    def __init__(self, path=PATH):
        z = np.load(path)
        self.bases, self.lrs = z["bases"], z["lrs"]
        self.t = {k: z[k] for k in z.files if k not in ("bases", "lrs")}

    def at(self, b, lr):
        """Bilinearly interpolated PMFs at (base, log-ratio)."""
        i = np.clip(np.searchsorted(self.bases, b) - 1, 0, len(self.bases) - 2)
        j = np.clip(np.searchsorted(self.lrs, lr) - 1, 0, len(self.lrs) - 2)
        u = np.clip((b - self.bases[i]) / (self.bases[i + 1] - self.bases[i]), 0, 1)
        v = np.clip((lr - self.lrs[j]) / (self.lrs[j + 1] - self.lrs[j]), 0, 1)
        return {k: (1 - u) * (1 - v) * T[i, j] + u * (1 - v) * T[i + 1, j] + (1 - u) * v * T[i, j + 1] + u * v * T[i + 1, j + 1]
                for k, T in self.t.items()}

    def solve(self, total_line, p_over, p_home):
        """(base, lr) whose final-score PMF matches P(over total_line | no push) and P(home wins)."""
        def resid(x):
            d = self.at(*x)
            tot = total_dist(d["final"])
            k = np.arange(len(tot))
            over, push = tot[k > total_line].sum(), tot[k == total_line].sum()
            po = np.clip(over / max(1 - push, 1e-9), 1e-4, 1 - 1e-4)
            ph = np.clip(home_win(d["final"]), 1e-4, 1 - 1e-4)
            return [np.log(po / (1 - po)) - np.log(p_over / (1 - p_over)), np.log(ph / (1 - ph)) - np.log(p_home / (1 - p_home))]
        x0 = np.clip([total_line / 2.05, 0.5 * np.log(p_home / (1 - p_home)) * 0.45],
                     [self.bases[0] + 1e-6, self.lrs[0] + 1e-6], [self.bases[-1] - 1e-6, self.lrs[-1] - 1e-6])
        s = optimize.least_squares(resid, x0, bounds=([self.bases[0], self.lrs[0]], [self.bases[-1], self.lrs[-1]]))
        return s.x, self.at(*s.x)


# ---------------------------------------------------------------- PMF helpers
def total_dist(m):
    k = m.shape[0]
    out = np.zeros(2 * k - 1)
    for h in range(k):
        out[h:h + k] += m[h]
    return out


def margin_dist(m):
    """P(home - away = d), index d + (k-1)."""
    k = m.shape[0]
    out = np.zeros(2 * k - 1)
    for h in range(k):
        for a in range(k):
            out[h - a + k - 1] += m[h, a]
    return out


def home_win(m):
    return float(np.tril(m, -1).sum())


def prob(d, market, side, line):
    """Win probability (push excluded from both win and loss -> returns (win, push))."""
    if market == "total":
        dist, kk = total_dist(d), np.arange(2 * d.shape[0] - 1)
    elif market in ("home_tt", "away_tt"):
        dist = d.sum(1) if market == "home_tt" else d.sum(0)
        kk = np.arange(len(dist))
    elif market == "home_spread":                    # home +line covers if margin + line > 0
        dist, kk = margin_dist(d), np.arange(2 * d.shape[0] - 1) - (d.shape[0] - 1)
        return float(dist[kk + line > 0].sum()), float(dist[kk + line == 0].sum())
    else:
        raise ValueError(market)
    if side == "over":
        return float(dist[kk > line].sum()), float(dist[kk == line].sum())
    return float(dist[kk < line].sum()), float(dist[kk == line].sum())


def _p(o):
    o = float(o)
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build()
    else:
        line, o, u, h, a = map(float, sys.argv[2:7])
        g = Grid()
        po = _p(o) / (_p(o) + _p(u))
        ph = _p(h) / (_p(h) + _p(a))
        x, d = g.solve(line, po, ph)
        td = total_dist(d["final"])
        print(f"base {x[0]:.3f} lr {x[1]:+.3f} | mean total {np.dot(np.arange(len(td)), td):.2f} | P(home) {home_win(d['final']):.3f}")
        for L in (4.5, 5.5, 6.5, 7.5, 8.5, 9.5):
            print(f"  total o{L}: {prob(d['final'], 'total', 'over', L)[0]:.3f}")
        for L in (-1.5, -2.5, -3.5, 1.5):
            print(f"  home {L:+}: {prob(d['final'], 'home_spread', None, L)[0]:.3f}")
