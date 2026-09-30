# 03 — Advanced Stats & Matchup Factors for NHL Player Props

*Research digest, 2026-09-30. Scope: which advanced stats and matchup factors predict next-game player outcomes (SOG, goals, assists, points, saves) and team outcomes, and exactly how to build them from our tables (`docs/DATA.md`).*

**How to read this doc**
- **[LIT]** = number from a published source (citation + URL given). **[OURS]** = computed by us on our curated data during this research (scripts were ad hoc in the session scratchpad; SQL/pandas recipes are reproduced below so they can be productionized). **[UNVERIFIED]** = claim seen in a source we could not confirm or that looks garbled; do not rely on it.
- "k" = **stabilization constant**: the sample size at which observed rate is 50% signal / 50% noise (split-half r = 0.5). Use it directly as a shrinkage prior: `est = (obs*n + prior_mean*k)/(n + k)`.
- Confidence: **H** (multiple sources agree and/or our data confirms with large n), **M**, **L**.

---

## 0. Key takeaways — ranked by predictive value for props

1. **Player's own volume/deployment dominates everything.** TOI/game (split-half r = 0.99, k ≈ 0.5 games) and shot attempts/60 (r = 0.90, k ≈ 4 games) are near-pure skill/role. SOG/game (r = 0.91–0.92, k ≈ 3.5–5 games) is more reliable than SOG/60 (k ≈ 8–9 games), because TOI differences are real signal. A good SOG prop model is a good *TOI × shot-rate* model. [OURS, H]
2. **Project TOI and PP TOI with a short EWMA (half-life ≈ 5 games), not season averages.** Next-game TOI: EWMA-h5 r = 0.84 (MAE 110 s) vs last game 0.77 and season-to-date 0.82. PP **share** of team PP time is very predictable (r = 0.87). Absolute PP seconds are much less so (r = 0.70), because the number of PP opportunities is noisy. So model `PP_TOI = PP_share (EWMA) × expected team PP time (team draw rate × opp take rate)`. [OURS, H]
3. **Shooting % is mostly noise at player level: regress hard.** Split-half r ≈ 0.26 (F) / 0.20 (D) on about 60–70 shots per half, so k ≈ 200–240 shots within season. Year-over-year r = 0.34 (F) and 0.22 (D) at 500+ min. Literature uses +375 shots (F) and +275 (D) of league-average shooting [LIT]. **Goals model = shots (or ixG) × heavily shrunk finishing.** ixG/60 is far more reliable (k ≈ 12–16 games) than goals/60 (k ≈ 35–45 games). [OURS+LIT, H]
4. **Primary assists are more repeatable than secondary assists, but both are noisy.** Split-half primary A/60 k ≈ 30–35 games vs secondary k ≈ 46–49 games. YoY: A1/60 r = 0.62 (F) and 0.59 (D); A2/60 r = 0.49 and 0.51. Points/60 (k ≈ 15 games) stabilizes faster than either because it pools events. For assists, use on-ice xGF/teammate quality and PP share rather than past assist counts. [OURS+LIT, H]
5. **Opponent shot suppression matters, but shrink it ~25%.** Poisson GLM on 154k player-games: elasticity of player SOG to opponent season-to-date SA/game = **0.75** (SE 0.03). For goals and points, elasticity to opponent GA/game ≈ **0.56–0.58**. Use `mult = (opp_rate/league)^0.75` for SOG and `^0.55–0.6` for goals/points, or better, fit it in the model. [OURS, H]
6. **Home/away and rest are small but real multiplicative effects.** Home: +3.7% SOG, +7% goals and points. Own back-to-back: −3% SOG, −6.5% goals and points. Opponent on a B2B: +2.6% SOG, +4% goals and points. B2B team vs a rested opponent wins 40.7% (n = 702) vs 50% baseline. Rotowire's 11-season study: B2B *plus* a time-zone change = 46.8% vs 49.5% [LIT]. [OURS+LIT, H]
7. **Goalie quality moves team goal totals by ~3% per SD of *shrunk* GSAx.** Save% is a weak skill signal: split-half r = 0.25 at ~730 shots per half, so k ≈ 2,200 shots [OURS]. The Tango/Birnbaum regression constant is ~3,000 shots [LIT]. GSAx YoY r is only 0.12–0.16 [OURS]. For saves props, **shots against (opponent volume) is the main driver**, and the goalie's own sv% adds little unless the sample is very large. [OURS+LIT, H]
8. **Starter identity is the biggest goalie factor, and B2B is the key signal.** On the 2nd night of a B2B, the night-1 starter starts again only **7.8%** of the time (n = 1,597) vs 48.5% overall same-as-previous [OURS]. Sportlogiq's model (season start share + B2B + recent starts) gets 70% accuracy vs a 59.6% baseline [LIT]. We found no measurable fatigue sv% drop on same-goalie B2Bs (n = 125, small). [OURS+LIT, H for selection, L for fatigue]
9. **Rink/scorer bias: material for hits (and blocks, giveaways, takeaways), negligible for SOG.** Our 2022–26 rink factors (home-game totals / home team's road-game totals): hits SD 0.14 (TOR 1.24, TBL 1.19, EDM 1.14 … SJS 0.86, NJD 0.87, CBJ 0.87). Hits factors persist partly YoY (r 0.52/0.29/−0.15). Blocks SD 0.06 (YoY r 0.26–0.58). SOG SD 0.04, YoY r 0.12–0.27, so mostly noise; don't adjust SOG. [OURS, M-H; LIT agrees: Schuckers & Macdonald 2014]
10. **Early season: weight last season heavily; the prior is "worth" ~20 games for SOG, ~33 for points, ~40 for goals, ~5 for TOI.** Optimal weight on current season-to-date for predicting the rest of the season: SOG 0.19 at 5 GP, 0.32 at 10 GP, 0.51 at 20 GP, 0.70 at 40 GP. Goals: 0.09, 0.17, 0.34, 0.49. TOI: 0.58 at 5 GP, 0.79 at 20 GP. [OURS, H]
11. **Low value / skip for props:** zone starts (season-level effect small, [LIT]), altitude (COL home edge in 2022–26 is *not* larger than league-normal, [OURS]), NHL EDGE speed/burst (correlates with shot *volume* at team level only, [LIT]; not in our pipeline), referee effects (can't test: **our `nhl_officials` table is all NULL**, see §7).

---

## 1. Stat stability / repeatability

### 1.1 Our own numbers (computed on our data)

**Within-season split-half** (odd vs even games, regular season, player-seasons with ≥ 60 GP; ~37.6 games per half). SOG, G, A, TOI, hits and blocks come from `nhl_skater_game` (2022-23 → 2025-26). Shot attempts and A1/A2 come from `nhl_pbp` (2023-24 → 2025-26). ixG comes from `mp_shots_*`. `k` is the games (or shots) at which r = 0.5.

| Metric | F r(half) | F k | D r(half) | D k | Notes |
|---|---|---|---|---|---|
| TOI/game | 0.988 | 0.5 g | 0.984 | 0.6 g | Role is extremely stable; changes come from line/injury events |
| SOG/game | 0.918 | 3.4 g | 0.884 | 4.9 g | Better than SOG/60 because TOI is signal |
| SOG/60 | 0.832 | 7.6 g | 0.806 | 9.0 g | |
| Shot attempts (iCF)/60 | 0.899 | 4.2 g | 0.898 | 4.2 g | pbp seasons only |
| ixG/60 (MoneyPuck xG) | 0.725 | 14.3 g | 0.744 | 12.9 g | |
| Goals/60 | 0.528 | 33.8 g | 0.448 | 45.9 g | |
| Shooting % (G/SOG) | 0.258 | **~209 shots** | 0.185 | **~238 shots** | k in shots |
| Assists/60 | 0.645 | 20.8 g | 0.643 | 20.7 g | |
| Primary A/60 | 0.559 | 29.8 g | 0.518 | 34.8 g | pbp seasons |
| Secondary A/60 | 0.434 | 49.4 g | 0.449 | 45.8 g | pbp seasons |
| Points/60 | 0.715 | 15.0 g | 0.708 | 15.4 g | |
| Hits/60 | 0.966 | 1.3 g | 0.944 | 2.2 g | Includes rink bias (both halves mix rinks) |
| Blocks/60 | 0.742 | 13.2 g | 0.770 | 11.2 g | |

Caveat: the ≥ 60 GP restriction limits the talent range, which understates reliability for the full population. Treat k as conservative for regulars.

**Year-over-year** (MoneyPuck `mp_skaters_seasons`, regular season, both seasons ≥ 500 min all-situations, 2015→2025; n ≈ 3,120 F pairs, 1,743 D pairs):

| Metric | F r | D r |
|---|---|---|
| TOI/GP | 0.84 | 0.81 |
| PP TOI/GP (5on4) | 0.87 | 0.89 |
| PP share of team 5on4 time | 0.83 | 0.86 |
| Shot attempts/60 | 0.86 | 0.82 |
| SOG/60 | 0.83 | 0.80 |
| ixG/60 | 0.73 | 0.76 |
| Goals/60 | 0.59 | 0.50 |
| Sh% | 0.34 | 0.22 |
| (G − xG)/unblocked attempt (finishing) | 0.27 | 0.06 |
| Primary A/60 | 0.62 | 0.59 |
| Secondary A/60 | 0.49 | 0.51 |
| Points/60 | 0.74 | 0.72 |
| Hits/60 | 0.91 | 0.89 |
| Blocks/60 | 0.76 | 0.73 |
| 5v5 on-ice xGF/60 | 0.56 | 0.44 |
| 5v5 on-ice xGA/60 | 0.38 | 0.39 |
| 5v5 OZ-start share | 0.67 | 0.52 |

Team changers (all positions pooled): TOI/GP YoY r drops from 0.89 (same team) to 0.82 (moved). PP share goes 0.86 → 0.79 and points/60 0.84 → 0.75. SOG/60 (0.89 → 0.86) and ixG/60 (0.92 → 0.89) barely move. **Shot generation travels with the player; points and deployment depend on the team.** [OURS, H]

**Goalies**, YoY (MoneyPuck `mp_goalies_seasons`):

| Filter | pairs | sv% r | GSAx/shot r | HD sv% r |
|---|---|---|---|---|
| all sits, ≥ 500 SOG both yrs | 493 | 0.30 | 0.12 | 0.36 |
| all sits, ≥ 1000 SOG both yrs | 229 | 0.33 | 0.16 | 0.43 |
| 5v5, ≥ 1000 SOG both yrs | 120 | 0.32 | 0.13 | 0.49 |

Raw sv% repeats better than GSAx here, which suggests part of sv% persistence is team shot quality/system. HD sv% results are small-sample and may reflect MoneyPuck danger-tier definitions, so treat them as L confidence.

Within-season goalie split-half (alternating starts, ≥ 40 starts, n = 112 goalie-seasons, ~730 shots per half): **r = 0.25, so k ≈ 2,200 shots.** [OURS, M]

### 1.2 Literature

| Finding | Source | Confidence |
|---|---|---|
| Shooting talent regression: add **375 shots (F) / 275 shots (D)** of league-average Sh% (KR-21). ixG/60 beats iCF and Sh% for predicting future scoring from a 10-game window onward | Hockey-Graphs, "Expected Goals are a better predictor of future scoring than Corsi, Goals" (2015) https://hockey-graphs.com/2015/10/01/expected-goals-are-a-better-predictor-of-future-scoring-than-corsi-goals/ | H |
| Goalie sv% regression constant ≈ **3,000 shots** (league 0.920, observed-SD z = 1.38, r = 0.47 at 2,665 shots) | Tango, *The Book* blog, "How to figure out how much talent there is: NHL goalies" https://insidethebook.com/ee/index.php/site/comments/how_to_figure_out_how_much_talent_there_is_example_with_nhl_goalies | H |
| Split-half (even/odd shots) sv% correlation for goalies with > 500 shots: 0.20, 0.28, 0.18, 0.15 across 2009-13. Shot-type-adjusted sv% (DIGR) is higher in some seasons (0.29–0.66) | Schuckers, "Statistical Evaluation of Ice Hockey Goaltending" (2016) http://myslu.stlawu.edu/~msch/sports/StatEvalofGoalies2016Schuckers.pdf | H |
| Split-half (away games, 5v5, > 1000 SA) reliability: sv% ≈ 0.17, adjusted sv% 0.21, expected sv% −0.14 (goalie level). Team: sv% 0.33. Team shots-for/60 0.51, Fenwick 0.59, Corsi 0.57, GF/60 0.25; GA/60 only 0.04 vs CA/60 0.68 | Macdonald, Lennon, Sturdivant, "Evaluating NHL Goalies, Skaters, and Teams Using Weighted Shots" (arXiv 1205.1746) https://arxiv.org/pdf/1205.1746 | H |
| Primary assists far more predictable when proxied by shot assists: "basic shot assists … more than twice as better, expected primary assists three times, danger-zone shot assists four times" (we lack passing data) | Hockey-Graphs, "Expected Primary Points…" (2017) https://hockey-graphs.com/2017/01/19/expected-primary-points-are-a-better-predictor-of-future-scoring-than-shots-points/ | M |
| Secondary assists "only a small step above random" YoY, but the secondary-assist *ratio* is fairly stable | Dobber Frozen Tools (2020) https://dobberhockey.com/2020/02/28/frozen-tools-secondary-assist-rates/ (search-result summary; not fetched) | M |
| At team level, xG beats Corsi and GF% for predicting future goals after ~20 games. Scoring chances peak ~game 40. Actual goals beat Corsi for offense after ~25 games | Hockey-Graphs 2015 (above). Puck Over the Glass, "Which is better at predicting future goals" https://puckovertheglass.substack.com/p/which-is-better-at-predicting-future | H |
| EH's xG model rejected a player "shooting talent" variable (never used in any tree) → finishing is small relative to shot location/type | Evolving-Hockey, "A New Expected Goals Model" https://evolving-hockey.com/blog/a-new-expected-goals-model-for-predicting-goals-in-the-nhl/ | M |
| Skill-adjusted xG (shooter + goalie skill features) improves log loss/Brier/AUC by at most ~5% | "Expected by Whom?" arXiv 2511.07703 https://arxiv.org/abs/2511.07703 | M |
| Goals−xG is a high-variance, biased measure of finishing. Standard xG under-rates elite finishers (soccer, Messi GAX −17%). Implication: shrink but keep a small finishing term for proven elite shooters | Davis & Robberechts, arXiv 2401.09940 https://arxiv.org/abs/2401.09940 | M |
| GSAx/60 average season-to-season delta 0.361 (~13–14 goals); team xGA/60 delta 0.269 | Tape to Tape, "Why Save Percentage Isn't Enough: A Guide to GSAx" https://tapetotapemk.substack.com/p/why-save-percentage-isnt-enough-a (search summary only) | L |
| Zone starts: effect mostly within 10–20 s of the faceoff. At season scale only ~5% of players' CF% moves > 1 pt when adjusted | Jeremy Davis, Canucks Army, "Beware of what zone starts are telling you, Part II" https://canucksarmy.com/news/beware-of-what-zone-starts-are-telling-you-part-ii-shot-metrics | H |

### 1.3 How to compute (our tables)

- **SOG, G, A, P, hits, blocks, TOI per game:** `nhl_skater_game` (`toi_sec`, `sog`, `goals`, `assists`, `points`, `hits`, `blockedShots`).
- **Shot attempts (iCF):** `nhl_pbp_*` where `typeDescKey in ('shot-on-goal','missed-shot','blocked-shot','goal')`. Shooter is `coalesce(shootingPlayerId, scoringPlayerId)`: `goal` rows use `scoringPlayerId`, and `blocked-shot.shootingPlayerId` is the shooter, not the blocker.
- **Primary/secondary assists:** `nhl_pbp` `typeDescKey='goal'` → `assist1PlayerId`, `assist2PlayerId`.
- **ixG:** `mp_shots_<yr>` summed `xGoal` by `shooterPlayerId`. **Join key: `mp_shots.season*1000000 + mp_shots.game_id` = NHL `game_id`** (mp game_id is short, e.g. 20001, and `season` is the start year).
- **Goalie GSAx:** `mp_shots` grouped by `goalieIdForShot`, `sum(xGoal) - sum(goal)`, excluding `shotOnEmptyNet=1`. Denominator: unblocked attempts (Fenwick) or SOG (`shotWasOnGoal`).
- **MoneyPuck team codes** use `T.B`, `N.J`, `L.A`, `S.J`. Map them to `TBL`, `NJD`, `LAK`, `SJS` when joining `mp_team_games` to NHL tables. `mp_team_games.gameId` is already the full NHL id.
- **Never use `mp_*_seasons` as in-season features** (end-of-season leakage, per DATA.md). Use them only as prior-season priors (season s−1 and earlier).

---

## 2. Matchup effects

### 2.1 Opponent shot suppression / xGA / GA — [OURS, H]

Poisson GLM with player-game SOG as the outcome (2022-23 → 2025-26 regular season, n = 154,522). Inputs: player's own prior EWMA (half-life 10 games, ≥ 10 GP), opponent season-to-date SA/game ÷ league average, home, own B2B, opponent B2B.

| Term | SOG coef (SE) | Goals coef (SE) | Points coef (SE) |
|---|---|---|---|
| log(player EWMA) | 0.851 (0.004) | 0.662 (0.009) | 0.746 (0.006) |
| log(opp SA or GA / league) | **0.752 (0.027)** | **0.564 (0.049)** | **0.582 (0.029)** |
| home | +0.037 | +0.069 | +0.067 |
| own B2B | −0.030 | −0.066 | −0.065 |
| opp B2B | +0.026 | +0.040 | +0.043 |
| Pearson dispersion | 1.13 | 1.04 | – |

Interpretation:
- Player coefficients < 1 show the EWMA itself needs ~15% (SOG) to ~34% (goals) regression toward the mean.
- The opponent effect transfers at ~75% for SOG and ~57% for goals/points. A team allowing 10% more shots than average raises a player's SOG expectation by ~7.4%.
- SOG is mildly **over-dispersed (1.13) → use a negative binomial** or Poisson-gamma for over/under pricing, especially at alt lines.

**Team level** (Poisson on team goals, 9,154 team-games 2022-25): log(own xGF EWMA, h = 15) coef 0.59; log(opp xGA EWMA) coef **0.81**; home +0.069.

**How to compute:** team-game table from `nhl_games` (home/away sog and score), or `mp_team_games` (situation = 'all'; `xGoalsFor`/`xGoalsAgainst`, `shotsOnGoalFor/Against`, and splits by `situation` = 5on5/5on4/4on5 for **opponent xGA by strength**). Compute as-of (shifted) expanding or EWMA means per team-season. Opponent PK quality = opponent `4on5` xGoalsAgainst per 60 of `iceTime`. Pair it with the player's PP share (§3).

Literature support: RotoWire's anytime-goal model builds a Poisson λ from the player's blended goals and xG rate. It adjusts by opponent goals allowed at the player's position and an opposing-goalie multiplier, **both dampened toward neutral** (https://rotowire.com/hockey/article/nhl-anytime-goal-scorer-model-137385), which is consistent with our <1 elasticities. [LIT, M]

### 2.2 Goalie quality → team totals and saves props — [OURS+LIT]

- **[OURS, M-H]** Opposing starter's prior GSAx per 100 unblocked attempts is cumulative since 2022-23 and shrunk to 0 with K extra shots. Its coefficient on team goals is −0.115 per unit at K = 3,000 (SE 0.022), about **−3.1% goals per 1 SD**. Results were nearly identical for K = 1,500/3,000/6,000. An elite goalie at +1.0 GSAx/100 attempts implies ~−11% opponent goals.
- **[LIT, H]** MoneyPuck's game model (rebuilt Jan 2025) weights: scoring chances 54%, **goaltending 29%**, "ability to win" 17%. Goalie inputs: GSAx/60, sv% over 2 years, how often pulled recently, games-played share. https://moneypuck.com/about.htm
- **[LIT, M]** HockeyViz Magnus: goalie impact on goal odds ranges about −12% (Hellebuyck 2019-20) to +14% (Dubnyk). https://hockeyviz.com/txt/fabricxg
- **Saves props:** saves = SA × sv%. SA comes from opponent shot volume (shots-for EWMA, elasticity to own team's SA-allowed), plus score effects (see 2.4) and the chance of a pull/early exit. sv% should be a heavily shrunk estimate (k ≈ 2,200–3,000 shots). In our data the season sv% range for regular starters is ~.890–.920, so shrinkage moves very little. **Spend modelling effort on SA and on the probability the starter plays the full game.**
- **How to compute:** starter from `nhl_goalie_game.starter`. Goalie shots and saves by strength are columns (`evenStrengthShotsAgainst`, `powerPlayShotsAgainst`, …). Shot quality comes from `mp_shots` (`xGoal`, `goalieIdForShot`). Early exits: `nhl_goalie_game.toi_sec` < ~3,000 for a starter.

### 2.3 Rink / scorer bias — [OURS+LIT]

**[LIT, H]** Schuckers & Macdonald (2007-08 → 2012-13, log-linear, elastic net) rink multipliers:

| Event | Range | Highest | Lowest |
|---|---|---|---|
| Shots | 0.08 | FLA 1.03 | STL 0.955 |
| Missed | 0.69 | TOR 1.25 | CHI 0.56 |
| Blocks | 0.73 | MTL 1.27 | NJ 0.54 |
| Hits | 0.71 | LA 1.30 | NJ 0.59 |
| Giveaways | 2.02 | EDM 2.17 | CBJ 0.14 |
| Takeaways | 1.73 | NYI 1.94 | PIT 0.21 |

Source: https://arxiv.org/html/1412.1035v1. HockeyViz: location bias is mostly MSG and TB, and "less of an issue in recent years"; adjustments move locations, not rates. https://hockeyviz.com/txt/scorerBias

**[OURS, M-H]** 2022-23 → 2025-26 factor = mean event total in games at rink R ÷ mean total in the home team's road games (same season), averaged over 4 seasons:

- **Hits** (SD 0.139; YoY r of factor 0.52, 0.29, −0.15): TOR 1.24, TBL 1.19, ARI 1.16, EDM 1.14, PIT 1.11, BOS 1.08, VGK 1.06 … SJS 0.86, NJD 0.87, CBJ 0.87, SEA 0.89, CGY/ANA 0.93.
- **Blocks** (SD 0.058; YoY r 0.48, 0.26, 0.58): UTA 1.10, ARI 1.09, PIT 1.08, WSH 1.08, MTL 1.07 … MIN 0.92, VAN 0.94, TOR 0.94, CHI 0.95.
- **Giveaways/takeaways** (SD 0.18–0.23): huge factors (MTL giveaways 1.37, LAK takeaways 0.72), but YoY r is unstable (0.82 → 0.0 → 0.1). Scorers change.
- **SOG** (SD 0.038, YoY r 0.12–0.27): FLA 1.07, TBL 1.05, UTA 1.04 … CAR 0.96, NJD 0.96. **Mostly noise. Do not rink-adjust SOG props**, or shrink the factor by > 75%.
- Home vs away credited per team-game: SOG 30.0 vs 28.8; hits 22.2 vs 21.3; blocks 14.7 vs 15.2.

**How to use:** hits/blocks prop mean = player's rink-neutralized rate × venue factor. Estimate the factor with shrinkage: rolling 2 seasons, shrink ~50% toward 1.0 given the YoY r. Rink-neutralize each player's history by dividing each game's count by that game's venue factor. The confound (home-team style is partly in the factor) is small because we divide by the same team's road games.

**How to compute:** `nhl_skater_game` summed by `game_id` → join `nhl_games(home, away, season)`. Factor(team T, season s) = avg(total at T home) / avg(total in T's road games). Note `venue` exists, but `home` is simpler, except when a team relocates (ARI→UTA). Scripts are recreatable in ~40 lines of pandas.

### 2.4 Score effects on shot volume and TOI

- **[LIT, H]** Evolving-Hockey (McCurdy method) 5v5 Corsi weights. Home trailing by 3+: 0.843, tied 0.970, leading 3+: 1.140. Away: 1.230 / 1.032 / 0.891. Fenwick is similar. xG weights: trailing home 0.923 / away 1.091; tied 0.954 / 1.051; leading 0.991 / 1.010. https://evolving-hockey.com/glossary/score-adjustments/
- **[LIT, H]** McCurdy: score effects are driven more by **leading teams sitting back** (xG production of leaders falls ~10–15%) than by trailers pushing. Teams up 2-1 after conceding show ~30% below-average threat late. A trailing-by-one team is 10–15% more threatening in the 2nd period. https://hockeyviz.com/txt/scoreSeq
- **Implication for props:** expected game script matters. A heavy favourite's skaters lose SOG volume when leading, and the underdog's D-men and top forwards gain attempts. Use the moneyline/total implied goal difference as a feature, or simulate score states. Top offensive players get **more** TOI when trailing and defensive players more when leading [LIT qualitative, EH glossary]. Empty-net situations add SOG/goal upside to the trailing team's top unit and to the leading team's EN attempts.
- **How to compute:** `nhl_pbp.homeScore/awayScore` give the running score after goals. Forward-fill the score state onto shift intervals (see §3 recipe) to get player TOI and attempts by score state. `mp_team_games` already has `scoreAdjusted*` and `scoreVenueAdjustedxGoals*` columns for team-level adjusted rates.

### 2.5 Home/away, rest, travel, altitude — [OURS+LIT]

Our team-game table (nhl_games 2022-23 → 2025-26 regular season, 5,248 games):

| Situation | n | Win% | GF | GA | SF | SA |
|---|---|---|---|---|---|---|
| Own B2B vs opp 1 day rest | 702 | .407 | 2.86 | 3.31 | 28.5 | 30.1 |
| Own B2B vs opp 2+ days | 381 | .428 | 2.88 | 3.35 | 28.3 | 31.0 |
| Both B2B | 504 | .500 | 3.03 | 3.03 | 28.8 | 28.8 |
| Both 1 day | 4,120 | .500 | 3.14 | 3.14 | 29.4 | 29.4 |
| Home, 1 day | 3,192 | .536 | 3.23 | 3.02 | 30.1 | 28.7 |
| Away, B2B | 1,071 | .406 | 2.84 | 3.33 | 28.2 | 30.5 |

(Win% counts OT/SO wins.) Road B2B is the worst spot: −0.2 GF and +0.3 GA vs normal road games.

- **[LIT, H]** Rotowire, 11 seasons (2015-16 → 2025-26): B2B with a time-zone change 46.8% wins vs 49.5% for all other games. Time-zone change alone 49.1% vs 49.4% for none. Eastward 48.3% vs westward 49.9% (n.s.). https://www.rotowire.com/hockey/article/how-time-zone-travel-hurts-nhl-teams-11-seasons-of-data-122663
- **[LIT, M]** MoneyPuck: home teams win ~54%, partly due to referee bias. B2B "can decrease a team's chances of winning by ~4%". https://moneypuck.com/about.htm
- **Altitude (Colorado)** [OURS, M]: road teams at COL score 2.73 GF vs 3.02 elsewhere and allow 3.73 vs 3.21, winning 36.0% (n = 164). But COL's own home/road win split is .64/.61, a +3 pt home edge vs a league-typical ~+6 pts. **COL's results are team quality, not an extra altitude edge.** SciAm reports visiting players suffer a "5–10% performance decline during the first 10 minutes" and SpO2 drops. https://www.scientificamerican.com/article/the-colorado-avalanche-is-dominating-the-nhl-denvers-high-elevation-could-be-the-reason/ **[UNVERIFIED: no underlying study cited]**. Recommendation: no altitude feature. Optionally test a COL-venue × opponent-B2B interaction.
- **How to compute:** rest = days since the team's previous game (any game_type within the season) from `nhl_games.date`, minus 1. Time-zone change needs a team→tz map (static dict of 32 arenas) and the previous game's venue team. Travel distance needs arena lat/lon (static dict).

### 2.6 Referees and PP opportunities

- **[LIT, H]** Beaudoin, Schulte & Swartz, "Biased Penalty Calls in the NHL" (2009-10 → 2013-14): the strongest predictor of who gets the next penalty is the **penalty differential**. With the road team +3 in penalties, P(next on home) = 0.66; baseline P(home) = 0.47 (≈ 11:10 road:home). Situational effects also include score differential and game stage. https://www.sfu.ca/~tswartz/papers/penalty.pdf
- **[LIT, H]** Home penalty advantage disappears without fans. NHL regular season 2019-20: away 3.11 vs home 2.83 penalties per game. 2020-21 (no fans): 2.93 vs 2.95. https://pmc.ncbi.nlm.nih.gov/articles/PMC8378689/
- **[LIT, M]** 2024-25 had 2.71 PP opportunities per team per game, the lowest since 1977-78 (ESPN https://www.espn.com/nhl/story/_/id/44428407/nhl-2024-25-penalties-decrease-power-plays-players-referees). Leading teams receive ~44.2% of PPs vs 55.8% when trailing (Habs Eyes on the Prize 2025-26 database, search summary only, https://www.habseyesontheprize.com/2025-26-nhl-minor-penalty-database-analysis-leading-trailing-officiating-penalty-types-by-division-team/). [M]
- **[LIT, L]** Referee penalties per game ranged ~5.6–8.3 in 2022-23 (Scouting The Refs https://scoutingtherefs.com/2022-23-nhl-referee-stats/). Much of that range is sample noise: we could not test split-half reliability (see below). Treat referee effects as **unproven**. Expected SD of a referee's mean from noise alone at ~200 games is ≈ 3.0/√200 ≈ 0.21 minors per game.
- **[OURS]** Minors (2-min) per game from pbp: 2023-24 6.79, 2024-25 6.16, 2025-26 6.59 (SD 2.99 per game). **`nhl_officials` has 4,197 rows but `referee1`, `referee2`, `linesman1` and `linesman2` are all NULL.** Referee features are blocked until ingest is fixed (see open questions).
- **How to compute team PP time expected:** team PP seconds per game from shifts + pbp (§3 recipe, `team_pp_sec`). Mean ≈ 302 s per team-game. Predict it as `f(team penalties-drawn rate, opponent penalties-taken rate, league env)`, both EWMA. Penalties come from `nhl_pbp` `typeDescKey='penalty'` (`committedByPlayerId`, `drawnByPlayerId`, `duration`, `eventOwnerTeamId`).

---

## 3. Deployment: TOI, PP units, lines

### 3.1 Our results — projecting next-game TOI (2023-24 → 2025-26, evaluated from game 21 of each player-season onward, n ≈ 92.7k player-games) [OURS, H]

| Target | last game | last 5 | last 10 | season-to-date | **EWMA h = 5** | EWMA h = 10 |
|---|---|---|---|---|---|---|
| Total TOI (r / MAE s) | .772 / 137 | .832 / 113 | .834 / 113 | .819 / 117 | **.841 / 110** | .836 / 112 |
| PP TOI seconds | .546 / 61 | .667 / 50 | .684 / 49 | .684 / 50 | **.696 / 48** | .697 / 49 |
| PP **share** of team PP time | .820 | .862 | .860 | .842 | **.868** | .862 |
| 5v5 TOI | .624 / 139 | .722 / 112 | .732 / 109 | .727 / 111 | **.743 / 107** | .741 / 108 |

- Players with last-5 PP share ≥ 0.55 ("PP1-like") averaged a 0.64 share next game. Only 2.7% fell below 0.30 (n = 26.9k). **PP1 status is sticky game-to-game.** Changes arrive as discrete events (line shuffles, injuries, trades), which DailyFaceoff snapshots should catch.
- **[LIT, M]** Dobber (2016-17 →, 183 F cases): PP1 forwards average 2.28 PP min/game vs 1.55 for PP2. PP points per minute are 0.121 (PP1) vs 0.067 (PP2). **76.5% of PP1 forwards (71.9% of D) keep PP1 the next season.** https://dobberhockey.com/2026/09/11/analytics-advantage-the-draft-cost-of-power-play-roles-for-stone-zibanejad-nugent-hopkins-dobson-and-more/
- **[LIT, M]** Line trios are unstable. Even a stable team's top trio rarely shares > 55% of their EV TOI, while duos are ~80% (Oilersnation, search summary; page 403 on fetch, https://oilersnation.com/news/nhl-line-combinations-continuity-analysis-32-teams). **Model linemate effects at the pair level with decay, not by trio.**
- **[LIT, M]** TopDownHockey projects TOI with regression-derived weights on the prior 3 seasons (search summary of https://medium.com/data-science/2021-nhl-projection-model-high-level-overview-2366b3be5538; the fetch was 403, so exact weights are unverified). JFresh cards: 3-year weighted averages with weights fit per component. The example weights "0.15·Y1 + 0.25·Y2 + 0.6·Y3" are illustrative, **not verified exact** (https://jfresh.substack.com/p/player-card-20-explainer).

### 3.2 Recipe — EV/PP/PK TOI from `nhl_shifts` + `nhl_pbp` (validated: mean team PP = 302 s per game; EV + PP + PK ≈ 96% of TOI)

```sql
-- 1) state intervals from pbp (regulation periods; situationCode = [awayGoalie][awaySkaters][homeSkaters][homeGoalie])
create table ev as
select game_id, period_number p, sortOrder,
  cast(split_part(timeInPeriod,':',1) as int)*60 + cast(split_part(timeInPeriod,':',2) as int) t,
  situationCode sc
from read_parquet('data/curated/nhl_pbp/*/*.parquet', hive_partitioning=true)
where situationCode is not null and length(situationCode)=4;
create table iv as
select game_id, p, t t0, coalesce(lead(t) over (partition by game_id,p order by sortOrder), 1200) t1, sc from ev;
create table st as
select iv.game_id, p, t0, t1,
  case when cast(substr(sc,3,1) as int) > cast(substr(sc,2,1) as int) and substr(sc,1,1)='1' and substr(sc,4,1)='1' then g.home
       when cast(substr(sc,2,1) as int) > cast(substr(sc,3,1) as int) and substr(sc,1,1)='1' and substr(sc,4,1)='1' then g.away end pp_team,
  (substr(sc,2,2)='55' and substr(sc,1,1)='1' and substr(sc,4,1)='1') ev55
from iv join 'data/curated/nhl_games.parquet' g using(game_id) where t1 > t0;
-- 2) overlap with shifts (typeCode 517 = shift; 505 = goal marker rows, exclude)
select s.gameId game_id, s.playerId, s.teamAbbrev team,
  sum(case when st.pp_team = s.teamAbbrev then least(s.endTime_sec,t1) - greatest(s.startTime_sec,t0) else 0 end) pp_sec,
  sum(case when st.pp_team is not null and st.pp_team <> s.teamAbbrev then least(s.endTime_sec,t1) - greatest(s.startTime_sec,t0) else 0 end) pk_sec,
  sum(case when st.ev55 then least(s.endTime_sec,t1) - greatest(s.startTime_sec,t0) else 0 end) ev_sec
from read_parquet('data/curated/nhl_shifts/*/*.parquet', hive_partitioning=true) s
join st on st.game_id = s.gameId and st.p = s.period and st.t0 < s.endTime_sec and st.t1 > s.startTime_sec
where s.typeCode = 517
group by all;
-- team_pp_sec = sum(t1-t0) from st grouped by game_id, pp_team; pp_share = pp_sec / team_pp_sec
```

Caveats:
- The first version was regulation-only. Add OT with `period_number = 4` and a 300 s cap in regular season.
- The situationCode on the penalty event itself can lag by one event. This is minor.
- A few games have duplicated shift rows (ev_sec > 3,600 s). Deduplicate shifts on (gameId, playerId, period, startTime_sec) first.
- Shift seasons are partitioned by *start year* (`season=2024` = 2024-25).

### 3.3 Injuries and line changes

When a top-6 F or top-4 D is out, their TOI redistributes mostly within position and unit. Estimate it empirically from our shifts: find games where a regular (EWMA TOI > X) is absent, and regress teammates' TOI and PP share deltas on the absent player's EWMA TOI and PP share. Not done yet; see open questions. DailyFaceoff snapshots (from 2026-09-30) give projected lines and PP units, but there is no history, so backtests must use actual deployment (hindsight). Quantify that degradation per DATA.md.

---

## 4. Early season: priors vs current season

### 4.1 Our result — optimal blend weights [OURS, H]

OLS of rest-of-season per-game rate on [prior-season per-game rate, current season-to-date], players with ≥ 40 GP prior season and ≥ 20 GP remaining, 2023-24 → 2025-26 (n ≈ 1,270–1,620).

| Games into season | SOG w_cur | Goals w_cur | Points w_cur | TOI w_cur | Hits w_cur | Blocks w_cur |
|---|---|---|---|---|---|---|
| 3 | .13 | .06 | .09 | .51 | .17 | .11 |
| 5 | .19 | .09 | .12 | .58 | .25 | .18 |
| 10 | .32 | .17 | .21 | .69 | .40 | .30 |
| 20 | .51 | .34 | .37 | .79 | .56 | .43 |
| 30 | .63 | .45 | .47 | .87 | .68 | .55 |
| 40 | .70 | .49 | .56 | .89 | .84 | .55 |

- **Equivalent prior weight (k in games):** SOG ≈ 17–21, points ≈ 31–35, goals ≈ 40–42, TOI ≈ 4–5, hits ≈ 8–15, blocks ≈ 26–33. Use `w_cur = n/(n+k)`.
- The coefficient sum is 0.82–0.96, so **also shrink the blend ~5–15% toward the position/role mean**: SOG ~10%, goals ~15%, points ~8%, TOI ~5%.
- **TOI is the exception:** current-season deployment overtakes the prior within ~5 games (coaching/role changes). This is why October TOI/PP projections should lean on the DailyFaceoff lines and the first few games.
- **Team changers and rookies:** points/60 and PP share lose the most YoY correlation on team changes (§1.1), so give movers a smaller k for points/PP (e.g., ×0.6) but keep k for SOG/60 and ixG/60. For rookies, use `nhl_player_seasons` (AHL/CHL/Europe) translated with league-equivalency factors. TopDownHockey's NHLe work is the reference (https://topdownhockey.medium.com/nhl-equivalency-and-prospect-projection-models-building-the-prospect-projection-model-part-3-5ed9e1cff67f); **the fetch was 403, so factors were not extracted**. Fall back to position × draft-round × TOI-role means with a large k.

### 4.2 Aging

- **[LIT, M]** Delta-method on EV rates (Evolving-Hockey data): forward scoring rate peaks ~24, shot rate ~22, gradual decline through late 20s, steep in 30s. https://sabermetricmusings.blogspot.com/2020/07/nhl-skill-aging-curves-scoring-and-shot.html. Other summaries: forwards within 90% of peak from 24–32 (search summary, unverified); FPCA aging curves by Swartz et al. https://www.sfu.ca/~tswartz/papers/aging.pdf (not fetched).
- **Practical:** apply an age delta to the prior-season rate (−2% to −4% per year for SOG/60 after ~29, +3–5% for ≤ 23). Estimate the exact deltas ourselves from `mp_skaters_seasons` 2015+ with the delta method (bio ages in `mp_players` / `nhl_players`).

### 4.3 In-season update speed

- For per-game features, use EWMA with half-life ~5 games for TOI and PP share. For shot rates, use ~10–15 games plus the season prior with k from the table above. For finishing and goalie sv%, use cumulative multi-season data with large k (200–375 shots for skaters; 2,000–3,000 shots for goalies).
- MoneyPuck/Hockey-Graphs agree that xG-type process stats beat results stats at every horizon ≥ 10 games.

---

## 5. Goalies

| Signal | Finding | Source | Conf |
|---|---|---|---|
| B2B starter rotation | 2nd night of a B2B: same goalie as night 1 only **7.8%** (n = 1,597); overall consecutive-start rate 48.5% | OURS | H |
| Starter model | Logit on season main-goalie start share (log-odds coef 4.69), main started last game (0.90) or 2 games ago (1.02), B2B with main starting night 1 (−2.70), rest days, home. Test accuracy 70.1% vs 59.6% "always main" baseline. Sensitivity 87.9%, specificity 43.9% | Sportlogiq, "Predicting the Starting Goalie" https://www.sportlogiq.com/2020/08/07/elementor-2557/ | H |
| Workload trend | 60-start goalies are nearly extinct (13 in 2007-08 → 1 last season). Scheduled rest grew from 16% to 30% of team games. Same-goalie start share YoY r = 0.32 | Dobber, "Disappearance of the 60-start goalie" https://dobberhockey.com/2026/07/31/analytics-advantage-the-disappearance-of-the-60-start-goalie-and-new-goaltending-trends/ | M |
| Main-goalie share | Our top goalie start share per team-season: mean 0.595 (IQR 0.52–0.67) | OURS | H |
| B2B fatigue | No detectable sv% penalty on consecutive-night starts over 19 seasons (+0.02 pts, p = 0.80). **4th/5th start in 14 days: −0.2 sv% pts** (95% CI −0.31 to −0.09) | Dobber (above) | M |
| B2B fatigue (older) | Tulsky 2013 found a meaningful drop. NHL.com restates it as "reduced sv% by just over 11 percent … ~3 more goals/game", **which is not plausible as written [UNVERIFIED/garbled]**. Later work by A. Thomas and D. Luszczyszyn found smaller effects (no numbers given) | NHL.com Kraken "Examining Goalie Workload" https://www.nhl.com/kraken/news/core-concepts-examining-goalie-workload-329507592 | L |
| B2B, box scores | 1,409 B2B starts vs 9,889 rested: GAA 2.79 vs 2.77. Coach selection filters fatigue. The same page's sv% figures (54.4%/58.2%) are nonsensical **[UNVERIFIED]** | DataStreak https://datastreak.com/insights/nhl-goalies-back-to-back | L |
| Ours | Backups starting night 2: raw sv% .8996 vs rested starts .9016 (but backup quality is confounded). Same goalie both nights: .9042 (n = 125). Teams face slightly more shots on B2B nights (29.2 vs 28.3 SA) | OURS | M |

**Recommendation:** the starter-probability model is the highest-value goalie feature for saves and team totals. Inputs: season start share (EWMA), who started the last 1–2 games, B2B flag and night-1 starter, days of rest for each goalie, starts in the last 14 days, home/away, opponent strength (coaches save starters for tougher opponents: test it). At bet time, blend with DailyFaceoff "confirmed/likely" status. Goalie-quality effect on opponent goals ≈ 3% per SD of shrunk GSAx (§2.2). For the saves line, model SA carefully: opponent SF EWMA^~0.75 × own SA-allowed, plus score-script and pull risk.

---

## 6. NHL EDGE / tracking

- **Availability [LIT, H]:** skating speed and bursts, distance, shot speed, shot location, zone time, and goalie save% by location. Data starts in 2021-22 and updates overnight, not in real time. https://www.dailyfaceoff.com/news/new-stat-portal-nhl-edge-gives-fans-access-to-player-and-puck-tracking-for-first-time
- **Endpoints [LIT, H]:** `api-web.nhle.com/v1/edge/skater-detail/{id}/{season}/{gameType}` (or `/now`), `skater-shot-speed-detail`, `skater-skating-speed-detail`, `skater-zone-time/{id}/…`, `skater-shot-location-detail`, `team-zone-time-details/{teamId}/…`, `team-shot-location-detail`, and `*-top-10` leaderboards. Goalie EDGE endpoints exist but paths were truncated in the reference. https://github.com/Zmalski/NHL-API-Reference
- **Value [LIT, M]:** team 18+ mph burst rates correlate with Corsi and xG *volume* (90% conf.), not shot quality (xG/Fenwick) (2021-23). https://puckovertheglass.substack.com/p/nhl-edge-data-deeper-dive-team-burst. Tracking won the Sloan Alpha Award 2022 (https://www.nhl.com/news/nhl-puck-player-tracking-honored-at-sloan-sports-analytics-conference-331649276), but public EDGE is **season-aggregate**, so it can't build as-of game-level features historically unless we snapshot it daily.
- **Recommendation:** low priority. Possible uses: (a) OZ time % as a stable "offensive-environment" prior for players with few NHL games; (b) shot-location mix. Start a daily snapshot now if we want it later (same logic as DailyFaceoff). Not needed for v1.

---

## 7. Recommended feature list (with lag windows and shrinkage)

All features are **as-of** (strictly prior games). "EWMA hN" = exponentially weighted mean with half-life N games. "k" = prior weight in games (or shots) toward the prior-season/role mean.

| # | Feature (prop) | Build from | Window / shrinkage | Priority |
|---|---|---|---|---|
| 1 | TOI/game proj (all) | `nhl_skater_game.toi_sec` | EWMA h5; prior k ≈ 4–5 g; override with DFO line slot at bet time | Must |
| 2 | PP share of team PP time (SOG, G, A, P) | shifts × pbp recipe §3.2 | EWMA h5; prior = last-season 5on4 share (MP) with k ≈ 5 g | Must |
| 3 | Expected team PP seconds | pbp penalties drawn/taken, recipe `team_pp_sec` | Team EWMA h15 drawn × opp taken, normalized to league | Must |
| 4 | Shot attempts/60 and SOG/60 by strength (EV, PP) | pbp attempts ÷ ev_sec/pp_sec | EWMA h10–15; k ≈ 20 g vs prior-season rate; ×0.9 regression | Must |
| 5 | ixG/60 by strength (G) | `mp_shots` xGoal by shooter | EWMA h15; k ≈ 15 g within season, prior season heavy | Must |
| 6 | Finishing multiplier (G) | career G vs ixG | Shrink G/ixG ratio toward 1.0 with +200–375 shots of prior (F: 375 per LIT, ~210 per OURS; D: 275, but D finishing YoY r ≈ 0.06, so effectively set to 1.0) | Must |
| 7 | Primary/secondary assist rates (A, P) | pbp assist1/assist2 | A1 k ≈ 30 g, A2 k ≈ 48 g; prefer on-ice xGF/60 × assist share | Should |
| 8 | On-ice xGF/60 (5v5) and linemate quality (A, P) | `mp_shots` + shifts on-ice | EWMA h15; YoY r only 0.44–0.56, so shrink ~50% | Should |
| 9 | Opp SA/60 (and SOG allowed) by strength (SOG) | `nhl_games`/`mp_team_games` | EWMA h15–20 as-of; apply with elasticity ≈ 0.75 | Must |
| 10 | Opp xGA/60 by strength and opp PK xGA (G, P) | `mp_team_games` situation splits | EWMA h15–20; elasticity ≈ 0.55–0.6 (fit) | Must |
| 11 | Opp starter goalie shrunk GSAx/shot (G, P, team totals) | `mp_shots` cumulative since 2022 | +3,000 shots of 0 GSAx (k ≈ 2,200–3,000) | Must |
| 12 | Starter probability (saves, team totals) | `nhl_goalie_game.starter` history + schedule | Logit (Sportlogiq-style); B2B night-1 starter flag is the key input | Must |
| 13 | Home flag (all) | `nhl_skater_game.is_home` | Fixed coef: SOG +3.7%, G/P +7% | Must |
| 14 | Own/opp rest days, B2B, B2B × tz change (all) | `nhl_games.date` + arena tz dict | Categorical: 0 / 1 / 2+ days; own B2B −3% SOG, −6.5% G/P | Must |
| 15 | Rink factor for hits and blocks (hits/blocks props) | §2.3 | 2-season rolling, shrink 50% to 1.0; SOG: none | Must (for hits/blk) |
| 16 | Game script: implied team goal diff and total (all) | SGO consensus close/fair lines | Direct from market; interacts with trailing-team volume | Should |
| 17 | Score-state-adjusted rates (SOG) | pbp score + shift intervals | Use EH weights for 5v5 Corsi normalization | Nice |
| 18 | Early-season blend weights (all) | §4.1 table | `w_cur = n/(n+k)`; k: SOG 20, P 33, G 40, TOI 5, hits 12, blk 30 | Must |
| 19 | Age delta on priors | `nhl_players` birthdate | Delta-method curves (to estimate) | Should |
| 20 | Goalie workload (4+ starts / 14 d) (saves) | `nhl_goalie_game` | Binary; −0.2 sv% pts | Nice |
| 21 | Referee penalty rate (PP TOI) | `nhl_officials` (**broken: all NULL**) | Only after ingest fix, and only if split-half r > ~0.2 | Blocked |
| 22 | Distribution: NegBin dispersion for SOG | fit | Dispersion ≈ 1.13 at game level (Pearson) | Must |

---

## 8. Open questions / to-do

1. **`nhl_officials` is empty** (all referee and linesman fields NULL for 4,197 games). Fix `src/ingest/nhl.py` or curate (likely a field-name change in the gamecenter `right-rail`/`game-story` response). Then test referee split-half reliability of minors per game before using it.
2. **Shift duplicates:** some player-games give > 3,600 s EV time. Dedupe in `curate.py`. Also add OT periods to the PP/EV/PK recipe.
3. **TOI redistribution when players are absent:** estimate from shifts (absent regular → teammates' TOI and PP share deltas). This is needed for injury news trading.
4. **Hindsight degradation:** our TOI/PP-share features use actual deployment. Quantify the error when using DFO projected lines, once enough snapshots accrue (from 2026-09-30).
5. **Opponent defense by position/zone:** does opponent SA allowed to D-men vs forwards (from pbp shooter position) add beyond team SA? Also test opp shot-*block* rate for SOG props (blocked attempts don't count as SOG).
6. **Goalie shot-location-adjusted sv% (DIGR/aSVP):** Schuckers found better reliability than raw sv% in some seasons. Test it using `mp_shots` xGoal (GSAx is this) vs danger-tier-specific sv%.
7. **Scorer bias for SOG by home/away team:** we only computed game totals. Check whether rinks shade *home-team* SOG specifically (home SOG 30.0 vs 28.8 away is partly real home advantage).
8. **Score-state TOI elasticity** per player type (top-6 F vs defensive D). Compute it from shift intervals with forward-filled score, then feed it into a game-script simulation.
9. **Verify unverified claims** marked above (Tulsky B2B magnitude, SciAm altitude figures, JFresh/TopDownHockey exact weights, NHLe factors).
10. **Market check:** after building these features, measure which ones add log-loss improvement **versus SGO closing prices**, not just vs outcomes. Books already price TOI, PP and opponent, so the edge is probably in fast deployment updates (#1–3, #12) and rink-adjusted hits/blocks (#15).

---

### Source list (fetched or read)

1. Hockey-Graphs — xG better predictor (2015) https://hockey-graphs.com/2015/10/01/expected-goals-are-a-better-predictor-of-future-scoring-than-corsi-goals/
2. Hockey-Graphs — Expected Primary Points (2017) https://hockey-graphs.com/2017/01/19/expected-primary-points-are-a-better-predictor-of-future-scoring-than-shots-points/
3. Hockey-Graphs — Save % vs the experts (2014) https://hockey-graphs.com/2014/01/20/2013-2014-goaltending-performance-save-percentage-correlation/
4. Macdonald, Lennon, Sturdivant — Weighted Shots (arXiv 1205.1746) https://arxiv.org/pdf/1205.1746
5. Schuckers — Statistical Evaluation of Goaltending (2016) http://myslu.stlawu.edu/~msch/sports/StatEvalofGoalies2016Schuckers.pdf
6. Tango — NHL goalie talent / regression constant https://insidethebook.com/ee/index.php/site/comments/how_to_figure_out_how_much_talent_there_is_example_with_nhl_goalies
7. Schuckers & Macdonald — Rink effects in RTSS (arXiv 1412.1035) https://arxiv.org/html/1412.1035v1
8. HockeyViz — Scorer Bias Adjustment https://hockeyviz.com/txt/scorerBias
9. HockeyViz — Score Sequencing https://hockeyviz.com/txt/scoreSeq
10. HockeyViz — Magnus 3: xG, Shooting, Goalie-ing https://hockeyviz.com/txt/fabricxg
11. Evolving-Hockey — Score Adjustments glossary https://evolving-hockey.com/glossary/score-adjustments/
12. Evolving-Hockey — A New Expected Goals Model https://evolving-hockey.com/blog/a-new-expected-goals-model-for-predicting-goals-in-the-nhl/
13. MoneyPuck — About / methodology https://moneypuck.com/about.htm
14. Puck Over the Glass — predicting future goals https://puckovertheglass.substack.com/p/which-is-better-at-predicting-future
15. Puck Over the Glass — EDGE burst rates https://puckovertheglass.substack.com/p/nhl-edge-data-deeper-dive-team-burst
16. JFresh — Player Card 2.0 Explainer https://jfresh.substack.com/p/player-card-20-explainer
17. Canucks Army (J. Davis) — Zone starts Part II https://canucksarmy.com/news/beware-of-what-zone-starts-are-telling-you-part-ii-shot-metrics
18. Beaudoin, Schulte, Swartz — Biased Penalty Calls in the NHL https://www.sfu.ca/~tswartz/papers/penalty.pdf
19. PLOS ONE — Absence of fans removes home penalty advantage https://pmc.ncbi.nlm.nih.gov/articles/PMC8378689/
20. Scouting The Refs — 2022-23 referee stats https://scoutingtherefs.com/2022-23-nhl-referee-stats/
21. Sportlogiq — Predicting the Starting Goalie https://www.sportlogiq.com/2020/08/07/elementor-2557/
22. Dobber — Disappearance of the 60-start goalie (2026) https://dobberhockey.com/2026/07/31/analytics-advantage-the-disappearance-of-the-60-start-goalie-and-new-goaltending-trends/
23. Dobber — Draft cost of PP roles (2026) https://dobberhockey.com/2026/09/11/analytics-advantage-the-draft-cost-of-power-play-roles-for-stone-zibanejad-nugent-hopkins-dobson-and-more/
24. NHL.com (Kraken) — Examining Goalie Workload https://www.nhl.com/kraken/news/core-concepts-examining-goalie-workload-329507592
25. DataStreak — Tired goalies, 1,409 starts https://datastreak.com/insights/nhl-goalies-back-to-back
26. Rotowire — Time-zone travel, 11 seasons https://www.rotowire.com/hockey/article/how-time-zone-travel-hurts-nhl-teams-11-seasons-of-data-122663
27. Rotowire — Anytime goal scorer model https://rotowire.com/hockey/article/nhl-anytime-goal-scorer-model-137385
28. Scientific American — Avalanche altitude https://www.scientificamerican.com/article/the-colorado-avalanche-is-dominating-the-nhl-denvers-high-elevation-could-be-the-reason/
29. Sabermetric Musings — NHL skill aging curves https://sabermetricmusings.blogspot.com/2020/07/nhl-skill-aging-curves-scoring-and-shot.html
30. Daily Faceoff — NHL EDGE portal https://www.dailyfaceoff.com/news/new-stat-portal-nhl-edge-gives-fans-access-to-player-and-puck-tracking-for-first-time
31. Zmalski — NHL API Reference (EDGE endpoints) https://github.com/Zmalski/NHL-API-Reference
32. "Expected by Whom?" skill-adjusted xG (arXiv 2511.07703) https://arxiv.org/abs/2511.07703
33. Davis & Robberechts — Biases in xG confound finishing (arXiv 2401.09940) https://arxiv.org/abs/2401.09940
34. hockey-statistics.com — Building the game projection model https://hockey-statistics.com/2020/11/27/building-the-game-projection-model/
35. NHL.com — Tracking honored at Sloan https://www.nhl.com/news/nhl-puck-player-tracking-honored-at-sloan-sports-analytics-conference-331649276

Search-summary-only (the page itself was not fetched or returned 403; treat as M/L): ESPN 2024-25 penalties; Habs Eyes on the Prize penalty DB; Oilersnation line continuity; TopDownHockey projection/NHLe; Tape to Tape GSAx; Dobber secondary assists.
