"""Shared HTTP + storage helpers for resumable ingestion."""
import gzip
import json
import os
import time

import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (nhl-2026 research)"


def load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)


def get(url, params=None, headers=None, tries=5, timeout=60):
    for i in range(tries):
        try:
            r = S.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code}")
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                print("FAIL", url, e, flush=True)
                return None
            time.sleep(2 ** i)


def save_json_gz(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def load_json_gz(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def download(url, path, min_bytes=100):
    if os.path.exists(path) and os.path.getsize(path) >= min_bytes:
        return "skip"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    r = get(url, timeout=600)
    if r is None:
        return "fail"
    tmp = path + ".tmp"
    open(tmp, "wb").write(r.content)
    os.replace(tmp, path)
    return "ok"
