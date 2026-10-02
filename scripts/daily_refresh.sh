#!/bin/bash
# Daily incremental refresh of current-season data -> features -> prop model v2 next-game predictions.
# Run each morning (and before building a card). Idempotent; ~5-10 min.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
CUR_MP=2026            # MoneyPuck season label of the current season (2026 = 2026-27)
echo "[$(date -u +%FT%TZ)] daily refresh start"
# 1. MoneyPuck current-season files are overwritten upstream daily -> delete local copies so they re-download
rm -f data/raw/moneypuck/shots/shots_${CUR_MP}.zip data/raw/moneypuck/seasonSummary/regular/*_${CUR_MP}.csv \
      data/raw/moneypuck/gameByGame/all_teams.csv
PYTHONPATH=src/ingest python3 src/ingest/moneypuck.py > logs/moneypuck.log 2>&1 || echo "moneypuck ingest failed"
for k in skaters goalies teams lines; do
  [ -f data/raw/moneypuck/seasonSummary/regular/${k}_${CUR_MP}.csv ] && \
    cp data/raw/moneypuck/seasonSummary/regular/${k}_${CUR_MP}.csv data/raw/moneypuck/${k}_${CUR_MP}.csv
done
# 2. NHL API (schedule for the current season is always re-fetched; finished games' files are added)
PYTHONPATH=src/ingest python3 src/ingest/nhl.py > logs/nhl.log 2>&1 || echo "nhl ingest failed"
# 3. curate + features + model predictions
PYTHONPATH=src/ingest python3 src/ingest/curate.py mp > logs/curate_mp.log 2>&1 || echo "curate mp failed"
PYTHONPATH=src/ingest python3 src/ingest/curate.py nhl > logs/curate_nhl.log 2>&1 || echo "curate nhl failed"
python3 src/features/deployment.py > logs/deployment.log 2>&1 || echo "deployment failed"
python3 src/features/build.py > logs/features.log 2>&1 || echo "features failed"
python3 src/features/shotq.py > logs/shotq.log 2>&1 || echo "shotq failed"
python3 src/features/lines.py > logs/lines.log 2>&1 || echo "lines failed"
python3 -c "import sys; sys.path.insert(0, 'src'); from models import props_v2 as P; P.predict_all()" > logs/props_v2.log 2>&1 || echo "props_v2 predict failed"
python3 src/dashboard/export.py > logs/dashboard.log 2>&1 || echo "dashboard export failed"
echo "[$(date -u +%FT%TZ)] daily refresh done"
