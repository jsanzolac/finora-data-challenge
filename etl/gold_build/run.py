"""gold_build: full rebuild of the gold acquisition model (docs/gold_acquisition_model.md)
from the latest succeeded silver run, inside the Glue Spark job finora-dl-gold-build
(MaxConcurrentRuns=1). Step Functions runs it after finora-dl-dq-publish, so a
gold failure can never stop or change the DQ publish.

Writes, for a run_id: the job-owned gold Iceberg tables through
write-audit-publish (one snapshot per table, tagged <run_id>), the run report
s3://<gold>/_runs/run_id=<id>/gold_report.json, then the acquisition serving
snapshot acq/runs/<id>/summary.json and the acq/latest.json pointer LAST. A
failed control or audit publishes nothing: main, acq/latest.json and dq/* stay
as they were. Reads the rates table, never writes it (§6.5).
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Callable

from common.s3io import get_json, log, now_iso, put_json
from gold_build import engine, gconfig, spark_io, summary

RUN_ID = re.compile(r"r[0-9]{8}T[0-9]{6}Z")
ALERT_FINDINGS = {"RATE_HISTORY_REWRITTEN", "WON_ON_UNKNOWN_MEMBER", "UNKNOWN_INDUSTRY_CODE", "UNKNOWN_SPEND_CATEGORY"}


def latest_succeeded_silver(serving: str) -> str:
    """The silver run to read: the newest run marked succeeded in dq/runs.json.
    A failed run's tag (for example r20261117T040928Z) is never read."""
    runs = get_json(serving, "dq/runs.json") or []
    ok = sorted(r["run_id"] for r in runs if r.get("status") == "succeeded" and RUN_ID.fullmatch(r.get("run_id", "")))
    if not ok:
        raise engine.GoldControlError("input: no succeeded silver run in dq/runs.json")
    return ok[-1]


def run(event: dict, *, reader: spark_io.SilverReader, writer: spark_io.GoldWriter,
        alert: Callable[[str, str], None] | None = None, now: datetime | None = None) -> dict:
    gcfg = gconfig.load()
    run_id = event["run_id"]
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("bad run_id")
    gold, serving = os.environ["GOLD_BUCKET"], os.environ["SERVING_BUCKET"]
    built_at = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    report: dict = {"run_id": run_id, "status": "running", "started_at": event.get("started_at"),
                    "gold_model_version": gcfg["gold_model_version"], "built_at": built_at.strftime("%Y-%m-%dT%H:%M:%SZ")}
    key = f"_runs/run_id={run_id}/gold_report.json"
    try:
        silver_run_id = latest_succeeded_silver(serving)
        report["silver_run_id"] = silver_run_id
        if event.get("expected_silver_run_id") and event["expected_silver_run_id"] != silver_run_id:
            report["note"] = f"pipeline run {event['expected_silver_run_id']} is not the latest succeeded silver run"
        silver, snaps = reader.read_all(silver_run_id)
        report["silver_snapshots"] = snaps
        previous = writer.previous_status()
        rows, sid = writer.rate_rows()
        prev_rows = prev_err = None
        if previous and previous.get("rate_table_snapshot_id") is not None:
            try:
                prev_rows, _ = writer.rate_rows(int(previous["rate_table_snapshot_id"]))
            except Exception as err:  # noqa: BLE001 -- an unreadable snapshot is itself the finding
                prev_err = type(err).__name__
        rate = engine.rate_state(rows, sid, gcfg, built_at.replace(tzinfo=None), previous, prev_rows, prev_err)
        report["previous_gold_run_id"] = previous.get("_run_id") if previous else None
        res = engine.build(silver, gcfg, {"run_id": run_id, "silver_run_id": silver_run_id, "built_at": built_at,
                                          "gold_model_version": gcfg["gold_model_version"], "rate": rate})
        report.update({"controls": res["controls"], "findings": res["findings"], "figures": res["figures"],
                       "watermarks": {"window_start_month": res["window_start"],
                                      "revenue_complete_through": res["as_of_month"],
                                      "spend_complete_through": res["spend_complete_through"],
                                      "data_complete_through": res["data_complete_through"]},
                       "rate_table": {k: rate[k] for k in ("snapshot_id", "rows_sha256", "base_match", "row_count")}})
        engine.assert_controls(res)
        report["iceberg"] = spark_io.write_audit_publish(writer, res["tables"], run_id)
    except Exception as err:
        report["status"] = "failed"
        report["error"] = f"{type(err).__name__}: {str(err)[:500]}"
        put_json(gold, key, report)
        log("gold.failed", run_id=run_id, error=type(err).__name__)
        raise
    report["status"] = "succeeded"
    report["finished_at"] = now_iso()
    put_json(gold, key, report)
    payload = summary.build(res, gcfg)
    put_json(serving, f"acq/runs/{run_id}/summary.json", payload)
    put_json(serving, "acq/latest.json", {"run_id": run_id, "published_at": now_iso()})  # last
    alerts = [f for f in res["findings"] if f["finding"] in ALERT_FINDINGS]
    if alerts and alert:
        alert(f"Finora gold {run_id}: {', '.join(sorted({f['finding'] for f in alerts}))}",
              f"Gold run {run_id} published with findings that need attention. Report: s3://{gold}/{key}")
    log("gold.published", run_id=run_id, silver_run_id=silver_run_id, rows=res["figures"]["rows"],
        findings=[f["finding"] for f in res["findings"]])
    return {"status": "succeeded", "run_id": run_id, "silver_run_id": silver_run_id}
