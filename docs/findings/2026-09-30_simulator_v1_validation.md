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

## v2 (2026-10-01): line-level structure
- **Forward lines and D pairs** come from DailyFaceoff. Each unit gets a per-game "unit night" multiplier (gamma, cv 0.25) shared by linemates.
- **Assists** go to the scorer's forward linemates with weight ×10.
- **Player SOG** is Poisson–gamma: team non-goal SOG × share × unit multiplier × pace × score effect × team shot-night (cv 0.15).
- **Empirical linemate targets** (2025-26, 12,202 pairs identified from shift co-starts): points corr **0.457**, SOG **0.129**, goals 0.021.

| Correlation | Empirical | v1 | v2 |
|---|---|---|---|
| Linemate points | 0.457 | ~0.16 (no line structure) | **0.346** |
| Linemate SOG | 0.129 | ~0.07 | **0.10–0.12** |
| Teammate (top-4) points | 0.141 | 0.157 | 0.160 |
| Teammate (top-4) SOG | 0.089 | ~0.07 | 0.04–0.07 |
| Team SOG sd | 6.6 | 7.3 | 6.8–7.7 |

- Marginals are unchanged: AG within 0.5 pt of the de-vigged market.
- **Remaining gap:** linemate points are understated because lines are only partially represented, since players without props are absent from the player list (e.g. Marchenko). v3: include the full dressed roster from the NHL `rosterSpots` with model-based shares.

## v3 (2026-10-01): full dressed roster + on-ice assist structure + two marginal bugs fixed
**Changes**
- **Full dressed roster**: every DailyFaceoff line/pair member is in the sim. Players without props get model means (shrunk MoneyPuck rates × TOI) but only take the *residual* goal/assist/SOG share left by priced players, so market marginals are untouched (`src/sim/price.py`).
- **Per-stat fallback**: a player with a goal prop but no assist/SOG prop now gets the model mean for the missing stat. Before, the missing stat was 0. On thin-market slates (Oct 1 preview) that zeroed assists for Kaprizov, Forsberg, Josi and others, so their simulated points were goals-only.
- **On-ice assist structure**: when a forward scores, assists go to the two linemates (×30) and D (×(1 + 29/3), since a given pair is on ice with a line ~1/3 of the time); other forwards ×1.
- **Marginal-preserving assists (IPF)**: pre-weights are solved so each player's expected assists equal their target share, whatever the boost structure. The structure then moves correlation only.

**Bugs found**
1. In v2, D received only **51%** of their target assists, because the linemate boost starved them. **Sim D points/assists legs were underpriced in SGPs.**
2. The unnamed-pool assist weight `2·(1 − Σa/2)` was too large, so named players got **~78% of target assists** (v1 and v2). The new pool weight is `A_PER_GOAL − Σa`, with A_PER_GOAL = 1.685: NHL assists per goal, stable at 1.683–1.689 for 2022–26. `A_PROBS = (0.925, 0.76)`.

**Validation (Sept 30 inputs, 3 games, 65k sims)**

| Metric | Empirical | v2 | v3 |
|---|---|---|---|
| Linemate points corr | 0.457 | 0.29–0.35 | **0.432** |
| Linemate SOG corr | 0.129 | 0.08–0.12 | **0.129** |
| Linemate goals corr | 0.021 | 0.008 | 0.010 |
| Top-4 teammate points | 0.141 | 0.16 | 0.190 (slightly high) |
| Top-4 teammate SOG | 0.089 | 0.04–0.07 | 0.058 |
| Team SOG sd | 6.6 (incl. between-game mean variation) | 6.8–7.7 | 7.2 |
| Assists sim/target (D / F) | 1.00 | **0.51 / 1.08** | **0.99 / 1.00** |
| AG sim − de-vigged market | 0 | −0.009 | −0.012 |
| 2+ goals sim − market | 0 | — | −0.001 |
| 1+ point sim − market | 0 | — | −0.019 (consistent with the public-over tax on points overs) |

Knobs: `LINEMATE_W=30`, `LINEMATE_D_FRAC=1/3`, `UNIT_CV=0.28`, `TEAM_SOG_CV=0.13`.
