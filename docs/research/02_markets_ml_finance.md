# 02 — Markets, ML and Staking: research digest for the NHL "pyramid"

**Status:** 2026-09-30. Research agent output. Read-only relative to the rest of the repo.
**Scope:** (1) market efficiency of props vs sides/totals, (2) de-vig methods, (3) CLV as a skill signal, (4) ML methodology, (5) staking and portfolio theory for an aggressive pyramid, (6) Python tooling.
**Conventions:** `d` = decimal odds; `p` = our probability; `EV = p·d − 1`; Kelly `f* = (p·d − 1)/(d − 1)`.
**Confidence tags:** **[H]** = peer-reviewed or primary source read directly. **[M]** = reputable practitioner source, or a peer-reviewed result seen only via abstract or secondary summary. **[L]** = vendor/blog claim or single-source number. **[UNVERIFIED]** = plausible, but I could not confirm the primary source in this session. **[DERIVED]** = my own calculation (scripts in the session scratchpad, reproduced inline).

---

## 0. Key takeaways, ranked by expected profit impact

1. **Calibration beats accuracy, and the edge estimate is the thing to shrink.** Choosing a model by calibration instead of accuracy turned a −35% ROI into +35% in an NBA betting experiment (Walsh & Joshi 2024). In Kelly terms, betting 2× your true Kelly fraction gives **zero** growth [DERIVED]. So if the model overstates edge by 2×, "full Kelly" is break-even at best. In our pyramid simulation, overstating every edge by 3 points turned a median 2.0× season into a coin-flip on losing money [DERIVED §5.6]. → *Fit with proper scores, recalibrate out-of-fold, and shrink stakes by uncertainty.*
2. **Use the market as the prior. Don't try to out-predict it from scratch.** Our job is to predict the *residual* against a de-vigged sharp price, not the outcome. Stacking `logit(p_market) + model residual` (already the H3/H4 design) is the right structure (Egidi et al. 2018; Wunderlich & Memmert 2020; Hubáček et al. 2019). Kaunitz et al. (2017) made money on 56k+ football games using *only* the consensus of other books' odds against the soft books.
3. **Props are softer than sides/totals, and no single book is "sharp" on props.** Pinnacle posts props with low limits (~$250–500 on NFL). Many US books license third-party prop numbers. FanDuel and Caesars are cited as originators [M/L]. Consequences: (a) Pinnacle prop closes are a *weaker* truth benchmark than Pinnacle ML/totals closes; (b) the soft-book edge on props is real but short-lived and limited by account restrictions.
4. **Parlays: only +EV legs, and only small stakes. Retail SGPs are presumed −EV unless we price the correlation ourselves.** Leg EVs compound: four legs at +5% give +21.6%, and four legs at −4.5% give −16.8% [DERIVED]. Under Kelly, the optimal parlay stake is the *product* of the single-leg Kelly stakes. The growth lost by banning parlays entirely is only O(ε⁴) (Long 2026; Grant, Johnstone & Kwon 2008). **Parlays add almost nothing to long-run growth. They are a variance and "big night" tool, not a growth engine.** Parlay hold at US books runs ~13–30% (Illinois 13–14.3% in autumn 2025) [M].
5. **The favourite–longshot bias (FLB) is strong in exactly the markets the top tier targets.** It shows up in longshots, anytime/first scorer, alt ladders and multi-leg parlays. Kalshi parlays are overpriced by ≈3% per leg, which reaches ≈22% at 10 legs (Moshrefi 2026). Bookmaker loss rates on longshots exceed what the overround implies (Hegarty & Whelan 2025). → *EV thresholds must rise with odds, and de-vigging must allocate more of the margin to longshots (power / Shin / odds-ratio, never multiplicative for longshot boards).*
6. **NHL moneylines historically show a *reverse* FLB (underdogs underbet).** Evidence: Woodland & Woodland 2001; Gandar et al. 2004; Paul & Weinbach 2012. At least one newer study disagrees. → *Don't hard-code a direction. Measure the FLB by odds decile on our own close data (PLAN M3 step 2).*
7. **CLV is the fastest valid skill signal, but only against a close that is itself calibrated.** A result-based ROI test needs ~2,500 bets at even money with a 5% edge, and ~10,000 at +400 [DERIVED]. A CLV test needs ~25–400 bets, depending on CLV dispersion [DERIVED]. Buchdahl gives similar orders of magnitude: "~50 bets vs several thousand". → *Track CLV from day 1 against Pinnacle (props: leave-one-book-out consensus close) and gate stake scaling on CLV t-stats, not P&L.*
8. **Stake with ≤¼ Kelly on single bets and use simultaneous (portfolio) Kelly for same-slate bets. The lottery tier gets a separately capped budget.** Fractional Kelly (tuned) was the most robust strategy across horse racing, basketball and football (Uhrín et al. 2021). Risk-constrained Kelly (Busseti, Ryu & Boyd 2016) handles drawdowns formally. The chance of ever halving the bankroll is 12.5% at ½ Kelly and 0.8% at ¼ Kelly [DERIVED from the continuous-time drawdown law].
9. **The "10×–100× nights" goal is only compatible with survival if defined on the lottery bucket, not on the bankroll.** In the simulation, a top tier of 2%/ticket/night (≈1.85× Kelly) raised the season P(loss) from 5.5% to 32% and cut the median outcome [DERIVED §5.6]. A 0.5% top tier was roughly neutral-to-positive.
10. **Account lifetime is a scarce, depletable asset.** UKGC data: 4% of accounts are restricted, and restricted accounts are ~2× as likely to be in profit (46.8% vs 25.4%). Massachusetts now forces books to explain limits. FanDuel's notices cite "pricing inefficiencies and/or market timing" [M]. → *Rank bets by EV × remaining-account-value. Don't burn DK/FD on thin edges.*

---

## 1. Betting-market efficiency

### 1.1 Sides/totals vs props; who is sharp

| Finding | Source | Key numbers | Confidence |
|---|---|---|---|
| Bookmakers are better forecasters than bettors. They take positions rather than balancing books, and can shade prices toward public biases. | Levitt (2004), *Economic Journal* 114:223–246. https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1468-0297.2004.00207.x | NFL contest data | H (abstract) |
| Counterpoint: in 1,139 MLB games, realized bookmaker margin was indistinguishable from the hold. The public leans to favourites, but there is no matching shading. | Dmochowski (2026), "The profit-bias identity", arXiv 2609.06739. https://arxiv.org/abs/2609.06739 | margin ≈ hold | M (preprint) |
| Pinnacle closing lines are ~1:1 calibrated, with the lowest blind loss (−3.31%). DraftKings' blind loss was −7.01%, and its odds "add a bit of predictive value" but lag Pinnacle. The softest markets (3-balls, offered only by soft books) gave 9.7% ROI vs 1.7% on round matchups for Data Golf's model. | Data Golf, "How sharp are bookmakers?" https://datagolf.com/how-sharp-are-bookmakers | 106,204 bets, 11 books, golf 2019–20 | M |
| "There is no sharpest sportsbook for props." Pinnacle NFL prop limits are ~$250 pregame and ~$500 gameday, vs $100k+ on sides. Books set props at the **median**, and player stats are right-skewed, so mean projections bias you toward overs. | Unabated. https://unabated.com/articles/the-biggest-mistake-youre-making-when-betting-nfl-player-props | limits as quoted | M |
| Only a few US books originate prop lines (Caesars, FanDuel). DraftKings, MGM and others use the same third-party feeds. FanDuel's price discovery is slower but independent. | Establish The Run. https://establishtherun.com/understanding-the-current-ecosystem-of-nfl-player-props/ | NFL-specific | L–M (NHL unverified) |
| Weak-form NBA efficiency holds for sides. Opening lines are biased when a key player is absent, but the bias is gone by the close. | Player absence and NBA lines, *Finance Research Letters* 13 (2015). https://ideas.repec.org/a/eee/finlet/v13y2015icp130-136.html | close ≈ 50/50 | M (abstract) |
| Prop hold at recreational books is 6–10%+, vs 2–4% at sharp books. | Pinnacle betting resources, "Betting hold". https://www.pinnacle.com/betting-resources/en/educational/betting-hold-what-it-is-and-why-it-matters-for-your-sports-betting-strategy | — | M |
| Goal-scorer markets carry "20–35% vig". Moving from PP2 to PP1 raises a player's goal probability by ~10–15%. | Practitioner blogs (tonyspicks, propsbot). https://www.tonyspicks.com/2026/05/15/nhl-anytime-goal-scorer-props-reading-power-play-time-as-the-edge/ | — | **L — verify on our SGO data** |

**How to apply.**
- Treat per-market sharpness as an *empirical property* to be measured, not assumed. For each (market, book), compute the log-loss of the de-vigged close vs outcome, 2025-02 → 2026-06 (PLAN M3 step 2). Use the sharpest *measured* source as the CLV benchmark for that market.
- In props, the edge sits in role/usage information (lines, PP units, TOI, goalie confirmation) that feeds the third-party prop feeds slowly. That is precisely the TOI → SOG → xG decomposition in PLAN M4–M6.
- Compare the market **median** to our distribution's median, never its mean. For Poisson/NB SOG this is automatic if we price `P(X ≥ k)` directly.

### 1.2 Soft vs sharp lead–lag
- Vendor claims: sharp books (Pinnacle) reprice in milliseconds, DK/FD in 5–30 s in-play, and pregame soft books "lag by 15–60 minutes". **[L — vendor marketing]** (https://sharpapi.io/learn/how-live-is-real-time-odds-data, https://dev.to/edgelab/line-shopping-actually-works-i-tracked-odds-across-10-sportsbooks-and-found-47k-in-annual-leakage-2h4a).
- The academic foundation is Kaunitz, Zhong & Kreiner (2017), arXiv 1710.02824 (https://arxiv.org/abs/1710.02824) **[H]**. Their method bet soft books whenever the price exceeded the de-vigged *average* of all books by a margin. It beat random betting by 10.8 SD over 56,435 games, and they were then **restricted by the books**.
- **Apply:** H2 (prospective lead-lag) is testable from the 5-minute snapshot logger. Estimate `Δlogit(DK/FD)_t+k ~ Δlogit(Pinnacle or consensus)_t` by market type and time to puck drop. The practical signal: DK/FD price vs *current* sharp fair, with a staleness timer. Expect the edge to decay within minutes to hours. The snapshot cadence (5 min) may be too slow to capture it; see Open Q1.

### 1.3 Alt lines and ladders
- Practitioners broadly report worse pricing and wider hold on alt lines and milestones **[L]** (https://betpredictionsite.com/blog/alt-lines-milestones-overpriced/, https://www.si.com/betting/what-are-alt-lines-sports-betting-alternate-lines). No peer-reviewed study of alt-ladder pricing turned up.
- Mechanism (my inference): a soft book derives the ladder from one fitted distribution per player, often Poisson-like. Any mis-specified dispersion (NB vs Poisson) produces *systematic, rung-dependent* mispricing. Too thin tails make the 5+ SOG rung too long; too fat tails make it too short. Our PIT-calibrated NB/GP family (PLAN M5) is exactly the right weapon. **[DERIVED hypothesis; H1 is prospective only]**
- **Apply:** for each rung, compute `EV_rung = p_model(X ≥ k)·d_k − 1`. Also compute the **implied dispersion** that reproduces the book's ladder. If a book's implied dispersion is stable across players and differs from ours, that is a structural, repeatable edge.

### 1.4 Same-game parlays (SGPs) and correlation
- SGP pricing uses correlation matrices and copulas, and books acknowledge correlation mis-estimation risk (OpticOdds, https://opticodds.com/blog/correlation-in-same-game-parlays) **[L]**. Parlays can hold 15–25%+, and parlays have been ~⅓ of handle but >½ of revenue in some months **[L]**.
- Illinois parlay hold was 13% (Sep 2025) and 14.3% (Oct 2025), on ~$540M monthly parlay handle (https://www.covers.com/industry/illinois-sets-new-sports-betting-handle-record-in-october-dec-23-2025) **[M]**.
- **Apply:** the only way an SGP is +EV is if our *joint* probability exceeds the book's by more than the hold. Needed: the joint simulator (PLAN M8–M10), with player outcomes drawn from shared game-state draws (pace, score state, PP time, empty net). Default assumption: **retail SGPs are −EV** until the simulator shows otherwise on ≥300 settled logged SGP quotes.

### 1.5 Favourite–longshot bias (FLB)
| Finding | Source | Numbers | Conf. |
|---|---|---|---|
| FLB is driven by probability *misperception* (prospect-theory weighting), not risk-love. Compound bets (exactas, trifectas) show it most. | Snowberg & Wolfers (2010), *JPE* 118(4). https://www.nber.org/system/files/working_papers/w15923/w15923.pdf | US racing | H |
| Kalshi NBA/MLB/NHL: calibration is near perfect 30–240 min before expiry and breaks in the final 10 min. Cross-game parlays are fair at 2–4 legs, then overpriced by 1.005 at 5 legs, 1.066 at 8 and 1.223 at 10: **≈3% per-leg inflation** (β₁≈0.029). | Moshrefi (2026), arXiv 2607.14430. https://arxiv.org/html/2607.14430 | 23M trades (NHL 2.8M); 12,639 parlays | M (preprint, read directly) |
| If margins are higher on longshots (FLB), actual average loss rates exceed the overround: **+20% (soccer), +40% (tennis)**. Loss rates are worse still on proposition bets. | Hegarty & Whelan (2025). https://www.karlwhelan.com/Papers/Overround.pdf | — | H (read directly) |
| NHL moneyline: **reverse** FLB (underdogs win more than priced). | Woodland & Woodland (2001, 2011); Gandar, Zuber & Johnson (2004); Paul & Weinbach (2012), as summarized at https://pages.charlotte.edu/wp-content/uploads/sites/850/2012/10/wp2016-006.pdf and in Moshrefi 2026 | — | M (secondary); a newer thesis (Aalto) found normal FLB [L] |
| Anytime/first goalscorer markets on unlikely scorers sit at the "long-shot end of a high-margin market". | Practitioner (caanberry). https://caanberry.com/first-vs-anytime-goalscorer/ | — | L |

**Apply:** (i) EV thresholds increase with odds (§7.1). (ii) De-vig longshot-heavy boards with power/Shin/odds-ratio. (iii) Build the "market-only calibration by odds decile" table (PLAN M3) before any longshot bet goes live. If our own data shows a *reverse* FLB in NHL ML, the middle tier should tilt toward dogs.

### 1.6 Limits and account restrictions
- **UKGC (2025 data release, 2024 activity):** 643,779 of ~15M accounts restricted (4%). 62% of restrictions were max-stake cuts. **46.78% of restricted accounts were in profit vs 25.42% of all active accounts.** 51.29% of restricted accounts were nonetheless *losing*. The regulator says being a successful bettor is not a protected characteristic. https://igamingbusiness.com/sports-betting/operators-in-great-britain-player-account-restrictions-2024/, https://sbcamericas.com/2025/07/25/uk-regulator-sports-betting-limits/ **[M]**
- **Massachusetts:** books must explain limits within 48 h. FanDuel notices cite exploiting "pricing inefficiencies and/or market timing". https://www.gambling.com/us/news/massachusetts-first-state-to-make-sportsbooks-explain-account-limits **[M]**
- Kaunitz et al. (2017) were restricted within months of winning **[H]**.
- **Apply (within ToS; no multi-accounting or proxy betting):** model each account as a depletable asset with an expected remaining lifetime handle `H_rem`. Rank bets by `EV × stake` and skip bets whose EV is below the band threshold even if technically +EV. Timing (sniping stale lines seconds after sharp moves) is the flagged behaviour, and it is also the most "detectable". Prefer model-driven edges that exist at stable prices. Log limit events per book as data (stake accepted vs requested).

---

## 2. De-vig methods

### 2.1 Methods (for implied probabilities `r_i = 1/d_i`, overround `M = Σr_i − 1`, n outcomes)
| Method | Formula | Behaviour |
|---|---|---|
| Multiplicative (basic) | `p_i = r_i / Σr` | Margin proportional to probability. No FLB, so it **overstates longshots**. |
| Additive | `p_i = r_i − M/n` | Equal margin per outcome. Can go negative for many-outcome boards. |
| Power | `p_i = r_i^k`, with k solved so Σp=1 (k>1) | More margin on longshots. Never leaves [0,1]. |
| Shin (1992/93) | Solves for the insider fraction z. `p_i = [√(z² + 4(1−z) r_i²/Σr) − z] / (2(1−z))` | Insider-trading model. More margin on longshots. |
| Odds ratio (Cheung) | `r_i = c·p_i / (1 − p_i + c·p_i)`, solve c | Constant odds ratio between book and fair probabilities. |
| Logarithmic | Subtract constant c in log-odds space | Similar in spirit to odds-ratio. |
| Margin-proportional-to-odds (WPO, Buchdahl) | `fair_i = n·d_i / (n − M·d_i)` | Caps odds at n/M. Breaks for many-runner books. |

Sources: Lindstrøm, R package `implied` vignette (https://cran.r-project.org/web/packages/implied/vignettes/introduction.html) **[H]**; penaltyblog docs and blog (https://penaltyblog.readthedocs.io/en/latest/implied/implied.html, https://pena.lt/y/2025/09/14/from-biased-odds-to-fair-probabilities/) **[H]**; Buchdahl, *Wisdom of the Crowd* (https://www.football-data.co.uk/The_Wisdom_of_the_Crowd_updated.pdf) **[M, not fetched: HTTP 429]**.

### 2.2 Empirical comparisons
| Study | Data | Result | Conf. |
|---|---|---|---|
| Štrumbelj (2014), *IJF* 30(4):934–943 | football, many books | **Shin more accurate than basic normalization and than regression models.** | H (abstract) https://www.researchgate.net/publication/264349990 |
| Clarke, Kovalchik & Ingram (2017), *Am. J. Sports Sci.* 5(6):45–49 | tennis and other bookmaker data | **Power universally beats multiplicative and is comparable to or better than Shin.** Additive can go negative. Multiplicative has no FLB. | H (abstract/secondary) https://www.researchgate.net/publication/326510904 |
| `implied` vignette (Lindstrøm) | football, several books | Shin and power are very close. Shin is best for Pinnacle/Betfair/bet365; power is best for some softer books. | M |
| penaltyblog (2025) | EPL 2024/25, 380 matches, RPS | Multiplicative 0.19724 ≈ log 0.19730 ≈ OR 0.19730 ≈ Shin 0.19731 ≈ power 0.19739. **Differences negligible in an efficient 3-way market.** | M |
| Practitioner repo PR (football-ai) | 2,660 matches | Multiplicative not beaten by additive/power/Shin (Δlog-loss ~1e-4). | L https://github.com/MaksimBlud/football-ai/pull/442 |

**Synthesis:**
- **Two-way props near even money (−130 to +130):** all methods agree to <0.5 pp, so the choice barely matters. For n=2, Shin reduces to the additive method **[UNVERIFIED as a theorem; confirm in the `devig.py` unit tests]**.
- **Two-way props with a heavy favourite (e.g. SOG 1.5 over −300/+220, anytime goal "No"):** method choice matters by 1–3 pp on the dog side. Power, Shin and odds-ratio all load margin onto the dog. That is consistent with FLB evidence, so **multiplicative overstates the longshot's fair probability**, which inflates EV on the exact bets the top tier wants.
- **Multi-outcome boards (first goal scorer, ~40 outcomes):** use **power or Shin, not multiplicative or additive.** Additive goes negative, and WPO breaks at n/M. Racing FLB evidence (Snowberg & Wolfers) implies margin concentrates on longshots.
  - FGS nuance: the board should sum to 1 − P(no goal before shootout). That is ~0 in the NHL but non-zero if the book voids shootout-only games; check the rules. The `implied` package supports a `target_probability`.
  - **Anytime goal scorer is not a partition.** Σ P(scores) = E[#distinct scorers] ≈ 4.5–5 per game, not 1. Never normalize an AGS board to 1. Either de-vig each player's yes/no pair (if both sides are listed), or de-vig the board to a *target sum* from the team-goal model (E[distinct scorers] from the joint simulator). **[DERIVED]**
- **One-sided markets (DK/FD alt ladders list only the Over):** there is no de-vig. The fair value comes from our fitted distribution anchored to the de-vigged main line (the main rung pins the location; our dispersion supplies the tails).
- **Decision rule:** compute all methods. Use the **most conservative (lowest) fair probability for the side we bet** as the gating EV ("worst-case devig"). Log the per-method spread as an uncertainty feature. Choose the default method per market by out-of-sample log-loss of the close on our 2025-02 → 2026-06 data (PLAN M3, step 2).

---

## 3. Closing line value (CLV)

### 3.1 Evidence and caveats
- The close as truth: Pinnacle closes are ~1:1 calibrated in golf matchups (Data Golf) **[M]**. The Kaunitz et al. consensus-close method yielded profits at scale **[H]**.
- Beating the close by x% implies an expected long-run ROI of ≈x%, *if the close is efficient* (Buchdahl, via https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl; https://www.sportstradingnetwork.com/article/using-the-closing-line-to-test-your-skill-in-betting/) **[M]**. Buchdahl reports that CLV can reach significance in "as few as ~50 bets" where results take "several thousand" **[M]**.
- **Caveat 1:** props closes are less efficient (§1.1). CLV against a DK prop close mostly measures *copying the market*, not skill. Benchmark against the sharpest *measured* close per market, and verify the benchmark's own calibration first.
- **Caveat 2:** CLV and ROI can diverge if we systematically bet where the *close* is biased (e.g. FLB longshots). Always run the ROI test in parallel, with Bonferroni/BH across segments.

### 3.2 Measuring CLV properly
For a bet at decimal odds `d_b` with a de-vigged closing fair probability `q_c` of the same exact contract (same line/rung, same book or sharp benchmark):
- **Expected-value CLV:** `CLV_EV = q_c · d_b − 1`. This is the expected ROI if the close is true, and it is the primary metric.
- **Log-odds CLV:** `CLV_logit = logit(q_c) − logit(1/d_b fair-at-bet)`. It is additive and closer to normal, so use it for t-tests.
- Always use **leave-one-book-out** closes (don't include the book we bet at in the consensus) and **exact-contract keys**. Both are already PLAN M3 requirements.
- If the line moved (e.g. SOG 2.5 → 3.5), interpolate via our fitted distribution, or record "line-move CLV" separately. Don't compare across rungs.

### 3.3 Sample sizes [DERIVED]
The n needed to detect an edge with one-sided α=5% and 80% power is `n ≈ ((1.645 + 0.84)·σ/μ)²`.

| Test | Odds | True edge μ | σ per bet | n |
|---|---|---|---|---|
| ROI | −150 | 3% | 0.81 | ≈4,500 |
| ROI | +100 | 3% | 1.00 | ≈6,900 |
| ROI | +100 | 5% | 1.00 | ≈2,500 |
| ROI | +250 | 5% | 1.60 | ≈6,400 |
| ROI | +400 | 5% | 2.04 | ≈10,200 |
| ROI | +1000 | 10% | 3.30 | ≈6,700 |
| ROI | +3000 parlay | 20% | 5.98 | ≈5,500 |
| CLV | any | 2% | 0.04 | ≈25 |
| CLV | any | 2% | 0.08 | ≈100 |
| CLV | any | 1% | 0.08 | ≈400 |

(σ of CLV per bet is an **assumption** of 4–8% for props; estimate it from our own logs in week 1.)

**Implication:** the top tier's ROI will be statistically invisible for many seasons. **Only CLV and proper-score skill of its legs can validate it.**

---

## 4. Machine learning methodology

| Topic | Source | Key point | Conf. |
|---|---|---|---|
| Calibration vs accuracy for betting | Walsh & Joshi (2024), *ML with Applications* 16. https://www.sciencedirect.com/science/article/pii/S266682702400015X ; arXiv 2303.06021 | Calibration-selected models: **ROI +34.69% vs −35.17%** (accuracy-selected). Best case +36.93% vs +5.56%. NBA. | H |
| Accuracy ≠ profitability | Wunderlich & Memmert (2020), *IJF* 36(2):713–722. https://www.sciencedirect.com/science/article/abs/pii/S016920701930233X | The relationship between accuracy and betting return is **non-monotonic**. Don't select models on backtest ROI. | H (abstract) |
| Decorrelate from the book | Hubáček, Šourek & Železný (2019), *IJF* 35(2):783–796. https://ida.fel.cvut.cz/papers/hubacek2019exploiting.html | Penalizing correlation with bookmaker predictions improves profit. MPT-style bet allocation. NBA 2007–14. | H (abstract) |
| "Bad" model can beat the market | Hubáček & Šír (2023), *IJF* 39(2):691–719; arXiv 2010.12508 | Profits come from decorrelated errors plus being a market *taker* (choosing when to bet). | H (abstract) |
| Market odds as prior | Egidi, Pauli & Torelli (2018), *Stat. Modelling* 18:436–459. https://arxiv.org/pdf/1802.08848 | Hierarchical Bayesian Poisson whose rates are convex combinations of history-based and odds-based parameters. Better fit and prediction. | H |
| Proper scoring rules | Gneiting & Raftery (2007), *JASA* 102:359–378. https://ideas.repec.org/a/bes/jnlasa/v102y2007p359-378.html | Use strictly proper scores (log, Brier, CRPS/RPS) for model selection. Estimation by optimum score. | H |
| Platt/isotonic | Niculescu-Mizil & Caruana (2005), ICML. https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf | Boosted trees give a sigmoid distortion that Platt and isotonic both fix. **Isotonic overfits with small calibration sets.** sklearn advises against isotonic with ≪1,000 samples. | H |
| Beta calibration | Kull, Silva Filho & Flach (2017), AISTATS. https://proceedings.mlr.press/v54/kull17a.html | Three-parameter family. Contains the identity (can't make a calibrated model worse), handles skewed scores, beats logistic calibration. | H |
| Venn–Abers | Vovk & Petej (2014), UAI. https://www.auai.org/uai2014/proceedings/individuals/166.pdf | Isotonic-based multiprobabilistic predictor [p0, p1] with a **calibration guarantee under exchangeability**. The interval width is an uncertainty measure usable for stake shrinkage. | H |
| Tree models on tabular data | Grinsztajn et al. (2022), NeurIPS. https://www.researchgate.net/publication/362123616 | GBDTs beat deep nets on medium tabular data (~10k rows). | H |
| Time-series CV | Bergmeir & Benítez (2012), *Inf. Sci.*; Cerqueira et al. (2020), *Mach. Learn.* https://arxiv.org/pdf/1905.11744 | Use blocked/forward-chaining CV. Random k-fold leaks the future. | H |
| Leakage | Kaufman, Rosset & Perlich (2012), *ACM TKDD*. https://dl.acm.org/doi/epdf/10.1145/2382577.2382579 | Learn–predict separation. Leakage detection tactics. | H |
| Multiple testing | Harvey, Liu & Zhu (2016), *RFS* 29(1). https://academic.oup.com/rfs/article-abstract/29/1/5/1843824 ; Bailey & López de Prado (2014), Deflated Sharpe Ratio, *JPM* 40(5). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551 ; Bailey, Borwein, López de Prado & Zhu (2017), PBO, *J. Comp. Fin.* 20(4) | A new "factor" needs t>3. Deflate the best backtest by the number of trials. Estimate the probability of backtest overfitting via CSCV. | H |

**Rules for our system:**
1. **Target = residual to market.** Model: `logit(p) = a + b·logit(q_market_fair) + g(features)`, cross-fitted. Report the incremental log-loss vs the market-only fit (b free, g=0). If b≈1 and g≈0 out-of-fold, there is no edge. For count props, the analogue is a hierarchical NB/GP with the market-implied mean as an offset or prior (the Egidi et al. structure).
2. **Model families:** GLM/GAM or Bayesian hierarchical (partial pooling across players, as in PLAN M4–M6) as the backbone. GBDT (LightGBM/CatBoost) only on the residual, with monotone constraints where known (TOI↑ ⇒ SOG↑). Bayesian shrinkage matters most for low-sample players, who are the longshot AGS/FGS population.
3. **Calibration layer:** fit on out-of-fold predictions only.
   - Default **beta calibration** for binary rungs.
   - **Isotonic / Venn–Abers** only for markets with ≥1,000 OOF samples. Use the Venn–Abers `[p0,p1]` width as σ(edge) in stake shrinkage.
   - Check randomized PIT for counts.
4. **Evaluation:** nested walk-forward by month. Outer fold = model/hyperparameter evaluation; inner = tuning and calibration. Primary metric is log-loss (per rung) vs market-only. Secondary metrics are Brier, calibration slope/intercept, and ECE by odds decile. **Never select on ROI** (Wunderlich & Memmert).
5. **Leakage checklist (NHL-specific):**
   - Line combos, PP units or goalie starters taken from post-game data.
   - Season-to-date aggregates that include the target game.
   - MoneyPuck xG/shot features computed with the game.
   - Closing odds used as a feature for bet-time decisions. The bet-time price must be the snapshot at decision time.
   - Player-ID mapping drift.
   - Grading props from boxscores that include shootout goals or empty-net goals when the book's rules exclude them.
6. **Multiple testing:** every (market × rung × book × odds band × timing window) is a hypothesis.
   - BH-FDR at 10% for "which segments to deploy" (already in PLAN).
   - Report the deflated Sharpe / PBO for any strategy chosen from >20 variants.
   - Pre-register thresholds before looking at the holdout.

---

## 5. Staking: Kelly, portfolios, drawdowns and the pyramid

### 5.1 Single-bet Kelly and growth
`f* = (p·d − 1)/(d − 1) = EV/(d−1)`. Growth rate `g(f) = p·ln(1+f(d−1)) + (1−p)·ln(1−f)`. For small edges, `g(f*) ≈ EV²/(2(d−1))` (roughly; exact values in the table).

Numbers at EV = +5% [DERIVED]:

| Odds | p | full-Kelly f | g (full) per bet | g (¼ Kelly) |
|---|---|---|---|---|
| −200 | .700 | 10.0% | .00254 | .00110 |
| −110 | .550 | 5.5% | .00138 | .00060 |
| +100 | .525 | 5.0% | .00125 | .00055 |
| +250 | .300 | 2.0% | .00050 | .00022 |
| +400 | .210 | 1.25% | .00031 | .00014 |
| +1000 | .095 | 0.50% | .00012 | .00005 |
| +2000 | .050 | 0.25% | .00006 | .00003 |

**At the same EV, a −200 bet contributes ~40× the log-growth of a +2000 bet.** The pyramid's base tier is the growth engine. The top tier is nearly irrelevant to growth unless its EV is far larger.

**Over-betting is lethal:** growth as a fraction of optimum at even money [DERIVED]:

| Multiple of Kelly | 0.25 | 0.5 | 1 | 1.5 | 2 | 2.5 |
|---|---|---|---|---|---|---|
| Growth vs optimum | 0.44 | 0.75 | 1.00 | 0.75 | ≈0 | −1.27 |

If our edge estimate is 2× too big, "full Kelly" on the estimate is 2× true Kelly, which gives zero growth.

### 5.2 Parameter uncertainty (shrinkage)
- Baker & McHale (2013), *Decision Analysis* 10(3):189–199 (https://ideas.repec.org/a/inm/ordeca/v10y2013i3p189-199.html) **[H, abstract]**: with estimated p, the out-of-sample-optimal stake is `k·f*(p̂)` with 0<k<1.
- Chu, Wu & Swartz (2018), *JQAS* 14(1) (https://doi.org/10.1515/jqas-2017-0122) **[H, abstract]**: decision-theoretic modified Kelly. Stakes are smaller than Kelly in all cases studied, and it outperforms Kelly on long seasons.
- Practical approximation **[DERIVED / UNVERIFIED as their exact formula]**: `k ≈ μ̂² / (μ̂² + σ̂²_μ)`, where μ̂ is the estimated edge and σ̂_μ its standard error (from bootstrap / Venn–Abers width / devig-method spread). Example: μ̂ = 4%, σ̂ = 3% gives k = 0.64. Apply this *on top of* a base fraction ≤0.5.

### 5.3 Drawdowns and risk of ruin
- Continuous-time law: for fraction c of Kelly, `P(ever falling to a·W₀) = a^(2/c − 1)` (MacLean, Thorp & Ziemba 2010, via https://hmaquant.substack.com/p/position-sizing-under-fat-tails-when **[M]**). "Full Kelly: 50% chance of halving" is confirmed in Busseti et al. (https://web.stanford.edu/~boyd/papers/pdf/kelly.pdf) **[H]**.

| c (Kelly fraction) | P(ever −20%) | P(ever −30%) | P(ever −50%) | P(ever −75%) |
|---|---|---|---|---|
| 1.0 | 80% | 70% | 50% | 25% |
| 0.5 | 51% | 34% | 12.5% | 1.6% |
| 0.33 | 32% | 16% | 3.0% | 0.1% |
| 0.25 | 21% | 8% | 0.8% | ~0 |
| 0.1 | 1.4% | 0.1% | ~0 | ~0 |

(These assume the edge is *correctly* estimated. Overestimation shifts every row toward full Kelly.)
- **Risk-constrained Kelly** (Busseti, Ryu & Boyd 2016, *J. Investing*; arXiv 1603.06183) **[H]**: maximize E[log W] subject to a convex bound on the drawdown probability. It **beats fractional Kelly at equal drawdown risk**, and cvxpy code is available.
- **Uhrín, Šourek, Hubáček & Železný (2021), *IMA J. Mgmt Math*; arXiv 2107.08827 [H, read]:**
  - Pure Kelly and max-Sharpe are "infeasible in almost all practical scenarios with uncertain probability estimates" and "often led to ruin".
  - **Tuned fractional Kelly was best or near-best.**
  - A drawdown constraint performed similarly to fractional Kelly. Max-bet caps were inconclusive. Distributionally-robust Kelly was the safest.

### 5.4 Simultaneous and correlated bets (portfolio Kelly)
- Whitrow (2007), *JRSS C* **[H, abstract]**: stochastic-gradient solution for dozens of simultaneous bets. Simultaneous optimal stakes are close to proportional to (and a bit smaller than) the isolated Kelly stakes.
- Grant, Johnstone & Kwon (2008), *Decision Analysis* **[H, abstract]**: with multiplicative parlay payouts, a Kelly or λ-Kelly bettor using the full menu of singles and parlays achieves **the same wealth as sequential Kelly betting**.
- Long (2026), arXiv 2603.26620 **[M, preprint read]**:
  - The optimal full-menu stake on ticket γ is `x*_γ = Π_{ℓ∈T} s*_ℓ · Π_{r∉T} c*_r`, the **outer product of the one-event Kelly solutions**.
  - A parlay is active iff *every* leg is active (+EV) on its own.
  - The **growth lost by forbidding parlays is O(ε⁴)**, and simultaneous singles are the isolated Kelly stakes with cubic shrinkage.
- **Correlated legs (same game):** independence fails. Optimize `E[log(1 + Σ_j f_j R_j)]` over joint scenarios drawn from the joint simulator (Monte Carlo, 10–50k draws), with cvxpy or scipy. This handles, e.g., the Over on team total + the AGS of the top-line centre + his SOG over, which are positively correlated, so singles on all three are *already* a concentrated position.

**Two-leg example [DERIVED]** (independent legs, each p=.525 at 2.0, EV +5%):

| Strategy | Stakes | Log-growth per slate |
|---|---|---|
| Singles only (simultaneous Kelly) | 5.00% each | .002498 |
| Full menu (singles + parlay) = sequential Kelly | — | .002501 |
| Parlay only (EV +10.25%, d=4) | Kelly 3.42% | .001713 (**−31%**) |

**Parlaying +EV legs raises EV per dollar but lowers growth per unit of bankroll risk vs betting the legs as singles.**

### 5.5 Reconciling a GPP/lottery top tier with long-run growth
- **Barbell** (Taleb, secondary summaries, e.g. https://fourweekmba.com/barbell-strategy-taleb/) **[L–M]**: most capital in the robust core, a small bounded sleeve in convex payoffs, and nothing in the middle.
  - Mapped to us: the core is the ¼-Kelly base and middle tiers. The sleeve is a fixed nightly lottery budget B_top with bounded loss (the whole sleeve).
  - Note: Taleb's "avoid the middle" does *not* transfer. Our middle tier (+EV plus-money singles) is perfectly good Kelly business.
- **DFS GPP analogy:** Haugh & Singal (2021), "How to Play Fantasy Sports Strategically (and Win)", *Management Science*; preprint http://www.columbia.edu/~mh2078/DFS_Revision_1_May2019.pdf **[H]**.
  - Top-heavy payouts reward *variance and low correlation with the field*. A mean-variance/Dirichlet-multinomial opponent model is used.
  - The analogy is imperfect: sportsbook parlays are *fixed-odds*. There is no field to be contrarian against, and variance is not rewarded per se; only EV and log-growth are.
  - What *does* transfer: when you want a fat right tail, **concentrate the lottery budget on the highest-EV correlated structures** (e.g. a stack of one line's players when our joint model says the book underprices the correlation), rather than on many random longshots.
- **Kelly for longshots:** stakes shrink ∝ 1/(d−1). A +5000 ticket with a genuine 20% EV has full-Kelly f = 0.4%, so a ¼-Kelly stake is 0.1% of bankroll. It pays 5.1% of bankroll when it hits. **A "100× night" on the bankroll would require ~20× Kelly-sized lottery stakes, which has negative long-run growth.** Define "10×–100×" on the lottery budget, not the bankroll.

### 5.6 Pyramid simulation [DERIVED; 180 nights, 1,500 paths, independent legs]
Setup:
- Base: 8 bets/night at −150, est. EV 3%.
- Middle: 5 bets/night at +200, est. EV 5%.
- Top: 2 three-leg parlays of +150 legs (each leg est. EV 5%, parlay EV 15.8%, d=15.6, full-Kelly 1.08%).
- Base/middle are staked at ¼ or ½ Kelly. Top is a fixed fraction per ticket.
- "Shift" = the true EV is lower than estimated by 3 pp on every bet and leg.

| Shift | Top stake/ticket | Kelly (base/mid) | Median final W | P10 | P90 | P(W<1) | Median maxDD |
|---|---|---|---|---|---|---|---|
| 0 | 0 | ¼ | 1.98 | 1.13 | 3.46 | 6% | 25% |
| 0 | 0.5% | ¼ | **2.40** | 1.17 | 4.98 | 5.5% | 31% |
| 0 | 2.0% | ¼ | 1.98 | 0.32 | 14.8 | 32% | 72% |
| 0 | 0.5% | ½ | 3.81 | 1.04 | 13.0 | 9% | 48% |
| −3pp | 0 | ¼ | 1.03 | 0.59 | 1.77 | 48% | 37% |
| −3pp | 0.5% | ¼ | 1.09 | 0.52 | 2.21 | 44% | 43% |
| −3pp | 2.0% | ¼ | 0.58 | 0.10 | 4.06 | 65% | 82% |
| −3pp | 0.5% | ½ | 0.87 | 0.27 | 3.12 | 55% | 65% |

Reading:
- (a) A small top tier (≈½ Kelly of the ticket) adds growth *if the legs are truly +EV*.
- (b) A 2% top tier (~2× Kelly) creates a lottery-shaped bankroll: P90 of 15×, but a third of paths lose money.
- (c) **Edge overestimation dominates everything.** At −3 pp, every configuration is at best flat. That is why calibration, CLV gating and shrinkage rank #1.
- These sims assume independence and an unrealistically steady edge supply. Treat them as **directional only**.

---

## 6. Python tooling

| Need | Library | Notes | Verified this session |
|---|---|---|---|
| De-vig (multiplicative, additive, power, Shin, OR, log, DMW) | `penaltyblog` (`penaltyblog.implied.calculate_implied`) | Most complete Python set | yes (docs) |
| Shin only | `shin` (github.com/mberk/shin) | Fast; n-outcome | yes |
| Reference implementation | R `implied` (Lindstrøm), incl. `target_probability`, `bb`, `jsd` | Use as the unit-test oracle via rpy2 or copied known answers | yes |
| Calibration | `scikit-learn` `CalibratedClassifierCV` (sigmoid/isotonic), `betacal`, `venn-abers` (github.com/ip200/venn-abers) | venn-abers has had no PyPI release in 12 months | yes |
| Proper scores | `scoringrules` (Python port) / `properscoring`; sklearn `log_loss`, `brier_score_loss` | CRPS for count distributions | partially (R `scoringRules` seen) |
| GBDT | `lightgbm`, `catboost`, `xgboost` | Monotone constraints; categorical players | standard (not re-verified) |
| GLM / count models | `statsmodels` (NB2, GeneralizedPoisson, ZeroInflated) | Offsets for TOI | standard |
| Bayesian hierarchical | `PyMC`, `NumPyro`, `bambi`, `cmdstanpy` | Partial pooling across players/goalies | standard |
| Time-series CV | sklearn `TimeSeriesSplit` + custom month-block nested splitter | Keep our own harness (PLAN M12) | — |
| Multiple testing | `statsmodels.stats.multitest.multipletests(method="fdr_bh")` | BH-FDR | standard |
| Portfolio / risk-constrained Kelly | `cvxpy` (Busseti et al. formulation), `scipy.optimize` | Scenario-based E[log W] | paper code referenced |
| Conformal/intervals | `mapie` | Prediction intervals for TOI/SOG | standard (not re-verified) |
| Deflated Sharpe / PBO | small custom module (formulas in Bailey & López de Prado) | Avoid unvetted packages | — |

---

## 7. Recommended rules and parameters (v0, to be re-fit on our data)

### 7.1 EV thresholds by odds band
EV is computed vs the **conservative (worst-case across devig methods) fair probability**, blended with the model (stack output, after calibration and shrinkage).

| Band (American) | Min EV | Extra requirement |
|---|---|---|
| −300 to −131 | 2.0% | Model and market agree on direction. Cap is inherited from Kelly. |
| −130 to +130 | 3.0% | — |
| +131 to +300 | 5.0% | — |
| +301 to +1000 | 8.0% | Segment CLV t-stat > 0 over the last 100 bets. |
| > +1000 (AGS/FGS longshots, alt top rungs) | 12–15% | A structural reason logged (line/PP promotion, goalie change, dispersion mismatch), not model residual alone. |
| Parlays (independent legs) | Each leg passes its own band | Parlay EV = Π(1+EV_i) − 1. Max 3 legs by default (≤4 in the lottery tier). |
| SGP | Joint EV ≥ 15% vs **our simulated joint** | Only after ≥300 logged SGP quotes show the simulator's joint is calibrated. Otherwise **no SGPs**. |

Rationale: estimation error and FLB both grow with odds (§1.5, §2.2). The bands roughly track 1–1.5σ of the edge standard error at typical sample sizes **[DERIVED, to be re-estimated]**.

### 7.2 Staking
- **Base and middle tiers:** stake = `0.25 × k_unc × f*` (Kelly fraction ¼ times the uncertainty shrink `k_unc = μ̂²/(μ̂²+σ̂²)`, floored at 0.3).
  - Per-bet cap: 1.5% of bankroll.
  - Per-game correlated cap: 4%, with stakes jointly optimized on simulated joint outcomes.
  - Nightly total exposure cap: 15%.
- **Lottery tier:** fixed nightly budget **B_top = 0.5% of bankroll** (hard max 1%).
  - Each ticket ≤ min(½ Kelly of the ticket, 0.5% of bankroll).
  - If the lottery tier's cumulative CLV over 200 tickets is ≤ 0, cut B_top to 0.25%.
  - Define and report "10×/100× nights" relative to B_top.
- **Drawdown governor:**
  - At −20% from peak, halve all fractions.
  - At −35%, pause live betting and move to paper trading pending review.
  - Alternatively, implement risk-constrained Kelly with `P(DD to 0.7) ≤ 10%`.
- **Scale-up gate:** raise the Kelly fraction from ¼ to ⅓ only when **all** of these hold:
  - ≥500 settled bets in the segment
  - mean CLV_EV > 1% with t > 3 (Harvey et al. hurdle)
  - out-of-fold log-loss better than market-only in the majority of months

### 7.3 CLV tracking spec
- **For every candidate (bet or pass), log:**
  - timestamp, book, exact contract key, bet price, fair probability at bet (per devig method), model p, σ(edge)
  - at close: sharp-book close, leave-one-book-out consensus close, same-book close
- **Metrics:** `CLV_EV` (primary) and `CLV_logit` (for tests), plus a line-move flag.
- **Report** by market × rung × odds band × book × time-to-puck. Show mean, SE, t, and the cumulative CLV chart vs cumulative ROI chart.
- **Alarms:**
  - rolling-200 CLV t < 0 → segment auto-paused
  - the gap between CLV-implied ROI and realized ROI beyond 2.5σ → investigate grading or close quality
- **Benchmark validity:** quarterly, re-fit the log-loss of each close source vs outcomes by market. Use the best source as the CLV reference for that market.

### 7.4 Parlay policy (summary)
1. Only combine legs that are individually +EV above their band threshold.
2. Independent (cross-game) legs by default.
3. Same-game legs only through the joint simulator.
4. Prefer singles for growth. Parlays live only in the lottery budget.
5. Legs ≤3, or ≤4 in the lottery tier. The per-leg decay of ~3% (Moshrefi) plus FLB kills longer tickets.
6. Never use book-promoted "boosts" as validation. Treat a boost as a price, and run it through the same EV gate.

---

## 8. Open questions

1. **Is the 5-minute snapshot cadence fast enough for H2 lead-lag?** Vendor claims (pregame lags of 15–60 min) are unverified. Measure the half-life of DK/FD–Pinnacle gaps from our own archive.
2. **Which close is sharpest per NHL prop market?** Pinnacle, the SGO consensus, or FanDuel? No NHL-specific study was found. This must be measured (PLAN M3 step 2).
3. **Direction of the NHL moneyline FLB in 2025–26.** The literature conflicts (reverse FLB in older studies; normal FLB in one thesis).
4. **Does Shin reduce exactly to additive for n=2?** Believed true; confirm with known-answer unit tests. Which method minimizes log-loss for AGS boards de-vigged to a target sum?
5. **Account lifetime model.** The number of bets or amount of CLV before DK/FD limit an NHL prop account is unknown. Log stake-acceptance data from day 1.
6. **σ of CLV per bet for NHL props** (the sample sizes in §3.3 assume 4–8%).
7. **Primary-source checks still pending:**
   - Buchdahl's *Wisdom of the Crowd* PDF (HTTP 429)
   - Pinnacle articles (JS-rendered, not readable)
   - the exact Baker–McHale shrinkage formula
   - the Clarke et al. full comparison table (HTTP 403)
   - the Woodland & Woodland original numbers
8. **Top-tier validation.** The ROI of +1000 tickets is unmeasurable for years (§3.3). Decide whether lottery-tier legitimacy rests solely on leg-level CLV and leg-level calibration.

---

## Source list (distinct sources consulted: 45)
Walsh & Joshi 2024; Štrumbelj 2014; Lindstrøm `implied`; Clarke/Kovalchik/Ingram 2017; penaltyblog docs + blog; Moshrefi 2026; Snowberg & Wolfers 2010; Levitt 2004; Dmochowski 2026 (profit-bias); Dmochowski 2023 (PMC10306238, statistical theory of betting); Hegarty & Whelan 2025; Woodland & Woodland (via UNC Charlotte WP and Aalto thesis); Kaunitz/Zhong/Kreiner 2017; Hubáček/Šourek/Železný 2019; Hubáček & Šír 2023; Uhrín et al. 2021; Baker & McHale 2013; Chu/Wu/Swartz 2018; Busseti/Ryu/Boyd 2016; MacLean/Thorp/Ziemba 2010; Whitrow 2007; Grant/Johnstone/Kwon 2008; Long 2026; Gneiting & Raftery 2007; Kull et al. 2017; Niculescu-Mizil & Caruana 2005; Vovk & Petej 2014; Egidi/Pauli/Torelli 2018; Wunderlich & Memmert 2020; Kaufman/Rosset/Perlich 2012; Bergmeir & Benítez 2012; Cerqueira et al. 2020; Harvey/Liu/Zhu 2016; Bailey & López de Prado 2014; Bailey et al. 2017; Grinsztajn et al. 2022; Haugh & Singal 2021; Data Golf; Unabated; Establish The Run; UKGC restriction data (iGB, SBC Americas); Massachusetts limits rule (gambling.com); Illinois parlay hold (Covers); OpticOdds SGP; Pinnacle hold article; Buchdahl CLV interview (pinnacleoddsdropper); scikit-learn calibration docs; betacal and venn-abers repos; practitioner de-vig PR (football-ai); Taleb barbell (secondary).
