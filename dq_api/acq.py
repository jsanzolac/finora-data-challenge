"""Acquisition API: /api/acq/* (contracts/acq_api_contract.md v1.1).

- GET  /api/acq/summary    the gold job's serving snapshot; HR spend categories
                           are "__restricted__" for every role except finance.
- GET  /api/acq/scenarios  live from Athena (v_funnel_rate_current + v_funnel_scenario_status).
- POST /api/acq/scenarios  finance and revops only. Validates GR-01..GR-06 first,
                           then appends rows with one Athena INSERT (never UPDATE
                           or DELETE). changed_by = dashboard:<first 12 hex of
                           SHA-256(email)>, never the email.

SQL is built from strictly validated values only: the scenario id matches its
pattern, stage codes come from a fixed list, rates are re-rendered from a
Decimal, and free text is a Trino string literal (quotes doubled, control
characters refused).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import boto3
from botocore.exceptions import ClientError

from authlib.http import ApiError, json_response, require_user

ROLES = {"data", "finance", "revops"}
EDIT_ROLES = {"finance", "revops"}
HR_ROLES = {"finance"}
RESTRICTED = "__restricted__"
RUN_ID = re.compile(r"r[0-9]{8}T[0-9]{6}Z")
SCENARIO_ID = re.compile(r"[a-z][a-z0-9_]{0,39}")
RATE_TEXT = re.compile(r"[0-9]+(\.[0-9]+)?")
STAGES = ["NEW", "WORKING", "ENGAGED", "SQL", "DEMO", "PROPOSAL", "WON"]
TRANSITIONS = list(zip(STAGES, STAGES[1:]))
LABEL_MAX, REASON_MAX = 200, 500
BUDGET_S = 25.0
POLL_S = 0.25

_s3 = None
_athena = None
_cache: dict[str, Any] = {}


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def athena():
    global _athena
    if _athena is None:
        _athena = boto3.client("athena")
    return _athena


def _db() -> str:
    return os.environ.get("GOLD_DATABASE", "finora_gold")


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


# --------------------------------------------------------------------------- #
# GET /api/acq/summary                                                        #
# --------------------------------------------------------------------------- #

def mask(payload: dict, role: str) -> dict:
    """HR categories (and any category the payload does not declare as shared)
    become "__restricted__" for non-finance roles."""
    if role in HR_ROLES:
        return payload
    out = copy.deepcopy(payload)
    shared = {c["code"] for c in out.get("spend_categories", []) if c.get("hr_sensitive") is False}
    for m in out.get("months", []):
        sv = m.get("spend_value") or {}
        m["spend_value"] = {k: (v if k in shared else RESTRICTED) for k, v in sv.items()}
    return out


def summary(event):
    user = _user(event)
    run = ((event.get("queryStringParameters") or {}).get("run") or "latest").strip()
    if run == "latest":
        latest = _get("acq/latest.json")
        if not latest:
            raise ApiError(404, "no_gold_run", "No acquisition data has been published yet.")
        run = latest["run_id"]
    elif not RUN_ID.fullmatch(run):
        raise ApiError(404, "unknown_run", "Unknown run.")
    payload = _get(f"acq/runs/{run}/summary.json", immutable=True)
    if not payload:
        raise ApiError(404, "unknown_run", "Unknown run.")
    return json_response(200, mask(payload, user["role"]))


# --------------------------------------------------------------------------- #
# Athena                                                                      #
# --------------------------------------------------------------------------- #

def run_query(sql: str, deadline: float) -> list[dict[str, str | None]]:
    """Run one statement in the finora-dl workgroup and return its rows as strings."""
    try:
        qid = athena().start_query_execution(
            QueryString=sql, WorkGroup=os.environ.get("ATHENA_WORKGROUP", "finora-dl"),
            QueryExecutionContext={"Database": _db()})["QueryExecutionId"]
        while True:
            st = athena().get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
            if st["State"] == "SUCCEEDED":
                break
            if st["State"] in ("FAILED", "CANCELLED"):
                print(json.dumps({"event": "athena_failed", "state": st["State"],
                                  "reason": (st.get("StateChangeReason") or "")[:300]}))
                raise ApiError(502, "athena_failed", "The query engine could not complete the request.")
            if time.monotonic() > deadline:
                raise ApiError(504, "upstream_timeout", "The query engine did not answer in time. Try again.")
            time.sleep(POLL_S)
        rows: list[list[str | None]] = []
        token = None
        while True:
            kw = {"QueryExecutionId": qid, "MaxResults": 1000}
            if token:
                kw["NextToken"] = token
            res = athena().get_query_results(**kw)
            rows += [[c.get("VarCharValue") for c in r["Data"]] for r in res["ResultSet"]["Rows"]]
            token = res.get("NextToken")
            if not token:
                break
    except ClientError as e:
        print(json.dumps({"event": "athena_error", "code": e.response["Error"]["Code"]}))
        raise ApiError(502, "athena_failed", "The query engine could not complete the request.") from None
    if not rows or sql.lstrip().upper().startswith("INSERT"):
        return []
    header = rows[0]
    return [dict(zip(header, r)) for r in rows[1:]]


def scenario_sql(scenario_id: str | None = None) -> str:
    db = _db()
    where = ""
    if scenario_id is not None:
        if not SCENARIO_ID.fullmatch(scenario_id):
            raise ValueError("invalid scenario id")
        where = f"\nWHERE s.scenario_id = '{scenario_id}'"
    return (f"SELECT s.scenario_id, s.scenario_label, s.status, s.failed_checks,\n"
            f"  CAST(s.latest_changed_at AS VARCHAR) AS latest_changed_at, s.latest_changed_by, s.latest_change_reason,\n"
            f"  c.from_stage_code, c.to_stage_code, CAST(c.rate AS VARCHAR) AS rate\n"
            f"FROM {db}.v_funnel_scenario_status s\n"
            f"JOIN {db}.v_funnel_rate_current c ON c.scenario_id = s.scenario_id{where}")


def _iso(ts: str | None) -> str | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace(" ", "T")[:19]).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def scenarios_from_rows(rows: list[dict]) -> list[dict]:
    by: dict[str, dict] = {}
    for r in rows:
        sid = r["scenario_id"]
        s = by.setdefault(sid, {
            "scenario_id": sid, "label": r["scenario_label"], "status": r["status"],
            "failed_checks": [c for c in (r["failed_checks"] or "").split(",") if c],
            "rates": [], "changed_at": _iso(r["latest_changed_at"]), "changed_by": r["latest_changed_by"],
            "change_reason": r["latest_change_reason"]})
        s["rates"].append({"from_stage": r["from_stage_code"], "to_stage": r["to_stage_code"], "rate": r["rate"]})
    order = {s: i for i, s in enumerate(STAGES)}
    for s in by.values():
        s["rates"].sort(key=lambda x: (order.get(x["from_stage"], len(STAGES)), x["from_stage"] or ""))
    return sorted(by.values(), key=lambda s: (s["scenario_id"] != "base", s["scenario_id"]))


def scenarios(event):
    user = _user(event)
    rows = run_query(scenario_sql(), time.monotonic() + BUDGET_S)
    return json_response(200, {"can_edit": user["role"] in EDIT_ROLES, "scenarios": scenarios_from_rows(rows)})


# --------------------------------------------------------------------------- #
# POST /api/acq/scenarios                                                     #
# --------------------------------------------------------------------------- #

def _text_ok(s: str) -> bool:
    return not any(ord(ch) < 32 or 127 <= ord(ch) < 160 or ch in "  " for ch in s)


def _d(check: str, field: str, message: str) -> dict:
    return {"check": check, "field": field, "message": message}


def validate(body: Any) -> tuple[dict | None, list[dict]]:
    """Returns (clean request, details). details lists every failed check as
    {check, field, message} (contract v1.1)."""
    det: list[dict] = []
    if not isinstance(body, dict):
        return None, [_d("GR-01", "scenario_id", "The request body must be a JSON object.")]
    sid = body.get("scenario_id")
    if not isinstance(sid, str) or not SCENARIO_ID.fullmatch(sid):
        det.append(_d("GR-01", "scenario_id", "scenario_id must match ^[a-z][a-z0-9_]{0,39}$."))
    for field, check, limit in (("label", "LABEL_LENGTH", LABEL_MAX), ("change_reason", "REASON_LENGTH", REASON_MAX)):
        v = body.get(field)
        if not isinstance(v, str) or not v.strip() or len(v) > limit:
            det.append(_d(check, field, f"{field} must have 1 to {limit} characters."))
        elif not _text_ok(v):
            det.append(_d("GR-06", field, f"{field} must not contain control characters."))
    rates = body.get("rates")
    clean: dict[str, Decimal] = {}
    if not isinstance(rates, list) or len(rates) != len(TRANSITIONS) or not all(isinstance(r, dict) for r in rates):
        det.append(_d("GR-04", "rates", "rates must list exactly the 6 transitions, one per stage."))
    else:
        seen = set()
        pairs = set(TRANSITIONS)
        for r in rates:
            f, t = r.get("from_stage"), r.get("to_stage")
            if (f, t) not in pairs:
                det.append(_d("GR-02", "rates", f"{str(f)[:20]} -> {str(t)[:20]} is not a consecutive stage pair."))
                continue
            if f in seen:
                det.append(_d("GR-04", "rates", f"{f} -> {t} appears more than once."))
                continue
            seen.add(f)
            v = r.get("rate")
            try:
                d = Decimal(v) if isinstance(v, str) and RATE_TEXT.fullmatch(v) else None
            except InvalidOperation:
                d = None
            if d is None or not (Decimal(0) < d <= Decimal(1)) or -d.as_tuple().exponent > 4:
                det.append(_d("GR-03", "rates",
                              f"{f} -> {t}: the rate must be a decimal string, 0 < rate <= 1, at most 4 decimals."))
                continue
            clean[f] = d.quantize(Decimal("0.0001"))
        if len(seen) != len(TRANSITIONS) and not any(x["check"] == "GR-04" for x in det):
            det.append(_d("GR-04", "rates", "rates must list exactly the 6 transitions, one per stage."))
    if det:
        return None, det
    return {"scenario_id": sid, "label": body["label"].strip(), "change_reason": body["change_reason"].strip(),
            "rates": clean}, []


def sql_string(s: str) -> str:
    if not _text_ok(s):
        raise ValueError("control characters are not allowed in a SQL literal")
    return "'" + s.replace("'", "''") + "'"


def changed_by(email: str) -> str:
    return "dashboard:" + hashlib.sha256(email.encode("utf-8")).hexdigest()[:12]


def insert_sql(req: dict, froms: list[str], by: str) -> str:
    to = dict(TRANSITIONS)
    vals = []
    for f in froms:
        rate = req["rates"][f]
        assert f in to and Decimal(0) < rate <= 1 and SCENARIO_ID.fullmatch(req["scenario_id"])
        vals.append(f"('{req['scenario_id']}', {sql_string(req['label'])}, '{f}', '{to[f]}', "
                    f"CAST('{rate:.4f}' AS DECIMAL(5,4)), CAST(current_timestamp AT TIME ZONE 'UTC' AS timestamp(6)), "
                    f"{sql_string(by)}, {sql_string(req['change_reason'])})")
    return (f"INSERT INTO {_db()}.funnel_conversion_rate "
            "(scenario_id, scenario_label, from_stage_code, to_stage_code, rate, changed_at, changed_by, change_reason)\n"
            "VALUES\n" + ",\n".join(vals))


def create_scenario(event):
    user = _user(event)
    if user["role"] not in EDIT_ROLES:
        raise ApiError(403, "role_not_allowed", "Your role can view scenarios but not change them.")
    raw = event.get("body")
    if event.get("isBase64Encoded") and raw:
        import base64
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        body = json.loads(raw or "")
    except (ValueError, TypeError):
        body = None
    req, det = validate(body)
    if det:
        return json_response(400, {"error": {"code": "invalid_scenario", "message": "The scenario is not valid.",
                                             "details": det}})
    deadline = time.monotonic() + BUDGET_S
    current = scenarios_from_rows(run_query(scenario_sql(req["scenario_id"]), deadline))
    cur = current[0] if current else None
    if cur is None or cur["status"] != "valid":
        froms = [f for f, _ in TRANSITIONS]  # a new scenario, or a fix of an invalid one: all six rows
    else:
        have = {r["from_stage"]: Decimal(r["rate"]) for r in cur["rates"] if r["rate"] is not None}
        froms = [f for f, _ in TRANSITIONS if have.get(f) != req["rates"][f]]
    if not froms:
        raise ApiError(400, "no_change", "No rate differs from the scenario's current rates.")
    run_query(insert_sql(req, froms, changed_by(user["email"])), deadline)
    after = scenarios_from_rows(run_query(scenario_sql(req["scenario_id"]), deadline))
    print(json.dumps({"event": "acq.scenario_appended", "scenario_id": req["scenario_id"], "rows": len(froms),
                      "role": user["role"]}))
    return json_response(201, after[0] if after else {"scenario_id": req["scenario_id"]})


ROUTES = {
    "GET /api/acq/summary": summary,
    "GET /api/acq/scenarios": scenarios,
    "POST /api/acq/scenarios": create_scenario,
}
