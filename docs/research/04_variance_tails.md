# 04: Variance, randomness and tail pricing

*Research digest, 2026-10-01.*

**Scope.** How random hockey is. Where the tails of the outcome distribution sit: blowouts, 9+ goal games, comebacks, first goal scorer, depth scorers. Whether betting markets price those tails correctly. How pros bet variance. Builds on digests 01–03 and `docs/findings/2026-09-30_*`.

**How to read this doc**
- **Tags**
  - **[LIT]**: a number from a published source (citation and URL given).
  - **[OURS]**: computed on our curated data during this research. The scripts were ad hoc; the recipes are reproduced in §3 so they can be productionized.
  - **[UNVERIFIED]**: seen in a secondary source or a search snippet that we could not confirm against the primary source. Do not rely on it.
- **Confidence:** **H** = several sources agree and/or our data confirms with large n. **M** = one good source or a moderate-n check of our own. **L** = thin.
- **Samples used for [OURS]:**
  - Regular-season games 2023-24 → 2025-26: n = 3,936–3,938 (pbp), 5,248 (boxscores 2022-26).
  - Per-book pregame closes 2026-01-17 → 2026-04: 539 regular-season games. That covers 190,921 first-goal-scorer (FGS) book×player quotes and about 50k anytime-goal (AG) quotes.

**Bottom line for the "value is in the tails" thesis.**
- Our data and the literature both say **the *yes* side of rare events is where books load the most margin**. This holds for:
  - depth and 4th-line players to score first or anytime;
  - 10+ goal games;
  - 5+ goal margins.
- On top of that, **hockey's game-level tails are *thinner* than the Poisson/NB models that most books and bettors use**. This is mostly because of score effects and the post-goal faceoff "refractory" period.
- Tails are where mispricing is *largest*, but the mispricing mostly favours the **under / no / short side**.
- Profitable *yes*-side tail bets need a specific information edge. Examples:
  - a line promotion or a PP1 promotion;
  - an injury that the price has not absorbed;
  - a correlation the book under-models;
  - a sharp-book price on a longshot.
- "Unlikely things happen more than people think" is not an edge. In hockey they happen *less* often than a naive Poisson model says.

---

## 1. Key takeaways, ranked by exploitable value

1. **Depth and defenseman scorer longshots are the most overpriced segment we have measured. Middle-six forwards are close to fair.** [OURS, H on direction, M on size]
   - Roles below are by trailing 10-game TOI rank (computed before the game, so no leakage): F_top = rank 1–3 forwards, F_mid = 4–9, F_bottom = 10+; D_top = rank 1–2, D_mid = 3–4, D_bottom = 5+.
   - **First goal scorer (FGS), per-book closes:**

     | Role | Hit rate | Implied prob | Hit / implied | ROI |
     |---|---|---|---|---|
     | F_bottom | 1.25% | 2.95% | 0.42 | −52% |
     | D_bottom / D_mid | 0.7–0.9% | 1.6–2.0% | 0.43 | −53% / −55% |
     | F_top | — | — | 0.68 | — |
     | F_mid | — | — | 0.81 | −19% |

   - **FGS, best price across 13 books:** F_bottom ROI **−38%**, D_mid −44%, D_top −11%, F_top −19%, **F_mid −5%**.
   - **Anytime goal (AG), best price:** **F_bottom −28%** (hit 7.8% vs 11.0% implied), D_bottom −21%, D_mid −13%, D_top −7%, F_top −2%, **F_mid +2.7%** (19.7% vs 19.4%, not significant).
   - **FGS ROI by price at per-book close** (blanket):

     | Price band | ROI | Hit / implied |
     |---|---|---|
     | +900 to +2,200 | −24% to −28% | — |
     | +3,000 to +4,500 | −40% | — |
     | +4,500 to +10,000 | −41% | 0.58 |

   - This is a textbook favourite–longshot bias layered on a ~15–25% FGS overround.
   - **Action:**
     - Never blanket-bet depth or D longshots.
     - If we bet scorer markets, it is **middle-six forwards at the best price**, or a role change the price has not absorbed.
2. **Game and team goal tails are thinner than Poisson. 10+ / 12+ totals and 5+ margins happen less often than a Poisson model fitted to the market's main line implies.** [OURS + LIT, H]
   - **Dispersion:** total-goals var/mean is **0.82–0.89** per season, 2022-26 (regulation-only goals: 0.92).
   - **Poisson solved per game from the closing main total** (539 games, 2026) vs actual:

     | Outcome | Actual | Poisson |
     |---|---|---|
     | ≥10 goals | 7.6% | 12.3% |
     | ≥11 goals | 4.8% | 6.8% |
     | ≥12 goals | 1.1% | 3.5% |
     | Team scores ≥7 | 3.1% | 4.9% |
     | Team scores ≥6 | 10.2% | 11.1% |
     | Margin of 5+ (2023-26, vs independent-Poisson Skellam) | 5.9% | 7.1% |
     | Margin of 6+ | 2.0% | 2.9% |

   - **Mechanisms:**
     - Score effects: leaders sit back [LIT: hockeyviz].
     - A ~20 s post-faceoff warm-up after every goal [LIT: Thomas 2007].
     - A shared pace factor is *not* needed (digest 01, sim v1).
   - **Action:** high alt overs (9.5+, 10.5+), alt puck lines −3.5/−4.5 and team-total 6.5+ overs are structurally rich if a book prices them off Poisson or NB. **Alt unders and "no" sides are the systematic tail side.** We need the snapshot ladders (H1) to confirm the book side.
3. **The OT/shootout +1 creates a strong odd/even sawtooth that smooth ladders cannot price.** [OURS, H]
   - Shootout winners add one goal to the winner's team total and the game total (DK house rules, §2.3). Tied regulation games therefore end on an odd total.
   - Final-total distribution 2023-26:

     | Total | Share of games |
     |---|---|
     | 5 | 22.0% |
     | 6 | 11.1% |
     | 7 | 20.5% |
     | 8 | 7.7% |
     | **9** | **10.4%** |
     | **10** | **2.7%** |
     | 11 | 3.2% |

   - So **Over 8.5 and Over 9.5 differ by ~10.4 points**, versus ~8 points under a smooth Poisson with the same mean.
   - Team totals carry the same effect: the winner gets +1 in OT/SO.
   - **Action:** price each ladder rung from the simulator, which handles OT/SO explicitly. Hunt for rungs where a book's ladder is smooth: Over 9.5 and team-total Over 4.5 for the side likely to win in OT are likely too expensive.
4. **The empty net makes 3-goal margins common, but 5+ margins rare.** [OURS, H]
   - |margin| ≥ 3 occurs in **40.3%** of games vs 30.7% under independent Poisson. This is the empty-net goal turning 2 into 3.
   - |margin| ≥ 5 is *rarer* than Poisson (above).
   - A game reaches 5–0 at some point in **4.2%** of games. Some team leads by 5+ at some point in 8.1%.
   - **Action:** alt puck line ±2.5 is where the empty-net mass lives. ±4.5/5.5 is where Poisson pricing overstates.
5. **"Starting lineup / opening shift" gives no first-goal edge, and first goals are slightly *less* top-line-concentrated than all goals.** [OURS, H]
   - Opening-shift skaters (12 per game) score **32.0%** of first goals. They are about 33% of dressed skaters.
   - Median first goal is at **6:27 of P1**. 83% of first goals come in P1; only **6.3%** come in the first 60 s.
   - **First-goal share relative to all-goal share, by role:** F rank 1–3: **0.94**. F 4–6: 1.01. F 7–9: 1.06. **F 10+: 1.09**. D: 0.94–1.07.
   - All-goal shares include late PP time and empty-net goals, which go to stars ([LIT]: Daily Faceoff, 7% of goals are empty-net goals, mostly scored by stars).
   - **Implication:** an FGS price built as "AG share × team-scores-first" *slightly underprices depth* on structure (+6–9%). The 40–60% margin markup on depth (takeaway 1) swamps this.
   - The home team's last change (deployment) matters only through which lines get the most P1 ice time, not who starts.
6. **Hockey is very random at the game level, but the market already prices that.** [LIT, H]
   - Luck explains 34% (Teeter) to ~53% (Birnbaum/Tango) of season-standings variance.
   - The best team beats a median team only **57%** of the time on neutral ice (NBA 67%, NFL 65%, MLB 56%; Lopez et al. 2018).
   - Randomness widens the distribution, but books start from the same Poisson-ish shape we do. Edge comes from getting the *shape* right (takeaways 2–4), not from "upsets are underpriced".
   - **Reverse favourite–longshot bias on NHL moneylines** existed in 1990–96 (Woodland & Woodland) but converged to efficiency.
7. **No exploitable momentum at team, goalie or game-to-game level. The player "hot hand" is small and probably role-driven.** [LIT + OURS, H]
   - **Team:** the next goal goes to the team that scored last 50.8% of the time [OURS]. With a 1–2 goal lead in P1–P2 at 5v5, the leader scores next 49.5–49.9% [OURS]. Score effects cancel the better-team selection.
   - Post-goal shot quality is roughly ±5% (hockeyviz).
   - Bettors stake ~40% more on teams with "momentum", and that loses money (Ötting et al., Bundesliga).
   - **Goalies:** no hot hand; recent good saving slightly *predicts worse* next-shot saves (Ding et al., 48k playoff shots).
   - **Blowouts:** no carry-over to the next game (Chachad et al.).
   - **Players:** a forward with ≥2 goals above expectation in his last 5 scores at **1.05–1.07×** his leave-out season rate. A cold player scores at 0.90–0.95× [OURS].
     - Logistic: +8% odds per extra goal in the last 5, given the season rate.
     - This is consistent with role and TOI changes. Use TOI/PP EWMA, not goal streaks.
8. **Player "volatility" is not a persistent trait. Use one NB α for everyone.** [OURS, H]
   - The per-player-season SOG dispersion index has SD **0.186**, identical to a pure-Poisson null with the same means and n (0.186).
   - Year-over-year correlation of the index is **0.06** (n = 920).
   - There are no persistently "boom-bust" shooters to target with alt ladders. Ceiling differences come from *mean* differences (TOI, PP1), not shape.
9. **Book choice matters more for longshots than for anything else.** [OURS + LIT, H]
   - **FGS overround** (sum of implied probabilities over the ~30 listed players):

     | Book(s) | Overround |
     |---|---|
     | ESPNBet | 1.15 |
     | BetMGM | 1.18 |
     | DK | 1.20 |
     | FD | 1.19 |
     | Bet365 / Caesars / Bovada | 1.22–1.24 |
     | Hard Rock | 1.30 (only 20 listed) |
     | Fliff | 1.35 |
     | BetRivers / BallyBet | **1.54** |

   - Kalshi FGS was a −64% blanket ROI, on thin n.
   - Literature: traditional books shorten favourites ~3% but longshots ~12% (Buchdahl / football-data). Pinnacle and exchanges show little bias.
   - **Action:** longshots must be priced against the best of 10+ books. Never take a soft-book longshot without shopping.
10. **For multi-leg tail bets, correlation is the only lever, and SGP holds are 15–25%.** [LIT, M]
    - Books model same-game correlation with copulas or empirical frequencies.
    - Value is rare. It is most likely in combinations the book's generic copula misses: hockey-specific dependencies such as OT/SO parity, empty-net timing, the FGS team ↔ moneyline link, and goalie pulls.
    - Pinnacle prices parlays as a straight product, with no correlation adjustment. *Positively* correlated legs at Pinnacle are a known structural edge, subject to limits.
    - Our simulator v1 already reproduces the teammate correlations (points–points 0.14) needed to price these.

---

## 2. Findings by topic

### 2.1 How random is hockey?

| Finding | Key numbers | Source | Conf. |
|---|---|---|---|
| Share of season-standings variance due to luck | NHL **34.4%**, NBA 13.3%, MLB 27.8%, EPL 31.4%, NFL 43.1% (true-score theory, ~25 seasons) | Teeter 2023, https://www.cteeter.ca/blog/2023-10-22-sports-luck/ | H |
| Games needed for talent SD = luck SD | ~36 games (Tango). Over 82 games, talent SD 8.95 vs luck SD 8.44 points | Birnbaum 2013, http://blog.philbirnbaum.com/2013/01/luck-vs-talent-in-nhl-standings.html (page returned 503; numbers from the search snippet) | M [partly UNVERIFIED] |
| Probability the best team beats a median team at a neutral site | NHL **57%** vs NBA 67%, NFL 65%, MLB 56%. NHL is the most random league per game after MLB | Lopez, Matthews & Baumer 2018, *Ann. Appl. Stat.* 12(4), https://arxiv.org/abs/1701.05976 | H |
| Scoring tempo is close to a Poisson process; NHL games show "more blowouts and fewer ties than expected" under a balanced Bernoulli. The probability of scoring next rises with lead size, consistent with team-skill heterogeneity rather than momentum | NHL 2000–09, 11,813 games | Merritt & Clauset 2014, *EPJ Data Science* 3:4, https://arxiv.org/abs/1310.4461 | H (era caveat) |
| Lead-size dynamics in the modern NHL | Leader scores next: L=1: 51.6% (P1–2 at 5v5: 49.9%). L=2: 53.8% (P1–2: 49.6%). L=3: 53.3% (P1–2 at 5v5: 53.4%). L=4+: 50.5% (P1–2 at 5v5: 54.8%). The all-period numbers are inflated by empty-net goals | [OURS] pbp 2023-26 | H |
| Lead changes follow a random walk: number of lead changes ~ Gaussian; the timing of the max lead and of the last lead change follow arcsine laws | 1.25M scoring events, 4 sports | Clauset, Kogan & Redner 2015, *Phys Rev E* 91, https://arxiv.org/abs/1503.03509 | M |
| Goals arrive with a ~20 s "warm-up" after each faceoff (plateau-hazard), then a flat hazard. The asymptotic rate rises slightly with goal differential: 1.57 → 1.71 per 1,000 s from tied to +3 | NHL 2006-07 | Thomas 2007, *JQAS* 3(3), https://hockeyanalytics.com/Research_files/Interarrival%20Times%20of%20Goals%20in%20Ice%20Hockey.pdf | H |
| Goals are **underdispersed** at game level | Total-goals var/mean: 0.815 / 0.858 / 0.886 / 0.845 (2022-23 → 2025-26). Regulation-only 0.918. Home 0.97, away 1.00, corr(home, away) −0.12 | [OURS] `nhl_games`, pbp | H |
| Older literature reports *broader* than Poisson | "Underproducing games with 3 events and overproducing games with 0 or with 8 or more" | Search snippet attributed to Washburn/NPS 2011 *JQAS*, https://faculty.nps.edu/awashburn/docs/EstimatingNHLScoringRates.pdf | L [UNVERIFIED; conflicts with our 2022-26 data: different era, and the pooled-mean effect] |
| PDO, shooting % and save % have weak year-over-year repeatability. Only ~3.6% of players with on-ice SH% > 11% repeat it | Narrative + numbers | JFresh, https://jfresh.substack.com/p/percentage-luck-in-hockey-explained | M |
| Player shooting % needs heavy shrinkage (k ≈ 200–240 shots); save % k ≈ 2,200–3,000 shots | See digest 03 §1 | digest 03 | H |
| Raw goals-minus-xG is a poor finishing metric: high variance and xG-model bias toward elite finishers | Soccer (Messi GAX understated 17%) | Davis & Robberechts 2024, https://arxiv.org/abs/2401.09940 | M (soccer analogue) |

**Interpretation.** The *talent* spread between NHL teams is narrow and each game is noisy, so outcome *uncertainty* is high. But the within-game process is more *regular* than Poisson. Three things cut both tails:
- the refractory faceoff after each goal;
- leaders sitting back;
- trailing teams pushing.

Late-game empty-net goals then push mass onto a 2–3 goal margin. High uncertainty about *who wins* coexists with thin tails on *how lopsided* or *how high-scoring*. This explains why books and bettors who think "hockey is random, so blowouts and 9+ games are common" overprice the far tails.

### 2.2 Tail events: blowouts, high totals, comebacks, empty nets

| Event (regular season) | Frequency [OURS] | Comparison | Conf. |
|---|---|---|---|
| Total ≥ 9 (final, incl. SO +1) | 16.7–18.4% per season | Poisson at the season mean: ~16.5% (fine at 9 because of the odd spike) | H |
| Total ≥ 10 | 7.1–7.6% | Poisson from closing totals: 12.3%. Poisson at the season mean: 9.2% | H |
| Total ≥ 12 | 1.4% (2023-26) / 1.1% (2026 market sample) | Poisson: 2.3% / 3.5% | H |
| Total ≤ 2 | 2.6–2.8% | Poisson: 4.1–4.5%. *Both* tails are thin | H |
| Exactly 9 vs exactly 10 | 10.4% vs 2.7% | The OT/SO parity sawtooth | H |
| Final margin ≥ 5 | 5.5–6.5% per season | Skellam (independent Poisson): 7.1% | H |
| Final margin ≥ 3 | 39–42% | Skellam 30.7%. Empty-net goals inflate this | H |
| Game reaches 5–0 at any point | 4.2% | — | H |
| Some team leads by ≥5 at any point | 8.1% | — | H |
| Team with a 2-goal lead loses | 13.3% (425/3,195 games with a 2-goal lead) | — | H |
| Team with a 3-goal lead loses | **3.6%** (70/1,960) | Yost/TSN: down 3 with 20 min left, about 2% win | H |
| Games to OT / SO | 22.1% (15.0% OT + 7.1% SO) | sim v1 matches | H |
| Empty-net goals per game | 0.376 (ours) | Daily Faceoff: 7% of all goals in 2024-25, vs 2.4% in 2005-06. Superstars get most of them | H |

- **Score effects.** Leading teams sitting back drive score effects more than trailing teams pushing. In P3, offence falls 10–30% for leaders, sharpest with two-goal leads. Teams that just scored show ~5% better output. (McCurdy, https://hockeyviz.com/txt/scoreSeq; https://hockeyviz.com/static/pdf/cbjhac20.pdf) [LIT, H]
- **Scoring first.** The team that scores first wins about 67%. 2–0 → 80.4%. 1–1 → 50%. Scoring first has no special value beyond being a goal. (Hockey-Graphs, https://hockey-graphs.com/2016/11/29/behind-the-numbers-scoring-first-and-conditional-probability/) [LIT, H]
- **Goalie pull.**
  - Asness & Brown (2018 SSRN, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3132563; summary at https://www.chicagobooth.edu/review/when-hockey-teams-and-money-managers-should-go-broke): the optimal pull is **5:40** left when down 1, **11:40** down 2, **17:40** down 3.
  - Per 10 s with the net empty: +1.18% to score for the pulling team vs +2.54% for the opponent.
  - Beaudoin & Swartz 2010 (*Am. Stat.* 64:197–204, https://www.semanticscholar.org/paper/Strategies-for-Pulling-the-Goalie-in-Hockey-Beaudoin-Swartz/323ececffef50b8b520c379b46f6a594fedceede) also find earlier pulls are optimal.
  - Coaches are pulling earlier over time (Daily Faceoff: average pull ~30 s earlier; extra-attacker goals on pace for 240 vs 138 a decade ago).
  - **Tail relevance:** earlier pulls fatten *both* the ±2/±3 margin mass and the late "total +1/+2" mass in games within one or two goals. This is a drift that ladders calibrated on old seasons will miss. [LIT, H]
- **Do markets price these tails?**
  - Woodland & Woodland found a persistent **under bias** in 1990s NHL totals: unders won 54.2% across 5,000+ games, strongest at totals ≥ 5.5 (https://www.researchgate.net/publication/227410468_Market_Efficiency_and_the_NHL_totals_betting_market_Is_there_an_under_bias).
  - Traugutt (2018 dissertation, https://digscholarship.unco.edu/dissertations/502/) found the main-line totals market "substantially efficient", with one marginal strategy.
  - **No published study of NHL *alt* totals, alt puck lines or team-total ladders exists that we could find.** This is open ground. See H-T1 to H-T3.
- **Our own SGO data limitation.**
  - The SGO consensus `close_fair_line` on game-total and puck-line rows is often an *in-game* line: lines of 0.5 or 12.5 at ~50% implied appear.
  - Alt rows (`alt = true`) carry no per-book open/close.
  - **So alt-ladder calibration cannot be done historically. Use `data/raw/snapshots/`** (started 2026-09-30) and per-book main-line `book_close_*` from 2026-01-17 to anchor λ.

### 2.3 First goal scorer (FGS) and anytime goal (AG) pricing

**Settlement rules** (DraftKings MA house rules, 2024-08-01, §Hockey, https://massgaming.com/wp-content/uploads/DraftKings-House-Rules-8.1.24.pdf) [LIT, H]:
- *"First/Last/Anytime Goalscorer – Player must be dressed/active for bets to stand… Own goals are ignored for settlement purposes and if only own goals are scored in a game, then 'No Goalscorer' will be settled as the winner. Any stats accrued in shootouts do not count."*
- Markets include OT and SO unless stated otherwise. *"In the event of the game being decided by a penalty shootout, one goal will be added to the winning team's score and the game total."* Period markets exclude OT.
- The NHL credits own goals to the last attacking player who touched the puck, so true "own goals" barely exist in NHL data. "No Goalscorer" happens only in 0–0 games decided in the shootout: **0.08% of games** in 2023-26 [OURS].
- FanDuel (search snippet): props void if the player records no TOI; shootout goals don't count [UNVERIFIED primary text].

**Pricing structure** [OURS, 539 games, per-book closes, players matched to boxscores so voids are excluded]:
- Books list ~29–32 skaters per game. The sum of implied probabilities over listed players is **1.15–1.24 at mainstream books** and **1.54 at BetRivers/BallyBet**.
- Hit/implied falls monotonically with price:
  - 0.73–0.76 at +900 to +1,600;
  - 0.65 at +2,200 to +3,000;
  - 0.60 at +3,000 to +4,500;
  - 0.58 at +4,500 to +10,000.
- Defensemen: 0.56 overall. Forwards: 0.71.
- **By role at best price across books** (the most favourable executable case):

| Role (trailing-10 TOI rank) | n | Hit | Best-price implied | ROI |
|---|---|---|---|---|
| F rank 1–3 | 3,223 | 5.09% | 6.42% | −19% |
| **F rank 4–9** | 5,787 | 3.85% | 3.98% | **−5%** |
| F rank 10+ (4th line) | 2,417 | 1.32% | 2.28% | **−38%** |
| D rank 1–2 | 2,077 | 2.02% | 2.35% | −11% |
| D rank 3–4 | 1,988 | 0.86% | 1.51% | −44% |
| D rank 5+ | 1,794 | 0.72% | 1.16% | −28% |

- **Base rates from 3 seasons of pbp** (first goals per player-game): F 1–3 5.6%, F 4–6 4.1%, F 7–9 2.8%, F 10+ 1.8%, D 1–2 1.9%, D 3–4 0.96%, D 5+ 0.79%.
  - Against these base rates, the best-price markup is about **+16% for top forwards** and **+27% for 4th-liners**. It is about **+47% for bottom-pair D**.
  - Our 2026 sample hit rate for 4th-liners (1.3%) is below the 3-season 1.8%, so part of the −38% is sample noise. The structural markup is still ≥25%.
- **Anytime goal** (same sample) shows the same shape at best price: F_bottom −28%, D_bottom −21%, D_mid −13%, D_top −7%, F_top −2%, **F_mid +2.7%**.
  - Prior finding: the Pinnacle AG two-way close is calibrated (findings 2026-09-30).
  - Simulator v1: market AG prices on a team summed to more goals than the team total.

**Literature on scorer markets and the favourite–longshot bias (FLB):**
- **Cain, Law & Peel 2003**, *Bull. Econ. Res.* 55(3) (https://onlinelibrary.wiley.com/doi/abs/10.1111/1467-8586.00174):
  - FLB exists across bookmaker sports markets, including UK football scores and goalscorer-type markets.
  - Margins rise with the number of competitors (Shin insider model).
  - [LIT, H for existence; the exact goalscorer numbers were not retrieved]
- **"Expected loss on first goalscorer at UK bookmakers, 2014 World Cup ≈ 48%** (vs 5% match odds, 28% correct score)." This appeared only in a search snippet tied to an *Applied Economics* 2025 article (https://www.tandfonline.com/doi/full/10.1080/00036846.2025.2507979, paywalled/403). **[UNVERIFIED]**
- Practitioner sources (caanberry, https://caanberry.com/first-vs-anytime-goalscorer/):
  - FGS carries ~6% more margin than AG on the same player.
  - Elite EPL strikers score in ~42% of matches but first in only ~11%.
  - [LIT-practitioner, M]
- **Buchdahl / football-data** (https://www.football-data.co.uk/blog/favourite_longshot_bias_revisited.php):
  - Randomly betting football odds < 1.50 is about break-even; odds > 5.00 lose up to ~20%.
  - Soft books shorten favourites ~3% and longshots ~12%.
  - Pinnacle and Betfair are close to true probabilities.
  - [LIT, H]
- **Snowberg & Wolfers 2010**, *JPE* 118(4) (https://www.nber.org/papers/w15923): FLB is driven by *probability misperception* (overweighting small probabilities), not risk-love. It therefore persists wherever recreational bettors set demand. [LIT, H]
- **Green, Lee & Rothschild 2018** (https://jacobslevycenter.wharton.upenn.edu/wp-content/uploads/2018/08/The-Favorite-Longshot-Midas.pdf):
  - At US tracks, a 1/1 favourite returns $0.85 and a 30/1 longshot $0.63.
  - The bias is partly *manufactured* by the market maker's displayed predictions.
  - [LIT, H]
- **DataGolf** (https://datagolf.com/fav-longshot-not-a-bias): with *equal absolute* margin per side (as at sharp books), longshot ROI is *mechanically* worse. A 70/30 market at +1% margin per side gives −1.23% on the favourite vs −4.76% on the longshot. Even "fair" sharp markets punish longshot ROI per dollar. [LIT, H]
- **Pinnacle** (https://www.pinnacle.com/betting-resources/en/betting-strategy/what-is-the-favourite-longshot-bias/vun2u32r85ppf4yp): longshots absorb a disproportionate share of the margin. In horse racing, sub-evens runners lost ~7% and 40/1+ runners lost >40%. [LIT, H]
- **Reverse bias in NHL moneylines.** Woodland & Woodland (*Southern Econ. J.* 2001, https://www.researchgate.net/publication/227577382) found NHL underdogs underbet in 1990–96. Profitable underdog betting existed early, then disappeared as the market converged. [LIT, M; abstract-level only]

**Opening shift and deployment** [OURS, H]:
- Opening-shift skaters score 32% of first goals, which is about proportional.
- First-goal shares per role vs all-goal shares: F 10+ is 1.09×, top-3 F 0.94×.
- 76% of first goals are 5v5 (situationCode 1551). About 21% come on the PP or PK (1451/1541).
- PP1 is the main structural FGS lever: PP share of first goals.
- The **home coach's last change** affects matchups, not who scores first. Its effect is mostly captured by P1 TOI share.

### 2.4 Player-level variance

| Finding | Numbers | Source | Conf. |
|---|---|---|---|
| SOG dispersion is not a stable trait | Per-player-season var/mean (≥60 GP, mean ≥1 SOG/game): mean 1.09, SD 0.186. A Poisson null with the same means/n gives SD 0.186. Year-over-year r = **0.06** (n = 920) | [OURS] `nhl_skater_game` 2022-26 | H |
| Pooled SOG NB α ≈ 0.045 (var/mean 1.05–1.13) | — | digest 03, PLAN v4 | H |
| Player goal "hot hand" | Leave-out test: ≥2 goals above expectation in the last 5 → 1.05–1.07× leave-out rate. ≥1 below → 0.90×. Logistic +0.078 log-odds per goal in the last 5 (SE 0.006) | [OURS] | M (probably role/TOI) |
| Vesper (2011-12): an *adverse* hot hand in NHL shooting (rushing shots after scoring) | — | cited in Frontiers 2023 review, https://www.frontiersin.org/journals/sports-and-active-living/articles/10.3389/fspor.2023.1241014/full | L [secondary citation] |
| Miller & Sanjurjo correction: classic hot-hand tests are biased toward zero; corrected, basketball shows a modest hot hand | — | via the Frontiers 2023 review (above) | M |
| No goalie hot hand; good recent saving slightly *lowers* next-shot save probability | 48,431 playoff shots, 93 goalies, 2008–16 | Ding, Cribben, Ingolfsson & Tran 2025, https://arxiv.org/abs/2102.09689 | H |
| No team carry-over after a blowout (6+ goal margin) | 285 games, 2005–19 | Chachad, Pradhan & Medina, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10800907/ | M |
| Recent form (L5) predicts next-game SOG *worse* than long memory | corr 0.42 vs 0.45 | findings 2026-09-30 | H |
| PP share is very predictable (r = 0.87); absolute PP minutes are noisy (r = 0.70) because PP opportunities are random | — | digest 03 | H |

**Implication for "ceiling" betting:**
- A player's upside comes from *opportunity* tails, not shot-making tails:
  - extra PP time from a penalty-heavy game;
  - a promotion when a linemate is injured;
  - OT 3-on-3;
  - empty-net deployment for stars.
- These are mostly game-level states. Ceiling props should be priced from the simulator conditional on game state, not from a fatter per-player distribution.

### 2.5 Practical frameworks for betting variance

**Why median / most-likely thinking fails, and what replaces it:**
- The question is never "what is the most likely outcome". It is **"at what price is this outcome offered vs its probability"**.
- Tails have *less* liquidity, *more* margin and *more* model error. All three cut against the bettor.
- The edge has to exceed: margin, plus model error (which is much larger in relative terms at p = 0.02), plus a limits/variance cost.
- That is why PLAN v4 already sets EV floors of 8–12% beyond +400 (digest 02).

**DFS GPP → betting mapping** (and where it breaks):
- **What DFS research says about top-heavy payouts:** Hunter, Vielma & Zaman (https://arxiv.org/abs/1604.01455, with hockey code at https://github.com/zlisto/Daily-Fantasy-Hockey-for-DraftKings) and Haugh & Singal (*Mgmt Sci* 2021, https://pubsonline.informs.org/doi/10.1287/mnsc.2019.3528) find that in top-heavy contests you should:
  - maximize mean subject to *high variance*;
  - use positive within-lineup correlation (line stacks);
  - limit overlap across entries;
  - model opponents' ownership (Dirichlet-multinomial).
  - Hunter et al. placed top-10 "multiple times in hockey and baseball contests with thousands of entries". [LIT, H]
- **Stacking practice:** first-line stacks are crowded, so lower-owned second-line or PP stacks give leverage (Stokastic, https://www.stokastic.com/articles/nhl-dfs/nhl-dfs-beginner-guide). [LIT-practitioner, M]
- **Where it breaks:** fixed-odds betting pays a *price*, not a *rank*. There is no ownership leverage, except that the *price* already embeds public demand. In betting, "contrarian" means **taking the side the public underbets**: unders, "no", alt unders, unpopular depth *unders*.
  - Rufus Peabody's prop operation mostly bets **unders**, because "we like to bet overs" is the public instinct. He advises betting unders late, after public over money has pushed lines (The Ringer, https://www.theringer.com/2022/9/28/23375387/gamblers-super-bowl-episode-3-rufus-peabody).
  - Our own finding: SOG overs are overstated by 1.3–5 points at every book (findings 2026-09-30).
- **Where it maps directly:**
  1. **Correlated parlays and SGPs** behave like DFS stacks. The payoff is convex in a shared game state (e.g., team scores 5+ → its top line all get points). Value exists only if the book under-models the correlation. SGP holds are 15–25% vs 4–5% for singles (Wizard of Odds, https://wizardofodds.com/article/same-game-parlays-the-mathematics-of-correlation/). Pinnacle multiplies parlay legs with no correlation adjustment [practitioner, M].
  2. **Prediction markets and parimutuel-like venues** (Kalshi, Polymarket) are where crowd FLB is strongest. They are worth monitoring for *no*-side value on longshots. Our Kalshi FGS sample shows longshot *yes* at a −64% blanket ROI.

**Kelly for longshots:**
- f* = (bp − q)/b. For a +4,000 longshot with a true p = 3% (2.5-point edge over 2.44% implied): f* ≈ 0.6% of bankroll at full Kelly, ≈ 0.15% at quarter Kelly.
- Overestimating p by 1 point (3% vs a true 2%) flips the bet to −EV. Estimation error dominates at small p.
- Thorp 1997/2006 (https://gwern.net/doc/statistics/decision/2006-thorp.pdf) and Chu, Wu & Swartz on modified Kelly (https://www.sfu.ca/~tswartz/papers/kelly.pdf) both argue for fractional Kelly.
- Wizard of Odds (https://wizardofodds.com/article/variance-and-bankroll-management-for-player-props/): a 3-point overestimate of p can make you bet 5–10× too much.
- A practitioner claim (search snippet): full Kelly on longshots has a 50% chance of a 50% drawdown. **[UNVERIFIED source; mathematically standard for full Kelly in general.]**
- Our PLAN v4 settings already fit this: 0.5% stake beyond +500, a lottery bucket of ≈0.5% per night, quarter Kelly.
- **Variance budget:** at +2,000 and p = 5%, the SD of ROI over N bets is ≈ √(p(1−p))·21/N^0.5 ≈ 4.6/√N. For example, ROI SD is ±21% at N = 500 and ±10% at N = 2,000.
  - So **a +5% edge on FGS longshots cannot be verified by results for thousands of bets.**
  - Validate tail edges with CLV and calibration curves (hit/implied by bucket over all quotes), not with P&L.

---

## 3. Testable hypotheses with exact data recipes

Common building blocks (DuckDB):
```sql
-- goals with order (exclude shootout)
create view p as select * from read_parquet('data/curated/nhl_pbp/**/*.parquet', hive_partitioning=true);
create view g as select * from 'data/curated/nhl_games.parquet' where game_type=2;
create table gl as select p.game_id, sortOrder, period_number, scoringPlayerId::bigint pid, eventOwnerTeamId::bigint team,
  situationCode sc, cast(homeScore as int) hs, cast(awayScore as int) as_,
  cast(split_part(timeInPeriod,':',1) as int)*60+cast(split_part(timeInPeriod,':',2) as int) t,
  row_number() over (partition by p.game_id order by sortOrder) k
from p join g using(game_id) where typeDescKey='goal' and period_periodType<>'SO';
-- pre-game role: trailing-10 TOI rank within team × (F/D)
create table skr as select s.*, g.date, g.season,
  avg(toi_sec) over (partition by playerId, g.season order by g.date rows between 10 preceding and 1 preceding) toi_l10
from 'data/curated/nhl_skater_game.parquet' s join g using(game_id);
create table skr2 as select *, rank() over (partition by game_id, team, (position='D') order by toi_l10 desc nulls last) rr from skr;
-- per-book closes for player markets (FGS: stat='firstToScore'; AG: stat='points' and bt='yn')
select o.book, m.game_id, mp.player_id, o.book_close_odds
from read_parquet('data/curated/sgo_odds/*.parquet') o
join 'data/curated/map_sgo_event.parquet' m using(eventID)
join 'data/curated/map_sgo_player.parquet' mp on mp.sgo_player=o.entity
where o.stat='firstToScore' and o.side='yes' and o.book_close_odds is not null and m.game_type=2;
```

| # | Hypothesis | Recipe | Success criterion | Status |
|---|---|---|---|---|
| **H-T1** | Alt game-total *overs* at 9.5+ and alt *unders* at 4.5− are overpriced vs empirical/sim tails | From `data/raw/snapshots/` take the last pregame quote per book × rung (game total, `alt = true`). De-vig per rung using the two-way pair, or the pinnacle main line plus our sim for one-way rungs. Compare to the simulator (65k sims, OT/SO explicit) and to the empirical conditional distribution: bucket games by closing λ (Poisson λ solved from the de-vigged main total at per-book close); for each bucket compute the empirical P(T ≥ k). | Over 9.5/10.5 implied > sim by ≥2 points on average; bet the unders at ≥ EV floor; CLV > 0 over ≥300 rungs | Prospective (needs snapshots). Pre-evidence: Poisson-from-close overstates 10+ by 4.7 points [OURS] |
| **H-T2** | Ladders are smooth across the odd/even sawtooth: Over 8.5 → 9.5 → 10.5 price gaps are too small at 9.5 | For each book × game, compute the implied-probability gap between adjacent rungs. Compare to the sim gap and to empirical P(T = 9) ≈ 10.4%, P(T = 10) ≈ 2.7% (conditioned on λ bucket) | Book gap(8.5 → 9.5) < sim gap by ≥2 points | Prospective |
| **H-T3** | Alt puck lines: ±2.5 rich because of the empty-net mass; −3.5/−4.5 overs overpriced (5+ margins thinner than Skellam) | Snapshot alt `sp` rungs vs the sim. Historical check: the empirical margin distribution conditional on the closing moneyline bucket (from `book_close_odds`, `bt = 'ml'`). Use pbp max-lead tables for "lead by X at any time" markets if offered | −3.5/−4.5 implied exceeds sim by ≥1.5 points | Prospective; empirical margins done [OURS] |
| **H-T4** | Team-total 6.5+ overs overpriced; team-total 4.5 overs for the likely OT winner mispriced by the SO +1 | `stat = 'points'`, entity home/away, `bt = 'ou'`, per-book `book_close_line` / `odds` (main lines 2026-01+) plus snapshot alt rungs. Empirical: team goals incl. SO +1 from `nhl_games` vs Poisson-from-close (done: 7+ 3.1% vs 4.9%) | Same as H-T1 | Partly done (main lines) |
| **H-T5** | FGS/AG: 4th-line F and bottom-4 D are overpriced by ≥25% even at the best price; middle-six F are near fair | Join per-book closes to `skr2`. Role = rr (F ≤ 3 / 4–9 / 10+; D ≤ 2 / 3–4 / 5+). Outcome FGS = `gl.k = 1` scorer; AG = `goals > 0`. Report hit/implied with Wilson CIs by role × book × price bucket, at per-book and best price. Re-run each month to watch stability | CI of hit/implied excludes 1 for F_bottom/D; F_mid CI includes ≥0.95 | **Done on 539 games** (§2.3); extend to 2026-27 |
| **H-T6** | Structural FGS model (P(team scores first) × player share of P1 xG/TOI incl. PP1) beats books on F_mid and finds the rare depth value (promotions) | P(team first) from the sim. Player share = EWMA P1 TOI share × ixG/60 by strength (shifts × pbp situationCode), shrunk. Compare log-loss vs de-vigged best-book FGS across all listed players (multinomial incl. "other/none") | Log-loss better than de-vigged market; positive CLV on F_mid with edge ≥ 8% | To build |
| **H-T7** | Opening shift / home last change has no first-goal effect beyond P1 TOI share | Shifts: `period = 1 and startTime_sec = 0` for the opening skaters (done: 32% of FGs). Logistic FG ~ log(P1 TOI share) + opening_shift + home + PP1 | opening_shift coefficient ≈ 0 | Done descriptively [OURS] |
| **H-T8** | Player SOG/goal dispersion heterogeneity is noise → a single NB α is adequate for alt SOG ladders | Per player-season DI vs a parametric-bootstrap null; year-over-year r. Then fit NB α by player group (F/D, PP1/no) with a likelihood-ratio test | YoY r < 0.15; group α differences < 0.02 | Done for SOG (r = 0.06) [OURS]; do group α |
| **H-T9** | Goal "hot hand" disappears after controlling for TOI and PP share changes | Regress goals(t) on leave-out season rate, EWMA TOI, EWMA PP share, and goals in the last 5 (Poisson GLM, player-season clusters) | Last-5 coefficient not significant once TOI/PP are included | To run |
| **H-T10** | Empty-net drift: earlier pulls are raising P(margin = 2/3) and late total +1, by season | pbp `situationCode` with the goalie-out flag (first digit 0 / fourth digit 0) by season: pull time distribution, EN goals per game, P(margin ≥ 3 \| 1-goal game at 3:00 left) | A monotone trend → refit the sim EN hazard on the most recent season only | To run |
| **H-T11** | Longshot *no* sides on prediction markets (Kalshi) are +EV | `book = 'kalshi'`, `side = 'no'` closes for FGS and other yes/no markets | ROI > 0 after fees over ≥500 contracts | n = 82 so far (+4.4%), far too thin |
| **H-T12** | SGP mispricing: books under-model OT/SO parity and empty-net correlations (e.g., team ML + game Over 5.5; FGS-team + ML) | Log SGP quotes (DK/FD) vs the sim joint probability; ≥300 quotes before any bet (PLAN v4 B4) | Mean (sim − implied) > hold on a specific combo family | Prospective |

**Statistical-power warning.** At p ≈ 2–5% and fair odds of +2,000–+5,000, the ROI SD is ±4.5/√N to ±7/√N. A 10% edge needs roughly N ≈ 2,000–5,000 independent bets to reach t = 2. **Judge tail strategies by calibration curves on all quotes (≈100k per season) and by CLV, never by realized P&L.**

---

## 4. Open questions

1. **How do the books actually construct alt ladders?** Smooth Poisson/NB around the main total, or a simulator with OT/SO and empty net? The answer decides whether H-T1/H-T2 are real. It needs ≥4 weeks of snapshots.
2. **Is the 2026 FGS 4th-line hit rate (1.3%) an outlier against the 3-season base rate (1.8%)?** Re-test H-T5 on 2026-27 with pre-registered buckets.
3. **FanDuel / BetMGM / Caesars primary rule text** for FGS (dressed vs TOI > 0, "no goalscorer" handling). DK's text is confirmed. The others are from snippets.
4. **Do any books offer "team to lead by 5", "race to 5" or "highest-scoring period" markets?** These are tail markets where our sim has a structural edge (DK lists "Race to Goals (2,3,4,5)" and "Winning Margin"). Are they in SGO? (`stat` inventory: no.) We'd need snapshot capture.
5. **The early-season scoring environment.** League save % reportedly dipped to a three-decade low (ESPN, https://www.espn.com/nhl/story/_/id/48487239/nhl-goalies-save-percentage-dips-lowest-point-three-decades; we could not load the article, numbers [UNVERIFIED]). If scoring rises, does dispersion change, and do books lag on the 10+ tail?
6. **Pinnacle's correlation-free parlay policy:** is it current, and what are the limits? [practitioner claim, unverified]
7. **Woodland-style reverse FLB on modern NHL moneylines and puck lines.** Testable now with 1,078 games of per-book ML closes. Not yet run.
8. **The expected-loss figure for FGS markets** (World Cup 48% claim) and any hockey-specific academic study of scorer markets. We found none. Our 539-game study may be the first hockey FGS calibration.

---

### Sources consulted (distinct)
Teeter (cteeter.ca) · Birnbaum (philbirnbaum.com) · Lopez, Matthews & Baumer (arXiv 1701.05976) · Merritt & Clauset (arXiv 1310.4461) · Clauset, Kogan & Redner (arXiv 1503.03509) · Thomas 2007 JQAS (hockeyanalytics.com) · McCurdy/hockeyviz (scoreSeq, cbjhac20) · Hockey-Graphs scoring first · Ötting et al., Gambling on Momentum (arXiv 2211.06052) · Chachad et al. (PMC10800907) · Ding et al. (arXiv 2102.09689) · Frontiers 2023 hot-hand review · JFresh percentage luck · Davis & Robberechts (arXiv 2401.09940) · Washburn NPS (snippet) · Asness & Brown (SSRN 3132563 / Chicago Booth Review) · Beaudoin & Swartz 2010 · Daily Faceoff empty-net articles · Yost/TSN three-goal comebacks · Woodland & Woodland (NHL longshots; NHL totals under bias) · Traugutt 2018 dissertation · Cain, Law & Peel 2003 · Snowberg & Wolfers 2010 · Green, Lee & Rothschild 2018 · DataGolf FLB · football-data/Buchdahl FLB revisited · Pinnacle FLB articles · caanberry FGS vs AG · DraftKings house rules (MA, 2024-08) · FanDuel rules (snippet) · Hunter, Vielma & Zaman (arXiv 1604.01455) · Haugh & Singal (Mgmt Sci) · Stokastic NHL DFS · Thorp Kelly · Chu, Wu & Swartz modified Kelly · Wizard of Odds (props variance; SGP correlation) · The Ringer / Rufus Peabody.
