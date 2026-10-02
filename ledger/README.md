# Bets ledger

`bets.csv` records the bets actually placed (not the paper picks the cards publish). The dashboard reads it for the real bankroll curve.

Fill in one row per bet:
- `stake_pct`: stake as a % of bankroll, e.g. 1.5.
- `pnl_units`: profit or loss in bankroll %. A boost applies to the profit only.
- `boost`: 0.5 means a 50% profit boost.
- `result`: won, lost, push or void.
- `notes`: anything else.

The dashboard computes the bankroll curve from the cumulative sum of `pnl_units`, starting from `start_bankroll` on the first row.
