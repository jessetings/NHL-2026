"""Empirical market-bias corrections (probability points) from historical closes vs outcomes.

SOG overs: de-vigged closes (DK/FD/Pinnacle per-book 2026-01..06, and consensus 2024-26) overstate the over
hit-rate, growing with the rung. Measured on ~9k per-book and ~26k consensus contracts (reports/…, 2026-09-30).
Negative = subtract from P(over); unders get the mirror adjustment.
"""
SOG_OVER_BIAS = {0.5: -0.02, 1.5: -0.013, 2.5: -0.022, 3.5: -0.037, 4.5: -0.05, 5.5: -0.05, 6.5: -0.05}


# Assists 1+: DK close overstates by 1.7 pts, Pinnacle by 0.9 (2026 per-book closes, ~10k contracts).
# AG and points 1+: Pinnacle/DK closes calibrated within ~0.5 pt -> no correction.
AST_OVER_BIAS = {0.5: -0.012}


def adjust(market, side, line, p):
    if market == "A":
        b = AST_OVER_BIAS.get(line, 0.0)
        return p + b if side == "over" else p - b
    if market != "SOG":
        return p
    b = SOG_OVER_BIAS.get(line, -0.05 if line > 4 else 0.0)
    return p + b if side == "over" else p - b
