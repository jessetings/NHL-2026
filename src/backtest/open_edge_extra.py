"""Opening-line test for extra prop markets (power-play points, blocks, goalie saves), DK/FD/Pinnacle 2026-01-17+.

Same protocol as open_edge.py: same-line open/close pairs, de-vigged; model probability at the line from the
model mean (Poisson / NB2); line-movement slope; flat-stake ROI at DK/FD OPEN prices by side and edge,
raw and level-corrected per date (relative signal).
Usage: python src/backtest/open_edge_extra.py
"""
import duckdb
import numpy as np
import pandas as pd
from scipy import optimize, stats

CUR = "data/curated"


def prob(o):
    o = np.asarray(o, float)
    return np.where(o > 0, 100 / (o + 100), -o / (-o + 100))


def pairs(stat):
    con = duckdb.connect()
    o = con.execute(f"""
        select eventID, entity, side, book, any_value(book_open_odds) oo, any_value(book_close_odds) co,
               any_value(book_open_line) ol, any_value(book_close_line) cl
        from '{CUR}/sgo_odds/*.parquet'
        where period = 'game' and bt = 'ou' and not alt and stat = '{stat}' and entity not in ('home','away','all')
          and book in ('draftkings','fanduel','pinnacle') and book_open_odds is not null and book_close_odds is not null
          and startsAt >= '2026-01-17'
        group by all""").df()
    o = o[o.ol == o.cl]
    w = o.pivot_table(index=["eventID", "entity", "book", "ol"], columns="side", values=["oo", "co"]).dropna()
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w.reset_index().rename(columns={"ol": "line"})
    qo, qu = prob(w.oo_over), prob(w.oo_under)
    w["p_open"] = qo / (qo + qu)
    qo, qu = prob(w.co_over), prob(w.co_under)
    w["p_close"] = qo / (qo + qu)
    ev = con.execute(f"select eventID, game_id from '{CUR}/map_sgo_event.parquet'").df()
    pm = con.execute(f"select sgo_player as entity, player_id from '{CUR}/map_sgo_player.parquet'").df()
    return w.merge(ev, on="eventID").merge(pm, on="entity", how="left")


def run(name, w, mu, y, dist, alpha=None):
    w = w.copy()
    w["mu"], w["y"] = mu, y
    w = w[w.mu.notna() & w.y.notna() & (w.line % 1 == 0.5)]
    k = np.floor(w.line)
    if dist == "nb":
        n = 1 / alpha
        sf = lambda m: stats.nbinom.sf(k, n, n / (n + m))            # noqa: E731
    else:
        sf = lambda m: stats.poisson.sf(k, m)                          # noqa: E731
    w["p_mdl"] = sf(w.mu)
    w["over_hit"] = (w.y > w.line).astype(float)
    sl, ic, r, p, se = stats.linregress((w.p_mdl - w.p_open).clip(-0.3, 0.3), w.p_close - w.p_open)
    L = [f"## {name}", "", f"n={len(w)}; line movement toward model: corr {r:+.3f}, slope {sl:+.3f} (t {sl / se:+.1f}); "
         f"actual over rate {w.over_hit.mean():.3f}, mean p_open {w.p_open.mean():.3f}, mean p_model {w.p_mdl.mean():.3f}", ""]

    def inv(pv, line):
        try:
            return optimize.brentq(lambda m: (stats.nbinom.sf(np.floor(line), 1 / alpha, (1 / alpha) / (1 / alpha + m)) if dist == "nb"
                                              else stats.poisson.sf(np.floor(line), m)) - pv, 0.005, 60)
        except Exception:  # noqa: BLE001
            return np.nan
    w["date"] = w.game_id.astype(str).str[:4]                     # fallback
    gd = duckdb.connect().execute(f"select game_id, date from '{CUR}/nhl_games.parquet'").df()
    w = w.drop(columns="date").merge(gd, on="game_id", how="left")
    w["mu_mkt"] = [inv(pv, ln) for pv, ln in zip(w.p_open, w.line)]
    lvl = (w.mu / w.mu_mkt).groupby(w.date).transform("median")
    w["p_rel"] = sf(w.mu / lvl)
    b = w[w.book.isin(["draftkings", "fanduel"])]
    L += ["| Signal | Side | Edge ≥ | n | hit | ROI | ±2se | CLV (pts) |", "|---|---|---|---|---|---|---|---|"]
    for sig in ("p_mdl", "p_rel"):
        for side in ("over", "under"):
            odds = b[f"oo_{side}"]
            dec = np.where(odds > 0, 1 + odds / 100, 1 + 100 / -odds)
            pm = b[sig] if side == "over" else 1 - b[sig]
            win = b.over_hit if side == "over" else 1 - b.over_hit
            clv = (b.p_close - b.p_open) * (1 if side == "over" else -1)
            for thr in (-1, 0.03, 0.06):
                sel = ((pm - prob(odds)) >= thr) if thr > -1 else np.ones(len(b), bool)
                if sel.sum() < 30:
                    continue
                pnl = np.where(win[sel] == 1, dec[sel] - 1, -1)
                L.append(f"| {'raw' if sig == 'p_mdl' else 'level-corr'} | {side} | {'all' if thr < 0 else f'{thr:.0%}'} | "
                         f"{sel.sum()} | {win[sel].mean():.3f} | {pnl.mean():+.1%} | {2 * pnl.std() / np.sqrt(sel.sum()):.1%} | "
                         f"{100 * clv[sel].mean():+.2f} |")
    return L


def main():
    L = ["# Opening-line test: extra prop markets (2026-01-17+)", ""]
    pred = pd.read_parquet(f"{CUR}/models/props_extra_pred.parquet")
    pg = pd.read_parquet(f"{CUR}/features/player_game.parquet", columns=["game_id", "player_id", "blockedShots"])
    pts = pd.read_parquet(f"{CUR}/features/pts_strength_game.parquet")
    ppp = pts[pts.str == "PP"].groupby(["game_id", "player_id"])[["pg", "pa"]].sum().sum(axis=1).rename("ppp").reset_index()
    for name, stat, mcol, ycol, dist in (("Power-play points", "powerPlay_goals+assists", "mu_PPP", "ppp", "poisson"),
                                          ("Blocked shots", "blocks", "mu_BLK", "blockedShots", "nb")):
        w = pairs(stat).merge(pred, on=["game_id", "player_id"], how="left")
        w = w.merge(pg, on=["game_id", "player_id"], how="left").merge(ppp, on=["game_id", "player_id"], how="left")
        if ycol == "ppp":
            w["ppp"] = w.ppp.fillna(0).where(w.blockedShots.notna())     # played the game -> 0 PPP if none
        L += run(name, w, w[mcol], w[ycol], dist, alpha=float(pred.alpha_BLK.iloc[0]) if dist == "nb" else None) + [""]
    try:
        from models import goalie_saves as GS  # noqa: F401
        L += GS.open_test()
    except Exception as e:  # noqa: BLE001
        L += [f"_goalie saves: {e}_"]
    out = "\n".join(L)
    print(out)
    open("reports/open_edge_extra.md", "w").write(out)


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    main()
