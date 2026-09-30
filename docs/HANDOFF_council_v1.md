# HANDOFF v1 → Agent Council (Red Team / Blue Team / Research)

**Project:** NHL 2026-27 betting research. Player props first, then sides and totals.
**Repo:** `jessetings/nhl-2026`, branch `claude/sleepy-pascal-7z9q1i`
**Date:** 2026-09-30 (opening week of the season)
**Author:** Claude Code session (the builder). You review, research and propose. The builder implements.
**Return format:** Section 10. Please follow it exactly so the builder can turn it into a concrete plan.

> Do **not** ask for or include API keys. The SportsGameOdds key lives in an environment variable (`SGO_API_KEY`).

---

## 0. Your mandate

| Role | Job |
|---|---|
| **Red Team** | Break the current system. Find leakage, bias, false edges, bad assumptions, overfitting risk, execution risk (limits, stale lines, bet acceptance), and ways the card could be systematically wrong. Rank by expected damage to ROI and CLV. |
| **Blue Team** | Propose the strongest achievable version of the system: architecture, models, validation, bankroll and correlation rules, daily operations. Every proposal must be buildable with the data in §3. |
| **Research** | Find and summarise peer-reviewed papers, credible public analytics work and practitioner best practice on the topics in §7. Give **full citations with links**, and mark anything you could not verify. Say which findings are *actionable* for us. |

Ground rules:
- Distinguish **evidence** (studies, backtests) from **opinion**.
- Quantify wherever possible, as expected edge, CLV, or calibration error.
- Prefer ideas we can test on historical data **before** risking money.
- Flag anything that needs data we do **not** have (§3).

---

## 1. Goal and constraints

**Goal**
Daily NHL recommendations with an explicit probability, fair price, edge, stake and price ceiling. Everything is logged for CLV and ROI tracking.

Markets in scope:
- player SOG, points, assists, anytime goal (AG)
- goalie saves
- moneyline, totals, puck line
- first-period and first-goal markets only when the premium is large

**Constraints**
- **Books:** DraftKings and FanDuel. We can only bet there, so edges must exist at DK/FD prices. Pinnacle and other books are for benchmarking only.
- The user also has **SportsPredictApp** and **Action Network** subscriptions. There is no API; data comes by manual export or screenshot.
- Daily workflow: morning build, then a refresh 30 minutes before each puck drop, then postgame grading.
- **Compute:** a Python cloud container with full network access. It is ephemeral, so anything important must go in git.
- **Bankroll and unit size:** not yet specified by the user. Stakes are in units.

**Prior process failures** (from the user's earlier research docs, summarised)
- No probabilities or no-vig benchmark.
- Narrative "good spot" picks.
- Tiny samples.
- Correlated slips with no exposure caps.
- No archived prices, so no CLV.
- First-period-scorer picks made on reputation.

---

## 2. What exists now (read the repo)

| Path | Purpose |
|---|---|
| `docs/00_research_notes_and_plan.md` | Audit of the user's two research PDFs and the initial plan |
| `src/odds.py` | SportsGameOdds v2 fetch (`/v2/events`, `includeAltLines=true`); flattens to one row per event × market × player × side × book × line for DK/FD/Pinnacle |
| `src/model.py` | MoneyPuck-based team ratings, goalie factor, player rates, game model |
| `src/run_slate.py` | Market-implied means, model vs market, blending, decisions → `cards/<date>/props_all.csv`, `game_lines.csv`, `game_model.csv` |
| `src/build_card.py` | Tiering (CORE/LEAN), stakes, correlation caps → `card.csv`, `card_table.md` |
| `cards/2026-09-30/CARD.md` | Tonight's human-readable card |

Run it with:
```
python src/run_slate.py --refresh && python src/build_card.py
```

### 2.1 Model spec as implemented (critique these exact choices)

**Player rates**
- MoneyPuck season summaries (`situation=all`) for 2024-25, 2025-26 and 2026-27 to date, with season weights {2026: 1.0, 2025: 1.0, 2024: 0.45}.
- TOI-weighted per-60 rates for SOG, ixG, goals, assists and points.
- **Shrinkage:** toward positional priors worth 250 minutes. Priors per 60 (all situations):
  - forwards: SOG 6.6, ixG 0.80, A 1.05, PTS 1.85
  - defensemen: SOG 4.3, ixG 0.22, A 0.85, PTS 1.07
- **Goal rate** = 0.55 × ixG/60 + 0.45 × G/60 (finishing is shrunk toward xG).
- **Rookies with no NHL data** get 85% of the positional prior.

**Projected TOI**
- 50% historical TOI/GP plus 50% a role table:
  - forwards F1–F4: 18.0 / 16.0 / 13.5 / 10.5 minutes
  - defense pairs D1–D3: 22.5 / 20.0 / 16.5 minutes
- Roles come from DailyFaceoff line combinations, scraped from `__NEXT_DATA__` JSON.

**Adjustments**
- **Power play:** PP1 ×1.06, PP2 ×0.98, none ×0.92 on goals, points and assists. Half that effect on SOG.
- **Opponent SOG allowed per 60:** shrunk 55% toward league average.
- **Opponent xGA per 60:** shrunk 55%.
- **Opposing goalie factor:** GA/xGA, credibility-weighted, then ×0.35 shrink and clipped to [0.88, 1.12].
- **Home:** ±2% on SOG and √1.04 on goals.
- **Empty-net goals:** +3%.

**Distributions**
- SOG: negative binomial with variance = 1.2 × mean.
- Goals, assists, points: Poisson, assumed independent across players. This is a known flaw.

**Market-implied mean**
- For each player and stat: de-vig every two-way line from DK/FD/Pinnacle (Pinnacle weighted 2×), plus SGO's consensus `fairOdds` at `fairOverUnder`.
- Whole-number lines are handled push-aware.
- Solve for the mean under the same distribution, then average.
- Alt rungs are priced from that mean.

**Level calibration**
- Model means are rescaled per market so the median model/market ratio = 1. The raw model ran about 7.5% below the market on every market.
- The model is therefore used only for **relative** signal. It cannot find edges where the whole market is shifted.

**Blend and tiers**
- Blend: p = 0.4 × model + 0.6 × market.
- **CORE:** model ≥ implied + 2 pts, and market ≥ implied + 1 pt, and EV ≥ 5%, and implied ≥ 18%.
- **LEAN:** blended edge ≥ 1.5 pts and EV ≥ 3%.
- **Data-check:** model and market differ by more than 12 pts.

**Stakes**
- CORE 0.5u, LEAN 0.25u.
- Caps of 1u per player and 2u per game, applied by pro-rata scaling.
- Correlation is not modelled.

**Game model**
- Team λ = 3.05 × offence (0.7 × xGF + 0.3 × GF, relative to league, shrunk 55%) × opponent defence (xGA) × goalie factor × home.
- Independent Poisson in regulation.
- Overtime is 52/48 home. OT or shootout adds exactly one goal to the total.
- Nothing else: no score effects, no pulled goalie, no rest or travel, no in-season updating.

### 2.2 Tonight's output (Sept 30, 2026: PIT@PHI, NYI@TOR, LAK@COL)

**CORE picks**
- Malkin 1+ assist, FD +182
- Konecny 3+ SOG, FD +215
- Nylander 2+ points, FD +285
- Makar 4+ SOG, FD +245
- Martone 4+ SOG, FD +265 (rookie)

**Other results**
- Nine leans.
- All game lines are passes.
- NYI ML +110 is a watch: the model disagrees with the market by about 5 pts, and TOR is on a back-to-back.

**Observations**
- Most "edges" are on **FanDuel's alternate SOG ladder** (3+ and 4+ rungs priced better than FD's own main line implies under our NB assumption).
- The anytime-goal market looked efficient. Every AG candidate was within ±3% EV.
- Recommendations from the user's prior research (MacKinnon AG, MacKinnon 4+ SOG, Crosby 2+ SOG, Kempe/Schaefer 3+ SOG) were all negative or zero EV at live prices.

---

## 3. Data inventory

| Source | Status | Detail |
|---|---|---|
| **SportsGameOdds v2 (Pro tier)** | ✅ Live access | Unlimited objects, 300 requests/min. About 85 books including DK, FD, Pinnacle, Circa, Kalshi/Polymarket, with alt lines. |
| **SGO historical** | ✅ Confirmed | Past events return per-book odds, `closeBookOdds`, `closeFairOdds`, open fields, and **full box-score results per player** (SOG, TOI, points, PP etc.). Tested on 2025-10-10 and 2026-09-29. |
| MoneyPuck season summaries | ⚠️ Partial | 2024, 2025 and 2026 pulled (skaters, goalies, teams, lines). History back to 2008 exists and is not yet pulled. |
| MoneyPuck shot-level files | ❌ Not yet | `shots_2025.zip` (20 MB) and `shots_2007-2024.zip` (327 MB) are reachable. |
| MoneyPuck game-by-game | ❌ Not yet | Per-player and per-team game logs are reachable. Needed for rolling features and backtests. |
| NHL API (`api-web.nhle.com`, `nhl-api-py`) | ✅ Reachable, barely used | Schedule, boxscore, play-by-play, shift charts. |
| DailyFaceoff | ✅ Scraped | Line combinations, PP units, injuries, starting goalies with Confirmed/Likely status. **No history.** Snapshots must be archived going forward. |
| Referee assignments / tendencies | ❌ | Not sourced |
| SportsPredict / Action Network | ❌ | Manual only |

**Open questions on SGO history for you**
- How far back does NHL player-prop history go?
- Is there an odds-movement or snapshot history, or only close?
- Are the per-book historical `odds` values pre-match closes, or can they be last live ticks? One observation suggests live: the DK ML at -14999 was timestamped after puck drop.
- The builder will verify empirically, but please research SGO documentation on historical data semantics (`closeBookOdds` vs per-book `odds`, and the `lastUpdatedAt` filter).

---

## 4. Builder's self red-team (known weaknesses, please extend and rank)

1. **Independent Poisson for points and goals across teammates.** Points are correlated: one goal gives 1-3 points to linemates. This affects same-game exposure, SGP pricing and the tails of points distributions.
2. **The SOG tail shape (var/mean 1.2) is assumed, not fitted.** Most "edges" are on alt rungs, so if real overdispersion is higher, the FD ladder edges may be illusory. This is the #1 thing to validate.
3. **The market blend is circular.** With a 0.6 weight on market, edges mostly come from DK/FD deviating from consensus (price-shopping) or from alt-ladder shape. That may be a real edge or a modelling artefact.
4. **Level calibration hides global bias.** We cannot detect whether the market systematically over- or under-prices a whole class, such as SOG overs, which are often said to be shaded.
5. **TOI and role projection is crude.** It uses a static role table. There are no deployment models (score effects, PK usage, back-to-backs) and no line-matching.
6. **No usage-change detection.** Players who changed teams or roles (Marchenko→TOR, Panarin→LAK, rookies) carry last season's context.
7. **Team ratings come from last season**, shrunk 55%. There are no roster-change adjustments and no in-season Bayesian updating yet.
8. **The game model ignores** score effects, pulled goalie, special-teams volume and penalty rates (including referees), and rest/travel. There is also no bivariate or dependence structure.
9. **No uncertainty intervals.** Point estimates only.
10. **Data gaps:**
    - No historical backtest yet.
    - Zero calibration evidence.
    - Thresholds (2 pts / 1 pt / 5% EV) were chosen a priori.
    - Some players are missing from the SGO feed (Marchenko, McKenna), which suggests player-ID mapping gaps.
11. **Execution risks:** DK/FD limits on prop winners, alt-line max bets, stale-line risk, and the 10-minute update cadence (moot on the Pro tier, but still worth checking).
12. **Time-of-day effects:** when to bet (open vs close) is unknown for these markets.

---

## 5. Questions for the Red Team
1. Is the FD alt-SOG-ladder "edge" plausible, or an artefact of our NB tail? What overdispersion do NHL player SOG counts actually show, by position and role?
2. What leakage or look-ahead risks exist when backtesting with SGO history plus MoneyPuck summaries? Examples: season summaries include future games; role labels come from hindsight.
3. Which of our constants are most likely wrong, and in which direction? Consider:
   - the 250-minute prior
   - 0.55 xG weight
   - 55% team shrink
   - the goalie shrink
   - PP multipliers
   - the TOI role table
4. Is blending 60% market justified? What do studies say about beating closing lines in player props versus sides?
5. Where will DK/FD execution kill a paper edge (limits, voids, correlated-leg rules)?
6. What failure modes should trigger an automatic "no bet"?

## 6. Questions for the Blue Team
1. Propose the **target architecture** for:
   - a data lake (raw JSON + Parquet + DuckDB)
   - feature store
   - models
   - calibration
   - decision engine
   - logging and CLV tracking
2. Propose the **player opportunity model**: TOI by strength state (EV/PP/PK), shot attempts and SOG rate, xG per attempt, finishing, and assist mechanics. Should it be hierarchical Bayesian, gradient-boosted, or both?
3. Propose the **game simulator** (see §8). How should player props be derived from simulated team outcomes so that correlation is native?
4. Propose the **validation protocol**:
   - walk-forward
   - calibration (Brier, log-loss, reliability)
   - CLV versus DK/FD/Pinnacle close
   - significance given noise
   - minimum sample before sizing up
5. Propose **bankroll rules**: fractional Kelly under parameter uncertainty, portfolio Kelly for correlated same-game props, and caps.
6. Propose **market-selection priorities**: where are soft-book props most beatable (SOG, saves, assists, blocks, hits, P1 markets)? Evidence, please.

## 7. Research agenda (cite, summarise, mark as actionable or not)

**A. Hockey scoring and game modelling**
- Poisson / negative binomial / bivariate Poisson models of NHL scoring
- Dependence between team scores
- Score effects
- Pulling the goalie
- Overtime and shootout modelling

Known starting points (verify the citations):
- Buttrey, Washburn & Price, "Estimating NHL Scoring Rates", *JQAS* (2011)
- Beaudoin & Swartz on goalie pulling (*The American Statistician*, 2010)
- Dixon & Coles (1997) and Karlis & Ntzoufras (2003) on bivariate/dependent Poisson (soccer, transferable)
- Thomas, Ventura, Jensen & Ma, hazard models for hockey (*Annals of Applied Statistics*, 2013)

**B. Expected goals and shot quality**
- xG model design: MoneyPuck, Evolving-Hockey, HockeyViz and academic work
- Stability and repeatability of shooting talent versus finishing luck, and how much to regress
- Shooting-percentage regression studies
- Shot-rate repeatability by position

**C. Player deployment**
- TOI prediction
- PP unit value
- Line-matching and last change
- Effect of back-to-backs and travel on TOI, shots and goalie performance
- Rookie projection and new-team adjustments

**D. Goalies**
- GSAx stability and year-to-year repeatability
- Workload and back-to-back effects
- Starter-confirmation timing
- How much goalie information the market prices in

**E. Special teams and officiating**
- Penalty-rate models
- Referee tendencies and their effect on PP opportunities, and through them on points and SOG props

**F. Betting-market efficiency**
- NHL sides and totals efficiency
- Closing-line value as a skill proxy
- Consensus/sharp-book "fair odds" methods (e.g., Kaunitz, Zhong & Kreiner, "Beating the bookies with their own numbers", 2017)
- Levitt (2004) on bookmaker behaviour
- Favourite–longshot bias in props and alt lines
- Soft-book versus sharp-book pricing gaps
- Same-game-parlay pricing
- **Player-prop market efficiency studies specifically** (NHL if available, otherwise NBA/NFL/MLB analogues)

**G. De-vigging methods**
- Multiplicative, additive, power, Shin and odds-ratio methods
- Which works best for two-way props and for one-sided AG boards

**H. Bankroll and portfolio**
- Kelly under estimation error
- Fractional Kelly
- Simultaneous and correlated bets
- Drawdown control

**I. Simulation best practice**
- Monte Carlo game sims (event-level versus period-level)
- Dirichlet-multinomial shot allocation among teammates
- Latent pace factors
- Producing full outcome ranges and percentiles for props

**J. Practitioner sources**
- Credible public NHL prop-modelling write-ups
- Evolving-Hockey and Hockey-Graphs methodology posts
- MoneyPuck methodology
- Pinnacle betting resources on CLV and de-vigging

---

## 8. Draft simulation design (Blue Team: improve it, Red Team: attack it)

**1. Game-level latent state**
- Pace multiplier ~ Gamma (shared by both teams).
- Team strength offsets.
- Starting goalies with uncertainty.

**2. Strength-state timeline**
- Simulate penalties (team and referee rates), which produces EV/PP/PK minutes.

**3. Shot generation per strength state**
- Team unblocked attempts ~ NB given the state, opponent and score (score effects).
- Each attempt is assigned to an on-ice player via deployment shares (Dirichlet-multinomial by line, PP unit and TOI).
- Its xG is drawn from the player's xG-per-attempt distribution.
- Goal ~ Bernoulli(xG × goalie adjustment).
- Assists go to linemates by historical share.

**4. Endgame**
- Pulled-goalie logic when trailing late, which drives empty-net goals.
- Overtime 3-on-3 and shootout.

**5. Outputs from 10k–50k sims per game**
- Win, total and puck-line probabilities.
- Every player's SOG, points, assists and goals **distributions**, with correlation preserved.
- Percentile ranges, and SGP and correlated-portfolio pricing.

**6. Calibration layer**
- Compare simulated distributions to realised outcomes historically.
- Recalibrate tails, which matters most for alt ladders.

**7. Market layer**
- Compare to de-vigged DK/FD/Pinnacle.
- Log everything, including passes.

---

## 9. Proposed backtest (to be refined)
- **Seasons:** 2023-24 → 2025-26 regular seasons, or however far SGO prop history goes.
- **Features:** strictly as-of each game, using MoneyPuck game-by-game logs plus NHL shift and boxscore data.
- **Lineups:** there is no historical DailyFaceoff, so use the actual dressed lineup and a TOI proxy. This is hindsight-leaky, so the degradation needs estimating.
- **Evaluate on:**
  - Brier and log-loss versus de-vigged close
  - calibration by market and rung
  - CLV of "would-have-bet" picks at the prices logged at recommendation time
  - ROI with bootstrap confidence intervals
- **Key hypotheses to test first:**
  - H1: FD/DK alt SOG ladders are mispriced relative to their main lines.
  - H2: DK/FD player props lag Pinnacle/consensus, giving exploitable price-shop gaps.
  - H3: Our opportunity model adds information beyond the market (positive Brier skill score versus close).
  - H4: The AG market is efficient at DK/FD, so skip it or use it only in extreme cases.

---

## 10. RETURN HANDOFF FORMAT (please follow exactly)

```
# HANDOFF v2 → Builder

## A. Verdict summary (≤10 bullets)

## B. Red Team findings
| # | Issue | Evidence/rationale | Severity (1-5) | Likelihood (1-5) | Fix | Test to confirm |

## C. Blue Team proposals
| # | Proposal | Expected benefit | Effort (S/M/L) | Dependencies | Priority (P0-P3) |

## D. Research digest
For each source: citation + link | key finding | how it applies to us | actionable (Y/N) | confidence

## E. Recommended parameter changes
| Parameter | Current | Proposed | Justification/source |

## F. Simulation spec (final)
Numbered, implementable. Include distributions and parameters, and how to fit each from our data (§3).

## G. Validation and backtest protocol (final)

## H. Bankroll, staking and correlation rules (final)

## I. Build plan
Ordered milestones with acceptance criteria, e.g.:
- M1: ingest MoneyPuck game-by-game + SGO history, 2023-26
- M2: fit SOG overdispersion; test H1
- ...
Mark what must be done before the next betting day vs later.

## J. Open questions for the user
(bankroll, unit size, risk tolerance, markets to exclude, time available per day)
```

---

## 11. Facts the council should not re-derive
- DK/FD are the only betting books. Pinnacle and SGO consensus are benchmarks.
- The SGO key is Pro tier: unlimited objects, historical odds and results included.
- NHL API, MoneyPuck (all files) and DailyFaceoff are all reachable from the builder's container.
- The user wants automation, with no screenshots unless unavoidable (SportsPredict and Action exports only).
