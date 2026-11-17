"""gold_mrr: full rebuild of the gold MRR model (docs/mrr_discounts_model.md §6)
from the latest succeeded silver run, inside the Glue Spark job
finora-dl-gold-mrr (MaxConcurrentRuns=1). Step Functions runs it after the
acquisition gold build and its gold.refreshed event, so an MRR failure can never
stop or change the DQ publish (dq/*) or the acquisition publish (acq/*).

Writes, for a run_id: the four MRR Iceberg tables through write-audit-publish
(one snapshot per table, tagged <run_id>), the run report
s3://<gold>/_runs/run_id=<id>/mrr_report.json, then the serving snapshot
mrr/runs/<id>/movements/page-<n>.json, mrr/runs/<id>/summary.json and the
mrr/latest.json pointer LAST. A failed control or audit publishes nothing.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from common.s3io import get_json, log, now_iso, put_json
from gold_mrr import engine, iceberg_io, mconfig, summary

RUN_ID = re.compile(r"r[0-9]{8}T[0-9]{6}Z")


def latest_succeeded_silver(serving: str) -> str:
    """The newest run marked succeeded in dq/runs.json (a failed run's tag is never read)."""
    runs = get_json(serving, "dq/runs.json") or []
    ok = sorted(r["run_id"] for r in runs if r.get("status") == "succeeded" and RUN_ID.fullmatch(r.get("run_id", "")))
    if not ok:
        raise engine.MrrControlError("input: no succeeded silver run in dq/runs.json")
    return ok[-1]


def run(event: dict, *, reader: iceberg_io.SilverReader, writer: iceberg_io.MrrWriter,
        now: datetime | None = None) -> dict:
    cfg = mconfig.load()
    run_id = event["run_id"]
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("bad run_id")
    gold, serving = os.environ["GOLD_BUCKET"], os.environ["SERVING_BUCKET"]
    built_at = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    report: dict = {"run_id": run_id, "status": "running", "started_at": event.get("started_at"),
                    "gold_model_version": cfg["gold_model_version"], "spec_sha256": cfg["spec_sha256"],
                    "mrr_basis": cfg["params"]["mrr_basis"], "built_at": built_at.strftime("%Y-%m-%dT%H:%M:%SZ")}
    key = f"_runs/run_id={run_id}/mrr_report.json"
    try:
        silver_run_id = latest_succeeded_silver(serving)
        report["silver_run_id"] = silver_run_id
        if event.get("expected_silver_run_id") and event["expected_silver_run_id"] != silver_run_id:
            report["note"] = f"pipeline run {event['expected_silver_run_id']} is not the latest succeeded silver run"
        silver, snaps = reader.read_all(silver_run_id)
        report["silver_snapshots"] = snaps
        meta = {"run_id": run_id, "silver_run_id": silver_run_id, "built_at": built_at,
                "gold_model_version": cfg["gold_model_version"]}
        res = engine.build(silver, cfg, meta)
        report.update({"controls": res["controls"], "figures": res["figures"]})
        engine.assert_controls(res)
        payload = summary.build(res, cfg, meta)
        pages = summary.movement_pages(res, cfg, run_id)
        errs = summary.check_contract(payload, pages)
        report["contract_checks"] = errs or "passed"
        if errs:
            raise engine.MrrControlError(f"contract identities failed on the snapshot: {errs[:5]}")
        report["iceberg"] = iceberg_io.write_audit_publish(writer, res["tables"], run_id)
    except Exception as err:
        report["status"] = "failed"
        report["error"] = f"{type(err).__name__}: {str(err)[:500]}"
        put_json(gold, key, report)
        log("gold_mrr.failed", run_id=run_id, error=type(err).__name__)
        raise
    report["status"] = "succeeded"
    report["finished_at"] = now_iso()
    put_json(gold, key, report)
    for p in pages:
        put_json(serving, f"mrr/runs/{run_id}/movements/page-{p['page']}.json", p)
    put_json(serving, f"mrr/runs/{run_id}/summary.json", payload)
    put_json(serving, "mrr/latest.json", {"run_id": run_id, "published_at": now_iso()})  # last
    log("gold_mrr.published", run_id=run_id, silver_run_id=silver_run_id, rows=res["figures"]["rows"],
        pages=len(pages))
    return {"status": "succeeded", "run_id": run_id, "silver_run_id": silver_run_id}
