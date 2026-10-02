"""Extra prop markets: power-play points (PPP) and blocked shots (BLK), same as-of feature stack as props_v2.

  PPP = exp(c + dD*isD + h*home) * pp_pts60 * PPh * PKopp^k * E_pp^p * goalie       (Poisson)
  BLK = exp(c + dD*isD + h*home + r*b2b) * blk_pg * (TOIproj/TOIhist) * (own shot attempts allowed/lg)^a
        * (opp shot attempts for/lg)^b                                                (NB2)
Fit 2023-24 + 2024-25, test 2025-26 vs naive EWMA baselines.
Usage: python src/models/props_extra.py   -> data/curated/models/props_extra.json + props_extra_pred.parquet
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import optimize

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from models import props_v2 as V  # noqa: E402

CUR = "data/curated"
OUT = f"{CUR}/models/props_extra.json"


def frame():
    raw = V.frame()
    raw = raw[(raw.gp_career_prior >= 10) & raw.own_gp_prior.ge(10) & raw.opp_gp_prior.ge(10)]
    P = json.load(open(V.PARAMS))
    d = V.prep(raw, pd.Series(P["_lg"]))
    pts = pd.read_parquet(f"{CUR}/features/pts_strength_game.parquet")
    pp = pts[pts.str == "PP"].groupby(["game_id", "player_id"])[["pg", "pa"]].sum().sum(1).rename("ppp").reset_index()
    d = d.merge(pp, on=["game_id", "player_id"], how="left")
    d["ppp"] = d.ppp.fillna(0)
    return d


def lg_of(d):
    tr = d[d.season.isin(V.TRAIN)]
    return dict(own_a_ev_att60=float(tr.own_a_ev_att60.median()), opp_f_ev_att60=float(tr.opp_f_ev_att60.median()))


def mu_ppp(p, d):
    return (np.exp(p[0] + p[1] * d.isD + p[2] * (d.home - 0.5)) * d.pp_pts60 * d.PPh * d.PKopp ** p[3] * d.E_pp ** p[4]
            * np.exp(p[5] * d.gsax)).clip(1e-4)


def mu_blk(p, d, lg):
    toi_proj = 0.6 * d.toi_min_ewm5 + 0.4 * d.toi_min_ewm15
    base = (0.5 * d.blockedShots_ewm15 + 0.5 * d.blockedShots_ewm40) * (toi_proj / (0.5 * d.toi_min_ewm15 + 0.5 * d.toi_min_ewm40)).clip(0.5, 1.6)
    return (np.exp(p[0] + p[1] * d.isD + p[2] * (d.home - 0.5) + p[3] * d.b2b_own) * base
            * (d.own_a_ev_att60 / lg["own_a_ev_att60"]).clip(0.6, 1.6) ** p[4]
            * (d.opp_f_ev_att60 / lg["opp_f_ev_att60"]).clip(0.6, 1.6) ** p[5]).clip(1e-3)


def main():
    d = frame()
    lg = lg_of(d)
    tr, te = d[d.season.isin(V.TRAIN)], d[d.season.isin(V.TEST)]
    out = {"_lg": lg}
    # PPP
    f = lambda p: V.nll(mu_ppp(p, tr).values, tr.ppp.values).mean()  # noqa: E731
    p_ppp = optimize.minimize(f, [0, 0, 0, 0.5, 0.5, 0], method="L-BFGS-B").x
    base = (0.5 * te.pp_pg60 + 0.5 * te.pp_pa60).clip(0) * 0 + te.pp_pts60 * te.PPh     # naive: rate x PP time
    s = tr.ppp.sum() / (tr.pp_pts60 * tr.PPh).sum()
    dd = V.nll(mu_ppp(p_ppp, te).values, te.ppp.values) - V.nll((base * s).clip(1e-4).values, te.ppp.values)
    print(f"PPP params {np.round(p_ppp, 3)}  OOS Δ×1000 vs naive {1000 * dd.mean():+.2f} ± {2000 * dd.std() / np.sqrt(len(dd)):.2f}")
    out["PPP"] = list(map(float, p_ppp))
    # BLK
    ok = tr.blockedShots_ewm15.notna() & tr.toi_min_ewm5.notna()
    t2 = tr[ok]

    def fb(z):
        mu = mu_blk(z[:6], t2, lg).values
        return V.nll(mu, t2.blockedShots.values, np.exp(z[6])).mean()
    z = optimize.minimize(fb, [0, 0, 0, 0, 0.5, 0.5, np.log(0.1)], method="L-BFGS-B").x
    p_blk, a_blk = z[:6], float(np.exp(z[6]))
    e2 = te[te.blockedShots_ewm15.notna() & te.toi_min_ewm5.notna()]
    naive = (0.5 * e2.blockedShots_ewm15 + 0.5 * e2.blockedShots_ewm40).clip(1e-3)
    dd = V.nll(mu_blk(p_blk, e2, lg).values, e2.blockedShots.values, a_blk) - V.nll(naive.values, e2.blockedShots.values, a_blk)
    print(f"BLK params {np.round(p_blk, 3)} alpha {a_blk:.3f}  OOS Δ×1000 vs naive EWMA {1000 * dd.mean():+.2f} ± {2000 * dd.std() / np.sqrt(len(dd)):.2f}")
    out["BLK"], out["BLK_alpha"] = list(map(float, p_blk)), a_blk
    json.dump(out, open(OUT, "w"), indent=1)
    pred = d[["game_id", "player_id"]].copy()
    pred["mu_PPP"] = mu_ppp(p_ppp, d).values
    pred["mu_BLK"] = mu_blk(p_blk, d, lg).values
    pred["alpha_BLK"] = a_blk
    pred.to_parquet(f"{CUR}/models/props_extra_pred.parquet", index=False)


if __name__ == "__main__":
    main()
