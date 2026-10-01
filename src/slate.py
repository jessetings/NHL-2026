"""Slate configuration derived from a date (America/New_York). Single source of truth for all card scripts.

  SLATE_DATE env var or --date; default = today in ET.
  events(): SGO eventIDs for NHL games starting on that ET date
  back_to_back(): teams that also played the previous ET day (NHL schedule)
  game_markets(df): de-vigged total mean and P(home win) per game (Pinnacle preferred, else DK/FD)
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import requests
from scipy import optimize, stats

ET = ZoneInfo("America/New_York")
DATE = os.environ.get("SLATE_DATE") or datetime.now(ET).strftime("%Y-%m-%d")
OUT = f"cards/{DATE}"

ABBR = {"ANAHEIM_DUCKS": "ANA", "ARIZONA_COYOTES": "ARI", "BOSTON_BRUINS": "BOS", "BUFFALO_SABRES": "BUF",
        "CALGARY_FLAMES": "CGY", "CAROLINA_HURRICANES": "CAR", "CHICAGO_BLACKHAWKS": "CHI",
        "COLORADO_AVALANCHE": "COL", "COLUMBUS_BLUE_JACKETS": "CBJ", "DALLAS_STARS": "DAL",
        "DETROIT_RED_WINGS": "DET", "EDMONTON_OILERS": "EDM", "FLORIDA_PANTHERS": "FLA", "LOS_ANGELES_KINGS": "LAK",
        "MINNESOTA_WILD": "MIN", "MONTREAL_CANADIENS": "MTL", "NASHVILLE_PREDATORS": "NSH", "NEW_JERSEY_DEVILS": "NJD",
        "NEW_YORK_ISLANDERS": "NYI", "NEW_YORK_RANGERS": "NYR", "OTTAWA_SENATORS": "OTT", "PHILADELPHIA_FLYERS": "PHI",
        "PITTSBURGH_PENGUINS": "PIT", "SAN_JOSE_SHARKS": "SJS", "SEATTLE_KRAKEN": "SEA", "ST_LOUIS_BLUES": "STL",
        "TAMPA_BAY_LIGHTNING": "TBL", "TORONTO_MAPLE_LEAFS": "TOR", "UTAH_HOCKEY_CLUB": "UTA", "UTAH_MAMMOTH": "UTA",
        "VANCOUVER_CANUCKS": "VAN", "VEGAS_GOLDEN_KNIGHTS": "VGK", "WASHINGTON_CAPITALS": "WSH", "WINNIPEG_JETS": "WPG"}
SGO_TEAM = {f"{k}_NHL": v for k, v in ABBR.items()}
FULLNAME = {k.replace("_", " ").title().replace("St Louis", "St. Louis"): v for k, v in ABBR.items()}
FULLNAME.update({"Utah Mammoth": "UTA", "Utah Hockey Club": "UTA", "Montréal Canadiens": "MTL"})
SLUG = {k.lower().replace("_", "-"): v for k, v in ABBR.items()}


def window_utc(date=DATE):
    d0 = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=ET, hour=6)
    return d0.astimezone(ZoneInfo("UTC")), (d0 + timedelta(days=1)).astimezone(ZoneInfo("UTC"))


def events(date=DATE, key=None):
    """SGO eventIDs + teams for NHL games starting on the ET date."""
    key = key or os.environ["SGO_API_KEY"]
    a, b = window_utc(date)
    r = requests.get("https://api.sportsgameodds.com/v2/events", headers={"x-api-key": key}, timeout=60,
                     params={"leagueID": "NHL", "startsAfter": a.isoformat(), "startsBefore": b.isoformat(),
                             "limit": 50})
    r.raise_for_status()
    out = []
    for e in r.json().get("data", []):
        if e.get("type") not in (None, "match") and "preseason" in str(e.get("type")).lower():
            continue
        out.append(dict(eventID=e["eventID"], home=SGO_TEAM.get(e["teams"]["home"]["teamID"]),
                        away=SGO_TEAM.get(e["teams"]["away"]["teamID"]), startsAt=e["status"]["startsAt"]))
    return out


def back_to_back(date=DATE):
    """Teams playing on `date` that also played the previous day."""
    prev = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    def teams(d):
        j = requests.get(f"https://api-web.nhle.com/v1/schedule/{d}", timeout=30).json()
        day = [w for w in j.get("gameWeek", []) if w["date"] == d]
        return {t for w in day for g in w["games"] if g.get("gameType") in (2, 3)
                for t in (g["awayTeam"]["abbrev"], g["homeTeam"]["abbrev"])}
    return teams(date) & teams(prev)


def _devig2(o, u):
    qo = 100 / (o + 100) if o > 0 else -o / (-o + 100)
    qu = 100 / (u + 100) if u > 0 else -u / (-u + 100)
    return qo / (qo + qu)


def game_markets(df):
    """{game: (total_mean, p_home)} from a flattened odds frame (src/odds.flatten)."""
    out = {}
    for ev_id, g in df.groupby("eventID"):
        home, away = SGO_TEAM.get(g.home.iloc[0]), SGO_TEAM.get(g.away.iloc[0])
        gl = g[(g.stat == "points") & ~g.alt]
        ml = gl[gl.bt == "ml"]
        p_home = None
        for book in ("pinnacle", "draftkings", "fanduel"):
            h = ml[(ml.book == book) & (ml.side == "home")].odds
            a = ml[(ml.book == book) & (ml.side == "away")].odds
            if len(h) and len(a):
                p_home = _devig2(h.iloc[0], a.iloc[0])
                break
        tot = gl[(gl.bt == "ou") & (gl.entity == "all")]
        means = []
        for (book, line), t in tot.groupby(["book", "line"]):
            o, u = t[t.side == "over"].odds, t[t.side == "under"].odds
            if len(o) and len(u) and not float(line).is_integer():
                p = _devig2(o.iloc[0], u.iloc[0])
                means.append((optimize.brentq(lambda m: stats.poisson.sf(np.floor(line), m) - p, 1, 15),
                              2 if book == "pinnacle" else 1))
        total = float(np.average([m for m, _ in means], weights=[w for _, w in means])) if means else 6.1
        out[f"{away}@{home}"] = (total, p_home if p_home is not None else 0.53)
    return out
