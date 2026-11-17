"""Gold MRR model (docs/mrr_discounts_model.md §6) on the golden silver run of
data/*.csv: every figure of §6.6, the 2024-10 fixture, the run controls
GC-MRR-1..5 and the contract identities, the serving snapshot shape
(contracts/mrr_api_contract.md v1), and synthetic edge cases."""

from __future__ import annotations

import copy
import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal as D
from functools import lru_cache
from pathlib import Path

import pytest

from gold_helpers import SILVER_RUN, golden_silver
from gold_mrr import engine, mconfig, schemas, summary

CFG = mconfig.load()
RUN = "r20261117T200000Z"
META = {"run_id": RUN, "silver_run_id": SILVER_RUN, "built_at": datetime(2026, 11, 17, 20, tzinfo=timezone.utc),
        "gold_model_version": CFG["gold_model_version"]}
ROOT = Path(__file__).resolve().parents[2]


def silver_inputs(silver=None):
    s = silver or golden_silver()["silver"]
    return {t: s[t] for t in schemas.SILVER_INPUTS}


@lru_cache(maxsize=1)
def golden():
    return engine.build(silver_inputs(), CFG, META)


def line_total(res, line, months=None):
    rows = [r for r in res["tables"]["agg_mrr_bridge_month"] if r["line"] == line
            and (months is None or engine.kmonth(r["month_key"]) in months)]
    return rows


# --------------------------------------------------------------------------- #
# Config and spec pin                                                         #
# --------------------------------------------------------------------------- #
def test_config_is_generated_from_the_current_spec():
    assert CFG["spec_sha256"] == hashlib.sha256((ROOT / "docs" / "mrr_discounts_model.md").read_bytes()).hexdigest(), \
        "docs/mrr_discounts_model.md changed: re-run etl/config/build_gold_mrr_json.py and re-check §6"
    assert [(ln["line"], ln["line_order"]) for ln in CFG["lines"]] == [
        ("opening", 0), ("new", 1), ("reactivation", 2), ("expansion", 3), ("contraction", 4), ("churn", 5),
        ("pause", 6), ("resume", 7), ("grace_drop", 8), ("list_price_change", 9), ("inferred_price_step", 10),
        ("discount_start", 11), ("discount_change", 12), ("discount_base_effect", 13), ("discount_end", 14),
        ("discount_released_on_churn", 15), ("first_payment_multiple", 16), ("closing", 17),
        ("timing_arrears", 20), ("timing_prepay", 21), ("timing_split", 22), ("timing_uneven_split", 23),
        ("timing_late_price_step", 24), ("collected", 25)]


# --------------------------------------------------------------------------- #
# §6.6 expected figures                                                       #
# --------------------------------------------------------------------------- #
def test_controls_all_pass():
    res = golden()
    assert [c for c in res["controls"] if not c["passed"]] == []
    ids = {c["control"] for c in res["controls"]}
    assert {"GC-MRR-1", "GC-MRR-2", "GC-MRR-3", "GC-MRR-3.continuity", "GC-MRR-4", "GC-MRR-5",
            "contract.period"} <= ids
    engine.assert_controls(res)


def test_row_counts():
    T = golden()["tables"]
    assert len(T["fact_customer_month_mrr"]) == 66674
    assert len(T["fact_mrr_movement"]) == 4589
    assert len(T["agg_mrr_bridge_month"]) == 33 * 24 == 792
    assert len({r["month_key"] for r in T["agg_mrr_bridge_month"]}) == 33
    assert min(r["month_key"] for r in T["agg_mrr_bridge_month"]) == 202202
    assert len(T["dim_movement_type"]) == 24


def test_period_levels_and_drivers():
    f = golden()["figures"]
    assert f["period"] == {"from": "2022-02", "to": "2024-10", "opening": "3500.030835", "opening_customers": 377,
                           "closing": "9636.064683", "closing_customers": 1678, "net_movement": "6136.033848"}
    assert f["drivers"] == {"behaviour": "6320.070330", "pricing": "57.436743", "timing": "-241.473225"}
    assert D("6320.070330") + D("57.436743") + D("-241.473225") == D("6136.033848")


@pytest.mark.parametrize("line,events,amount", [
    ("new", 1584, "10548.251196"), ("reactivation", 64, "1602.749232"), ("expansion", 1116, "3707.896089"),
    ("contraction", 897, "-6281.965923"), ("churn", 301, "-3486.389529"), ("pause", 193, "-1901.644479"),
    ("resume", 193, "2457.988533"), ("grace_drop", 46, "-326.814789"), ("inferred_price_step", 140, "57.436743"),
    ("first_payment_multiple", 55, "-241.473225")])
def test_lines(line, events, amount):
    f = golden()["figures"]["lines"][line]
    assert (f["events"], D(f["amount"])) == (events, D(amount))
    rows = line_total(golden(), line)
    assert sum(r["events"] for r in rows) == events
    assert sum(r["amount"] for r in rows) == D(amount)


def test_cro05_split_and_gc_mrr_4():
    f = golden()["figures"]
    assert f["covered"] == {"expansion": {"events": 1072, "amount": "3375.380760"},
                            "contraction": {"events": 814, "amount": "-4589.451833"}}
    assert D("3499.903452") - D("3375.380760") == D("124.522692")
    assert D("4656.537782") - D("4589.451833") == D("67.085949")
    assert D("124.522692") - D("67.085949") == D("57.436743")
    s = golden_silver()["silver"]["customer_month"]
    assert sum(r["expansion_amount"] for r in s) - sum(r["contraction_amount"] for r in s) == D("-1156.634330")


def test_inferred_rows_and_flags():
    f = golden()["figures"]
    assert f["inferred_rows"] == 581 == 193 + 193 + 140 + 55
    assert f["price_step_windows"] == 140 and f["price_step_customers"] == 140
    assert f["flags"] == {"one_off_spike": {"events": 222, "amount": "1325.161824"},
                          "temporary_dip": {"events": 31, "amount": "-110.196093"}}


def test_timing_by_type():
    t = golden()["figures"]["timing_by_type"]
    assert {k: (v["rows"], v["abs_sum"], v["net"]) for k, v in t.items()} == {
        "arrears": (376, "4105.445054", "0.000000"), "prepay": (94, "498.743700", "0.000000"),
        "split": (31, "938.687596", "0.000000"), "uneven_split": (22, "82.483002", "0.000000"),
        "late_price_step": (280, "127.739094", "0.000000")}
    cm = golden()["tables"]["fact_customer_month_mrr"]
    assert sum(r["timing_adjustment"] for r in cm) == 0
    assert sum(r["collected_amount"] for r in cm) == D("221441.504508")


def test_customer_94():
    mv = [r for r in golden()["tables"]["fact_mrr_movement"] if r["customer_id"] == 94]
    assert len(mv) == 29 and all(r["is_outlier_customer"] for r in mv)
    assert sum(r["amount"] for r in mv if r["movement_type"] == "expansion") == D("450.147852")
    assert sum(r["amount"] for r in mv if r["movement_type"] == "contraction") == D("-389.343129")
    assert {r["customer_id"] for r in golden()["tables"]["fact_mrr_movement"] if r["is_outlier_customer"]} <= {94, 322}


def test_fixture_2024_10():
    b = {r["line"]: r for r in golden()["tables"]["agg_mrr_bridge_month"] if r["month_key"] == 202410}
    want = {"opening": "9274.712517", "new": "220.133340", "reactivation": "217.944993", "expansion": "212.900352",
            "contraction": "-174.803937", "churn": "0", "pause": "0", "inferred_price_step": "0",
            "resume": "116.008620", "grace_drop": "-230.012202", "first_payment_multiple": "-0.819000",
            "closing": "9636.064683", "timing_arrears": "64.680000", "timing_prepay": "0", "timing_split": "0",
            "timing_uneven_split": "0", "timing_late_price_step": "0", "collected": "9700.744683"}
    assert {k: D(b[k]["amount"]) for k in want} == {k: D(v) for k, v in want.items()}
    for k in ("list_price_change", "discount_start", "discount_change", "discount_base_effect", "discount_end",
              "discount_released_on_churn"):
        assert b[k]["amount"] is None and b[k]["amount_value"] is None and b[k]["events"] is None
    assert all(r["is_provisional"] for r in b.values())
    assert b["closing"]["amount_value"] == D("96360646.83") and b["closing"]["events"] == 1678
    mc = {r["month"]: r for r in golden_silver()["silver"]["month_control"]}
    assert D(b["collected"]["amount"]) == mc["2024-10"]["revenue_total"]


def test_bridge_ties_every_month_independently():
    """Recompute opening + lines 1-16 = closing and closing + 20-24 = collected from the rows."""
    rows = defaultdict(dict)
    for r in golden()["tables"]["agg_mrr_bridge_month"]:
        rows[r["month_key"]][r["line_order"]] = r["amount"]
    months = sorted(rows)
    for i, k in enumerate(months):
        v = rows[k]
        assert v[0] + sum(v[o] for o in range(1, 17) if v[o] is not None) == v[17], k
        assert v[17] + sum(v[o] for o in range(20, 25)) == v[25], k
        if i:
            assert v[0] == rows[months[i - 1]][17], k
    assert rows[202202][0] == D("3500.030835") and rows[202410][17] == D("9636.064683")
    provisional = {r["month_key"] for r in golden()["tables"]["agg_mrr_bridge_month"] if r["is_provisional"]}
    assert provisional == {202409, 202410} and golden()["churn_confirmed_through"] == "2024-08"


def test_fact_customer_month_columns():
    cm = golden()["tables"]["fact_customer_month_mrr"]
    s = {(r["customer_id"], r["month"]): r for r in golden_silver()["silver"]["customer_month"]}
    steps = [r for r in cm if r["is_inferred_price_step"]]
    assert len(steps) == 280 and all(r["timing_type"] == "late_price_step" for r in steps)
    for r in cm:
        src = s[(r["customer_id"], engine.kmonth(r["month_key"]))]
        assert r["collected_amount"] == src["amount"]
        assert r["mrr"] == r["mrr_proxy"]
        if not r["is_inferred_price_step"]:
            assert r["mrr_proxy"] == src["amount_normalized"]
        assert r["timing_adjustment"] == r["collected_amount"] - r["mrr"]
        assert r["list_mrr"] is r["discount_mrr"] is r["net_mrr"] is r["billed_amount"] is None
        assert r["mrr_basis"] == "cash_proxy" and r["currency_status"] == "unconfirmed"
        assert (r["mrr"] > 0) == (r["lifecycle_state"] in ("new", "paying", "reactivated", "settled_gap"))
    assert all(r["mrr_value"] == r["mrr"] * 10000 for r in cm)


def test_movement_columns():
    mv = golden()["tables"]["fact_mrr_movement"]
    assert all(r["item_id"] == "-" and r["discount_id"] == "-" for r in mv)
    assert all(r["amount"] != 0 for r in mv)
    pk = {(r["customer_id"], r["month_key"], r["movement_type"], r["item_id"], r["discount_id"]) for r in mv}
    assert len(pk) == len(mv)
    rules = {r["movement_type"]: r["inference_rule"] for r in mv if r["is_inferred"]}
    assert rules == {"pause": "GLD-MRR-02.pause", "resume": "GLD-MRR-02.resume",
                     "inferred_price_step": "GLD-MRR-01", "first_payment_multiple": "GLD-MRR-02.7b"}
    assert {r["driver"] for r in mv if r["movement_type"] == "first_payment_multiple"} == {"timing"}
    assert {r["driver"] for r in mv if r["movement_type"] == "inferred_price_step"} == {"pricing"}


# --------------------------------------------------------------------------- #
# Serving snapshot (contract v1)                                              #
# --------------------------------------------------------------------------- #
def test_summary_contract_shape():
    res = golden()
    pay = summary.build(res, CFG, META)
    assert pay["run"]["mrr_basis"] == "cash_proxy" and pay["run"]["churn_confirmed_through"] == "2024-08"
    assert pay["statuses"]["discount_data_status"] == "not_available"
    assert [s["code"] for s in pay["steps"]] == [ln["line"] for ln in CFG["lines"] if 1 <= ln["line_order"] <= 16]
    assert all({"code", "label", "driver", "order"} <= set(s) for s in pay["steps"])
    assert {d["code"]: d["available"] for d in pay["drivers"]} == {"behaviour": True, "pricing": True,
                                                                  "discount": False, "timing": True}
    assert len(pay["months"]) == 33 and pay["months"][0]["month"] == "2022-02"
    last = pay["months"][-1]
    assert last["opening_mrr_value"] == "92747125.17" and last["closing_mrr_value"] == "96360646.83"
    assert last["cash_value"] == "97007446.83" and last["timing_value"] == "646800.00"
    for code in ("discount_start", "discount_change", "discount_base_effect", "discount_end",
                 "discount_released_on_churn", "list_price_change"):
        assert last["step_value"][code] is None and last["step_customers"][code] is None
    assert last["step_value"]["churn"] == "0.00" and last["step_customers"]["churn"] == 0
    assert last["null_reason"] == {"discount": "no_billing_data", "list": "no_billing_data"}
    assert last["timing_lines"] == {"timing_arrears": "646800.00", "timing_prepay": "0.00", "timing_split": "0.00",
                                    "timing_uneven_split": "0.00", "timing_late_price_step": "0.00"}
    assert [(s["code"], s["order"], s["driver"]) for s in pay["steps"]][-1] == ("first_payment_multiple", 16, "timing")
    assert next(d for d in pay["drivers"] if d["code"] == "timing")["in_mrr"] is True
    assert last["is_provisional"] and last["is_complete"]
    pages = summary.movement_pages(res, CFG, RUN)
    assert summary.check_contract(pay, pages) == []
    assert len(pages) == 23 and pages[0]["total"] == 4589 and all(len(p["movements"]) == 200 for p in pages[:-1])
    flat = [m for p in pages for m in p["movements"]]
    ch = [abs(D(m["change_value"])) for m in flat]
    assert ch == sorted(ch, reverse=True)
    assert sum(1 for m in flat if "late_price_step" in m["flags"]) == 140
    assert sum(1 for m in flat if "one_off_spike" in m["flags"]) == 222
    # per customer-month the rows sum to the MRR change
    for m in flat[:300]:
        assert D(m["mrr_after_value"]) - D(m["mrr_before_value"]) == D(m["change_value"])
    assert "name" not in flat[0] and not any("Cliente" in str(v) for v in flat[0].values())


# --------------------------------------------------------------------------- #
# Synthetic edge cases                                                        #
# --------------------------------------------------------------------------- #
def test_price_step_scan_and_tagging():
    p = D
    xs = [p(5), p(5), p("5.4"), p("5.2"), p("5.2"), p("5.2")]
    assert engine.price_steps(xs, ["paying"] * 6, [None] * 6, {"paying"}) == [1]
    # a settlement in the window, or a non-paying month, blocks the match
    assert engine.price_steps(xs, ["paying"] * 6, [None, None, "arrears", None, None, None], {"paying"}) == []
    assert engine.price_steps(xs, ["new"] + ["paying"] * 5, [None] * 6, {"paying"}) == []
    # unchanged price: no match
    assert engine.price_steps([p(5)] * 6, ["paying"] * 6, [None] * 6, {"paying"}) == []


def test_failed_control_blocks_publish():
    s = copy.deepcopy(silver_inputs())
    # tamper: a CRO-05 figure that no longer reconciles (GC-MRR-4)
    s["customer_month"][100]["expansion_amount"] = D("1.000000")
    res = engine.build(s, CFG, META)
    assert {c["control"] for c in res["controls"] if not c["passed"]} == {"GC-MRR-4"}
    with pytest.raises(engine.MrrControlError):
        engine.assert_controls(res)


def test_hole_month_has_no_bridge():
    s = copy.deepcopy(silver_inputs())
    r = next(r for r in s["customer_month"] if r["month"] == "2023-05" and r["lifecycle_state"] == "paying")
    r.update(is_hole=True, amount=None, amount_value=None, amount_normalized=None, hole_reason="excluded_row")
    res = engine.build(s, CFG, META)
    b = {(engine.kmonth(x["month_key"]), x["line"]): x for x in res["tables"]["agg_mrr_bridge_month"]}
    assert b[("2023-05", "closing")]["amount"] is None and b[("2023-06", "opening")]["amount"] is None
    assert b[("2023-04", "closing")]["amount"] is not None
    pay = summary.build(res, CFG, META)
    m = {x["month"]: x for x in pay["months"]}
    assert not m["2023-05"]["is_complete"] and m["2023-05"]["closing_mrr_value"] is None
    assert m["2023-05"]["null_reason"]["mrr"] == "hole"
    # the month bridge and GC-MRR-2 still hold where both months are known; GC-MRR-0 flags the cash
    failed = {c["control"] for c in res["controls"] if not c["passed"]}
    assert "GC-MRR-2" not in failed and "GC-MRR-3" not in failed


def test_writer_refuses_acquisition_tables():
    pytest.importorskip("pyspark")
    from gold_mrr import iceberg_io

    w = iceberg_io.MrrWriter(spark=None, catalog="glue_catalog")
    with pytest.raises(PermissionError):
        w.fq("fact_customer_month_revenue")
    assert w.fq("fact_mrr_movement") == "glue_catalog.finora_gold.fact_mrr_movement"
