#!/usr/bin/env bash
# Nightly card: refresh odds + lines/goalies, price everything, build quarry -> pyramid.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH=src/ingest
export SLATE_DATE="${1:-$(TZ=America/New_York date +%F)}"
echo "slate date: $SLATE_DATE"
set -a; [ -f .env ] && . ./.env; set +a
python3 src/ingest/dailyfaceoff.py
PYTHONPATH=src python3 src/run_slate.py --refresh > /dev/null
python3 src/boards.py > /dev/null          # AG / 2+ goals / first goal / points / assists
python3 src/build_pyramid.py > /dev/null   # RAW_MATERIALS.md (the quarry)
python3 src/construct.py > /dev/null       # PYRAMID.md (inspected + built)
python3 src/sgp_card.py > /dev/null        # SGP_MENU.md (simulator v1 correlated combos + min quotes)
python3 src/tails_board.py > /dev/null     # TAILS.md (alt totals / team totals / puck lines vs simulator)
EARLY_TAG=$([ -f "cards/$SLATE_DATE/EARLY.md" ] && echo _late) python3 src/early_card.py "$SLATE_DATE" > /dev/null   # EARLY.md (prop model v2; validated SOG-under rule)
python3 src/dashboard/export.py > /dev/null 2>&1 || echo "dashboard export failed"   # dashboard/data/*.json
pgrep -f "snapshot_supervisor.sh" > /dev/null || (setsid nohup ./scripts/snapshot_supervisor.sh 180 >> logs/snapshot.log 2>&1 < /dev/null &)
pgrep -f "scripts/autosave.sh" > /dev/null || (setsid nohup ./scripts/autosave.sh >> logs/autosave.log 2>&1 < /dev/null &)
echo "done: cards/*/PYRAMID.md, RAW_MATERIALS.md, BOARDS.md"
