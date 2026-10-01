"""Lines, linemates and power-play units per player-game from shift charts (2023-24 onward).

For every skater-game:
  - linemates: the 2 forwards (for F) / 1 defenseman partner (for D) sharing the most on-ice seconds
  - lm_ev_xg60, lm_ev_pts60, lm_ev_sog60: linemates' AS-OF EV rates (from shotq_player; known pregame once
    lines are known, which DailyFaceoff provides live)
  - pp_rank: rank of the player's PP seconds within his team that game (1-5 ~ PP1, 6-10 ~ PP2)
Output: data/curated/features/lines_player_game.parquet
Usage: python src/features/lines.py
"""
import duckdb
import numpy as np
import pandas as pd

CUR = "data/curated"


def coshift(con, season):
    return con.execute(f"""
        with s as (
          select sh.gameId game_id, sh.playerId pid, sh.teamAbbrev team, sh.period, sh.startTime_sec a, sh.endTime_sec b,
                 case when sk.position = 'D' then 'D' else 'F' end pos
          from '{CUR}/nhl_shifts/season={season}/*.parquet' sh
          join (select distinct game_id, playerId, position from '{CUR}/nhl_skater_game.parquet') sk
            on sk.game_id = sh.gameId and sk.playerId = sh.playerId
          where sh.typeCode = 517 and sh.endTime_sec > sh.startTime_sec and cast(sh.gameId as varchar) like '____02%')
        select x.game_id, x.team, x.pid, x.pos, y.pid mate, y.pos mate_pos,
               sum(least(x.b, y.b) - greatest(x.a, y.a)) secs
        from s x join s y on x.game_id = y.game_id and x.team = y.team and x.period = y.period and x.pid <> y.pid
             and x.a < y.b and y.a < x.b
        group by all""").df()


def main():
    con = duckdb.connect()
    seasons = sorted(r[0].split("=")[-1] for r in con.execute(
        f"select distinct regexp_extract(filename, 'season=[0-9]+') from read_parquet('{CUR}/nhl_shifts/*/*.parquet', filename=true)").fetchall())
    parts = []
    for s in seasons:
        c = coshift(con, s.replace("season=", ""))
        c = c[c.secs > 0]
        # linemates: F -> top-2 F mates; D -> top-1 D mate
        f = c[(c.pos == "F") & (c.mate_pos == "F")].sort_values("secs", ascending=False).groupby(["game_id", "pid"]).head(2)
        d = c[(c.pos == "D") & (c.mate_pos == "D")].sort_values("secs", ascending=False).groupby(["game_id", "pid"]).head(1)
        parts.append(pd.concat([f, d]))
        print(s, len(c), flush=True)
    lm = pd.concat(parts, ignore_index=True)
    sp = pd.read_parquet(f"{CUR}/features/shotq_player.parquet",
                         columns=["game_id", "player_id", "ev_xg60", "ev_pg60", "ev_pa60", "ev_sog60", "gp_prior"])
    sp["ev_pts60"] = sp.ev_pg60 + sp.ev_pa60
    lm = lm.merge(sp.rename(columns={"player_id": "mate"}), on=["game_id", "mate"], how="left")
    agg = lm.groupby(["game_id", "pid"]).agg(lm_ev_xg60=("ev_xg60", "mean"), lm_ev_pts60=("ev_pts60", "mean"),
                                             lm_ev_sog60=("ev_sog60", "mean"), lm_secs=("secs", "mean"),
                                             lm_n=("mate", "size")).reset_index().rename(columns={"pid": "player_id"})
    dep = pd.read_parquet(f"{CUR}/features/deployment.parquet")
    dep["pp_rank"] = dep.groupby(["game_id", "team"]).pp_sec.rank(ascending=False, method="first")
    dep.loc[dep.pp_sec <= 30, "pp_rank"] = 99
    out = agg.merge(dep[["game_id", "player_id", "pp_rank"]], on=["game_id", "player_id"], how="left")
    out.to_parquet(f"{CUR}/features/lines_player_game.parquet", index=False)
    print(f"lines_player_game: {len(out):,} rows; mean linemate EV pts/60 {out.lm_ev_pts60.mean():.2f}")


if __name__ == "__main__":
    main()
