"""Game simulator v1: time-stepped, state-dependent, vectorised over simulations.

Regulation is simulated in DT-second steps. In each step, each team scores with a probability given by:
  base team rate (goalie-present, per 60) x period/score-state multiplier (fitted, src/sim/fit.py) x shared pace
When a team trails late in P3, it pulls its goalie with the fitted pulled-share by deficit and time remaining.
Then the extra-attacker rate (6.4/60) applies for the trailing team and the empty-net rate (14.5/60) for the other.
A tie after regulation goes to 3-on-3 OT (68% decided, home share 52.4% adjusted by strength), else a shootout
coin flip. Shootout goals are not credited to players.

Players:
  - Each goal goes to a scorer by goal shares (pregame lambda_i / lambda_team; remainder = "other").
  - 0-2 assists from teammates by assist shares (primary 90%, secondary 65% of goals; excluding the scorer).
  - Team SOG = goalie-present goals + non-goal shots ~ NB(mean from pregame, trailing boost).
  - Player SOG = own goalie-present goals + multinomial split of non-goal shots by SOG shares.
  - Saves = opponent SOG - opponent goalie-present goals.
Common random numbers: seeded by (seed, game_key) so scenario comparisons share randomness.

Calibration v1 (2023-26 regular season, 3,936 games; league-average teams):
                 total  var/mean  corr(h,a)  reg tie  EN/game  home win
  empirical      6.19   0.863     -0.123     0.221    0.376    0.542
  simulator      6.36   0.839     -0.126     0.218    0.390    0.541   (after pull-lookup bug fix)
Knobs: possession split sd 0.08 (negative dependence), post-goal cooldown x0.5 for 60 s (underdispersion),
EN/extra-attacker scale 1.3, pace cv 0.03. Simulated pulled time 1.43 min/game vs 1.35 empirical.
Per game, team rates are solved to the de-vigged market total and moneyline.
"""
import hashlib
import json

import numpy as np

PARAMS = json.load(open("data/curated/sim/params.json"))
DT = 20                     # seconds per step
# EN / extra-attacker per-60 rates are fit over all goalie-out time (incl. delayed penalties); scale 1.3 matches
# per-game EN goals (0.376) given the simulated late pulled time.
EN_SCALE = 1.3
N_DEFAULT = 65_536


def _seed(key, seed=0):
    return int(hashlib.sha256(f"{seed}|{key}".encode()).hexdigest()[:12], 16)


def state_mult():
    """Multiplier table [period(1-3)][diff -2..2] relative to the overall goalie-present mean."""
    r = PARAMS["rate_by_period_state"]
    vals = np.array([[r[f"{p}|{d}"] for d in range(-2, 3)] for p in (1, 2, 3)])
    return vals / np.nanmean(vals)


def pull_prob(deficit, remain):
    s = PARAMS["share_time_goalie_pulled"]
    d = min(deficit, 3)
    for lo, hi in ((0, 60), (60, 120), (120, 180), (180, 240), (240, 360)):
        if lo <= remain < hi:
            return s.get(f"{d}|{lo}-{hi}") or 0.0
    return 0.0


def simulate(home, away, n=N_DEFAULT, seed=0, pace_cv=0.03, game_key="g", split_sd=0.08, en_scale=None,
             cooldown=0.5, cooldown_steps=3):
    """home/away: dict(rate60=goalie-present regulation goals per 60, sog=expected team SOG,
                       players={name: dict(g=goal_share, a=assist_share, s=sog_share)})"""
    rng = np.random.default_rng(_seed(game_key, seed))
    M = state_mult()
    k = 1 / pace_cv ** 2
    pace = rng.gamma(k, 1 / k, n)
    # possession split: one team's dominance suppresses the other (negative dependence, underdispersed totals)
    split = np.clip(rng.normal(0, split_sd, n), -0.6, 0.6)
    ens = EN_SCALE if en_scale is None else en_scale
    hs = np.zeros(n, np.int16)
    as_ = np.zeros(n, np.int16)
    h_en = np.zeros(n, np.int16)        # goals scored INTO an empty net by home (away pulled)
    a_en = np.zeros(n, np.int16)
    h_gp = np.zeros(n, np.int16)        # goalie-present / extra-attacker goals (credited to shooters normally)
    a_gp = np.zeros(n, np.int16)
    steps = 3600 // DT
    pulled_sec = np.zeros(n, np.int32)
    cool = np.zeros(n, np.int16)     # steps remaining in post-goal cooldown
    first = np.zeros(n, np.int8)     # 1 = home scored first, 2 = away, 0 = none yet
    pull_cache = {}
    for i in range(steps):
        t = i * DT
        p = min(t // 1200, 2)
        remain = 3600 - t
        diff = np.clip(hs - as_, -2, 2)
        mh = M[p, diff + 2]
        ma = M[p, -diff + 2]
        lam_h = home["rate60"] * mh * pace * (1 + split) * DT / 3600
        lam_a = away["rate60"] * ma * pace * (1 - split) * DT / 3600
        if p == 2 and remain <= 360:
            deficit_h = as_ - hs
            key = (remain,)
            if key not in pull_cache:
                pull_cache[key] = np.array([0.0] + [pull_prob(d, remain) for d in (1, 2, 3, 4, 5)])
            tbl = pull_cache[key]
            h_pull = rng.random(n) < tbl[np.clip(deficit_h, 0, 5)]
            a_pull = rng.random(n) < tbl[np.clip(-deficit_h, 0, 5)]
            ea = PARAMS["extra_attacker_goals_for_per60"] * ens * DT / 3600
            en = PARAMS["en_goals_against_per60"] * ens * DT / 3600
            lam_h = np.where(h_pull, ea * home["rate60"] / 2.75, np.where(a_pull, en, lam_h))
            lam_a = np.where(a_pull, ea * away["rate60"] / 2.75, np.where(h_pull, en, lam_a))
        else:
            h_pull = a_pull = np.zeros(n, bool)
        pulled_sec += (h_pull | a_pull) * DT
        cm = np.where(cool > 0, cooldown, 1.0)
        lam_h = lam_h * cm
        lam_a = lam_a * cm
        cool = np.maximum(cool - 1, 0)
        gh = rng.random(n) < lam_h
        ga = rng.random(n) < lam_a
        none_yet = first == 0
        both = gh & ga & none_yet
        coin = rng.random(n) < 0.5
        first = np.where(none_yet & gh & (~ga | coin), 1, np.where(none_yet & ga & (~gh | ~coin), 2, first)).astype(np.int8)
        del both
        hs += gh
        as_ += ga
        cool = np.where(gh | ga, cooldown_steps, cool)
        h_en += gh & a_pull
        a_en += ga & h_pull
        h_gp += gh & ~a_pull
        a_gp += ga & ~h_pull
    tie = hs == as_
    decided = tie & (rng.random(n) < PARAMS["ot_decided_share"])
    str_ratio = home["rate60"] / (home["rate60"] + away["rate60"])
    p_home_ot = np.clip(PARAMS["ot_home_win_share"] + (str_ratio - 0.5), 0.3, 0.7)
    ot_home = decided & (rng.random(n) < p_home_ot)
    ot_away = decided & ~ot_home
    so_home = tie & ~decided & (rng.random(n) < 0.5)
    home_win = (hs > as_) | ot_home | so_home
    h_gp += ot_home
    a_gp += ot_away
    first = np.where((first == 0) & ot_home, 1, np.where((first == 0) & ot_away, 2, first))
    total = hs + as_ + tie.astype(np.int16)          # OT or SO winner adds one to the game total

    res = dict(home_goals=hs + ot_home, away_goals=as_ + ot_away, home_win=home_win, total=total,
               reg_tie=tie, en_goals=h_en + a_en, pulled_sec=pulled_sec, first_team=first)
    for side, team, gp, en, opp_gp in (("home", home, h_gp, h_en, a_gp), ("away", away, a_gp, a_en, h_gp)):
        names = list(team["players"])
        gs = np.array([team["players"][x]["g"] for x in names])
        ash = np.array([team["players"][x]["a"] for x in names])
        ss = np.array([team["players"][x]["s"] for x in names])
        pg = np.append(gs, max(0.0, 1 - gs.sum()))
        pg /= pg.sum()
        tot_goals = gp + en
        G = np.zeros((n, len(names) + 1), np.int16)
        A = np.zeros((n, len(names) + 1), np.int16)
        pa = np.append(ash, max(0.0, 2 * (1 - ash.sum() / 2)))
        for gnum in range(1, int(tot_goals.max()) + 1):
            idx = np.where(tot_goals >= gnum)[0]
            sc = rng.choice(len(pg), size=len(idx), p=pg)
            G[idx, sc] += 1
            if gnum == 1:
                FG = np.full(n, -1, np.int16)
                FG[idx] = sc
            for prob in (0.90, 0.65):
                has = rng.random(len(idx)) < prob
                w = np.tile(pa, (len(idx), 1))
                w[np.arange(len(idx)), sc] = 0
                w /= w.sum(1, keepdims=True)
                cum = w.cumsum(1)
                pick = (rng.random((len(idx), 1)) < cum).argmax(1)
                A[idx[has], pick[has]] += 1
        # shots: non-goal SOG ~ NB around (team SOG - team goals), trailing teams shoot more (score effect)
        mean_ng = max(team["sog"] - team["rate60"], 5.0)
        trail = (res[f"{'away' if side == 'home' else 'home'}_goals"] > res[f"{side}_goals"]).astype(float)
        mu = mean_ng * pace * (1 + 0.04 * trail)
        r_nb = 30.0   # compromise: team SOG sd ~7.3 (emp 6.6) vs teammate SOG corr ~0.07 (emp 0.089); v2: line-level allocation
        ng = rng.poisson(rng.gamma(r_nb, mu / r_nb))
        ps = np.append(ss, max(0.0, 1 - ss.sum()))
        ps /= ps.sum()
        S = rng.multinomial(ng, ps) if False else _multinomial_rows(rng, ng, ps)
        S = S + G * 1  # every goal was a shot (EN goals count as SOG too)
        team_sog = S.sum(1)
        res[f"{side}_sog"] = team_sog
        res[f"{side}_gp_goals"] = gp
        for j, x in enumerate(names):
            res[f"G|{x}"] = G[:, j]
            res[f"FG|{x}"] = (first == (1 if side == "home" else 2)) & (FG == j)
            res[f"A|{x}"] = A[:, j]
            res[f"S|{x}"] = S[:, j]
    res["home_saves"] = res["away_sog"] - res["away_gp_goals"]
    res["away_saves"] = res["home_sog"] - res["home_gp_goals"]
    return res


def _multinomial_rows(rng, counts, p):
    out = np.zeros((len(counts), len(p)), np.int16)
    for c in np.unique(counts):
        idx = counts == c
        out[idx] = rng.multinomial(int(c), p, size=int(idx.sum()))
    return out
