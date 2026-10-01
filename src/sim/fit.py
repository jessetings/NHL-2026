"""Fit empirical game-process inputs for the simulator from 2023-26 regular-season play-by-play.

Outputs data/curated/sim/params.json:
  - league goal rate per 60 (goalie-present, all strengths) by period and team score-state (diff -4..+4)
  - home share of goalie-present goals
  - pulled-goalie: hazard of pulling by deficit and seconds remaining (P3), EN goals for/against per 60
  - OT: share of tied games decided in OT, home share of OT winners; shootout home win share
Usage: python src/sim/fit.py
"""
import json
import os

import duckdb
import numpy as np
import pandas as pd

CUR = "data/curated"
OUT = f"{CUR}/sim"


SMAX = 4   # score states -4..+4 (v3: blowout states split out of the old +/-2 bucket)


def timeline():
    con = duckdb.connect()
    ev = con.execute(f"""
        select game_id, period_number as p, period_periodType as ptype, timeInPeriod as tip, situationCode as sc,
               typeDescKey as typ, try_cast(eventOwnerTeamId as double) as owner, cast(home_id as double) as home_id, cast(away_id as double) as away_id, sortOrder
        from '{CUR}/nhl_pbp/*/*.parquet'
        where cast(game_id as varchar) like '____02%' and situationCode is not null
        order by game_id, sortOrder""").df()
    m, s = ev.tip.str.split(":", expand=True).astype(int).T.values
    ev["t"] = (ev.p.astype(int) - 1) * 1200 + m * 60 + s
    code = ev.sc.astype(str).str.zfill(4)
    ev["aw_g"], ev["aw_s"], ev["hm_s"], ev["hm_g"] = (code.str[i].astype(int) for i in range(4))
    return ev


def fit():
    ev = timeline()
    reg = ev[ev.ptype == "REG"].copy()
    rows = []   # segments: (game, period, dur, home_diff, home_g_out, away_g_out, goals home/away in segment)
    goal_rows = []
    for gid, g in reg.groupby("game_id", sort=False):
        g = g.sort_values(["t", "sortOrder"])
        hs = as_ = 0
        t = g.t.values
        nxt = g.iloc[1:]
        for i in range(len(g) - 1):
            dur = t[i + 1] - t[i]
            r = nxt.iloc[i]
            if dur > 0:
                rows.append((gid, int(r.p), dur, hs - as_, r.hm_g == 0, r.aw_g == 0, t[i]))
            if r.typ == "goal":
                home_goal = r.owner == r.home_id
                # state BEFORE the goal, goalie situation at the goal
                goal_rows.append((gid, int(r.p), hs - as_, bool(home_goal), r.hm_g == 0, r.aw_g == 0, t[i + 1]))
                hs += home_goal
                as_ += not home_goal
    seg = pd.DataFrame(rows, columns=["game_id", "p", "dur", "hdiff", "h_out", "a_out", "t0"])
    gl = pd.DataFrame(goal_rows, columns=["game_id", "p", "hdiff", "home_goal", "h_out", "a_out", "t"])

    # --- goalie-present scoring rate by period and team score-state (team perspective)
    both_in = seg[~seg.h_out & ~seg.a_out]
    g_in = gl[~gl.h_out & ~gl.a_out]
    out = {"rate_by_period_state": {}, "n_games": int(seg.game_id.nunique())}
    for p in (1, 2, 3):
        for d in range(-SMAX, SMAX + 1):
            # home team at diff d  + away team at diff d (away perspective diff = -hdiff); |diff| >= SMAX pooled
            exp_h = both_in[(both_in.p == p) & (both_in.hdiff.clip(-SMAX, SMAX) == d)].dur.sum()
            exp_a = both_in[(both_in.p == p) & ((-both_in.hdiff).clip(-SMAX, SMAX) == d)].dur.sum()
            g_h = ((g_in.p == p) & (g_in.hdiff.clip(-SMAX, SMAX) == d) & g_in.home_goal).sum()
            g_a = ((g_in.p == p) & ((-g_in.hdiff).clip(-SMAX, SMAX) == d) & ~g_in.home_goal).sum()
            exp = exp_h + exp_a
            out["rate_by_period_state"][f"{p}|{d}"] = float((g_h + g_a) / exp * 3600) if exp > 0 else None
    # v3: strength-adjusted states. Raw rates at big leads are confounded (teams up 4 are usually much stronger),
    # so measure goals / expected goals, expected = league rate x team GF ratio x opponent GA ratio (team-season).
    con = duckdb.connect()
    gm = con.execute(f"""select game_id, season, home, away, home_score, away_score from '{CUR}/nhl_games.parquet'
                         where game_type = 2 and home_score is not null""").df()
    tg = pd.concat([gm.rename(columns={"home": "team", "home_score": "gf", "away_score": "ga"})[["season", "team", "gf", "ga"]],
                    gm.rename(columns={"away": "team", "away_score": "gf", "home_score": "ga"})[["season", "team", "gf", "ga"]]])
    ts = tg.groupby(["season", "team"])[["gf", "ga"]].mean()
    ts = ts / ts.groupby(level=0).transform("mean")
    gm = gm.join(ts.add_prefix("h_"), on=["season", "home"]).join(ts.add_prefix("a_"), on=["season", "away"])
    gm["s_home"], gm["s_away"] = gm.h_gf * gm.a_ga, gm.a_gf * gm.h_ga
    sm = gm.set_index("game_id")[["s_home", "s_away"]]
    bi = both_in.join(sm, on="game_id")
    gi = g_in.join(sm, on="game_id")
    adj, raw_mean = {}, np.nanmean([v for v in out["rate_by_period_state"].values() if v])
    for p in (1, 2, 3):
        for d in range(-SMAX, SMAX + 1):
            hm, am = (bi.p == p) & (bi.hdiff.clip(-SMAX, SMAX) == d), (bi.p == p) & ((-bi.hdiff).clip(-SMAX, SMAX) == d)
            exp = (bi[hm].dur * bi[hm].s_home).sum() + (bi[am].dur * bi[am].s_away).sum()
            g_n = ((gi.p == p) & (gi.hdiff.clip(-SMAX, SMAX) == d) & gi.home_goal).sum() + \
                  ((gi.p == p) & ((-gi.hdiff).clip(-SMAX, SMAX) == d) & ~gi.home_goal).sum()
            adj[f"{p}|{d}"] = float(g_n / exp * 3600) if exp > 0 else None
    k = raw_mean / np.nanmean([v for v in adj.values() if v])
    out["rate_by_period_state_raw"] = out["rate_by_period_state"]
    out["rate_by_period_state"] = {key: (v * k if v else v) for key, v in adj.items()}
    out["home_share_goalie_present"] = float(g_in.home_goal.mean())

    # --- pulled goalie (P3, regulation): hazard of pulling by deficit and time remaining
    p3 = seg[seg.p == 3].copy()
    p3["remain"] = 3600 - p3.t0
    pulls = {}
    for deficit in (1, 2, 3):
        # home trailing by `deficit` with goalie in -> does home pull? (same for away, mirrored)
        for tb in [(0, 60), (60, 120), (120, 180), (180, 240), (240, 360)]:
            m_h = (p3.hdiff == -deficit) & p3.remain.between(tb[0], tb[1] - 1e-9)
            m_a = (p3.hdiff == deficit) & p3.remain.between(tb[0], tb[1] - 1e-9)
            t_out = p3[m_h & p3.h_out].dur.sum() + p3[m_a & p3.a_out].dur.sum()
            t_all = p3[m_h].dur.sum() + p3[m_a].dur.sum()
            pulls[f"{deficit}|{tb[0]}-{tb[1]}"] = float(t_out / t_all) if t_all > 0 else None
    out["share_time_goalie_pulled"] = pulls
    en_seg = seg[(seg.h_out ^ seg.a_out)]
    en_time = en_seg.dur.sum()
    en_g = gl[gl.h_out ^ gl.a_out]
    # goals into the empty net = scored by the team whose OPPONENT pulled
    ga_en = ((en_g.h_out & ~en_g.home_goal) | (en_g.a_out & en_g.home_goal)).sum()
    gf_extra = len(en_g) - ga_en
    out["en_goals_against_per60"] = float(ga_en / en_time * 3600)
    out["extra_attacker_goals_for_per60"] = float(gf_extra / en_time * 3600)
    out["en_goals_per_game"] = float(ga_en / seg.game_id.nunique())

    # --- OT / shootout
    last = ev.groupby("game_id").agg(maxp=("p", "max"), types=("ptype", lambda s: ",".join(sorted(set(s)))))
    ot_games = last[last.types.str.contains("OT|SO")]
    so_games = last[last.types.str.contains("SO")]
    out["ot_share_of_games"] = float(len(ot_games) / len(last))
    out["ot_decided_share"] = float(1 - len(so_games) / max(len(ot_games), 1))
    otg = ev[(ev.ptype == "OT") & (ev.typ == "goal")]
    out["ot_home_win_share"] = float((otg.owner == otg.home_id).mean())
    ot_time = ev[ev.ptype == "OT"].groupby("game_id").t.max() - 3600
    out["ot_goal_rate_per60"] = float(len(otg) / ot_time.clip(lower=1).sum() * 3600)
    os.makedirs(OUT, exist_ok=True)
    json.dump(out, open(f"{OUT}/params.json", "w"), indent=1)
    return out, seg, gl


if __name__ == "__main__":
    o, seg, gl = fit()
    print(json.dumps({k: v for k, v in o.items() if k != "share_time_goalie_pulled"}, indent=1))
    print("pulled share (deficit|seconds remaining):", {k: round(v, 3) if v else v for k, v in o["share_time_goalie_pulled"].items()})
