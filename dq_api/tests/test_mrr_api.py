"""MRR API (/api/mrr/*, contracts/mrr_api_contract.md v1) through finora-dq-api:
401 / 403 password_change_required, 404 no_gold_run / unknown_run, all three
roles unmasked, movements filtered (month range, repeatable step and driver,
from rawQueryString or comma-joined), sorted (abs_desc / asc / desc) and paged
across stored pages, and 400 invalid_query details."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import boto3
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "auth" / "tests"))
from helpers import body_of, ev, load_auth, token_of  # noqa: E402

import api_handler  # noqa: E402
import mrr  # noqa: E402
from authlib import db, passwords  # noqa: E402

auth = load_auth()
RUN = "r20261117T193900Z"
STEPS = [("new", "behaviour"), ("expansion", "behaviour"), ("contraction", "behaviour"), ("churn", "behaviour"),
         ("list_price_increase", "pricing"), ("discount_start", "discount")]
MONTHS = ["2024-07", "2024-08", "2024-09", "2024-10"]
ROUTES = ["GET /api/mrr/summary", "GET /api/mrr/movements"]


def put(key, obj):
    boto3.client("s3").put_object(Bucket="serving", Key=key, Body=json.dumps(obj).encode())


def rows():
    out = []
    for i in range(450):
        step, driver = STEPS[i % 5]
        change = Decimal(10000 - i * 10) * (-1 if step in ("contraction", "churn") else 1)
        out.append({"customer_id": 1000 + i, "month": MONTHS[i % 4], "step": step, "driver": driver,
                    "inferred": driver == "pricing", "industry_code": "RETAIL", "mrr_before_value": "100.00",
                    "mrr_after_value": "200.00", "change_value": f"{change:.2f}", "list_before_value": None,
                    "list_after_value": None, "discount_before_value": None, "discount_after_value": None,
                    "settlement_type": None, "is_provisional": False, "flags": []})
    out.sort(key=lambda r: -abs(Decimal(r["change_value"])))
    return out


@pytest.fixture(autouse=True)
def fresh():
    mrr._s3 = None
    mrr._cache.clear()


@pytest.fixture
def published():
    rs = rows()
    put("mrr/latest.json", {"run_id": RUN, "published_at": "2026-11-17T19:50:00Z"})
    put(f"mrr/runs/{RUN}/summary.json", {
        "run": {"run_id": RUN, "mrr_basis": "cash_proxy"},
        "drivers": [{"code": d} for d in ("behaviour", "pricing", "discount", "timing")],
        "steps": [{"code": s, "driver": d, "order": i} for i, (s, d) in enumerate(STEPS, start=1)],
        "months": [{"month": m, "opening_mrr_value": "1.00"} for m in MONTHS]})
    for p in range(3):
        put(f"mrr/runs/{RUN}/movements/page-{p + 1}.json",
            {"run_id": RUN, "total": 450, "page": p + 1, "page_size": 200, "pages": 3, "sort": "abs_desc",
             "movements": rs[p * 200:(p + 1) * 200]})
    return rs


_T: dict = {}


def token(role="data", must_change=False):
    k = (role, must_change)
    if k not in _T or must_change:
        email = f"{role}{'-mc' if must_change else ''}@finora.example"
        db.put_user(email, passwords.hash_password("Temporary-Pass-2026"), role, must_change)
        _T[k] = token_of(auth.handler(ev("POST /api/auth/login", {"email": email, "password": "Temporary-Pass-2026"}),
                                      None))
    return _T[k]


@pytest.fixture(autouse=True)
def tokens():
    _T.clear()


def call(route, tok=None, query=None, raw=None):
    e = ev(route, cookie=tok, query=query)
    if raw is not None:
        e["rawQueryString"] = raw
    return api_handler.handler(e, None)


@pytest.mark.parametrize("route", ROUTES)
def test_401_without_a_session_and_403_while_the_password_must_change(route, published):
    r = call(route)
    assert r["statusCode"] == 401 and body_of(r)["error"]["code"] == "unauthenticated"
    assert call(route, tok="forged")["statusCode"] == 401
    r = call(route, tok=token("finance", must_change=True))
    assert r["statusCode"] == 403 and body_of(r)["error"]["code"] == "password_change_required"
    assert call(route, tok=token("marketing"))["statusCode"] == 403


@pytest.mark.parametrize("route", ROUTES)
def test_404_codes(route):
    r = call(route, tok=token())
    assert r["statusCode"] == 404 and body_of(r)["error"]["code"] == "no_gold_run"
    for bad in ("r20200101T000000Z", "../../acq/latest"):
        r = call(route, tok=token(), query={"run": bad})
        assert r["statusCode"] == 404 and body_of(r)["error"]["code"] == "unknown_run"


def test_summary_for_every_role_unmasked(published):
    for role in ("data", "finance", "revops"):
        b = body_of(call("GET /api/mrr/summary", tok=token(role)))
        assert b["run"]["run_id"] == RUN and len(b["months"]) == 4 and "__restricted__" not in json.dumps(b)
    assert body_of(call("GET /api/mrr/summary", tok=token(), query={"run": RUN}))["run"]["run_id"] == RUN


def test_movements_default_paging_across_stored_pages(published):
    rs = published
    b = body_of(call("GET /api/mrr/movements", tok=token()))
    assert (b["run_id"], b["total"], b["page"], b["page_size"], b["sort"]) == (RUN, 450, 1, 50, "abs_desc")
    assert b["movements"] == rs[:50]
    b = body_of(call("GET /api/mrr/movements", tok=token(), query={"page": "2", "page_size": "200"}))
    assert b["movements"] == rs[200:400]
    b = body_of(call("GET /api/mrr/movements", tok=token(), query={"page": "3", "page_size": "200"}))
    assert b["movements"] == rs[400:450]
    assert body_of(call("GET /api/mrr/movements", tok=token(), query={"page": "99"}))["movements"] == []


def test_movements_filters_and_sorts(published):
    rs = published
    b = body_of(call("GET /api/mrr/movements", tok=token("revops"), query={"from": "2024-08", "to": "2024-09",
                                                                         "page_size": "200"}))
    want = [r for r in rs if "2024-08" <= r["month"] <= "2024-09"]
    assert b["total"] == len(want) and b["movements"] == want[:200]
    # repeated step: rawQueryString keeps repeats; the comma-joined form gives the same answer
    b1 = body_of(call("GET /api/mrr/movements", tok=token(), raw="step=new&step=churn&page_size=200"))
    b2 = body_of(call("GET /api/mrr/movements", tok=token(), query={"step": "new,churn", "page_size": "200"}))
    want = [r for r in rs if r["step"] in ("new", "churn")]
    assert b1["total"] == b2["total"] == len(want) == 180 and b1["movements"] == b2["movements"] == want[:200][:180]
    b = body_of(call("GET /api/mrr/movements", tok=token(), query={"driver": "pricing", "page_size": "200"}))
    assert b["total"] == 90 and {r["driver"] for r in b["movements"]} == {"pricing"}
    asc = body_of(call("GET /api/mrr/movements", tok=token(), query={"sort": "asc", "page_size": "200"}))["movements"]
    desc = body_of(call("GET /api/mrr/movements", tok=token(), query={"sort": "desc", "page_size": "200"}))["movements"]
    vals = [Decimal(r["change_value"]) for r in rs]
    assert [Decimal(r["change_value"]) for r in asc] == sorted(vals)[:200]
    assert [Decimal(r["change_value"]) for r in desc] == sorted(vals, reverse=True)[:200]
    assert body_of(call("GET /api/mrr/movements", tok=token(), query={"step": "discount_start"}))["total"] == 0


def _details(query=None, raw=None):
    r = call("GET /api/mrr/movements", tok=token(), query=query, raw=raw)
    assert r["statusCode"] == 400 and body_of(r)["error"]["code"] == "invalid_query"
    return {(d["check"], d["field"]) for d in body_of(r)["error"]["details"]}


def test_invalid_queries(published):
    assert _details({"from": "2024-13"}) == {("month_format", "from")}
    assert _details({"to": "24-10"}) == {("month_format", "to")}
    assert _details({"from": "2024-10", "to": "2024-01"}) == {("month_range", "from")}
    assert _details({"sort": "random"}) == {("sort", "sort")}
    assert _details({"page": "0"}) == {("paging", "page")}
    assert _details({"page_size": "201"}) == {("paging", "page_size")}
    assert _details({"page_size": "-5"}) == {("paging", "page_size")}
    assert _details({"page": "1e3"}) == {("paging", "page")}
    assert _details({"step": "bogus"}) == {("unknown_code", "step")}
    assert _details({"driver": "x'; DROP"}) == {("unknown_code", "driver")}
    assert _details(raw="page=1&page=2") == {("single_value", "page")}
    assert _details({"from": "bad", "sort": "x", "page_size": "0"}) == {("month_format", "from"), ("sort", "sort"),
                                                                        ("paging", "page_size")}
