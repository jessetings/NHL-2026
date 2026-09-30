"""Pyramid card: BASE (cash-game), MIDDLE, TOP (GPP singles + cross-game parlays) with bankroll %.

Inputs: cards/<date>/props_all.csv from run_slate.py. Probabilities: blend_p = 0.4 model + 0.6 de-vigged market.
Staking: nightly budget split by tier, within tier by quarter-Kelly on blend_p, with per-bet/per-player caps.
Parlays: cross-game only (independent legs, priced exactly as product). Same-game combos are NOT priced
until the joint simulator exists.
Usage: python src/build_pyramid.py [--budget 0.10]
"""
import argparse
import itertools
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

OUT = "cards/2026-09-30"
TIER_SHARE = {"BASE": 0.50, "MIDDLE": 0.30, "TOP": 0.20}
BET_CAP = {"BASE": 0.020, "MIDDLE": 0.010, "TOP": 0.005}     # of bankroll
PLAYER_CAP = 0.03
MKT = {"SOG": "SOG", "PTS": "pts", "A": "ast", "G": "goals"}


def dec(o):
    return 1 + (o / 100 if o > 0 else 100 / -o)


def amer(d):
    return round((d - 1) * 100) if d >= 2 else round(-100 / (d - 1))


def pick_label(r):
    k = int(r.line + 0.5)
    return f"{r.player} {k}+ {MKT[r.market]}" if r.side == "over" else f"{r.player} U{r.line:g} {MKT[r.market]}"


def load():
    pr = pd.read_csv(f"{OUT}/props_all.csv")
    pr = pr[pr.mkt_p.notna() & (pr.decision != "data-check")].copy()
    pr = pr.sort_values("ev", ascending=False).drop_duplicates(["player", "market", "line", "side"])
    pr["m_edge"] = pr.model_p - pr.implied
    pr["k_edge"] = pr.mkt_p - pr.implied
    pr["dec"] = pr.odds.map(dec)
    pr["pick"] = pr.apply(pick_label, axis=1)
    return pr


def tiers(pr):
    base = pr[(pr.implied >= 0.42) & (pr.ev >= 0.025) & (pr.m_edge >= -0.01) & (pr.k_edge >= -0.01)]
    mid = pr[(pr.implied >= 0.22) & (pr.implied < 0.42) & (pr.ev >= 0.05) &
             (np.maximum(pr.m_edge, pr.k_edge) >= 0.015) & (np.minimum(pr.m_edge, pr.k_edge) >= -0.01)]
    floor = np.where(pr.market == "G", 0.03, 0.05)   # 2+ goal lottery tickets allowed down to +3200
    top = pr[(pr.implied >= floor) & (pr.implied < 0.22) & (pr.ev >= 0.06) & (pr.m_edge >= 0) & (pr.k_edge >= -0.002)]
    out = []
    for name, df, n in (("BASE", base, 8), ("MIDDLE", mid, 10), ("TOP", top, 8)):
        out.append(df.head(n).assign(tier=name))
    return pd.concat(out, ignore_index=True)


def stake(card, budget):
    card["kelly"] = ((card.dec * card.blend_p - 1) / (card.dec - 1)).clip(lower=0) * 0.25
    for t in TIER_SHARE:
        m = card.tier == t
        w = card.loc[m, "kelly"]
        if w.sum() > 0:
            card.loc[m, "stake"] = np.minimum(w / w.sum() * budget * TIER_SHARE[t], BET_CAP[t])
    card["stake"] = card.stake.fillna(0)
    # per-player cap (nested rungs / same player across tiers count as one exposure)
    tot = card.groupby("player").stake.transform("sum")
    card["stake"] = np.where(tot > PLAYER_CAP, card.stake * PLAYER_CAP / tot, card.stake)
    return card


def parlays(legs, max_legs=3):
    rows = []
    legs = legs.to_dict("records")
    for k in range(2, max_legs + 1):
        for combo in itertools.combinations(legs, k):
            games = [c["game"] for c in combo]
            if len(set(games)) < k:          # cross-game only
                continue
            p = float(np.prod([c["blend_p"] for c in combo]))
            d = float(np.prod([c["dec"] for c in combo]))
            rows.append(dict(legs=" + ".join(f"{c['pick']} ({c['book'][:2].upper()} {c['odds']:+d})" for c in combo),
                             n=k, payout_x=d, american=amer(d), p=p, ev=p * d - 1,
                             fair_x=1 / p))
    return pd.DataFrame(rows)


def main(budget):
    pr = load()
    card = stake(tiers(pr), budget)
    legs = card[card.tier.isin(["BASE", "MIDDLE", "TOP"])]
    pl = parlays(legs)
    bands = [(1, 5, "2-5x"), (5, 20, "5-20x"), (20, 60, "20-60x"), (60, 1e9, "60x+ (100x-style)")]
    top_parlays = []
    for lo, hi, lab in bands:
        b = pl[(pl.payout_x >= lo) & (pl.payout_x < hi) & (pl.ev > 0)].sort_values("ev", ascending=False).head(4)
        top_parlays.append(b.assign(band=lab))
    tp = pd.concat(top_parlays, ignore_index=True)
    # parlay stakes come out of the TOP tier budget: 0.25% each, 0.1% for 60x+
    tp["stake"] = np.where(tp.payout_x >= 60, 0.001, 0.0025)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L = [f"# Pyramid Card — {OUT.split('/')[-1]}", "",
         f"_Generated {ts}. Odds snapshot: {pr.snapshot.iloc[0]}. Nightly risk budget {budget:.0%} of bankroll "
         f"(BASE {TIER_SHARE['BASE']:.0%} / MIDDLE {TIER_SHARE['MIDDLE']:.0%} / TOP {TIER_SHARE['TOP']:.0%})._", "",
         "Stake = % of bankroll. **Kill price** = worst odds still worth betting. p = blended probability "
         "(40% model, 60% de-vigged market). EV per $1. Full AG / 2+ goals / first-goal / points boards: BOARDS.md", ""]
    for t, blurb in (("BASE", "cash-game tier: ~42-60% hit rate, near-even money"),
                     ("MIDDLE", "+140 to +350: justified by model AND market"),
                     ("TOP", "longshot singles: both model and market must agree")):
        c = card[card.tier == t]
        L += [f"## {t} — {blurb}", ""]
        if c.empty:
            L += ["_No qualifying bets._", ""]
            continue
        L += ["| Pick | Game | Role | Book/price | Kill | p (model / mkt) | Implied | EV | Stake |",
              "|---|---|---|---|---|---|---|---|---|"]
        for r in c.itertuples():
            L.append(f"| **{r.pick}** | {r.game} | {r.role}/{r.pp} | {r.book[:2].upper()} {r.odds:+d} | "
                     f"{int(r.ceiling):+d} | {r.blend_p:.1%} ({r.model_p:.0%} / {r.mkt_p:.0%}) | {r.implied:.1%} | "
                     f"{r.ev:+.1%} | {r.stake:.2%} |")
        L.append("")
    L += ["## TOP — cross-game parlays (GPP tickets)", "",
          "Legs are from the tiers above, one per game (independent), so the true probability is the product. "
          "Same-game parlays are not priced yet.", "",
          "| Band | Ticket | Pays | Hit prob | Fair pays | EV | Stake |", "|---|---|---|---|---|---|---|"]
    for r in tp.itertuples():
        L.append(f"| {r.band} | {r.legs} | {r.payout_x:.1f}x ({r.american:+d}) | {r.p:.1%} | {r.fair_x:.1f}x | "
                 f"{r.ev:+.1%} | {r.stake:.2%} |")
    # slate context
    best100 = pl[pl.payout_x >= 60].sort_values("p", ascending=False).head(1)
    n_pos = int((pl.ev > 0).sum())
    L += ["", "## Slate context", "",
          f"- Games: {card.game.nunique()} with qualifying legs. A 3-game slate caps cross-game parlays at 3 legs, "
          "which limits the size of 100x tickets.",
          f"- +EV parlay combinations available: {n_pos} of {len(pl)}.",
          (f"- Best 60x+ ticket hits {best100.p.iloc[0]:.1%} of the time (pays {best100.payout_x.iloc[0]:.0f}x). "
           f"**100x on the full bankroll is not realistic tonight.** Treat 60x+ tickets as lottery-sized (0.1%)."
           if not best100.empty else "- No 60x+ ticket from +EV legs tonight: **not a 100x slate.**"),
          f"- Total staked: singles {card.stake.sum():.2%} + parlays {tp.stake.sum():.2%} of bankroll.", ""]
    open(f"{OUT}/PYRAMID.md", "w").write("\n".join(L))
    card.to_csv(f"{OUT}/pyramid_singles.csv", index=False)
    tp.to_csv(f"{OUT}/pyramid_parlays.csv", index=False)
    print("\n".join(L))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=0.10)
    main(ap.parse_args().budget)
    sys.exit(0)
