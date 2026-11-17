"""MRR API: /api/mrr/* (contracts/mrr_api_contract.md v1, "v1 decisions").

- GET /api/mrr/summary?run=latest|<run_id>      mrr/latest.json -> mrr/runs/<run_id>/summary.json
- GET /api/mrr/movements?from=&to=&run=&step=&driver=&sort=&page=&page_size=
      Filters, sorts and pages the stored rows mrr/runs/<run_id>/movements/page-<n>.json
      (every non-zero movement, |change| descending, 200 per page). step and driver may
      repeat; valid codes come from the run's own summary (metadata-driven steps).

All three roles, nothing masked (no HR data). 401 / 403 password_change_required as
every route; 404 no_gold_run before the first publish, unknown_run for an unknown id;
400 invalid_query with error.details [{check, field, message}].
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs

import boto3
from botocore.exceptions import ClientError

from authlib.http import ApiError, json_response, require_user

ROLES = {"data", "finance", "revops"}
RUN_ID = re.compile(r"r[0-9]{8}T[0-9]{6}Z")
MONTH = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")
SORTS = ("abs_desc", "asc", "desc")
MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50

_s3 = None
_cache: dict[str, Any] = {}  # published runs are immutable


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


def _params(event) -> dict[str, list[str]]:
    """Query parameters with repeats. HTTP API (payload 2.0) joins repeats with commas in
    queryStringParameters; rawQueryString keeps them apart."""
    raw = event.get("rawQueryString")
    if raw:
        return {k: v for k, v in parse_qs(raw, keep_blank_values=True).items()}
    return {k: (v.split(",") if isinstance(v, str) else [str(v)])
            for k, v in (event.get("queryStringParameters") or {}).items()}


def _resolve(run: str) -> tuple[str, dict]:
    run = (run or "latest").strip()
    if run == "latest":
        latest = _get("mrr/latest.json")
        if not latest:
            raise ApiError(404, "no_gold_run", "No MRR data has been published yet.")
        run = latest["run_id"]
    elif not RUN_ID.fullmatch(run):
        raise ApiError(404, "unknown_run", "Unknown run.")
    payload = _get(f"mrr/runs/{run}/summary.json", immutable=True)
    if not payload:
        raise ApiError(404, "unknown_run", "Unknown run.")
    return run, payload


def summary(event):
    _user(event)
    run = (_params(event).get("run") or ["latest"])[0]
    _, payload = _resolve(run)
    return json_response(200, payload)


def _invalid(details: list[dict]):
    return json_response(400, {"error": {"code": "invalid_query", "message": "The query is not valid.",
                                         "details": details}})


def _rows(run_id: str) -> list[dict]:
    first = _get(f"mrr/runs/{run_id}/movements/page-1.json", immutable=True)
    if not first:
        return []
    n = int(first.get("pages") or 1)
    with ThreadPoolExecutor(max_workers=16) as pool:
        rest = list(pool.map(lambda i: _get(f"mrr/runs/{run_id}/movements/page-{i}.json", True), range(2, n + 1)))
    if any(p is None for p in rest):
        raise ApiError(500, "internal")
    return [r for p in [first] + rest for r in p["movements"]]


def movements(event):
    _user(event)
    q = _params(event)
    det: list[dict] = []

    def one(name: str) -> str | None:
        v = q.get(name) or []
        if len(v) > 1:
            det.append({"check": "single_value", "field": name, "message": f"{name} may appear only once."})
        return v[0].strip() if v else None

    run = one("run") or "latest"
    lo, hi = one("from"), one("to")
    sort = one("sort") or "abs_desc"
    page_s, size_s = one("page"), one("page_size")
    for name, v in (("from", lo), ("to", hi)):
        if v is not None and v != "" and not MONTH.fullmatch(v):
            det.append({"check": "month_format", "field": name, "message": f"{name} must be YYYY-MM."})
    lo, hi = lo or None, hi or None
    if lo and hi and MONTH.fullmatch(lo) and MONTH.fullmatch(hi) and lo > hi:
        det.append({"check": "month_range", "field": "from", "message": "from must not be after to."})
    if sort not in SORTS:
        det.append({"check": "sort", "field": "sort", "message": f"sort must be one of {', '.join(SORTS)}."})
    page = size = None
    for name, v, lo_b, hi_b, default in (("page", page_s, 1, None, 1),
                                         ("page_size", size_s, 1, MAX_PAGE_SIZE, DEFAULT_PAGE_SIZE)):
        if v is None or v == "":
            val = default
        elif not re.fullmatch(r"[0-9]{1,6}", v) or int(v) < lo_b or (hi_b is not None and int(v) > hi_b):
            det.append({"check": "paging", "field": name,
                        "message": f"{name} must be an integer >= {lo_b}" + (f" and <= {hi_b}." if hi_b else ".")})
            continue
        else:
            val = int(v)
        if name == "page":
            page = val
        else:
            size = val
    steps = [s.strip() for s in q.get("step", []) if s.strip()]
    drivers = [d.strip() for d in q.get("driver", []) if d.strip()]
    if det:
        return _invalid(det)
    run_id, payload = _resolve(run)
    known_steps = {s["code"] for s in payload.get("steps", [])}
    known_drivers = {d["code"] for d in payload.get("drivers", [])}
    bad = [{"check": "unknown_code", "field": "step", "message": f"Unknown step {s[:40]!r}."}
           for s in steps if s not in known_steps]
    bad += [{"check": "unknown_code", "field": "driver", "message": f"Unknown driver {d[:40]!r}."}
            for d in drivers if d not in known_drivers]
    if bad:
        return _invalid(bad)
    rows = _rows(run_id)
    sel = [r for r in rows
           if (lo is None or r["month"] >= lo) and (hi is None or r["month"] <= hi)
           and (not steps or r["step"] in steps) and (not drivers or r["driver"] in drivers)]
    if sort != "abs_desc":  # stored order is |change| descending; sorted() is stable on it
        sel = sorted(sel, key=lambda r: Decimal(r["change_value"]), reverse=(sort == "desc"))
    chunk = sel[(page - 1) * size: page * size]
    return json_response(200, {"run_id": run_id, "total": len(sel), "page": page, "page_size": size,
                               "sort": sort, "movements": chunk})


ROUTES = {
    "GET /api/mrr/summary": summary,
    "GET /api/mrr/movements": movements,
}
