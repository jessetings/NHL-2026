"""H3: does our opportunity model add information beyond the market? Walk-forward by month.

For each market family, fit on all months < m, evaluate on month m:
  market-only:  logit(p) = a + b * logit(p_mkt)                       (recalibrated market)
  stack:        logit(p) = a + b * logit(p_mkt) + c * (logit(p_model) - logit(p_mkt)) + d * features
Report outer-fold Brier/log-loss, Brier skill vs raw market, and ROI of betting when stack edge > threshold
at the book's pregame close price (2026 per-book closes only, since that is executable).
Usage: python src/backtest/h3.py
"""
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression

CUR = "data/curated"
EPS = 1e-4
MODEL = __import__("os").environ.get("H3_MODEL", "v1")


def logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def model_prob(x):
    """Opportunity model from lagged features only (no market input)."""
    toi = 0.5 * x.toi_min_ewm15 + 0.5 * x.toi_min_ewm40
    k = np.floor(x.line)
    out = np.full(len(x), np.nan)
    sog = x.stat == "shots_onGoal"
    mu = (0.5 * x.sog60_ewm15 + 0.5 * x.sog60_ewm40) * toi / 60
    a = 0.045
    n = 1 / a
    out[sog] = stats.nbinom.sf(k[sog], n, n / (n + mu[sog]))
    for st, col in (("points", "goals60"), ("goals+assists", "points60"), ("assists", "assists60")):
        m = x.stat == st
        mu = (0.4 * x[f"{col}_ewm15"] + 0.6 * x[f"{col}_ewm40"]) * toi / 60
        out[m] = stats.poisson.sf(k[m], mu[m])
    return out


def run():
    c = pd.read_parquet(f"{CUR}/market/contracts.parquet")
    c = c[c.over_hit.notna() & ~c.push & (c.gp_career_prior >= 10)].copy()
    # benchmark: Pinnacle close if present, else DK, else consensus (consensus excluded for goals: contaminated)
    c["p_mkt"] = c.get("p_mult_pinnacle")
    for alt in ("p_mult_draftkings", "p_mult_fanduel"):
        c["p_mkt"] = c.p_mkt.fillna(c[alt])
    c["src"] = np.where(c.get("p_mult_pinnacle").notna(), "pinnacle",
                        np.where(c.p_mkt.notna(), "book", "consensus"))
    cons_ok = (c.stat != "points") & (c.line % 1 == 0.5)
    c.loc[c.p_mkt.isna() & cons_ok, "p_mkt"] = c.loc[c.p_mkt.isna() & cons_ok, "p_cons"]
    c = c[c.p_mkt.notna() & c.p_mkt.between(0.02, 0.98)]
    c = c[c.line % 1 == 0.5]
    if MODEL == "v2":       # prop model v2 (strength-split, shot quality, matchup) means
        pr = pd.read_parquet(f"{CUR}/models/props_v2_pred.parquet").drop(columns=["season"])
        c = c.merge(pr, on=["game_id", "player_id"], how="inner")
        k = np.floor(c.line)
        n = 1 / c.alpha_SOG
        c["p_model"] = np.select(
            [c.stat == "shots_onGoal", c.stat == "points", c.stat == "goals+assists", c.stat == "assists"],
            [stats.nbinom.sf(k, n, n / (n + c.mu_SOG)), stats.poisson.sf(k, c.mu_G),
             stats.poisson.sf(k, c.mu_PTS), stats.poisson.sf(k, c.mu_A)], np.nan)
    else:
        c["p_model"] = model_prob(c)
    c = c[np.isfinite(c.p_model)]
    c["ym"] = pd.to_datetime(c.date).dt.strftime("%Y-%m")
    c["lm"] = logit(c.p_mkt)
    c["ld"] = logit(c.p_model) - c.lm
    c["b2b"] = c.b2b.fillna(0)
    c["opp_sa"] = (c.opp_sa_ewm20 - 30) / 3
    c["home"] = c.is_home.astype(float)
    c["pp_min"] = (c.get("pp_sec_ewm20") / 60 - 1.3).fillna(0)
    c["pp_share"] = (c.get("pp_share_ewm20") - 0.4).fillna(0)
    c["ev_min"] = (c.get("ev_sec_ewm20") / 60 - 15).fillna(0) / 3
    c["toi_trend"] = (c.toi_min_ewm5 - c.toi_min_ewm40).fillna(0) / 2
    rows, bets = [], []
    for st, g in c.groupby("stat"):
        months = sorted(g.ym.unique())
        for i, m in enumerate(months):
            tr, te = g[g.ym < m], g[g.ym == m]
            if len(tr) < 3000 or len(te) < 200:
                continue
            X1 = ["lm"]
            X2 = ["lm", "ld", "b2b", "home", "pp_min", "pp_share", "ev_min", "toi_trend"]
            p = {}
            for name, X in (("market_recal", X1), ("stack", X2)):
                lr = LogisticRegression(C=1.0).fit(tr[X].fillna(0), tr.over_hit)
                p[name] = lr.predict_proba(te[X].fillna(0))[:, 1]
                if name == "stack":
                    coef = dict(zip(X, lr.coef_[0].round(3)))
            y = te.over_hit.values
            res = dict(stat=st, month=m, n=len(te), coef_ld=coef["ld"])
            for name, pp in (("market_raw", te.p_mkt.values), ("model", te.p_model.values),
                             ("market_recal", p["market_recal"]), ("stack", p["stack"])):
                pp = np.clip(pp, EPS, 1 - EPS)
                res[f"brier_{name}"] = np.mean((pp - y) ** 2)
                res[f"ll_{name}"] = -np.mean(y * np.log(pp) + (1 - y) * np.log(1 - pp))
            rows.append(res)
            # executable-price ROI: bet over/under at DK or FD close where stack edge >= 3 pts
            for book in ("draftkings", "fanduel"):
                if f"over_{book}" not in te:
                    continue
                t = te.assign(ps=p["stack"])
                t = t[t[f"over_{book}"].notna()]
                for side in ("over", "under"):
                    odds = t[f"{side}_{book}"].astype(float)
                    imp = np.where(odds > 0, 100 / (odds + 100), -odds / (-odds + 100))
                    ps = t.ps if side == "over" else 1 - t.ps
                    win = t.over_hit if side == "over" else 1 - t.over_hit
                    dec = np.where(odds > 0, 1 + odds / 100, 1 + 100 / -odds)
                    sel = (ps - imp) >= 0.03
                    for w, d, e in zip(win[sel], dec[sel], (ps - imp)[sel]):
                        bets.append(dict(stat=st, month=m, book=book, side=side, win=w, dec=d, edge=e,
                                         pnl=(d - 1) if w else -1))
    r = pd.DataFrame(rows)
    b = pd.DataFrame(bets)
    r.to_csv(f"reports/h3_folds_{MODEL}.csv", index=False)
    b.to_csv(f"reports/h3_bets_{MODEL}.csv", index=False)
    agg = r.groupby("stat").apply(lambda d: pd.Series({
        "folds": len(d), "n": d.n.sum(),
        **{f"brier_{k}": np.average(d[f"brier_{k}"], weights=d.n) for k in ("market_raw", "market_recal", "model", "stack")},
        "stack_beats_mkt_folds": int((d.brier_stack < d.brier_market_raw).sum()),
        "mean_coef_ld": d.coef_ld.mean()}))
    agg["BSS_stack_vs_mkt_%"] = (1 - agg.brier_stack / agg.brier_market_raw) * 100
    print(agg.round(5).to_string())
    if not b.empty:
        print("\nExecutable bets at DK/FD pregame close (stack edge >= 3pt), 2026 per-book window:")
        print(b.groupby(["stat", "side"]).agg(n=("pnl", "size"), hit=("win", "mean"), roi=("pnl", "mean"),
                                              avg_edge=("edge", "mean")).round(3).to_string())
    return agg, b


if __name__ == "__main__":
    run()
