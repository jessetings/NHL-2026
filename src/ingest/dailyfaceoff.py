"""DailyFaceoff snapshots (starting goalies + line combos/PP units/injuries), timestamped.

DailyFaceoff has no history, so run this on every build (morning, T-30) to accumulate an archive.
Usage: python src/ingest/dailyfaceoff.py [team-slug ...]   (default: all 32 teams)
"""
import json
import re
import sys
from datetime import datetime, timezone

from common import get, save_json_gz

RAW = "data/raw/dailyfaceoff"
SLUGS = ["anaheim-ducks", "boston-bruins", "buffalo-sabres", "calgary-flames", "carolina-hurricanes",
         "chicago-blackhawks", "colorado-avalanche", "columbus-blue-jackets", "dallas-stars", "detroit-red-wings",
         "edmonton-oilers", "florida-panthers", "los-angeles-kings", "minnesota-wild", "montreal-canadiens",
         "nashville-predators", "new-jersey-devils", "new-york-islanders", "new-york-rangers", "ottawa-senators",
         "philadelphia-flyers", "pittsburgh-penguins", "san-jose-sharks", "seattle-kraken", "st-louis-blues",
         "tampa-bay-lightning", "toronto-maple-leafs", "utah-mammoth", "vancouver-canucks", "vegas-golden-knights",
         "washington-capitals", "winnipeg-jets"]


def next_data(url):
    r = get(url)
    if r is None:
        return None
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    return json.loads(m.group(1))["props"]["pageProps"] if m else None


def snapshot(slugs=SLUGS):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = {"ts": ts, "goalies": None, "lines": {}}
    pp = next_data("https://www.dailyfaceoff.com/starting-goalies")
    out["goalies"] = pp.get("data") if pp else None
    for s in slugs:
        pp = next_data(f"https://www.dailyfaceoff.com/teams/{s}/line-combinations")
        out["lines"][s] = pp.get("combinations") if pp else None
    save_json_gz(f"{RAW}/{ts}.json.gz", out)
    ok = sum(v is not None for v in out["lines"].values())
    print(f"dailyfaceoff snapshot {ts}: goalies={len(out['goalies'] or [])} lines={ok}/{len(slugs)}")
    return out


if __name__ == "__main__":
    snapshot(sys.argv[1:] or SLUGS)
