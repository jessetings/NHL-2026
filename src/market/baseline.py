"""Historical market-only baseline for player props, joined to outcomes and as-of features.

contracts.parquet: one row per (eventID, player, stat, line) with
  - p_cons: SGO consensus no-vig close P(over) at its own close line (2025-02+)
  - p_<book>: per-book pregame close de-vigged P(over) (multiplicative + power), 2026-01-17+
  - odds_over_<book>/odds_under_<book>: the executable close prices (for ROI / CLV)
  - outcome (actual stat from NHL boxscore) and model features from features/player_game.parquet
Usage: python src/market/baseline.py
"""
import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from devig import american_to_prob, two_way  # noqa: E402

CUR = "data/curated"
STAT = {"shots_onGoal": "sog", "points": "goals", "goals+assists": "points", "assists": "assists"}
BOOKS = ("draftkings", "fanduel", "pinnacle")


def main():
    con = duckdb.connect()
    o = con.execute(f"""
        select eventID, entity, stat, side, book, alt, close_fair_odds, close_fair_line,
               book_close_odds, book_close_line
        from '{CUR}/sgo_odds/*.parquet'
        where period = 'game' and bt = 'ou' and stat in ('shots_onGoal','points','goals+assists','assists')
          and entity not in ('home','away','all')""").df()
    # 1) consensus close (market-level fields repeat on every book row) -> one row per contract side
    c = o.dropna(subset=["close_fair_odds"]).drop_duplicates(["eventID", "entity", "stat", "side"])
    c["close_fair_line"] = pd.to_numeric(c.close_fair_line, errors="coerce")
    c["q"] = american_to_prob(pd.to_numeric(c.close_fair_odds, errors="coerce"))
    cons = c.pivot_table(index=["eventID", "entity", "stat", "close_fair_line"], columns="side", values="q").reset_index()
    cons = cons.rename(columns={"close_fair_line": "line", "over": "p_cons_over", "under": "p_cons_under"})
    # fair odds are already vig-free; normalise defensively (integer lines carry push mass)
    cons["p_cons"] = cons.p_cons_over / (cons.p_cons_over + cons.p_cons_under)

    # 2) per-book pregame close, main line only (alt lines have no close)
    b = o[~o.alt & o.book.isin(BOOKS) & o.book_close_odds.notna()].copy()
    b["line"] = b.book_close_line
    bp = b.pivot_table(index=["eventID", "entity", "stat", "line", "book"], columns="side",
                       values="book_close_odds", aggfunc="first").reset_index()
    bp = bp.dropna(subset=["over", "under"])
    bp["p_mult"] = two_way(bp.over.values, bp.under.values, "multiplicative")
    bp["p_pow"] = two_way(bp.over.values, bp.under.values, "power")
    wide = bp.pivot_table(index=["eventID", "entity", "stat", "line"], columns="book",
                          values=["p_mult", "p_pow", "over", "under"]).reset_index()
    wide.columns = ["_".join([x for x in col if x]) if isinstance(col, tuple) else col for col in wide.columns]

    k = ["eventID", "entity", "stat", "line"]
    m = cons.merge(wide, on=k, how="outer")
    # outcomes + features
    ev = con.execute(f"select eventID, game_id from '{CUR}/map_sgo_event.parquet'").df()
    pm = con.execute(f"select sgo_player as entity, player_id from '{CUR}/map_sgo_player.parquet'").df()
    m = m.merge(ev, on="eventID").merge(pm, on="entity", how="left")
    f = pd.read_parquet(f"{CUR}/features/player_game.parquet")
    m = m.merge(f, on=["game_id", "player_id"], how="left")
    m["target"] = m.stat.map(STAT)
    m["actual"] = [r[t] if isinstance(t, str) and t in r else np.nan for r, t in
                   zip(m[["sog", "goals", "points", "assists"]].to_dict("records"), m.target)]
    m["over_hit"] = np.where(m.actual.isna(), np.nan, (m.actual > m.line).astype(float))
    m["push"] = m.actual == m.line
    os.makedirs(f"{CUR}/market", exist_ok=True)
    m.to_parquet(f"{CUR}/market/contracts.parquet", index=False)
    s = m[m.over_hit.notna()]
    print(f"contracts: {len(m):,}; with outcome: {len(s):,}; with consensus: {s.p_cons.notna().sum():,}; "
          f"with DK close: {s.filter(like='p_mult_draftkings').notna().sum().sum():,}; "
          f"FD close: {s.filter(like='p_mult_fanduel').notna().sum().sum():,}")
    print(s.groupby("stat").size())


if __name__ == "__main__":
    main()
