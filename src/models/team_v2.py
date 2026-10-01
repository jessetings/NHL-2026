"""Team / game model v2: regulation goals per team from strength-split, shot-quality team features.

  lambda_team = exp(c + h*home + r*b2b) * [ EV term + PP term + SH term ] * goalie_opp
    EV term = w_ev * (own EV xGF60 / lg)^a1 * (opp EV xGA60 / lg)^a2 * (own EV GF/xGF)^f
    PP term = w_pp * PPtime * (own PP xGF60 / lg)^b1 * (opp PK xGA60 / lg)^b2
              PPtime = (own PP time pg / lg)^k1 * (opp PK time pg / lg)^k2   (penalties drawn x taken)
    SH term = w_sh (constant)
    goalie_opp = exp(t * opposing starter GSAx per 100 shots)
All features as-of (strictly prior games). Fit by Poisson ML on 2023-24 + 2024-25 regulation goals (incl. EN),
test 2025-26 vs a GF/GA EWMA baseline; then vs the market: clean consensus close (2026-01-17+) and the
opening-line movement test (does the market move toward the model?).
Usage: python src/models/team_v2.py   -> data/curated/models/team_v2.json, reports/team_v2.md
"""
import json
import os
import sys

import duckdb
import numpy as np
import pandas as pd
from scipy import optimize, special, stats

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CUR = "data/curated"
TRAIN = (20232024, 20242025)
TEST = (20252026,)
OUT = f"{CUR}/models/team_v2.json"
NAMES = ["c", "h", "r", "w_pp", "w_sh", "a1", "a2", "f", "b1", "b2", "k1", "k2", "t"]
LGC = ["f_ev_xg60", "a_ev_xg60", "f_pp_xg60", "a_pp_xg60", "pp_sec_pg", "pk_sec_pg"]


def frame():
    con = duckdb.connect()
    g = con.execute(f"""
        with gl as (select game_id,
                      sum(case when period_number <= 3 and try_cast(eventOwnerTeamId as double) = home_id then 1 else 0 end) rh,
                      sum(case when period_number <= 3 and try_cast(eventOwnerTeamId as double) = away_id then 1 else 0 end) ra
                    from '{CUR}/nhl_pbp/*/*.parquet' where typeDescKey = 'goal' group by 1)
        select g.game_id, g.season, g.date, g.home, g.away, gl.rh, gl.ra, g.home_score, g.away_score
        from '{CUR}/nhl_games.parquet' g join gl using (game_id) where g.game_type = 2""").df()
    t = pd.read_parquet(f"{CUR}/features/shotq_team.parquet").drop(columns=["date", "season"])
    st = con.execute(f"""select game_id, team, playerId goalie_id from '{CUR}/nhl_goalie_game.parquet' where starter""").df()
    gq = pd.read_parquet(f"{CUR}/features/shotq_goalie.parquet")[["game_id", "goalie_id", "gsax100"]]
    st = st.merge(gq, on=["game_id", "goalie_id"], how="left")
    rows = []
    for side, opp_side, y in (("home", "away", "rh"), ("away", "home", "ra")):
        x = g.rename(columns={side: "team", opp_side: "opp", y: "goals"})[["game_id", "season", "date", "team", "opp", "goals"]]
        x["home"] = float(side == "home")
        rows.append(x)
    d = pd.concat(rows, ignore_index=True)
    d = d.merge(t.add_prefix("own_").rename(columns={"own_game_id": "game_id", "own_team": "team"}), on=["game_id", "team"])
    d = d.merge(t.add_prefix("opp_").rename(columns={"opp_game_id": "game_id", "opp_team": "opp"}), on=["game_id", "opp"])
    d = d.merge(st.rename(columns={"team": "opp", "gsax100": "opp_gsax"})[["game_id", "opp", "opp_gsax"]], on=["game_id", "opp"], how="left")
    # rest
    sch = pd.concat([g[["game_id", "date", "home"]].rename(columns={"home": "team"}), g[["game_id", "date", "away"]].rename(columns={"away": "team"})])
    sch["date"] = pd.to_datetime(sch.date)
    sch = sch.sort_values(["team", "date"])
    sch["b2b"] = (sch.groupby("team").date.diff().dt.days == 1).astype(float)
    d = d.merge(sch[["game_id", "team", "b2b"]], on=["game_id", "team"], how="left")
    d = d[(d.own_gp_prior >= 10) & (d.opp_gp_prior >= 10)].copy()
    return d, g


def prep(d, lg):
    x = d.copy()
    x["EVf"] = (x.own_f_ev_xg60 / lg.f_ev_xg60).clip(0.5, 2)
    x["EVa"] = (x.opp_a_ev_xg60 / lg.a_ev_xg60).clip(0.5, 2)
    x["FIN"] = ((x.own_f_ev_g60 + 0.5) / (x.own_f_ev_xg60 + 0.5)).clip(0.6, 1.6)
    x["PPf"] = (x.own_f_pp_xg60 / lg.f_pp_xg60).clip(0.4, 2.5)
    x["PKa"] = (x.opp_a_pp_xg60 / lg.a_pp_xg60).clip(0.4, 2.5)
    x["PPd"] = (x.own_pp_sec_pg / lg.pp_sec_pg).clip(0.4, 2.5)
    x["PKt"] = (x.opp_pk_sec_pg / lg.pk_sec_pg).clip(0.4, 2.5)
    x["G"] = x.opp_gsax.fillna(0).clip(-3, 3)
    x["b2b"] = x.b2b.fillna(0)
    return x


def lam(p, x):
    p = dict(zip(NAMES, p))
    ev = x.EVf ** p["a1"] * x.EVa ** p["a2"] * x.FIN ** p["f"]
    pp = np.exp(p["w_pp"]) * x.PPd ** p["k1"] * x.PKt ** p["k2"] * x.PPf ** p["b1"] * x.PKa ** p["b2"]
    return np.exp(p["c"] + p["h"] * (x.home - 0.5) + p["r"] * x.b2b + p["t"] * x.G) * (ev + pp + np.exp(p["w_sh"]))


def nll(mu, y):
    return -(y * np.log(mu) - mu - special.gammaln(y + 1))


def fit(x):
    x0 = np.array([0.6, 0.08, -0.05, -1.0, -3.0, 1, 1, 0.2, 1, 1, 0.5, 0.5, -0.03])
    r = optimize.minimize(lambda p: nll(lam(p, x).values, x.goals.values).mean(), x0, method="L-BFGS-B")
    return r.x


def baseline(d, x):
    """GF/GA EWMA baseline (team goals for x opp goals against, per 60 all strengths)."""
    gf = (x.own_f_ev_g60 * x.own_ev_sec_pg + x.own_f_pp_g60 * x.own_pp_sec_pg) / 3600
    ga = (x.opp_a_ev_g60 * x.opp_ev_sec_pg + x.opp_a_pp_g60 * x.opp_pk_sec_pg) / 3600
    return np.sqrt(gf.clip(0.5) * ga.clip(0.5))


def main():
    d, games = frame()
    lg = d[d.season.isin(TRAIN)][[f"own_{c}" for c in LGC]].median()
    lg.index = [c.replace("own_", "") for c in lg.index]
    lg["a_ev_xg60"] = d[d.season.isin(TRAIN)].opp_a_ev_xg60.median()
    lg["a_pp_xg60"] = d[d.season.isin(TRAIN)].opp_a_pp_xg60.median()
    lg["pk_sec_pg"] = d[d.season.isin(TRAIN)].opp_pk_sec_pg.median()
    x = prep(d, lg)
    tr, te = x[x.season.isin(TRAIN)], x[x.season.isin(TEST)]
    p = fit(tr)
    P = dict(zip(NAMES, map(float, p)))
    print("params", {k: round(v, 3) for k, v in P.items()})
    mu2 = lam(p, te).values
    b = baseline(d, x)
    s = tr.goals.sum() / b[tr.index].sum()
    mu1 = (b[te.index] * s).values
    y = te.goals.values
    dd = nll(mu2, y) - nll(mu1, y)
    L = ["# Team/game model v2", "", f"Params: {P}", "",
         f"OOS 2025-26 team-games n={len(te)}: Poisson LL v2 {nll(mu2, y).mean():.4f} vs GF/GA baseline {nll(mu1, y).mean():.4f} "
         f"(Δ×1000 {1000 * dd.mean():+.2f} ± {2000 * dd.std() / np.sqrt(len(dd)):.2f})"]
    x["mu"] = lam(p, x).values
    json.dump(dict(params=P, lg={k: float(v) for k, v in lg.items()}), open(OUT, "w"), indent=1)
    # ---- vs market (clean 2026-01-17+): predicted P(over main total) and P(home) from the sim grid
    from sim.grid import Grid, total_dist
    from backtest.sim_games import contracts, load
    o, res = load()
    G = Grid()
    m = x.pivot_table(index="game_id", columns="home", values="mu")
    m.columns = ["mu_away", "mu_home"]
    ev = res[["eventID", "game_id", "fh", "fa"]].merge(m.reset_index(), on="game_id")
    rows = []
    for e in ev.itertuples():
        cs = contracts(o[o.eventID == e.eventID])
        if "game|total" not in cs or "game|ml" not in cs:
            continue
        line, po = cs["game|total"]
        ph = cs["game|ml"][1]
        # model's own grid point: rates proportional to regulation lambdas (base, lr)
        def rr(z):           # grid point whose REGULATION mean goals match the model's lambdas
            reg = G.at(*z)["reg"]
            k = np.arange(reg.shape[0])
            return [np.dot(k, reg.sum(1)) - e.mu_home, np.dot(k, reg.sum(0)) - e.mu_away]
        z0 = np.clip([np.sqrt(e.mu_home * e.mu_away), 0.5 * np.log(e.mu_home / e.mu_away)],
                     [G.bases[0] + 1e-6, G.lrs[0] + 1e-6], [G.bases[-1] - 1e-6, G.lrs[-1] - 1e-6])
        z = optimize.least_squares(rr, z0, bounds=([G.bases[0], G.lrs[0]], [G.bases[-1], G.lrs[-1]])).x
        dm = G.at(*z)["final"]
        td = total_dist(dm)
        kk = np.arange(len(td))
        p_over = td[kk > line].sum() / max(1 - td[kk == line].sum(), 1e-9)
        p_home = np.tril(dm, -1).sum()
        tot = e.fh + e.fa
        rows.append(dict(eventID=e.eventID, line=line, mkt_over=po, mdl_over=p_over, mkt_home=ph, mdl_home=p_home,
                         y_over=np.nan if tot == line else float(tot > line), y_home=float(e.fh > e.fa),
                         mdl_mean=float(np.dot(kk, td))))
    R = pd.DataFrame(rows)

    def ll(p, y):
        p = np.clip(p, 1e-4, 1 - 1e-4)
        return -(y * np.log(p) + (1 - y) * np.log(1 - p))
    L += ["", f"## vs clean consensus close (n={len(R)} games, 2026-01-17+)", "",
          "| Market | LL market | LL model | Δ×1000 | LL 80/20 blend | corr(model−mkt, outcome−mkt) |", "|---|---|---|---|---|---|"]
    for nm, pm, pk, yy in (("total over", R.mdl_over, R.mkt_over, R.y_over), ("home ML", R.mdl_home, R.mkt_home, R.y_home)):
        ok = yy.notna()
        a, b_, y_ = pm[ok], pk[ok], yy[ok]
        L.append(f"| {nm} | {ll(b_, y_).mean():.4f} | {ll(a, y_).mean():.4f} | {1000 * (ll(a, y_) - ll(b_, y_)).mean():+.1f} | "
                 f"{ll(0.8 * b_ + 0.2 * a, y_).mean():.4f} | {np.corrcoef(a - b_, y_ - b_)[0, 1]:+.3f} |")
    out = "\n".join(L)
    print(out)
    os.makedirs("reports", exist_ok=True)
    open("reports/team_v2.md", "w").write(out)
    R.to_csv("reports/team_v2_vs_market.csv", index=False)


if __name__ == "__main__":
    main()
