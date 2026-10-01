"""Historical backtest of the game simulator vs consensus closing lines (2025-26, ~2,000 games).

For each game the sim grid is solved to ONLY two inputs: the consensus close fair main total and moneyline.
Every other market is then priced out-of-sample by the sim and compared with (a) the consensus close fair
probability for that market and (b) the actual result:
  game: team totals, puck line          reg: total, team totals, spread, 3-way, 2-way ML (draw = push)
  1p:   total, team totals, spread, 3-way, 2-way ML
Tails (no market): total >= 9 / <= 3, |margin| >= 4, team shutout, team 5+, 1P 0-0 -- sim vs an
independent-Poisson baseline calibrated to the same total/ML.
Usage: python src/backtest/sim_games.py   -> reports/sim_backtest_*.csv + docs/findings/..._sim_backtest.md
"""
import os
import sys

import duckdb
import numpy as np
import pandas as pd
from scipy import optimize, stats

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from sim.grid import Grid, margin_dist, total_dist  # noqa: E402

ODDS = "data/curated/sgo_odds/*.parquet"
# SGO consensus close_fair before 2026-01-17 is frequently captured IN-GAME (moneyline log-loss 0.25-0.46 vs ~0.67
# pregame; up to half of games priced beyond 10/90). From 2026-01-17 it matches per-book puck-drop closes.
CLEAN_FROM = "2026-01-17"
BOOKS = ("draftkings", "fanduel")


def _p(o):
    o = float(o)
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def load():
    c = duckdb.connect()
    o = c.execute(f"""
        select eventID, oddID, any_value(close_fair_odds) fo, any_value(close_fair_line) fl
        from '{ODDS}' where player is null and stat = 'points' and not alt and close_fair_odds is not null
          and period in ('game', 'reg', '1p') and bt in ('ou', 'ml', 'sp', 'ml3way')
          and startsAt >= '{CLEAN_FROM}'
        group by 1, 2""").df()
    o["q"] = o.fo.map(_p)
    o["fl"] = pd.to_numeric(o.fl, errors="coerce")
    res = c.execute("""
        with g as (select m.eventID, g.game_id, g.home_score fh, g.away_score fa, g.season
                   from 'data/curated/map_sgo_event.parquet' m join 'data/curated/nhl_games.parquet' g using (game_id)
                   where g.home_score is not null),
             gl as (select game_id,
                      sum(case when period_number <= 3 and try_cast(eventOwnerTeamId as double) = home_id then 1 else 0 end) rh,
                      sum(case when period_number <= 3 and try_cast(eventOwnerTeamId as double) = away_id then 1 else 0 end) ra,
                      sum(case when period_number = 1 and try_cast(eventOwnerTeamId as double) = home_id then 1 else 0 end) h1,
                      sum(case when period_number = 1 and try_cast(eventOwnerTeamId as double) = away_id then 1 else 0 end) a1
                    from 'data/curated/nhl_pbp/*/*.parquet' where typeDescKey = 'goal' group by 1)
        select * from g join gl using (game_id)""").df()
    return o, res


def contracts(ev):
    """Two-way / three-way fair probabilities for one event: {key: (line, p_side_A_given_no_push)}."""
    d = {r.oddID: r for r in ev.itertuples()}
    out = {}

    def two(a, b, key):
        if a in d and b in d:
            qa, qb = d[a].q, d[b].q
            out[key] = (d[a].fl, qa / (qa + qb))
    for per in ("game", "reg", "1p"):
        two(f"points-all-{per}-ou-over", f"points-all-{per}-ou-under", f"{per}|total")
        two(f"points-home-{per}-ou-over", f"points-home-{per}-ou-under", f"{per}|home_tt")
        two(f"points-away-{per}-ou-over", f"points-away-{per}-ou-under", f"{per}|away_tt")
        two(f"points-home-{per}-sp-home", f"points-away-{per}-sp-away", f"{per}|home_sp")
        two(f"points-home-{per}-ml-home", f"points-away-{per}-ml-away", f"{per}|ml")
        k3 = [f"points-home-{per}-ml3way-home", f"points-all-{per}-ml3way-draw", f"points-away-{per}-ml3way-away"]
        if all(k in d for k in k3):
            q = np.array([d[k].q for k in k3])
            out[f"{per}|3way"] = (None, q / q.sum())
    return out


def sim_prob(pm, kind, line):
    """P(side A wins | no push) from a score PMF; side A = over / home."""
    if kind == "total":
        dist = total_dist(pm); kk = np.arange(len(dist)); win, push = dist[kk > line].sum(), dist[kk == line].sum()
    elif kind in ("home_tt", "away_tt"):
        dist = pm.sum(1) if kind == "home_tt" else pm.sum(0); kk = np.arange(len(dist))
        win, push = dist[kk > line].sum(), dist[kk == line].sum()
    elif kind == "home_sp":
        dist = margin_dist(pm); kk = np.arange(len(dist)) - (pm.shape[0] - 1)
        win, push = dist[kk + line > 0].sum(), dist[kk + line == 0].sum()
    elif kind == "ml":
        win, push = np.tril(pm, -1).sum(), np.trace(pm)
    elif kind == "3way":
        return np.array([np.tril(pm, -1).sum(), np.trace(pm), np.triu(pm, 1).sum()])
    return float(win / max(1 - push, 1e-12))


def outcome(kind, line, h, a):
    """1 = side A wins, 0 = loses, None = push."""
    if kind == "total":
        v = h + a; return None if v == line else float(v > line)
    if kind in ("home_tt", "away_tt"):
        v = h if kind == "home_tt" else a; return None if v == line else float(v > line)
    if kind == "home_sp":
        v = h - a + line; return None if v == 0 else float(v > 0)
    if kind == "ml":
        return None if h == a else float(h > a)
    if kind == "3way":
        return 0 if h > a else (1 if h == a else 2)


def poisson_pm(lh, la, k=16):
    return np.outer(stats.poisson.pmf(np.arange(k), lh), stats.poisson.pmf(np.arange(k), la))


def poisson_solve(line, p_over, p_home):
    """Independent Poisson (regulation) + OT coin, the textbook baseline, matched to the same two inputs."""
    def final_pm(x):
        lh, la = np.exp(x)
        m = poisson_pm(lh, la)
        f = m.copy()
        tie = np.diag(m).copy()
        np.fill_diagonal(f, 0)
        ph_ot = 0.52
        for i in range(15):
            f[i + 1, i] += tie[i] * ph_ot
            f[i, i + 1] += tie[i] * (1 - ph_ot)
        return f

    def resid(x):
        f = final_pm(x)
        po, ph = sim_prob(f, "total", line), np.tril(f, -1).sum()
        return [np.log(po / (1 - po)) - np.log(p_over / (1 - p_over)), np.log(ph / (1 - ph)) - np.log(p_home / (1 - p_home))]
    s = optimize.least_squares(resid, np.log([3.1, 2.9]), bounds=(np.log(0.5), np.log(8)))
    return final_pm(s.x)


def ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def main():
    o, res = load()
    G = Grid()
    res = res.set_index("eventID")
    rows, tails, PM = [], [], {}
    for ev_id, ev in o.groupby("eventID"):
        if ev_id not in res.index:
            continue
        cs = contracts(ev)
        if "game|total" not in cs or "game|ml" not in cs:
            continue
        g = res.loc[ev_id]
        if isinstance(g, pd.DataFrame):
            g = g.iloc[0]
        line, po = cs["game|total"]
        ph = cs["game|ml"][1]
        if not (0.15 < po < 0.85 and 0.1 < ph < 0.9 and 4 <= line <= 8):
            continue                                       # broken / stale consensus rows
        x, d = G.solve(line, po, ph)
        pois = poisson_solve(line, po, ph)
        scores = {"game": (g.fh, g.fa), "reg": (g.rh, g.ra), "1p": (g.h1, g.a1)}
        pm = {"game": d["final"], "reg": d["reg"], "1p": d["p1"]}
        PM[ev_id] = (pm, scores)
        for key, (ln, q) in cs.items():
            per, kind = key.split("|")
            if key in ("game|total", "game|ml"):
                continue                                   # the two inputs: in-sample by construction
            h, a = scores[per]
            if kind == "3way":
                sp = sim_prob(pm[per], kind, ln)
                y = outcome(kind, ln, h, a)
                for i, nm in enumerate(("home", "draw", "away")):
                    rows.append(dict(eventID=ev_id, season=g.season, market=f"{per}|3way_{nm}", line=np.nan,
                                     mkt=q[i], sim=sp[i], y=float(y == i)))
                continue
            y = outcome(kind, ln, h, a)
            if y is None or ln is None or (kind != "ml" and pd.isna(ln)):
                continue
            rows.append(dict(eventID=ev_id, season=g.season, market=key, line=ln, mkt=q, sim=sim_prob(pm[per], kind, ln), y=y))
        # tails (no market): sim vs Poisson baseline
        fh, fa = g.fh, g.fa
        td_s, td_p = total_dist(d["final"]), total_dist(pois)
        md_s, md_p = margin_dist(d["final"]), margin_dist(pois)
        kk = np.arange(len(td_s)); mm = np.arange(len(md_s)) - 15
        hs_s, as_s, hs_p, as_p = d["final"].sum(1), d["final"].sum(0), pois.sum(1), pois.sum(0)
        for nm, ps, pp, y in (
                ("total>=9", td_s[kk >= 9].sum(), td_p[kk >= 9].sum(), fh + fa >= 9),
                ("total<=3", td_s[kk <= 3].sum(), td_p[kk <= 3].sum(), fh + fa <= 3),
                ("total=even", td_s[kk % 2 == 0].sum(), td_p[kk % 2 == 0].sum(), (fh + fa) % 2 == 0),
                ("|margin|>=4", md_s[np.abs(mm) >= 4].sum(), md_p[np.abs(mm) >= 4].sum(), abs(fh - fa) >= 4),
                ("|margin|=1", md_s[np.abs(mm) == 1].sum(), md_p[np.abs(mm) == 1].sum(), abs(fh - fa) == 1),
                ("|margin|=3", md_s[np.abs(mm) == 3].sum(), md_p[np.abs(mm) == 3].sum(), abs(fh - fa) == 3),
                ("home shutout", as_s[0], as_p[0], fa == 0), ("away shutout", hs_s[0], hs_p[0], fh == 0),
                ("home 5+", hs_s[5:].sum(), hs_p[5:].sum(), fh >= 5), ("away 5+", as_s[5:].sum(), as_p[5:].sum(), fa >= 5),
                ("reg tie", np.trace(d["reg"]), None, g.rh == g.ra), ("1P 0-0", d["p1"][0, 0], None, g.h1 + g.a1 == 0)):
            tails.append(dict(eventID=ev_id, tail=nm, sim=ps, pois=pp, y=float(y)))
    B, T = pd.DataFrame(rows), pd.DataFrame(tails)
    os.makedirs("reports", exist_ok=True)
    B.to_csv("reports/sim_backtest_markets.csv", index=False)
    T.to_csv("reports/sim_backtest_tails.csv", index=False)
    M = money_test(PM)
    M.to_csv("reports/sim_backtest_money.csv", index=False)
    report(B, T, M)


def side_prob(pm, entity, bt, side, line):
    """(P(win), P(push)) for one side of a game-level contract from a score PMF."""
    k = pm.shape[0]
    if bt == "ou":
        dist = total_dist(pm) if entity == "all" else (pm.sum(1) if entity == "home" else pm.sum(0))
        kk = np.arange(len(dist))
        win = dist[kk > line].sum() if side == "over" else dist[kk < line].sum()
        return win, dist[kk == line].sum()
    if bt == "sp":
        dist = margin_dist(pm); kk = np.arange(len(dist)) - (k - 1)
        if side == "away":
            kk = -kk
        return dist[kk + line > 0].sum(), dist[kk + line == 0].sum()
    hw, dr, aw = np.tril(pm, -1).sum(), np.trace(pm), np.triu(pm, 1).sum()
    if bt == "ml":                                        # 2-way: a draw (reg / 1p) is a push
        return (hw if side == "home" else aw), dr
    if bt == "ml3way":
        return {"home": hw, "draw": dr, "away": aw}[side], 0.0
    return np.nan, np.nan


def side_outcome(entity, bt, side, line, h, a):
    """Result of one bet side: 1 win, 0 loss, 0.5 push marker -> returned as None for push."""
    if bt == "ou":
        v = h + a if entity == "all" else (h if entity == "home" else a)
        return None if v == line else float((v > line) if side == "over" else (v < line))
    if bt == "sp":
        m = (h - a) if side == "home" else (a - h)
        return None if m + line == 0 else float(m + line > 0)
    if bt == "ml":
        if h == a:
            return None
        return float((h > a) if side == "home" else (a > h))
    if bt == "ml3way":
        return float({"home": h > a, "draw": h == a, "away": a > h}[side])


def money_test(PM):
    """Bet every DK/FD closing price (book's own line) where the sim shows EV; grade on actual results."""
    c = duckdb.connect()
    b = c.execute(f"""
        select eventID, oddID, entity, period, bt, side, book, any_value(book_close_odds) odds, any_value(book_close_line) line
        from '{ODDS}' where player is null and stat = 'points' and not alt and book in {BOOKS}
          and book_close_odds is not null and period in ('game', 'reg', '1p') and bt in ('ou', 'ml', 'sp', 'ml3way')
          and startsAt >= '{CLEAN_FROM}'
        group by all""").df()
    out = []
    for r in b.itertuples():
        if r.eventID not in PM or (r.period == "game" and r.bt == "ml") or (r.period == "game" and r.bt == "ou" and r.entity == "all"):
            continue                                      # main total & ML are the sim's inputs
        pm, scores = PM[r.eventID]
        line = 0.0 if r.bt in ("ml", "ml3way") else r.line
        if line is None or pd.isna(line):
            continue
        win, push = side_prob(pm[r.period], r.entity, r.bt, r.side, line)
        dec = 1 + (r.odds / 100 if r.odds > 0 else 100 / -r.odds)
        h, a = scores[r.period]
        y = side_outcome(r.entity, r.bt, r.side, line, h, a)
        pnl = 0.0 if y is None else (dec - 1 if y == 1 else -1.0)
        out.append(dict(eventID=r.eventID, market=f"{r.period}|{r.entity}|{r.bt}", side=r.side, line=line, book=r.book,
                        odds=r.odds, sim_win=win, sim_push=push, ev=win * dec + push - 1, implied=1 / dec, pnl=pnl,
                        win=y))
    return pd.DataFrame(out)


def report(B, T, M=None):
    L = []
    B["ll_m"], B["ll_s"] = ll(B.mkt, B.y), ll(B.sim, B.y)
    B["ll_b"] = ll(0.5 * B.mkt + 0.5 * B.sim, B.y)
    L += ["| Market | n | Outcome rate | Mkt mean | Sim mean | LogLoss mkt | LogLoss sim | Δ (sim−mkt) ×1000 | ±2se | Blend Δ ×1000 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for m, x in B.groupby("market"):
        dd = (x.ll_s - x.ll_m)
        L.append(f"| {m} | {len(x)} | {x.y.mean():.3f} | {x.mkt.mean():.3f} | {x.sim.mean():.3f} | {x.ll_m.mean():.4f} | "
                 f"{x.ll_s.mean():.4f} | {1000 * dd.mean():+.1f} | {2000 * dd.std() / np.sqrt(len(x)):.1f} | "
                 f"{1000 * (x.ll_b - x.ll_m).mean():+.1f} |")
    L += ["", "| Tail | n | Actual | Sim | Poisson | LogLoss sim − Poisson ×1000 | ±2se |", "|---|---|---|---|---|---|---|"]
    for t, x in T.groupby("tail", sort=False):
        if x.pois.isna().all():
            L.append(f"| {t} | {len(x)} | {x.y.mean():.3f} | {x.sim.mean():.3f} | — | — | — |")
            continue
        dd = ll(x.sim, x.y) - ll(x.pois.astype(float), x.y)
        L.append(f"| {t} | {len(x)} | {x.y.mean():.3f} | {x.sim.mean():.3f} | {x.pois.mean():.3f} | "
                 f"{1000 * dd.mean():+.1f} | {2000 * dd.std() / np.sqrt(len(x)):.1f} |")
    if M is not None and len(M):
        L += ["", "**Money test: flat 1u on every DK/FD closing price with sim EV above threshold**", "",
              "| Market | EV > 0 bets | ROI | EV > 3% bets | ROI | ±2se | EV > 6% bets | ROI | All prices ROI (vig check) |",
              "|---|---|---|---|---|---|---|---|---|"]
        for m, x in list(M.groupby("market")) + [("ALL", M)]:
            def roi(t):
                z = x[x.ev > t]
                return len(z), (z.pnl.mean() if len(z) else np.nan), (2 * z.pnl.std() / np.sqrt(len(z)) if len(z) > 1 else np.nan)
            n0, r0, _ = roi(0); n3, r3, s3 = roi(0.03); n6, r6, _ = roi(0.06)
            L.append(f"| {m} | {n0} | {r0:+.1%} | {n3} | {r3:+.1%} | {s3:.1%} | {n6} | {r6:+.1%} | {x.pnl.mean():+.1%} |")
    print("\n".join(L))
    open("reports/sim_backtest_summary.md", "w").write("\n".join(L))


if __name__ == "__main__":
    main()
