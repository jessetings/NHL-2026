"""SportsGameOdds historical NHL events (odds incl. alt lines + results), weekly windows, resumable."""
import os
import sys
from datetime import date, datetime, timedelta, timezone

from common import get, load_env, save_json_gz

RAW = "data/raw/sgo_history"
START = date(2024, 9, 1)
URL = "https://api.sportsgameodds.com/v2/events"


def window(d0, d1):
    path = f"{RAW}/{d0.isoformat()}.json.gz"
    if os.path.exists(path):
        return "skip", 0
    events, cursor = [], None
    while True:
        params = {"leagueID": "NHL", "startsAfter": f"{d0}T00:00:00Z", "startsBefore": f"{d1}T00:00:00Z",
                  "includeAltLines": "true", "limit": 50}
        if cursor:
            params["cursor"] = cursor
        r = get(URL, params=params, headers={"x-api-key": os.environ["SGO_API_KEY"]}, timeout=180)
        if r is None:
            return "fail", len(events)
        j = r.json()
        events += j.get("data", [])
        cursor = j.get("nextCursor")
        if not cursor or not j.get("data"):
            break
    save_json_gz(path, {"window": [str(d0), str(d1)], "fetched": datetime.now(timezone.utc).isoformat(),
                        "data": events})
    return "ok", len(events)


if __name__ == "__main__":
    load_env()
    today = datetime.now(timezone.utc).date()
    d = START
    while d < today:
        d1 = min(d + timedelta(days=7), today)
        st, n = window(d, d1)
        print(d, st, n, flush=True)
        d = d1
    sys.exit(0)
