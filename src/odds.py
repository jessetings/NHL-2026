"""SportsGameOdds (SGO) fetch + flatten into a tidy prop/game odds table."""
import glob
import json
import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests

RAW = "data/raw/odds"
BOOKS = ["draftkings", "fanduel", "pinnacle"]
PLAYER_STATS = {
    "shots_onGoal": "SOG",
    "points": "G",  # SGO: hockey "points" stat = goals
    "goals+assists": "PTS",
    "assists": "A",
    "goalie_saves": "SAVES",
    "powerPlay_goals+assists": "PPP",
}


def load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)


def fetch_events(event_ids=None, league="NHL", alt=True):
    load_env()
    params = {"leagueID": league, "includeAltLines": str(alt).lower()}
    if event_ids:
        params["eventIDs"] = ",".join(event_ids)
    else:
        params["oddsAvailable"] = "true"
    r = requests.get("https://api.sportsgameodds.com/v2/events", params=params,
                     headers={"x-api-key": os.environ["SGO_API_KEY"]}, timeout=60)
    r.raise_for_status()
    os.makedirs(RAW, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"{RAW}/sgo_slate_alt_{ts}.json"
    json.dump(r.json(), open(path, "w"))
    return path


def latest_snapshot():
    return sorted(glob.glob(f"{RAW}/sgo_slate_alt_*.json"))[-1]


def american_to_prob(o):
    o = float(o)
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def prob_to_american(p):
    if p <= 0 or p >= 1:
        return None
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def _team(tid):
    return tid.replace("_NHL", "").replace("_", " ").title()


def flatten(path):
    """One row per (event, market, player/team, side, book, line)."""
    d = json.load(open(path))
    rows = []
    for e in d["data"]:
        home, away = e["teams"]["home"]["teamID"], e["teams"]["away"]["teamID"]
        players = e.get("players", {})
        for oid, o in e["odds"].items():
            stat, ent, period, bt, side = o["statID"], o["statEntityID"], o["periodID"], o["betTypeID"], o["sideID"]
            if period != "game":
                continue
            base = dict(eventID=e["eventID"], home=home, away=away, startsAt=e["status"]["startsAt"],
                        oddID=oid, stat=stat, entity=ent, bt=bt, side=side,
                        fair_line=o.get("fairOverUnder") or o.get("fairSpread"),
                        fair_odds=o.get("fairOdds"))
            if ent not in ("home", "away", "all"):
                p = players.get(ent, {})
                base.update(player=p.get("name", ent), team=p.get("teamID"))
            for b, bo in o.get("byBookmaker", {}).items():
                if b not in BOOKS:
                    continue
                lines = [bo] + (bo.get("altLines") or [])
                for i, ln in enumerate(lines):
                    if not ln.get("available", True) or ln.get("odds") is None:
                        continue
                    rows.append(dict(base, book=b, odds=int(float(ln["odds"])), alt=i > 0,
                                     line=ln.get("overUnder") or ln.get("spread"),
                                     updated=ln.get("lastUpdatedAt")))
    df = pd.DataFrame(rows)
    df["line"] = pd.to_numeric(df["line"], errors="coerce")
    df["fair_line"] = pd.to_numeric(df["fair_line"], errors="coerce")
    df["snapshot"] = os.path.basename(path)
    return df


if __name__ == "__main__":
    import sys
    ids = sys.argv[1:] or None
    p = fetch_events(ids)
    print("saved", p, len(flatten(p)), "rows")
    time.sleep(0)
