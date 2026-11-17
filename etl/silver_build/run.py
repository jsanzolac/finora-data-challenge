"""silver_build: full rebuild of silver and the DQ store from the current bronze
snapshot of each dataset (CTO-10). Runs inside the Glue Spark job
finora-dl-silver-build (MaxConcurrentRuns=1 serializes runs).

Writes, for a run_id: the silver and DQ Iceberg tables (through `write_tables`,
one snapshot per table tagged with the run_id), the keys snapshot for CDO-06,
the serving bundle for dq_publish and the run report. Nothing is published
here: a failed run control raises, the report says why, and the previous
publish stays live.
"""

from __future__ import annotations

import hashlib
import os
from typing import Callable

from common import config, dq
from common.records import strip_bronze
from common.s3io import get_bytes, get_json, log, now_iso, put_json
from silver_build.engine import DatasetInput, RunControlError, assert_controls, build


def _load_inputs(cfg: dict) -> dict:
    bronze_bucket = os.environ["BRONZE_BUCKET"]
    out = {}
    for ds in cfg["dataset_order"]:
        cur = get_json(bronze_bucket, f"_current/{ds}.json")
        if not cur:
            out[ds] = None
            continue
        manifest = get_json(bronze_bucket, cur["manifest_key"])
        bronze = get_bytes(bronze_bucket, cur["bronze_key"])
        staging, _ = strip_bronze(bronze) if bronze else (b"", [])
        if hashlib.sha256(staging).hexdigest() != cur["sha256"]:
            raise RunControlError(f"CTO-01: bronze snapshot of {ds} does not reproduce its staging bytes")
        out[ds] = DatasetInput(staging=staging, source_key=manifest["source_key"], sha256=cur["sha256"],
                               ingested_at=manifest["_ingested_at"], bronze_key=cur["bronze_key"])
    return out


def _previous() -> dict | None:
    latest = get_json(os.environ["SERVING_BUCKET"], "dq/latest.json")
    if not latest:
        return None
    keys = get_json(os.environ["SILVER_BUCKET"], f"_runs/run_id={latest['run_id']}/keys.json.gz")
    return {"run_id": latest["run_id"], "keys": keys} if keys else None


def run(event: dict, *, write_tables: Callable[[dict, dict, str], dict],
        evaluate_dq: Callable[[dict, dict], tuple] | None = None, lifecycle_map=None) -> dict:
    """event = {"run_id", "started_at"}. `evaluate_dq(inputs, cfg)` returns
    (Predicates, report) from Glue Data Quality; `write_tables(res, store,
    run_id)` commits the Iceberg tables and returns their snapshot record."""
    cfg = config.load()
    run_id = event["run_id"]
    silver_bucket = os.environ["SILVER_BUCKET"]
    inputs = _load_inputs(cfg)
    pred, dq_report = evaluate_dq(inputs, cfg) if evaluate_dq else (None, None)
    res = build(inputs, cfg, run_id, _previous(), predicates=pred, lifecycle_map=lifecycle_map)
    run_info = {"run_id": run_id, "started_at": event.get("started_at"), "finished_at": None,
           "as_of_month": res["as_of_month"], "status": "succeeded",
           "datasets": {ds: {"source_key": inp.source_key, "sha256": inp.sha256,
                             "rows_read": len(res["rows"][ds])}
                        for ds, inp in inputs.items() if inp}}
    summary = dq.summarize(res, cfg, run_info)
    report = {"run_id": run_id, "rules_version": cfg["rules_version"], "built_at": now_iso(),
              "as_of_month": res["as_of_month"], "controls": res["controls"],
              "datasets": summary["datasets"],
              "rules": [{"rule_id": r["rule_id"], "results": r["results"]} for r in summary["rules"]],
              "figures": res["figures"], "outliers": res["outliers"],
              "inputs": {ds: {"sha256": i.sha256, "bronze_key": i.bronze_key, "source_key": i.source_key}
                         for ds, i in inputs.items() if i}}
    if pred is not None:
        report["glue_dq"] = {"datasets": dq_report, "consulted": dict(pred.consulted),
                             "mismatches": pred.mismatches[:50], "mismatch_count": len(pred.mismatches)}
    try:
        assert_controls(res)
        if pred is not None and pred.mismatches:
            raise RunControlError(f"Glue DQ and the reference predicates disagree on {len(pred.mismatches)} "
                                  "row checks (DQDL translation defect)")
    except RunControlError as err:
        report["status"] = "failed"
        report["error"] = str(err)
        put_json(silver_bucket, f"_runs/run_id={run_id}/report.json", report)
        log("silver.run_control_failed", run_id=run_id, error=str(err))
        raise
    records = dq.records_for(res, cfg)
    store = dq.dq_store_rows(res, cfg, records)
    try:
        tables = write_tables(res, store, run_id)
    except Exception as err:  # a failed commit: record it, the previous publish stays live
        report["status"] = "failed"
        report["error"] = f"table write failed: {type(err).__name__}: {str(err)[:500]}"
        put_json(silver_bucket, f"_runs/run_id={run_id}/report.json", report)
        log("silver.write_failed", run_id=run_id, error=type(err).__name__)
        raise
    put_json(silver_bucket, f"_runs/run_id={run_id}/keys.json.gz", res["keys"])
    bundle = {"summary": summary,
              "columns": {ds: cfg["datasets"][ds]["columns"] for ds in cfg["dataset_order"]},
              "records": {f"{r}|{d}": recs for (r, d), recs in records.items()}}
    put_json(silver_bucket, f"_runs/run_id={run_id}/dq_bundle.json.gz", bundle)
    report["status"] = "succeeded"
    report["written"] = {t: v["rows"] for t, v in tables.items()}
    report["iceberg"] = tables
    put_json(silver_bucket, f"_runs/run_id={run_id}/report.json", report)
    log("silver.built", run_id=run_id, written=report["written"])
    return {"status": "succeeded", "as_of_month": res["as_of_month"],
            "datasets": {d["dataset_id"]: {k: d[k] for k in ("rows_read", "rows_excluded", "rows_flagged",
                                                             "row_compliance_pct")}
                         for d in summary["datasets"]}}
