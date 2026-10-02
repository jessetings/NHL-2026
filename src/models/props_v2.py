"""Prop model v2: strength-split, shot-quality, matchup-aware player means (SOG, goals, assists, points).

Every input is as-of (strictly prior games): src/features/build.py (TOI, EWMA rates) + src/features/shotq.py.

  SOG  = s * [ EV_sog60 * EVh * R_ev_sa^a  +  PP_sog60 * PPh * PKopp^k * R_pk_sa^b ] * home^h * rest
  G    = g * [ EV_xg60  * EVh * R_ev_xga^c +  PP_xg60  * PPh * PKopp^k * R_pk_xga^d ] * finish^f * goalie * home * rest
  A    = a * [ EV_a60   * EVh * E_ev^e     +  PP_a60   * PPh * PKopp^k * E_pp^p ]     * goalie * home * rest
  PTS  = same structure as A with EV/PP points rates
where EVh/PPh = projected EV/PP hours (EWMA 5/20 blend), R_* = opponent allowed rate / league,
PKopp = opponent PK time per game / league (more penalties taken -> more PP time), E_* = own team xG-for x opp
xG-against environment, goalie = exp(t1 * GSAx/100 + t2 * HD save-above-expected) for the opposing starter.
Parameters are fit by maximum likelihood (NB2 for SOG, Poisson otherwise) on 2023-24 + 2024-25 and evaluated
out-of-sample on 2025-26 against the v1 opportunity model (EWMA per-60 x TOI) used in H3.
Usage: python src/models/props_v2.py      -> data/curated/models/props_v2.json, reports/props_v2_eval.md
"""
import json
import os

import duckdb
import numpy as np
import pandas as pd
from scipy import optimize, special, stats

CUR = "data/curated"
TRAIN = (20232024, 20242025)
TEST = (20252026,)
PARAMS = f"{CUR}/models/props_v2.json"


def frame():
    con = duckdb.connect()
    d = con.execute(f"""
        select f.*, p.* exclude (game_id, player_id, team, date, season, gp_prior),
               p.gp_prior as gp_shotq
        from '{CUR}/features/player_game.parquet' f
        join '{CUR}/features/shotq_player.parquet' p using (game_id, player_id)
        where f.game_type = 2 and f.season >= 20232024""").df()
    t = pd.read_parquet(f"{CUR}/features/shotq_team.parquet")
    tc = [c for c in t.columns if c not in ("game_id", "team", "date", "season")]
    d = d.merge(t[["game_id", "team"] + tc].add_prefix("own_").rename(columns={"own_game_id": "game_id", "own_team": "team"}),
                on=["game_id", "team"], how="left")
    d = d.merge(t[["game_id", "team"] + tc].add_prefix("opp_").rename(columns={"opp_game_id": "game_id", "opp_team": "opp"}),
                on=["game_id", "opp"], how="left")
    lmf = pd.read_parquet(f"{CUR}/features/lines_player_game.parquet")[["game_id", "player_id", "lm_ev_xg60", "lm_ev_pts60", "lm_ev_sog60", "pp_rank"]]
    d = d.merge(lmf, on=["game_id", "player_id"], how="left")
    g = pd.read_parquet(f"{CUR}/features/shotq_goalie.parquet")[["game_id", "goalie_id", "gsax100", "hd_svx", "gp_prior"]]
    d = d.merge(g.rename(columns={"goalie_id": "opp_goalie_id", "gp_prior": "og_gp"}), on=["game_id", "opp_goalie_id"], how="left")
    return d


LG_COLS = ["opp_pk_sec_pg", "opp_a_ev_sog60", "opp_a_pp_sog60", "opp_a_ev_xg60", "opp_a_pp_xg60", "opp_a_ev_hd60",
           "own_f_ev_xg60", "own_f_pp_xg60", "lm_ev_xg60", "lm_ev_pts60", "lm_ev_sog60"]


def league(d):
    return d[d.season.isin(TRAIN)][LG_COLS].median()


def prep(d, lg=None, live=False):
    if not live:
        d = d[(d.gp_career_prior >= 10) & d.own_gp_prior.ge(10) & d.opp_gp_prior.ge(10)].copy()
    else:
        d = d.copy()
    lg = league(d) if lg is None else lg
    d["EVh"] = (0.6 * d.ev_sec_ewm5.fillna(d.ev_sec_ewm) + 0.4 * d.ev_sec_ewm20.fillna(d.ev_sec_ewm)) / 3600
    d["PPh"] = (0.6 * d.pp_sec_ewm5.fillna(0) + 0.4 * d.pp_sec_ewm20.fillna(0)) / 3600
    d["PKopp"] = (d.opp_pk_sec_pg / lg.opp_pk_sec_pg).clip(0.5, 2)
    for col in ("a_ev_sog60", "a_pp_sog60", "a_ev_xg60", "a_pp_xg60", "a_ev_hd60"):
        d[f"R_{col}"] = (d[f"opp_{col}"] / lg[f"opp_{col}"]).clip(0.5, 2)
    d["E_ev"] = (d.own_f_ev_xg60 / lg.own_f_ev_xg60 * d.opp_a_ev_xg60 / lg.opp_a_ev_xg60).clip(0.4, 2.5)
    d["E_pp"] = (d.own_f_pp_xg60 / lg.own_f_pp_xg60 * d.opp_a_pp_xg60 / lg.opp_a_pp_xg60).clip(0.4, 2.5)
    for c in ("lm_ev_xg60", "lm_ev_pts60", "lm_ev_sog60"):     # linemate quality (EV), 1.0 when unknown
        d[f"LM_{c}"] = (d[c] / lg[c]).clip(0.4, 2.5).fillna(1.0) if c in d else 1.0
    d["gsax"] = d.gsax100.fillna(0).clip(-3, 3)
    d["hdsv"] = (d.hd_svx.fillna(0) * 10).clip(-2, 2)
    d["home"] = d.is_home.astype(float)
    d["b2b_own"] = d.b2b.fillna(0).astype(float)
    d["isD"] = (d.pg == "D").astype(float)
    # v1 opportunity mean (H3 baseline)
    toi = 0.5 * d.toi_min_ewm15 + 0.5 * d.toi_min_ewm40
    d["v1_SOG"] = (0.5 * d.sog60_ewm15 + 0.5 * d.sog60_ewm40) * toi / 60
    d["v1_G"] = (0.4 * d.goals60_ewm15 + 0.6 * d.goals60_ewm40) * toi / 60
    d["v1_A"] = (0.4 * d.assists60_ewm15 + 0.6 * d.assists60_ewm40) * toi / 60
    d["v1_PTS"] = (0.4 * d.points60_ewm15 + 0.6 * d.points60_ewm40) * toi / 60
    d["ev_pts60"] = d.ev_pg60 + d.ev_pa60
    d["pp_pts60"] = d.pp_pg60 + d.pp_pa60
    if live:
        return d
    return d.dropna(subset=["EVh", "ev_sog60", "R_a_ev_sog60", "R_a_pp_sog60", "v1_SOG"])


LMCOL = {"SOG": "LM_lm_ev_sog60", "G": "LM_lm_ev_pts60", "A": "LM_lm_ev_xg60", "PTS": "LM_lm_ev_xg60"}
SPEC = {   # market: (EV rate col, PP rate col, EV ratio col, PP ratio col, goalie?, finish?)
    "SOG": ("ev_sog60", "pp_sog60", "R_a_ev_sog60", "R_a_pp_sog60", False, False),
    "G": ("ev_xg60", "pp_xg60", "R_a_ev_xg60", "R_a_pp_xg60", True, True),
    "A": ("ev_pa60", "pp_pa60", "E_ev", "E_pp", True, False),
    "PTS": ("ev_pts60", "pp_pts60", "E_ev", "E_pp", True, False),
}
TARGET = {"SOG": "sog", "G": "goals", "A": "assists", "PTS": "points"}
NAMES = ["log_s", "dD", "a_ev", "a_pp", "k_pk", "w_pp", "h", "b2b", "t_gsax", "t_hd", "f_fin", "l_lm"]


def mean(x, d, mk):
    ev, pp, rev, rpp, goalie, fin = SPEC[mk]
    p = dict(zip(NAMES, x))
    lmq = d[LMCOL[mk]] ** p.get("l_lm", 0.0) if LMCOL[mk] in d else 1.0
    m = d[ev] * d.EVh * d[rev] ** p["a_ev"] * lmq + np.exp(p["w_pp"]) * d[pp] * d.PPh * d.PKopp ** p["k_pk"] * d[rpp] ** p["a_pp"]
    m = m * np.exp(p["log_s"] + p["dD"] * d.isD + p["h"] * (d.home - 0.5) + p["b2b"] * d.b2b_own)
    if goalie:
        m = m * np.exp(p["t_gsax"] * d.gsax + p["t_hd"] * d.hdsv)
    if fin:
        m = m * d.finish.clip(0.6, 1.6) ** p["f_fin"]
    return m.clip(1e-4, None)


def nll(mu, y, alpha=None):
    if alpha:      # NB2
        n = 1 / alpha
        return -(special.gammaln(y + n) - special.gammaln(n) - special.gammaln(y + 1)
                 + n * np.log(n / (n + mu)) + y * np.log(mu / (n + mu)))
    return -(y * np.log(mu) - mu - special.gammaln(y + 1))


def fit(d, mk):
    tr = d[d.season.isin(TRAIN)]
    y = tr[TARGET[mk]].values
    alpha = 0.04 if mk == "SOG" else None
    x0 = np.array([0, 0, 0.5, 0.5, 0.5, 0, 0.05, -0.03, 0, 0, 0.5, 0.0])
    fixed_off = {"t_gsax", "t_hd"} if not SPEC[mk][4] else set()
    if not SPEC[mk][5]:
        fixed_off |= {"f_fin"}
    free = [i for i, n in enumerate(NAMES) if n not in fixed_off]

    def obj(z):
        x = x0.copy(); x[free] = z
        x_ = x.copy()
        for i, n in enumerate(NAMES):
            if n in fixed_off:
                x_[i] = 0
        return nll(mean(x_, tr, mk).values, y, alpha).mean()
    r = optimize.minimize(obj, x0[free], method="L-BFGS-B")
    x = x0.copy(); x[free] = r.x
    for i, n in enumerate(NAMES):
        if n in fixed_off:
            x[i] = 0
    if mk == "SOG":     # refit NB alpha at the optimum
        mu = mean(x, tr, mk).values
        a = optimize.minimize_scalar(lambda a: nll(mu, y, a).mean(), bounds=(0.001, 0.3), method="bounded").x
        return x, float(a)
    return x, None


def evaluate(d, mk, x, alpha):
    te = d[d.season.isin(TEST)].copy()
    y = te[TARGET[mk]].values
    mu2 = mean(x, te, mk).values
    mu1 = te[f"v1_{mk}"].clip(1e-4, None).values
    # v1 rescaled to the same overall level (fair comparison: calibrate level on train)
    tr = d[d.season.isin(TRAIN)]
    s1 = tr[TARGET[mk]].sum() / tr[f"v1_{mk}"].sum()
    mu1 = mu1 * s1
    a = alpha if mk == "SOG" else None
    out = dict(market=mk, n=len(te), ll_v1=nll(mu1, y, a).mean(), ll_v2=nll(mu2, y, a).mean())
    out["delta_x1000"] = 1000 * (out["ll_v2"] - out["ll_v1"])
    dd = nll(mu2, y, a) - nll(mu1, y, a)
    out["se_x1000"] = 2000 * dd.std() / np.sqrt(len(dd))
    # line-level Brier at the most common prop lines
    lines = {"SOG": (1.5, 2.5, 3.5), "G": (0.5,), "A": (0.5,), "PTS": (0.5, 1.5)}[mk]
    for L in lines:
        k = int(np.floor(L))
        if mk == "SOG":
            n = 1 / alpha
            p1, p2 = stats.nbinom.sf(k, n, n / (n + mu1)), stats.nbinom.sf(k, n, n / (n + mu2))
        else:
            p1, p2 = stats.poisson.sf(k, mu1), stats.poisson.sf(k, mu2)
        h = (y > L).astype(float)
        out[f"brier_v1@{L}"] = np.mean((p1 - h) ** 2)
        out[f"brier_v2@{L}"] = np.mean((p2 - h) ** 2)
    return out


def main():
    global LG
    raw = frame()
    raw = raw[(raw.gp_career_prior >= 10) & raw.own_gp_prior.ge(10) & raw.opp_gp_prior.ge(10)]
    LG = league(raw)
    d = prep(raw, LG)
    print(f"rows {len(d):,} (train {d.season.isin(TRAIN).sum():,}, test {d.season.isin(TEST).sum():,})")
    params, rows = {}, []
    for mk in ("SOG", "G", "A", "PTS"):
        x, alpha = fit(d, mk)
        params[mk] = dict(zip(NAMES, map(float, x)), alpha=alpha)
        r = evaluate(d, mk, x, alpha)
        rows.append(r)
        print(mk, {k: round(v, 3) for k, v in params[mk].items() if v is not None})
    os.makedirs(os.path.dirname(PARAMS), exist_ok=True)
    params["_lg"] = {k: float(v) for k, v in LG.items()}
    json.dump(params, open(PARAMS, "w"), indent=1)
    R = pd.DataFrame(rows)
    print(R.round(5).to_string())
    os.makedirs("reports", exist_ok=True)
    R.round(5).to_csv("reports/props_v2_eval.csv", index=False)



def predict_all(d=None):
    """Means for every as-of row (for backtests and live use) -> data/curated/models/props_v2_pred.parquet."""
    P = json.load(open(PARAMS))
    d = prep(frame(), pd.Series(P["_lg"])) if d is None else d
    out = d[["game_id", "player_id", "season"]].copy()
    for mk, p in P.items():
        if mk.startswith("_"):
            continue
        out[f"mu_{mk}"] = mean(np.array([p.get(n, 0.0) for n in NAMES]), d, mk).values
    out["alpha_SOG"] = P["SOG"]["alpha"]
    out.to_parquet(f"{CUR}/models/props_v2_pred.parquet", index=False)
    return out



def live(date, goalies=None):
    """Next-game v2 means for every dressed skater on `date` (DailyFaceoff lines; NHL schedule).

    goalies: optional {team: goalie name} for the expected starters (else each team's most-used goalie).
    Returns one row per player: player_id, key (normalized name), team, opp, is_home, mu_SOG/G/A/PTS.
    """
    import re
    import sys
    import unicodedata

    import requests
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import model as M
    import slate as SL

    def key(s):
        s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z]", "", s)

    P = json.load(open(PARAMS))
    lg = pd.Series(P["_lg"])
    sched = requests.get(f"https://api-web.nhle.com/v1/schedule/{date}", timeout=30).json()
    day = [w for w in sched["gameWeek"] if w["date"] == date]
    games = [(g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"]) for g in (day[0]["games"] if day else []) if g["gameType"] in (2, 3)]
    b2b = SL.back_to_back(date)
    con = duckdb.connect()
    ppl = con.execute(f"""select player_id, first, last from '{CUR}/nhl_players.parquet'""").df()
    ppl["key"] = (ppl["first"].fillna("") + ppl["last"].fillna("")).map(key)
    lastteam = con.execute(f"""select playerId player_id, arg_max(team, game_id) team, arg_max(position, game_id) pos
                                  from '{CUR}/nhl_skater_game.parquet' group by 1""").df()
    ppl = ppl.merge(lastteam, on="player_id", how="left")
    sp = pd.read_parquet(f"{CUR}/features/shotq_player.parquet")
    sp = sp[sp.game_id == 9_999_999_999]
    st = pd.read_parquet(f"{CUR}/features/shotq_team.parquet")
    st = st[st.game_id == 9_999_999_999].set_index("team")
    sg = pd.read_parquet(f"{CUR}/features/shotq_goalie.parquet")
    sg = sg[sg.game_id == 9_999_999_999]
    gl_names = con.execute(f"""select g.playerId goalie_id, any_value(p.first || ' ' || p.last) as gname, arg_max(g.team, g.game_id) as team,
                                      count(*) n from '{CUR}/nhl_goalie_game.parquet' g join '{CUR}/nhl_players.parquet' p
                                      on p.player_id = g.playerId group by 1""").df()
    gl_names["key"] = gl_names.gname.map(key)
    lines = M.load_lines()
    slug = {v: k for k, v in SL.SLUG.items()}
    # tonight's PP units (DailyFaceoff): role changes vs history. Heuristic, NOT backtested (historical PP-unit
    # labels from shifts leak that game's PP volume): promoted -> PP time >= 60% of the unit's typical
    # (PP1 ~3.0 min, PP2 ~1.5 min); dropped from both units -> history halved.
    PP_TYP = {"pp1": 3.0 * 60, "pp2": 1.5 * 60}
    ppu = {}
    for tslug, pls in lines.items():
        for pl in pls:
            g_ = (pl.get("group") or "")
            if g_ in PP_TYP:
                ppu[(tslug, key(pl["name"]))] = g_
    rows = []
    for home, away in games:
        for team, opp, is_home in ((home, away, 1.0), (away, home, 0.0)):
            gname = (goalies or {}).get(opp)
            gk = gl_names[gl_names.key == key(gname)] if gname else gl_names[gl_names.team == opp].nlargest(1, "n")
            g_row = sg[sg.goalie_id.isin(gk.goalie_id)].head(1)
            for pl in lines.get(slug.get(team), []):
                grp = pl.get("group") or ""
                if grp[:1] not in ("f", "d") or not grp[1:].isdigit():
                    continue
                k = key(pl["name"])
                cand = ppl[ppl.key == k]
                if len(cand) > 1:
                    cand = cand[cand.team == team] if (cand.team == team).any() else cand
                if len(cand) > 1:                       # same name on one team: match position to the DF unit
                    cand = cand[(cand.pos == "D") == (grp[:1] == "d")]
                if len(cand) != 1:
                    continue
                if cand.empty:
                    continue
                pid = int(cand.player_id.iloc[0])
                last_team = cand.team.iloc[0]
                r = sp[sp.player_id == pid]
                if r.empty or team not in st.index or opp not in st.index:
                    continue
                r = r.iloc[0].to_dict()
                for c, v in st.loc[team].items():
                    r[f"own_{c}"] = v
                for c, v in st.loc[opp].items():
                    r[f"opp_{c}"] = v
                r.update(dict(name=pl["name"], key=k, team=team, opp=opp, is_home=is_home, b2b=float(team in b2b),
                              unit=grp, gsax100=g_row.gsax100.iloc[0] if len(g_row) else 0.0,
                              hd_svx=g_row.hd_svx.iloc[0] if len(g_row) else 0.0,
                              ev_sec_ewm5=r["q_ev_sec_e5"], ev_sec_ewm20=r["q_ev_sec_e20"],
                              pp_sec_ewm5=r["q_pp_sec_e5"], pp_sec_ewm20=r["q_pp_sec_e20"],
                              toi_min_ewm15=np.nan, toi_min_ewm40=np.nan, sog60_ewm15=np.nan, sog60_ewm40=np.nan,
                              goals60_ewm15=np.nan, goals60_ewm40=np.nan, assists60_ewm15=np.nan,
                              assists60_ewm40=np.nan, points60_ewm15=np.nan, points60_ewm40=np.nan))
                unit_pp = ppu.get((slug.get(team), k))
                for c in ("pp_sec_ewm5", "pp_sec_ewm20"):
                    if unit_pp:
                        r[c] = max(r[c] or 0.0, 0.6 * PP_TYP[unit_pp])
                    elif any(t_ == slug.get(team) for t_, _ in ppu):          # team has DF PP units listed
                        r[c] = 0.5 * (r[c] or 0.0)
                r["pp_unit"] = unit_pp or "-"
                r["new_team"] = bool(isinstance(last_team, str) and last_team != team)
                rows.append(r)
    R = pd.DataFrame(rows)
    # linemates from tonight's DailyFaceoff units (same team + same f#/d# group), their next-game EV rates
    R["ev_pts60_"] = R.ev_pg60 + R.ev_pa60
    for c, src in (("lm_ev_xg60", "ev_xg60"), ("lm_ev_pts60", "ev_pts60_"), ("lm_ev_sog60", "ev_sog60")):
        R[c] = [R[(R.team == t) & (R.unit == u) & (R.player_id != p)][src].mean() for t, u, p in zip(R.team, R.unit, R.player_id)]
    d = prep(R, lg, live=True)
    out = d[["player_id", "name", "key", "team", "opp", "is_home", "unit", "pp_unit", "gp_prior", "new_team"]].copy()
    for mk, p in P.items():
        if not mk.startswith("_"):
            out[f"mu_{mk}"] = mean(np.array([p.get(n, 0.0) for n in NAMES]), d, mk).values
    out["alpha_SOG"] = P["SOG"]["alpha"]
    return out


if __name__ == "__main__":
    main()
    predict_all()
