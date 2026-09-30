# NHL Card — Wednesday Sept 30, 2026

- **Odds snapshot:** SportsGameOdds, pulled 21:20 UTC (5:20 PM ET)
- **Books:** DraftKings and FanDuel, with Pinnacle and the SGO consensus used as the no-vig benchmark
- **Model:** MoneyPuck 2024-25, 2025-26 and 2026-27 season-to-date rates (TOI-weighted and shrunk), DailyFaceoff lines and PP units, confirmed or likely goalies. The model is level-calibrated to the market, so player-to-player differences drive the edges.
- **Regenerate:**
  ```
  python src/run_slate.py --refresh && python src/build_card.py
  ```

## Goalies
| Game | Away | Home |
|---|---|---|
| PIT @ PHI 7:30 | Silovs (confirmed) | Vladar (confirmed) |
| NYI @ TOR 7:30 | Sorokin (likely) | Stolarz (confirmed). TOR on a back-to-back. |
| LAK @ COL 10:00 | Kuemper (likely) | Blackwood (confirmed) |

## Bets

See `card_table.md` for the full table with every number. Stakes are in units. Caps are 1u per player and 2u per game; that's why the PIT-PHI stakes are scaled down to 0.33u and 0.17u.

### Core
Core means both the model and the de-vigged market sit above the offered price.

| Pick | Best price | Play if no worse than | Stake |
|---|---|---|---|
| **Malkin 1+ assist** | FD +182 | +164 | 0.33u |
| **Konecny 3+ SOG** | FD +215 | +200 | 0.33u |
| **Nylander 2+ points** | FD +285 | +273 | 0.5u |
| **Makar 4+ SOG** | FD +245 | +238 | 0.5u |
| **Martone 4+ SOG** | FD +265 | +257 | 0.33u |

Martone is a rookie with a 9-game NHL sample, so his model number leans on the PP1 / 1st-line role. It's the least certain of the five.

### Leans
These have one supporting source only.

| Pick | Best price | Ceiling | Why it's a lean |
|---|---|---|---|
| Tippett 4+ SOG | FD +280 | +272 | Model only. Note that he is PP2, not PP1. |
| Kadri 4+ SOG | FD +320 | +320 | Model only |
| Rakell 4+ SOG | FD +325 | +334 | Model only |
| Zegras 3+ SOG | FD +225 | +224 | Model only |
| Konecny 2+ points | DK +370 | +349 | Price-shop: DK is soft vs consensus |
| Zegras 2+ points | FD +330 | +340 | Price-shop |
| DeAngelo 3+ SOG | DK +230 | +228 | Price-shop |
| Toews 3+ SOG | DK +250 | +250 | Price-shop |
| Martone 1+ assist | DK +180 | +185 | Model only |

Most of the value sits on **FanDuel's alt SOG ladder** (the 3+ and 4+ rungs). FanDuel is pricing those rungs more generously than its own main line implies. This is only valid if SOG tails follow our negative-binomial assumption (variance ≈ 1.2 × mean). Keep stakes small until postgame tracking confirms it.

## Game lines: all PASS

| Game | Model | Market (no-vig) | Verdict |
|---|---|---|---|
| PIT @ PHI | PHI 56.3%, P(over 6.5) 42% | PHI 56.5%, U6.5 -130/-138 | No edge. Ledger's "Under" lean is already priced in. |
| NYI @ TOR | NYI 50.6% | NYI ~46% (DK +110) | Model likes NYI by ~5 pts and TOR is on a back-to-back. That is right at the disagreement limit, so it's a **watch**. If you want exposure, 0.25u NYI ML at +110 or better. |
| LAK @ COL | COL 57.7% | COL 63.5% | The model disagrees with the market by 6 pts. That is a data-check (LA roster changes), not a bet. Pass. |

## Ledger picks re-tested on live prices

| Ledger pick | Live price | Model / market | Verdict |
|---|---|---|---|
| MacKinnon anytime goal (B+) | FD +120 (45.5%) | 39.7% / 43.4% | **Pass.** No edge. |
| MacKinnon 4+ SOG (A-) | FD -148 (59.7%) | 55.9% / 58.0% | **Pass.** |
| Crosby 2+ SOG (A) | DK -230 (69.7%) | 67.4% / 64.6% | **Pass.** He averaged 2.35 SOG/gm last season, not ~3. |
| Crosby 3+ SOG | FD +138 (42.0%) | 43.2% / 40.2% | Pass (about fair). |
| Marchenko 3+ SOG (A) | Not in SGO feed | Model fair **-124** (55.4%) | **Check DK/FD yourself.** Playable at **-110 or better**. 4+ is playable at +213 or better. |
| Zegras 1+ point (B) | DK -150 (60.0%) | 57.9% / 64.5% | Pass/lean. The ledger's -178 ceiling was too high. |
| Kempe 3+ SOG (B) | DK -110 (52.4%) | 50.6% / 54.1% | Pass |
| Schaefer 3+ SOG (B-) | FD -128 (56.1%) | 52.4% / 54.5% | Pass |
| Tippett 3+ SOG (B) | FD +110 (47.6%) | 52.9% / 47.0% | Lean only. The model likes it; the market doesn't. |
| Crosby / Horvat / Rakell / Nylander anytime goal | — | All within ±3% EV | Pass. The anytime-goal market is efficient tonight. |

**McKenna** (TOR rookie, 2nd line with Nylander/Tavares, PP2) is also missing from the feed. Model fair prices:
- 2+ SOG: -108
- anytime goal: +419
- 1+ point: +172

Play only at those prices plus a 3-point margin (anytime goal at +515 or better, 1+ point at +196 or better).

## T-30 checklist (7:00 PM ET, and 9:30 PM ET for LA-COL)
1. Re-run `python src/run_slate.py --refresh && python src/build_card.py`. This costs 3 SGO objects of the 2,500/month.
2. Confirm Sorokin and Kuemper starting (both currently "likely").
3. Confirm Martone and Konecny lines and PP units at warmups. Re-check Tippett's PP unit.
4. Drop any pick whose price has moved past its ceiling.

## Postgame (tomorrow)
Log the closing price, result, SOG/TOI/PP TOI and CLV per pick. Then check whether the FD alt-ladder edge holds up before sizing it any higher.
