#!/usr/bin/env python3
"""Builds the MRR mock fixtures (contracts/mrr_api_contract.md v1): summary.json and movements.json.

MOCK ONLY. Run it from the repo root with the infra venv (it only reads data/ and etl/):

    infra/.venv/bin/python -I dashboard/mocks/mrr/generate_fixture.py

It implements docs/mrr_discounts_model.md §6 (the CDO's gold build spec) exactly, on today's
real files through the silver engine, so the page shows the numbers the gold snapshot will:
GLD-MRR-01 (late price step), GLD-MRR-02 (one movement per customer-month, first match wins),
GLD-MRR-03 (flags), the mrr lines 1-16 and the cash lines 20-24 of agg_mrr_bridge_month.
Every §6.6 expected figure and the run controls GC-MRR-1..4 are asserted before writing.
Lines that cannot be observed on cash_proxy (list_price_change and the discount lines) are null.
"""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "etl"))

from common import config  # noqa: E402
from common.records import make_bronze, strip_bronze  # noqa: E402
from silver_build.engine import DatasetInput, build  # noqa: E402

FILES = {"transactions": ("transactions/Transactions.csv", "Transactions.csv"),
         "industry": ("industry/Industry.csv", "Industry.csv"),
         "sm_spend": ("s_and_m/S&M_spend.csv", "S&M_spend.csv")}
SCALE = Decimal(10_000)
ACTIVE = {"new", "paying", "reactivated", "settled_gap"}
ZERO = Decimal(0)

DRIVERS = [
    {"code": "behaviour", "label": "Customer behaviour", "inferred": False, "available": True},
    {"code": "pricing", "label": "Pricing", "inferred": True, "available": True},
    {"code": "discount", "label": "Discounts", "inferred": False, "available": False},
    # §6: first_payment_multiple is an mrr line with driver timing; the cash lines reconcile MRR to cash.
    {"code": "timing", "label": "Timing of payments", "inferred": False, "available": True, "in_mrr": True},
]
# agg_mrr_bridge_month, section mrr, lines 1-16 (line_order = order).
STEPS = [
    (1, "new", "New", "behaviour"),
    (2, "reactivation", "Reactivation", "behaviour"),
    (3, "expansion", "Expansion", "behaviour"),
    (4, "contraction", "Contraction", "behaviour"),
    (5, "churn", "Churn", "behaviour"),
    (6, "pause", "Paused (unpaid 1–2 months)", "behaviour"),
    (7, "resume", "Resumed after a pause", "behaviour"),
    (8, "grace_drop", "Unpaid, not yet churn", "behaviour"),
    (9, "list_price_change", "List price changes", "pricing"),
    (10, "inferred_price_step", "Price steps (inferred)", "pricing"),
    (11, "discount_start", "Discounts started", "discount"),
    (12, "discount_change", "Discount changes", "discount"),
    (13, "discount_base_effect", "Discount base effect", "discount"),
    (14, "discount_end", "Discounts ended", "discount"),
    (15, "discount_released_on_churn", "Discounts released on churn", "discount"),
    (16, "first_payment_multiple", "Prepaid first invoices", "timing"),
]
DRIVER_OF = {code: driver for _, code, _, driver in STEPS}
NULL_LINES = {"list_price_change", "discount_start", "discount_change", "discount_base_effect", "discount_end",
              "discount_released_on_churn"}
INFERRED = {"pause", "resume", "inferred_price_step", "first_payment_multiple"}
CASH_TYPES = ["arrears", "prepay", "split", "uneven_split", "late_price_step"]


def money(native: Decimal) -> str:
    return f"{(native * SCALE).quantize(Decimal('0.01'))}"


def load_silver():
    ts = "2026-11-17T00:00:00Z"
    inputs = {}
    for ds, (key, name) in FILES.items():
        raw = (ROOT / "data" / name).read_bytes()
        staging, _ = strip_bronze(make_bronze(raw, ts))
        inputs[ds] = DatasetInput(staging=staging, source_key=key,
                                  sha256=hashlib.sha256(raw).hexdigest(), ingested_at=ts)
    res = build(inputs, config.load(), "fixture", None)
    return res["silver"], res["W"]


def shift(month, k):
    y, m = map(int, month.split("-"))
    m += k
    while m < 1:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return f"{y:04d}-{m:02d}"


def main():
    silver, W = load_silver()
    as_of = silver["month_control"][0]["as_of_month"]
    churn_confirmed = shift(as_of, -2)
    customers = {c["customer_id"]: c for c in silver["customer"]}
    panel = defaultdict(dict)
    for row in silver["customer_month"]:
        panel[row["customer_id"]][row["month"]] = row
    index = {m: i for i, m in enumerate(W)}

    def amt(row):
        return Decimal(row["amount"]) if row["amount"] is not None else None

    # ---------------------------------------------------------- GLD-MRR-01
    step_start = {}          # customer -> set of m (start month of a late price step)
    tagged = defaultdict(set)
    mrr = defaultdict(dict)  # native mrr_proxy per customer-month
    for cid, months in panel.items():
        for month in W:
            value = months[month]["amount_normalized"]
            mrr[cid][month] = Decimal(value) if value is not None else None
        for i in range(1, len(W) - 2):
            window = [W[i - 1], W[i], W[i + 1], W[i + 2]]
            rows = [months[m] for m in window]
            if any(m in tagged[cid] for m in window):
                continue
            if not all(r["lifecycle_state"] == "paying" and amt(r) is not None and amt(r) > 0 and r["settlement_type"] is None for r in rows):
                continue
            x = [amt(r) for r in rows]
            if x[1] == x[0] and x[1] + x[2] == 2 * x[3] and x[3] != x[0]:
                step_start.setdefault(cid, set()).add(W[i])
                tagged[cid].update({W[i], W[i + 1]})
                mrr[cid][W[i]] = x[3]
                mrr[cid][W[i + 1]] = x[3]

    # ------------------------------------------------------- facts per month
    def state(cid, month):
        return panel[cid][month]["lifecycle_state"]

    for cid in panel:
        for month in W:
            if state(cid, month) not in ACTIVE:
                assert (mrr[cid][month] or ZERO) == ZERO, (cid, month, state(cid, month))

    movements = []
    unmatched = []
    for cid, months in panel.items():
        first_paid = next((m for m in W if amt(months[m]) is not None and amt(months[m]) > 0), None)
        starts = step_start.get(cid, set())
        for prev, month in zip(W, W[1:]):
            a, b = mrr[cid][prev] or ZERO, mrr[cid][month] or ZERO
            delta = b - a
            if delta == 0:
                continue
            s0, s1 = state(cid, prev), state(cid, month)
            if month == first_paid:
                kind, amount = "new", b
            elif s1 == "reactivated":
                kind, amount = "reactivation", b
            elif months[month]["is_churn_event"]:
                kind, amount = "churn", -a
            elif s0 in ACTIVE and s1 == "paused":
                kind, amount = "pause", -a
            elif s0 == "paused" and s1 in ACTIVE:
                kind, amount = "resume", b
            elif s0 in ACTIVE and s1 == "grace":
                kind, amount = "grace_drop", -a
            elif s0 in ACTIVE and s1 in ACTIVE and month in starts:
                kind, amount = "inferred_price_step", delta
            elif s0 == "new" and s1 == "paying" and (a == 2 * b or a == 3 * b):
                kind, amount = "first_payment_multiple", delta
            elif s0 in ACTIVE and s1 in ACTIVE:
                kind, amount = ("expansion" if delta > 0 else "contraction"), delta
            else:
                unmatched.append((cid, month, s0, s1, delta))
                continue
            assert amount == delta, (cid, month, kind, amount, delta)  # GC-MRR-2
            movements.append({"customer_id": cid, "prev": prev, "month": month, "kind": kind, "before": a, "after": b,
                              "amount": amount, "cro05": s0 == "paying" and s1 == "paying",
                              "settlement_type": months[month]["settlement_type"], "flags": []})
    assert not unmatched, unmatched[:5]

    # GLD-MRR-03 flags.
    for m in movements:
        if m["kind"] not in ("expansion", "contraction"):
            continue
        for k in (1, 2, 3):
            later = shift(m["month"], k)
            if later not in index:
                break
            if mrr[m["customer_id"]][later] == m["before"] and state(m["customer_id"], later) in ACTIVE:
                m["flags"].append("one_off_spike" if m["kind"] == "expansion" else "temporary_dip")
                break
    for m in movements:
        if m["kind"] == "inferred_price_step":
            m["flags"].append("late_price_step")

    # Cash lines: timing_adjustment = collected − mrr, by timing_type.
    cash_line = defaultdict(lambda: defaultdict(Decimal))
    collected = defaultdict(Decimal)
    closing = defaultdict(Decimal)
    customers_with_mrr = Counter()
    per_customer_timing = defaultdict(Decimal)
    for cid, months in panel.items():
        for month in W:
            row = months[month]
            c = amt(row) or ZERO
            value = mrr[cid][month] or ZERO
            collected[month] += c
            closing[month] += value
            if value > 0:
                customers_with_mrr[month] += 1
            adj = c - value
            per_customer_timing[cid] += adj
            kind = row["settlement_type"] or ("late_price_step" if month in tagged[cid] else None)
            if adj != 0:
                assert kind is not None, (cid, month, adj)
                cash_line[month][kind] += adj
    assert all(v == 0 for v in per_customer_timing.values()), "GC-MRR-1"

    # ------------------------------------------------------------- months
    by_month = defaultdict(list)
    for m in movements:
        by_month[m["month"]].append(m)
    out_months = []
    for prev, month in zip(W, W[1:]):
        rows = by_month[month]
        step_value, step_customers = {}, {}
        for _, code, _, _ in STEPS:
            if code in NULL_LINES:
                step_value[code], step_customers[code] = None, None
                continue
            picked = [m for m in rows if m["kind"] == code]
            step_value[code] = money(sum((m["amount"] for m in picked), ZERO))
            step_customers[code] = len(picked)
        steps_sum = sum((m["amount"] for m in rows), ZERO)
        assert closing[prev] + steps_sum == closing[month], ("GC-MRR-3 mrr", month)
        assert closing[month] + sum(cash_line[month].values(), ZERO) == collected[month], ("GC-MRR-3 cash", month)
        out_months.append({
            "month": month,
            "opening_mrr_value": money(closing[prev]),
            "closing_mrr_value": money(closing[month]),
            "cash_value": money(collected[month]),
            "timing_value": money(collected[month] - closing[month]),
            "step_value": step_value,
            "step_customers": step_customers,
            "customers_opening": customers_with_mrr[prev],
            "customers_closing": customers_with_mrr[month],
            "list_mrr_value": None,
            "discount_value": None,
            "is_provisional": month > churn_confirmed,
            "is_complete": month <= as_of,
            "null_reason": {"discount": "no_billing_data", "list": "no_billing_data"},
        })

    # ------------------------------------------------- §6.6 expected figures
    D = Decimal
    count = Counter(m["kind"] for m in movements)
    total = defaultdict(Decimal)
    for m in movements:
        total[m["kind"]] += m["amount"]
    by_driver = defaultdict(Decimal)
    for m in movements:
        by_driver[DRIVER_OF[m["kind"]]] += m["amount"]
    assert sum(len(s) for s in step_start.values()) == 140 and len(step_start) == 140, "GLD-MRR-01 windows"
    assert closing[W[0]] == D("3500.030835") and customers_with_mrr[W[0]] == 377, closing[W[0]]
    assert closing[as_of] == D("9636.064683") and customers_with_mrr[as_of] == 1678, closing[as_of]
    assert by_driver["behaviour"] == D("6320.070330"), by_driver["behaviour"]
    assert by_driver["pricing"] == D("57.436743"), by_driver["pricing"]
    assert by_driver["timing"] == D("-241.473225"), by_driver["timing"]
    expected = {"new": (1584, "10548.251196"), "reactivation": (64, "1602.749232"), "expansion": (1116, "3707.896089"),
                "contraction": (897, "-6281.965923"), "churn": (301, "-3486.389529"), "pause": (193, "-1901.644479"),
                "resume": (193, "2457.988533"), "grace_drop": (46, "-326.814789"), "inferred_price_step": (140, "57.436743"),
                "first_payment_multiple": (55, "-241.473225")}
    for kind, (n, value) in expected.items():
        assert (count[kind], total[kind]) == (n, D(value)), (kind, count[kind], total[kind])
    assert len(movements) == 4589, len(movements)
    spikes = [m for m in movements if "one_off_spike" in m["flags"]]
    dips = [m for m in movements if "temporary_dip" in m["flags"]]
    assert (len(spikes), sum((m["amount"] for m in spikes), ZERO)) == (222, D("1325.161824")), (len(spikes), sum(m["amount"] for m in spikes))
    assert (len(dips), sum((m["amount"] for m in dips), ZERO)) == (31, D("-110.196093")), (len(dips), sum(m["amount"] for m in dips))
    covered = sum((m["amount"] for m in movements if m["kind"] in ("expansion", "contraction") and m["cro05"]), ZERO)
    assert covered + total["inferred_price_step"] == D("-1156.634330"), "GC-MRR-4"
    oct_ = next(m for m in out_months if m["month"] == "2024-10")
    assert (oct_["opening_mrr_value"], oct_["closing_mrr_value"], oct_["cash_value"]) == ("92747125.17", "96360646.83", "97007446.83"), oct_
    assert {k: oct_["step_value"][k] for k in ("new", "reactivation", "expansion", "contraction", "resume", "grace_drop", "first_payment_multiple")} == {
        "new": "2201333.40", "reactivation": "2179449.93", "expansion": "2129003.52", "contraction": "-1748039.37",
        "resume": "1160086.20", "grace_drop": "-2300122.02", "first_payment_multiple": "-8190.00"}, oct_["step_value"]
    assert cash_line["2024-10"]["arrears"] == D("64.680000")

    summary = {
        "run": {
            "run_id": "r20261117T190000Z",
            "silver_run_id": "r20261117T150932Z",
            "built_at": "2026-11-17T19:08:00Z",
            "as_of_month": as_of,
            "data_complete_through": as_of,
            "churn_confirmed_through": churn_confirmed,
            "gold_model_version": "sha256:mrr-mock-fixture-not-a-real-model-hash",
            "mrr_basis": "cash_proxy",
        },
        "statuses": {"currency_status": "unconfirmed", "revenue_basis_status": "unconfirmed",
                     "pricing_status": "inferred", "discount_data_status": "not_available",
                     "list_price_status": "not_available"},
        "drivers": DRIVERS,
        "steps": [{"code": code, "label": label, "driver": driver, "order": order} for order, code, label, driver in STEPS],
        "months": out_months,
    }
    rows = sorted(
        ({
            "customer_id": m["customer_id"], "month": m["month"], "step": m["kind"],
            "driver": DRIVER_OF[m["kind"]], "inferred": m["kind"] in INFERRED,
            "industry_code": customers[m["customer_id"]]["industry_code"],
            "mrr_before_value": money(m["before"]), "mrr_after_value": money(m["after"]),
            "change_value": money(m["amount"]),
            "list_before_value": None, "list_after_value": None,
            "discount_before_value": None, "discount_after_value": None,
            "settlement_type": m["settlement_type"], "flags": m["flags"],
        } for m in movements),
        key=lambda r: (-abs(Decimal(r["change_value"])), r["month"], r["customer_id"]),
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    (OUT / "movements.json").write_text(json.dumps(rows, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote summary.json ({len(out_months)} months) and movements.json ({len(rows)} rows); "
          "§6.6 figures and GC-MRR-1..4 hold")


if __name__ == "__main__":
    main()
