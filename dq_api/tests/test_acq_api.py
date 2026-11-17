"""Acquisition API (/api/acq/*, contracts/acq_api_contract.md v1.1) through the
finora-dq-api entry point: 401 without a session and 403 password_change_required
on every route, HR masking per role, 404 no_gold_run / unknown_run, live
scenarios, POST validation (every check), no_change, role rules, and an INSERT
that is safe: the fake Athena only applies it after parsing it as strict Trino
literals, and every parsed value must equal the request's value exactly."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import boto3
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "auth" / "tests"))
sys.path.insert(0, str(ROOT / "etl"))
from helpers import body_of, ev, load_auth, token_of  # noqa: E402

import acq  # noqa: E402
import api_handler  # noqa: E402
from authlib import db, passwords  # noqa: E402
from gold_build import funnel, gconfig  # noqa: E402

auth = load_auth()
G = gconfig.load()
RUN = "r20261117T160000Z"
CATS = [("PaidMedia", False), ("Travel", False), ("PublicidadNoWeb", False), ("Freelance", True),
        ("SoftwareTools", False), ("Team", True), ("PayrollExpenses", True)]
ROUTES = [("GET /api/acq/summary", None), ("GET /api/acq/scenarios", None), ("POST /api/acq/scenarios", {})]
T0 = datetime(2026, 11, 17, 16, 0, 0)


def put(key, obj):
    boto3.client("s3").put_object(Bucket="serving", Key=key, Body=json.dumps(obj).encode())


def payload():
    return {"run": {"run_id": RUN}, "spend_categories": [{"code": c, "hr_sensitive": hr} for c, hr in CATS],
            "months": [{"month": "2024-10", "spend_value": {c: str(1000 + i) for i, (c, _) in enumerate(CATS)},
                        "spend_people_value": "76000000", "spend_total_value": "200000000"},
                       {"month": "2024-09", "spend_value": {c: None for c, _ in CATS},
                        "spend_people_value": None, "spend_total_value": None}]}


def session_for(role, must_change=False):
    email = f"{role}@finora.example"
    db.put_user(email, passwords.hash_password("Temporary-Pass-2026"), role, must_change)
    return token_of(auth.handler(ev("POST /api/auth/login", {"email": email, "password": "Temporary-Pass-2026"}), None))


def call(route, token=None, body=None, query=None):
    e = ev(route, body=body, cookie=token, query=query)
    return api_handler.handler(e, None)


# --------------------------------------------------------------------------- #
# A fake Athena over an in-memory rates table                                 #
# --------------------------------------------------------------------------- #
TOKEN = re.compile(r"\s+|'(?:[^']|'')*'|[A-Za-z_][A-Za-z0-9_.]*|[0-9]+|[(),]|.", re.S)


def tokens(sql):
    return [t for t in TOKEN.findall(sql) if not t.isspace()]


def lit(t):
    assert t.startswith("'") and t.endswith("'"), t
    return t[1:-1].replace("''", "'")


class FakeAthena:
    def __init__(self, rows):
        self.rows, self.sql, self.clock = rows, [], T0 + timedelta(minutes=5)

    def __call__(self, sql, deadline):
        self.sql.append(sql)
        if sql.startswith("INSERT"):
            self.insert(sql)
            return []
        return self.select(sql)

    def insert(self, sql):
        tk = tokens(sql)
        head = ["INSERT", "INTO", "finora_gold.funnel_conversion_rate", "(", "scenario_id", ",", "scenario_label", ",",
                "from_stage_code", ",", "to_stage_code", ",", "rate", ",", "changed_at", ",", "changed_by", ",",
                "change_reason", ")", "VALUES"]
        assert tk[:len(head)] == head
        i = len(head)
        self.clock += timedelta(seconds=1)
        L = "<lit>"
        shape = ["(", L, ",", L, ",", L, ",", L, ",", "CAST", "(", L, "AS", "DECIMAL", "(", "5", ",", "4", ")", ")", ",",
                 "CAST", "(", "current_timestamp", "AT", "TIME", "ZONE", "'UTC'", "AS", "timestamp", "(", "6", ")", ")",
                 ",", L, ",", L, ")"]
        while True:
            row = tk[i:i + len(shape)]
            assert len(row) == len(shape), row
            for want, got in zip(shape, row):
                assert (got.startswith("'") and got.endswith("'") and len(got) >= 2) if want == L else got == want, \
                    (want, got)
            v = [lit(row[k]) for k, w in enumerate(shape) if w == L]
            self.rows.append({"scenario_id": v[0], "scenario_label": v[1], "from_stage_code": v[2],
                              "to_stage_code": v[3], "rate": Decimal(v[4]), "changed_at": self.clock,
                              "changed_by": v[5], "change_reason": v[6]})
            i += len(shape)
            if i >= len(tk):
                break
            assert tk[i] == ",", tk[i]
            i += 1

    def select(self, sql):
        m = re.search(r"WHERE s\.scenario_id = '([a-z][a-z0-9_]{0,39})'$", sql)
        st = funnel.scenario_status(self.rows, G, self.clock)
        cur = funnel.current_rows(self.rows)
        out = []
        for (sid, f), r in cur.items():
            if m and sid != m.group(1):
                continue
            s = st[sid]
            lt = s["latest"]
            out.append({"scenario_id": sid, "scenario_label": s["scenario_label"], "status": s["status"],
                        "failed_checks": ",".join(s["failed_checks"]),
                        "latest_changed_at": lt["changed_at"].strftime("%Y-%m-%d %H:%M:%S.%f"),
                        "latest_changed_by": lt["changed_by"], "latest_change_reason": lt["change_reason"],
                        "from_stage_code": f, "to_stage_code": r["to_stage_code"], "rate": f"{r['rate']:.4f}"})
        return out


def seed_rows():
    return [{"scenario_id": "base", "scenario_label": "Base (user rates 2026-11-17)", "from_stage_code": r["from_stage_code"],
             "to_stage_code": r["to_stage_code"], "rate": Decimal(r["rate"]), "changed_at": T0, "changed_by": "seed",
             "change_reason": "User definition 2026-11-17, docs/gold_acquisition_model.md"}
            for r in G["base_seed"]["rates"]]


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    acq._s3 = None
    acq._cache.clear()
    fake = FakeAthena(seed_rows())
    monkeypatch.setattr(acq, "run_query", fake)
    yield fake


@pytest.fixture
def published():
    put("acq/latest.json", {"run_id": RUN, "published_at": "2026-11-17T16:06:00Z"})
    put(f"acq/runs/{RUN}/summary.json", payload())


def req(sid="sql_demo_080", label="SQL to Demo at 80%", reason="What if demos are booked faster", **rates):
    base = {r["from_stage_code"]: r["rate"] for r in G["base_seed"]["rates"]}
    base.update(rates)
    return {"scenario_id": sid, "label": label, "change_reason": reason,
            "rates": [{"from_stage": f, "to_stage": t, "rate": base[f]} for f, t in G["transitions"]]}


# --------------------------------------------------------------------------- #
# Session rules                                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("route,body", ROUTES)
def test_every_acq_route_is_401_without_a_session(route, body, published, fresh):
    r = call(route, body=body)
    assert r["statusCode"] == 401 and body_of(r)["error"]["code"] == "unauthenticated"
    assert call(route, token="forged", body=body)["statusCode"] == 401
    assert fresh.sql == []


@pytest.mark.parametrize("route,body", ROUTES)
def test_every_acq_route_is_403_while_the_password_must_change(route, body, published, fresh):
    r = call(route, token=session_for("finance", must_change=True), body=body)
    assert r["statusCode"] == 403 and body_of(r)["error"]["code"] == "password_change_required"
    assert fresh.sql == []


def test_unknown_role_is_forbidden_and_dq_routes_still_answer(published):
    assert call("GET /api/acq/summary", token=session_for("marketing"))["statusCode"] == 403
    assert call("GET /api/dq/runs")["statusCode"] == 401
    assert set(api_handler.ROUTES) >= {"GET /api/dq/runs", "GET /api/dq/summary",
                                      "GET /api/dq/rules/{rule_id}/datasets/{dataset_id}/records"}


# --------------------------------------------------------------------------- #
# GET /api/acq/summary                                                        #
# --------------------------------------------------------------------------- #

def test_summary_masks_hr_categories_for_non_finance(published):
    fin = body_of(call("GET /api/acq/summary", token=session_for("finance")))
    assert fin["months"][0]["spend_value"]["Team"] == "1005" and fin["months"][0]["spend_value"]["Freelance"] == "1003"
    for role in ("data", "revops"):
        b = body_of(call("GET /api/acq/summary", token=session_for(role)))
        sv = b["months"][0]["spend_value"]
        assert sv["Team"] == sv["PayrollExpenses"] == sv["Freelance"] == "__restricted__"
        assert sv["PaidMedia"] == "1000" and sv["SoftwareTools"] == "1004"
        assert b["months"][0]["spend_people_value"] == "76000000" and b["months"][0]["spend_total_value"] == "200000000"
        assert b["months"][1]["spend_value"]["Team"] == "__restricted__" and b["months"][1]["spend_value"]["Travel"] is None
    # the cached unmasked payload is not altered by masking
    assert body_of(call("GET /api/acq/summary", token=session_for("finance")))["months"][0]["spend_value"]["Team"] == "1005"


def test_summary_404_codes():
    token = session_for("data")
    r = call("GET /api/acq/summary", token=token)
    assert r["statusCode"] == 404 and body_of(r)["error"]["code"] == "no_gold_run"
    put(f"acq/runs/{RUN}/summary.json", payload())
    assert body_of(call("GET /api/acq/summary", token=token, query={"run": RUN}))["run"]["run_id"] == RUN
    for bad in ("r20200101T000000Z", "../../dq/latest", "latest2"):
        r = call("GET /api/acq/summary", token=token, query={"run": bad})
        assert r["statusCode"] == 404 and body_of(r)["error"]["code"] == "unknown_run"


# --------------------------------------------------------------------------- #
# Scenarios                                                                   #
# --------------------------------------------------------------------------- #

def test_get_scenarios_lists_base_first_with_can_edit_per_role(fresh):
    fresh.rows += [dict(r, scenario_id="alpha", scenario_label="A", changed_by="x", change_reason="y",
                        changed_at=T0 + timedelta(minutes=1)) for r in seed_rows()]
    fresh.rows.append(dict(seed_rows()[0], scenario_id="aaa_bad", rate=Decimal("1.5000")))
    for role, can in (("data", False), ("finance", True), ("revops", True)):
        b = body_of(call("GET /api/acq/scenarios", token=session_for(role)))
        assert b["can_edit"] is can
        assert [s["scenario_id"] for s in b["scenarios"]] == ["base", "aaa_bad", "alpha"]
    base = b["scenarios"][0]
    assert base == {"scenario_id": "base", "label": "Base (user rates 2026-11-17)", "status": "valid",
                    "failed_checks": [], "changed_at": "2026-11-17T16:00:00Z", "changed_by": "seed",
                    "change_reason": "User definition 2026-11-17, docs/gold_acquisition_model.md",
                    "rates": [{"from_stage": f, "to_stage": t, "rate": r} for (f, t), r in
                              zip(G["transitions"], ["0.8000", "0.4000", "0.5000", "0.7000", "0.6000", "0.4000"])]}
    bad = b["scenarios"][1]
    assert bad["status"] == "invalid" and bad["failed_checks"] == ["GR-03", "GR-04"]


def test_post_requires_finance_or_revops(fresh):
    r = call("POST /api/acq/scenarios", token=session_for("data"), body=req())
    assert r["statusCode"] == 403 and body_of(r)["error"]["code"] == "role_not_allowed"
    assert fresh.sql == []


def test_post_new_scenario_appends_six_rows_then_no_change_then_one_row(fresh):
    token = session_for("revops")
    r = call("POST /api/acq/scenarios", token=token, body=req(SQL="0.8000"))
    assert r["statusCode"] == 201
    s = body_of(r)
    assert s["scenario_id"] == "sql_demo_080" and s["status"] == "valid" and s["label"] == "SQL to Demo at 80%"
    assert {x["from_stage"]: x["rate"] for x in s["rates"]}["SQL"] == "0.8000"
    who = "dashboard:" + hashlib.sha256(b"revops@finora.example").hexdigest()[:12]
    assert s["changed_by"] == who and "revops@finora.example" not in json.dumps(fresh.rows, default=str)
    assert len(fresh.rows) == 12 and sum(1 for x in fresh.sql if x.startswith("INSERT")) == 1
    assert not any(re.search(r"\b(UPDATE|DELETE|MERGE|DROP)\b", x) for x in fresh.sql)
    r = call("POST /api/acq/scenarios", token=token, body=req(SQL="0.8"))
    assert r["statusCode"] == 400 and body_of(r)["error"]["code"] == "no_change" and len(fresh.rows) == 12
    r = call("POST /api/acq/scenarios", token=token, body=req(SQL="0.8000", DEMO="0.65", reason="Q4 review"))
    assert r["statusCode"] == 201 and len(fresh.rows) == 13
    assert fresh.rows[-1]["from_stage_code"] == "DEMO" and fresh.rows[-1]["rate"] == Decimal("0.6500")
    assert body_of(r)["change_reason"] == "Q4 review"


def test_editing_base_and_fixing_an_invalid_scenario(fresh):
    token = session_for("finance")
    r = call("POST /api/acq/scenarios", token=token, body=req("base", "Base (user rates 2026-11-17)",
                                                               "Board asked for 0.45", PROPOSAL="0.4500"))
    assert r["statusCode"] == 201 and len(fresh.rows) == 7 and fresh.rows[-1]["from_stage_code"] == "PROPOSAL"
    fresh.rows.append(dict(seed_rows()[0], scenario_id="broken", changed_by=" ", changed_at=T0))
    r = call("POST /api/acq/scenarios", token=token, body=req("broken", "Fixed", "complete it"))
    assert r["statusCode"] == 201 and body_of(r)["status"] == "valid"
    assert sum(1 for x in fresh.rows if x["scenario_id"] == "broken") == 7  # all six appended


_TOKENS: dict = {}


def _details(body):
    token = _TOKENS.get("revops") or _TOKENS.setdefault("revops", session_for("revops"))
    r = call("POST /api/acq/scenarios", token=token, body=body)
    assert r["statusCode"] == 400
    err = body_of(r)["error"]
    assert err["code"] == "invalid_scenario" and isinstance(err["message"], str)
    return {(d["check"], d["field"]) for d in err["details"]}


def test_every_validation_error(fresh):
    _TOKENS.clear()
    assert _details(req("Bad-ID")) == {("GR-01", "scenario_id")}
    assert _details(req("x" * 41)) == {("GR-01", "scenario_id")}
    assert _details(req("1abc")) == {("GR-01", "scenario_id")}
    assert _details(req(label="")) == {("LABEL_LENGTH", "label")}
    assert _details(req(label="   ")) == {("LABEL_LENGTH", "label")}
    assert _details(req(label="x" * 201)) == {("LABEL_LENGTH", "label")}
    assert _details(req(reason="")) == {("REASON_LENGTH", "change_reason")}
    assert _details(req(reason="y" * 501)) == {("REASON_LENGTH", "change_reason")}
    assert _details(req(label="two\nlines")) == {("GR-06", "label")}
    assert _details(req(reason="tab\there")) == {("GR-06", "change_reason")}
    for bad in ("0", "0.0000", "1.0001", "1.5", "-0.5", "0.12345", "abc", "", "1e-1", " 0.5"):
        assert _details(req(SQL=bad)) == {("GR-03", "rates")}, bad
    b = req()
    b["rates"][0]["rate"] = 0.8
    assert _details(b) == {("GR-03", "rates")}
    b = req()
    b["rates"][3]["to_stage"] = "WON"
    assert ("GR-02", "rates") in _details(b)
    b = req()
    b["rates"] = b["rates"][:5]
    assert _details(b) == {("GR-04", "rates")}
    b = req()
    b["rates"][5] = dict(b["rates"][0])
    assert ("GR-04", "rates") in _details(b)
    b = req("Bad-ID", "", "")
    assert _details(b) == {("GR-01", "scenario_id"), ("LABEL_LENGTH", "label"), ("REASON_LENGTH", "change_reason")}
    r = api_handler.handler({**ev("POST /api/acq/scenarios", cookie=_TOKENS["revops"]), "body": "{not json"}, None)
    assert r["statusCode"] == 400 and body_of(r)["error"]["code"] == "invalid_scenario"
    assert fresh.sql == []  # nothing reached Athena


def test_valid_rates_with_fewer_decimals_and_one_are_accepted(fresh):
    r = call("POST /api/acq/scenarios", token=session_for("revops"), body=req("edge", NEW="1", WORKING="0.5",
                                                                                ENGAGED="1.0000"))
    assert r["statusCode"] == 201
    rates = {x["from_stage_code"]: x["rate"] for x in fresh.rows if x["scenario_id"] == "edge"}
    assert rates["NEW"] == Decimal("1.0000") and rates["WORKING"] == Decimal("0.5000")
    assert "CAST('1.0000' AS DECIMAL(5,4))" in fresh.sql[-2]


@pytest.mark.parametrize("label,reason", [
    ("x'); DROP TABLE finora_gold.dim_month; --", "a' OR '1'='1"),
    ("O'Brien''s ''quoted''", "ends with a quote '"),
    ("Ünïcödé — test ✓", "back\\slash and ; semicolon /* comment */"),
])
def test_the_insert_is_injection_safe(fresh, label, reason):
    r = call("POST /api/acq/scenarios", token=session_for("finance"), body=req("safe_one", label, reason))
    assert r["statusCode"] == 201
    ins = [x for x in fresh.sql if x.startswith("INSERT")][-1]
    new = [x for x in fresh.rows if x["scenario_id"] == "safe_one"]
    assert len(new) == 6 and {x["scenario_label"] for x in new} == {label} and {x["change_reason"] for x in new} == {reason}
    outside = re.sub(r"'(?:[^']|'')*'", "''", ins)  # the statement with every literal blanked
    assert ";" not in outside and "--" not in outside and "/*" not in outside
    assert outside.count("VALUES") == 1 and "DROP" not in outside
    assert acq.sql_string("it's") == "'it''s'"
    with pytest.raises(ValueError):
        acq.sql_string("a\x00b")
