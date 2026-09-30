"""MoneyPuck: season summaries (2015+), shot files (2022+), team game-by-game."""
import sys
from concurrent.futures import ThreadPoolExecutor

from common import download

RAW = "data/raw/moneypuck"
SUMMARY_SEASONS = range(2015, 2027)   # 2015 = 2015-16
SHOT_SEASONS = range(2022, 2027)
KINDS = ["skaters", "goalies", "teams", "lines"]


def jobs():
    for s in SUMMARY_SEASONS:
        for gt in ["regular", "playoffs"]:
            for k in KINDS:
                yield (f"https://moneypuck.com/moneypuck/playerData/seasonSummary/{s}/{gt}/{k}.csv",
                       f"{RAW}/seasonSummary/{gt}/{k}_{s}.csv")
    for s in SHOT_SEASONS:
        yield (f"https://peter-tanner.com/moneypuck/downloads/shots_{s}.zip", f"{RAW}/shots/shots_{s}.zip")
    yield ("https://moneypuck.com/moneypuck/playerData/careers/gameByGame/all_teams.csv",
           f"{RAW}/gameByGame/all_teams.csv")
    yield ("https://moneypuck.com/moneypuck/playerData/playerBios/allPlayersLookup.csv",
           f"{RAW}/allPlayersLookup.csv")


if __name__ == "__main__":
    with ThreadPoolExecutor(4) as ex:
        for (u, p), res in zip(list(jobs()), ex.map(lambda j: download(*j), list(jobs()))):
            print(res, p, flush=True)
    sys.exit(0)
