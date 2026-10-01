#!/bin/bash
# SessionStart: make sure python deps exist and the irreplaceable live-capture loops are running.
set -euo pipefail
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"
mkdir -p logs
python3 -c "import pandas, numpy, scipy, duckdb, pyarrow, sklearn, requests" 2>/dev/null \
  || pip install -q -r requirements.txt pyflakes >/dev/null 2>&1
pgrep -f "scripts/snapshot_supervisor.sh" >/dev/null \
  || (setsid nohup ./scripts/snapshot_supervisor.sh 180 >> logs/snapshot.log 2>&1 < /dev/null &)
pgrep -f "scripts/autosave.sh" >/dev/null \
  || (setsid nohup ./scripts/autosave.sh >> logs/autosave.log 2>&1 < /dev/null &)
echo "session-start: deps ok; snapshot supervisor + autosave running"
