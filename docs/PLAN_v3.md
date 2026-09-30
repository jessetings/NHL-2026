# PLAN v3: Builder response to Council Handoff v2

**Status:** 2026-09-30.
**The v2 handoff is accepted as the governing spec.** Every adjustment below comes from the M0 data audit and nothing else.

---

## 1. What the M0 audit found (changes some v2 assumptions)

Source: `reports/coverage_*.csv` and `src/audit/coverage.py`.

| Fact | Consequence |
|---|---|
| SGO NHL history starts **2024-09**. Player props at DK/FD appear from **Feb 2025**. | The earliest usable prop season is late 2024-25. |
| The stored per-book `odds` in history are the **last tick, which is usually in-game**. Only 0–15% of DK/FD prop rows and **0% of MLs** were updated pregame. | Raw historical per-book prices are **unusable** as bet-time prices. |
| **Per-book `openOdds`/`closeOdds`** (close = price at puck drop) exist only from **2026-01-17**, via `includeOpenCloseOdds=true`. Now ingested. | **True bet-time backtest window: 2026-01-17 → 2026-06 (≈700 games).** That covers 174k DK, 94k FD and 90k Pinnacle prop rows with a pregame close. |
| **Alt lines never carry open/close** at any date. | **H1 (alt-ladder mispricing) cannot be backtested historically.** It is testable only **prospectively** from our own snapshots. Logger started 2026-09-30. |
| SGO consensus `closeFairOdds` covers ~95–100% of main-line contracts in all markets from **2025-02**. | Market-only baseline for proper-score tests (H3/H4) spans **2025-02 → 2026-06 (~2,000 games)**. Caveat: the consensus includes DK/FD. A leave-one-book-out version is only possible where per-book closes exist (2026-01+). |
| SGO player results only from 2025-11. | **Grade from NHL boxscores**, which we have for every game since 2022-23. SGO results are a cross-check only. |
| SGO→NHL mapping: events 2,541/2,847 (the rest are preseason); players 1,037/1,079 (96.1%). | The ~4% unmapped are mostly fringe players and new call-ups. They go to the quarantine table per v2 §G. The target is >99% for players with priced props. |
| There is no historical DailyFaceoff, and historical PP units exist only via shifts (hindsight). | The deployable backtest uses **lagged shift-derived roles** (last N games before t0). Oracle = actual. |

### Revised backtest windows (replaces v2 §E "Research window")

| Purpose | Window |
|---|---|
| Features and model fitting | 2022-23 → t0 (NHL/MoneyPuck), strictly lagged |
| Proper-score skill vs consensus close (H3, H4, main lines) | 2025-02 → 2026-06, nested walk-forward by month |
| Bet-time exact-price / CLV / ROI (main lines) | 2026-01-17 → 2026-06 |
| Untouched holdout | **2026 playoffs + the first 6 weeks of 2026-27, prospectively.** The 2025-26 season can't be held out entirely because per-book closes only exist in its second half. |
| H1 alt ladders and H2 lead-lag | Prospective only, from the snapshot archive, starting 2026-09-30 |

---

## 2. Data layer status (M0–M2)

| Item | Status |
|---|---|
| MoneyPuck season summaries 2015→now (regular and playoffs); shots 2022→now; team game logs; player lookup | ✅ `data/curated/mp_*` |
| NHL boxscores 2022-23→now (5,597 games) | ✅ `nhl_skater_game` (201k), `nhl_goalie_game` |
| NHL play-by-play (1.34M events) and shifts (3.16M) for 2023-24→now | ✅ partitioned parquet |
| NHL officials (4,197 games) and player careers (1,528 players, 51k season rows, all leagues) | ✅ |
| SGO history (10.6M odds rows), including per-book open/close from 2026-01 | ✅ `sgo_odds/`, `sgo_events/`, `sgo_results/` |
| ID maps | ✅ `map_sgo_event`, `map_sgo_player` |
| DailyFaceoff snapshots | ✅ started (no history exists) |
| Live odds snapshots every 5 min (all books, alt lines) | ✅ started 2026-09-30 22:26Z |
| **Persistence** | ⚠️ The container is ephemeral and data is about 1 GB. **Needs HF_TOKEN** for a private Hugging Face dataset (§6). Until then, everything except the snapshot archives is rebuildable in ~15 min. |

---

## 3. Build order (P0 before real money; each item has acceptance tests)

| # | Milestone (v2 ref) | Concrete deliverable | Accept when |
|---|---|---|---|
| 1 | **M3 no-vig engine** | `src/market/devig.py`: multiplicative/additive/power/Shin/odds-ratio; two-way exact-contract keys; leave-one-book-out consensus. `src/market/contracts.py`: canonical wager key | Known-answer unit tests; exact-line reconciliation report with zero cross-rung comparisons |
| 2 | **Market-only baseline** | Bet-time and close market probabilities for every graded contract, plus Brier/log-loss tables by market and rung | Reproducible table; calibration plots of the market itself (e.g. favourite–longshot by decile) |
| 3 | **M4 pregame TOI/role model** | EV/PP/PK TOI distributions from lagged shifts (EWMA + hierarchical shrink), using role from the last N games' PP-unit share | Outer-fold MAE and interval coverage; deployable-vs-oracle gap reported |
| 4 | **M5 SOG distributions** | Poisson / NB2 / generalized Poisson / hurdle-NB per player-game with pregame TOI offset | Randomized PIT and calibration at every rung 1+…5+; the chosen family wins outer-fold log-loss |
| 5 | **H3/H4 tests** (main lines) | Logistic stack: outcome ~ logit(market) + model residual, cross-fitted | Incremental Brier/log-loss vs market-only in a majority of outer folds; BH-FDR 10% |
| 6 | **M6 AG decomposition** | TOI → SOG → xG/shot (MoneyPuck shots) → shrunk shooter and goalie effects → separate empty-net hazard | AG calibration by odds decile; decomposition fields saved per player-game |
| 7 | **M7 logger + paper trading** | Every candidate and pass logged with timestamp, price, fair price, interval, reason code. Automatic grading from NHL boxscores; CLV vs per-book close | Zero manual edits; reproduction from snapshot hash |
| 8 | **H1 prospective** | Weekly report: FD/DK alt-rung prices vs fitted distribution vs outcome, from snapshots | ≥300 settled alt contracts before any conclusion |
| 9 | M8–M10 joint simulator | Poisson-gamma team model → state TOI → Dirichlet-multinomial shot allocation → xG marks → goals → assists → saves | Reconciliation in every draw; empirical same-game correlations reproduced |
| 10 | M11–M15 | Lead-lag, nested harness, ensemble registry, portfolio Kelly, monitors | Per v2 |

**Betting policy until items 1–7 pass:** paper trading only. The Sept 30 card stands as a paper-trade record. It was produced by the pre-v2 model and is graded but not used as evidence.

---

## 4. Deviations from v2 (with reasons)
1. **Holdout.** The whole of 2025-26 cannot be untouched, because bet-time prices only exist from 2026-01-17. The holdout is prospective instead (see §1).
2. **H1 is prospective-only.** No historical alt-line prices exist.
3. **The consensus benchmark before 2026-01 includes DK/FD** and cannot be made leave-one-book-out. It is used only for proper-score tests, never for CLV claims.
4. **Settlement comes from NHL boxscores**, not SGO results, because of coverage.

---

## 5. Engineering practices
- **Ingestion:** threaded I/O (8 workers for NHL, paginated SGO), gzip raw JSON, resumable and idempotent (skip-if-exists, atomic writes).
- **Curation:** process pools writing partitioned Parquet **inside workers** (flat parent memory; SGO 10.6M rows in about 2 min at under 1 GB RSS); DuckDB for queries.
- **Next:** snapshot hashes (SHA-256 of raw payloads) in every prediction log row; `make`-style one-command rebuild; unit tests for de-vig, contract keys and ID maps.

## 6. Needed from the user
1. **HF_TOKEN** (Hugging Face write token) as an environment variable, for private dataset persistence of raw, curated and snapshot data.
2. Answers to v2 §J: bankroll and unit, risk profile, drawdown pause, excluded markets, bets per slate, review times, alerts vs auto, and how to use SportsPredict/Action.
