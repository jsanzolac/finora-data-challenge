"""DQ API Lambda: /api/dq/* over the serving snapshots (contracts/dq_api_contract.md).

Every route needs a live session (401) and a changed password (403
password_change_required). HR-sensitive S&M columns are masked as
`__restricted__` for every role except finance (CDO-11); search runs on the
masked record so a restricted value can never be probed.
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import boto3
from botocore.exceptions import ClientError

from authlib.http import ApiError, dispatch, json_response, require_user

ROLES = {"data", "finance", "revops"}
HR_COLUMNS = {"Team", "PayrollExpenses", "Freelance"}
HR_ROLES = {"finance"}
RESTRICTED = "__restricted__"
STAGE_A = {"CDO-01", "SQ-01"}
RUN_ID = re.compile(r"r[0-9]{8}T[0-9]{6}Z")
RULE_ID = re.compile(r"[A-Z]{2,3}-[0-9]{2}[ab]?")
DATASETS = {"transactions", "industry", "sm_spend"}
MAX_PAGE_SIZE = 200
STORED_PAGE = 200

_s3 = None
_cache: dict[str, Any] = {}  # published runs are immutable, so their files cache safely


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _get(key: str, immutable: bool = False) -> Any:
    if immutable and key in _cache:
        return _cache[key]
    try:
        body = s3().get_object(Bucket=os.environ["SERVING_BUCKET"], Key=key)["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404", "AccessDenied"):
            return None
        raise
    val = json.loads(body)
    if immutable:
        _cache[key] = val
    return val


def _user(event) -> dict:
    user = require_user(event)
    if user.get("role") not in ROLES:
        raise ApiError(403, "forbidden")
    return user


def _resolve_run(event) -> str:
    run = ((event.get("queryStringParameters") or {}).get("run") or "latest").strip()
    if run == "latest":
        latest = _get("dq/latest.json")
        if not latest:
            raise ApiError(404, "not_found", "No published run yet.")
        return latest["run_id"]
    if not RUN_ID.fullmatch(run):
        raise ApiError(404, "not_found", "Unknown run.")
    return run


def runs(event):
    _user(event)
    return json_response(200, _get("dq/runs.json") or [])


def summary(event):
    _user(event)
    run_id = _resolve_run(event)
    s = _get(f"dq/runs/{run_id}/summary.json", immutable=True)
    if not s:
        raise ApiError(404, "not_found", "Unknown run.")
    return json_response(200, s)


def mask(record: dict, dataset_id: str, rule_id: str, role: str) -> dict:
    if dataset_id != "sm_spend" or role in HR_ROLES:
        return record
    out = dict(record)
    stage_a = rule_id in STAGE_A or any(r in STAGE_A for r in record.get("other_failed_rules", []))
    if stage_a:  # no trusted positions: every value is restricted
        out["values"] = {c: RESTRICTED for c in record.get("values", {})}
        out["key"] = {c: RESTRICTED for c in record.get("key", {})}
    else:
        out["values"] = {c: (RESTRICTED if c in HR_COLUMNS else v) for c, v in record.get("values", {}).items()}
    return out


def _matches(record: dict, q: str) -> bool:
    hay = [*map(str, record.get("key", {}).values()), *map(str, record.get("values", {}).values()),
           record.get("reason", "")]
    return any(q in h.casefold() for h in hay)


def _int(params: dict, name: str, default: int) -> int:
    try:
        return int(params.get(name) or default)
    except (TypeError, ValueError):
        raise ApiError(400, "bad_request", f"{name} must be an integer") from None


def records(event):
    user = _user(event)
    pp = event.get("pathParameters") or {}
    rule_id, dataset_id = pp.get("rule_id", ""), pp.get("dataset_id", "")
    if not RULE_ID.fullmatch(rule_id) or dataset_id not in DATASETS:
        raise ApiError(404, "not_found", "Unknown rule or dataset.")
    run_id = _resolve_run(event)
    params = event.get("queryStringParameters") or {}
    page = max(1, _int(params, "page", 1))
    page_size = min(MAX_PAGE_SIZE, max(1, _int(params, "page_size", 50)))
    q = (params.get("q") or "").strip().casefold()
    base = f"dq/runs/{run_id}/records/{rule_id}/{dataset_id}"
    first = _get(f"{base}/page-1.json", immutable=True)
    if not first:
        if not _get(f"dq/runs/{run_id}/summary.json", immutable=True):
            raise ApiError(404, "not_found", "Unknown run.")
        raise ApiError(404, "not_found", "Unknown rule or dataset.")
    role = user["role"]
    if q:
        n = first["page_count"]
        with ThreadPoolExecutor(max_workers=16) as pool:
            pages = [first] + list(pool.map(lambda i: _get(f"{base}/page-{i}.json", True), range(2, n + 1)))
        allrecs = [mask(r, dataset_id, rule_id, role) for pg in pages if pg for r in pg["records"]]
        hits = [r for r in allrecs if _matches(r, q)]
        total, chunk = len(hits), hits[(page - 1) * page_size: page * page_size]
    else:
        total = first["total"]
        lo, hi = (page - 1) * page_size, min(page * page_size, total)
        chunk = []
        if lo < total:
            for sp in range(lo // STORED_PAGE + 1, (hi - 1) // STORED_PAGE + 2):
                pg = first if sp == 1 else _get(f"{base}/page-{sp}.json", immutable=True)
                start = (sp - 1) * STORED_PAGE
                for i, r in enumerate(pg["records"] if pg else []):
                    if lo <= start + i < hi:
                        chunk.append(r)
        chunk = [mask(r, dataset_id, rule_id, role) for r in chunk]
    return json_response(200, {"rule_id": rule_id, "dataset_id": dataset_id, "run_id": run_id, "total": total,
                               "page": page, "page_size": page_size, "columns": first["columns"],
                               "records": chunk})


ROUTES = {
    "GET /api/dq/runs": runs,
    "GET /api/dq/summary": summary,
    "GET /api/dq/rules/{rule_id}/datasets/{dataset_id}/records": records,
}


def handler(event, context):
    return dispatch(ROUTES, event)
