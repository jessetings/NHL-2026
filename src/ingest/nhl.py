"""NHL API: schedules, boxscores, play-by-play, shifts, right-rail (officials), player careers.

Resumable: skips files already on disk. Run from repo root with PYTHONPATH=src/ingest.
"""
import glob
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from common import get, load_json_gz, save_json_gz

RAW = "data/raw/nhl"
WEB = "https://api-web.nhle.com/v1"
BOX_SEASONS = [20222023, 20232024, 20242025, 20252026, 20262027]
DETAIL_SEASONS = {20232024, 20242025, 20252026, 20262027}   # pbp, shifts, officials
TEAMS = ["ANA", "ARI", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM", "FLA", "LAK",
         "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR",
         "UTA", "VAN", "VGK", "WPG", "WSH"]
DONE = {"OFF", "FINAL"}


def schedules():
    games = {}
    for season in BOX_SEASONS:
        path = f"{RAW}/schedule/{season}.json.gz"
        if os.path.exists(path) and season != BOX_SEASONS[-1]:
            data = load_json_gz(path)
        else:
            data = {}
            for t in TEAMS:
                r = get(f"{WEB}/club-schedule-season/{t}/{season}")
                if r is not None:
                    for g in r.json().get("games", []):
                        data[str(g["id"])] = g
            save_json_gz(path, data)
        for gid, g in data.items():
            if g.get("gameType") in (2, 3) and g.get("gameState") in DONE:
                games[int(gid)] = season
        print("schedule", season, len(data), flush=True)
    return games


def fetch(kind, gid):
    season = int(str(gid)[:4])
    path = f"{RAW}/{kind}/{season}/{gid}.json.gz"
    if os.path.exists(path):
        return "skip"
    if kind == "shifts":
        r = get("https://api.nhle.com/stats/rest/en/shiftcharts", params={"cayenneExp": f"gameId={gid}"})
    else:
        r = get(f"{WEB}/gamecenter/{gid}/{kind}")
    if r is None:
        return "fail"
    save_json_gz(path, r.json())
    return "ok"


def run(kind, gids, workers=8):
    stats = {}
    with ThreadPoolExecutor(workers) as ex:
        for res in ex.map(lambda g: fetch(kind, g), gids):
            stats[res] = stats.get(res, 0) + 1
    print(kind, stats, flush=True)


def player_ids():
    ids = set()
    for f in glob.glob(f"{RAW}/boxscore/*/*.json.gz"):
        b = load_json_gz(f)
        for side in ("awayTeam", "homeTeam"):
            pg = b.get("playerByGameStats", {}).get(side, {})
            for grp in ("forwards", "defense", "goalies"):
                for p in pg.get(grp, []):
                    ids.add(p["playerId"])
    return sorted(ids)


def fetch_player(pid):
    path = f"{RAW}/players/{pid}.json.gz"
    if os.path.exists(path):
        return "skip"
    r = get(f"{WEB}/player/{pid}/landing")
    if r is None:
        return "fail"
    save_json_gz(path, r.json())
    return "ok"


if __name__ == "__main__":
    games = schedules()
    all_ids = sorted(games)
    detail_ids = [g for g, s in games.items() if s in DETAIL_SEASONS]
    print("completed games", len(all_ids), "detail", len(detail_ids), flush=True)
    run("boxscore", all_ids)
    run("right-rail", detail_ids)
    run("play-by-play", detail_ids)
    run("shifts", detail_ids, workers=6)
    pids = player_ids()
    print("players", len(pids), flush=True)
    st = {}
    with ThreadPoolExecutor(8) as ex:
        for res in ex.map(fetch_player, pids):
            st[res] = st.get(res, 0) + 1
    print("players", st, flush=True)
    sys.exit(0)
