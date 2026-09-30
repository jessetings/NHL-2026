# Simulator v1: calibration and validation (2026-09-30)

- Code: `src/sim/fit.py` (empirical inputs → `data/curated/sim/params.json`), `src/sim/engine.py` (engine), `src/sim/price.py` (per-game calibration and pricing).
- Speed: 65,536 sims per game in ~1 s. Common random numbers seeded per game key.

## Empirical inputs (2023–26 regular season, 3,941 games) vs research
| Input | Ours | Research |
|---|---|---|
| Empty-net goals per game | 0.376 | 0.34–0.40 |
| Games reaching OT | 22.1% | 20.7–24.8% |
| OT-decided share | 68.1% | 63.5–71.6% |
| OT home win | 52.4% | 50–57% |
| P2 scoring vs P1 | +20% | +16–17% |
| P3 leader rate vs trailer | −10% | −10 to −15% |
| Goals per 60: into the empty net / by the extra attacker | 14.5 / 6.4 | 12–19 / ~6.5 |

## Game-level validation (league-average teams)
| | Total | Var/mean | Corr(home, away) | Regulation tie | EN/game | Home win |
|---|---|---|---|---|---|---|
| Empirical | 6.19 | 0.863 | −0.123 | 0.221 | 0.376 | 0.542 |
| Sim v1 | 6.36* | 0.839 | −0.126 | 0.218 | 0.390 | 0.541 |

\* The total is solved to the market per game. Knobs: possession split sd 0.08, post-goal cooldown ×0.5 for 60 s, EN scale 1.3, pace cv 0.03.

## Same-game player validation (teammates, top-4 TOI, 2024–26)
| Correlation | Empirical | Sim |
|---|---|---|
| Goals–goals | −0.002 | −0.003 |
| Points–points | 0.141 | 0.157 |
| SOG–SOG | 0.089 | ~0.07 (with team SOG sd 7.3 vs 6.6) |
| Player goals vs rest-of-team goals | −0.074 | −0.007 |

## Bug found and fixed during calibration
`np.vectorize` inferred an int output from the first simulation. That zeroed pull probabilities at random and made home/away asymmetric (pulled time 0.74 → 1.43 min/game after the fix; empirical 1.35).

## Per-game market fit (Sept 30)
- The solver matches the de-vigged total and ML: NYI@TOR 6.18 / 53.8%, PIT@PHI 6.25 / 56.1%, LAK@COL 6.29 / 63.4%.
- AG from the sim is within ~1 pt of the de-vigged market for TOR, NYI and COL.
- PHI players' market AG prices sum to **more goals than the team is expected to score**. The sim scales them down 2–3 pts: direct evidence of AG-board overpricing.

## Known limitations → v2
- Line-level shot and assist allocation (linemate correlation). Needed for SOG-pair and points SGPs.
- A persistent pull-state model.
- Rest-of-team goal dependence.
- Players without market lines use the model mean (some missing SOG shares, e.g. Foerster).
