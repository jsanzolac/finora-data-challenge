"""Decision levers (docs/gold_acquisition_model.md §16): the per-customer run-rate and
retention markers on fact_acquisition, agg_acq_cohort_quality, agg_acq_lever_period,
agg_acq_lever_industry, agg_acq_value_change, the v_acq_cohort_half rollup (in Python
for the snapshot; the Athena view is in ddl.py) and the run controls GC-13 / GC-14.

Exact arithmetic: Fractions, one HALF_UP rounding per published figure. §16 exception:
new_mrr_per_month_value and payback_months use the published (rounded) operands.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from fractions import Fraction

from gold_build import funnel
from gold_build.stats import qfrac

STATUS_OK, STATUS_NONE, STATUS_IMMATURE = "ok", "no_paid_month", "immature"


def _madd(m: str, k: int) -> str:
    t = int(m[:4]) * 12 + int(m[5:7]) - 1 + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def _mkey(m: str) -> int:
    return int(m[:4]) * 100 + int(m[5:7])


def _km(k: int) -> str:
    return f"{k // 100:04d}-{k % 100:02d}"


def half(m: str) -> str:
    return f"{m[:4]}-H{1 if int(m[5:7]) <= 6 else 2}"


def _share(n: int, d: int, places: str = "0.0001"):
    return qfrac(Fraction(n, d), places) if d else None


def customer_columns(fa: list[dict], fcm: dict, dct: str | None, p: dict) -> None:
    """§16.4(a): adds the lever columns to each fact_acquisition row in place."""
    lv = p["levers"]
    for f in fa:
        c = _km(f["won_month_key"])
        f["cohort_half"] = half(c)
        window = [_madd(c, k) for k in lv["run_rate_window"]]
        if dct is None or window[-1] > dct:
            f.update(run_rate_status=STATUS_IMMATURE, run_rate_m2_4_months=None, run_rate_m2_4_value=None)
        else:
            vals = []
            for m in window:
                r = fcm.get((f["customer_id"], _mkey(m)))
                if r is not None and r["amount_normalized"] is not None and r["amount_normalized"] > 0:
                    vals.append(Fraction(r["amount_normalized_value"]))
            if vals:
                f.update(run_rate_status=STATUS_OK, run_rate_m2_4_months=len(vals),
                         run_rate_m2_4_value=qfrac(sum(vals) / len(vals), "0.000001"))
            else:
                f.update(run_rate_status=STATUS_NONE, run_rate_m2_4_months=0, run_rate_m2_4_value=None)
        for col, k in (("paying_m6", lv["paying_months"]["m6"]), ("paying_m12", lv["paying_months"]["m12"])):
            m = _madd(c, k)
            r = fcm.get((f["customer_id"], _mkey(m)))
            f[col] = None if (dct is None or m > dct or r is None) else bool(r["is_paying"])


def _counts(fs: list[dict]) -> dict:
    ok = [f for f in fs if f["run_rate_status"] == STATUS_OK]
    m6 = [f["paying_m6"] for f in fs if f["paying_m6"] is not None]
    m12 = [f["paying_m12"] for f in fs if f["paying_m12"] is not None]
    return {"won_count": len(fs), "run_rate_customers": len(ok),
            "run_rate_no_paid_customers": sum(1 for f in fs if f["run_rate_status"] == STATUS_NONE),
            "run_rate_immature_customers": sum(1 for f in fs if f["run_rate_status"] == STATUS_IMMATURE),
            "_rr_sum": sum((Fraction(f["run_rate_m2_4_value"]) for f in ok), Fraction(0)),
            "paying_m6_eligible": len(m6), "paying_m6_count": sum(m6),
            "paying_m12_eligible": len(m12), "paying_m12_count": sum(m12),
            "outlier_customers": sum(1 for f in fs if f["is_outlier_customer"])}


def _rr(c: dict):
    return c["_rr_sum"] / c["run_rate_customers"] if c["run_rate_customers"] else None


def _retention(c: dict) -> dict:
    return {"paying_m6_share": _share(c["paying_m6_count"], c["paying_m6_eligible"]),
            "paying_m12_share": _share(c["paying_m12_count"], c["paying_m12_eligible"])}


def _public(c: dict) -> dict:
    return {k: v for k, v in c.items() if not k.startswith("_")}


def build(T: dict, gcfg: dict, ctx: dict, lin) -> dict:
    """ctx: W, reportable, dim_month, data_through, ind_scope, agg_m (month_key -> agg row),
    statuses, regime labels. Returns the lever tables plus the cohort-half rollup."""
    p = gcfg["params"]
    lv = p["levers"]
    dct = ctx["data_through"]
    fa = T["fact_acquisition"]
    defs = gcfg["won_definitions"]
    member = {"first_payment": lambda f: True, "new_logo": lambda f: f["is_new_logo"]}
    rep_months = [m for m in ctx["W"] if ctx["reportable"][m]]
    by_mi = defaultdict(list)
    for f in fa:
        by_mi[(f["won_month_key"], f["industry_key"])].append(f)
    out = {t: [] for t in ("agg_acq_cohort_quality", "agg_acq_lever_period", "agg_acq_lever_industry",
                           "agg_acq_value_change")}
    # (b) cohort quality: won_definition x won month x industry, dense on the registered industries
    L = lin("agg_acq_cohort_quality")
    for d in defs:
        for m in rep_months:
            for k in ctx["ind_scope"]:
                fs = [f for f in by_mi.get((_mkey(m), k), []) if member[d](f)]
                c = _counts(fs)
                out["agg_acq_cohort_quality"].append({
                    "won_definition": d, "won_month_key": _mkey(m), "industry_key": k, "cohort_half": half(m),
                    **_public(c), "run_rate_m2_4_sum_value": qfrac(c["_rr_sum"], "0.000001"),
                    "is_low_n": c["won_count"] < lv["low_n"], "is_small_cell": 0 < c["won_count"] < lv["small_cell"],
                    **L})
    # (c) periods = the inferred sm_regime of dim_month, reportable months up to data_complete_through
    periods = {}
    for m in rep_months:
        if dct is not None and m <= dct:
            periods.setdefault(ctx["dim_month"][m]["sm_regime"], []).append(m)
    order = sorted(periods, key=lambda r: periods[r][0])
    L = lin("agg_acq_lever_period")
    pstats: dict = {}
    for d in defs:
        for code in order:
            ms = periods[code]
            fs = [f for f in fa if _km(f["won_month_key"]) in set(ms) and member[d](f)]
            c = _counts(fs)
            pstats[(d, code)] = (c, fs)
            rows = [dict(ctx["agg_m"][_mkey(m)], month=m) for m in ms]
            reason = funnel.period_reason(rows, d, dct)
            spends = [r["spend_total_value"] for r in rows]
            spend = sum(spends, Decimal(0)) if all(s is not None for s in spends) else None
            wpm = qfrac(Fraction(c["won_count"], len(ms)), "0.000001")
            rr = qfrac(_rr(c), "0.01") if c["run_rate_customers"] else None
            cost = qfrac(Fraction(spend) / c["won_count"], "0.01") if reason is None and spend is not None else None
            mature = [m for m in ms if _madd(m, lv["run_rate_window"][-1]) <= dct]
            out["agg_acq_lever_period"].append({
                "won_definition": d, "period_code": code, "period_label": ctx["regime_labels"][code],
                "is_inferred": True, "first_month_key": _mkey(ms[0]), "last_month_key": _mkey(ms[-1]),
                "months": len(ms), "won_per_month": wpm,
                **{k: v for k, v in _public(c).items() if k not in ("paying_m6_count", "paying_m12_count")},
                "paying_m6_count": c["paying_m6_count"], "paying_m12_count": c["paying_m12_count"],
                "run_rate_last_cohort_month_key": _mkey(mature[-1]) if mature else None,
                "run_rate_mrr_per_won_value": rr,
                "new_mrr_per_month_value": qfrac(Fraction(wpm) * Fraction(rr), "0.01") if rr is not None else None,
                "spend_total_value": spend,
                "spend_per_month_value": qfrac(Fraction(spend) / len(ms), "0.01") if cost is not None else None,
                "cost_per_won_value": cost,
                "payback_months": qfrac(Fraction(cost) / Fraction(rr), "0.1") if cost is not None and rr else None,
                "cost_null_reason": reason, **_retention(c), **ctx["statuses"], **L})
    # (d) industries within a period (no spend: CDO-10)
    L = lin("agg_acq_lever_industry")
    istats: dict = {}
    for d in defs:
        for code in order:
            pc, pfs = pstats[(d, code)]
            for k in ctx["ind_scope"]:
                c = _counts([f for f in pfs if f["industry_key"] == k])
                istats[(d, code, k)] = c
                out["agg_acq_lever_industry"].append({
                    "won_definition": d, "period_code": code, "industry_key": k, **_public(c),
                    "won_share": _share(c["won_count"], pc["won_count"]),
                    "run_rate_share": _share(c["run_rate_customers"], pc["run_rate_customers"]),
                    "run_rate_mrr_per_won_value": qfrac(_rr(c), "0.01") if c["run_rate_customers"] else None,
                    **_retention(c), "is_low_n": c["run_rate_customers"] < lv["low_n"],
                    "is_small_cell": 0 < c["won_count"] < lv["small_cell"], **L})
    # (e) shift-share of the run-rate between two periods, run-rate-customer weights
    L = lin("agg_acq_value_change")
    exact_vc = {}
    for d in defs:
        for p0, p1 in lv["value_change"]:
            if p0 not in periods or p1 not in periods:
                continue
            n0, n1 = pstats[(d, p0)][0]["run_rate_customers"], pstats[(d, p1)][0]["run_rate_customers"]
            cells = {k: (istats[(d, p0, k)], istats[(d, p1, k)]) for k in ctx["ind_scope"]}
            one_sided = any((a["run_rate_customers"] > 0) != (b["run_rate_customers"] > 0) for a, b in cells.values())
            reason = "industry_not_in_both_periods" if one_sided or not n0 or not n1 else None
            terms = {}
            for k, (a, b) in cells.items():
                s0 = Fraction(a["run_rate_customers"], n0) if n0 else None
                s1 = Fraction(b["run_rate_customers"], n1) if n1 else None
                v0, v1 = _rr(a), _rr(b)
                t = None
                if reason is None:
                    if v0 is None and v1 is None:
                        t = (Fraction(0),) * 4
                    else:
                        t = ((s1 - s0) * v0, s1 * (v1 - v0), (s1 - s0) * v1, s0 * (v1 - v0))
                terms[k] = t
                out["agg_acq_value_change"].append({
                    "won_definition": d, "from_period_code": p0, "to_period_code": p1, "industry_key": k,
                    "share_from": qfrac(s0, "0.0001") if s0 is not None else None,
                    "share_to": qfrac(s1, "0.0001") if s1 is not None else None,
                    "value_from": qfrac(v0, "0.01") if v0 is not None else None,
                    "value_to": qfrac(v1, "0.01") if v1 is not None else None,
                    **{col: (qfrac(t[i], "0.000001") if t is not None else None) for i, col in enumerate(
                        ("mix_term_value", "within_term_value", "mix_reverse_term_value", "within_reverse_term_value"))},
                    "null_reason": reason, **L})
            if reason is None:
                exact_vc[(d, p0, p1)] = {"total": _rr(pstats[(d, p1)][0]) - _rr(pstats[(d, p0)][0]),
                                         "mix": sum(t[0] for t in terms.values()),
                                         "within": sum(t[1] for t in terms.values()),
                                         "mix_reverse": sum(t[2] for t in terms.values()),
                                         "within_reverse": sum(t[3] for t in terms.values())}
    return {"tables": out, "cohort_half": cohort_half(out["agg_acq_cohort_quality"]), "exact_vc": exact_vc}


def cohort_half(cq: list[dict]) -> list[dict]:
    """§16.4(f) v_acq_cohort_half in Python: Σ counts; run-rate = Σ sum ÷ Σ customers (2 dp)."""
    acc: dict = {}
    keys = ("won_count", "run_rate_customers", "run_rate_no_paid_customers", "run_rate_immature_customers",
            "paying_m6_eligible", "paying_m6_count", "paying_m12_eligible", "paying_m12_count", "outlier_customers")
    for r in cq:
        a = acc.setdefault((r["won_definition"], r["cohort_half"]), {**{k: 0 for k in keys}, "_sum": Decimal(0)})
        for k in keys:
            a[k] += r[k]
        a["_sum"] += r["run_rate_m2_4_sum_value"]
    out = []
    for (d, h), a in sorted(acc.items()):
        out.append({"won_definition": d, "cohort_half": h, **{k: a[k] for k in keys},
                    "run_rate_mrr_per_won_value": (qfrac(Fraction(a["_sum"]) / a["run_rate_customers"], "0.01")
                                                   if a["run_rate_customers"] else None),
                    "paying_m6_share": _share(a["paying_m6_count"], a["paying_m6_eligible"]),
                    "paying_m12_share": _share(a["paying_m12_count"], a["paying_m12_eligible"]),
                    "is_complete_m6": a["paying_m6_eligible"] == a["won_count"],
                    "is_complete_m12": a["paying_m12_eligible"] == a["won_count"],
                    "is_complete_run_rate": a["run_rate_immature_customers"] == 0})
    return out


def controls(T: dict, lev: dict) -> list[dict]:
    """GC-13 and GC-14 (§16.4)."""
    out = []
    cq, per = T["agg_acq_cohort_quality"], T["agg_acq_lever_period"]
    wmi = {(r["month_key"], r["industry_key"]): r["won_count"] for r in T["agg_won_month_industry"]}
    ok13 = all(r["won_count"] == wmi.get((r["won_month_key"], r["industry_key"]), 0)
               for r in cq if r["won_definition"] == "first_payment")
    ok13 &= sum(r["won_count"] for r in cq if r["won_definition"] == "first_payment") == len(T["fact_acquisition"])
    ok13 &= all(r["run_rate_customers"] + r["run_rate_no_paid_customers"] + r["run_rate_immature_customers"]
                == r["won_count"] for r in cq + per + T["agg_acq_lever_industry"])
    fa = T["fact_acquisition"]
    for d, pred in (("first_payment", lambda f: True), ("new_logo", lambda f: f["is_new_logo"])):
        ok13 &= sum(r["run_rate_m2_4_sum_value"] for r in cq if r["won_definition"] == d) == \
            sum(f["run_rate_m2_4_value"] for f in fa if pred(f) and f["run_rate_m2_4_value"] is not None)
        for p in (r for r in per if r["won_definition"] == d):
            rows = [r for r in cq if r["won_definition"] == d and p["first_month_key"] <= r["won_month_key"]
                    <= p["last_month_key"]]
            n = sum(r["run_rate_customers"] for r in rows)
            ok13 &= all(sum(r[k] for r in rows) == p[k] for k in (
                "won_count", "run_rate_customers", "run_rate_no_paid_customers", "run_rate_immature_customers",
                "paying_m6_eligible", "paying_m6_count", "paying_m12_eligible", "paying_m12_count"))
            ok13 &= p["run_rate_mrr_per_won_value"] == (
                qfrac(Fraction(sum(r["run_rate_m2_4_sum_value"] for r in rows)) / n, "0.01") if n else None)
    out.append({"id": "GC-13", "passed": bool(ok13), "detail": "" if ok13 else "lever counts do not reconcile"})
    ok14 = True
    for key, e in lev["exact_vc"].items():
        rows = [r for r in T["agg_acq_value_change"] if (r["won_definition"], r["from_period_code"],
                                                        r["to_period_code"]) == key]
        ok14 &= abs(sum(Fraction(r["mix_term_value"]) + Fraction(r["within_term_value"]) for r in rows)
                    - e["total"]) <= Fraction(1, 100000)
        ok14 &= e["mix"] + e["within"] == e["total"] == e["mix_reverse"] + e["within_reverse"]
    for p in per:
        if p["run_rate_mrr_per_won_value"] is not None:
            ok14 &= p["new_mrr_per_month_value"] == qfrac(Fraction(p["won_per_month"]) *
                                                         Fraction(p["run_rate_mrr_per_won_value"]), "0.01")
            if p["cost_per_won_value"] is not None:
                ok14 &= p["payback_months"] == qfrac(Fraction(p["cost_per_won_value"]) /
                                                     Fraction(p["run_rate_mrr_per_won_value"]), "0.1")
    for r in per + T["agg_acq_lever_industry"] + cq:
        ok14 &= r["paying_m6_count"] <= r["paying_m6_eligible"] <= r["won_count"]
        ok14 &= r["paying_m12_count"] <= r["paying_m12_eligible"] <= r["won_count"]
    out.append({"id": "GC-14", "passed": bool(ok14), "detail": "" if ok14 else "lever identities do not hold"})
    return out
