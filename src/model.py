"""Lightweight pre-game models: team goal expectations + player prop probabilities.

Data: MoneyPuck season summaries (2024-25, 2025-26, 2026-27 to date), DailyFaceoff
lines/goalies. Rates are TOI-weighted across seasons and shrunk toward positional priors.
"""
import json
import re
import unicodedata
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy import stats

MP = "data/raw/moneypuck"
SEASON_W = {2026: 1.0, 2025: 1.0, 2024: 0.45}   # 2026 = current season (tiny sample)
PRIOR_MIN = 250                                  # prior strength, all-situation minutes
LEAGUE_GOALS_PER_TEAM = 3.05                     # recent NHL scoring environment, incl. EN
HOME_ADV = 1.04
TEAM_SHRINK = 0.55                               # keep 55% of last-season team signal
GOALIE_SHRINK = 0.35                             # GSAx/shot credibility for a single goalie
SOG_NB_ALPHA = 0.045                             # NB2 alpha for player SOG (fitted, see nb_tail)

NAME_FIX = {"nick robertson": "nicholas robertson", "t.j. hughes": "tj hughes",
            "matt schaefer": "matthew schaefer", "alex laferriere": "alex laferriere"}


def norm(n):
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[^a-z .'-]", "", n).strip()
    n = n.replace(".", "").replace("  ", " ")
    return NAME_FIX.get(n, n)


# ---------------------------------------------------------------- loading
@lru_cache(None)
def load_skaters():
    fr = []
    for s in SEASON_W:
        d = pd.read_csv(f"{MP}/skaters_{s}.csv")
        fr.append(d)
    d = pd.concat(fr)
    d["key"] = d["name"].map(norm)
    return d


@lru_cache(None)
def load_teams():
    fr = [pd.read_csv(f"{MP}/teams_{s}.csv").assign(season=s) for s in SEASON_W]
    return pd.concat(fr)


@lru_cache(None)
def load_goalies():
    fr = [pd.read_csv(f"{MP}/goalies_{s}.csv").assign(season=s) for s in SEASON_W]
    d = pd.concat(fr)
    d["key"] = d["name"].map(norm)
    return d


# ---------------------------------------------------------------- teams
def team_ratings():
    t = load_teams()
    t = t[t.situation == "all"].copy()
    t["w"] = t.season.map(SEASON_W)
    cols = ["xGoalsFor", "xGoalsAgainst", "goalsFor", "goalsAgainst",
            "shotsOnGoalFor", "shotsOnGoalAgainst", "iceTime"]
    for c in cols:
        t[c] = t[c] * t["w"]
    g = t.groupby("team")[cols].sum()
    per60 = g[cols[:-1]].div(g["iceTime"], axis=0) * 3600
    lg = per60.mean()
    r = pd.DataFrame(index=per60.index)
    # offence: 70% xG, 30% actual goals; defence uses xGA only (goalie handled separately)
    off = 0.7 * per60.xGoalsFor / lg.xGoalsFor + 0.3 * per60.goalsFor / lg.goalsFor
    r["off"] = 1 + TEAM_SHRINK * (off - 1)
    r["def"] = 1 + TEAM_SHRINK * (per60.xGoalsAgainst / lg.xGoalsAgainst - 1)
    r["sog_for"] = 1 + TEAM_SHRINK * (per60.shotsOnGoalFor / lg.shotsOnGoalFor - 1)
    r["sog_against"] = 1 + TEAM_SHRINK * (per60.shotsOnGoalAgainst / lg.shotsOnGoalAgainst - 1)
    r["sog_against_raw60"] = per60.shotsOnGoalAgainst
    r["sog_for_raw60"] = per60.shotsOnGoalFor
    return r


def goalie_factor(name):
    """Multiplier on goals allowed from shrunk GSAx per unblocked attempt."""
    g = load_goalies()
    g = g[(g.situation == "all") & (g.key == norm(name))]
    if g.empty:
        return 1.0, "no data"
    w = g.season.map(SEASON_W)
    xg, ga, att = (g.xGoals * w).sum(), (g.goals * w).sum(), (g.unblocked_shot_attempts * w).sum()
    if xg <= 0:
        return 1.0, "no data"
    # credibility grows with sample: k attempts for 50% weight
    cred = att / (att + 2500)
    ratio = ga / xg
    f = 1 + GOALIE_SHRINK * cred * 2 * (ratio - 1)
    return float(np.clip(f, 0.88, 1.12)), f"GA/xGA {ratio:.3f} over {att:.0f} att"


def game_model(home, away, home_goalie, away_goalie, ratings):
    """Return team lambdas and ML/total probabilities (regulation Poisson + OT coin)."""
    gh, _ = goalie_factor(home_goalie)
    ga, _ = goalie_factor(away_goalie)
    lam_h = LEAGUE_GOALS_PER_TEAM * ratings.loc[home, "off"] * ratings.loc[away, "def"] * ga * np.sqrt(HOME_ADV)
    lam_a = LEAGUE_GOALS_PER_TEAM * ratings.loc[away, "off"] * ratings.loc[home, "def"] * gh / np.sqrt(HOME_ADV)
    # regulation ~ 94% of goals (rest EN/OT handled via OT step)
    rh, ra = lam_h * 0.97, lam_a * 0.97
    k = np.arange(0, 15)
    ph, pa = stats.poisson.pmf(k, rh), stats.poisson.pmf(k, ra)
    M = np.outer(ph, pa)
    p_home_reg = np.tril(M, -1).sum()
    p_tie = np.trace(M)
    p_home = p_home_reg + p_tie * 0.52
    tot = {}
    for L in (5.5, 6.0, 6.5):
        over = 0.0
        push = 0.0
        for i in k:
            for j in k:
                s = i + j + (1 if i == j else 0)   # OT/SO adds exactly one goal
                if s > L:
                    over += M[i, j]
                elif s == L:
                    push += M[i, j]
        tot[L] = (over, push)
    return dict(lam_home=lam_h, lam_away=lam_a, p_home=p_home, p_tie_reg=p_tie, totals=tot,
                goalie_home=gh, goalie_away=ga)


# ---------------------------------------------------------------- players
POS_PRIOR = {  # per-60 all-situations priors (middle-six forward / 2nd-pair D)
    "F": dict(sog=6.6, ixg=0.80, g=0.80, a=1.05, pts=1.85),
    "D": dict(sog=4.3, ixg=0.22, g=0.22, a=0.85, pts=1.07),
}


def player_rates(key, pos_hint="F"):
    s = load_skaters()
    r = s[(s.key == key) & (s.situation == "all")].copy()
    pos = "D" if (not r.empty and (r.position == "D").any()) or pos_hint == "D" else "F"
    pr = POS_PRIOR[pos]
    if r.empty:
        return dict(pos=pos, gp=0, toi=15.0 if pos == "F" else 18.0, **{k: v * 0.85 for k, v in pr.items()},
                    n_min=0, note="no NHL data: 85% of positional prior")
    r["w"] = r.season.map(SEASON_W)
    mins = (r.icetime * r.w).sum() / 60
    gp = (r.games_played * r.w).sum()
    # TOI projection: favour most recent seasons
    toi = mins / gp
    def rate(col):
        return (r[col] * r.w).sum() / mins * 60
    raw = dict(sog=rate("I_F_shotsOnGoal"), ixg=rate("I_F_xGoals"), g=rate("I_F_goals"),
               a=rate("I_F_primaryAssists") + rate("I_F_secondaryAssists"), pts=rate("I_F_points"))
    shr = {k: (raw[k] * mins + pr[k] * PRIOR_MIN) / (mins + PRIOR_MIN) for k in raw}
    # goals: xG rate x empirically-Bayes-shrunk finishing multiplier (research digest 01 §6):
    #   forwards: (G + 64) / (xG + 64) on raw career-window totals (K = 64 xG ~ 775 unblocked attempts)
    #   defensemen: no repeatable finishing (YoY r ~ -0.03) -> xG only
    if pos == "D":
        shr["g"] = shr["ixg"]
    else:
        g_tot, xg_tot = (r.I_F_goals * r.w).sum(), (r.I_F_xGoals * r.w).sum()
        shr["g"] = shr["ixg"] * (g_tot + 64) / (xg_tot + 64)
    return dict(pos=pos, gp=float(r.games_played.sum()), toi=toi, n_min=mins, note="", **shr)


def nb_tail(mean, k, alpha=None):
    """P(X >= k) for NB2 with var = mean + alpha*mean^2.

    alpha fitted on 177k NHL skater-games 2022-26 (pregame mean): F 0.039, D 0.031; 0.045 adds
    allowance for pregame mean uncertainty. Empirically SOG is only mildly overdispersed.
    """
    a = SOG_NB_ALPHA if alpha is None else alpha
    if a <= 1e-6:
        return float(stats.poisson.sf(k - 1, mean))
    n = 1 / a
    p = n / (n + mean)
    return float(stats.nbinom.sf(k - 1, n, p))


def player_probs(rates, team, opp, is_home, team_lam, ratings, opp_goalie_f, toi_override=None):
    toi = toi_override or rates["toi"]
    ha = np.sqrt(HOME_ADV) if is_home else 1 / np.sqrt(HOME_ADV)
    sog_mult = ratings.loc[opp, "sog_against"] * (1.02 if is_home else 0.98)
    # scoring environment relative to league for this team tonight
    env = team_lam / LEAGUE_GOALS_PER_TEAM
    m = dict(
        SOG=rates["sog"] * toi / 60 * sog_mult,
        G=rates["g"] * toi / 60 * ratings.loc[opp, "def"] * opp_goalie_f * ha,  # EN goals already in 'all' rates
        A=rates["a"] * toi / 60 * env,
        PTS=rates["pts"] * toi / 60 * env,
    )
    return m


def prob_over(market, mean, line):
    k = int(np.floor(line)) + 1   # over 2.5 -> 3+
    if market == "SOG":
        return nb_tail(mean, k)
    return float(stats.poisson.sf(k - 1, mean))


def load_lines():
    return json.load(open("data/raw/nhl/df_lines.json"))
