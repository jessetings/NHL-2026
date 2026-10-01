#!/usr/bin/env bash
# Every 30 min: compact live captures into archive/ and push ONLY archive/ to the working branch.
# Irreplaceable data (odds snapshots incl. alt lines, DailyFaceoff lines/goalies) survives container resets.
cd "$(dirname "$0")/.."
BRANCH=$(git rev-parse --abbrev-ref HEAD)
while true; do
  python3 src/ingest/archive.py > /dev/null 2>&1
  if [ -n "$(git status --porcelain archive/)" ]; then
    git add archive/ && git commit -q -m "autosave: live odds/lineup captures $(date -u +%Y-%m-%dT%H:%MZ)" -- archive/ \
      && for i in 1 2 3 4; do git push -q origin "$BRANCH" && break || sleep $((2**i)); done
    echo "$(date -u +%T) archived + pushed"
  fi
  sleep 1800
done
