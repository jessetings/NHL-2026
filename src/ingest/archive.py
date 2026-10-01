"""Archive irreplaceable live captures into git-tracked, compact files under archive/.

- Odds snapshots: per day, a CHANGE-LOG parquet (zstd). A row is kept only when (eventID, oddID, book, alt, line)
  first appears or its odds/availability changed versus the previous snapshot. Exact reconstruction of every
  snapshot is possible (forward-fill by snap_ts). Snapshot timestamps are kept in a separate small index.
- DailyFaceoff snapshots: copied as-is (already gzip JSON, ~300 KB each).
Idempotent: re-running rebuilds the day file from all compact snapshots on disk plus the existing archive.
Usage: python src/ingest/archive.py [YYYY-MM-DD ...]   (default: every day present)
"""
import glob
import os
import shutil
import sys

import pandas as pd

SNAP = "data/raw/snapshots/compact"
ARCH = "archive"
KEY = ["eventID", "oddID", "book", "alt", "line"]


def archive_day(day):
    files = sorted(glob.glob(f"{SNAP}/{day}/*.parquet"))
    out = f"{ARCH}/odds_snapshots/{day}.parquet"
    frames = [pd.read_parquet(f) for f in files]
    if os.path.exists(out):                       # merge with what is already archived (e.g. after a restart)
        frames.append(pd.read_parquet(out).drop(columns=["changed"], errors="ignore"))
    if not frames:
        return None
    s = pd.concat(frames, ignore_index=True)
    s["line"] = s.line.astype(str)
    s["odds"] = s.odds.astype(str)
    s = s.drop_duplicates(KEY + ["snap_ts"]).sort_values(KEY + ["snap_ts"])
    prev = s.groupby(KEY, dropna=False)[["odds", "available"]].shift(1)
    s["changed"] = prev.odds.isna() | (prev.odds != s.odds) | (prev.available != s.available)
    log = s[s.changed].drop(columns=["changed"])
    os.makedirs(f"{ARCH}/odds_snapshots", exist_ok=True)
    log.to_parquet(out, index=False, compression="zstd")
    idx = pd.DataFrame({"snap_ts": sorted(s.snap_ts.unique())})
    idx.to_csv(f"{ARCH}/odds_snapshots/{day}_snapshots.csv", index=False)
    return len(s), len(log), os.path.getsize(out)


def archive_df():
    os.makedirs(f"{ARCH}/dailyfaceoff", exist_ok=True)
    n = 0
    for f in glob.glob("data/raw/dailyfaceoff/*.json.gz"):
        dst = f"{ARCH}/dailyfaceoff/{os.path.basename(f)}"
        if not os.path.exists(dst):
            shutil.copy2(f, dst)
            n += 1
    return n


if __name__ == "__main__":
    days = sys.argv[1:] or sorted(os.path.basename(d) for d in glob.glob(f"{SNAP}/*"))
    for d in days:
        r = archive_day(d)
        if r:
            print(f"{d}: {r[0]:,} snapshot rows -> {r[1]:,} change rows ({r[2] / 1e6:.2f} MB)")
    print("dailyfaceoff copied:", archive_df())
