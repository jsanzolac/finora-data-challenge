"""Voice agent routes (contracts/agent_api_contract.md v1.1): agent token issue and
validation, cookie vs bearer separation, 401/403/404/503, the credit floor, and the
results role re-check. ElevenLabs, Bedrock and Athena are stubbed; DynamoDB and S3 are moto."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import boto3
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "auth" / "tests"))
sys.path.insert(0, str(ROOT / "voice"))
from helpers import body_of, ev, load_auth, token_of  # noqa: E402

import agent_api  # noqa: E402
from agentlib import elevenlabs  # noqa: E402
from authlib import agent_tokens, db, passwords, sessions  # noqa: E402

auth = load_auth()
PW = "a-long-enough-password"


@pytest.fixture(autouse=True)
def tables(monkeypatch):
    monkeypatch.setenv("AGENT_TOKENS_TABLE", "agent_tokens")
    monkeypatch.setenv("AGENT_RESULTS_TABLE", "agent_results")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent_test")
    ddb = boto3.client("dynamodb")
    for name, key in (("agent_tokens", "token_hash"), ("agent_results", "pk")):
        ddb.create_table(TableName=name, BillingMode="PAY_PER_REQUEST",
                         KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
                         AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}])
    agent_api._s3 = None
    agent_api._ddb = None
    monkeypatch.setattr(elevenlabs, "remaining_credits", lambda timeout=4.0: 7554)
    monkeypatch.setattr(elevenlabs, "signed_url", lambda agent_id, timeout=6.0: "wss://example.invalid/signed")


def user(email="ana@example.com", role="revops", must_change=False):
    db.put_user(email, passwords.hash_password(PW), role, must_change_password=must_change)
    r = auth.handler(ev("POST /api/auth/login", {"email": email, "password": PW}), None)
    return token_of(r)


def session(cookie):
    return agent_api.handler(ev("POST /api/agent-session", cookie=cookie), None)


def bearer(route, token, body=None):
    e = ev(route, body)
    e["headers"]["authorization"] = f"Bearer {token}"
    return agent_api.handler(e, None)


def test_session_issues_a_hashed_45_minute_token():
    r = session(user())
    assert r["statusCode"] == 200, r
    b = body_of(r)
    assert b["signed_url"].startswith("wss://") and b["agent_id"] == "agent_test"
    assert b["dynamic_variables"]["user_role"] == "revops"
    tok = b["agent_token"]
    row = db.get_agent_token(sessions.hash_token(tok))
    assert row and tok not in json.dumps(row, default=str)  # only the hash is stored
    assert 44 * 60 < int(row["expires_at"]) - time.time() <= 45 * 60
    assert row["role"] == "revops" and row["scope"] == "agent:read"


def test_session_needs_a_cookie_and_a_changed_password():
    assert session(None)["statusCode"] == 401
    assert session(user("b@example.com", must_change=True))["statusCode"] == 403


def test_voice_unavailable_below_the_credit_floor_or_without_agent(monkeypatch):
    cookie = user()
    monkeypatch.setattr(elevenlabs, "remaining_credits", lambda timeout=4.0: 5999)
    r = session(cookie)
    assert r["statusCode"] == 503 and body_of(r)["error"]["reason"] == "budget"
    assert db.get_agent_token("x") is None
    monkeypatch.setattr(elevenlabs, "remaining_credits", lambda timeout=4.0: 9000)
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "")
    assert session(cookie)["statusCode"] == 503


def test_daily_cap(monkeypatch):
    monkeypatch.setenv("VOICE_SESSIONS_PER_DAY", "2")
    cookies = [user(f"u{i}@example.com") for i in range(3)]
    assert [session(c)["statusCode"] for c in cookies] == [200, 200, 503]


def test_agent_token_only_on_webhook_routes_and_cookie_never_on_them(monkeypatch):
    cookie = user()
    tok = body_of(session(cookie))["agent_token"]
    boto3.client("s3").put_object(Bucket="serving", Key="agent/briefing/latest.json",
                                  Body=json.dumps({"run_id": "r20261117T201211Z"}).encode())
    boto3.client("s3").put_object(Bucket="serving", Key="agent/briefing/r20261117T201211Z.json", Body=json.dumps(
        {"as_of_month": "2024-10", "refreshed_at": "x", "status": "ok", "facts": [], "definitions": []}).encode())
    assert bearer("GET /api/agent/briefing", tok)["statusCode"] == 200
    e = ev("GET /api/agent/briefing")
    e["headers"]["authorization"] = tok  # a bare token (variable_name header) is accepted too
    assert agent_api.handler(e, None)["statusCode"] == 200
    assert agent_api.handler(ev("GET /api/agent/briefing", cookie=cookie), None)["statusCode"] == 401
    # the agent token is not a session cookie
    assert agent_api.handler(ev("GET /api/agent/results/{result_id}", cookie=tok,
                                path_params={"result_id": "r_" + "0" * 24}), None)["statusCode"] == 401
    r = bearer("GET /api/agent/briefing", "fat_" + "A" * 43)
    assert r["statusCode"] == 401 and body_of(r)["error"]["message"] == agent_tokens.RELOAD_ES


def test_token_dies_with_expiry_logout_and_role_change():
    cookie = user()
    tok = body_of(session(cookie))["agent_token"]
    th = sessions.hash_token(tok)
    boto3.resource("dynamodb").Table("agent_tokens").update_item(
        Key={"token_hash": th}, UpdateExpression="SET expires_at = :e", ExpressionAttributeValues={":e": int(time.time()) - 1})
    assert bearer("POST /api/agent/ask", tok, {"question": "hola"})["statusCode"] == 401
    tok2 = body_of(session(cookie))["agent_token"]
    db.put_user("ana@example.com", passwords.hash_password(PW), "data", must_change_password=False)
    assert bearer("POST /api/agent/ask", tok2, {"question": "hola"})["statusCode"] == 401
    cookie3 = user("c@example.com")
    tok3 = body_of(session(cookie3))["agent_token"]
    auth.handler(ev("POST /api/auth/logout", cookie=cookie3), None)
    assert bearer("POST /api/agent/ask", tok3, {"question": "hola"})["statusCode"] == 401


def test_briefing_404_before_the_first_refresh():
    tok = body_of(session(user()))["agent_token"]
    assert bearer("GET /api/agent/briefing", tok)["statusCode"] == 404


def test_results_rechecked_against_the_callers_role():
    agent_api.put_result({"result_id": "r_" + "a" * 24, "status": "answered", "allowed_roles": ["finance"],
                          "rows": "[]", "columns": "[]", "chart": "{}", "question": "q"})
    assert agent_api.handler(ev("GET /api/agent/results/{result_id}", path_params={"result_id": "r_" + "a" * 24}),
                             None)["statusCode"] == 401
    revops = user()
    r = agent_api.handler(ev("GET /api/agent/results/{result_id}", cookie=revops,
                             path_params={"result_id": "r_" + "a" * 24}), None)
    assert r["statusCode"] == 403
    fin = user("f@example.com", role="finance")
    r = agent_api.handler(ev("GET /api/agent/results/{result_id}", cookie=fin,
                             path_params={"result_id": "r_" + "a" * 24}), None)
    assert r["statusCode"] == 200 and "rows" in body_of(r) and "caveats_es" in body_of(r)
    r = agent_api.handler(ev("GET /api/agent/results/{result_id}", cookie=fin,
                             path_params={"result_id": "r_" + "b" * 24}), None)
    assert r["statusCode"] == 404


def test_ask_never_returns_rows(monkeypatch):
    tok = body_of(session(user()))["agent_token"]
    monkeypatch.setattr(agent_api, "run_ask", lambda q, role, prev, deadline: {
        "status": "answered", "result_id": "r_" + "c" * 24, "summary_es": "x", "_spec": {}})
    b = body_of(bearer("POST /api/agent/ask", tok, {"question": "¿MRR?"}))
    assert "rows" not in b and "_spec" not in b


def test_eval_hook_is_not_reachable_through_api_gateway():
    e = ev("POST /api/agent/ask", {"question": "x"})
    e["source"] = "finora.voice-eval"
    e["role"] = "finance"
    assert agent_api.handler(e, None)["statusCode"] == 401  # API events carry requestContext: normal auth applies
