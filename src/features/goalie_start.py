"""Goalie start model: P(goalie starts team's next game) from pregame-only signals.

Candidates per team-game = goalies who appeared for that team in its previous 20 games.
Features (all lagged): share of team starts over last 10 / 30 games, started previous team game,
team on 2nd night of back-to-back, interaction (started previous x b2b), starts in last 14 days, days since last start.
Walk-forward: train seasons < S, test season S. Metric: accuracy of top-probability goalie per team-game
vs baseline 'goalie with most starts in last 10'.
Usage: python src/features/goalie_start.py
"""
import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

CUR = "data/curated"


def build():
    con = duckdb.connect()
    g = con.execute(f"""
        select k.game_id, k.team, k.playerId as goalie_id, k.starter, gm.date, gm.season
        from '{CUR}/nhl_goalie_game.parquet' k join '{CUR}/nhl_games.parquet' gm using(game_id)
        where gm.game_type = 2""").df()
    g["date"] = pd.to_datetime(g.date)
    starts = g[g.starter == True][["game_id", "team", "goalie_id", "date", "season"]]  # noqa: E712
    tg = starts.sort_values(["team", "date"]).reset_index(drop=True)
    tg["gidx"] = tg.groupby("team").cumcount()
    tg["prev_date"] = tg.groupby("team").date.shift(1)
    tg["b2b"] = ((tg.date - tg.prev_date).dt.days == 1).astype(int)
    rows = []
    for team, t in tg.groupby("team"):
        t = t.reset_index(drop=True)
        gl = t.goalie_id.values
        dates = t.date.values
        for i in range(20, len(t)):
            hist = gl[max(0, i - 30):i]
            cands = set(gl[max(0, i - 20):i])
            for c in cands:
                last10 = (gl[i - 10:i] == c).mean()
                last30 = (hist == c).mean()
                prev = int(gl[i - 1] == c)
                recent = (gl[:i] == c) & (dates[:i] >= dates[i] - np.timedelta64(14, "D"))
                last_start = np.where(gl[:i] == c)[0]
                days_since = (dates[i] - dates[last_start[-1]]) / np.timedelta64(1, "D") if len(last_start) else 60
                rows.append(dict(team=team, game_id=t.game_id[i], season=t.season[i], goalie_id=c,
                                 y=int(gl[i] == c), s10=last10, s30=last30, prev=prev, b2b=t.b2b[i],
                                 prev_b2b=prev * t.b2b[i], starts14=int(recent.sum()), days_since=min(days_since, 60)))
    return pd.DataFrame(rows)


X = ["s10", "s30", "prev", "b2b", "prev_b2b", "starts14", "days_since"]


def evaluate(d):
    out = []
    for s in sorted(d.season.unique())[1:]:
        tr, te = d[d.season < s], d[d.season == s].copy()
        lr = LogisticRegression(max_iter=1000).fit(tr[X], tr.y)
        te["p"] = lr.predict_proba(te[X])[:, 1]
        te["p"] = te.p / te.groupby(["team", "game_id"]).p.transform("sum")
        top = te.loc[te.groupby(["team", "game_id"]).p.idxmax()]
        base = te.loc[te.groupby(["team", "game_id"]).s10.idxmax()]
        b2b = top[top.b2b == 1]
        out.append(dict(season=s, games=len(top), acc_model=top.y.mean(), acc_baseline=base.y.mean(),
                        acc_model_b2b=b2b.y.mean(), n_b2b=len(b2b),
                        brier=((te.p - te.y) ** 2).mean()))
    return pd.DataFrame(out), lr


if __name__ == "__main__":
    d = build()
    r, lr = evaluate(d)
    print(r.round(3).to_string(index=False))
    print(dict(zip(X, lr.coef_[0].round(3))))
    d.to_parquet(f"{CUR}/features/goalie_start_train.parquet", index=False)
