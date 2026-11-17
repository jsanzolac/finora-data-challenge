"""bronze_ingest: staging -> bronze, byte-faithful (BRZ-06, CTO-01/02/03). Runs in
the Glue job finora-dl-bronze-ingest.

Read the staging object (read-only), append `_ingested_at`, self-test the round
trip, write the bronze object and a write-once manifest keyed on (dataset,
SHA-256). Re-delivered bytes create nothing new; their snapshot becomes current.
No file check runs and no file is ever rejected.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import unquote_plus

from common import config
from common.records import data_records, make_bronze, round_trip_ok, split_records
from common.s3io import get_bytes, get_json, log, new_run_id, now_iso, put_bytes, put_json, s3

G_AMOUNT = re.compile(r"-?[0-9]+(\.[0-9]+)?")
G_SPEND = re.compile(r"-?\$[0-9]{1,6}\.[0-9]{3}")


class SelfTestError(Exception):
    """CTO-01: our writer produced bytes that do not round-trip. A code defect."""


def _control_totals(ds: str, staging: bytes, cfg: dict) -> dict:
    _, recs = data_records(staging)
    total, bad = Decimal(0), 0
    for rec in recs:
        fields = rec.decode("utf-8", "replace").split(",")
        if ds == "transactions":
            cells, pat, strip = fields[2:3], G_AMOUNT, False
        elif ds == "sm_spend":
            cells, pat, strip = fields[1:8], G_SPEND, True
        else:
            return {}
        for c in cells:
            if pat.fullmatch(c):
                total += Decimal(c.replace("$", "", 1) if strip else c)
            else:
                bad += 1
    return {"sum": str(total), "unparsed_cells": bad}


def _resolve_keys(event: dict, staging_bucket: str, cfg: dict) -> list[tuple[str, str | None]]:
    if event.get("detail", {}).get("object"):
        obj = event["detail"]["object"]
        return [(obj["key"], obj.get("version-id"))]
    if event.get("keys"):
        return [(k, None) for k in event["keys"]]
    if event.get("all"):
        out = []
        for ds in cfg["dataset_order"]:
            prefix = cfg["datasets"][ds]["staging_prefix"]
            got = s3().list_objects_v2(Bucket=staging_bucket, Prefix=prefix).get("Contents", [])
            got = [o for o in got if not o["Key"].endswith("/")]
            if got:
                out.append((max(got, key=lambda o: o["LastModified"])["Key"], None))
        return out
    raise ValueError("no staging keys in the event")


def ingest(ds: str, key: str, version_id: str | None, run_id: str, cfg: dict) -> dict:
    staging_bucket, bronze_bucket = os.environ["STAGING_BUCKET"], os.environ["BRONZE_BUCKET"]
    head_kw = {"Bucket": staging_bucket, "Key": key, **({"VersionId": version_id} if version_id else {})}
    try:
        head = s3().head_object(**head_kw)
    except Exception:  # EventBridge keys can arrive URL-encoded; try the decoded form once.
        key = unquote_plus(key)
        head_kw["Key"] = key
        head = s3().head_object(**head_kw)
    body = get_bytes(staging_bucket, key, version_id)
    sha = hashlib.sha256(body).hexdigest()
    manifest_key = f"_manifests/{ds}/{sha}.json"
    manifest = get_json(bronze_bucket, manifest_key)
    status = "duplicate"
    if manifest is None:
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        bronze = make_bronze(body, ts)
        if not round_trip_ok(body, bronze, ts):
            raise SelfTestError(f"CTO-01 round trip failed for {ds}/{sha[:8]}")
        bronze_key = f"{ds}/ingest_date={now:%Y-%m-%d}/{ds}__{now:%Y%m%dT%H%M%SZ}__{sha[:8]}.csv"
        put_bytes(bronze_bucket, bronze_key, bronze, "text/csv", once=True)
        header, recs = data_records(body)
        h = header[3:] if header and header.startswith(b"\xef\xbb\xbf") else header
        header_text = h.decode("utf-8", "replace") if h is not None else None
        manifest = {
            "dataset_id": ds, "source_bucket": staging_bucket, "source_key": key,
            "source_version_id": head.get("VersionId") if head.get("VersionId") not in (None, "null") else None,
            "size": head["ContentLength"], "etag": head["ETag"], "sha256": sha,
            "staging_last_modified": head["LastModified"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "record_count": len(split_records(body)), "data_row_count": len(recs),
            "header_as_received": header_text,
            "header_matches_registry": header_text == ",".join(cfg["datasets"][ds]["columns"]),
            "_ingested_at": ts, "first_run_id": run_id, "_rules_version": cfg["rules_version"],
            "control_totals": _control_totals(ds, body, cfg), "bronze_bucket": bronze_bucket,
            "bronze_key": bronze_key, "bronze_size": len(bronze),
            "bronze_sha256": hashlib.sha256(bronze).hexdigest(), "self_test": "CTO-01 passed",
        }
        if put_json(bronze_bucket, manifest_key, manifest, once=True):
            status = "ingested"
        else:  # lost a race with an identical delivery: the first manifest wins
            manifest = get_json(bronze_bucket, manifest_key)
    current_key = f"_current/{ds}.json"
    current = get_json(bronze_bucket, current_key)
    became_current = not current or current.get("sha256") != sha
    if became_current:
        put_json(bronze_bucket, current_key, {"dataset_id": ds, "sha256": sha, "manifest_key": manifest_key,
                                              "bronze_key": manifest["bronze_key"], "set_at": now_iso(),
                                              "run_id": run_id})
    put_json(bronze_bucket, f"_deliveries/{ds}/{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}__{sha[:8]}.json",
             {"dataset_id": ds, "source_key": key, "version_id": version_id, "sha256": sha, "status": status,
              "became_current": became_current, "run_id": run_id, "at": now_iso()}, once=True)
    log("bronze.ingest", dataset=ds, sha8=sha[:8], status=status, became_current=became_current,
        rows=manifest["data_row_count"])
    return {"dataset_id": ds, "source_key": key, "sha256": sha, "status": status,
            "bronze_key": manifest["bronze_key"], "rows": manifest["data_row_count"]}


def handler(event, context=None):
    """Called by the Glue job finora-dl-bronze-ingest. Step Functions passes the
    run_id and started_at it derived from the execution start time."""
    cfg = config.load()
    run_id, started = event.get("run_id") or new_run_id(), event.get("started_at") or now_iso()
    ingested = {}
    for key, version_id in _resolve_keys(event, os.environ["STAGING_BUCKET"], cfg):
        ds = config.dataset_for_key(cfg, key)
        if ds is None:
            log("bronze.not_a_dataset")  # outside the registered prefixes: not a dataset, nothing to load
            continue
        ingested[ds] = ingest(ds, key, version_id, run_id, cfg)
    return {"run_id": run_id, "started_at": started, "ingested": ingested}
