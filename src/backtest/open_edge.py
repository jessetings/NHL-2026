"""Does the model know something the OPENING line doesn't? (2026-01-17+, per-book open/close, main prop lines)

For each player prop where a book's open and close line are the same number:
  p_open, p_close = de-vigged (multiplicative) over probability at open / close
  edge_open       = p_model - p_open           (model v1 or v2)
Tests
  1. Line-movement: regress (p_close - p_open) on edge_open. Positive slope = the market moves toward the model
     (the model holds information the market only prices in later) -> bet early.
  2. Executable: flat 1u at the OPEN price when |edge_open| >= threshold, graded on results; CLV of those bets.
Usage: python src/backtest/open_edge.py
"""
import duckdb
import numpy as np
import pandas as pd
from scipy import stats

CUR = "data/curated"
STATS = {"shots_onGoal": "sog", "points": "goals", "goals+assists": "points", "assists": "assists"}


def prob(o):
    o = np.asarray(o, float)
    return np.where(o > 0, 100 / (o + 100), -o / (-o + 100))


def load():
    con = duckdb.connect()
    o = con.execute(f"""
        select eventID, entity, stat, side, book, any_value(book_open_odds) oo, any_value(book_close_odds) co,
               any_value(book_open_line) ol, any_value(book_close_line) cl
        from '{CUR}/sgo_odds/*.parquet'
        where period = 'game' and bt = 'ou' and not alt and stat in ('shots_onGoal','points','goals+assists','assists')
          and entity not in ('home','away','all') and book in ('draftkings','fanduel','pinnacle')
          and book_open_odds is not null and book_close_odds is not null
        group by all""").df()
    o = o[o.ol == o.cl]
    w = o.pivot_table(index=["eventID", "entity", "stat", "book", "ol"], columns="side", values=["oo", "co"]).dropna()
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w.reset_index().rename(columns={"ol": "line"})
    qo, qu = prob(w.oo_over), prob(w.oo_under)
    w["p_open"] = qo / (qo + qu)
    qo, qu = prob(w.co_over), prob(w.co_under)
    w["p_close"] = qo / (qo + qu)
    c = pd.read_parquet(f"{CUR}/market/contracts.parquet",
                        columns=["eventID", "entity", "stat", "line", "game_id", "player_id", "actual", "date",
                                 "sog60_ewm15", "sog60_ewm40", "toi_min_ewm15", "toi_min_ewm40", "goals60_ewm15",
                                 "goals60_ewm40", "points60_ewm15", "points60_ewm40", "assists60_ewm15", "assists60_ewm40"])
    c = c.drop_duplicates(["eventID", "entity", "stat", "line"])
    w = w.merge(c, on=["eventID", "entity", "stat", "line"], how="inner")
    w = w[w.actual.notna() & (w.line % 1 == 0.5)]
    w["over_hit"] = (w.actual > w.line).astype(float)
    return w


def add_models(w):
    pr = pd.read_parquet(f"{CUR}/models/props_v2_pred.parquet").drop(columns=["season"])
    w = w.merge(pr, on=["game_id", "player_id"], how="left")
    k = np.floor(w.line)
    n = 1 / w.alpha_SOG
    w["p_v2"] = np.select([w.stat == "shots_onGoal", w.stat == "points", w.stat == "goals+assists", w.stat == "assists"],
                          [stats.nbinom.sf(k, n, n / (n + w.mu_SOG)), stats.poisson.sf(k, w.mu_G),
                           stats.poisson.sf(k, w.mu_PTS), stats.poisson.sf(k, w.mu_A)], np.nan)
    toi = 0.5 * w.toi_min_ewm15 + 0.5 * w.toi_min_ewm40
    mu = {"shots_onGoal": (0.5 * w.sog60_ewm15 + 0.5 * w.sog60_ewm40), "points": 0.4 * w.goals60_ewm15 + 0.6 * w.goals60_ewm40,
          "goals+assists": 0.4 * w.points60_ewm15 + 0.6 * w.points60_ewm40, "assists": 0.4 * w.assists60_ewm15 + 0.6 * w.assists60_ewm40}
    w["p_v1"] = np.nan
    for st, m in mu.items():
        s = w.stat == st
        mm = (m * toi / 60)[s]
        w.loc[s, "p_v1"] = stats.nbinom.sf(k[s], 1 / 0.045, (1 / 0.045) / (1 / 0.045 + mm)) if st == "shots_onGoal" else stats.poisson.sf(k[s], mm)
    return w


def main():
    w = add_models(load())
    print(f"contracts with same-line open/close: {len(w):,}; books {w.book.value_counts().to_dict()}")
    L = ["# Opening-line test (2026-01-17+): does the model predict line movement and beat the OPEN price?", ""]
    L += ["## 1. Line movement toward the model", "",
          "slope = Δp(open→close) per unit of (model − open). 0 = market ignores the model; 1 = market moves all the way.", "",
          "| Model | Stat | n | corr(edge, move) | slope | t-stat | mean |move| |", "|---|---|---|---|---|---|---|"]
    for mdl in ("p_v1", "p_v2"):
        for st, x in w[w[mdl].notna()].groupby("stat"):
            e, mv = (x[mdl] - x.p_open).clip(-0.3, 0.3), x.p_close - x.p_open
            if len(x) < 200:
                continue
            sl, ic, r, p, se = stats.linregress(e, mv)
            L.append(f"| {mdl[2:]} | {st} | {len(x)} | {r:+.3f} | {sl:+.4f} | {sl / se:+.1f} | {mv.abs().mean():.4f} |")
    L += ["", "## 2. Bet at the OPEN price when model edge ≥ threshold (flat 1u; graded on results)", "",
          "| Model | Stat | Side | Thr | n | hit | ROI | ±2se | avg CLV (pts) |", "|---|---|---|---|---|---|---|---|---|"]
    rows = []
    for mdl in ("p_v1", "p_v2"):
        for st, x in w[w[mdl].notna() & w.book.isin(["draftkings", "fanduel"])].groupby("stat"):
            for side in ("over", "under"):
                odds = x[f"oo_{side}"]
                imp = prob(odds)
                pm = x[mdl] if side == "over" else 1 - x[mdl]
                po_fair = x.p_open if side == "over" else 1 - x.p_open
                pc_fair = x.p_close if side == "over" else 1 - x.p_close
                win = x.over_hit if side == "over" else 1 - x.over_hit
                dec = np.where(odds > 0, 1 + odds / 100, 1 + 100 / -odds)
                for thr in (0.03, 0.06):
                    sel = (pm - imp) >= thr
                    if sel.sum() < 20:
                        continue
                    pnl = np.where(win[sel] == 1, dec[sel] - 1, -1)
                    clv = (pc_fair - po_fair)[sel]
                    rows.append(dict(model=mdl, stat=st, side=side, thr=thr, n=int(sel.sum()), hit=win[sel].mean(),
                                     roi=pnl.mean(), se=2 * pnl.std() / np.sqrt(sel.sum()), clv=clv.mean()))
                    L.append(f"| {mdl[2:]} | {st} | {side} | {thr:.0%} | {sel.sum()} | {win[sel].mean():.3f} | {pnl.mean():+.1%} | "
                             f"{2 * pnl.std() / np.sqrt(sel.sum()):.1%} | {100 * clv.mean():+.2f} |")
    out = "\n".join(L)
    print(out)
    open("reports/open_edge.md", "w").write(out)
    pd.DataFrame(rows).to_csv("reports/open_edge.csv", index=False)


if __name__ == "__main__":
    main()
