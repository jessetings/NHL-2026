"""Live SGO odds snapshotter: captures upcoming NHL events (all books, alt lines) on a fixed cadence.

Alt-line prices and intraday movement have NO history at SGO, so this archive is the only source for
H1 (alt-ladder pricing) and H2 (DK/FD lag vs Pinnacle). Run it on every game day.
Usage: python src/ingest/snapshot.py [--interval 300] [--once]
Writes data/raw/snapshots/<YYYY-MM-DD>/<HHMMSSZ>.json.gz and a compact parquet of DK/FD/Pinnacle rows.
"""
import argparse
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from common import get, load_env, save_json_gz

RAW = "data/raw/snapshots"
URL = "https://api.sportsgameodds.com/v2/events"
BOOKS = ("draftkings", "fanduel", "pinnacle")


def pull():
    now = datetime.now(timezone.utc)
    params = {"leagueID": "NHL", "oddsAvailable": "true", "includeAltLines": "true", "limit": 50,
              "startsAfter": now.isoformat(), "startsBefore": (now + timedelta(hours=36)).isoformat()}
    events, cursor = [], None
    while True:
        if cursor:
            params["cursor"] = cursor
        r = get(URL, params=params, headers={"x-api-key": os.environ["SGO_API_KEY"]}, timeout=120)
        if r is None:
            break
        j = r.json()
        events += j.get("data", [])
        cursor = j.get("nextCursor")
        if not cursor or not j.get("data"):
            break
    ts = now.strftime("%H%M%SZ")
    day = now.strftime("%Y-%m-%d")
    save_json_gz(f"{RAW}/{day}/{ts}.json.gz", {"ts": now.isoformat(), "data": events})
    rows = []
    for e in events:
        for oid, o in e.get("odds", {}).items():
            if o.get("periodID") != "game":
                continue
            for b, bo in (o.get("byBookmaker") or {}).items():
                if b not in BOOKS:
                    continue
                for i, ln in enumerate([bo] + (bo.get("altLines") or [])):
                    if ln.get("odds") is None:
                        continue
                    rows.append((now.isoformat(), e["eventID"], e["status"]["startsAt"], oid, b, i > 0,
                                 ln.get("odds"), ln.get("overUnder") or ln.get("spread"), ln.get("available"),
                                 ln.get("lastUpdatedAt")))
    df = pd.DataFrame(rows, columns=["snap_ts", "eventID", "startsAt", "oddID", "book", "alt", "odds", "line",
                                     "available", "updated"])
    os.makedirs(f"{RAW}/compact/{day}", exist_ok=True)
    df.to_parquet(f"{RAW}/compact/{day}/{ts}.parquet", index=False)
    starts = sorted({e["status"]["startsAt"] for e in events})
    print(f"{now:%H:%M:%S}Z events={len(events)} rows={len(df)} next_start={starts[0] if starts else None}",
          flush=True)
    return events


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    load_env()
    while True:
        ev = pull()
        if a.once:
            break
        # stop once nothing starts within 36h (end of slate window); otherwise keep cadence
        if not ev:
            break
        time.sleep(a.interval)
