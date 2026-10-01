#!/usr/bin/env bash
# Rebuild ALL derived data in a fresh container (~20-30 min). Needs SGO_API_KEY in env or .env.
# Irreplaceable captures are restored from git (archive/); everything else is re-pulled.
set -euo pipefail
cd "$(dirname "$0")/.."
pip install -q -r requirements.txt scikit-learn pyarrow
export PYTHONPATH=src/ingest
mkdir -p logs
python3 src/ingest/moneypuck.py > logs/moneypuck.log
python3 src/ingest/nhl.py > logs/nhl.log
python3 src/ingest/sgo_history.py > logs/sgo_history.log
python3 src/ingest/sgo_history.py --open-close > logs/sgo_oc.log
python3 src/ingest/curate.py all
python3 src/ingest/idmap.py
python3 src/features/deployment.py
python3 src/features/build.py
python3 src/market/baseline.py
python3 src/features/goalie_start.py
python3 src/sim/fit.py
# restore archived live captures as raw snapshots are not needed by the models (archive/ is read directly)
echo "bootstrap complete"
