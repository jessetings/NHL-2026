# PLAN v4: research integration and next builds (2026-09-30, night)

Sources:
- `docs/research/01_simulation_and_modeling.md` (~60 sources)
- `docs/research/02_markets_ml_finance.md` (~45)
- `docs/research/03_advanced_stats_matchups.md` (~40)
- `docs/findings/2026-09-30_market_efficiency.md` (our own 161k-contract study)

## A. Decisions already applied in code

| Area | Setting | Evidence |
|---|---|---|
| SOG distribution | NB2, α = 0.045 | Our 177k player-games (var/mean 1.05–1.08); digest 03: 1.13 |
| SOG-over bias | −1.3 / −2.2 / −3.7 / −5 pts at 2+/3+/4+/5+ | Our per-book closes, all books |
| Assists-over bias | −1.2 pts | Our DK/Pinnacle closes |
| Finishing | Forwards: xG × (G + 64)/(xG + 64); defensemen: xG only | Digest 01 §6, digest 03 §2 |
| Empty-net goals | No extra multiplier (already inside all-situation rates) | Digest 01 §3 |
| Opponent SOG effect | (opponent SOG-allowed ratio)^0.75 | Digest 03 §5 |
| Home | SOG ×1.037; goals/points ×1.07 (home vs away) | Digest 03 §5 |
| Back-to-back | Own: SOG −3%, goals/points −6.5%. Opponent: +2.6% / +4% | Digest 03 §5–6 |
| EV floor by odds | 2% (≤ −200), 3% (≤ +150), 5% (≤ +400), 8% (≤ +1000), 12% beyond | Digest 02 §5 (favourite–longshot bias) |
| Stakes | 1.5% per bet (0.5% longer than +500), 4% per game, lottery ≈0.5%/night; quarter Kelly | Digest 02 §8–9 |
| Public-over tax | Inspection crack from blanket side ROI at close (overs −6% to −15%) | Our study |
| Officials, coaches, scratches | Now parsed for all 4,197 games | Digest 03 bug report |
| Shift duplicates | Deduplicated (5.6k rows) | Digest 03 bug report |

## B. Next builds (in order)

1. **TOI and PP projection v2.** EWMA with half-life 5 (r = 0.84 on TOI, 0.87 on PP share). PP minutes = PP share × expected team PP time (team penalties drawn × opponent penalties taken). Early-season blend: the prior season is worth ~5 games for TOI, ~20 for SOG, ~33 for points, ~40 for goals; current-season SOG weight is 0.19 / 0.32 / 0.51 / 0.70 at 5 / 10 / 20 / 40 games. Then an extra 5–15% shrink toward role.
2. **Goalie start model.** The night-one starter repeats on night two of a back-to-back only 7.8% of the time. Logistic on season start share, recent starts and back-to-back (~70% accuracy). Goalie quality moves team goals only ~3% per SD, so starter identity matters more than form.
3. **Event-driven game simulator** (digest 01 §1–5, 8–10):
   - Time to the next event depends on game state.
   - Score effects: leader's expected goals −10–15%.
   - P2 long-change bump: +16–17%.
   - Separate pulled-goalie / empty-net hazard: ~6.5/60 for the attacking team, 12–19/60 against; refit on 2023–26 pull times.
   - OT 3-on-3 with recent-season rates; shootout ≈ coin flip. OT goals settle props, shootout goals do not.
   - A small shared pace factor, tuned so totals have var/mean ≈ 1.0 and team goal correlation ≈ −0.1.
   - Shot allocation by deployment shares; xG marks resampled from MoneyPuck (per unblocked attempt). Goals are Bernoulli marks; assists come from on-ice teammates; saves = opponent SOG − goals.
   - 65,536 sims per game (131,072 for SGPs and deep alt rungs), with common random numbers keyed by game and model version. Player props computed in closed form from team paths where possible.
   - First goal scorer is a race on time-varying rates, dominated by P1 deployment (first line, PP1).
4. **Validation of the simulator** before any same-game-parlay use: reproduce empirical same-game correlations, calibration against ≥300 logged SGP quotes, and exact team-to-player reconciliation every draw.
5. **H1/H2 prospective studies** from `data/raw/snapshots/`: alt-ladder pricing vs our NB2 tails, and DK/FD lag vs Pinnacle. Five-minute cadence to start; consider one-minute near puck drop.
6. **Timing tests.** Our model adds little at the close. Test whether open or early prices carry larger edges (snapshots needed).
7. **CLV tracking** on every bet from day one; scale-up gate at t > 3 over ≥500 bets (digest 02 §7).
8. **Account-limit hygiene** (digest 02 §10): rank by EV × stake, skip thin edges, log requested vs accepted stakes. No multi-accounting.

## C. Open questions (from the digests)
- Pull-time model form, and whether empty-net goals against run 12 or 19 per 60.
- Whether a shared pace factor is needed at all.
- Each book's first-goal-scorer settlement rules (OT, own goals).
- Which book's close is sharpest per NHL prop market (the CLV benchmark).
- Per-bet CLV SD on NHL props (sets the sample needed).
- Limit thresholds at DK/FD for NHL props.
