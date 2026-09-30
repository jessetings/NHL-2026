# Research Digest 01: Simulation and Game/Player Modeling for NHL Market Pricing

**Status:** 2026-09-30. Research agent output for Handoff v1 §7 (A, B, C, D, I) and §8 (draft simulation design).
**Scope:** Monte Carlo practice, NHL scoring-process models, player-level models (shots, xG, finishing, goalies, TOI, PP, rest), first/anytime goal-scorer pricing, and open-source tools.

**Labels used below**
- **[V]** means verified: I read the primary source, its abstract, or its publisher/index page in this session.
- **[S]** means secondary: the claim comes from a secondary write-up or a search snippet, and I did not read the primary source.
- **[U]** means unverified or conflicting. Do not rely on it without checking.
- **[INT]** means an internal estimate I computed in this session from our own curated data (`data/curated/`). It is a quick method-of-moments check, not a fitted model. Re-derive it inside the M4–M6 pipeline before using it.

---

## 1. Key takeaways (ranked by expected profit impact for us)

1. **Monte Carlo error must be far below the edge threshold. For single-player props, compute analytically instead of simulating.**
   - With N iid sims, SE(p̂) = √(p(1−p)/N). At N = 10k and p = 0.5, SE = 0.5 pp, which is as large as many real edges.
   - Use conditional / Rao-Blackwellized estimators. Example: simulate team shots and TOI, then compute P(player SOG ≥ k) exactly from the binomial or Poisson given those draws, and average over draws.
   - Reserve the full joint simulation for things that need joint structure: SGPs, puck line, 3-way, empty-net and endgame markets, and correlated portfolios.
   - Defaults are in §3.1.
   - Sources: Owen, *Monte Carlo theory, methods and examples*, ch. 8; SciPy QMC docs. **High impact:** it stops us from betting noise.

2. **Empty-net goals are the dominant non-Poisson feature of NHL scoring. They must be a separate endgame sub-model.** [INT][V]
   - In our 2023-24 → 2025-26 regular-season PBP, EN goals were **0.34–0.40 per game** (about 6–7% of all goals).
   - The EN rate has roughly tripled since 2005-06 (2.4% → 7.0% of goals; Pidutti/DailyFaceoff).
   - Excluding EN goals, period-3 scoring equals period-1 scoring exactly (2023-24: 1.790 goals per game in both; this matches Sound of Hockey).
   - EN goals drive the negative correlation between home and away regulation goals, and they shape puck-line (±1.5) and totals pricing.
   - **High impact:** puck line, totals, anytime goal (AG) for top-line players and D who play 6v5 / 5v6, and SGPs.

3. **Regulation goals excluding EN are *under*dispersed and roughly independent between the two teams. Do not add a large shared Gamma "pace" factor.** [INT]

   | Season | Team-goal var/mean (with EN) | Team-goal var/mean (no EN) | corr(H, A), all | corr(H, A), no EN |
   |---|---|---|---|---|
   | 2023-24 | 1.00 / 1.06 | 0.94 / 0.96 | −0.12 | −0.01 |
   | 2024-25 | 1.01 / 1.04 | 0.93 / 0.95 | −0.09 | +0.05 |
   | 2025-26 | 1.01 / 0.96 | 0.93 / 0.87 | −0.08 | +0.08 |

   - A shared Gamma pace multiplier (handoff §8.1) *adds* overdispersion and *positive* correlation. The data leave little room for either.
   - The pace variance must be fitted so that the simulated marginal var/mean ≈ 1.0 (including EN) and corr ≈ −0.1.
   - Ryder (2004) found the same near-independence (league GF–GA correlation −0.04 over 1999-2004) [V].
   - **High impact** on totals and alt-total ladders, where tails are exactly what the pace factor distorts.

4. **Shrink finishing talent heavily, and shrink it by position. Defensemen have essentially no repeatable finishing above xG.** [INT]
   - Using MoneyPuck xG on unblocked, non-EN regular-season attempts from 2022-23 → 2025-26:
     - **Forwards:** SD of the true G/xG multiplier ≈ 0.125. The regression constant is **K ≈ 64 xG ≈ 775 unblocked attempts** (roughly 3–4 seasons for a typical top-9 forward). Year-over-year r(G/xG) = 0.34.
     - **Defensemen:** year-over-year r(G/xG) ≈ −0.03. Treat D finishing as league-average × xG.
   - External work agrees that single-season shooting % carries little signal:
     - Fowleball: sh% explains 6.4% of next-year variance, which implies "regress about 75%" [S].
     - Evolving-Hockey found a shooter-talent feature was never used by their XGBoost xG model [V].
   - **High impact on anytime-goal pricing.** Books appear to price "narrative" scorers (see §2.4).

5. **Goalie talent is real but small and slow to reveal. Shrink GSAx hard.** [INT][V]
   - Our estimate: SD of true GSAx per shot on goal ≈ 0.0065 (about 6.5 points of sv%). The regression constant is **K ≈ 2,100 shots on goal** (about 1.3 seasons of a starter's workload). Year-over-year r ≈ 0.22 (n = 162 goalie-season pairs).
   - External numbers match: Schuckers (2016) reports split-half sv% correlations averaging about 0.21 (500+ shots) and near-zero year-over-year sv% correlations [V]; Puck Over the Glass reports a GSAx autocorrelation of about 0.22 [S].
   - **Medium-high impact** on ML, totals and saves props. Starter confirmation matters more than goalie "form."

6. **Model overtime and the shootout from recent seasons. Rates shift a lot from year to year.** [INT][V]

   | Season | Regulation tie rate | OT games decided in 3v3 | Home win in 3v3 OT | Home win in SO |
   |---|---|---|---|---|
   | 2022-23 | 23.0% | 68.5% | 56.5% | 42% |
   | 2023-24 | 20.7% | 69.9% | 53.7% | 59% |
   | 2024-25 | 20.7% | 71.6% | 54.1% | 53% |
   | 2025-26 | 24.8% | 63.5% | 50.2% | 47% |

   - DailyFaceoff independently reports 71.6% and 63.6% for the "decided in 3v3" column [V].
   - The shootout is close to a coin flip. Use about 50%, with only weak skater and goalie effects.
   - **Medium impact:** 3-way/regulation ML, "reg-time" markets, and whether OT goals count for props (they count at FD/DK; shootout goals do not).

7. **Score effects and "last goal" effects are real and time-dependent. A game-state simulation captures them; independent Poisson draws do not.** [V]
   - Leading teams' xG production falls about 10–15%, while trailing teams keep roughly tied-game pace (McCurdy/HockeyViz).
   - The team that scored the most recent goal gets about a 5% threat change. Third-period tying goals depress the scorer's next-shot threat by 10–15%.
   - **Medium impact** on SOG overs for trailing teams' players, saves props, and SGPs such as "team wins + opposing goalie saves over."

8. **Build correlation structurally, from shared latent drivers and a game-state timeline. Do not glue marginals together with copulas.**
   - Copulas with discrete (count) margins are not unique and distort rank-dependence measures (Genest & Nešlehová 2007) [V].
   - The Gaussian copula has zero tail dependence, so it understates joint extremes (Embrechts, McNeil & Straumann 2002) [V].
   - In our setting the joint structure comes naturally from: team goals → assists and points; team shots → player SOG → opposing goalie saves; game script → EN goals.
   - Use a copula only as a diagnostic, or to add residual correlation that the structural sim provably misses.
   - **High impact for SGPs**, where books apply their own correlation engines and prices differ across books by +650 vs +850 for the same SGP [S].

9. **The second period is the highest-scoring period (the long-change effect). First-period scoring is the lowest.** [V][INT]
   - Our data give about 1.73–1.79 goals per game in P1 versus 2.00–2.10 in P2. Sound of Hockey reports P2 +17.2% over P1/P3 excluding EN in 2023-24.
   - A flat per-minute rate therefore **overstates first-goal timing in P1**. That matters for the first-goal-scorer (FGS) market, first-period markets, and "goal in first 10 minutes."
   - **Medium impact.**

10. **Rest and back-to-back effects: team effects exist; individual goalie effects are mostly removed by selection.** [S][U]
    - Old team-level splits (2007-12, McKeen's): rested teams won 59.6% against tired teams' 49.5%, with a 3.6-point CF% swing [S].
    - HockeyViz's Magnus model uses about an 11.5% rested-vs-tired advantage [S].
    - Goalie-level: a DataStreak analysis of 1,409 back-to-back starts found GAA of 2.79 versus 2.77 for rested starts, attributing the absence of an effect to coaches screening out fatigued goalies [S].
    - The oft-quoted "11% save-percentage drop" (Tulsky 2013, as quoted by NHL.com) is almost certainly a mis-statement of a roughly 0.01 sv% drop [U].
    - **Low-medium impact.** Markets already know the schedule. Use small priors, and let the H3/H4 residual tests decide.

---

## 2. Detailed findings by topic

### 2.1 Monte Carlo simulation best practice

**(a) Time resolution: event, period or minute?**
- **HockeyViz Magnus 5 game sim** [V] — https://hockeyviz.com/txt/magnus5GameSim
  - It runs **per-second Bernoulli draws** for 3,600 seconds.
  - Penalties are drawn each second from team rates. A penalty lasts 120 seconds; the source excerpt I read does not say whether a power-play goal ends it early.
  - Shots are drawn each second at team rate / 3600. Then the shooter, location and type are drawn.
  - Score-dependent shot rates are used, with "hardcoded goal probabilities in the final three minutes" by score differential (the endgame).
  - 300 seconds of OT, then a **50/50 shootout**.
  - "Approximately ten thousand simulations are sufficient."
  - *Apply:* the per-second Bernoulli scheme is equivalent to a piecewise-constant hazard. We should implement the same model **event-driven**: draw exponential waiting times for the next event given the current state (strength, score, time, goalie in or out), in the style of Gillespie (1977, *J. Phys. Chem.* 81:2340), which is not re-verified here. This is exact and about 100× fewer RNG calls.
  - State changes only at goals, penalties, penalty expiry, goalie pulls, period ends, and line changes if we model them.
- **Thomas, Ventura, Jensen & Ma (2013)**, "Competing process hazard function models for player ratings in ice hockey", *Annals of Applied Statistics* 7(3):1497–1524 [V] — https://arxiv.org/abs/1208.0799 and https://projecteuclid.org/euclid.aoas/1380804804
  - Each team's scoring is modeled as a semi-Markov process whose hazard depends on the players on ice. It covers 5v5 only, with hierarchical Bayes shrinkage by position.
  - *Apply:* this is the theoretical justification for piecewise-constant, deployment-dependent hazards. The same structure lets us time-vary hazards by period and state.
- **Recommendation**
  - For ML, totals, puck line and 3-way: an event-driven sim with states {score diff, period, time, strength, goalie pulled}.
  - Period-level Poisson is acceptable *only* as a fast baseline, and only with an explicit endgame/EN sub-model bolted on.
  - Minute-level discretization adds bias (at most one event per minute) with no benefit over event-driven.
  - **Confidence: high.**

**(b) How many sims?** (formula, not a source claim)
- SE(p̂) = √(p(1−p)/N). The relative SE for small p is ≈ √(1/(pN)).

  | Target | Required N |
  |---|---|
  | Main ML/total, SE ≤ 0.25 pp at p ≈ 0.5 | N ≥ 40,000 |
  | Alt rung with p = 0.05, relative SE ≤ 5% | N ≥ 7,600 |
  | Alt rung or SGP with p = 0.02, relative SE ≤ 5% | N ≥ 19,600 |
  | 3-leg SGP with p = 0.01, relative SE ≤ 5% | N ≥ 40,000 |

- Rao-Blackwellization (conditioning), described below, cuts these numbers substantially for player props.
- For Sobol QMC, use N = 2^m (for example 65,536 = 2^16). Changing N by even one sample can degrade QMC convergence (SciPy docs [V]).
- **Confidence: high.**

**(c) Variance reduction**
- **Owen, *Monte Carlo theory, methods and examples*, ch. 8 "Variance reduction"** [S: search summary of the chapter; the PDF returned 503 during fetch] — https://artowen.su.domains/mc/Ch-var-basic.pdf
  - Antithetic sampling helps when the paired evaluations are negatively correlated, which is typical for monotone functions of the uniforms. In the worst case it doubles the variance.
  - Common random numbers (CRN) are the tool for *differences* between systems.
  - The chapter also covers stratification and control variates.
- **SciPy `scipy.stats.qmc`** [V] — https://docs.scipy.org/doc/scipy/reference/stats.qmc.html
  - Engines: Sobol', Halton, LatinHypercube, MultivariateNormalQMC.
  - Scrambled (randomized) QMC gives unbiased estimates plus CIs, with error approaching O(n⁻¹) for smooth integrands.
  - Prefer powers of 2 for Sobol'.
- **MIT 15.450 lecture on RNG, variance reduction and QMC** (finance) [S] — https://ocw.mit.edu/courses/15-450-analytics-of-finance-fall-2010/4fa033082ff5ee58722a67fe81f0dce7_MIT15_450F10_lec03.pdf
- **NumPy parallel RNG** [V] — https://numpy.org/doc/stable/reference/random/parallel.html
  - Use `SeedSequence.spawn()` (or `default_rng([stream_id, root_seed])`) for independent, reproducible streams. Never use `root_seed + i`.
  - *Apply:* give each game a spawned stream keyed by (game_id, model_version). Then reruns are bit-identical (this fits the "reproduce from snapshot hash" requirement), and CRN comparisons are possible.
- **How to apply**
  1. **CRN for scenario deltas.** Examples: starter A vs backup B, a player in or out, or PP1 promotion. Reuse the same uniforms so that the *difference* in prices has low variance. This is essential for the "what if the goalie is not confirmed" pricing and for line-move attribution.
  2. **Conditioning / Rao-Blackwellization** is usually the biggest win.
     - Given a simulated team-level path (team SOG, player TOI by state, goalie), compute each player's P(SOG ≥ k), P(goal ≥ 1) and so on in closed form (binomial or Poisson given the conditional rate), then average.
     - The sports precedent is "Rao-Blackwellizing field goal percentage" (Daly-Grafstein & Bornn, arXiv:1808.04871 [S; seen in search, not read]).
  3. **QMC** helps for the low-dimensional *continuous* latent layer: pace, team-strength posterior draws and goalie draws. It helps little for the long discrete event chain. Use scrambled Sobol for the latent draws, and PCG64 for the event chain.
  4. **Antithetic** variates help for monotone latent draws, such as a team-strength posterior draw and its mirror. They should not be used on the discrete event chain without checking the gain empirically.
- **Confidence: high** (standard numerical practice).

**(d) Correlation: copulas vs shared latent factors**
- **Embrechts, McNeil & Straumann (2002)**, "Correlation and dependence in risk management: properties and pitfalls", in Dempster (ed.), *Risk Management: Value at Risk and Beyond*, CUP, pp. 176–223 [V] — https://www.risknet.de/fileadmin/eLibrary/Embrechts-Correlations-1999-ETH-Paper.pdf
  - Linear correlation is not dependence.
  - The Gaussian copula has zero tail dependence.
  - Not every correlation matrix is attainable for given margins.
- **Genest & Nešlehová (2007)**, "A primer on copulas for count data", *ASTIN Bulletin* 37(2):475–515, doi:10.2143/AST.37.2.2024077 [V] — https://www.casact.org/abstract/primer-copulas-count-data
  - With discrete margins the copula is not unique, and Kendall's tau and Spearman's rho depend on the margins. Inference and interpretation become tricky.
- **NORTA / Gaussian copula for correlated NB counts** [S] — for example https://link.springer.com/article/10.1186/s40488-021-00119-y
  - It works for *generation*, but the correlation must be calibrated on the latent scale.
- **Industry analogue:** the insurance/credit one-factor (Vasicek-type) model conditions on a common factor and treats exposures as conditionally independent. That is the "shared latent factor" design in §8 of the handoff.
- **Recommendation**
  - Correlation should come from structure:
    - (i) game-level latent draws (team strengths, posterior uncertainty, a small pace factor);
    - (ii) the shared timeline (score state, strength state, EN);
    - (iii) the accounting identities (the goalie's saves equal the opponent's SOG minus goals; assists attach to goals).
  - Validate the result against empirical pairwise correlations. Examples: player SOG vs teammate SOG; player points vs team goals; opposing goalie saves vs team SOG; AG vs team win.
  - Add a copula only as a residual layer, and only if validation fails.
  - **Confidence: high.**

### 2.2 Hockey scoring-process models

**Named papers (all verified)**

| Paper | Venue | Key content | How to apply |
|---|---|---|---|
| **Buttrey, Washburn & Price (2011)**, "Estimating NHL Scoring Rates" [V]. https://doi.org/10.2202/1559-0410.1334 · https://ideas.repec.org/a/bpj/jqsprt/v7y2011i3n24.html | *JQAS* 7(3), Art. 24 | Goals follow a Poisson process whose rate depends on the two teams, home ice and manpower (PP/SH). Useful for handicapping and for pull-the-goalie decisions. | This is exactly the per-state rate structure we need. Fit λ(team, opp, home, strength) on regulation, non-EN time, with state exposure from shifts/PBP. |
| **Beaudoin & Swartz (2010)**, "Strategies for pulling the goalie in hockey" [V]. https://econpapers.repec.org/article/besamstat/v_3a64_3ai_3a3_3ay_3a2010_3ap_3a197-204.htm | *The American Statistician* 64(3):197–204 | A simulator with finer game situations, penalties and home ice. Constrained Bayesian estimation by MCMC. Finds optimal pulls earlier than coaches use; Schuckers summarises the gain as roughly 1–2 extra points per season. | A template for the endgame sub-model. But we must model the *coaches' actual* pull behaviour, not the optimal one. |
| **Asness & Brown (2018)**, "Pulling the Goalie: Hockey and Investment Implications" [S: from search summaries and Chicago Booth Review, abstract page not read]. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3132563 · https://review.chicagobooth.edu/finance/2018/article/when-hockey-teams-and-money-managers-should-go-broke | SSRN | 2015-16 data. Pulling raises own scoring by about 1.18% per 10 s but opponent scoring by about 2.54% per 10 s. Optimal pull at about 6 min when down 1 and about 13 min when down 2. | Actual coaching behaviour is later but trending earlier. |
| **Hall (2020)**, "The State of Goalie Pulling in the NHL" [V]. https://hockey-graphs.com/2020/05/18/the-state-of-goalie-pulling-in-the-nhl/ | Hockey-Graphs | 2013-14 → 2019-20. 6v5 ≈ **6.5 GF/60**; EN against ≈ **12 GA/60** (6v4 about 12/60 as well; a search snippet said 19/60 [U]). Average 1-goal-down pull time rose by about 30 s over 7 seasons. Trailing team ties or wins in about 15% of 1-goal pulls. | Starting priors for the endgame hazards. **Refit on 2023-26 PBP** (we have `situationCode` goalie flags), because pull times keep moving earlier. |
| **Pidutti (2024)**, "The rise of empty net goals is changing the NHL" [V]. https://www.dailyfaceoff.com/news/how-empty-net-goals-have-changed-the-nhl | DailyFaceoff | EN share of goals 2.4% (2005-06) → 7.0% (2024-25, first quarter). About 0.42 EN goals per game. 13.8 EN goals per team in 2023-24. | Our INT figure is 0.34–0.40 per game over full seasons. |
| **Ryder (2004)**, "Poisson Toolbox" [V]. http://hockeyanalytics.com/Research_files/Poisson_Toolbox.pdf | HockeyAnalytics.com | Goal counts pass a chi-square test for Poisson. Endgame EN goals are about 100% "excess" (≈ 0.1 goals per team per game in 2004). GF and GA are nearly independent (league r = −0.04), and hockey is a "negative-correlation sport". | Confirms the structure. The endgame share has since grown about 3×. |
| **Karlis & Ntzoufras (2003)**, "Analysis of sports data by using bivariate Poisson models" [V]. https://rss.onlinelibrary.wiley.com/doi/abs/10.1111/1467-9884.00366 | *JRSS D* 52(3):381–393 | Bivariate Poisson with a common λ₃ (positive covariance), plus diagonal inflation for draws. | Bivariate Poisson allows only *positive* covariance, but our non-EN correlation is ≈ 0 and the with-EN correlation is negative. **Not a good fit for the NHL.** Get dependence from the state sim instead. |
| **Dixon & Coles (1997)** [V]. https://doi.org/10.1111/1467-9876.00065 | *JRSS C* 46(2):265–280 | Poisson with a low-score dependence correction τ and time-decay weighting of past matches. Showed a positive betting return. | The **time-decay weighting** (exp(−ξt)) transfers directly to team-strength fitting. The low-score τ correction is soccer-specific; hockey's analogue is the regulation-tie inflation, which the state sim captures. |
| **Marek, Šedivá & Ťoupal (2014)**, "Modeling and prediction of ice hockey match results" [V]. https://doi.org/10.1515/jqas-2013-0129 | *JQAS* 10(3):357–365 | An alternative bivariate Poisson for the Czech Extraliga, 1999–2012. | Hockey-specific bivariate model. A baseline comparator only. |
| **Baio & Blangiardo (2010)**, Bayesian hierarchical model for football results [V via PyMC example]. https://www.pymc.io/projects/examples/en/latest/case_studies/rugby_analytics.html | *J. Appl. Stat.* 37(2) | Log-linear attack/defence/home random effects. | The standard hierarchical team model. It is used in the `gloria`/`turf` NHL repos. |

**Score and sequence effects** [V]
- Sources: https://hockeyviz.com/txt/scoreSeq, https://hockeyviz.com/static/pdf/cbjhac20.pdf, and https://thelivingfossils.substack.com/p/why-is-a-2-goal-lead-the-worst-lead
- Leading teams "sitting back" drives score effects. Leading-team xG falls 10–15%.
- The effect depends on period and on the sequence of goals, not just the current score differential.
- The "most recent goal" effect is about 5%.
- Magnus 3 (xG model) estimates trailing-team shot conversion odds at −7% [V] — https://hockeyviz.com/txt/fabricxg
- *Apply:* multiply each team's shot hazard by exp(β·f(score_diff, period, time)). Fit it on 2023-26 PBP with exposure time by state. Separate the shot-rate effect from the per-shot quality effect.
- **Confidence: high.**

**Period effects** [V][INT]
- Source: https://soundofhockey.com/2024/08/01/the-long-change-effect-nhl-scoring-trends-for-the-2023-24-season/
- 2023-24: P1 2,349 goals, P2 2,752, P3 2,349 excluding 446 EN goals.
- P2 is +17.2%, driven by the long change: +307 even-strength goals and +149 power-play goals.
- Our PBP reproduces this exactly: 2023-24 P1 = P3(non-EN) = 1.790 goals per game.
- *Apply:* use a period multiplier on the hazards of about 1.0 / 1.16 / 1.0 for P1/P2/P3 (non-EN). Fit it; do not hardcode.

**Overtime and shootout**
- Our data: see takeaway 6 [INT]. DailyFaceoff's 2025-26 trends article [V] (https://www.dailyfaceoff.com/news/5-major-nhl-trends-defined-2025-26-season-loser-point-overtime-save-percentage) gives OT conversion of 71.6% (2024-25) → 63.6% (2025-26) and 119 shootouts in 2025-26 versus 77 the year before.
- The 3v3 scoring rate is about 0.168 goals per minute versus about 0.091 at 4v4 (CBC via search, 2015) [S], and about 5.97 goals per 60 [S].
- The home team's 3v3 OT edge is 50–57% by season [INT].
- Shootouts: home-team rates of 42–59% by season [INT]. Research on the shootout home advantage is mixed: ScienceDirect 2016, "Examining the home advantage in the NHL: comparisons among regulation, overtime and the shootout" (https://www.sciencedirect.com/science/article/abs/pii/S1469029216301558) [S, abstract not read].
- *Apply:* simulate 5 minutes of 3v3 with its own hazard (team 3v3 skill shrunk hard toward league average), then a Bernoulli shootout with p ≈ 0.5 plus a small goalie/shooter adjustment.
- **Confidence: medium-high.**

**Home ice** [INT]
- Our data, 2022-23 → 2025-26: home win rate 52.2–56.3% including OT and SO.
- Mean regulation goals: home 3.07–3.12, away 2.79–2.94 (with EN).
- Home SOG exceeds away SOG by about 1.0–1.7 per game (note possible rink scorer bias; see Schuckers and arXiv:1412.1035 on RTSS rink effects [S]).
- Swartz & Arce (2014), *Int. J. Sports Sci. & Coaching* 9(4):681, doi:10.1260/1747-9541.9.4.681 [S].
- *Apply:* model home ice as a state-rate multiplier. Also model the home last-change effect on matchups (see 2.3(f)).

### 2.3 Player-level modeling

**(a) Shot generation and allocation (Dirichlet-multinomial)**
- **Internal check [INT]:** within a player-season (≥40 GP), per-game SOG var/mean has median **1.07**, and 1.06–1.10 across TOI bands. So *unconditional on game TOI*, SOG is only mildly overdispersed.
  - After conditioning on projected TOI and team shot volume, NB2 dispersion should be small, with an implied NB size r in the tens.
  - The M5 bake-off (Poisson / NB2 / generalized Poisson / hurdle) will likely be won by NB2 with a weak prior, or by plain Poisson plus latent TOI uncertainty.
- **Dirichlet-multinomial for teammate allocation** [S]
  - It is used in basketball shot-zone models: https://arxiv.org/pdf/2007.10550 (Modeling player and team performance in basketball).
  - It is also used for DFS opponent modeling (Haugh & Singal, "How to play fantasy sports strategically (and win)", http://www.columbia.edu/~mh2078/DFS_Revision_1_May2019.pdf) [V].
  - *Apply:*
    - Team SOG in each state goes to the on-ice players via p ~ Dirichlet(α·share_hat).
    - Here share_hat = (TOI_state × individual rate) / Σ over on-ice players.
    - The concentration α controls extra-multinomial variance. Fit α per state by maximum marginal likelihood on player-game SOG given team SOG.
  - This guarantees Σ player SOG = team SOG in every draw, which is the reconciliation requirement.
- **Stability of rates** [S] — Fowleball, https://fowleball.substack.com/p/32-charts-predicting-5v5-goals. Year-over-year variance explained (with age):

  | Metric | Variance explained |
  |---|---|
  | 5v5 unblocked-shot rate | 56% |
  | Shot rate | 52% |
  | xSh% (unblocked) | 29% |
  | TOI | 27% |
  | Sh% | 6.4% |

  - *Apply:* shot *rates* deserve light shrinkage. Finishing deserves heavy shrinkage.
  - Our INT year-over-year r for xG per unblocked attempt is 0.54–0.60, so shot *quality* (location/role) is fairly repeatable.

**(b) xG models**
- **MoneyPuck** [V] — https://moneypuck.com/about.htm
  - Gradient boosting trained on about 800k shots from 2007-08 to 2014-15.
  - Features: distance, angle, shot type, time and "speed" since the previous event, and rebound features.
  - Adds a Bayesian **shooting-talent adjustment** and a **flurry adjustment**.
  - Their pre-game model weights: 17% "ability to win", 54% scoring chances, 29% goaltending. 2024-25 favourite hit rate 60.4%, log loss 0.658.
- **Evolving-Hockey** [V] — https://evolving-hockey.com/blog/a-new-expected-goals-model-for-predicting-goals-in-the-nhl/ · code: https://github.com/evolvingwild/hockey-all/tree/master/xG
  - XGBoost with **four separate models** by strength: EV, PP, SH and EN.
  - EV AUC 0.782 in cross-validation and 0.775 out of sample (2017-18). PP AUC about 0.70–0.72.
  - The shooter-talent variable was never used by the trees.
- **HockeyViz Magnus 3** [V] — https://hockeyviz.com/txt/fabricxg
  - Generalized ridge logistic regression with shooter and goalie indicators, hex-grid location "fabrics" by shot type, and rush/rebound, strength and score terms.
  - Prior-year estimates serve as the ridge centre (a dynamic prior).
  - PP vs 3 defenders: +104% odds. Rush/rebound: about +100%.
  - Goalie effects range from about −12% (best, Hellebuyck) to +14% on shot conversion odds.
- **Noel (2025)**, arXiv:2511.07703, "Expected by Whom? A Skill-Adjusted xG Model" [V abstract] — https://arxiv.org/abs/2511.07703
  - LightGBM with shooter and goalie skill features (overall, locational, situational). Up to 5% improvement in log loss, Brier and AUC.
- **PyMC Labs HSGP goalie model** [V] — https://www.pymc-labs.com/blog-posts/bayesian-spatial-modeling-for-evaluating-hockey-goaltending-performance
  - Spatial Gaussian process with hierarchical shooter effects. 2023-24 GSAx for top and bottom goalies ranges about ±10–15. Most goalies' intervals include 0.
- **Apply**
  - **Do not build our own xG first.** MoneyPuck `xGoal` is already in `mp_shots_*`.
  - The per-shot goal probability for the sim is xG × shooter multiplier × goalie multiplier, each shrunk per 2.3(c) and 2.3(d).
  - Keep separate EV / PP / SH / EN treatment, following Evolving-Hockey.
  - Note: MoneyPuck xG is for *unblocked* attempts. Conditioning on shots on goal inflates G/xG (we measured about 1.35 for forwards on SOG only). Keep units consistent: either simulate unblocked attempts and then on-goal / missed, or re-calibrate xG to an on-goal basis.
  - **Confidence: high.**

**(c) Finishing talent: regression amounts**
- **External**
  - Fowleball: regress single-season sh% about 75% [S].
  - JFresh: only about 4 of 37 players who shot 15%+ repeated the next season [S] — https://jfresh.substack.com/p/percentage-luck-in-hockey-explained
  - Hockey-Graphs empirical Bayes for scoring rates (Weibull prior for forwards, Gamma for D; parameters not published in the text) [V] — https://hockey-graphs.com/2018/06/21/comparing-scoring-talent-with-empirical-bayes/
  - A JuniorPuck page claims sh% is "half signal" after 30–70 SOG [U]. **This conflicts** with the other evidence and with our INT estimate, because it confounds shot quality with finishing. Do not use it.
- **Internal [INT]:** raw sh% (on SOG), method of moments, 2022-23 → 2025-26 regular season:

  | Group | SD of true sh% | Regression constant K |
  |---|---|---|
  | Forwards | ≈ 2.3 pp (mean 12.6–12.9%) | ≈ 205–225 SOG |
  | Defensemen | ≈ 1.1–1.3 pp (mean 5.7–6.2%) | ≈ 350–440 SOG |

  - Raw sh% *includes* shot quality and role, which is why it looks more "stable" (pooled F+D year-over-year r = 0.63; forward-only year-over-year r ≈ 0.36).
  - Finishing *above xG* is what we must shrink. For forwards, K ≈ 64 xG (≈ 775 unblocked attempts). For D, shrink fully.
- **Apply:** multiplier = (G + K·1) / (xG + K), with K = 64 xG for forwards and K = ∞ for D. Use a recency-weighted G and xG, with a half-life to be tuned (start with 2 seasons).
- **Confidence: medium.** It needs a proper beta-binomial or gamma-Poisson hierarchical fit with aging.

**(d) Goalies: GSAx stability**
- **Schuckers (2016)**, "Statistical Evaluation of Ice Hockey Goaltending" (book chapter draft) [V] — http://myslu.stlawu.edu/~msch/sports/StatEvalofGoalies2016Schuckers.pdf
  - Even/odd-shot within-season sv% correlations: 0.15–0.28 (500+ shots), averaging about 0.21.
  - Year-to-year sv% correlations: −0.04 to 0.19, excluding the 8-goalie lockout outlier.
  - With 1,500 shots at .925, the binomial SE ≈ .007, so the 95% interval is .909–.939.
  - Cites Desjardins: it takes about 3 years of data to evaluate a goalie.
- **Puck Over the Glass** (2018-19 → 2025-26, top 64 goalies): GSAx year-over-year r ≈ 0.22 [S] — https://puckovertheglass.substack.com/p/goaltending-is-not-voodoo
- **Tape-to-Tape / Expected Buffalo** [S]: GSAx/60 swings about 0.36 per 60 year over year, which is about 13–14 goals per season.
- **Internal [INT]:** SD of true GSAx per SOG ≈ 0.0065, K ≈ 2,100 SOG, year-over-year r = 0.22.
- **Apply:** goalie multiplier on per-shot goal probability = 1 − shrunk GSAx per shot / league goal rate per shot, with K ≈ 2,000 SOG (recency-weighted). Backups and rookies default to about league average minus a small replacement-level penalty (to be estimated).
- **Confidence: medium-high.**

**(e) TOI projection and PP units**
- No peer-reviewed TOI-projection benchmark was found.
- HockeyViz uses a "fully algorithmic approach based on historical deployment" plus explicit line "groupings" [V] — https://hockeyviz.com/txt/preview2627
- Practitioner heuristics [S] — https://www.tonyspicks.com/2026/05/15/nhl-anytime-goal-scorer-props-reading-power-play-time-as-the-edge/ and https://propsbot.ai/shots-on-goal-props-today/. These are *low-credibility tout sites, used only for magnitudes*:
  - PP1 takes 60–70% of PP time.
  - PP1 generates 55–70 shots per 60 versus 25–30 at EV.
  - Moving from PP2 to PP1 adds 10–15% to AG probability.
  - Top-line vs third-line deployment is about a 1.5-SOG swing.
- *Apply:* the M4 plan (EWMA + hierarchical shrink on lagged shift-derived role) is right. Model TOI **by state** (EV/PP/PK) and treat it as *random* in the sim. TOI uncertainty is a major source of prop-distribution width and cross-player correlation, because game script and penalties move all PP players together.

**(f) Line matching / last change**
- No quantitative public source was verified in this pass [U].
- The home team's last change means home top lines face weaker opposition more often.
- *Apply:* estimate opponent-quality-faced from shifts (we have 3.16M shift rows) as a feature, not as a structural sim component, at least until v2.

**(g) Rest / back-to-back**
- **McKeen's** (2007-12, about 1,620 games): rested vs tired win% .596 vs .495; CF% 51.8 vs 48.2 [S] — https://www.mckeenshockey.com/nhl-blog/analytic-differentials-restedtired-b2b/
- **nhlscraper "back-to-back tax" vignette** (2005-06 onward): zero rest is worst, and the "biggest improvement comes from moving from zero days of rest to one" [V, no numbers extracted] — https://rdrr.io/cran/nhlscraper/f/inst/doc/back-to-back-tax.Rmd
- **NHL.com / Kraken "Examining Goalie Workload"** [V]
  - Attributes to Tulsky (2013) that a back-to-back "reduced their save percentage by just over 11 percent" [U: almost certainly a mis-statement].
  - Notes that later work by Andrew Thomas and Dom Luszczyszyn found smaller effects.
  - https://www.nhl.com/kraken/news/core-concepts-examining-goalie-workload-329507592
- **DataStreak** [S] — https://datastreak.com/insights/nhl-goalies-back-to-back
  - 1,409 back-to-back starts vs 9,889 rested: GAA 2.79 vs 2.77.
  - The absence of an effect is attributed to selection.
- *Apply:* include rest as a team-rate covariate with a weak prior. Use a goalie back-to-back flag mainly to predict *who starts*, not their sv%.
- **Confidence: low-medium.**

### 2.4 First goal scorer (FGS) and anytime goal (AG)

**Pricing mechanics**
- This is standard competing-risks math, derived rather than sourced. It is consistent with Buttrey et al. and Thomas et al.
- Let each player i have a time-varying goal hazard h_i(t) = (on-ice indicator × state rate × shooter multiplier × opposing goalie multiplier).
- Let H(t) = Σ_i h_i(t) over both teams, including opponents. Then

  P(i scores first) = ∫₀^T h_i(t) · exp(−∫₀^t H(s) ds) dt

  where T includes 3v3 OT, because OT goals count at FD/DK. Shootout goals do not count, and a game with no goal before the shootout has no first-goal winner (the house rule for that case is still to be verified). If the player does not play, the bet is void.
  - FanDuel house rules [V]: https://www.fanduel.com/fanduel-sportsbook-house-rules-on
  - DraftKings Pick6 rules [S]: https://pick6.draftkings.com/pick6-rules-and-scoring-nhl
- In practice the sim gives this directly: record who scores the first goal in each draw. The Rao-Blackwellized version replaces "who scored" with h_i(t*)/H(t*) at each simulated first-goal time t*.
- **First-period deployment matters.** FGS is mostly decided in P1, where scoring runs about 1.75 goals per game (the lowest period). The starting line and PP1 get the first shifts. So FGS share is *not* equal to season goal share. It tilts toward the starting line, PP1, and players with high P1 TOI share.
- Use shifts to estimate each player's P1 TOI share by state.
- **AG** = 1 − exp(−∫ h_i). Include the EN hazard (top forwards and PP D who are on for 6v5 / 5v6), and the team-level uncertainty (latent strength draws). The latter makes AG slightly *less* than the plug-in Poisson value, by Jensen's inequality on 1 − e^(−λ).

**Known market biases**
- Exotic markets such as FGS and correct score carry high margins, 20–40% [S].
- Favourite-longshot bias exists in exact-score odds, per Reade, Singleton & Vaughan Williams (2020), "Betting markets for English Premier League results and scorelines: evaluating a forecasting model", *Economic Issues* [V] (https://www.reading.ac.uk/web/files/economics/emdp202003.pdf). Their scoreline probabilities beat the bookmaker's, but a simple strategy did not make money.
- "Narrative bias" pricing of star scorers in AG markets [S, low-credibility].
- Early-season AG prices are the most dispersed, because books lean on last year's role [S] — RotoWire Lamp Lab, https://www.rotowire.com/hockey/article/nhl-anytime-goal-scorer-model-137385
- **Apply:**
  - De-vig one-sided AG and FGS boards with a longshot-aware method: power, Shin or odds-ratio. That is research doc G, not this one.
  - Expect value, if any, in mid-price regulars whose role changed (PP1 promotion, line change) before the book updates, and in fading low-probability "name" players.
  - **Do not bet FGS longshots on model edge alone.** The margin on longshots is enormous, and our FGS calibration will be the least certain part of the model.
  - **Confidence: medium.**

**Parlay pricing**
- Moshrefi (2026), arXiv:2607.14430, "Prices, Probabilities, and Parlays: Systematic Bias in Sports Prediction Markets" [V abstract], studied 23M Kalshi moneyline trades.
- Multi-leg parlays are systematically overpriced relative to their legs, and more so as legs are added.
- *Apply:* for the SGP builder, the default assumption is that the SGP is −EV unless our structural joint probability beats the book's price by a wide margin. Log SGP quotes prospectively; they cannot be backtested.

### 2.5 Empirical facts from our own data (for calibration targets) [INT]

These come from regular season only, with seasons labelled by their start year (for example 2023 = 2023-24), using `nhl_pbp` and `nhl_games`. Script logic is in §6. Every simulator build should reproduce these within sampling error.

**Scoring by period and team-goal dispersion**

| Season | Reg goals/g | EN goals/g | P1 | P2 | P3 | P3 no-EN | Home reg goals | Away reg goals | var/mean H, A | corr(H, A) | corr(H, A), no EN | Reg tie % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2023-24 | 6.02 | 0.34 | 1.79 | 2.10 | 2.13 | 1.79 | 3.12 | 2.90 | 1.00 / 1.06 | −0.12 | −0.01 | 20.7 |
| 2024-25 | 5.87 | 0.40 | 1.73 | 2.00 | 2.14 | 1.74 | 3.09 | 2.79 | 1.01 / 1.04 | −0.09 | +0.05 | 20.7 |
| 2025-26 | 6.01 | 0.39 | 1.76 | 2.09 | 2.16 | 1.77 | 3.07 | 2.94 | 1.01 / 0.96 | −0.08 | +0.08 | 24.8 |

**Game outcomes**

| Season | Home win % | To OT % | SO % | OT decided in 3v3 | Home 3v3 win | Home SO win | Home SOG | Away SOG |
|---|---|---|---|---|---|---|---|---|
| 2022-23 | 52.4 | 23.0 | 7.2 | 68.5% | 56.5% | 42% | 32.1 | 30.4 |
| 2023-24 | 54.1 | 20.7 | 6.3 | 69.9% | 53.7% | 59% | 31.0 | 29.6 |
| 2024-25 | 56.3 | 20.7 | 5.9 | 71.6% | 54.1% | 53% | 28.8 | 27.8 |
| 2025-26 | 52.2 | 24.8 | 9.1 | 63.5% | 50.2% | 47% | 28.4 | 27.3 |

**Talent-spread estimates** (method of moments)

| Quantity | Estimate |
|---|---|
| Forward G/xG multiplier, true SD | 0.125 |
| Forward regression constant | K ≈ 64 xG (≈ 775 unblocked attempts) |
| Forward G/xG year-over-year r | 0.34 |
| D G/xG year-over-year r | −0.03 (no signal) |
| Goalie GSAx per SOG, true SD | 0.0065 |
| Goalie regression constant | K ≈ 2,100 SOG |
| Goalie GSAx year-over-year r | 0.22 |

**Other targets**
- Player SOG within player-season: var/mean median 1.07.

---

## 3. Recommended parameters and defaults

### 3.1 Simulation engine

| Parameter | Default | Rationale / source |
|---|---|---|
| Time resolution | Event-driven, piecewise-constant hazards; states = (score diff, period, clock, strength, goalie-pulled flags) | Equivalent to Magnus per-second [V], with far fewer RNG calls; Thomas et al. semi-Markov [V] |
| N sims, main markets | **65,536 (2^16)** | SE ≤ 0.2 pp at p = 0.5; power of 2 for Sobol on the latent layer (SciPy [V]) |
| N sims, SGP / alt tails (p < 0.03) | **131,072 (2^17)**, or importance-sample the tail | Relative SE ≤ 5% at p = 0.02 |
| Player single props | **Rao-Blackwellized closed form** given the simulated team path | Owen ch. 8 [S]; biggest variance cut |
| RNG | PCG64 via `SeedSequence.spawn`, keyed by (game_id, model_version) | NumPy [V]; reproducible, CRN-ready |
| Latent layer | Scrambled Sobol → inverse-CDF for team-strength posterior, pace and goalie draws | SciPy QMC [V] |
| Scenario deltas (goalie in/out, lineup) | CRN: identical seeds across scenarios | Owen [S] |
| MC-error reporting | Every price logs p̂ and its MC SE; a bet requires edge > 3×SE_MC + model-uncertainty margin | Formula |

### 3.2 Game model

| Parameter | Default / prior | Source |
|---|---|---|
| Team state rates | log λ = μ_state + att_team − def_opp + home + score_effect(sd, period, t) + period_mult + rest | Buttrey et al. [V]; McCurdy [V] |
| Team-strength fitting | Hierarchical (Baio–Blangiardo) with **time decay** exp(−ξ·days); start with a ξ half-life of about 60–90 days, then tune | Dixon & Coles [V]; the half-life value is my suggestion, not sourced |
| Pace factor | Gamma(shape k, mean 1) shared by both teams. **Fit k so that the simulated team-goal var/mean ≈ 1.00 including EN.** Expect k ≥ 50 (SD ≤ 0.14), because non-EN goals are already underdispersed | [INT] |
| Period multipliers (non-EN) | Fit; expect about 1.00 / 1.16 / 1.00 | Sound of Hockey [V]; [INT] |
| Score effects | Leading team shot hazard × about 0.85–0.90 in P3; trailing about 1.0; the leading team's per-shot quality slightly up | HockeyViz [V] |
| Penalty rates | Team drawn/taken rates plus a referee-crew effect, shrunk | Magnus [V]; topic E (other doc) |
| 6v5 GF rate | Prior about 6.5/60 | Hall 2020 [V] |
| EN GA rate | Prior about 12/60 (refit) | Hall 2020 [V]; search snippet said 19 [U] |
| Pull-time hazard | Empirical, by deficit (1/2/3), score, time and team/coach; refit on 2023-26 PBP each season | Hall [V]; Pidutti [V] |
| 3v3 OT | Its own rate, fitted from recent seasons; league mean ≈ 0.17 goals/min [S]; team 3v3 effects shrunk ≥ 80% | CBC [S]; [INT] |
| Shootout | p_home = 0.50 ± small goalie/shooter adjustment | Magnus uses 50/50 [V]; [INT] |
| Calibration targets | §2.5 table (tie rate, EN/g, corr, var/mean, OT/SO split) | [INT] |

### 3.3 Player model

| Parameter | Default | Source |
|---|---|---|
| SOG family | NB2 with dispersion prior centred on a small overdispersion (size r ~ 20–50 given TOI); compare against Poisson + latent TOI | [INT] var/mean 1.07 |
| Teammate allocation | Dirichlet-multinomial within state; α fitted by marginal likelihood; initial α ≈ 50–200 (to be fitted) | DM literature [S]; α is my guess |
| Shot quality (xG per attempt) | Player mean xG per attempt, shrunk with K ≈ 50–100 attempts (year-over-year r 0.54–0.60) | [INT]; Fowleball [S]. K is a rough suggestion |
| Forward finishing multiplier | (G + K)/(xG + K) with **K = 64 xG** (≈ 775 attempts), recency-weighted | [INT] |
| D finishing multiplier | **1.0** (full shrink) | [INT] |
| Goalie GSAx | Shrink with **K ≈ 2,000 SOG**; backup default about league average minus 0.002–0.004 sv% (to be fitted) | [INT]; Schuckers [V] |
| TOI | Distribution by state (EV/PP/PK); EWMA of recent games, shrunk to role; PP1 share 60–70% of PP time as a prior | M4 plan; tout sources for magnitudes [S] |
| Assists | Per goal: P(assisted) by state from PBP; A1/A2 allocated to on-ice teammates by historical share | Handoff §8 |
| Rest | Team rate covariate, prior centred on a small effect; goalie back-to-back used for starter probability | McKeen's [S]; DataStreak [S] |

---

## 4. Libraries and open-source code

| Library | Language | Good for | Notes |
|---|---|---|---|
| **nhl-api-py** (coreyjs) — https://github.com/coreyjs/nhl-api-py [V] | Python | Current NHL API (api-web): schedule, boxscore, PBP, shifts, stats, Edge tracking | Apache-2.0; actively updated for 2026-27. Good for live ingestion. |
| **Hockey-Scraper** (Harry Shomer) — https://github.com/HarryShomer/Hockey-Scraper [V] | Python | Historical PBP and shifts, 2007-08 onward | **Unmaintained**, GPL-3.0; the old statsapi is dead. Reference only. |
| **nhlscraper** (CRAN) — https://rdrr.io/cran/nhlscraper/ [V] | R | Scraping plus vignettes (back-to-back tax) | Use for analysis ideas. |
| **penaltyblog** — https://github.com/martineastwood/penaltyblog [V] | Python | Poisson, bivariate Poisson, Dixon-Coles, NB and Bayesian hierarchical goal models; implied-odds/de-vig helpers; Elo/Massey/Colley/Pi ratings | MIT. Soccer-oriented but sport-agnostic. A fast baseline comparator for team models, and a check against our devig code. |
| **statsmodels** discrete models — https://www.statsmodels.org/stable/discretemod.html [V] | Python | Poisson, NegativeBinomial (NB1/NB2), NegativeBinomialP, GeneralizedPoisson, ZI-*, HurdleCountModel, truncated | The right tool for the M5 SOG family bake-off, with offsets = log TOI. |
| **PyMC** (rugby hierarchical example) — https://www.pymc.io/projects/examples/en/latest/case_studies/rugby_analytics.html [V] | Python | Hierarchical team and player shrinkage; posterior predictive sims | Use the posterior draws as the sim's latent layer (propagates parameter uncertainty). |
| **NumPyro / JAX** | Python | Same models, much faster (GPU/CPU vectorized); `vmap` sims | Not researched in depth here. |
| **Stan / cmdstanpy** | Python/R | Gold-standard HMC for hierarchical count models | Not researched in depth here. |
| **gloria / turf** (dflemin3) — https://github.com/dflemin3/gloria, https://github.com/dflemin3/turf [S] | Python | Worked NHL Baio–Blangiardo hierarchical Poisson plus season simulation | Borrow structure, not code quality (unreviewed). |
| **LightGBM / XGBoost / CatBoost** | Python | xG-style per-shot models; TOI regression; stacking residual on logit(market) | Evolving-Hockey uses XGBoost [V]; Noel uses LightGBM [V]; MoneyPuck uses GBM [V]. |
| **scikit-learn** | Python | Calibration (isotonic/Platt), CV splitters, logistic stack for H3/H4 | Standard. |
| **SciPy `stats.qmc`** [V] | Python | Sobol/Halton/LHS, scrambled RQMC | Latent-layer variance reduction. |
| **NumPy `random`** [V] | Python | PCG64/Philox, SeedSequence.spawn | Reproducible parallel streams, CRN. |
| **sportypy** — https://github.com/sportsdataverse/sportypy [V] | Python | Rink plotting only (GPL-3.0) | Diagnostics and visualization; not modeling. |
| **Evolving-Hockey hockey-all/xG** [V] | R | Reference xG training code | Only needed if we ever replace MoneyPuck xG. |
| **MoneyPuck data** (already ingested) [V] | CSV | Shots with `xGoal`, flurry/rebound fields; team and goalie seasons | Primary xG source. |

---

## 5. Open questions

1. **Pull-time model.** What hazard form for goalie pulls (by deficit, time, score, coach) best fits 2023-26 PBP? How much does coach identity matter? This needs a PBP study, and it is the biggest single lever for puck line and totals.
2. **EN rate.** Is the EN goals-against rate about 12/60 (Hall) or about 19/60 (search snippet)? Refit from our PBP (`situationCode` first/last digit = goalie in net).
3. **Pace factor.** Is any shared pace factor needed at all, once team strengths carry posterior uncertainty? Test: with pace variance at 0, do simulated totals reproduce the empirical var/mean and alt-total hit rates?
4. **SOG units.** MoneyPuck xG is per unblocked attempt. Should the sim generate attempts → on-goal / miss / block (three-way), or SOG directly with an on-goal-calibrated xG? The former is needed for blocked-shot props and gives correct SOG–goal coupling.
5. **Dirichlet concentration α.** How big is α by state (EV vs PP)? Is extra-multinomial variance mostly TOI variance? If so, model TOI randomness explicitly and use a plain multinomial.
6. **FGS settlement rules.** What exactly happens at DK/FD (and other books) when a game is 0–0 into a shootout, or when a player enters after the first goal? Verify the house-rule text for each book.
7. **Shootout skill.** Is any skater or goalie shootout skill detectable at our sample sizes? The prior is essentially none.
8. **Rest effects.** Refit rest and travel effects on 2022-26 data with market control: do they add anything beyond the closing line? (H3/H4 residual test.)
9. **Line matching.** Is last change measurable in player shot rates (home top line vs road top line), and is it big enough to include?
10. **Finishing-talent aging.** Our K ≈ 64 xG ignores aging and role changes. Does a hierarchical model with age curves beat it out of sample on AG log loss?
11. **Market biases.** Is favourite-longshot bias present in NHL AG and FGS boards specifically at DK/FD? It is testable on 2026-01 → 2026-06 per-book closes (the AG board is one-sided, so devig choice matters).
12. **Unverified items to chase.**
    - The Tulsky (2013) back-to-back figure (original Broad Street Hockey post).
    - The JuniorPuck "30–70 SOG" claim (likely wrong).
    - The NHL totals "under bias" paper, 54.2% unders at 5.5+ (academia.edu, https://www.academia.edu/65674388/Market_Efficiency_and_the_NHL_totals_betting_market_Is_there_an_under_bias; not read).

---

## 6. Reproducibility of the [INT] numbers

The numbers were computed ad hoc in the research session with DuckDB over:
- `data/curated/nhl_pbp/**` (regular-season games: game_id digits 5–6 = "02"). EN goals are goals where the conceding team's goalie digit in `situationCode` = 0. `situationCode` = [away goalie][away skaters][home skaters][home goalie].
- `data/curated/nhl_games.parquet`, using `last_period` ∈ {REG, OT, SO}.
- `data/curated/nhl_skater_game.parquet`.
- `data/curated/mp_shots_2022–2026.parquet`, using regular season, non-EN, and xGoal on unblocked attempts.

Talent spreads use the method of moments: true variance = observed variance − mean sampling variance, and K = sampling variance per unit / true variance.

The scripts were not committed; they are throwaway. Re-implement them in `src/` if the numbers are adopted.
