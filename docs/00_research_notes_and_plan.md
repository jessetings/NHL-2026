# NHL 2026 — Research Notes & Plan for Sept 30, 2026 Slate

Source docs (user-supplied, cursory research):
- **Ledger**: *NHL 2026 Master Research and Recommendation Ledger* (12 pp)
- **Blueprint**: *NHL 2026: Review Findings and Implementation Blueprint* (14 pp)

Books: **DraftKings, FanDuel**. Subscription inputs: **SportsPredictApp, Action Network** (user supplies screenshots or exports).

---

## 1. Tonight's slate (ET)

| Game | Time | FD ML snapshot | Total snapshot | Goalies (projected) |
|---|---|---|---|---|
| PIT @ PHI | 7:30 | PHI -146 / PIT +122 (DK -142/+120) | 6.5, U -138 (some books 6) | Silovs (PIT, .887 LY) vs Vladar (PHI, .906 LY) |
| NYI @ TOR | 7:30 | TOR -122 / NYI +102 | 6.5, U -142 | Sorokin vs Stolarz (expected) |
| LAK @ COL | 10:00 | COL -192 / LA +158 | 6.5, U -130 (some books 6) | TBD |

Projected lines (from the NHL.com previews cited in the docs):
- **PHI**: Tippett–Zegras–Martone / Bump–Dvorak–Konecny / Foerster–Cates–Michkov / Grundstrom–Couturier–Acciari
- **PIT**: Robertson–Crosby–Rakell / Chinakhov–Novak–Malkin
- **TOR**: Marchenko with Matthews (PP1); Nylander with Tavares
- **NYI**: Holmstrom–Horvat–Palmieri; Schaefer (D, PP1 claimed)
- **LAK**: Panarin–Byfield–Kempe
- **COL**: Lehkonen–MacKinnon–Necas

All three games are opening games for their teams except TOR. **TOR played last night** (lost 2-3 to MTL), so tonight is a back-to-back for them and a fatigue and goalie-rotation flag.

---

## 2. What the ledger recommends (short card)

1. Marchenko 3+ SOG at plus money
2. Crosby 2+ SOG (3+ as a plus-money alternate)
3. MacKinnon 4+ SOG, ceiling about -170
4. MacKinnon anytime goal (AG) at +120 or better
5. Zegras 0.5+ points at -165 to -170 or better
6. One of Tippett 3+ SOG or Kempe 3+ SOG

Sides and totals: lean PIT-PHI Under (no worse than -140), lean NYI-TOR Under (price compressed), pass on COL ML. The PIT ML and NYI ML angles are model-disagreement watchlist items only.

---

## 3. Audit of the ledger's numbers

I checked each call against a Poisson base rate built from the season rates the ledger itself cites, and converted every quoted price to implied probability.

| Item | Ledger grade | Base-rate check | Verdict |
|---|---|---|---|
| MacKinnon 4+ SOG @ -165 | A- | λ = 4.38 gives P = 63.6% (fair -175) vs 62.3% implied, a **+1.4 pt edge** | Thin. Opener vs LA's shot suppression may cut λ. Not "A-". |
| Kempe 3+ SOG @ -135 | B | λ = 2.79 gives 52.8% (fair -112) vs 57.4%, a **-4.6 pt edge** | **Negative on base rate.** Pass unless models show 58%+. |
| Schaefer 3+ SOG @ -152 | B- | λ = 2.71 gives 50.8% vs 60.3%, a **-9.5 pt edge** | **Pass.** "13 of final 15" is recency bias. |
| Tippett 3+ SOG | B | λ = 2.72 gives 51.0% (fair -104) | Plus money is required, as the ledger says. |
| Crosby "2+ SOG, 64% benchmark" | A | At about 3.0 SOG/gm, P(2+) ≈ 80% and P(3+) ≈ 58% | **Internal inconsistency.** 64% only fits the 2.5 line (3+). Confirm which line was meant. |
| Zegras 0.5+ pt, "60% benchmark, playable to 64% (-178)" | B | At 60%, fair is -150. At -178 the edge is -4 pts. | **Price ceiling is wrong.** Ceiling should be about -140, not -170/-178. |
| COL ML -192 | Pass | 60.1% gives fair -151 | Agree: pass. |
| Schaefer AG +390, "31.2% model" | Small stake | 31% for a defenseman is implausible (elite D score in about 15-18% of games) | **Model artifact.** Don't trust the +10.8 pt "edge". |
| MacKinnon AG +125, 48.6% | B+ | Edge +4.2 pts, but one source said 47% | Plausible. Needs a second model to agree. |
| Crosby AG +210 (36.7%) / Rakell +240 / Horvat +175 | watch | Edges of 2-4 pts, each from one source | Leans only under the ledger's own 2-source rule. |

**Systemic issue.** The "benchmark X%, playable to Y%" pattern (Crosby 64→70, Zegras 60→64, Nylander 50→55, Draisaitl 49→54, MacKinnon 47→53) treats the upper number as a price ceiling. That hands away the whole edge. Rule going forward:

> **Price ceiling = fair price from our consensus probability, minus a 2-3 point safety margin. It is never the upper end of a source's range.**

Other issues:
- **Tiny samples used as evidence**, which the blueprint itself calls a failure mode. Examples: Marchenko's case rests on one game (8 attempts, 4 SOG), and several notes cite head-to-head or "prior openers" samples.
- **Hot-hand chasing.** Nylander's two goals last night count only as information about his role.
- **Roster facts need verification.** Several players are on new teams relative to my knowledge (June 2026): Marchenko on TOR, Panarin on LAK, Raddysh on TOR, Nick Robertson on PIT, and Zuccarello listed in LA-COL context. They are plausible offseason moves, but each needs a lineup check before use.
- **Correlation.** Three "lean Under" games plus star SOG overs pull in opposite directions. Crosby SOG, PIT ML and PIT-PHI Under are also linked. Caps must be applied per game.

---

## 4. Lessons carried forward (from both docs)

**What worked on Sept 29**
- Game-environment reads: VAN-EDM over and CHI-VGS over / VGS ML.
- An immediate top-six role converting (Nylander's goal at 0:48).

**What failed**
- No probabilities, no no-vig benchmark, no timestamps.
- P1-scorer picks based on reputation.
- Correlated slips.
- Unresolved conflicts between models.
- No archived prices, so no ROI or CLV.

**Process order**
1. Game environment
2. Player opportunity (line, PP unit, TOI, attempts, ixG)
3. Best expression: SOG when the thesis is volume, points when it is creation, AG when price and shot quality support it, P1 / first goal only at a large premium
4. DK vs FD price, then model vs no-vig
5. Correlation caps

**Betting rules (from the ledger)**
- **Core play:** 2 or more independent sources agree **and** the edge is at least 3 pts after vig.
- **Lean:** one source shows an edge.
- **Pass:** sources disagree by more than 5 pts, lineup or goalie is uncertain, or the price has moved through the ceiling.
- **Stakes:** AG 0.25-0.5u; P1 / first goal 0.1-0.25u; at most 1u per player and 2u per game.

**Blueprint.** The long-term project is a hazard / LightGBM P1-scorer model with walk-forward validation, a DuckDB/Parquet store and CLV tracking (Phases 1-4). **It is not feasible for tonight.** Tonight we use a lightweight version of the same logic.

---

## 5. Environment constraints (important)

This container **cannot reach** NHL API, MoneyPuck, DailyFaceoff, DK/FD, the Odds API, or most news sites: the egress proxy blocks them. **Web search works** (result snippets only).

Consequences:
- Stats, lines and odds must come from search snippets or from **user-provided screenshots/exports** (DK/FD prop boards, SportsPredict, Action).
- To enable direct data pulls, allow `api-web.nhle.com`, `api.nhle.com`, `moneypuck.com`, `dailyfaceoff.com` (and an odds API if you have a key) under *Network access* in the environment settings.

---

## 6. Plan for tonight (deadline: first puck 7:30 ET)

**Step 1 — Refresh facts via search (now)**
- Confirm goalies, especially TOR on a back-to-back (Stolarz or the backup?) and the COL/LAK starters.
- Confirm lines and PP units, and check scratches and injuries.
- Pull 2025-26 per-game rates for the shortlist: SOG, points, goals, ixG, TOI, PP TOI.

**Step 2 — Game environment model**
For each game, estimate team goal rates (Poisson from xGF/xGA and goalie adjustment). That gives win%, P(Over 5.5/6/6.5), and puck-line probabilities, which are compared with no-vig ML and totals prices.

**Step 3 — Player model**
- **SOG props:** negative-binomial P(k+) from a shrunk SOG/gm rate, adjusted for opponent shots-against and projected TOI.
- **AG:** 1 - exp(-λ), where λ = shrunk goals/60 blended with ixG/60 × projected TOI, adjusted for opponent goalie and PP role.
- **Points:** same structure, from points/60.

**Step 4 — Market comparison**
You send the DK and FD prices (screenshots are ideal). For two-way props I de-vig; for AG I use a consensus or an assumed margin. Then compare with our model and with SportsPredict/Action where provided.

**Step 5 — Decision engine**
Apply the rules in §4, with a correct price ceiling for every candidate.

**Step 6 — Deliverables**
In `cards/2026-09-30/`:
- matchup map (attack / neutral / avoid)
- 10-player shortlist
- final card: best book, price, model probability, fair price, edge, stake, ceiling, T-30 re-check list
- `ledger.csv` with timestamps

**Step 7 — Postgame (tomorrow)**
Record closing prices, results and opportunity stats (SOG, TOI, PP TOI), then CLV and error classification.

### Initial shortlist to deep-dive (≤10)

1. MacKinnon (SOG 4+, AG)
2. Crosby (SOG, AG)
3. Marchenko (SOG)
4. Tippett (SOG)
5. Zegras (points)
6. Malkin (points)
7. Kempe (SOG, but base rate says pass at -135)
8. Nylander (SOG / AG, no chase)
9. Byfield (SOG / points)
10. Horvat (AG)

Schaefer and Raddysh are dropped unless prices move.

### What I need from you
- DK + FD screenshots or prices for: AG boards, SOG lines, points lines, totals and ML for all three games.
- SportsPredict and Action projections for the same players or games.
- Your unit size and bankroll, so stakes can be expressed in dollars.
