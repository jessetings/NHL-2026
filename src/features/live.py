"""Live (next-game) usage projections from all games played so far.

TOI projection = linear blend of EWMA(5/15/40) fitted out-of-sample (train 2022-25, test 2025-26:
MAE 1.87 min, r 0.845 vs 0.831 for EWMA15 alone). PP share = EWMA half-life 5 (r 0.87).
Usage: from features.live import usage; usage() -> DataFrame keyed by normalized name + team
"""
import re
import unicodedata

import duckdb
import numpy as np
import pandas as pd

CUR = "data/curated"
COEF = {"e5": 1.36, "e15": -1.015, "e40": 0.618, "d": 0.162, "b": 0.555}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def usage():
    con = duckdb.connect()
    d = con.execute(f"""
        select s.playerId as player_id, p.first, p.last, s.team, s.position, g.date, s.toi_sec / 60.0 toi,
               dp.pp_sec, dp.pk_sec
        from '{CUR}/nhl_skater_game.parquet' s join '{CUR}/nhl_games.parquet' g using(game_id)
        join '{CUR}/nhl_players.parquet' p on p.player_id = s.playerId
        left join '{CUR}/features/deployment.parquet' dp on dp.game_id = s.game_id and dp.player_id = s.playerId
        where g.game_type in (2, 3) order by s.playerId, g.date""").df()
    d["pp_sec"] = d.pp_sec.astype(float)
    team_pp = d.groupby(["team", "date"]).pp_sec.transform("max")
    d["pp_share"] = (d.pp_sec / team_pp.where(team_pp > 0)).astype(float)
    out = []
    for pid, g in d.groupby("player_id", sort=False):
        e = {hl: g.toi.ewm(halflife=hl).mean().iloc[-1] for hl in (5, 15, 40)}
        proj = COEF["b"] + COEF["e5"] * e[5] + COEF["e15"] * e[15] + COEF["e40"] * e[40] + \
            COEF["d"] * (g.position.iloc[-1] == "D")
        pps = g.pp_share.dropna()
        out.append(dict(player_id=pid, key=norm(g["first"].iloc[-1] + g["last"].iloc[-1]), last_team=g.team.iloc[-1],
                        gp=len(g), toi_proj=proj, toi_ewm5=e[5],
                        pp_share_proj=pps.ewm(halflife=5).mean().iloc[-1] if len(pps) else np.nan,
                        pp_min_ewm5=(g.pp_sec.dropna() / 60).ewm(halflife=5).mean().iloc[-1] if g.pp_sec.notna().any() else np.nan,
                        last_game=g.date.iloc[-1]))
    return pd.DataFrame(out)


if __name__ == "__main__":
    u = usage()
    print(u.sort_values("toi_proj", ascending=False).head(10).round(2).to_string(index=False))
