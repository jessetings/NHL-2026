"""De-vig methods for two-way and multi-way markets.

All functions take implied probabilities (with vig) and return fair probabilities summing to 1.
"""
import numpy as np
from scipy import optimize


def american_to_prob(o):
    o = np.asarray(o, dtype=float)
    return np.where(o > 0, 100 / (o + 100), -o / (-o + 100))


def prob_to_american(p):
    p = np.asarray(p, dtype=float)
    return np.where(p >= 0.5, -100 * p / (1 - p), 100 * (1 - p) / p)


def multiplicative(q):
    q = np.asarray(q, float)
    return q / q.sum()


def additive(q):
    q = np.asarray(q, float)
    return q - (q.sum() - 1) / len(q)


def power(q):
    """Find k with sum(q_i^k) = 1 (favourite-longshot aware)."""
    q = np.asarray(q, float)
    k = optimize.brentq(lambda k: (q ** k).sum() - 1, 0.5, 5)
    return q ** k


def shin(q):
    """Shin (1993) insider-trading model; z = proportion of insider money."""
    q = np.asarray(q, float)
    s = q.sum()

    def fair(z):
        return (np.sqrt(z ** 2 + 4 * (1 - z) * q ** 2 / s) - z) / (2 * (1 - z))

    z = optimize.brentq(lambda z: fair(z).sum() - 1, 0, 0.99)
    return fair(z)


def two_way(over_odds, under_odds, method="multiplicative"):
    """Vectorised two-way de-vig for arrays of American odds -> fair P(over)."""
    qo, qu = american_to_prob(over_odds), american_to_prob(under_odds)
    if method == "multiplicative":
        return qo / (qo + qu)
    if method == "additive":
        return qo - (qo + qu - 1) / 2
    out = np.full(len(qo), np.nan)
    f = {"power": power, "shin": shin}[method]
    for i, (a, b) in enumerate(zip(qo, qu)):
        if np.isfinite(a) and np.isfinite(b):
            out[i] = f([a, b])[0]
    return out
