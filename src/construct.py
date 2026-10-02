"""Construct the nightly pyramid from the quarry (raw materials).

Quarry = every +EV candidate (pyramid_singles.csv from build_pyramid.py = RAW_MATERIALS.md).
Each stone is inspected for cracks, enriched with historical hit rates at the exact line and matchup context,
scored, and placed:
  CAPSTONE      the 1-2 best spots on the slate (no cracks, both sources agree, history supports)
  UPPER COURSE  strong, at most one hairline crack
  MIDDLE COURSE solid, cracks noted
  FOUNDATION    high-probability cash-game stones
  RUBBLE        rejected from the build (fault line), with the reason
Crack taxonomy: HAIRLINE = minor, size down; FAULT = structural, do not build on it.
"""
import os
import gzip
import json
import glob
import re
import sys
import unicodedata
from datetime import datetime, timezone

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slate as SL  # noqa: E402
OUT = SL.OUT
CUR = "data/curated"
B2B = None                                  # derived from the NHL schedule on first use
BUDGET = 0.10                               # nightly singles budget (aggressive)
STAT = {"SOG": "sog", "G": "goals", "PTS": "points", "A": "assists"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def history():
    con = duckdb.connect()
    d = con.execute(f"""
        select s.playerId, p.first, p.last, s.team, s.position, g.season, g.date, s.sog, s.goals, s.assists, s.points,
               s.toi_sec
        from '{CUR}/nhl_skater_game.parquet' s join '{CUR}/nhl_games.parquet' g using(game_id)
        join '{CUR}/nhl_players.parquet' p on p.player_id = s.playerId
        where g.game_type = 2 order by g.date""").df()
    d["key"] = (d["first"] + d["last"]).map(norm)
    return d


def hit_rates(h, name, market, line, role=None):
    x = h[h.key == norm(name)]
    if x.empty:
        return {}
    if x.playerId.nunique() > 1:          # same name, different players (e.g. VAN's two Elias Petterssons)
        isd = str(role or "").startswith("d")
        y = x[(x.position == "D") == isd] if role else x.iloc[0:0]
        if y.playerId.nunique() != 1:
            return {}
        x = y
    col = STAT[market]
    k = int(np.floor(line)) + 1
    last = x[x.season == 20252026]
    l10 = x.tail(10)
    car = x
    last_team = x.team.iloc[-1]
    prev_team = last.team.iloc[-1] if len(last) else None
    return dict(gp_ly=len(last), hr_ly=(last[col] >= k).mean() if len(last) else np.nan,
                avg_ly=last[col].mean() if len(last) else np.nan,
                hr_l10=(l10[col] >= k).mean(), avg_l10=l10[col].mean(), n_l10=len(l10),
                hr_car=(car[col] >= k).mean(), gp_car=len(car), toi_ly=last.toi_sec.mean() / 60 if len(last) else np.nan,
                team_ly=prev_team, last_team=last_team)


def goalie_status():
    f = sorted(glob.glob("data/raw/dailyfaceoff/*.json.gz"))[-1]
    d = json.load(gzip.open(f))
    ab = SL.FULLNAME
    st = {}
    for g in d["goalies"] or []:
        for side in ("home", "away"):
            t = ab.get(g[f"{side}TeamName"])
            if t:
                st[t] = (g[f"{side}GoalieName"], g[f"{side}NewsStrengthName"])
    return st


SIDE_ROI = None


def side_roi(market, book, line, side):
    """Historical ROI of betting EVERY contract of this kind at the book's pregame close (2026)."""
    global SIDE_ROI
    if SIDE_ROI is None:
        try:
            SIDE_ROI = pd.read_csv("reports/blanket_side_roi_2026close.csv")
        except FileNotFoundError:
            SIDE_ROI = pd.DataFrame(columns=["stat", "book", "line", "side", "n", "roi"])
    stat = {"SOG": "shots_onGoal", "G": "points", "PTS": "goals+assists", "A": "assists"}[market]
    x = SIDE_ROI[(SIDE_ROI.stat == stat) & (SIDE_ROI.book == book) & (SIDE_ROI.line == line) & (SIDE_ROI.side == side)]
    return (float(x.roi.iloc[0]), int(x.n.iloc[0])) if len(x) else (None, 0)


def inspect(r, gst, counts):
    """Return list of (severity, tag) cracks."""
    c = []
    roi, n = side_roi(r.market, r.book, r.line, r.side)
    if roi is not None and roi < -0.05:
        c.append(("HAIRLINE", f"public-over tax: every {r.side} of this line at {r.book} returned {roi:+.0%} "
                              f"at close in 2026 (n={n}); needs a real model edge"))
    elif roi is not None and roi > 0:
        c.append(("NOTE", f"tailwind: blanket {r.side}s here returned {roi:+.1%} at close in 2026 (n={n})"))
    opp = r.game.split("@")[0] if r.team == r.game.split("@")[1] else r.game.split("@")[1]
    if r.hist_min < 400:
        c.append(("FAULT" if r.market in ("G", "PTS", "A") else "HAIRLINE",
                  f"thin NHL sample ({r.hist_min:.0f} min) - projection leans on role/prior"))
    if abs(r.model_p - r.mkt_p) > 0.06:
        c.append(("HAIRLINE", f"model and market disagree by {abs(r.model_p - r.mkt_p) * 100:.0f} pts"))
    if r.model_p < r.implied:
        c.append(("HAIRLINE", "borrowed stone: edge is price-shopping only, our model does not beat the price"))
    if r.mkt_p < r.implied:
        c.append(("HAIRLINE", "market consensus does not beat the price; edge is model-only"))
    if gst.get(opp, ("", "Confirmed"))[1] != "Confirmed" and r.market in ("G", "PTS", "A"):
        c.append(("HAIRLINE", f"opposing goalie {gst[opp][0]} not confirmed"))
    global B2B
    if B2B is None:
        try:
            B2B = SL.back_to_back(SL.DATE)
        except Exception:  # noqa: BLE001
            B2B = set()
    if r.team in B2B:
        c.append(("HAIRLINE", "team on back-to-back (TOI/legs risk)"))
    if isinstance(r.team_ly, str) and r.team_ly != r.team and r.gp_ly > 0:
        c.append(("HAIRLINE", f"new team (was {r.team_ly}) - usage history not from this system"))
    if r.implied < 0.12:
        c.append(("HAIRLINE", "thin-air longshot: favourite-longshot bias zone, needs a big cushion"))
    cushion = r.blend_p - r.implied
    if cushion < 0.02:
        c.append(("HAIRLINE", f"thin mortar: only {cushion * 100:.1f} pt cushion over the price"))
    if not np.isnan(r.hr_ly) and r.gp_ly >= 30 and r.hr_ly < r.implied - 0.08:
        c.append(("FAULT", f"history contradicts: hit {r.hr_ly:.0%} last season vs {r.implied:.0%} needed"))
    if r.pp == "-" and r.market in ("G", "PTS", "A"):
        c.append(("HAIRLINE", "no power-play role"))
    return c


def score(r):
    s = r.ev * 100
    s += 3 if (r.model_p >= r.implied + 0.02 and r.mkt_p >= r.implied + 0.01) else 0
    if not np.isnan(r.hr_ly) and r.gp_ly >= 30:
        s += np.clip((r.hr_ly - r.implied) * 40, -6, 6)
    if not np.isnan(r.hr_l10) and r.n_l10 >= 8:
        s += np.clip((r.hr_l10 - r.implied) * 10, -2, 2)
    s -= 2.5 * sum(1 for sev, _ in r.cracks if sev == "HAIRLINE")
    s -= 100 * sum(1 for sev, _ in r.cracks if sev == "FAULT")
    return s


def main():
    q = pd.read_csv(f"{OUT}/pyramid_singles.csv")
    h = history()
    gst = goalie_status()
    ext = pd.DataFrame([hit_rates(h, r.player, r.market, r.line, getattr(r, 'role', None)) for r in q.itertuples()], index=q.index)
    q = pd.concat([q, ext], axis=1)
    # hit rates were computed for the over; flip for unders
    und = q.side == "under"
    for c in ("hr_ly", "hr_l10", "hr_car"):
        q.loc[und, c] = 1 - q.loc[und, c]
    counts = q.player.value_counts().to_dict()
    q["cracks"] = [inspect(r, gst, counts) for r in q.itertuples()]
    q["score"] = [score(r) for r in q.itertuples()]
    q["n_fault"] = q.cracks.map(lambda c: sum(1 for s, _ in c if s == "FAULT"))
    q["n_hair"] = q.cracks.map(lambda c: sum(1 for s, _ in c if s == "HAIRLINE"))
    q = q.sort_values("score", ascending=False)

    # minimum EV rises with price (favourite-longshot bias; research digest 02 §5)
    band_min = np.select([q.odds <= -200, q.odds <= 150, q.odds <= 400, q.odds <= 1000], [0.02, 0.03, 0.05, 0.08], 0.12)
    q.loc[q.ev < band_min, "cracks"] = q.loc[q.ev < band_min, "cracks"].map(
        lambda c: c + [("FAULT", "EV below the minimum for this odds band (longshot bias buffer)")])
    q["n_fault"] = q.cracks.map(lambda c: sum(1 for s, _ in c if s == "FAULT"))
    ok = q[(q.n_fault == 0) & (q.n_hair <= 2)].copy()   # 3+ hairlines = crumbling, stays in quarry
    rubble = q[q.n_fault > 0]
    used = set()
    course = {}

    def take(df, n, name):
        rows = []
        for r in df.itertuples():
            if len(rows) >= n or r.Index in used:
                continue
            # at most one stone per player in the constructed pyramid
            if any(q.loc[i, "player"] == r.player for i in used):
                continue
            used.add(r.Index)
            rows.append(r.Index)
        course[name] = q.loc[rows]

    take(ok[(ok.n_hair == 0) & (ok.score > 0)], 2, "CAPSTONE")
    take(ok[ok.implied >= 0.42], 5, "FOUNDATION")
    take(ok[(ok.n_hair <= 1) & (ok.implied < 0.42)], 4, "UPPER COURSE")
    take(ok[ok.implied < 0.42], 5, "MIDDLE COURSE")

    # stakes: nightly budget split by course, quarter-Kelly weights within course, 25% trim per hairline crack,
    # per-bet cap 2% (1% for longshots), per-game cap 5%
    built = pd.concat([d.assign(course=k) for k, d in course.items() if not d.empty])
    share = {"CAPSTONE": 0.30, "FOUNDATION": 0.30, "UPPER COURSE": 0.25, "MIDDLE COURSE": 0.15}
    built["w"] = built.kelly.clip(lower=1e-4) * (0.75 ** built.n_hair)
    built["stake_b"] = built.course.map(share) * BUDGET * built.w / built.groupby("course").w.transform("sum")
    # caps per research digest 02 (quarter-Kelly regime): 1.5% per bet (0.5% if longer than +500), 4% per game
    built["stake_b"] = np.minimum(built.stake_b, np.where(built.implied < 0.17, 0.005, 0.015))
    g = built.groupby("game").stake_b.transform("sum")
    built["stake_b"] = np.where(g > 0.04, built.stake_b * 0.04 / g, built.stake_b)

    def ctx(r):
        bits = []
        if not np.isnan(r.hr_ly):
            bits.append(f"LY {r.hr_ly:.0%} hit ({r.gp_ly} GP, avg {r.avg_ly:.2f})")
        if r.n_l10:
            bits.append(f"L10 {r.hr_l10:.0%} (avg {r.avg_l10:.2f})")
        if r.gp_car:
            bits.append(f"since '22 {r.hr_car:.0%} ({r.gp_car} GP)")
        bits.append(f"proj TOI {r.toi:.1f}")
        return "; ".join(bits)

    def crack_txt(c):
        if not [x for x in c if x[0] != "NOTE"]:
            return "solid stone" + ("<br>" + "<br>".join("🟢 " + t for s, t in c if s == "NOTE") if c else "")
        return "<br>".join({"HAIRLINE": "🟡 hairline: ", "FAULT": "🔴 FAULT: ", "NOTE": "🟢 "}[s] + t for s, t in c)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L = [f"# The Pyramid — {OUT.split('/')[-1]}", "",
         f"_Built {ts} from the quarry (RAW_MATERIALS.md, {len(q)} stones inspected; {len(rubble)} rejected as rubble). "
         "Stake = % of bankroll. p = blend of model and de-vigged market. Hit rates are from NHL box scores at "
         "this exact line._", "",
         "**Legend:** solid stone = no flaws found | 🟡 hairline crack = minor flaw, stake trimmed 25% per crack | "
         "🔴 fault line = structural flaw, not built on", ""]
    icons = {"CAPSTONE": "🔺", "UPPER COURSE": "▲", "MIDDLE COURSE": "◆", "FOUNDATION": "▬"}
    blurbs = {"CAPSTONE": "the best spots on the slate",
              "UPPER COURSE": "strong plus-money stones, at most one hairline crack",
              "MIDDLE COURSE": "solid plus-money stones, cracks disclosed",
              "FOUNDATION": "high-probability cash-game stones the rest stands on"}
    for k in ("CAPSTONE", "UPPER COURSE", "MIDDLE COURSE", "FOUNDATION"):
        d = built[built.course == k]
        L += [f"## {icons[k]} {k} — {blurbs[k]}", ""]
        if d.empty:
            L += ["_Nothing met the bar for this course tonight._", ""]
            continue
        L += ["| Stone | Price (kill) | p / implied | EV | History & usage | Inspection | Stake |",
              "|---|---|---|---|---|---|---|"]
        for r in d.itertuples():
            L.append(f"| **{r.pick}**<br>{r.game} · {r.role}/{r.pp} | {r.book[:2].upper()} {r.odds:+d} ({int(r.ceiling):+d}) | "
                     f"{r.blend_p:.1%} / {r.implied:.1%}<br>model {r.model_p:.0%} · mkt {r.mkt_p:.0%} | {r.ev:+.1%} | "
                     f"{ctx(r)} | {crack_txt(r.cracks)} | {r.stake_b:.2%} |")
        L.append("")
    L += ["## 🧱 Rubble — rejected stones", "",
          "| Stone | Price | EV | Why it was rejected |", "|---|---|---|---|"]
    for r in rubble.itertuples():
        L.append(f"| {r.pick} ({r.game}) | {r.book[:2].upper()} {r.odds:+d} | {r.ev:+.1%} | {crack_txt(r.cracks)} |")
    rest = q[(q.n_fault == 0) & ~q.index.isin(built.index)]
    L += ["", "## ⛏️ Still in the quarry (good material, not placed)", "",
          "Not used because of the one-stone-per-player rule or course limits. Free to build your own tickets from these.", "",
          "| Stone | Price | EV | Flaws |", "|---|---|---|---|"]
    for r in rest.itertuples():
        L.append(f"| {r.pick} ({r.game}) | {r.book[:2].upper()} {r.odds:+d} | {r.ev:+.1%} | "
                 f"{'solid' if not r.cracks else '; '.join(t for _, t in r.cracks)} |")
    # tickets built directly from placed stones: cross-game, 2-3 legs
    import itertools
    rows = []
    recs = built.to_dict("records")
    for k in (2, 3):
        for combo in itertools.combinations(recs, k):
            if len({c["game"] for c in combo}) < k:
                continue
            p = float(np.prod([c["blend_p"] for c in combo]))
            d = float(np.prod([c["dec"] for c in combo]))
            rows.append(dict(legs=" + ".join(f"{c['pick']} ({c['book'][:2].upper()} {c['odds']:+d})" for c in combo),
                             x=d, p=p, ev=p * d - 1, cracks=sum(c["n_hair"] for c in combo)))
    tk = pd.DataFrame(rows)
    placed_tk = []
    L += ["", "## 🎟️ Tickets mortared from placed stones (cross-game, independent legs)", ""]
    if tk.empty:
        L += ["_Not enough placed stones across different games._"]
    else:
        L += ["| Size | Ticket | Pays | Hit prob | EV | Cracks | Stake |", "|---|---|---|---|---|---|---|"]
        for lo, hi, lab in ((1, 6, "small"), (6, 25, "medium"), (25, 1e9, "moonshot")):
            b = tk[(tk.x >= lo) & (tk.x < hi)].sort_values(["cracks", "ev"], ascending=[True, False]).head(3)
            for r in b.itertuples():
                st = {"small": 0.002, "medium": 0.001, "moonshot": 0.0005}[lab]  # lottery tier <= ~0.5%/night
                L.append(f"| {lab} | {r.legs} | {r.x:.1f}x | {r.p:.1%} | {r.ev:+.1%} | {r.cracks} | {st:.2%} |")
                placed_tk.append(dict(size=lab, legs=r.legs, payout_x=r.x, p=r.p, ev=r.ev, cracks=r.cracks, stake=st))
    L += ["", f"**Total built exposure:** {built.stake_b.sum():.2%} of bankroll in singles. "
          f"By game: {built.groupby('game').stake_b.sum().round(4).map(lambda x: f'{x:.2%}').to_dict()}", ""]
    open(f"{OUT}/PYRAMID.md", "w").write("\n".join(L))
    q.drop(columns=["cracks"]).assign(cracks=q.cracks.map(str)).to_csv(f"{OUT}/quarry_inspected.csv", index=False)
    # machine-readable placed stones + tickets (dashboard / grading)
    built.drop(columns=["cracks"]).assign(cracks=built.cracks.map(str), stake=built.stake_b).to_csv(
        f"{OUT}/pyramid_placed.csv", index=False)
    pd.DataFrame(placed_tk).to_csv(f"{OUT}/pyramid_tickets.csv", index=False)
    print("\n".join(L))


if __name__ == "__main__":
    main()
    sys.exit(0)
