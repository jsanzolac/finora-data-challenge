"""dq_publish (Glue job finora-dl-dq-publish): write the serving snapshot of a
succeeded run, then runs.json,
then the dq/latest.json pointer LAST (CTO-10). Published runs are immutable.
In mode "failed" it only records the failed run in runs.json; latest.json is
not touched, so the previous publish stays live."""

from __future__ import annotations

import os

from common import config
from common.s3io import get_json, log, now_iso, put_json


def _runs(serving: str) -> list[dict]:
    return get_json(serving, "dq/runs.json") or []


def publish(event: dict, cfg: dict) -> dict:
    serving, silver = os.environ["SERVING_BUCKET"], os.environ["SILVER_BUCKET"]
    run_id = event["run_id"]
    bundle = get_json(silver, f"_runs/run_id={run_id}/dq_bundle.json.gz")
    summary = bundle["summary"]
    run = {**summary["run"], "finished_at": now_iso(), "status": "succeeded"}
    summary["run"] = run
    page_size = int(cfg["dq"]["serving_page_size"])
    base = f"dq/runs/{run_id}"
    pages_written = 0
    for key, recs in bundle["records"].items():
        rule_id, ds = key.split("|")
        cols = bundle["columns"][ds]
        n_pages = max(1, -(-len(recs) // page_size))
        for p in range(n_pages):
            chunk = recs[p * page_size:(p + 1) * page_size]
            put_json(serving, f"{base}/records/{rule_id}/{ds}/page-{p + 1}.json",
                     {"rule_id": rule_id, "dataset_id": ds, "run_id": run_id, "total": len(recs),
                      "page": p + 1, "page_size": page_size, "page_count": n_pages, "columns": cols,
                      "records": chunk})
            pages_written += 1
    trend = get_json(serving, "dq/trend.json") or []
    trend = [t for t in trend if t["run_id"] != run_id]
    trend.append({"run_id": run_id, "as_of_month": run["as_of_month"],
                  **{d["dataset_id"]: d["row_compliance_pct"] for d in summary["datasets"]}})
    trend = trend[-int(cfg["dq"]["trend_runs"]):]
    summary["trend"] = trend
    put_json(serving, f"{base}/summary.json", summary)
    put_json(serving, "dq/trend.json", trend)
    runs = [run] + [r for r in _runs(serving) if r["run_id"] != run_id]
    put_json(serving, "dq/runs.json", runs)
    put_json(serving, "dq/latest.json", {"run_id": run_id, "published_at": now_iso()})  # last
    log("dq.published", run_id=run_id, pages=pages_written)
    return {"run_id": run_id, "published": True, "pages": pages_written}


def record_failure(event: dict) -> dict:
    serving = os.environ["SERVING_BUCKET"]
    run_id = event.get("run_id")
    if not run_id:
        log("dq.failed_before_run_id")
        return {"recorded": False}
    ingested = event.get("ingested") or {}
    entry = {"run_id": run_id, "started_at": event.get("started_at"), "finished_at": now_iso(),
             "as_of_month": None, "status": "failed",
             "datasets": {ds: {"source_key": v.get("source_key"), "sha256": v.get("sha256"),
                               "rows_read": v.get("rows")} for ds, v in ingested.items()}}
    runs = [entry] + [r for r in _runs(serving) if r["run_id"] != run_id]
    put_json(serving, "dq/runs.json", runs)
    log("dq.run_failed_recorded", run_id=run_id)
    return {"recorded": True, "run_id": run_id}


def handler(event, context=None):
    cfg = config.load()
    if event.get("mode") == "failed":
        return record_failure(event)
    return publish(event, cfg)
