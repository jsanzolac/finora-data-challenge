"""DQ API: 401 without a session on every route, 403 while
must_change_password, HR masking for non-Finance roles, q and paging."""

import json
import sys
from pathlib import Path

import boto3
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "auth" / "tests"))
from helpers import body_of, ev, load_auth, token_of  # noqa: E402

from authlib import db, passwords  # noqa: E402
import handler as api  # noqa: E402

auth = load_auth()
RUN = "r20261116T041000Z"
ROUTES = [("GET /api/dq/runs", {}), ("GET /api/dq/summary", {}),
          ("GET /api/dq/rules/{rule_id}/datasets/{dataset_id}/records", {"rule_id": "SB-10", "dataset_id": "sm_spend"})]
SM_COLS = ["Month", "PaidMedia", "Travel", "PublicidadNoWeb", "Freelance", "SoftwareTools", "Team", "PayrollExpenses"]


def put(key, obj):
    boto3.client("s3").put_object(Bucket="serving", Key=key, Body=json.dumps(obj).encode())


def rec(line, month, payroll, rule_others=()):
    vals = {c: "$0.100" for c in SM_COLS}
    vals.update(Month=month, PayrollExpenses=payroll, Team="$0.777", Freelance="$0.555")
    return {"source_line": line, "key": {"Month": month}, "values": vals, "failed_columns": ["PayrollExpenses"],
            "reason": "NEGATIVE_SPEND: negative value in PayrollExpenses", "action": "flag",
            "other_failed_rules": list(rule_others)}


@pytest.fixture
def published():
    put("dq/latest.json", {"run_id": RUN, "published_at": "2026-11-16T04:11:12Z"})
    put("dq/runs.json", [{"run_id": RUN, "status": "succeeded"}])
    put(f"dq/runs/{RUN}/summary.json", {"run": {"run_id": RUN}, "datasets": [], "rules": [], "trend": []})
    recs = [rec(i + 2, f"2023-{(i % 12) + 1:02d}", f"-$0.{i:03d}") for i in range(250)]
    for p, chunk in enumerate((recs[:200], recs[200:]), start=1):
        put(f"dq/runs/{RUN}/records/SB-10/sm_spend/page-{p}.json",
            {"rule_id": "SB-10", "dataset_id": "sm_spend", "run_id": RUN, "total": 250, "page": p,
             "page_size": 200, "page_count": 2, "columns": SM_COLS, "records": chunk})
    fc = {"source_line": 9, "key": {"Month": "2023-01"}, "values": {c: f"v{c}" for c in SM_COLS},
          "failed_columns": SM_COLS, "reason": "FIELD_COUNT: expected 8 fields, found 9", "action": "exclude",
          "other_failed_rules": []}
    put(f"dq/runs/{RUN}/records/SQ-01/sm_spend/page-1.json",
        {"rule_id": "SQ-01", "dataset_id": "sm_spend", "run_id": RUN, "total": 1, "page": 1, "page_size": 200,
         "page_count": 1, "columns": SM_COLS, "records": [fc]})


def session_for(role, must_change=False, email=None):
    email = email or f"{role}@finora.example"
    db.put_user(email, passwords.hash_password("Temporary-Pass-2026"), role, must_change)
    r = auth.handler(ev("POST /api/auth/login", {"email": email, "password": "Temporary-Pass-2026"}), None)
    return token_of(r)


def call(route, pp, token=None, query=None):
    return api.handler(ev(route, cookie=token, path_params=pp, query=query), None)


@pytest.mark.parametrize("route,pp", ROUTES)
def test_every_dq_route_is_401_without_a_session(route, pp, published):
    r = call(route, pp)
    assert r["statusCode"] == 401 and body_of(r)["error"]["code"] == "unauthenticated"
    assert call(route, pp, token="forged")["statusCode"] == 401


@pytest.mark.parametrize("route,pp", ROUTES)
def test_every_dq_route_is_403_while_the_password_must_change(route, pp, published):
    token = session_for("finance", must_change=True)
    r = call(route, pp, token)
    assert r["statusCode"] == 403 and body_of(r)["error"]["code"] == "password_change_required"


def test_summary_and_runs(published):
    token = session_for("data")
    assert body_of(call(*ROUTES[1], token))["run"]["run_id"] == RUN
    assert body_of(call(*ROUTES[0], token))[0]["run_id"] == RUN
    assert call(*ROUTES[1], token, query={"run": "r20200101T000000Z"})["statusCode"] == 404
    assert call(*ROUTES[1], token, query={"run": "../../etc"})["statusCode"] == 404


def test_finance_sees_hr_values_data_and_revops_see_restricted(published):
    fin = body_of(call(*ROUTES[2], session_for("finance")))["records"][0]["values"]
    assert fin["PayrollExpenses"] == "-$0.000" and fin["Team"] == "$0.777" and fin["Freelance"] == "$0.555"
    for role in ("data", "revops"):
        v = body_of(call(*ROUTES[2], session_for(role)))["records"][0]["values"]
        assert v["PayrollExpenses"] == v["Team"] == v["Freelance"] == "__restricted__"
        assert v["PaidMedia"] == "$0.100" and v["Month"] == "2023-01"


def test_a_stage_a_sm_record_is_fully_restricted_for_non_finance(published):
    pp = {"rule_id": "SQ-01", "dataset_id": "sm_spend"}
    r = body_of(call(ROUTES[2][0], pp, session_for("data")))["records"][0]
    assert set(r["values"].values()) == {"__restricted__"} and r["key"] == {"Month": "__restricted__"}
    r = body_of(call(ROUTES[2][0], pp, session_for("finance")))["records"][0]
    assert r["values"]["Month"] == "vMonth"


def test_search_never_matches_a_restricted_value(published):
    q = {"q": "0.777"}  # the Team value
    assert body_of(call(*ROUTES[2], session_for("data"), query=q))["total"] == 0
    assert body_of(call(*ROUTES[2], session_for("finance"), query=q))["total"] == 250
    assert body_of(call(*ROUTES[2], session_for("data"), query={"q": "2023-02"}))["total"] == 21


def test_paging_across_stored_pages(published):
    token = session_for("data")
    b = body_of(call(*ROUTES[2], token, query={"page": "4", "page_size": "60"}))
    assert b["total"] == 250 and b["page"] == 4 and b["page_size"] == 60
    assert [r["source_line"] for r in b["records"]] == list(range(182, 242))
    b = body_of(call(*ROUTES[2], token, query={"page": "2", "page_size": "1000"}))
    assert b["page_size"] == 200 and len(b["records"]) == 50
    assert body_of(call(*ROUTES[2], token, query={"page": "99"}))["records"] == []


def test_unknown_rule_or_dataset_is_404(published):
    token = session_for("data")
    assert call(ROUTES[2][0], {"rule_id": "SQ-99", "dataset_id": "sm_spend"}, token)["statusCode"] == 404
    assert call(ROUTES[2][0], {"rule_id": "SB-10", "dataset_id": "hr"}, token)["statusCode"] == 404


def test_an_unknown_role_is_forbidden(published):
    token = session_for("marketing")
    assert call(*ROUTES[1], token)["statusCode"] == 403
