"""EV / PP / PK time on ice per player-game from shift charts x play-by-play strength states (2023-24 onward).

Strength timeline: play-by-play events carry situationCode = [away goalie][away skaters][home skaters][home goalie].
The state between consecutive events is taken from the later event. Each shift [start, end) is intersected
with the timeline; seconds are classified from the player's team perspective (pp: own skaters > opp, pk: <, ev: =).
Output: data/curated/features/deployment.parquet (game_id, player_id, team, ev_sec, pp_sec, pk_sec, en_sec)
Usage: python src/features/deployment.py
"""
import glob
import os
from concurrent.futures import ProcessPoolExecutor

import duckdb
import numpy as np
import pandas as pd

CUR = "data/curated"


def t_sec(period, clock):
    m, s = clock.str.split(":", expand=True).astype(int).T.values
    return (period.astype(int) - 1) * 1200 + m * 60 + s


def one_season(season_dir):
    season = season_dir.split("=")[-1]
    con = duckdb.connect()
    pbp = con.execute(f"""select game_id, period_number, timeInPeriod, situationCode, sortOrder
                          from '{CUR}/nhl_pbp/season={season}/*.parquet'
                          where situationCode is not null order by game_id, sortOrder""").df()
    sh = con.execute(f"""select gameId as game_id, playerId as player_id, teamAbbrev as team, period,
                                startTime_sec, endTime_sec from '{CUR}/nhl_shifts/season={season}/*.parquet'
                         where typeCode = 517 and endTime_sec > startTime_sec""").df()
    games = con.execute(f"select game_id, home, away from '{CUR}/nhl_games.parquet'").df()
    pbp["t"] = t_sec(pbp.period_number, pbp.timeInPeriod)
    code = pbp.situationCode.astype(str).str.zfill(4)
    pbp["aw_g"] = code.str[0].astype(int)
    pbp["aw_s"] = code.str[1].astype(int)
    pbp["hm_s"] = code.str[2].astype(int)
    pbp["hm_g"] = code.str[3].astype(int)
    sh["s"] = (sh.period.astype(int) - 1) * 1200 + sh.startTime_sec
    sh["e"] = (sh.period.astype(int) - 1) * 1200 + sh.endTime_sec
    sh = sh.merge(games, on="game_id", how="left")
    out = []
    for gid, ev in pbp.groupby("game_id", sort=False):
        ev = ev.sort_values(["t"])
        t = ev.t.values
        a = t[:-1]
        b = t[1:]
        nxt = ev.iloc[1:]
        keep = b > a
        a, b = a[keep], b[keep]
        aw_s, hm_s = nxt.aw_s.values[keep], nxt.hm_s.values[keep]
        aw_g, hm_g = nxt.aw_g.values[keep], nxt.hm_g.values[keep]
        s = sh[sh.game_id == gid]
        if s.empty or len(a) == 0:
            continue
        ov = np.clip(np.minimum.outer(s.e.values, b) - np.maximum.outer(s.s.values, a), 0, None)  # shifts x segs
        is_home = (s.team.values == s.home.values)[:, None]
        own = np.where(is_home, hm_s[None, :], aw_s[None, :])
        opp = np.where(is_home, aw_s[None, :], hm_s[None, :])
        opp_goalie_out = np.where(is_home, aw_g[None, :] == 0, hm_g[None, :] == 0)
        own_goalie_out = np.where(is_home, hm_g[None, :] == 0, aw_g[None, :] == 0)
        en = opp_goalie_out | own_goalie_out
        pp = (own > opp) & ~en
        pk = (own < opp) & ~en
        evs = (own == opp) & ~en
        d = pd.DataFrame(dict(player_id=s.player_id.values, team=s.team.values,
                              ev_sec=(ov * evs).sum(1), pp_sec=(ov * pp).sum(1), pk_sec=(ov * pk).sum(1),
                              en_sec=(ov * en).sum(1)))
        d = d.groupby(["player_id", "team"], as_index=False).sum()
        d["game_id"] = gid
        out.append(d)
    return pd.concat(out, ignore_index=True)


def main():
    dirs = sorted(glob.glob(f"{CUR}/nhl_pbp/season=*"))
    with ProcessPoolExecutor(3) as ex:
        res = list(ex.map(one_season, dirs))
    d = pd.concat(res, ignore_index=True)
    os.makedirs(f"{CUR}/features", exist_ok=True)
    d.to_parquet(f"{CUR}/features/deployment.parquet", index=False)
    print(f"deployment: {len(d):,} player-games; mean ev/pp/pk min: "
          f"{d.ev_sec.mean() / 60:.1f}/{d.pp_sec.mean() / 60:.2f}/{d.pk_sec.mean() / 60:.2f}")


if __name__ == "__main__":
    main()
