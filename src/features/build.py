"""As-of feature store: every feature for a (player, game) uses ONLY games strictly before that game.

Output: data/curated/features/player_game.parquet (one row per skater-game, 2022-23 -> now) with
  targets (sog, goals, assists, points, toi_min) and lagged features:
  - EWMA per-game and per-60 rates (half-lives 5, 15, 40 games) for sog/goals/assists/points/toi
  - season-to-date and since-2022 means (lagged), games played, days rest, back-to-back
  - team and opponent lagged shots-for / shots-against / goals-for / goals-against EWMA
  - opposing starting goalie lagged save% EWMA (starter flag from boxscore -> known pregame once confirmed)
Usage: python src/features/build.py
"""
import os

import duckdb
import numpy as np
import pandas as pd

CUR = "data/curated"
OUT = f"{CUR}/features"
HL = (5, 15, 40)
STATS = ["sog", "goals", "assists", "points", "toi_min", "powerPlayGoals", "blockedShots", "hits"]


def ewm_lag(g, col, hl):
    return g[col].transform(lambda s: s.shift(1).ewm(halflife=hl, min_periods=1).mean())


def main():
    os.makedirs(OUT, exist_ok=True)
    con = duckdb.connect()
    d = con.execute(f"""
        select s.game_id, s.playerId as player_id, s.team, s.opp, s.is_home, s.position,
               s.sog, s.goals, s.assists, s.points, s.powerPlayGoals, s.blockedShots, s.hits,
               s.toi_sec / 60.0 as toi_min, g.date, g.season, g.game_type
        from '{CUR}/nhl_skater_game.parquet' s join '{CUR}/nhl_games.parquet' g using(game_id)
        where g.game_type in (2, 3) and s.toi_sec > 0
        order by s.playerId, g.date, s.game_id""").df()
    d["date"] = pd.to_datetime(d.date)
    g = d.groupby("player_id", sort=False)

    feats = {}
    for hl in HL:
        for c in STATS:
            feats[f"{c}_ewm{hl}"] = ewm_lag(g, c, hl)
        # per-60 rates as ratio of EWMAs (TOI-weighted)
        for c in ("sog", "goals", "assists", "points"):
            feats[f"{c}60_ewm{hl}"] = feats[f"{c}_ewm{hl}"] / feats[f"toi_min_ewm{hl}"] * 60
    F = pd.DataFrame(feats, index=d.index)
    d = pd.concat([d, F], axis=1)

    # season-to-date and career-to-date (lagged)
    gs = d.groupby(["player_id", "season"], sort=False)
    d["gp_season_prior"] = gs.cumcount()
    d["gp_career_prior"] = g.cumcount()
    for c in ("sog", "goals", "assists", "points", "toi_min"):
        d[f"{c}_std"] = gs[c].transform(lambda s: s.shift(1).expanding().mean())
        d[f"{c}_ctd"] = g[c].transform(lambda s: s.shift(1).expanding().mean())
    d["days_rest"] = g.date.diff().dt.days
    d["b2b"] = (d.days_rest == 1).astype(int)

    # team-level lagged context from games table
    tg = con.execute(f"""
        select game_id, date, home as team, away as opp, home_sog as sf, away_sog as sa,
               home_score as gf, away_score as ga, true as is_home from '{CUR}/nhl_games.parquet' where game_type in (2,3)
        union all
        select game_id, date, away, home, away_sog, home_sog, away_score, home_score, false
        from '{CUR}/nhl_games.parquet' where game_type in (2,3)""").df()
    tg["date"] = pd.to_datetime(tg.date)
    tg = tg.sort_values(["team", "date", "game_id"])
    t = tg.groupby("team", sort=False)
    for c in ("sf", "sa", "gf", "ga"):
        tg[f"team_{c}_ewm20"] = t[c].transform(lambda s: s.shift(1).ewm(halflife=20, min_periods=1).mean())
    tg["team_days_rest"] = t.date.diff().dt.days
    team_f = tg[["game_id", "team", "team_sf_ewm20", "team_sa_ewm20", "team_gf_ewm20", "team_ga_ewm20",
                 "team_days_rest"]]
    d = d.merge(team_f, on=["game_id", "team"], how="left")
    opp_f = team_f.rename(columns={"team": "opp", "team_sf_ewm20": "opp_sf_ewm20", "team_sa_ewm20": "opp_sa_ewm20",
                                   "team_gf_ewm20": "opp_gf_ewm20", "team_ga_ewm20": "opp_ga_ewm20",
                                   "team_days_rest": "opp_days_rest"})
    d = d.merge(opp_f, on=["game_id", "opp"], how="left")

    # opposing starting goalie: lagged save% EWMA (shots-weighted)
    gk = con.execute(f"""
        select k.game_id, k.playerId as goalie_id, k.team, k.saves, k.shotsAgainst as sa, k.starter, g.date
        from '{CUR}/nhl_goalie_game.parquet' k join '{CUR}/nhl_games.parquet' g using(game_id)
        where g.game_type in (2,3) order by k.playerId, g.date""").df()
    gk["date"] = pd.to_datetime(gk.date)
    kg = gk.groupby("goalie_id", sort=False)
    for c in ("saves", "sa"):
        gk[f"{c}_ewm"] = kg[c].transform(lambda s: s.shift(1).ewm(halflife=25, min_periods=1).mean())
    gk["g_svpct_ewm"] = gk.saves_ewm / gk.sa_ewm
    gk["g_gp_prior"] = kg.cumcount()
    st = gk[gk.starter == True][["game_id", "team", "goalie_id", "g_svpct_ewm", "g_gp_prior"]]  # noqa: E712
    st = st.rename(columns={"team": "opp", "goalie_id": "opp_goalie_id", "g_svpct_ewm": "opp_g_svpct_ewm",
                            "g_gp_prior": "opp_g_gp_prior"})
    d = d.merge(st.drop_duplicates(["game_id", "opp"]), on=["game_id", "opp"], how="left")
    d.to_parquet(f"{OUT}/player_game.parquet", index=False)
    print(f"player_game features: {len(d):,} rows x {d.shape[1]} cols -> {OUT}/player_game.parquet")


if __name__ == "__main__":
    main()
