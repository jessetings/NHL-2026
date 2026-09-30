# Findings — 2026-09-30 (historical market study)

Data: 161k player-prop contracts with outcomes (SGO 2024-26 joined to NHL boxscores); per-book pregame closes 2026-01-17 → 2026-06.
Scripts: `src/market/baseline.py`, `src/backtest/h3.py`. Reports: `reports/h3_folds.csv`, `reports/h3_bets.csv`.

## 1. Calibration of de-vigged closes (bias = predicted − observed hit rate)
| Market | Finding | Action |
|---|---|---|
| **SOG overs** | Overstated at every book **and both seasons**: 2+ −1.3 pts, 3+ −2.2, 4+ −3.6, 5+ ≈ −5 (small n). Pinnacle included. | Correction applied in `src/market/calibration.py`. Unders favoured. |
| Assists 1+ | Overs overstated: DK −1.7, Pinnacle −0.9 | −1.2 pt correction applied |
| Points 1+ | Pinnacle/DK calibrated within 0.1 pt | None |
| Anytime goal | Pinnacle two-way close calibrated (26.1 vs 25.9); FD de-vig +1.4 high | Use Pinnacle as the AG benchmark |
| SGO consensus, goals | **Contaminated.** 2+ goal and 1.0 lines are created in-game (players on them averaged ~1 goal); early-2025 AG consensus inflated (17% vs 10%) | Exclude consensus for goal markets |

## 2. H3 — does the v1 opportunity model add information beyond the market? (walk-forward by month)
| Market | Folds | Stack beats market | Brier skill vs market | Model coefficient |
|---|---|---|---|---|
| SOG | 10 | 7/10 | **+0.11%** | +0.20 |
| Points 1+ | 10 | 5/10 | −0.11% | ~0 |
| Assists | 10 | 5/10 | −0.13% | ~0 |
| Goals | 2 | 2/2 | +0.11% | (too few folds) |

Executable test at DK/FD pregame close, stack edge ≥3 pt:
- SOG unders: n=130, ROI +1.4%.
- Points overs: n=401, **ROI −2.6%**.

## 3. Implications
- **At the close, markets are efficient.** A lagged-EWMA opportunity model is barely additive on SOG and not additive on points or assists.
- Profit has to come from:
  - (a) systematic biases (SOG overs → unders);
  - (b) **timing**: betting before the close, and stale DK/FD lines (H2, needs snapshots);
  - (c) alt ladders (H1, prospective);
  - (d) better information: PP/deployment from shifts, confirmed lines, goalie confirmations earlier than the market;
  - (e) correlation and parlay mispricing (needs the simulator).
- Recent form (L5) predicts next-game SOG worse than long memory (15–40 game half-life): corr 0.42 vs 0.45.
