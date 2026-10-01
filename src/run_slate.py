"""Build tonight's card: model vs market for game lines and player props.

Usage: python src/run_slate.py [--refresh]
"""
import os
import re
import sys
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy import optimize

sys.path.insert(0, os.path.dirname(__file__))
import model as M  # noqa: E402
import odds as O  # noqa: E402
import slate as SL  # noqa: E402

DATE = SL.DATE
OUT = SL.OUT
MODEL_W = 0.40          # blend weight on our model vs de-vigged market
MIN_EDGE = 0.025        # absolute prob edge of blended p over best-price implied p
MIN_EV = 0.05
DISAGREE = 0.12         # model vs market gap that triggers a data check instead of a bet

TEAM = SL.SGO_TEAM
SLUG = SL.SLUG
GOALIES = {}     # filled from the latest DailyFaceoff snapshot
USAGE = {}
DF_G = {}
B2B = set()     # filled from the NHL schedule (SL.back_to_back)
ROLE_TOI = {"f1": 18.0, "f2": 16.0, "f3": 13.5, "f4": 10.5, "d1": 22.5, "d2": 20.0, "d3": 16.5}
STAT_MAP = {"shots_onGoal": "SOG", "points": "G", "goals+assists": "PTS", "assists": "A"}


def ev(p, american):
    dec = 1 + (american / 100 if american > 0 else 100 / -american)
    return p * dec - 1


# ------------------------------------------------------------ roster / roles
def roster():
    lines = M.load_lines()
    rows = []
    for slug, plist in lines.items():
        team = SLUG.get(slug)
        if team is None:
            continue
        groups = {}
        for p in plist:
            groups.setdefault(p["name"], []).append(p["group"])
        for name, gs in groups.items():
            ev_role = next((g for g in gs if g in ROLE_TOI), None)
            if ev_role is None:
                continue
            pp = "PP1" if "pp1" in gs else ("PP2" if "pp2" in gs else "-")
            rows.append(dict(team=team, name=name, key=M.norm(name), role=ev_role, pp=pp,
                             pos="D" if ev_role.startswith("d") else "F"))
    return pd.DataFrame(rows)


# ------------------------------------------------------------ market-implied means
def devig_two_way(p_over, p_under):
    s = p_over + p_under
    return p_over / s


def p_over_ex_push(market, mean, line):
    """P(over) excluding pushes (integer lines refund on exact hit)."""
    po = M.prob_over(market, mean, line)
    if float(line).is_integer():
        pu = 1 - M.prob_over(market, mean, line - 0.5)
        return po / (po + pu)
    return po


def solve_mean(market, line, p_over):
    f = lambda m: p_over_ex_push(market, m, line) - p_over  # noqa: E731
    try:
        return optimize.brentq(f, 1e-4, 15)
    except ValueError:
        return np.nan


def market_means(df):
    """Per (player, stat): market-implied mean from best two-way de-vig available."""
    out = {}
    pl = df[df.player.notna() & df.stat.isin(STAT_MAP) & (df.bt == "ou")]
    for (pid, stat), g in pl.groupby(["entity", "stat"]):
        mk = STAT_MAP[stat]
        cands = []
        for (book, line), gg in g.groupby(["book", "line"]):
            o = gg[gg.side == "over"].odds
            u = gg[gg.side == "under"].odds
            if len(o) and len(u):
                p = devig_two_way(O.american_to_prob(o.iloc[0]), O.american_to_prob(u.iloc[0]))
                w = 2.0 if book == "pinnacle" else 1.0
                m = solve_mean(mk, line, p)
                if not np.isnan(m):
                    cands.append((m, w, f"{book}@{line}"))
        # SGO consensus fair odds on its fair line
        fr = g[(g.side == "over") & g.fair_odds.notna()].drop_duplicates("oddID")
        for _, r in fr.iterrows():
            if pd.notna(r.fair_line):
                m = solve_mean(mk, r.fair_line, O.american_to_prob(int(float(r.fair_odds))))
                if not np.isnan(m):
                    cands.append((m, 2.0, f"sgo_fair@{r.fair_line}"))
        if cands:
            ms, ws, src = zip(*cands)
            out[(pid, mk)] = (float(np.average(ms, weights=ws)), ",".join(src))
    return out


def df_goalies():
    """Latest DailyFaceoff starters with status, keyed by team abbrev."""
    import glob as _g
    import gzip
    import json
    abbr = SL.FULLNAME
    fs = sorted(_g.glob("data/raw/dailyfaceoff/*.json.gz"))
    out = {}
    if fs:
        for g in json.load(gzip.open(fs[-1]))["goalies"] or []:
            for side in ("home", "away"):
                t = abbr.get(g[f"{side}TeamName"])
                if t:
                    out[t] = (g[f"{side}GoalieName"], g[f"{side}NewsStrengthName"])
    return out


def goalie_mix(team):
    """Goalie factor for `team`'s goalie; if not Confirmed, mix with the model's alternative by P(start)."""
    name, status = DF_G.get(team, (GOALIES.get(team), "Unknown"))
    if name and status == "Confirmed":
        GOALIES[team] = name
        return M.goalie_factor(name)[0], f"{name} confirmed"
    try:
        from features.goalie_start import predict_next
        probs = predict_next(team, DATE)
    except Exception:  # noqa: BLE001
        probs = {}
    import duckdb
    names = {}
    if probs:
        ids = ",".join(str(int(i)) for i in probs)
        q = duckdb.connect().execute(f"select player_id, first||' '||last from 'data/curated/nhl_players.parquet' "
                                     f"where player_id in ({ids})").fetchall()
        names = {i: n for i, n in q}
    if not name:
        # no DailyFaceoff entry yet: model-projected starter, factor mixed over all candidates by P(start)
        if not probs:
            GOALIES[team] = None
            return 1.0, "no goalie info"
        top = max(probs, key=probs.get)
        GOALIES[team] = names.get(top)
        f = sum(p * M.goalie_factor(names.get(i, ""))[0] for i, p in probs.items())
        return f, f"{names.get(top)} projected by model (P start {probs[top]:.0%})"
    GOALIES[team] = name
    f_named = M.goalie_factor(name)[0]
    p_named = max([p for i, p in probs.items() if M.norm(names.get(i, "")) == M.norm(name)] or [0.0])
    p_named = max(p_named, 0.80 if status == "Likely" else 0.5)     # DF 'Likely' floor
    alt = [(p, names.get(i)) for i, p in probs.items() if M.norm(names.get(i, "")) != M.norm(name)]
    if not alt:
        return f_named, f"{name} {status.lower()}"
    _, alt_name = max(alt)
    f = p_named * f_named + (1 - p_named) * M.goalie_factor(alt_name)[0]
    return f, f"{name} {status.lower()} (P start {p_named:.0%}; alt {alt_name})"


# ------------------------------------------------------------ main
def main(refresh=False):
    os.makedirs(OUT, exist_ok=True)
    print(f"slate {DATE} -> {OUT}")
    global B2B
    B2B = SL.back_to_back(DATE)
    if refresh:
        O.load_env()
        evs = SL.events(DATE)
        snap = O.fetch_events([e["eventID"] for e in evs])
    else:
        snap = O.latest_snapshot()
    df = O.flatten(snap)
    ratings = M.team_ratings()
    ros = roster()
    global DF_G
    DF_G = df_goalies()
    global USAGE
    try:
        from features.live import usage
        uu = usage()
        USAGE = {(r["key"], r["last_team"]): r for r in uu.to_dict("records")}
        uniq = uu.key.value_counts()
        USAGE.update({r["key"]: r for r in uu[uu.key.map(uniq) == 1].to_dict("records")})
    except Exception as e:  # noqa: BLE001
        print("usage projection unavailable:", e)
        USAGE = {}
    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ---------- game models
    games, glines = {}, []
    for ev_id, g in df.groupby("eventID"):
        h, a = TEAM[g.home.iloc[0]], TEAM[g.away.iloc[0]]
        gf = {t: goalie_mix(t) for t in (h, a)}
        gm = M.game_model(h, a, GOALIES[h], GOALIES[a], ratings, gf_home=gf[h][0], gf_away=gf[a][0])
        gm["goalie_note"] = {t: gf[t][1] for t in (h, a)}
        games[(h, a)] = gm
        gg = g[g.entity.isin(["home", "away", "all"]) & (g.stat == "points") & ~g.alt]
        for _, r in gg.iterrows():
            if r.bt == "ml":
                p = gm["p_home"] if r.side == "home" else 1 - gm["p_home"]
            elif r.bt == "ou" and r.entity == "all" and r.line in gm["totals"]:
                ov, push = gm["totals"][r.line]
                p = ov if r.side == "over" else 1 - ov - push
            else:
                continue
            glines.append(dict(game=f"{a}@{h}", market=r.bt, side=r.side, line=r.line, book=r.book,
                               odds=r.odds, model_p=p, fair_odds=r.fair_odds))
    gl = pd.DataFrame(glines)
    # market fair (SGO consensus) where on same line
    gl["implied"] = gl.odds.map(O.american_to_prob)
    gl["model_ev"] = [ev(p, o) for p, o in zip(gl.model_p, gl.odds)]

    # ---------- player props
    mm = market_means(df)
    props = []
    pl = df[df.player.notna() & df.stat.isin(STAT_MAP) & (df.bt == "ou") & df.book.isin(["draftkings", "fanduel"])]
    for (pid, stat), g in pl.groupby(["entity", "stat"]):
        mk = STAT_MAP[stat]
        name = g.player.iloc[0]
        team = TEAM.get(g.team.iloc[0], "?")
        h, a = TEAM[g.home.iloc[0]], TEAM[g.away.iloc[0]]
        is_home = team == h
        opp = a if is_home else h
        rr = ros[(ros.team == team) & (ros.key == M.norm(name))]
        if rr.empty:
            role, pp, pos = "not in DF lineup", "-", "F"
        else:
            role, pp, pos = rr.role.iloc[0], rr.pp.iloc[0], rr.pos.iloc[0]
        rates = _rates(M.norm(name), pos)
        role_toi = ROLE_TOI.get(role)
        uk = re.sub(r"[^a-z]", "", M.norm(name))
        u = USAGE.get((uk, team)) or USAGE.get(uk)
        if u is not None and u["gp"] >= 10:
            # v2: fitted EWMA-blend projection (OOS MAE 1.87 min), 25% pull toward tonight's DF line role
            toi = 0.75 * u["toi_proj"] + 0.25 * role_toi if role_toi else u["toi_proj"]
        else:
            toi = 0.5 * rates["toi"] + 0.5 * role_toi if role_toi else rates["toi"]
        gm = games[(h, a)]
        lam_team = gm["lam_home"] if is_home else gm["lam_away"]
        opp_gf = gm["goalie_away"] if is_home else gm["goalie_home"]
        means = M.player_probs(rates, team, opp, is_home, lam_team, ratings, opp_gf, toi_override=toi,
                               own_b2b=team in B2B, opp_b2b=opp in B2B)
        # PP-role adjustment (history may not reflect new unit)
        ppm = {"PP1": 1.06, "PP2": 0.98, "-": 0.92}[pp]
        mean_model = means[mk] * (ppm if mk != "SOG" else (1 + (ppm - 1) / 2))
        mkt = mm.get((pid, mk))
        for (book, line, side), r in g.groupby(["book", "line", "side"]):
            r = r.iloc[0]
            p_model_over = M.prob_over(mk, mean_model, line)
            p_mkt_over = M.prob_over(mk, mkt[0], line) if mkt else np.nan
            pm = p_model_over if side == "over" else 1 - p_model_over
            pk = p_mkt_over if side == "over" else 1 - p_mkt_over
            props.append(dict(game=f"{a}@{h}", player=name, team=team, role=role, pp=pp, market=mk,
                              side=side, line=line, book=book, odds=int(r.odds), alt=bool(r.alt),
                              model_mean=mean_model, mkt_mean=mkt[0] if mkt else np.nan,
                              model_p=pm, mkt_p=pk, toi=toi, hist_min=rates["n_min"], note=rates["note"],
                              mkt_src=mkt[1] if mkt else ""))
    pr = pd.DataFrame(props)
    # level-calibrate model to market per market type (model is used for relative signal)
    u = pr.drop_duplicates(["player", "market"])
    CAL = (u.mkt_mean / u.model_mean).groupby(u.market).median().to_dict()
    pr["cal"] = pr.market.map(CAL)
    pr["model_mean"] = pr.model_mean * pr.cal
    pr["model_p"] = [M.prob_over(m, mu, ln) if s == "over" else 1 - M.prob_over(m, mu, ln)
                     for m, mu, ln, s in zip(pr.market, pr.model_mean, pr.line, pr.side)]
    pr["implied"] = pr.odds.map(O.american_to_prob)
    pr["blend_p"] = np.where(pr.mkt_p.notna(), MODEL_W * pr.model_p + (1 - MODEL_W) * pr.mkt_p, np.nan)
    pr["edge"] = pr.blend_p - pr.implied
    pr["ev"] = [ev(p, o) if pd.notna(p) else np.nan for p, o in zip(pr.blend_p, pr.odds)]
    pr["gap"] = pr.model_p - pr.mkt_p
    pr["fair_blend"] = pr.blend_p.map(lambda p: O.prob_to_american(p) if pd.notna(p) else None)
    # ceiling = worst price still worth it: blended p minus 2.5pt margin
    pr["ceiling"] = (pr.blend_p - MIN_EDGE).map(lambda p: O.prob_to_american(p) if pd.notna(p) and p > 0 else None)
    pr["decision"] = np.select(
        [pr.mkt_p.isna(),
         pr.gap.abs() > DISAGREE,
         (pr.edge >= MIN_EDGE) & (pr.ev >= MIN_EV) & ((pr.implied >= 0.18) | ((pr.market == "G") & (pr.line == 0.5))),
         (pr.edge >= 0.01) & (pr.ev >= 0.02)],
        ["no-market", "data-check", "BET", "lean"], default="pass")
    pr["run_ts_utc"] = run_ts
    pr["snapshot"] = os.path.basename(snap)
    # best price per selection across DK/FD
    pr = pr.sort_values("ev", ascending=False)
    pr.to_csv(f"{OUT}/props_all.csv", index=False)
    gl.to_csv(f"{OUT}/game_lines.csv", index=False)
    pd.DataFrame([dict(game=f"{a}@{h}", lam_home=v["lam_home"], lam_away=v["lam_away"], p_home=v["p_home"],
                       **{f"p_over_{k}": v["totals"][k][0] for k in v["totals"]},
                       goalie_f_home=v["goalie_home"], goalie_f_away=v["goalie_away"])
                  for (h, a), v in games.items()]).to_csv(f"{OUT}/game_model.csv", index=False)
    return pr, gl, games


_RC = {}


def _rates(key, pos):
    if key not in _RC:
        _RC[key] = M.player_rates(key, pos)
    return _RC[key]



if __name__ == "__main__":
    pr, gl, games = main(refresh="--refresh" in sys.argv)
    pd.set_option("display.width", 250)
    for k, v in games.items():
        print(k, {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items() if kk != "totals"},
              {L: round(o, 3) for L, (o, _) in v["totals"].items()})
    best = pr.sort_values("ev", ascending=False).drop_duplicates(["player", "market", "side", "line"])
    cols = ["game", "player", "role", "pp", "market", "side", "line", "book", "odds", "model_p", "mkt_p",
            "blend_p", "edge", "ev", "ceiling", "decision"]
    print(best[best.decision.isin(["BET", "lean"])][cols].head(40).to_string(float_format=lambda x: f"{x:.3f}"))
    print(best.decision.value_counts())
