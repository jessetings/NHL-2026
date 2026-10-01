# Daily Runbook

## Every game day (about 60–30 min before first puck)
```bash
./nightly.sh                 # today's slate (ET date), or: ./nightly.sh 2026-10-01
```
This produces `cards/<date>/`:
- `PYRAMID.md`: the built card (capstone / upper / middle / foundation; cracks tagged; tickets)
- `RAW_MATERIALS.md`: the quarry (all +EV stones and cross-game parlays)
- `BOARDS.md`: AG, 2+ goals, first goal scorer, points, assists (fair + kill prices)
- `SGP_MENU.md`: simulator v1 same-game combos with min acceptable quotes (incl. 50% boost)
- CSVs for everything (`props_all.csv` is the full candidate log, passes included)

It also keeps the live odds snapshotter and the autosave loop running.

Profit boost on a given book:
```bash
python3 src/boost.py --book draftkings --boost 0.5 [--max-win-mult 20] [--exclude-game NYI@TOR]
```

## After the slate
```bash
python3 src/grade.py <date>        # results (boxscores), first scorers, CLV vs last pregame snapshot, Brier
```

## Fresh container
```bash
pip install -q -r requirements.txt
./scripts/bootstrap.sh             # ~20–30 min: re-pulls MoneyPuck/NHL/SGO history, curates, fits features/models
```
Live captures (odds snapshots, DailyFaceoff) are restored from `archive/` in git.

## Background processes (started by nightly.sh if missing)
- `scripts/snapshot_supervisor.sh`: SGO odds every 3 min, all books, alt lines. The only source for alt-line and line-movement history.
- `scripts/autosave.sh`: every 30 min, compacts captures into `archive/` and pushes them to GitHub.
