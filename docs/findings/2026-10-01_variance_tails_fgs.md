# Findings — Variance, tails and first goal scorer (2026-10-01)

Data: 3,941 games (2023–26 regular season, play-by-play + shifts); 39,627 DK/FD first-goal-scorer prices with outcomes (2024–26, pregame); DK/FD anytime-goal prices; simulator v1.
Scripts are inline in the session, and the history is saved to `data/curated/market/fgs_history.parquet`.

## 1. First-goal-scorer markets carry a severe favourite–longshot bias
| DK/FD price | Bets | Hit | Implied | Actual/implied | ROI |
|---|---|---|---|---|---|
| +800–1200 | 2,790 | 6.2% | 8.6% | 0.72 | −28% |
| +1200–1800 | 5,486 | 4.9% | 6.1% | 0.81 | −20% |
| +1800–2500 | 7,449 | 3.2% | 4.4% | 0.74 | −27% |
| +2500–4000 | 9,630 | 1.9% | 3.0% | 0.64 | −37% |
| **+4000+** | 14,076 | 0.8% | 1.6% | **0.51** | **−47%** |

A longshot first scorer (e.g. a 4th-liner at +4000) hits about **half** as often as priced. "It happened, so there must have been value" is outcome bias: the book wins the other 99 times.

## 2. Who actually scores first
First goals are 82.6% in P1. They come at even strength, with no empty nets and fewer power plays. So the share of first goals ≠ the share of all goals:

| Forward tier (game TOI rank) | Share of all goals | Share of first goals | Ratio |
|---|---|---|---|
| Top-3 TOI | 34.3% | 32.7% | 0.95 |
| 4–6 | 25.3% | 25.5% | 1.01 |
| 7–9 | 16.7% | 17.4% | 1.04 |
| **10–12** | 9.1% | 9.9% | **1.09** |
| Defense | 14.6% | 14.5% | 0.99 |

Depth forwards score first ~9% more often than their goal share; stars ~5% less.

## 3. The opening-shift angle (the only near-fair first-goal-scorer segment)
| Segment (DK/FD, pregame prices) | Bets | ROI | Actual/implied |
|---|---|---|---|
| Forwards NOT on the opening shift | 19,872 | −36% | 0.67 |
| **Forwards on the opening shift** | 6,128 | **−10.5%** | **0.87** |
| Opening forwards at +1800–2500 | 1,947 | **−0.6%** | 0.99 |
| Opening forwards at +1200–1800 | 1,835 | −13.6% | 0.87 |
| Defensemen NOT opening | 9,512 | −48% | 0.55 |

- **Deployability:** starting lineups are not in the NHL API pregame. They are announced by teams and broadcasts minutes before puck drop.
- A history-only predictor (opened ≥60% of the last 5 games) is just 47% accurate. ROI only improves from −36% to −30%.
- So the angle needs the actual starting lineup, i.e. a human check at puck drop.
- **With a 50% profit boost**, an opening-shift forward at +1800–2500 (≈ fair at true prices) is ≈ +45–50% EV. This is the best use of first-goal-scorer boosts we have found.
- **Without** a boost, first-goal-scorer bets remain negative EV.

## 4. Anytime goal by price (DK/FD, pregame)
| Price | Bets | ROI | Actual/implied |
|---|---|---|---|
| ≤ +150 (stars) | 527 | −1.4% | 0.98 |
| +150–250 | 2,304 | −10.0% | 0.90 |
| +250–350 | 1,190 | −14.8% | 0.85 |
| +350–500 | 226 | −1.1% | 0.99 (small n) |

Star AG favourites are near fair; mid-tier AG is taxed.

## 5. Game-level tails: the simulator reproduces them
| | P(total ≥ 9) | P(total ≥ 10) | P(total ≤ 3) | P(margin ≥ 4) | P(margin ≥ 5) | Shutout |
|---|---|---|---|---|---|---|
| Empirical 2023–26 | 17.5% | 7.4% | 13.3% | 16.6% | 5.9% | 10.4% |
| Sim v1 (league avg) | 18.9% | 8.3% | 12.0% | 16.9% | 7.5% | 9.2% |

The sim slightly overstates blowouts (5+ margins); this is a to-do in sim v2. Historical **alt-total / alt-puck-line prices have no per-book close**, so tail pricing (9+ goal alt overs, −2.5/−3.5 puck lines, team totals 5+) can only be tested **prospectively** from the snapshot archive. These are the next tail hypotheses to test.

## 6. What "betting the tails" means operationally
- The market prices the whole distribution, not just the median. Tails are usually priced *worse* for the bettor (longshot bias), not better.
- Edges in tails come from information the price ignores:
  - opening shift / starting lineup;
  - correlation books underprice (SGP);
  - boosts that remove the longshot tax;
  - alt rungs priced off a wrong distribution (H1, prospective).

## 7. Formal test of the opening-shift effect (reconciles with research digest 04)
Digest 04 found that opening-shift skaters score first-goal share ≈ their share of dressed skaters. Our §2 data agrees: first goals per goal are 0.162 for openers vs 0.164 for others. Starting does **not** raise a player's first-goal propensity relative to his scoring rate. The question that matters for betting is whether **the price** reflects it:
- **Logistic regression** (all DK/FD FGS bets 2023-26 with shift data), win ~ logit(implied) + opening + D:
  - opening **+0.212 (SE 0.070)**, t ≈ 3.0;
  - defenseman −0.16 (SE 0.11);
  - logit-implied slope 1.11 (>1 means the longshot bias is confirmed).
- Adding a **history-based** predicted-opener flag: −0.06 (SE 0.09). It adds nothing, so the edge needs the **confirmed** starting lineup.
- **Game-clustered bootstrap**, opening F vs non-opening F ROI: **+25.5 pts, 95% CI [+7.6, +44.0]**, 1,275 games.
- **Conclusion:** books price first goal scorer without regard to who takes the opening faceoff.
  - Confirmed opening forwards outperform their price relative to other players, but are still **≈ −10% ROI blanket**.
  - **Actionable only with a profit boost or the best price in the +1800–2500 band, after confirming lineups at puck drop.**
  - Digest 04 independently finds 4th-line and bottom-pair D scorer longshots the most overpriced (FGS −38% / −44%; AG −28% / −21% at the best of 13 books).
