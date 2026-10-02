"""On-ice impact and line matchups (quality of competition) from shots x shift charts (2023-24 onward).

1. on-ice: every EV (non-empty-net) unblocked attempt is matched to the skaters on the ice (shift start < t <= end)
   -> per player-game on-ice xGF / xGA / HD for-against / GF / GA
2. as-of on-ice rates per 60 EV (EWMA half-life 40 games, shrunk to league with 8 h of EV ice)
3. matchups: cross-team co-ice seconds per player-game -> QoC = co-ice-weighted average of the opponents'
   AS-OF on-ice xGA60 (how stingy the skaters he actually faced are) and xGF60
Outputs: data/curated/features/onice_player_game.parquet, onice_player.parquet (as-of), matchup_player_game.parquet
Usage: python src/features/onice.py
"""
import glob

import duckdb
import numpy as np
import pandas as pd

CUR = "data/curated"
OUT = f"{CUR}/features"
HL = 40
K = 8 * 3600


def onice(con):
    files = sorted(glob.glob(f"{CUR}/mp_shots_*.parquet"))
    q = " union all by name ".join(f"select * from '{f}'" for f in files)
    return con.execute(f"""
        with s as ({q}),
        sh as (
          select season * 1000000 + game_id as game_id, period, time - (period - 1) * 1200 as t, teamCode team,
                 xGoal xg, goal g, cast(xGoal >= 0.2 as int) hd
          from s where isPlayoffGame = 0 and period <= 3 and homeEmptyNet = 0 and awayEmptyNet = 0 and shotOnEmptyNet = 0
            and homeSkatersOnIce = awaySkatersOnIce),
        sk as (
          select f.gameId game_id, f.playerId player_id, f.teamAbbrev team, f.period, f.startTime_sec a, f.endTime_sec b
          from '{CUR}/nhl_shifts/*/*.parquet' f
          join (select distinct game_id, playerId from '{CUR}/nhl_skater_game.parquet') k
            on k.game_id = f.gameId and k.playerId = f.playerId
          where f.typeCode = 517 and f.endTime_sec > f.startTime_sec)
        select sk.game_id, sk.player_id, sk.team,
               sum(case when sh.team = sk.team then sh.xg else 0 end) oxgf, sum(case when sh.team <> sk.team then sh.xg else 0 end) oxga,
               sum(case when sh.team = sk.team then sh.hd else 0 end) ohdf, sum(case when sh.team <> sk.team then sh.hd else 0 end) ohda,
               sum(case when sh.team = sk.team then sh.g else 0 end) ogf, sum(case when sh.team <> sk.team then sh.g else 0 end) oga,
               sum(case when sh.team = sk.team then 1 else 0 end) ocf, sum(case when sh.team <> sk.team then 1 else 0 end) oca
        from sh join sk on sh.game_id = sk.game_id and sh.period = sk.period and sh.t > sk.a and sh.t <= sk.b
        group by 1, 2, 3""").df()


def matchups(con, season):
    return con.execute(f"""
        with s as (
          select sh.gameId game_id, sh.playerId pid, sh.teamAbbrev team, sh.period, sh.startTime_sec a, sh.endTime_sec b
          from '{CUR}/nhl_shifts/season={season}/*.parquet' sh
          join (select distinct game_id, playerId from '{CUR}/nhl_skater_game.parquet') k
            on k.game_id = sh.gameId and k.playerId = sh.playerId
          where sh.typeCode = 517 and sh.endTime_sec > sh.startTime_sec and cast(sh.gameId as varchar) like '____02%')
        select x.game_id, x.pid player_id, y.pid opp_id, sum(least(x.b, y.b) - greatest(x.a, y.a)) secs
        from s x join s y on x.game_id = y.game_id and x.team <> y.team and x.period = y.period and x.a < y.b and y.a < x.b
        group by 1, 2, 3""").df()


def main():
    con = duckdb.connect()
    o = onice(con)
    games = con.execute(f"select game_id, date from '{CUR}/nhl_games.parquet' where game_type = 2").df()
    games["date"] = pd.to_datetime(games.date)
    dep = pd.read_parquet(f"{CUR}/features/deployment.parquet")[["game_id", "player_id", "ev_sec"]]
    d = dep.merge(o.drop(columns=["team"]), on=["game_id", "player_id"], how="inner").merge(games, on="game_id")
    d.to_parquet(f"{OUT}/onice_player_game.parquet", index=False)
    # as-of rates (+ next-game sentinel row) shrunk to league average
    lg = {c: d[c].sum() / d.ev_sec.sum() * 3600 for c in ("oxgf", "oxga", "ohdf", "ohda", "ocf", "oca")}
    last = d.sort_values("date").groupby("player_id").tail(1)
    nxt = last[["player_id"]].assign(game_id=9_999_999_999, date=pd.Timestamp("2100-01-01"))
    a = pd.concat([d, nxt], ignore_index=True).fillna(0).sort_values(["player_id", "date", "game_id"])
    g = a.groupby("player_id", sort=False)
    n_eff = np.minimum(g.cumcount(), 2 * HL)
    sec = g.ev_sec.transform(lambda s: s.shift(1).ewm(halflife=HL, min_periods=1).mean()).fillna(0) * n_eff
    out = a[["game_id", "player_id"]].copy()
    for c, v in lg.items():
        m = g[c].transform(lambda s: s.shift(1).ewm(halflife=HL, min_periods=1).mean()).fillna(0) * n_eff
        out[f"on_{c}60"] = (m + v * K / 3600) / (sec + K) * 3600
    out["on_xgd60"] = out.on_oxgf60 - out.on_oxga60
    out.to_parquet(f"{OUT}/onice_player.parquet", index=False)
    print(f"on-ice rows {len(d):,}; league EV on-ice xGF60 {lg['oxgf']:.2f} (per skater-hour)")
    # matchups -> quality of competition (opponents' as-of on-ice xGA60 / xGF60), co-ice weighted
    seasons = sorted({s.split("=")[-1] for s in glob.glob(f"{CUR}/nhl_shifts/season=*")})
    parts = []
    for s in seasons:
        m = matchups(con, s)
        m = m[m.secs > 0].merge(out.rename(columns={"player_id": "opp_id"})[["game_id", "opp_id", "on_oxga60", "on_oxgf60"]],
                                on=["game_id", "opp_id"], how="left")
        m["wa"] = m.secs * m.on_oxga60.fillna(lg["oxga"])
        m["wf"] = m.secs * m.on_oxgf60.fillna(lg["oxgf"])
        q = m.groupby(["game_id", "player_id"], as_index=False)[["secs", "wa", "wf"]].sum()
        q["qoc_xga60"], q["qoc_xgf60"] = q.wa / q.secs, q.wf / q.secs
        q = q[["game_id", "player_id", "qoc_xga60", "qoc_xgf60"]]
        parts.append(q)
        print(s, len(q), flush=True)
    Q = pd.concat(parts, ignore_index=True)
    Q.to_parquet(f"{OUT}/matchup_player_game.parquet", index=False)
    print(f"matchups {len(Q):,}; QoC xGA60 sd {Q.qoc_xga60.std():.3f} (mean {Q.qoc_xga60.mean():.2f})")


if __name__ == "__main__":
    main()
