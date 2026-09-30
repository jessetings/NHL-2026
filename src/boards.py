"""Goal-scoring & points boards: anytime goal (AG), 2+ goals, first goal scorer (FGS), points, assists.

FGS uses a Poisson race: with player goal rates lambda_i and total game rate Lambda,
  P(player i scores the first goal) = lambda_i / Lambda * (1 - exp(-Lambda)).
lambda_i comes from (a) our model and (b) the de-vigged AG market (market-implied mean);
Lambda from the de-vigged Pinnacle/consensus game total. FGS books carry ~30-45% margin, so this mostly
yields fair prices and kill prices; a bet needs price >= kill.
Usage: python src/boards.py   (after run_slate.py)
"""
import glob
import os
import sys

import numpy as np
import pandas as pd
from scipy import optimize, stats

sys.path.insert(0, os.path.dirname(__file__))
import odds as O  # noqa: E402

OUT = "cards/2026-09-30"
EN_SHARE = 0.03   # share of a player's goal rate that is empty-net (cannot be a first goal)
TEAM = {"PITTSBURGH_PENGUINS_NHL": "PIT", "PHILADELPHIA_FLYERS_NHL": "PHI", "NEW_YORK_ISLANDERS_NHL": "NYI",
        "TORONTO_MAPLE_LEAFS_NHL": "TOR", "LOS_ANGELES_KINGS_NHL": "LAK", "COLORADO_AVALANCHE_NHL": "COL"}


def dec(o):
    return 1 + (o / 100 if o > 0 else 100 / -o)


def ev(p, o):
    return p * dec(o) - 1


def fmt(o):
    return f"{int(o):+d}" if o is not None and not pd.isna(o) else "—"


def total_mean(df, ev_id):
    """Market-implied expected total goals from de-vigged two-way totals (Pinnacle preferred)."""
    t = df[(df.eventID == ev_id) & (df.stat == "points") & (df.entity == "all") & (df.bt == "ou")]
    best = []
    for (book, line), g in t.groupby(["book", "line"]):
        o, u = g[g.side == "over"].odds, g[g.side == "under"].odds
        if len(o) and len(u) and not float(line).is_integer():
            p = O.american_to_prob(o.iloc[0]) / (O.american_to_prob(o.iloc[0]) + O.american_to_prob(u.iloc[0]))
            w = 2 if book == "pinnacle" else 1
            m = optimize.brentq(lambda m: stats.poisson.sf(np.floor(line), m) - p, 0.5, 15)
            best.append((m, w))
    return float(np.average([m for m, _ in best], weights=[w for _, w in best])) if best else 6.0


def main():
    pr = pd.read_csv(f"{OUT}/props_all.csv")
    snap = sorted(glob.glob("data/raw/odds/sgo_slate_alt_*.json"))[-1]
    df = O.flatten(snap)
    ids = df.drop_duplicates("eventID")[["eventID", "home", "away"]]
    ids["game"] = ids.away.map(TEAM) + "@" + ids.home.map(TEAM)
    L = [f"# Goals & Points Boards — {OUT.split('/')[-1]}", "",
         f"_Odds snapshot {os.path.basename(snap)}. p_model / p_mkt = our model / de-vigged market. "
         "Kill = worst price with >=2.5pt edge on the blended probability (40% model / 60% market). "
         "EV uses the blended probability._", ""]

    # ---------------- AG + 2+ goals
    g = pr[(pr.market == "G") & (pr.side == "over")].sort_values("ev", ascending=False)
    for line, title in ((0.5, "Anytime goal"), (1.5, "2+ goals")):
        b = g[g.line == line].drop_duplicates("player").sort_values("blend_p", ascending=False)
        b = b[b.blend_p >= (0.12 if line == 0.5 else 0.03)]
        L += [f"## {title} — best DK/FD price per player", "",
              "| Player | Game | Role | Best | p_model | p_mkt | p_blend | Fair | Kill | EV | Verdict |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in b.head(30).itertuples():
            verdict = ("**BET**" if r.ev >= 0.05 and r.model_p >= r.implied and r.mkt_p >= r.implied - 0.005
                       else "lean" if r.ev >= 0.02 else "pass")
            L.append(f"| {r.player} | {r.game} | {r.role}/{r.pp} | {r.book[:2].upper()} {r.odds:+d} | "
                     f"{r.model_p:.1%} | {r.mkt_p:.1%} | {r.blend_p:.1%} | {fmt(r.fair_blend)} | "
                     f"{fmt(r.ceiling)} | {r.ev:+.1%} | {verdict} |")
        L.append("")

    # ---------------- FGS via Poisson race
    fg_rows = []
    gm = pr[(pr.market == "G") & (pr.line == 0.5)].drop_duplicates("player")
    for _, e in ids.iterrows():
        lam_tot = total_mean(df, e.eventID)
        sub = gm[gm.game == e.game]
        lam_model = sub.set_index("player").model_mean * (1 - EN_SHARE)
        lam_mkt = sub.set_index("player").mkt_mean * (1 - EN_SHARE)
        f = df[(df.eventID == e.eventID) & (df.stat == "firstToScore") & (df.side == "yes") & ~df.alt &
               df.book.isin(["draftkings", "fanduel"]) & df.player.notna()]
        best = f.sort_values("odds", ascending=False).drop_duplicates("player")
        scale = (1 - np.exp(-lam_tot)) / lam_tot
        for r in best.itertuples():
            if r.player not in lam_mkt.index:
                continue
            pm = lam_model.get(r.player, np.nan) * scale
            pk = lam_mkt[r.player] * scale
            pb = 0.4 * pm + 0.6 * pk if not np.isnan(pm) else pk
            fg_rows.append(dict(game=e.game, player=r.player, book=r.book, odds=int(r.odds), lam_tot=lam_tot,
                                p_model=pm, p_mkt=pk, p_blend=pb, implied=O.american_to_prob(r.odds),
                                ev=ev(pb, r.odds), fair=O.prob_to_american(pb),
                                kill=O.prob_to_american(max(pb - 0.01, 1e-4))))
    fg = pd.DataFrame(fg_rows).sort_values("p_blend", ascending=False)
    fg.to_csv(f"{OUT}/fgs_board.csv", index=False)
    lt = fg.groupby("game").lam_tot.first().round(2).to_dict()
    L += ["## First goal scorer (Poisson race from AG market + totals)", "",
          f"Expected total goals (de-vigged market): {lt}. FGS boards carry roughly 30-45% margin; "
          "kill = fair price with a 1pt edge.", "",
          "| Player | Game | Best | p_model | p_mkt | p_blend | Fair | Kill | EV | Verdict |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in fg.head(25).itertuples():
        verdict = "**BET**" if r.ev >= 0.10 and r.p_model >= r.implied else ("lean" if r.ev >= 0.03 else "pass")
        L.append(f"| {r.player} | {r.game} | {r.book[:2].upper()} {r.odds:+d} | {r.p_model:.1%} | {r.p_mkt:.1%} | "
                 f"{r.p_blend:.1%} | {fmt(r.fair)} | {fmt(r.kill)} | {r.ev:+.1%} | {verdict} |")
    L.append("")

    # ---------------- points & assists
    for mk, line, title in (("PTS", 0.5, "1+ point"), ("PTS", 1.5, "2+ points"), ("A", 0.5, "1+ assist")):
        b = pr[(pr.market == mk) & (pr.line == line) & (pr.side == "over")].sort_values("ev", ascending=False)
        b = b.drop_duplicates("player").sort_values("ev", ascending=False)
        L += [f"## {title} — top 15 by EV", "",
              "| Player | Game | Role | Best | p_model | p_mkt | p_blend | Fair | Kill | EV |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for r in b.head(15).itertuples():
            L.append(f"| {r.player} | {r.game} | {r.role}/{r.pp} | {r.book[:2].upper()} {r.odds:+d} | {r.model_p:.1%} | "
                     f"{r.mkt_p:.1%} | {r.blend_p:.1%} | {fmt(r.fair_blend)} | {fmt(r.ceiling)} | {r.ev:+.1%} |")
        L.append("")
    open(f"{OUT}/BOARDS.md", "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
