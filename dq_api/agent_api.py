"""Voice agent routes (contracts/agent_api_contract.md v1.1, docs/semantic_layer.md), Lambda finora-dq-agent.

- POST /api/agent-session        browser, dq_session cookie: signed URL + a 45-minute agent token
- GET  /api/agent/briefing       ElevenLabs webhook, Bearer agent token: the briefing of the last refresh
- POST /api/agent/ask            ElevenLabs webhook, Bearer agent token: question -> Kimi K3 query spec
                                 (tool use, never SQL) -> semantic-layer compiler -> Athena / DQ snapshot
- GET  /api/agent/results/{id}   browser, dq_session cookie: rows + chart, re-checked against the caller's role

Agent tokens are accepted only by the two webhook routes (authlib.agent_tokens); the cookie
routes never read Authorization. Rows never go to the agent. A separate Lambda from
finora-dq-api on purpose: only this role reads the ElevenLabs key, calls Bedrock and reads
the agent's gold objects.

Voice budget: the ElevenLabs credits are shared with el_toldo's production agents, so a
session starts only while the account keeps VOICE_CREDIT_FLOOR credits (503
voice_unavailable, reason budget), at most 6 sessions per user per hour and
VOICE_SESSIONS_PER_DAY in total.

Direct invocation (IAM lambda:InvokeFunction only, never reachable through API Gateway,
whose events always carry requestContext): {"source": "finora.voice-eval", "question",
"role", "previous_result_id"} runs the ask pipeline for the eval set and also returns
the spec. Used by scripts/voice_eval.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from agentlib import ask as A
from agentlib import catalog as C
from agentlib import compiler as K
from agentlib import context as CTX
from agentlib import elevenlabs
from agentlib import post as P
from authlib import agent_tokens, db
from authlib.http import ApiError, dispatch, json_response, parse_body, require_user, session_token

ROLES = set(C.ROLES)
RESULT_ID = re.compile(r"r_[0-9a-f]{24}")
BUDGET_S = 20.0           # the contract's "about 20 s"; API Gateway stops waiting at 30 s
RESULT_TTL_S = 24 * 3600
SESSIONS_PER_USER_PER_HOUR = 6
ASKS_PER_TOKEN_PER_15MIN = 40
WINDOW = 15 * 60

_s3 = None
_ddb = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def results_table():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
    return _ddb.Table(os.environ["AGENT_RESULTS_TABLE"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(event: str, **kw: Any) -> None:
    print(json.dumps({"event": event, **kw}, ensure_ascii=False, default=str))  # never a token, key or email


def _get_json(key: str) -> Any:
    try:
        body = s3().get_object(Bucket=os.environ["SERVING_BUCKET"], Key=key)["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404", "AccessDenied"):
            return None
        raise
    return json.loads(body)


def _cookie_user(event) -> dict:
    user = require_user(event)
    if user.get("role") not in ROLES:
        raise ApiError(403, "forbidden")
    return user


def _sessions_per_day() -> int:
    try:
        return int(os.environ.get("VOICE_SESSIONS_PER_DAY", "5"))
    except ValueError:
        return 5


# --------------------------------------------------------------------------- #
# POST /api/agent-session                                                     #
# --------------------------------------------------------------------------- #

def agent_session(event):
    user = _cookie_user(event)
    now = int(time.time())
    uid = hashlib.sha256(user["email"].encode()).hexdigest()[:16]
    if db.hit_bucket(f"agent-session#{uid}#{now // 3600}", SESSIONS_PER_USER_PER_HOUR, now + 7200):
        _log("agent.session_rate_limited", role=user["role"], scope="user")
        raise ApiError(429, "rate_limited", "Demasiadas sesiones de voz seguidas. Intenta más tarde.")
    agent_id = os.environ.get("ELEVENLABS_AGENT_ID", "")
    try:
        if not agent_id:
            raise elevenlabs.VoiceUnavailable("agent_not_configured")
        left = elevenlabs.check_budget()
        if db.hit_bucket(f"agent-session#all#{now // 86400}", _sessions_per_day(), now + 2 * 86400):
            raise elevenlabs.VoiceUnavailable("daily_cap")
        signed = elevenlabs.signed_url(agent_id)
    except elevenlabs.VoiceUnavailable as err:
        reason = "budget" if err.kind in ("budget", "daily_cap") else "unreachable"
        _log("agent.voice_unavailable", kind=err.kind, status=err.status)
        return json_response(503, {"error": {"code": "voice_unavailable", "message": "La voz no está disponible ahora",
                                             "reason": reason}})
    token, expires = agent_tokens.issue(user, session_token(event), now)
    pointer = _get_json("agent/briefing/latest.json") or {}
    as_of = pointer.get("as_of_month") or ""
    _log("agent.session_started", role=user["role"], credits_left=left)
    return json_response(200, {
        "signed_url": signed, "agent_id": agent_id, "agent_token": token,
        "expires_at": datetime.fromtimestamp(expires, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dynamic_variables": {"user_role": user["role"], "as_of_month": as_of}})


# --------------------------------------------------------------------------- #
# GET /api/agent/briefing                                                     #
# --------------------------------------------------------------------------- #

def _agent(event) -> dict:
    try:
        principal = agent_tokens.require_agent(event)
    except ApiError as err:
        if err.status == 401:  # presence only, never the value: shows whether CloudFront forwards the header
            hdrs = {str(k).lower() for k in (event.get("headers") or {})}
            _log("agent.unauthenticated", has_authorization="authorization" in hdrs,
                 well_formed=bool(agent_tokens.bearer(event)))
        raise
    if principal["role"] not in ROLES:
        raise ApiError(403, "forbidden")
    return principal


BRIEFING_FIELDS = ("as_of_month", "refreshed_at", "status", "facts", "definitions", "caveats", "gold_run_id",
                   "catalog_version")


def briefing(event):
    _agent(event)
    pointer = _get_json("agent/briefing/latest.json") or {}
    run_id = pointer.get("run_id")
    doc = _get_json(f"agent/briefing/{run_id}.json") if run_id and K.RUN_ID_RE.fullmatch(run_id) else None
    if not doc:
        raise ApiError(404, "no_briefing", "Todavía no hay un resumen publicado.")
    return json_response(200, {k: doc[k] for k in BRIEFING_FIELDS if k in doc})


# --------------------------------------------------------------------------- #
# Results store (DynamoDB finora-dq-agent-results, 24 h TTL)                  #
# --------------------------------------------------------------------------- #

def new_result_id() -> str:
    return "r_" + secrets.token_hex(12)


def put_result(item: dict) -> None:
    item = {**item, "pk": f"r#{item['result_id']}", "expires_at": int(time.time()) + RESULT_TTL_S}
    results_table().put_item(Item={k: v for k, v in item.items() if v is not None})


def get_result(result_id: str) -> dict | None:
    if not isinstance(result_id, str) or not RESULT_ID.fullmatch(result_id):
        return None
    got = results_table().get_item(Key={"pk": f"r#{result_id}"}).get("Item")
    if not got or int(got.get("expires_at") or 0) <= int(time.time()):
        return None
    return got


def update_result(result_id: str, fields: dict) -> None:
    fields = {k: v for k, v in fields.items() if v is not None}
    results_table().update_item(
        Key={"pk": f"r#{result_id}"}, UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
        ExpressionAttributeNames={f"#{k}": k for k in fields},
        ExpressionAttributeValues={f":{k}": v for k, v in fields.items()},
        ConditionExpression=Attr("pk").exists())


def cache_key(spec_hash: str, role: str, gold_run_id: str) -> str:
    """§2.3 rule 9: (spec_hash, role, gold_run_id), never the raw question."""
    return "c#" + hashlib.sha256(f"{spec_hash}|{role}|{gold_run_id}".encode()).hexdigest()


def get_cached(key: str) -> dict | None:
    got = results_table().get_item(Key={"pk": key}).get("Item")
    if not got or int(got.get("expires_at") or 0) <= int(time.time()):
        return None
    return get_result(str(got.get("result_id") or ""))


def put_cache(key: str, result_id: str) -> None:
    results_table().put_item(Item={"pk": key, "result_id": result_id, "expires_at": int(time.time()) + RESULT_TTL_S})


# --------------------------------------------------------------------------- #
# POST /api/agent/ask                                                         #
# --------------------------------------------------------------------------- #

def _base_reply(ctx: K.Context | None) -> dict:
    return {"catalog_version": C.VERSION, "gold_run_id": ctx.gold_run_id if ctx else None,
            "as_of_month": ctx.data_complete_through if ctx else None}


def reply_of(item: dict, ctx: K.Context | None) -> dict:
    """What the agent hears: summary, IDs, caveats, evidence. Never rows."""
    st = item["status"]
    out = {"status": st, "result_id": item.get("result_id"), "reason_code": item.get("reason_code"),
           **_base_reply(ctx)}
    if item.get("gold_run_id"):
        out["gold_run_id"] = item["gold_run_id"]
    if st == "answered":
        out.update({"summary_es": item.get("summary_es", ""), "evidence": item.get("evidence", "observado"),
                    "caveats_es": json.loads(item.get("caveats_es") or "[]"),
                    "kpi_ids": json.loads(item.get("kpi_ids") or "[]"),
                    "chart": {"type": item.get("chart_type", "table"), "title_es": item.get("title_es", "")}})
    elif st == "pending":
        out.update({"reason_es": "La consulta sigue corriendo. Llama de nuevo a ask con previous_result_id.",
                    "evidence": item.get("evidence"), "caveats_es": [], "kpi_ids": []})
    elif st == "out_of_scope":
        out.update({"reason_es": item.get("reason_es", ""), "alternative_es": item.get("alternative_es", ""),
                    "evidence": item.get("evidence", "observado"), "caveats_es": [], "kpi_ids": []})
    else:
        out.update({"reason_es": item.get("reason_es", ""), "caveats_es": [], "kpi_ids": []})
    return out


def _error(reason_es: str, ctx: K.Context | None = None) -> dict:
    return json_response(200, reply_of({"status": "error", "reason_es": reason_es}, ctx))


def ask(event):
    principal = _agent(event)
    body = parse_body(event)
    now = int(time.time())
    if db.hit_bucket(f"agent-ask#{principal['token_hash'][:24]}#{now // WINDOW}", ASKS_PER_TOKEN_PER_15MIN,
                     now + 2 * WINDOW):
        return _error("Hiciste muchas preguntas seguidas. Espera un momento y vuelve a intentarlo.")
    out = run_ask(A.clean_question(body.get("question")), principal["role"], body.get("previous_result_id"),
                  time.monotonic() + BUDGET_S)
    out.pop("_spec", None)
    return json_response(200, out)


def run_ask(question: str, role: str, prev_id: Any, deadline: float) -> dict:
    started = time.monotonic()
    prev_id = prev_id if isinstance(prev_id, str) and RESULT_ID.fullmatch(prev_id) else None
    if not question and not prev_id:
        raise ApiError(400, "bad_request", "Falta la pregunta.")
    try:
        ctx = CTX.load()
    except CTX.ContextUnavailable as err:
        _log("agent.context_unavailable", detail=str(err)[:200])
        return reply_of({"status": "error", "reason_es": "Los datos no están disponibles ahora."}, None)
    prev = get_result(prev_id) if prev_id else None
    if prev and role not in set(prev.get("allowed_roles") or []):
        prev = None  # a result of a role this caller cannot see is never used, not even as context
    if prev and prev.get("status") == "pending" and \
            (not question or A.normalize(question) == prev.get("question_norm")):
        item = finalize(prev, deadline)
        return {**reply_of(item, ctx), "_spec": json.loads(item.get("spec") or "null")}
    if not question:
        return reply_of({"status": "error", "reason_es": "No encontré esa consulta. ¿Puedes repetir la pregunta?"}, ctx)

    context_prev = prev if prev and prev.get("status") == "answered" else None
    outcome = A.plan(question, role, ctx, context_prev, deadline)
    base = {"question": question, "question_norm": A.normalize(question), "created_role": role,
            "gold_run_id": ctx.gold_run_id, "run_id": ctx.gold_run_id, "created_at": _now_iso()}
    if outcome.status == "error":
        _log("agent.ask_error", role=role, errors=outcome.errors[:3], kimi_calls=outcome.kimi_calls)
        return reply_of({"status": "error", "reason_es": outcome.reason_es}, ctx)
    sh = K.spec_hash(outcome.spec)
    ck = cache_key(sh, role, ctx.gold_run_id)
    cached = get_cached(ck)
    if cached and cached.get("status") in ("answered", "out_of_scope", "pending"):
        _log("agent.ask_cached", role=role, status=cached["status"], spec_hash=sh)
        if cached["status"] == "pending":
            cached = finalize(cached, deadline)
        return {**reply_of(cached, ctx), "_spec": outcome.spec}

    result_id = new_result_id()
    if outcome.status == "out_of_scope":
        def run_alt(comp):
            try:
                return A.run_sync(comp, ctx, min(deadline, time.monotonic() + 8), lambda: CTX.dq_snapshot(ctx))
            except A.AthenaError:
                return None
        pay = A.oos_payload(outcome, role, ctx, run_alt)
        item = {**base, "result_id": result_id, "status": "out_of_scope", "spec": json.dumps(outcome.spec),
                "spec_hash": sh, "allowed_roles": sorted(ROLES), **pay}
        put_result(item)
        put_cache(ck, result_id)
        _log("agent.ask_out_of_scope", role=role, reason_code=pay["reason_code"], question=base["question_norm"][:200],
             spec_hash=sh)  # the demand signal (§3): reason, normalized question, role; no rows
        return {**reply_of(item, ctx), "_spec": outcome.spec}

    comp = outcome.compiled
    item = {**base, "result_id": result_id, "status": "pending", "spec": json.dumps(outcome.spec, ensure_ascii=False),
            "spec_hash": sh, "sql_hash": comp.sql_hash, "title_es": comp.title_es, "chart_type": comp.chart_type,
            "evidence": comp.evidence, "allowed_roles": sorted(comp.allowed_roles), "kind": comp.kind}
    try:
        if comp.kind == "dq":
            table = A.run_sync(comp, ctx, deadline, lambda: CTX.dq_snapshot(ctx))
            put_result(item)
            item = _store_answer(item, comp, table, ctx)
        else:
            item["qid"] = A.start_query(comp)
            put_result(item)
            item = finalize(item, deadline, comp=comp, ctx=ctx)
    except A.AthenaError as err:
        _log("agent.athena_start_failed", kind=err.kind)
        return reply_of({"status": "error", "reason_es": "El motor de consultas no respondió. Intenta de nuevo."}, ctx)
    put_cache(ck, result_id)
    _log("agent.ask", role=role, status=item["status"], source=comp.source, spec_hash=sh, sql_hash=comp.sql_hash,
         run=ctx.gold_run_id, kimi_calls=outcome.kimi_calls, ms=int((time.monotonic() - started) * 1000))
    return {**reply_of(item, ctx), "_spec": outcome.spec}


def _store_answer(item: dict, comp: K.Compiled, table: P.Table, ctx: K.Context) -> dict:
    pay = A.answer_payload(comp, table, ctx)
    fields = {"status": "answered", "rows": json.dumps(table.rows, ensure_ascii=False),
              "columns": json.dumps(table.columns), "chart": json.dumps(table.chart, ensure_ascii=False),
              "column_labels_es": json.dumps(column_labels(comp, table), ensure_ascii=False),
              "summary_es": pay["summary_es"], "summary_source": pay["summary_source"],
              "caveats_es": json.dumps(pay["caveats_es"], ensure_ascii=False), "kpi_ids": json.dumps(pay["kpi_ids"]),
              "evidence": pay["evidence"], "finished_at": _now_iso()}
    update_result(item["result_id"], fields)
    return {**item, **fields}


def finalize(item: dict, deadline: float, comp: K.Compiled | None = None, ctx: K.Context | None = None) -> dict:
    """Wait for a pending result's Athena query until `deadline`; on success store the
    rows and the checked summary. A pending item is recompiled from its stored spec
    and role against its own gold run (deterministic)."""
    if item.get("status") != "pending" or not item.get("qid"):
        return item
    state = A.wait_query(item["qid"], deadline)
    if state == "RUNNING":
        return item
    if state != "SUCCEEDED":
        fields = {"status": "error", "reason_es": "La consulta no pudo completarse. Intenta reformular la pregunta."}
        update_result(item["result_id"], fields)
        return {**item, **fields}
    try:
        ctx = ctx or CTX.load(item.get("gold_run_id"))
        comp = comp or K.compile_spec(K.validate(json.loads(item["spec"])), item["created_role"], ctx)
    except (K.CompileError, K.OutOfScope, CTX.ContextUnavailable):
        fields = {"status": "error", "reason_es": "La consulta ya no es válida. Pregunta de nuevo."}
        update_result(item["result_id"], fields)
        return {**item, **fields}
    header, rows = A.fetch_rows(item["qid"])
    return _store_answer(item, comp, P.to_table(comp, header, rows), ctx)


def column_labels(comp: K.Compiled, table: P.Table) -> dict:
    out = {}
    for c in table.columns:
        m = table.meta.get(c, {})
        if m.get("dim"):
            out[c] = C.DIMENSIONS.get(m["dim"], {"method": "método", "metric": "métrica", "run": "corrida"}.get(
                m["dim"], m["dim"])).capitalize()
        elif m.get("metric") in C.METRICS:
            name = C.METRICS[m["metric"]].name_es
            role = m.get("role")
            out[c] = {"from": f"{name} ({m.get('period', '')})", "to": f"{name} ({m.get('period', '')})",
                      "change": "Cambio", "change_pct": "Cambio %", "share": "% del total",
                      "ratio": "Razón"}.get(role, name[:1].upper() + name[1:]) if role or m.get("main") else \
                _aux_label(c)
        else:
            out[c] = _aux_label(c)
    return out


def _aux_label(col: str) -> str:
    return {"customers": "Clientes", "is_small_cell": "Menos de 5 clientes", "is_low_n": "Pocos casos",
            "base": "Base", "scenario": "Escenario", "rule_title": "Título de la regla",
            "status": "Estado", "as_of_month": "Datos hasta", "run_id": "Corrida"}.get(
        col, col.replace("_value", "").replace("_", " ").capitalize())


# --------------------------------------------------------------------------- #
# GET /api/agent/results/{result_id}                                          #
# --------------------------------------------------------------------------- #

def result(event):
    user = _cookie_user(event)
    rid = (event.get("pathParameters") or {}).get("result_id", "")
    item = get_result(rid)
    if not item or item.get("status") not in ("answered", "pending"):
        raise ApiError(404, "not_found", "Unknown result.")
    if user["role"] not in set(item.get("allowed_roles") or []):
        _log("agent.result_forbidden", role=user["role"])
        raise ApiError(403, "forbidden")
    if item["status"] == "pending":
        item = finalize(item, time.monotonic() + 8.0)
        if item["status"] == "pending":
            return json_response(202, {"result_id": rid, "status": "pending"})
        if item["status"] != "answered":
            raise ApiError(404, "not_found", "Unknown result.")
    return json_response(200, {
        "result_id": rid, "question": item.get("question", ""), "title_es": item.get("title_es", ""),
        "chart": json.loads(item.get("chart") or "{}"), "columns": json.loads(item.get("columns") or "[]"),
        "column_labels_es": json.loads(item.get("column_labels_es") or "{}"),
        "rows": json.loads(item.get("rows") or "[]"), "evidence": item.get("evidence", "observado"),
        "caveats_es": json.loads(item.get("caveats_es") or "[]"), "sql_hash": item.get("sql_hash", ""),
        "run_id": item.get("run_id", ""), "created_at": item.get("created_at", "")})


ROUTES = {
    "POST /api/agent-session": agent_session,
    "GET /api/agent/briefing": briefing,
    "POST /api/agent/ask": ask,
    "GET /api/agent/results/{result_id}": result,
}


def handler(event, context):
    if isinstance(event, dict) and event.get("source") == "finora.voice-eval" and \
            "requestContext" not in event and "routeKey" not in event:
        return _eval(event)
    return dispatch(ROUTES, event)


def _eval(event: dict) -> dict:
    """IAM-only (direct invoke): one eval question as `role`, with the spec for scoring."""
    role = event.get("role")
    if role not in ROLES:
        return {"error": "role"}
    try:
        out = run_ask(A.clean_question(event.get("question")), role, event.get("previous_result_id"),
                      time.monotonic() + BUDGET_S)
    except ApiError as err:
        return {"error": err.code}
    out["spec"] = out.pop("_spec", None)
    _log("agent.eval", role=role, status=out.get("status"))
    return out
