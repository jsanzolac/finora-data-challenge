"""The run context of the live gold build (docs/semantic_layer.md §1.0), read from our
own run reports, never from the model:

- gold_run_id: serving acq/latest.json (the gold build that published last);
- snapshots: Iceberg snapshot ids of that run, from s3://<gold>/_runs/run_id=<id>/
  gold_report.json and mrr_report.json (every SQL pins them: FOR VERSION AS OF);
- data_complete_through / window_start_month: the gold report's watermarks
  (the same values as gold_build_status);
- dq_run_id: the gold report's silver_run_id (DQ answers read the DQ snapshot of the
  same silver run, so gold and DQ never mix runs);
- churn_confirmed_through: the MRR serving snapshot's run block.

Cached per gold run in memory: a run's reports never change.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from .compiler import Context

POINTER_CACHE_S = 60
_s3 = None
_by_run: dict[str, Context] = {}
_pointer: tuple[float, str] | None = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def get_json(bucket: str, key: str) -> Any:
    try:
        return json.loads(s3().get_object(Bucket=bucket, Key=key)["Body"].read())
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404", "AccessDenied"):
            return None
        raise


def current_gold_run() -> str:
    global _pointer
    if _pointer and time.monotonic() - _pointer[0] < POINTER_CACHE_S:
        return _pointer[1]
    latest = get_json(os.environ["SERVING_BUCKET"], "acq/latest.json") or {}
    run = latest.get("run_id") or ""
    _pointer = (time.monotonic(), run)
    return run


class ContextUnavailable(Exception):
    pass


def load(run_id: str | None = None) -> Context:
    run = run_id or current_gold_run()
    if not run:
        raise ContextUnavailable("no published gold run")
    if run in _by_run:
        return _by_run[run]
    gold, serving = os.environ["GOLD_BUCKET"], os.environ["SERVING_BUCKET"]
    g = get_json(gold, f"_runs/run_id={run}/gold_report.json")
    m = get_json(gold, f"_runs/run_id={run}/mrr_report.json") or {}
    if not g or g.get("status") != "succeeded":
        raise ContextUnavailable(f"gold report of {run} missing or not succeeded")
    snaps = {t: v.get("snapshot_id") for t, v in (g.get("iceberg") or {}).items() if v.get("snapshot_id")}
    if m.get("status") == "succeeded":
        snaps.update({t: v.get("snapshot_id") for t, v in (m.get("iceberg") or {}).items() if v.get("snapshot_id")})
    wm = g.get("watermarks") or {}
    mrr_summary = get_json(serving, f"mrr/runs/{run}/summary.json") or {}
    dct = wm.get("data_complete_through") or (mrr_summary.get("run") or {}).get("data_complete_through")
    ctx = Context(gold_run_id=run, dq_run_id=g.get("silver_run_id") or run, data_complete_through=dct,
                  window_start_month=wm.get("window_start_month") or "2022-01",
                  churn_confirmed_through=(mrr_summary.get("run") or {}).get("churn_confirmed_through") or dct,
                  snapshots=snaps)
    _by_run[run] = ctx
    return ctx


_dq: dict[str, dict] = {}


def dq_snapshot(ctx: Context) -> dict:
    if ctx.dq_run_id not in _dq:
        snap = get_json(os.environ["SERVING_BUCKET"], f"dq/runs/{ctx.dq_run_id}/summary.json")
        if not snap:
            raise ContextUnavailable(f"DQ snapshot of {ctx.dq_run_id} missing")
        _dq[ctx.dq_run_id] = snap
    return _dq[ctx.dq_run_id]
