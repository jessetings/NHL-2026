#!/usr/bin/env bash
# Keeps the live odds snapshotter running forever (restarts it if it exits for any reason).
cd "$(dirname "$0")/.."
export PYTHONPATH=src/ingest
while true; do
  python3 src/ingest/snapshot.py --interval "${1:-180}"
  echo "$(date -u +%T)Z snapshot.py exited with $? - restarting in 15s"
  sleep 15
done
