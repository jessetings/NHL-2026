"""Shot-quality, strength-split feature store (as-of: every feature uses ONLY games strictly before the game).

Source: MoneyPuck shot-level files (every unblocked attempt with xGoal, strength, rush/rebound), 2022-23 -> now,
NHL play-by-play (points by strength) and our deployment table (EV/PP/PK TOI per player-game).
High danger = MoneyPuck's own definition, xGoal >= 0.20 (low < 0.08, medium 0.08-0.20).
Strength from the shooter's side: EV (equal skaters, both goalies in), PP (more skaters), SH (fewer);
shots with either net empty are EN and excluded from rates.

Outputs (data/curated/features/):
  shot_player_game.parquet  player x game x strength counts (att, sog, g, xg, hd_att, hd_xg, rush, reb) + pts by strength
  shot_team_game.parquet    team x game: for/against x strength (att, sog, g, xg, hd) + team EV/PP/PK seconds
  shot_goalie_game.parquet  goalie x game: faced sog/xg/hd, goals against (non-EN)
  shotq_player.parquet      as-of player features: per-60 by strength (EWMA + shrinkage) and HD/rush/reb shares
  shotq_team.parquet        as-of team features: EV for/against per 60, PP for / PK against per 60, PP/PK time per game
  shotq_goalie.parquet      as-of goalie: GSAx per 100 shots, HD save% above expected
Usage: python src/features/shotq.py
"""
import glob
import os

import duckdb
import numpy as np
import pandas as pd

CUR = "data/curated"
OUT = f"{CUR}/features"
HD = 0.20
NEXT = 9_999_999_999            # sentinel game_id: "next game" row = features as of now (all games played)
NEXT_DATE = pd.Timestamp("2100-01-01")
HL_P, HL_T, HL_G = 30, 25, 40          # EWMA half-lives (games) for player, team, goalie
K_EV, K_PP = 600 * 60, 120 * 60        # shrinkage strength in seconds of ice time (10 h EV, 2 h PP)


def shots(con):
    files = sorted(glob.glob(f"{CUR}/mp_shots_*.parquet"))
    q = " union all by name ".join(f"select * from '{f}'" for f in files)
    return con.execute(f"""
        with s as ({q}),
        x as (
          select season * 1000000 + game_id as game_id, teamCode as team,
                 case when isHomeTeam = 1 then awayTeamCode else homeTeamCode end as opp,
                 shooterPlayerId as player_id, goalieIdForShot as goalie_id,
                 case when homeEmptyNet = 1 or awayEmptyNet = 1 or shotOnEmptyNet = 1 then 'EN'
                      when (case when isHomeTeam = 1 then homeSkatersOnIce else awaySkatersOnIce end) >
                           (case when isHomeTeam = 1 then awaySkatersOnIce else homeSkatersOnIce end) then 'PP'
                      when (case when isHomeTeam = 1 then homeSkatersOnIce else awaySkatersOnIce end) <
                           (case when isHomeTeam = 1 then awaySkatersOnIce else homeSkatersOnIce end) then 'SH'
                      else 'EV' end as str,
                 xGoal as xg, goal as g, shotWasOnGoal as sog, xGoal >= {HD} as hd, shotRush as rush, shotRebound as reb,
                 period
          from s where isPlayoffGame = 0 and cast(game_id as varchar) like '2%')
        select * from x where period <= 4""").df()


def team_seconds(con):
    """Team EV / PP / PK seconds per game from player deployment (EV ~5 skaters, PP ~5, PK ~4 on ice)."""
    return con.execute(f"""
        select d.game_id, d.team, sum(ev_sec) / 5.0 ev_sec, sum(pp_sec) / 5.0 pp_sec, sum(pk_sec) / 4.0 pk_sec
        from '{CUR}/features/deployment.parquet' d
        join (select distinct playerId, game_id from '{CUR}/nhl_skater_game.parquet') k
          on k.playerId = d.player_id and k.game_id = d.game_id          -- skaters only (deployment includes goalies)
        group by 1, 2""").df()


def points_by_strength(con):
    """Goals and assists per player-game split EV / PP / SH from play-by-play situationCode."""
    return con.execute(f"""
        with g as (
          select game_id, situationCode sc, try_cast(eventOwnerTeamId as double) own_team, home_id,
                 scoringPlayerId s, assist1PlayerId a1, assist2PlayerId a2
          from '{CUR}/nhl_pbp/*/*.parquet' where typeDescKey = 'goal' and period_number <= 4
            and cast(game_id as varchar) like '____02%'),
        c as (
          select *, lpad(cast(sc as varchar), 4, '0') code from g),
        k as (
          select game_id, s, a1, a2,
                 cast(substr(code, 1, 1) as int) ag, cast(substr(code, 2, 1) as int) asks,
                 cast(substr(code, 3, 1) as int) hsk, cast(substr(code, 4, 1) as int) hg,
                 own_team = home_id is_home from c),
        st as (
          select *, case when ag = 0 or hg = 0 then 'EN'
                         when (case when is_home then hsk else asks end) > (case when is_home then asks else hsk end) then 'PP'
                         when (case when is_home then hsk else asks end) < (case when is_home then asks else hsk end) then 'SH'
                         else 'EV' end str from k),
        u as (
          select game_id, s player_id, str, 1 g, 0 a from st where s is not null
          union all select game_id, a1, str, 0, 1 from st where a1 is not null
          union all select game_id, a2, str, 0, 1 from st where a2 is not null)
        select game_id, cast(player_id as bigint) player_id, str, sum(g) pg, sum(a) pa from u group by 1, 2, 3""").df()


def ewm_lag(s, hl):
    return s.shift(1).ewm(halflife=hl, min_periods=1).mean()


def player_features(psg, dep, pts, games):
    """Lagged per-60 rates by strength with shrinkage toward position priors."""
    piv = psg.pivot_table(index=["game_id", "player_id"], columns="str",
                          values=["att", "sog", "g", "xg", "hd_att", "hd_xg", "rush", "reb"], aggfunc="sum", fill_value=0)
    piv.columns = [f"{s.lower()}_{v}" for v, s in piv.columns]
    pp = pts.pivot_table(index=["game_id", "player_id"], columns="str", values=["pg", "pa"], aggfunc="sum", fill_value=0)
    pp.columns = [f"{s.lower()}_{v}" for v, s in pp.columns]
    d = dep.merge(piv.reset_index(), on=["game_id", "player_id"], how="left").merge(pp.reset_index(), on=["game_id", "player_id"], how="left")
    d = d.merge(games[["game_id", "date", "season"]], on="game_id").fillna(0)
    last = d.sort_values("date").groupby("player_id").tail(1)
    last = last[last.date >= last.date.max() - pd.Timedelta(days=400)]
    nxt = last[["player_id", "team", "season"]].assign(game_id=NEXT, date=NEXT_DATE)
    d = pd.concat([d, nxt], ignore_index=True).fillna(0)
    d = d.sort_values(["player_id", "date", "game_id"])
    g = d.groupby("player_id", sort=False)
    out = d[["game_id", "player_id", "team", "date", "season"]].copy()
    out["gp_prior"] = g.cumcount()
    for sec in ("ev_sec", "pp_sec", "pk_sec"):           # short-memory deployment (TOI projection inputs)
        for hl in (5, 20):
            out[f"q_{sec}_e{hl}"] = g[sec].transform(lambda s: ewm_lag(s, hl))
    for strn, sec, K in (("ev", "ev_sec", K_EV), ("pp", "pp_sec", K_PP)):
        sec_m = g[sec].transform(lambda s: ewm_lag(s, HL_P))
        n_eff = np.minimum(out.gp_prior, 2 * HL_P)
        sec_eff = sec_m * n_eff
        out[f"{strn}_sec_ewm"] = sec_m
        for v in ("sog", "att", "xg", "hd_att", "hd_xg", "g", "pg", "pa", "rush", "reb"):
            col = f"{strn}_{v}"
            if col not in d:
                d[col] = 0.0
            m = g[col].transform(lambda s: ewm_lag(s, HL_P))
            raw60 = np.where(sec_m > 0, m / sec_m.where(sec_m > 0) * 3600, np.nan)
            out[f"{strn}_{v}60_raw"] = raw60
            out[f"_{strn}_{v}_cnt"] = m * n_eff
            out[f"_{strn}_sec_eff"] = sec_eff
    # position priors (league per-60 by strength, F vs D) and shrinkage
    pos = pd.read_parquet(f"{CUR}/nhl_skater_game.parquet", columns=["playerId", "position"]).drop_duplicates("playerId")
    out = out.merge(pos.rename(columns={"playerId": "player_id"}), on="player_id", how="left")
    out["pg"] = np.where(out.position == "D", "D", "F")
    tot = d.merge(out[["game_id", "player_id", "pg"]], on=["game_id", "player_id"])
    for strn, sec, K in (("ev", "ev_sec", K_EV), ("pp", "pp_sec", K_PP)):
        for v in ("sog", "att", "xg", "hd_att", "hd_xg", "g", "pg", "pa", "rush", "reb"):
            prior = (tot.groupby("pg")[f"{strn}_{v}"].sum() / tot.groupby("pg")[sec].sum().clip(lower=1) * 3600)
            pr = out.pg.map(prior)
            cnt, se = out[f"_{strn}_{v}_cnt"], out[f"_{strn}_sec_eff"]
            out[f"{strn}_{v}60"] = (cnt.fillna(0) + pr * K / 3600) / (se.fillna(0) + K) * 3600
    # finishing (EV+PP goals vs xG) with the forward K=64 xG shrink; D no finishing skill
    gsum = out["_ev_g_cnt"].fillna(0) + out["_pp_g_cnt"].fillna(0)
    xsum = out["_ev_xg_cnt"].fillna(0) + out["_pp_xg_cnt"].fillna(0)
    out["finish"] = np.where(out.pg == "D", 1.0, (gsum + 64 * 0.0 + 64) / (xsum + 64))
    out["hd_share"] = (out["_ev_hd_att_cnt"].fillna(0) + out["_pp_hd_att_cnt"].fillna(0) + 2) / \
                      (out["_ev_att_cnt"].fillna(0) + out["_pp_att_cnt"].fillna(0) + 25)
    out["sog_per_att"] = (out["_ev_sog_cnt"].fillna(0) + out["_pp_sog_cnt"].fillna(0) + 0.55 * 30) / \
                         (out["_ev_att_cnt"].fillna(0) + out["_pp_att_cnt"].fillna(0) + 30)
    return out[[c for c in out.columns if not c.startswith("_")]]


def team_features(tsg, tsec, games):
    """Lagged team for/against rates per 60 by strength, special-teams time per game."""
    w = tsg.pivot_table(index=["game_id", "team"], columns=["side", "str"], values=["att", "sog", "g", "xg", "hd"],
                        aggfunc="sum", fill_value=0)
    w.columns = [f"{side}_{s.lower()}_{v}" for v, side, s in w.columns]
    # inner: deployment exists 2023-24+
    w = w.reset_index().merge(tsec, on=["game_id", "team"], how="inner").merge(games[["game_id", "date", "season"]], on="game_id")
    lastt = w.sort_values("date").groupby("team").tail(1)
    w = pd.concat([w, lastt[["team", "season"]].assign(game_id=NEXT, date=NEXT_DATE)], ignore_index=True)
    w = w.fillna(0).sort_values(["team", "date", "game_id"])
    g = w.groupby("team", sort=False)
    out = w[["game_id", "team", "date", "season"]].copy()
    secm = {k: g[k].transform(lambda s: ewm_lag(s, HL_T)) for k in ("ev_sec", "pp_sec", "pk_sec")}
    out["pp_sec_pg"], out["pk_sec_pg"], out["ev_sec_pg"] = secm["pp_sec"], secm["pk_sec"], secm["ev_sec"]
    for v in ("att", "sog", "g", "xg", "hd"):
        for side, s, sec in (("f", "ev", "ev_sec"), ("a", "ev", "ev_sec"), ("f", "pp", "pp_sec"), ("a", "sh", "pp_sec"),
                             ("f", "sh", "pk_sec"), ("a", "pp", "pk_sec")):
            col = f"{side}_{s}_{v}"
            if col not in w:
                continue
            m = g[col].transform(lambda x: ewm_lag(x, HL_T))
            out[f"{side}_{s}_{v}60"] = m / secm[sec].where(secm[sec] > 0) * 3600
    out["gp_prior"] = g.cumcount()
    return out


def goalie_features(gg, games):
    gg = gg.merge(games[["game_id", "date"]], on="game_id")
    lastg = gg.sort_values("date").groupby("goalie_id").tail(1)
    gg = pd.concat([gg, lastg[["goalie_id", "team"]].assign(game_id=NEXT, date=NEXT_DATE)], ignore_index=True).fillna(0)
    gg = gg.sort_values(["goalie_id", "date", "game_id"])
    g = gg.groupby("goalie_id", sort=False)
    out = gg[["game_id", "goalie_id", "team", "date"]].copy()
    for c in ("sog", "ga", "xga", "hd", "hd_ga", "hd_xga"):
        out[f"_{c}"] = g[c].transform(lambda s: s.shift(1).ewm(halflife=HL_G, min_periods=1).mean() * np.minimum(
            np.arange(len(s)), 2 * HL_G))
    # GSAx per 100 unblocked-on-goal, shrunk with 600 shots prior at 0
    out["gsax100"] = (out._xga - out._ga) / (out._sog + 600) * 100
    out["hd_svx"] = (out._hd_xga - out._hd_ga) / (out._hd + 120)      # HD goals saved above expected per HD shot
    out["gp_prior"] = g.cumcount()
    return out.drop(columns=[c for c in out.columns if c.startswith("_")])


def main():
    con = duckdb.connect()
    s = shots(con)
    games = con.execute(f"select game_id, date, season from '{CUR}/nhl_games.parquet' where game_type = 2").df()
    games["date"] = pd.to_datetime(games.date)
    print(f"shots {len(s):,}; games {s.game_id.nunique():,}; strength mix {s.str.value_counts(normalize=True).round(3).to_dict()}")
    s["att"] = 1
    psg = s[s.str != "EN"].groupby(["game_id", "player_id", "team", "str"], as_index=False)[
        ["att", "sog", "g", "xg", "rush", "reb"]].sum()
    hd = s[(s.str != "EN") & s.hd].groupby(["game_id", "player_id", "str"], as_index=False).agg(hd_att=("att", "sum"), hd_xg=("xg", "sum"))
    psg = psg.merge(hd, on=["game_id", "player_id", "str"], how="left").fillna({"hd_att": 0, "hd_xg": 0})
    psg.to_parquet(f"{OUT}/shot_player_game.parquet", index=False)
    ne = s[s.str != "EN"].assign(hd=lambda x: x.hd.astype(int))
    f = ne.groupby(["game_id", "team", "str"], as_index=False)[["att", "sog", "g", "xg", "hd"]].sum().assign(side="f")
    a = ne.groupby(["game_id", "opp", "str"], as_index=False)[["att", "sog", "g", "xg", "hd"]].sum().rename(columns={"opp": "team"})
    a["str"] = a.str.map({"EV": "EV", "PP": "PP", "SH": "SH"})
    a["side"] = "a"            # 'a_pp' = allowed while the OPPONENT was on the PP (= our PK)
    tsg = pd.concat([f, a])
    tsg.to_parquet(f"{OUT}/shot_team_game.parquet", index=False)
    on = ne[ne.sog.astype(bool) | ne.g.astype(bool)]
    gg = ne.assign(hd_g=lambda x: x.g * x.hd).groupby(["game_id", "goalie_id", "opp"], as_index=False).agg(
        att=("att", "sum"), xga=("xg", "sum"), ga=("g", "sum"), hd=("hd", "sum"), hd_ga=("hd_g", "sum"),
        hd_xga=("xg", lambda x: x[ne.loc[x.index, "hd"] == 1].sum())).rename(columns={"opp": "team"})
    gg = gg.merge(on.groupby(["game_id", "goalie_id"], as_index=False).agg(sog=("att", "sum")), on=["game_id", "goalie_id"], how="left")
    gg = gg[gg.goalie_id > 0]
    gg.to_parquet(f"{OUT}/shot_goalie_game.parquet", index=False)

    dep = con.execute(f"select * from '{CUR}/features/deployment.parquet'").df()
    pts = points_by_strength(con)
    pts.to_parquet(f"{OUT}/pts_strength_game.parquet", index=False)
    pf = player_features(psg, dep, pts, games)
    pf.to_parquet(f"{OUT}/shotq_player.parquet", index=False)
    tsec = team_seconds(con)
    tf = team_features(tsg, tsec, games)
    tf.to_parquet(f"{OUT}/shotq_team.parquet", index=False)
    gf = goalie_features(gg, games)
    gf.to_parquet(f"{OUT}/shotq_goalie.parquet", index=False)
    print(f"player rows {len(pf):,}; team rows {len(tf):,}; goalie rows {len(gf):,}")
    lg = tf[tf.gp_prior > 20].mean(numeric_only=True)
    print("league (as-of, teams w/ 20+ GP):",
          {k: round(lg[k], 2) for k in ("f_ev_sog60", "f_ev_xg60", "f_ev_hd60", "f_pp_sog60", "f_pp_xg60", "a_pp_sog60", "pp_sec_pg", "pk_sec_pg", "ev_sec_pg")})


if __name__ == "__main__":
    main()
