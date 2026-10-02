"""Dashboard data layer: one JSON contract for everything a dashboard needs.

Writes dashboard/data/:
  manifest.json            generated_at, slates, files, schema version
  slates/<date>.json       games (start, status, score), picks from every source (graded once final),
                           tickets, per-source summary (n, staked, P&L, ROI, avg CLV)
  performance.json         daily + cumulative paper P&L / CLV per source, and the real-bets bankroll curve
  calibration.json         reliability bins (predicted p vs hit rate) over all graded picks
  research.json            headline backtests (open-line edge, model v2 eval, sim tails, team model)
Sources of picks (stake = % of bankroll as published on the card):
  pyramid  cards/<d>/pyramid_placed.csv     early   cards/<d>/early_bets.csv (or rule applied to early_all.csv)
  tickets  cards/<d>/pyramid_tickets.csv    ledger  ledger/bets.csv (bets actually placed; filled in by hand)
Results: NHL boxscores (cached to cards/<d>/results.parquet once all games are final); CLV vs the last pregame
snapshot price of the same book/line (data/raw/snapshots/compact).
Usage: python src/dashboard/export.py            (all slates in cards/)
"""
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import grade as GR  # noqa: E402

OUT = os.path.join(ROOT, "dashboard", "data")
SCHEMA = 1
STAT = {"SOG": "sog", "G": "goals", "A": "assists", "PTS": "points"}
SGO_STAT = {"SOG": "shots_onGoal", "G": "points", "A": "assists", "PTS": "goals+assists"}
PICK_RE = [(re.compile(r"^(.*) ([UO])(\d+(?:\.\d)?) SOG$"), "SOG"),
           (re.compile(r"^(.*) (\d+)\+ (pts|ast|goals|SOG)$"), None)]
WORD = {"pts": "PTS", "ast": "A", "goals": "G", "SOG": "SOG"}


def dec(o):
    return 1 + (o / 100 if o > 0 else 100 / -o)


def implied(o):
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def key(s):
    return GR.norm(s)


# ------------------------------------------------------------------ results
def results(date):
    path = os.path.join(ROOT, "cards", date, "results.parquet")
    if os.path.exists(path):
        r = pd.read_parquet(path)
        return r, json.load(open(path.replace(".parquet", "_meta.json")))
    try:
        r, first_goal, status = GR.results(date)
    except Exception as e:  # noqa: BLE001
        print(date, "results unavailable:", e)
        return pd.DataFrame(), {"status": {}, "first_goal": {}}
    meta = {"status": {str(k): v for k, v in status.items()}, "first_goal": first_goal}
    if status and all(v in ("OFF", "FINAL") for v in status.values()) and not r.empty:
        r.to_parquet(path, index=False)
        json.dump(meta, open(path.replace(".parquet", "_meta.json"), "w"))
    return r, meta


def schedule(date):
    import requests
    try:
        j = requests.get(f"https://api-web.nhle.com/v1/score/{date}", timeout=30).json()
    except Exception:  # noqa: BLE001
        return []
    return [dict(game=f"{g['awayTeam']['abbrev']}@{g['homeTeam']['abbrev']}", start=g.get("startTimeUTC"),
                 state=g.get("gameState"), away_score=g["awayTeam"].get("score"), home_score=g["homeTeam"].get("score"))
            for g in j.get("games", []) if g.get("gameType") in (2, 3)]


def stat_actual(res, player, market, game=None, role=None):
    """Actual stat for one player; disambiguates same-name players by game/team and F/D. None if unknown."""
    if res.empty:
        return None
    x = res[res.key == key(player)]
    if game is not None and len(x) > 1:
        x = x[x.game == game] if (x.game == game).any() else x
    if len(x) > 1 and role:
        x = x[x.pos == ("D" if str(role).startswith("d") else "F")]
    if len(x) != 1:
        return None
    return float(x.iloc[0][STAT[market]])


def settle(actual, side, line):
    if actual is None:
        return "void"
    if actual == line:
        return "push"
    return "won" if (actual > line) == (side == "over") else "lost"


# ------------------------------------------------------------------ closing prices (CLV)
def closing(date):
    fs = sorted(glob.glob(os.path.join(ROOT, "data/raw/snapshots/compact", date, "*.parquet")))
    if not fs:
        return pd.DataFrame()
    s = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    s = s[pd.to_datetime(s.snap_ts) < pd.to_datetime(s.startsAt)]
    s = s[s.oddID.str.contains("_NHL-game-ou-")]
    s["line"] = pd.to_numeric(s.line, errors="coerce")
    s = s.sort_values("snap_ts").drop_duplicates(["oddID", "book", "line"], keep="last")
    parts = s.oddID.str.extract(r"^(?P<stat>[^-]+)-(?P<ent>.+?_NHL)-game-ou-(?P<side>over|under)$")
    s = pd.concat([s, parts], axis=1).dropna(subset=["ent"])
    s["pkey"] = s.ent.str.replace(r"_\d+_NHL$", "", regex=True).str.replace("_", "").str.lower()
    n_ent = s.groupby("pkey").ent.nunique()
    s = s[s.pkey.map(n_ent) == 1]                     # drop same-name collisions (ambiguous)
    return s.set_index(["pkey", "stat", "side", "line", "book"]).odds


def clv_pts(close, player, market, side, line, book, odds):
    try:
        c = close.get((key(player), SGO_STAT[market], side, float(line), book))
    except Exception:  # noqa: BLE001
        c = None
    if c is None or pd.isna(c):
        return None, None
    return float(c), float(implied(float(c)) - implied(float(odds)))   # >0: the price shortened after we bet


# ------------------------------------------------------------------ picks per source
def parse_pick(text):
    text = text.strip()
    m = PICK_RE[0][0].match(text)
    if m:
        return dict(player=m.group(1), market="SOG", side="under" if m.group(2) == "U" else "over", line=float(m.group(3)))
    m = PICK_RE[1][0].match(text)
    if m:
        return dict(player=m.group(1), market=WORD[m.group(3)], side="over", line=float(m.group(2)) - 0.5)
    return None


def load_picks(date):
    d = os.path.join(ROOT, "cards", date)
    picks = []
    f = os.path.join(d, "pyramid_placed.csv")
    if os.path.exists(f):
        for r in pd.read_csv(f).to_dict("records"):
            picks.append(dict(source="pyramid", tier=r.get("course"), game=r["game"], player=r["player"], team=r.get("team"),
                              role=r.get("role"), market=r["market"], side=r["side"], line=float(r["line"]), book=r["book"],
                              odds=int(r["odds"]), p=r.get("blend_p"), p_model=r.get("model_p"), p_market=r.get("mkt_p"),
                              stake=float(r["stake"])))
    f = os.path.join(d, "early_bets.csv")
    if os.path.exists(f):
        eb = pd.read_csv(f)
    elif os.path.exists(os.path.join(d, "early_all.csv")):        # reconstruct with the published rule
        ea = pd.read_csv(os.path.join(d, "early_all.csv"))
        if "p_rel" in ea:
            ea = ea.sort_values("edge", ascending=False).drop_duplicates(["player", "market", "side", "line"])
            ea = ea[(ea.market == "SOG") & (ea.side == "under") & (ea.edge >= 0.04) & (ea.get("gp", 99) >= 30)]
            eb = ea.groupby("game").head(3).assign(stake=0.0075)
        else:
            eb = pd.DataFrame()
    else:
        eb = pd.DataFrame()
    for r in eb.to_dict("records"):
        picks.append(dict(source="early", tier="SOG-under rule", game=r["game"], player=r["player"], team=None,
                          role=r.get("unit"), market=r["market"], side=r["side"], line=float(r["line"]), book=r["book"],
                          odds=int(r["odds"]), p=r.get("p_rel", r.get("p_v2")), p_model=r.get("p_rel"), p_market=None,
                          stake=float(r["stake"])))
    tickets = []
    f = os.path.join(d, "pyramid_tickets.csv")
    if os.path.exists(f) and os.path.getsize(f) > 5:
        for r in pd.read_csv(f).to_dict("records"):
            legs = []
            for leg in str(r["legs"]).split(" + "):
                m = re.match(r"^(.*) \((\w\w) ([+-]\d+)\)$", leg.strip())
                if not m:
                    continue
                pp = parse_pick(m.group(1)) or {}
                legs.append(dict(text=m.group(1), book={"DR": "draftkings", "FA": "fanduel"}.get(m.group(2), m.group(2)),
                                 odds=int(m.group(3)), **pp))
            tickets.append(dict(source="ticket", tier=r["size"], legs=legs, payout_x=float(r["payout_x"]), p=float(r["p"]),
                                ev=float(r["ev"]), stake=float(r["stake"])))
    return picks, tickets


def ledger():
    f = os.path.join(ROOT, "ledger", "bets.csv")
    return pd.read_csv(f) if os.path.exists(f) else pd.DataFrame()


# ------------------------------------------------------------------ build
def build_slate(date):
    res, meta = results(date)
    if not res.empty and "pos" not in res:
        res["pos"] = None
    games = schedule(date)
    final = bool(games) and all(g["state"] in ("OFF", "FINAL") for g in games)
    close = closing(date)
    picks, tickets = load_picks(date)
    for p in picks:
        a = stat_actual(res, p["player"], p["market"], p["game"], p.get("role")) if final else None
        p["actual"] = a
        p["result"] = settle(a, p["side"], p["line"]) if final else "open"
        p["pnl"] = {"won": p["stake"] * (dec(p["odds"]) - 1), "lost": -p["stake"]}.get(p["result"], 0.0)
        p["close_odds"], p["clv"] = clv_pts(close, p["player"], p["market"], p["side"], p["line"], p["book"], p["odds"]) \
            if len(close) else (None, None)
        p["implied"] = implied(p["odds"])
    for t in tickets:
        rs = []
        for leg in t["legs"]:
            if "player" not in leg or not final:
                rs.append("open" if not final else "void")
                continue
            leg["actual"] = stat_actual(res, leg["player"], leg["market"])
            leg["result"] = settle(leg["actual"], leg["side"], leg["line"])
            rs.append(leg["result"])
        t["result"] = ("open" if "open" in rs else "void" if "void" in rs else "lost" if "lost" in rs
                       else "won" if all(x == "won" for x in rs) else "push")
        t["pnl"] = {"won": t["stake"] * (t["payout_x"] - 1), "lost": -t["stake"]}.get(t["result"], 0.0)
    allp = picks + tickets
    summary = {}
    for src in sorted({p["source"] for p in allp}):
        x = [p for p in allp if p["source"] == src]
        settled = [p for p in x if p["result"] in ("won", "lost", "push")]
        st = sum(p["stake"] for p in settled)
        cl = [p["clv"] for p in x if p.get("clv") is not None]
        summary[src] = dict(n=len(x), settled=len(settled), won=sum(p["result"] == "won" for p in x),
                            staked=st, pnl=sum(p["pnl"] for p in x), roi=(sum(p["pnl"] for p in x) / st) if st else None,
                            avg_clv=float(np.mean(cl)) if cl else None, n_clv=len(cl))
    return dict(date=date, final=final, games=games, first_goal=meta.get("first_goal", {}), picks=picks, tickets=tickets,
                summary=summary)


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 6)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def research():
    r = {}
    for name, f in (("open_edge", "reports/open_edge.csv"), ("props_v2_eval", "reports/props_v2_eval.csv"),
                    ("sim_tails", "reports/sim_backtest_tails.csv")):
        p = os.path.join(ROOT, f)
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p)
        if name == "sim_tails":
            d = d.groupby("tail").agg(n=("y", "size"), actual=("y", "mean"), sim=("sim", "mean"), poisson=("pois", "mean")).reset_index()
        r[name] = d.to_dict("records")
    r["headline"] = {
        "live_rule": "SOG unders, level-corrected v2 edge >= 4 pts, at OPENING DK/FD prices",
        "live_rule_backtest": {"n": 925, "roi": 0.040, "roi_2se": 0.066, "clv_pts": 0.51, "blanket_unders_roi": -0.021},
        "close_efficiency": "props and game lines at close: no model edge (H3 / team model)",
    }
    return r


def main():
    os.makedirs(os.path.join(OUT, "slates"), exist_ok=True)
    dates = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "cards", "20*")))
    slates = []
    for d in dates:
        s = build_slate(d)
        json.dump(clean(s), open(os.path.join(OUT, "slates", f"{d}.json"), "w"), indent=1)
        slates.append(s)
        print(d, "final" if s["final"] else "open", {k: (v["n"], round(v["pnl"], 4)) for k, v in s["summary"].items()})
    # performance: daily + cumulative per source
    rows = []
    for s in slates:
        for src, v in s["summary"].items():
            rows.append(dict(date=s["date"], source=src, **v))
    perf = pd.DataFrame(rows)
    if not perf.empty:
        perf = perf.sort_values("date")
        perf["cum_pnl"] = perf.groupby("source").pnl.cumsum()
        perf["cum_staked"] = perf.groupby("source").staked.cumsum()
    led = ledger()
    curve = []
    if not led.empty and "pnl_units" in led:
        led = led.sort_values("date")
        led["bankroll"] = led.get("start_bankroll", pd.Series([100] * len(led))).iloc[0] + led.pnl_units.fillna(0).cumsum()
        curve = led[["date", "bankroll"]].to_dict("records")
    json.dump(clean(dict(by_source_daily=perf.to_dict("records") if not perf.empty else [], ledger=led.to_dict("records"),
                         bankroll_curve=curve)), open(os.path.join(OUT, "performance.json"), "w"), indent=1)
    # calibration over settled single picks
    pk = pd.DataFrame([p for s in slates for p in s["picks"] if p["result"] in ("won", "lost") and p.get("p") is not None])
    cal = []
    if not pk.empty:
        pk["y"] = (pk.result == "won").astype(float)
        pk["bin"] = pd.cut(pk.p.astype(float), [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1])
        cal = [dict(bin=str(b), n=len(x), p_mean=x.p.mean(), hit=x.y.mean(), implied=x.implied.mean())
               for b, x in pk.groupby("bin", observed=True)]
    json.dump(clean(dict(bins=cal, n=len(pk))), open(os.path.join(OUT, "calibration.json"), "w"), indent=1)
    json.dump(clean(research()), open(os.path.join(OUT, "research.json"), "w"), indent=1)
    json.dump(dict(schema=SCHEMA, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), slates=dates,
                   files=["performance.json", "calibration.json", "research.json"] + [f"slates/{d}.json" for d in dates]),
              open(os.path.join(OUT, "manifest.json"), "w"), indent=1)
    print("dashboard data ->", OUT)


if __name__ == "__main__":
    main()
