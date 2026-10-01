"""Early card: price DK/FD player props with prop model v2 as soon as lines open (bet early, before the close).

Evidence (reports/open_edge.md, 2026-01-17+ per-book open/close):
  - the market moves toward the model between open and close (t = 20-43 in every prop market)
  - v2 SOG UNDERS with edge >= 6 pts at the OPEN price: +5.1% ROI (+-4.5%, n=1,912), CLV +0.5 pts
  - other markets / overs: CLV positive but ROI not significant -> shown as watchlist, not bets
Usage: python src/early_card.py [YYYY-MM-DD]    (uses the latest odds snapshot; run scripts/daily_refresh.sh first)
"""
import glob
import os
import re
import sys
import unicodedata

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import odds as O  # noqa: E402
import slate as SL  # noqa: E402
from models import props_v2 as V2  # noqa: E402

STAT = {"shots_onGoal": "SOG", "points": "G", "goals+assists": "PTS", "assists": "A"}
BET_RULE = {("SOG", "under"): 0.04}          # validated (level-corrected edge, open prices): +4.8% ROI, n=941, CLV +0.52
MAX_PER_GAME = 3
MIN_GP = 30
STAKE = 0.0075                               # 0.75% of bankroll per qualifying early bet (provisional signal)


def key(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def p_over(mk, mu, line, alpha):
    k = np.floor(line)
    if mk == "SOG":
        n = 1 / alpha
        return stats.nbinom.sf(k, n, n / (n + mu))
    return stats.poisson.sf(k, mu)


def main(date):
    snap = sorted(glob.glob("data/raw/odds/sgo_slate_alt_*.json") + glob.glob("data/raw/snapshots/*/*.json"))[-1]
    df = O.flatten(snap)
    pl = df[df.player.notna() & df.stat.isin(STAT) & (df.bt == "ou") & df.book.isin(["draftkings", "fanduel"]) & ~df.alt]
    goalies = {}
    try:                                   # DailyFaceoff expected starters (latest snapshot)
        import gzip
        import json
        fs = sorted(glob.glob("data/raw/dailyfaceoff/*.json.gz"))
        for g in (json.load(gzip.open(fs[-1]))["goalies"] or []) if fs else []:
            for side in ("home", "away"):
                t = SL.FULLNAME.get(g[f"{side}TeamName"])
                if t and g.get(f"{side}GoalieName"):
                    goalies[t] = g[f"{side}GoalieName"]
    except Exception:  # noqa: BLE001
        goalies = {}
    mu = V2.live(date, goalies or None)
    mu["k"] = mu.key + "|" + mu.team
    pl = pl.assign(team_abbr=pl.team.map(SL.SGO_TEAM), mk=pl.stat.map(STAT), pkey=pl.player.map(key))
    pl["k"] = pl.pkey + "|" + pl.team_abbr
    m = pl.merge(mu, on="k", how="inner", suffixes=("", "_v2"))
    rows = []
    for r in m.itertuples():
        mean = getattr(r, f"mu_{r.mk}")
        po = p_over(r.mk, mean, r.line, r.alpha_SOG)
        p = po if r.side == "over" else 1 - po
        imp = O.american_to_prob(r.odds)
        rows.append(dict(game=f"{r.opp}@{r.team_v2}" if r.is_home else f"{r.team_v2}@{r.opp}", player=r.player, unit=r.unit,
                         market=r.mk, side=r.side, line=r.line, book=r.book, odds=int(r.odds), mu=mean, p_v2=p,
                         implied=imp, edge=p - imp, gp=r.gp_prior, ev=p * (1 + (r.odds / 100 if r.odds > 0 else 100 / -r.odds)) - 1))
    t = pd.DataFrame(rows)
    # level correction (relative signal): market-implied mean per player-market from the de-vigged DK/FD pair,
    # slate-wide median v2/market ratio per market -> v2 means rescaled (robust to seasonal level drift)
    from scipy import optimize

    def mkt_mean(mk, p_over_fair, line, alpha):
        try:
            return optimize.brentq(lambda m: p_over(mk, m, line, alpha) - p_over_fair, 0.01, 15)
        except Exception:  # noqa: BLE001
            return np.nan
    pair = t.pivot_table(index=["player", "market", "line", "book"], columns="side", values="implied").dropna().reset_index()
    pair["p_fair"] = pair.over / (pair.over + pair.under)
    alpha = float(mu.alpha_SOG.iloc[0])
    pair["mu_mkt"] = [mkt_mean(mk, p, ln, alpha) for mk, p, ln in zip(pair.market, pair.p_fair, pair.line)]
    mm = pair.groupby(["player", "market"]).mu_mkt.median()
    t["mu_mkt"] = [mm.get((p, mk), np.nan) for p, mk in zip(t.player, t.market)]
    LVL = (t.drop_duplicates(["player", "market"]).pipe(lambda u: (u.mu / u.mu_mkt).groupby(u.market).median())).to_dict()
    t["mu_rel"] = t.mu / t.market.map(LVL)
    po = [p_over(mk, m, ln, alpha) for mk, m, ln in zip(t.market, t.mu_rel, t.line)]
    t["p_rel"] = np.where(t.side == "over", po, 1 - np.array(po))
    t["edge_raw"] = t.edge
    t["edge"] = t.p_rel - t.implied
    t["ev"] = t.p_rel / t.implied - 1
    t = t.sort_values("edge", ascending=False)
    best = t.drop_duplicates(["player", "market", "side", "line"])
    out = f"cards/{date}"
    os.makedirs(out, exist_ok=True)
    t.to_csv(f"{out}/early_all.csv", index=False)
    best = best[best.gp >= MIN_GP]                 # backtest population had real NHL history (thin samples shrink low)
    bets = best[[BET_RULE.get((mk, sd), 9) <= e for mk, sd, e in zip(best.market, best.side, best.edge)]]
    bets = bets.sort_values("edge", ascending=False).groupby("game").head(MAX_PER_GAME)   # shot volume correlates within a game
    L = [f"# Early Card — {date}", "",
         f"_Odds snapshot {os.path.basename(snap)}. Prop model v2 (strength-split EV/PP rates, xG/high-danger, opponent "
         "EV/PK allowed, opponent penalties → PP time, opposing goalie GSAx/HD). Bet these EARLY: the market moves toward "
         "v2 by close (t=20–43), so waiting gives the edge away._", "",
         f"## ✅ Bets — validated rule: SOG unders, level-corrected v2 edge ≥ 4 pts (backtest at open: +4.8% ROI ±6.5%, n=941, CLV +0.52; blanket unders −2.1%) · max {MAX_PER_GAME}/game · stake {STAKE:.2%} each", "", "_⏱️ Timing matters: the validated edge is at OPENING prices. Run this when DK/FD props open (morning ET). "
         "Near puck drop the same rule backtested −2.7% at close — late runs are informational/small stakes._", "",
         f"_v2 level vs market tonight: { {k: round(v, 3) for k, v in LVL.items()} } (ratios applied before edges)._", "",
         "| Player | Game | Unit | Bet | Price | v2 mean (lvl-adj) | v2 p | Implied | Edge | EV |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in bets.itertuples():
        L.append(f"| {r.player} | {r.game} | {r.unit} | {r.side.title()} {r.line:g} SOG | {r.book[:2].upper()} {r.odds:+d} | "
                 f"{r.mu_rel:.2f} | {r.p_rel:.1%} | {r.implied:.1%} | {r.edge:+.1%} | {r.ev:+.1%} |")
    if bets.empty:
        L.append("| — none at current prices — | | | | | | | | | |")
    L += ["", "## 👀 Watchlist — v2 edge ≥ 6 pts in markets without a validated ROI (CLV positive historically; not bets)", "",
          "| Player | Game | Market | Bet | Price | v2 p | Implied | Edge |", "|---|---|---|---|---|---|---|---|"]
    w = best[(best.edge >= 0.06) & ~best.index.isin(bets.index)].head(25)
    for r in w.itertuples():
        L.append(f"| {r.player} | {r.game} | {r.market} | {r.side.title()} {r.line:g} | {r.book[:2].upper()} {r.odds:+d} | "
                 f"{r.p_rel:.1%} | {r.implied:.1%} | {r.edge:+.1%} |")
    open(f"{out}/EARLY.md", "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else SL.DATE)
