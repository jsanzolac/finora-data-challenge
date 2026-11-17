"""Gold MRR engine (docs/mrr_discounts_model.md §6, phase 1, mrr_basis = cash_proxy).

Pure Python, exact Decimal: silver rows in, gold MRR rows out, plus the run
controls GC-MRR-1..5 and the contract identities (contracts/mrr_api_contract.md
v1: month bridge, continuity, period). The Glue job reads silver at its run tag
and writes these rows through write-audit-publish (iceberg_io.py); the tests
call build() directly on the silver engine's output.

Rules (all from §6.4):
  GLD-MRR-01  late price step (inferred): mrr_proxy of m and m+1 = x_{m+2}
  GLD-MRR-02  one movement per customer-month with delta != 0, first match wins
  GLD-MRR-03  one-off spike / temporary dip flags on expansion and contraction (inferred)
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

Q2 = Decimal("0.01")
REV = Decimal(10000)
ZERO = Decimal(0)


class MrrControlError(RuntimeError):
    pass


def mkey(m: str) -> int:
    return int(m[:4]) * 100 + int(m[5:7])


def kmonth(k: int) -> str:
    return f"{k // 100:04d}-{k % 100:02d}"


def full(v: Decimal | None) -> Decimal | None:
    """Native x 10,000 at 2 dp. Exact for 6-dp native values (checked by the caller's controls)."""
    if v is None:
        return None
    out = (v * REV).quantize(Q2)
    if out != v * REV:
        raise MrrControlError(f"units: {v} x 10,000 is not exact at 2 decimals")
    return out


def _uniform(rows: list[dict], col: str, what: str):
    vals = {r[col] for r in rows}
    if len(vals) > 1:
        raise MrrControlError(f"input: silver {what} rows carry more than one {col}: {sorted(map(str, vals))}")
    return next(iter(vals)) if vals else None


def _sum(vals) -> Decimal:
    return sum((v for v in vals if v is not None), ZERO)


def price_steps(xs: list, states: list, settle: list, allowed: set) -> list[int]:
    """GLD-MRR-01 on one customer's months (index i = month m). Returns the indexes m of
    the matched windows m-1 .. m+2, scanning m upward; months m and m+1 of a match are
    tagged and never re-tagged."""
    tagged: set[int] = set()
    out = []
    for i in range(1, len(xs) - 2):
        win = (i - 1, i, i + 1, i + 2)
        if any(j in tagged for j in win):
            continue
        if any(states[j] not in allowed or settle[j] is not None or xs[j] is None or xs[j] <= 0 for j in win):
            continue
        x0, x1, x2, x3 = (xs[j] for j in win)
        if x1 == x0 and x1 + x2 == 2 * x3 and x3 != x0:
            out.append(i)
            tagged.update((i, i + 1))
    return out


def build(silver: dict[str, list[dict]], cfg: dict, meta: dict) -> dict:
    """meta: run_id, silver_run_id, built_at (aware UTC datetime), gold_model_version."""
    p = cfg["params"]
    basis = p["mrr_basis"]
    if basis != "cash_proxy":
        raise MrrControlError("GC-MRR-5: only mrr_basis cash_proxy is implemented (phase 1)")
    active = set(p["active_states"])
    run_id, silver_run_id = meta["run_id"], meta["silver_run_id"]
    for t, rows in silver.items():
        rid = _uniform(rows, "_run_id", t)
        if rows and rid != silver_run_id:
            raise MrrControlError(f"input: silver {t} rows are from run {rid}, not {silver_run_id}")
    rules_version = _uniform([r for rows in silver.values() for r in rows], "_rules_version", "input")
    as_of = _uniform(silver["customer"] + silver["month_control"], "as_of_month", "customer/month_control")
    tx_sha = _uniform(silver["customer_month"], "_source_sha256", "customer_month")
    ind_sha = _uniform(silver["customer"], "_industry_source_sha256", "customer")
    mc = {r["month"]: r for r in silver["month_control"]}
    W = sorted(mc)
    if len(W) < 2:
        raise MrrControlError("input: silver month_control has fewer than two months")
    n = len(W)
    confirmed = [m for m in W if mc[m]["is_churn_confirmed"]]
    cct = max(confirmed) if confirmed else None
    src = {r["dataset_id"]: r for r in silver["source_status"]}.get("transactions", {})
    currency_status = src.get("currency_status") or "unconfirmed"
    built_at = meta["built_at"]

    def lin(uses_tx: bool, uses_ind: bool) -> dict:
        return {"_run_id": run_id, "_silver_run_id": silver_run_id, "_rules_version": rules_version,
                "_gold_model_version": meta["gold_model_version"],
                "_transactions_sha256": tx_sha if uses_tx else None,
                "_industry_sha256": ind_sha if uses_ind else None, "_sm_spend_sha256": None,
                "as_of_month": as_of, "_built_at": built_at}

    ind_key = {i["industry_code"]: i["industry_key"] for i in cfg["industries"]}
    unmapped = cfg["unmapped_industry_key"]
    cust = {r["customer_id"]: r for r in silver["customer"]}
    panel: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in silver["customer_month"]:
        if r["customer_id"] not in cust:
            raise MrrControlError(f"input: customer_month customer {r['customer_id']} is not in silver customer")
        if r["month"] not in mc:
            raise MrrControlError(f"input: customer_month month {r['month']} is not in W")
        if r["month"] in panel[r["customer_id"]]:
            raise MrrControlError(f"input: duplicate customer_month ({r['customer_id']}, {r['month']})")
        panel[r["customer_id"]][r["month"]] = r
    for c in cust:
        if len(panel.get(c, {})) != n:
            raise MrrControlError(f"input: customer {c} does not have a dense panel over W")

    lines = {ln["line"]: ln for ln in cfg["lines"]}
    order = {ln["line"]: ln["line_order"] for ln in cfg["lines"]}
    T: dict[str, list[dict]] = {"dim_movement_type": [], "fact_customer_month_mrr": [], "fact_mrr_movement": [],
                                "agg_mrr_bridge_month": []}
    L = lin(False, False)
    for ln in cfg["lines"]:
        T["dim_movement_type"].append({
            "line": ln["line"], "line_order": ln["line_order"], "section": ln["section"], "driver": ln["driver"],
            "label": ln["label"], "is_movement": ln["section"] == "mrr" and ln["line"] not in ("opening", "closing"),
            "is_observable_on_cash_proxy": ln["observable_on_cash_proxy"], "is_inferred": ln["is_inferred"],
            "inference_rule": ln["inference_rule"], **L})

    # ---- fact_customer_month_mrr (§6.1) and GLD-MRR-01
    L_cm, L_mv = lin(True, True), lin(True, True)
    mrr: dict[int, list] = {}
    state: dict[int, list] = {}
    steps_at: dict[int, set] = {}
    windows = 0
    hole_months: set[int] = set()
    timing_types = set(p["timing_types"])
    for c in sorted(cust):
        rows = [panel[c][m] for m in W]
        xs = [r["amount"] for r in rows]
        st = [r["lifecycle_state"] for r in rows]
        idx = price_steps(xs, st, [r["settlement_type"] for r in rows], set(p["price_step_states"]))
        windows += len(idx)
        steps_at[c] = set(idx)
        proxy = [r["amount_normalized"] for r in rows]
        step_month = {}
        for i in idx:
            proxy[i] = proxy[i + 1] = xs[i + 2]
            step_month[i] = step_month[i + 1] = W[i]
        cr = cust[c]
        ik = ind_key.get(cr["industry_code"], unmapped)
        coh = mkey(cr["cohort_month"]) if cr["cohort_month"] else None
        mrr[c] = [None if r["is_hole"] else proxy[i] for i, r in enumerate(rows)]
        state[c] = st
        for i, r in enumerate(rows):
            m = W[i]
            if r["is_hole"]:
                hole_months.add(i)
            if proxy[i] is not None and proxy[i] < 0:
                raise MrrControlError(f"input: negative mrr_proxy for customer {c} in {m}")
            v = mrr[c][i]
            col = None if r["is_hole"] else r["amount"]
            tadj = col - v if col is not None and v is not None else None
            if r["settlement_type"] in timing_types:
                ttype = r["settlement_type"]
            elif i in step_month:
                ttype = "late_price_step"
            elif r["settlement_type"] is not None:
                raise MrrControlError(f"input: unknown settlement_type {r['settlement_type']!r}")
            else:
                ttype = None
            if ttype is None and tadj not in (None, ZERO):
                raise MrrControlError(f"GC-MRR-3: customer {c} {m} has a timing adjustment with no timing type")
            T["fact_customer_month_mrr"].append({
                "customer_id": c, "month_key": mkey(m), "industry_key": ik, "cohort_month_key": coh,
                "lifecycle_state": r["lifecycle_state"], "mrr_basis": basis,
                "collected_amount": col, "collected_amount_value": full(col),
                "mrr_proxy": proxy[i], "mrr_proxy_value": full(proxy[i]),
                "list_mrr": None, "list_mrr_value": None, "discount_mrr": None, "discount_mrr_value": None,
                "net_mrr": None, "net_mrr_value": None, "billed_amount": None, "billed_amount_value": None,
                "mrr": v, "mrr_value": full(v), "timing_adjustment": tadj, "timing_adjustment_value": full(tadj),
                "timing_type": ttype, "is_inferred_price_step": i in step_month,
                "price_step_start_month": step_month.get(i), "is_hole": r["is_hole"],
                "is_provisional": cct is None or m > cct, "currency_status": currency_status,
                "_source_key": r["_source_key"], "_ingested_at": r["_ingested_at"], **L_cm})

    # ---- fact_mrr_movement (§6.2): GLD-MRR-02 and GLD-MRR-03
    mult = {Decimal(k) for k in p["first_payment_multiples"]}
    no_item = p["no_item"]
    unclassified = []
    delta_mismatch = []
    by_cm: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for c in sorted(cust):
        rows = [panel[c][m] for m in W]
        M, st = mrr[c], state[c]
        first = next((i for i, r in enumerate(rows) if r["amount"] is not None and r["amount"] > 0), None)
        cr = cust[c]
        for i in range(1, n):
            a, b = M[i - 1], M[i]
            if a is None or b is None:
                continue
            d = b - a
            if d == 0:
                continue
            ps, s = st[i - 1], st[i]
            if i == first:
                mt, amt = "new", b
            elif s == "reactivated":
                mt, amt = "reactivation", b
            elif rows[i]["is_churn_event"]:
                mt, amt = "churn", -a
            elif ps in active and s == "paused":
                mt, amt = "pause", -a
            elif ps == "paused" and s in active:
                mt, amt = "resume", b
            elif ps in active and s == "grace":
                mt, amt = "grace_drop", -a
            elif ps in active and s in active:
                if i in steps_at[c]:
                    mt = "inferred_price_step"
                elif ps == "new" and s == "paying" and any(a == k * b for k in mult):
                    mt = "first_payment_multiple"
                else:
                    mt = "expansion" if d > 0 else "contraction"
                amt = d
            else:
                unclassified.append((c, W[i]))
                continue
            if amt != d:
                delta_mismatch.append((c, W[i], mt))
            ln = lines[mt]
            flag_spike = flag_dip = False
            if mt in ("expansion", "contraction"):
                for k in p["flag_return_months"]:
                    j = i + k
                    if j < n and M[j] is not None and M[j] == a and st[j] in active:
                        flag_spike, flag_dip = mt == "expansion", mt == "contraction"
                        break
            row = {
                "customer_id": c, "month_key": mkey(W[i]), "industry_key": ind_key.get(cr["industry_code"], unmapped),
                "cohort_month_key": mkey(cr["cohort_month"]) if cr["cohort_month"] else None,
                "movement_type": mt, "driver": ln["driver"], "amount": amt, "amount_value": full(amt),
                "prior_state": ps, "state": s, "is_inferred": ln["is_inferred"], "inference_rule": ln["inference_rule"],
                "cro05_covered": ps == "paying" and s == "paying", "is_one_off_spike": flag_spike,
                "is_temporary_dip": flag_dip, "is_outlier_customer": bool(cr["is_outlier_customer"]),
                "is_provisional": cct is None or W[i] > cct, "mrr_basis": basis, "item_id": no_item,
                "discount_id": no_item, "price_book_version": None, "discount_reason_key": None, **L_mv}
            T["fact_mrr_movement"].append(row)
            by_cm[(c, i)].append(row)

    # ---- agg_mrr_bridge_month (§6.3)
    L_b = lin(True, False)
    mv_by_month: dict[int, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in T["fact_mrr_movement"]:
        mv_by_month[r["month_key"]][r["movement_type"]].append(r)
    cm_by_month: dict[int, list[dict]] = defaultdict(list)
    for r in T["fact_customer_month_mrr"]:
        cm_by_month[r["month_key"]].append(r)
    bridge: dict[str, dict[str, tuple]] = {}
    for i in range(1, n):
        m, k = W[i], mkey(W[i])
        holed = i in hole_months or (i - 1) in hole_months
        prev, cur = cm_by_month[mkey(W[i - 1])], cm_by_month[k]
        vals: dict[str, tuple] = {}
        for ln in cfg["lines"]:
            name = ln["line"]
            if holed:
                amt, ev = None, None
            elif name == "opening":
                amt, ev = _sum(r["mrr"] for r in prev), sum(1 for r in prev if (r["mrr"] or 0) > 0)
            elif name == "closing":
                amt, ev = _sum(r["mrr"] for r in cur), sum(1 for r in cur if (r["mrr"] or 0) > 0)
            elif name == "collected":
                amt, ev = _sum(r["collected_amount"] for r in cur), sum(1 for r in cur if (r["collected_amount"] or 0) > 0)
            elif ln["section"] == "cash":
                tt = name[len("timing_"):]
                rs = [r for r in cur if r["timing_type"] == tt]
                amt, ev = _sum(r["timing_adjustment"] for r in rs), len(rs)
            elif not ln["observable_on_cash_proxy"]:
                amt, ev = None, None  # GC-MRR-5: unknown, not absent
            else:
                rs = mv_by_month[k].get(name, [])
                amt, ev = _sum(r["amount"] for r in rs), len(rs)
            vals[name] = (amt, ev)
            T["agg_mrr_bridge_month"].append({
                "month_key": k, "section": ln["section"], "line": name, "line_order": ln["line_order"],
                "driver": ln["driver"], "amount": amt, "amount_value": full(amt), "events": ev, "mrr_basis": basis,
                "is_provisional": cct is None or m > cct, **L_b})
        bridge[m] = vals

    res = {"tables": T, "W": W, "as_of_month": as_of, "churn_confirmed_through": cct, "bridge": bridge,
           "hole_months": sorted(W[i] for i in hole_months), "currency_status": currency_status,
           "revenue_basis_status": src.get("basis_status") or "unconfirmed", "price_step_windows": windows,
           "mrr_basis": basis}
    res["controls"] = controls(res, silver, cfg, unclassified, delta_mismatch, by_cm, mrr)
    res["figures"] = figures(res, cfg)
    return res


# --------------------------------------------------------------------------- #
# Run controls                                                                #
# --------------------------------------------------------------------------- #
def controls(res: dict, silver: dict, cfg: dict, unclassified, delta_mismatch, by_cm, mrr) -> list[dict]:
    T, W, bridge = res["tables"], res["W"], res["bridge"]
    out = []

    def ctl(cid: str, ok: bool, detail: str) -> None:
        out.append({"control": cid, "passed": bool(ok), "detail": detail})

    cm = T["fact_customer_month_mrr"]
    mvl = [ln["line"] for ln in cfg["lines"] if ln["section"] == "mrr" and ln["line"] not in ("opening", "closing")]
    cashl = [ln["line"] for ln in cfg["lines"] if ln["section"] == "cash" and ln["line"] != "collected"]
    unobs = [ln["line"] for ln in cfg["lines"] if not ln["observable_on_cash_proxy"]]

    # GC-MRR-0 (input): dense panel and cash totals equal silver
    ctl("GC-MRR-0.rows", len(cm) == len(silver["customer_month"]),
        f"fact_customer_month_mrr {len(cm)} rows, silver customer_month {len(silver['customer_month'])}")
    s_amt = _sum(r["amount"] for r in silver["customer_month"])
    g_amt = _sum(r["collected_amount"] for r in cm)
    ctl("GC-MRR-0.collected", s_amt == g_amt, f"collected {g_amt} vs silver amount {s_amt}")

    # GC-MRR-1: sum mrr_proxy = sum collected per customer
    per = defaultdict(lambda: [ZERO, ZERO])
    for r in cm:
        if r["is_hole"]:
            continue
        per[r["customer_id"]][0] += r["mrr_proxy"]
        per[r["customer_id"]][1] += r["collected_amount"]
    bad = [c for c, (a, b) in per.items() if a != b]
    ctl("GC-MRR-1", not bad, f"{len(per)} customers, {len(bad)} with sum mrr_proxy != sum collected")

    # GC-MRR-2: per customer-month sum of movements = delta mrr; one row per delta != 0
    bad2 = list(delta_mismatch) + [("unclassified",) + u for u in unclassified]
    for (c, i), rows in by_cm.items():
        if len(rows) != 1 or _sum(r["amount"] for r in rows) != mrr[c][i] - mrr[c][i - 1]:
            bad2.append((c, W[i]))
    for c, M in mrr.items():
        for i in range(1, len(W)):
            if M[i] is not None and M[i - 1] is not None and M[i] != M[i - 1] and (c, i) not in by_cm:
                bad2.append((c, W[i], "missing"))
    ctl("GC-MRR-2", not bad2, f"{len(T['fact_mrr_movement'])} movement rows; {len(bad2)} mismatches"
        + (f" (first: {bad2[:3]})" if bad2 else ""))

    # GC-MRR-3 and the contract identities: month bridge, cash bridge, continuity, period
    rev = {r["month"]: r["revenue_total"] for r in silver["month_control"]}
    bad3, cont = [], []
    prev_close = _sum(mrr[c][0] for c in mrr) if 0 not in [W.index(h) for h in res["hole_months"]] else None
    for m in W[1:]:
        v = bridge[m]
        if v["opening"][0] is None:
            prev_close = None
            continue
        op, cl, col = v["opening"][0], v["closing"][0], v["collected"][0]
        if op + _sum(v[x][0] for x in mvl) != cl:
            bad3.append((m, "mrr"))
        if cl + _sum(v[x][0] for x in cashl) != col or col != rev[m]:
            bad3.append((m, "cash"))
        if prev_close is not None and op != prev_close:
            cont.append(m)
        prev_close = cl
    complete = [m for m in W[1:] if bridge[m]["opening"][0] is not None]
    ctl("GC-MRR-3", not bad3, f"{len(complete)} months bridged; {len(bad3)} mismatches {bad3[:3]}")
    ctl("GC-MRR-3.continuity", not cont, f"opening(t) = closing(t-1): {len(cont)} breaks {cont[:3]}")
    if complete and len(complete) == len(W) - 1:
        first, last = W[0], W[-1]
        cash0 = rev[first]
        mrr0 = _sum(mrr[c][0] for c in mrr)
        steps = _sum(_sum(bridge[m][x][0] for x in mvl) for m in complete)
        timing_last = bridge[last]["collected"][0] - bridge[last]["closing"][0]
        timing0 = cash0 - mrr0
        ok = steps + (timing_last - timing0) == bridge[last]["collected"][0] - cash0
        ctl("contract.period", ok, f"full period {W[1]}..{last}: steps {steps} + timing change "
            f"{timing_last - timing0} = cash change {bridge[last]['collected'][0] - cash0}")

    # GC-MRR-4: CRO-05 reconciliation
    mv = T["fact_mrr_movement"]
    lhs = _sum(r["amount"] for r in mv if r["cro05_covered"] and r["movement_type"] in ("expansion", "contraction")) \
        + _sum(r["amount"] for r in mv if r["movement_type"] == "inferred_price_step")
    rhs = _sum(r["expansion_amount"] for r in silver["customer_month"]) \
        - _sum(r["contraction_amount"] for r in silver["customer_month"])
    ctl("GC-MRR-4", lhs == rhs, f"covered expansion + contraction + inferred_price_step {lhs} = CRO-05 net {rhs}")

    # GC-MRR-5: unobservable lines and billing columns are NULL on cash_proxy
    b5 = [r for r in T["agg_mrr_bridge_month"] if r["line"] in unobs and r["amount"] is not None]
    b5 += [r for r in cm if any(r[k] is not None for k in ("list_mrr", "discount_mrr", "net_mrr", "billed_amount"))]
    ctl("GC-MRR-5", not b5, f"{len(b5)} non-NULL billing values on cash_proxy")

    # Domain and lineage
    dom = {ln["line"] for ln in cfg["lines"]}
    ctl("GC-MRR-domain", all(r["movement_type"] in dom for r in mv), "every movement_type is in dim_movement_type")
    lin_cols = ("_run_id", "_silver_run_id", "_rules_version", "_gold_model_version", "as_of_month", "_built_at")
    nulls = sum(1 for t in T.values() for r in t for k in lin_cols if r.get(k) is None)
    ctl("GC-MRR-lineage", nulls == 0, f"{nulls} NULL lineage cells")
    return out


def assert_controls(res: dict) -> None:
    bad = [c for c in res["controls"] if not c["passed"]]
    if bad:
        raise MrrControlError("run controls failed: " + "; ".join(f"{c['control']}: {c['detail']}" for c in bad))


# --------------------------------------------------------------------------- #
# Figures (run report and tests)                                              #
# --------------------------------------------------------------------------- #
def figures(res: dict, cfg: dict) -> dict:
    T, W, bridge = res["tables"], res["W"], res["bridge"]
    mv = T["fact_mrr_movement"]
    cm = T["fact_customer_month_mrr"]
    s = lambda rows: str(_sum(r["amount"] for r in rows))  # noqa: E731
    by_type = defaultdict(list)
    for r in mv:
        by_type[r["movement_type"]].append(r)
    by_driver = defaultdict(list)
    for r in mv:
        by_driver[r["driver"]].append(r)
    timing = {}
    for tt in cfg["params"]["timing_types"]:
        rs = [r for r in cm if r["timing_type"] == tt]
        timing[tt] = {"rows": len(rs), "abs_sum": str(_sum(abs(r["timing_adjustment"]) for r in rs
                                                         if r["timing_adjustment"] is not None)),
                      "net": str(_sum(r["timing_adjustment"] for r in rs))}
    first, last = W[1], W[-1]
    ob, cb = bridge[first]["opening"], bridge[last]["closing"]
    return {
        "rows": {t: len(v) for t, v in T.items()},
        "period": {"from": first, "to": last, "opening": str(ob[0]), "opening_customers": ob[1],
                   "closing": str(cb[0]), "closing_customers": cb[1],
                   "net_movement": str(cb[0] - ob[0]) if ob[0] is not None and cb[0] is not None else None},
        "drivers": {d: s(rs) for d, rs in sorted(by_driver.items())},
        "lines": {k: {"events": len(v), "amount": s(v)} for k, v in sorted(by_type.items())},
        "covered": {k: {"events": len([r for r in v if r["cro05_covered"]]),
                        "amount": s([r for r in v if r["cro05_covered"]])} for k, v in by_type.items()
                    if k in ("expansion", "contraction")},
        "inferred_rows": sum(1 for r in mv if r["is_inferred"]),
        "price_step_windows": res["price_step_windows"],
        "price_step_customers": len({r["customer_id"] for r in mv if r["movement_type"] == "inferred_price_step"}),
        "flags": {"one_off_spike": {"events": sum(r["is_one_off_spike"] for r in mv),
                                    "amount": s([r for r in mv if r["is_one_off_spike"]])},
                  "temporary_dip": {"events": sum(r["is_temporary_dip"] for r in mv),
                                    "amount": s([r for r in mv if r["is_temporary_dip"]])}},
        "timing_by_type": timing,
        "last_month": {"month": last, **{k: (None if v[0] is None else str(v[0])) for k, v in bridge[last].items()}},
        "churn_confirmed_through": res["churn_confirmed_through"],
        "hole_months": res["hole_months"],
    }
