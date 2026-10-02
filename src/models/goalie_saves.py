"""Goalie saves model (starters) + opening-line test.

  saves = exp(c + h*home + r*b2b) * [ (opp EV SOG-for60/lg)^a1 * (own EV SOG-against60/lg)^a2 * EVmin
                                      + w_pp * (opp PP time/lg)^k1 * (own PK time/lg)^k2 * (opp PP SOG60/lg)^b ]
          * exp(t * own goalie GSAx/100)                                                      (NB2)
All inputs as-of (shotq_team / shotq_goalie). Fit 2023-24 + 2024-25, test 2025-26 vs a naive EWMA of saves.
Usage: python src/models/goalie_saves.py
"""
import json
import os
import sys

import duckdb
import numpy as np
import pandas as pd
from scipy import optimize, stats

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from models import props_v2 as V  # noqa: E402

CUR = "data/curated"
OUT = f"{CUR}/models/goalie_saves.json"
TRAIN, TEST = V.TRAIN, V.TEST


def frame():
    con = duckdb.connect()
    g = con.execute(f"""
        select gg.game_id, gg.playerId goalie_id, gg.team, gg.opp, gg.is_home, gg.saves, gg.shotsAgainst, gg.toi_sec, g.season, g.date
        from '{CUR}/nhl_goalie_game.parquet' gg join '{CUR}/nhl_games.parquet' g using (game_id)
        where gg.starter and g.game_type = 2""").df()
    t = pd.read_parquet(f"{CUR}/features/shotq_team.parquet").drop(columns=["date", "season"])
    g = g.merge(t.add_prefix("own_").rename(columns={"own_game_id": "game_id", "own_team": "team"}), on=["game_id", "team"])
    g = g.merge(t.add_prefix("opp_").rename(columns={"opp_game_id": "game_id", "opp_team": "opp"}), on=["game_id", "opp"])
    q = pd.read_parquet(f"{CUR}/features/shotq_goalie.parquet")[["game_id", "goalie_id", "gsax100", "gp_prior"]]
    g = g.merge(q.rename(columns={"gp_prior": "g_gp"}), on=["game_id", "goalie_id"], how="left")
    g["date"] = pd.to_datetime(g.date)
    g = g.sort_values(["goalie_id", "date"])
    g["naive"] = g.groupby("goalie_id").saves.transform(lambda s: s.shift(1).ewm(halflife=10, min_periods=1).mean())
    sch = pd.concat([g[["game_id", "team", "date"]]]).drop_duplicates().sort_values(["team", "date"])
    sch["b2b"] = (sch.groupby("team").date.diff().dt.days == 1).astype(float)
    g = g.merge(sch[["game_id", "team", "b2b"]], on=["game_id", "team"], how="left")
    return g[(g.own_gp_prior >= 10) & (g.opp_gp_prior >= 10)].copy()


def lg_of(d):
    tr = d[d.season.isin(TRAIN)]
    return {c: float(tr[c].median()) for c in ("opp_f_ev_sog60", "own_a_ev_sog60", "opp_pp_sec_pg", "own_pk_sec_pg", "opp_f_pp_sog60",
                                                 "own_ev_sec_pg")}


def mu(p, d, lg):
    ev = (d.opp_f_ev_sog60 / lg["opp_f_ev_sog60"]).clip(0.6, 1.6) ** p[3] * (d.own_a_ev_sog60 / lg["own_a_ev_sog60"]).clip(0.6, 1.6) ** p[4]
    pp = np.exp(p[5]) * (d.opp_pp_sec_pg / lg["opp_pp_sec_pg"]).clip(0.4, 2.5) ** p[6] * \
        (d.own_pk_sec_pg / lg["own_pk_sec_pg"]).clip(0.4, 2.5) ** p[7] * (d.opp_f_pp_sog60 / lg["opp_f_pp_sog60"]).clip(0.5, 2) ** p[8]
    return (np.exp(p[0] + p[1] * (d.is_home - 0.5) + p[2] * d.b2b.fillna(0) + p[9] * d.gsax100.fillna(0).clip(-3, 3)) * (ev + pp)).clip(1)


def fit():
    d = frame()
    lg = lg_of(d)
    tr, te = d[d.season.isin(TRAIN)], d[d.season.isin(TEST)]
    x0 = [np.log(22), 0, 0, 0.8, 0.8, np.log(0.15), 0.5, 0.5, 0.5, 0.0, np.log(0.02)]
    f = lambda z: V.nll(mu(z[:10], tr, lg).values, tr.saves.values, np.exp(z[10])).mean()  # noqa: E731
    z = optimize.minimize(f, x0, method="L-BFGS-B").x
    p, a = z[:10], float(np.exp(z[10]))
    e = te[te.naive.notna()]
    s = tr.saves.sum() / tr.naive.sum()
    dd = V.nll(mu(p, e, lg).values, e.saves.values, a) - V.nll((e.naive * s).values, e.saves.values, a)
    msg = (f"saves params {np.round(p, 3)} alpha {a:.4f} | OOS Δ×1000 vs naive EWMA {1000 * dd.mean():+.2f} ± "
           f"{2000 * dd.std() / np.sqrt(len(dd)):.2f} (n={len(e)})")
    print(msg)
    json.dump(dict(params=list(map(float, p)), alpha=a, lg=lg), open(OUT, "w"), indent=1)
    d["mu"] = mu(p, d, lg).values
    d[["game_id", "goalie_id", "mu"]].assign(alpha=a).to_parquet(f"{CUR}/models/goalie_saves_pred.parquet", index=False)
    return msg


def open_test():
    from backtest.open_edge_extra import pairs, run
    pred = pd.read_parquet(f"{CUR}/models/goalie_saves_pred.parquet")
    a = float(pred.alpha.iloc[0])
    gg = duckdb.connect().execute(f"select game_id, playerId goalie_id, saves from '{CUR}/nhl_goalie_game.parquet'").df()
    w = pairs("goalie_saves").rename(columns={"player_id": "goalie_id"})
    w = w.merge(pred, on=["game_id", "goalie_id"], how="left").merge(gg, on=["game_id", "goalie_id"], how="left")
    return run("Goalie saves (starters; model as-of)", w, w.mu, w.saves, "nb", alpha=a)


if __name__ == "__main__":
    fit()
    print("\n".join(open_test()))
