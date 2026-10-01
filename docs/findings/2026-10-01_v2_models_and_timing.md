# Findings: shot-quality and strength-split models v2, and why timing matters (2026-10-01)

## 0. Data integrity
- **SGO consensus `close_fair` before 2026-01-17 is often captured in-game.**
  - Game moneyline log-loss on those prices is 0.25–0.46, where an honest pregame price gives about 0.67.
  - Up to half of the games have prices beyond 10/90.
  - The effect is small for player props (1–3% extreme rows in Oct–Jan 2025-26).
  - All game-level market benchmarks now use only 2026-01-17 onward. H3 already preferred per-book close prices.
- **Name collisions:** VAN has two Elias Petterssons (a forward and a defenseman). History and v2 now match players by position against the DailyFaceoff unit. An ambiguous name gets no data and a forced data-check.

## 1. Feature store (`src/features/shotq.py`, as-of, 2023-24 onward)
- MoneyPuck shot-level data: 453k unblocked attempts.
- **High danger** means xG ≥ 0.20, MoneyPuck's own definition.
- **Strength** (EV / PP / SH) is taken from the shooter's skater count. Empty-net shots are excluded from rates.
- **Player features:** per-60 rates for EV and PP separately (SOG, attempts, xG, HD attempts, HD xG, goals, assists, rush, rebound). They are EWMAs (half-life 30 games) shrunk to F/D priors. Also included: finishing (G+64)/(xG+64), HD share, and SOG per attempt.
- **Team features:** EV for and against per 60, PP for per 60, PK against per 60, and PP/PK time per game. League levels check out: EV SOG/60 27.7, EV xG/60 2.54, PP time 4.1 min/game.
- **Goalie features:** GSAx per 100 shots, and HD goals saved above expected.
- **Next-game rows** (sentinel `game_id` 9999999999) hold the features as of all games played. They're used live.

## 2. Prop model v2 (`src/models/props_v2.py`): out-of-sample on 2025-26, 46k player-games
| Market | Δ log-loss vs v1 (×1000) |
|---|---|
| SOG | −4.0 ± 1.4 |
| Goals | −10.7 ± 2.4 |
| Assists | −10.6 ± 2.3 |
| Points | −7.5 ± 1.8 |

Fitted structure:
- **SOG:** opponent EV shots-allowed elasticity 0.85. Opponent PK shots-allowed elasticity 0.37. Opponent PK time (penalties taken → our PP time) 0.54. Home +4%, back-to-back −2%.
- **Goals:** opponent EV xG-allowed elasticity 1.35. Finishing exponent 1.8, so the K=64 shrink is too strong. Opposing goalie GSAx −2.8% per GSAx/100.
- **Assists/points:** own-team × opponent xG environment elasticity about 0.73. Goalie GSAx −5%.

## 3. Does it beat the market?
- **At close: no.** In H3 the stack's Brier skill vs the raw close is about 0. Props at close are efficient.
- **At the open: yes, the market moves toward the model.** This holds in every market and both models, at t = 20–43. Bets placed at the open earn positive CLV.
- **The executable edge is SOG unders at DK/FD opening prices:**

| Selection (SOG unders at open) | n | ROI | CLV (pts) |
|---|---|---|---|
| Blanket (all unders) | 11,376 | −2.1% ± 1.8 | +0.07 |
| v2 raw edge ≥ 6 | 1,912 | +5.1% ± 4.5 | +0.52 |
| v2 level-corrected edge ≥ 0 / 2 / 4 / 6 | 3,024 / 1,808 / 941 / 451 | +2.7 / +3.8 / +4.8 / +7.7% | +0.36 / +0.42 / +0.52 / +0.66 |

- **SOG overs lose even with model edge**, despite strong CLV (+0.7 to +1.9). The over-side vig and the public tax eat it.
- **Live rule** (`src/early_card.py`): SOG unders where the level-corrected v2 edge is ≥ 4 pts. Players need ≥30 games of history. At most 3 per game, 0.75% stake. The rule must run when lines open, because near close the same rule backtested −2.7%.

## 4. Team/game model v2 (`src/models/team_v2.py`)
- Regulation goals come from EV xGF/xGA (own elasticity 0.63, opponent 1.20), PP time and PP xG vs opponent PK xGA, and goalie GSAx.
- Opponent penalties taken persist (k2 = 0.58), but a team's own drawn-penalty history does not (k1 = −0.29).
- Out-of-sample it beats a GF/GA baseline only marginally (Δ −3.1 ± 5.4).
- **Against the clean close it adds nothing.** Correlation with what the market misses is about 0.01.
- **Lines move toward it** (totals corr +0.34, t 9.9; ML t 5.9), but betting at DK/FD opening prices is not profitable (small n, negative). Game lines stay a no-bet market. The model is used for context (sim inputs, SGPs).

## 5. Operating changes
- `scripts/daily_refresh.sh` runs MoneyPuck current season → NHL API → curate → deployment → features → shotq → v2 predictions. It takes about 3 min.
- `nightly.sh` now writes EARLY.md. The main card (`run_slate`) uses v2 means, with v1 as fallback; 98.6% of rows are on v2.
- **To do: run the early card when DK/FD props open in the morning (ET).** That's where the validated edge lives.
