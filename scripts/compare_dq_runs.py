#!/usr/bin/env python3
"""Compare two DQ serving snapshots (summary.json + every records page).

    python3 scripts/compare_dq_runs.py <old> <new> [--history-aware]

<old>/<new> are local directories holding a run's serving files (summary.json,
records/<rule>/<dataset>/page-<n>.json) or s3://bucket/dq/runs/<run_id>/ URIs
(read with the default AWS credentials; nothing is written). run_id and
timestamps (started_at, finished_at, published_at) are normalized; everything
else must be equal. --history-aware also reports, separately, the blocks that
depend on the run history rather than on the data: CDO-06a/CDO-06b results
(na on a first run, evaluated against the previous run otherwise) and `trend`
(one entry per published run). Prints a unified diff; exit 0 when it is empty.
Record values may be HR-sensitive: the diff is printed, never stored by this script.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

TS = {"started_at", "finished_at", "published_at"}
HISTORY_RULES = {"CDO-06a", "CDO-06b"}


def load(src: str) -> dict[str, object]:
    out: dict[str, object] = {}
    if src.startswith("s3://"):
        import boto3

        bucket, _, prefix = src[5:].partition("/")
        prefix = prefix.rstrip("/") + "/"
        s3 = boto3.client("s3", region_name="us-west-2")
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            for o in page.get("Contents", []):
                out[o["Key"][len(prefix):]] = json.loads(s3.get_object(Bucket=bucket, Key=o["Key"])["Body"].read())
    else:
        root = Path(src)
        for p in sorted(root.rglob("*.json")):
            out[str(p.relative_to(root))] = json.loads(p.read_text(encoding="utf-8"))
    return out


def norm(o):
    if isinstance(o, dict):
        return {k: ("<ts>" if k in TS else "<run_id>" if k == "run_id" else norm(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [norm(v) for v in o]
    return o


def split_history(summary: dict) -> tuple[dict, dict]:
    """Move the history-dependent blocks out of a summary: the CDO-06a/b
    results, the share of each dataset's rules_evaluated / rules_failing they
    account for, and the trend length."""
    s = json.loads(json.dumps(summary))
    hist = {"trend_len": len(s.pop("trend", [])), "rules": {}, "datasets": {}}
    for r in s["rules"]:
        if r["rule_id"] not in HISTORY_RULES:
            continue
        res = r.pop("results")
        hist["rules"][r["rule_id"]] = res
        if not r.get("counts_toward_compliance"):
            continue
        for d in s["datasets"]:
            v = res.get(d["dataset_id"], {})
            h = hist["datasets"].setdefault(d["dataset_id"], {"rules_evaluated": 0, "rules_failing": 0})
            if v.get("evaluated", 0) > 0:
                d["rules_evaluated"] -= 1
                h["rules_evaluated"] += 1
                if v.get("failed", 0) > 0:
                    d["rules_failing"] -= 1
                    h["rules_failing"] += 1
    return s, hist


def text(o) -> list[str]:
    return json.dumps(o, indent=1, sort_keys=True, ensure_ascii=False).splitlines()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--history-aware", action="store_true")
    a = ap.parse_args()
    old, new = load(a.old), load(a.new)
    diff: list[str] = []
    if set(old) != set(new):
        diff += [f"files only in old: {sorted(set(old) - set(new))}", f"files only in new: {sorted(set(new) - set(old))}"]
    history = None
    for name in sorted(set(old) & set(new)):
        o, n = norm(old[name]), norm(new[name])
        if a.history_aware and name == "summary.json":
            o, ho = split_history(o)
            n, hn = split_history(n)
            history = (ho, hn)
        diff += list(difflib.unified_diff(text(o), text(n), f"old/{name}", f"new/{name}", lineterm=""))
    pages = sum(1 for k in new if k.startswith("records/"))
    print(f"compared {len(set(old) & set(new))} files (summary.json + {pages} record pages)")
    if history:
        print("history-dependent blocks (reported, not diffed):")
        print(json.dumps({"old": history[0], "new": history[1]}, sort_keys=True))
    print("\n".join(diff) if diff else "DIFF: empty")
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
