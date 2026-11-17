"""The MRR dashboard snapshot (contracts/mrr_api_contract.md v1):

  mrr/runs/<run_id>/summary.json              the GET /api/mrr/summary payload
  mrr/runs/<run_id>/movements/page-<n>.json   every non-zero movement, |change| descending, 200 per page

Money is an exact decimal string in full units (`_value`, native x 10,000), or
null where the value is not known: null never means 0. Steps are the CDO's
movement_type codes (docs/mrr_discounts_model.md §6.3 lines 1-16) with their
order and driver; the lines that cannot be observed on cash_proxy are null with
null_reason no_billing_data.
"""

from __future__ import annotations

from decimal import Decimal

from gold_mrr import engine

DRIVERS = [("behaviour", "Customer behaviour"), ("pricing", "Pricing"), ("discount", "Discounts"),
           ("timing", "Timing of payments")]


def _s(v) -> str | None:
    return None if v is None else str(engine.full(v))


def _step_lines(cfg: dict) -> list[dict]:
    return [ln for ln in cfg["lines"] if ln["section"] == "mrr" and ln["line"] not in ("opening", "closing")]


def build(res: dict, cfg: dict, meta: dict) -> dict:
    steps = _step_lines(cfg)
    cash_lines = [ln for ln in cfg["lines"] if ln["section"] == "cash" and ln["line"] != "collected"]
    nr = cfg["params"]["null_reason_cash_proxy"]
    W, cct = res["W"], res["churn_confirmed_through"]
    as_of = res["as_of_month"]
    months = []
    for m in W[1:]:
        v = res["bridge"][m]
        complete = v["opening"][0] is not None and m <= as_of
        op, cl, col = (v[k][0] if complete else None for k in ("opening", "closing", "collected"))
        months.append({
            "month": m,
            "opening_mrr_value": _s(op), "closing_mrr_value": _s(cl), "cash_value": _s(col),
            "timing_value": _s(col - cl) if complete else None,
            "timing_lines": {ln["line"]: _s(v[ln["line"]][0]) if complete else None for ln in cash_lines},
            "step_value": {ln["line"]: _s(v[ln["line"]][0]) if complete else None for ln in steps},
            "step_customers": {ln["line"]: v[ln["line"]][1] if complete else None for ln in steps},
            "customers_opening": v["opening"][1] if complete else None,
            "customers_closing": v["closing"][1] if complete else None,
            "list_mrr_value": None, "discount_value": None,
            "is_provisional": cct is None or m > cct,
            "is_complete": complete,
            "null_reason": {"discount": nr, "list": nr} if complete else
                           {"discount": nr, "list": nr, "mrr": "hole" if m <= as_of else "after_data_complete_through"},
        })
    observable = {d: any(ln["observable_on_cash_proxy"] for ln in steps if ln["driver"] == d) for d, _ in DRIVERS}
    inferred = {d: all(ln["is_inferred"] for ln in steps if ln["driver"] == d and ln["observable_on_cash_proxy"])
                for d, _ in DRIVERS}
    return {
        "run": {"run_id": meta["run_id"], "silver_run_id": meta["silver_run_id"],
                "built_at": meta["built_at"].strftime("%Y-%m-%dT%H:%M:%SZ"), "as_of_month": as_of,
                "data_complete_through": as_of, "churn_confirmed_through": cct,
                "gold_model_version": cfg["gold_model_version"], "mrr_basis": res["mrr_basis"]},
        "statuses": {"currency_status": res["currency_status"], "revenue_basis_status": res["revenue_basis_status"],
                     "pricing_status": "inferred", "discount_data_status": "not_available",
                     "list_price_status": "not_available"},
        "drivers": [{"code": d, "label": label, "inferred": inferred[d] and observable[d],
                     "available": observable[d],
                     # timing has an MRR step (first_payment_multiple, line 16) and the cash level
                     **({"in_mrr": True} if d == "timing" else {})} for d, label in DRIVERS],
        "steps": [{"code": ln["line"], "label": ln["label"], "driver": ln["driver"], "order": ln["line_order"],
                   "inferred": ln["is_inferred"], "available": ln["observable_on_cash_proxy"],
                   **({} if ln["observable_on_cash_proxy"] else {"null_reason": nr})} for ln in steps],
        "months": months,
    }


def movement_pages(res: dict, cfg: dict, run_id: str) -> list[dict]:
    """Every fact_mrr_movement row (all have a non-zero change), sorted by |change|
    descending (ties: month, customer, line order), in pages of page_size."""
    T = res["tables"]
    order = {ln["line"]: ln["line_order"] for ln in cfg["lines"]}
    code = {i["industry_key"]: i["industry_code"] for i in cfg["industries"]}
    cm = {(r["customer_id"], r["month_key"]): r for r in T["fact_customer_month_mrr"]}
    prev_key = {}
    W = res["W"]
    for i in range(1, len(W)):
        prev_key[engine.mkey(W[i])] = engine.mkey(W[i - 1])
    rows = []
    for r in T["fact_mrr_movement"]:
        before = cm[(r["customer_id"], prev_key[r["month_key"]])]
        after = cm[(r["customer_id"], r["month_key"])]
        flags = []
        if r["movement_type"] == "inferred_price_step":
            flags.append("late_price_step")
        if r["is_temporary_dip"]:
            flags.append("temporary_dip")
        if r["is_one_off_spike"]:
            flags.append("one_off_spike")
        rows.append({
            "customer_id": r["customer_id"], "month": engine.kmonth(r["month_key"]), "step": r["movement_type"],
            "driver": r["driver"], "inferred": r["is_inferred"],
            "industry_code": code.get(r["industry_key"], "UNMAPPED"),
            "mrr_before_value": str(before["mrr_value"]), "mrr_after_value": str(after["mrr_value"]),
            "change_value": str(r["amount_value"]),
            "list_before_value": None, "list_after_value": None,
            "discount_before_value": None, "discount_after_value": None,
            "settlement_type": None if after["timing_type"] in (None, "late_price_step") else after["timing_type"],
            "is_provisional": r["is_provisional"], "flags": flags,
            "_sort": (-abs(r["amount_value"]), r["month_key"], r["customer_id"], order[r["movement_type"]])})
    rows.sort(key=lambda x: x["_sort"])
    for x in rows:
        del x["_sort"]
    size = cfg["params"]["page_size"]
    pages = max(1, -(-len(rows) // size))
    return [{"run_id": run_id, "total": len(rows), "page": p + 1, "page_size": size, "pages": pages,
             "sort": "abs_desc", "movements": rows[p * size:(p + 1) * size]} for p in range(pages)]


def check_contract(payload: dict, pages: list[dict]) -> list[str]:
    """The contract identities, re-checked on the serialized payload (strings), as the UI
    does: month bridge, continuity and the full-period identity, plus the page totals."""
    errs = []
    ms = [m for m in payload["months"] if m["is_complete"]]
    for m in ms:
        tot = Decimal(m["opening_mrr_value"]) + sum((Decimal(v) for v in m["step_value"].values() if v is not None),
                                                    Decimal(0))
        if tot != Decimal(m["closing_mrr_value"]):
            errs.append(f"month bridge {m['month']}")
        if Decimal(m["closing_mrr_value"]) + Decimal(m["timing_value"]) != Decimal(m["cash_value"]):
            errs.append(f"cash {m['month']}")
    for a, b in zip(ms, ms[1:]):
        if a["closing_mrr_value"] != b["opening_mrr_value"]:
            errs.append(f"continuity {b['month']}")
    n = sum(len(p["movements"]) for p in pages)
    if pages and n != pages[0]["total"]:
        errs.append("movement pages total")
    step_n = sum(v for m in payload["months"] for v in m["step_customers"].values() if v is not None)
    if step_n != n:
        errs.append(f"movement rows {n} != step_customers {step_n}")
    return errs
