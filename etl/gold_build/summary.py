"""The acquisition dashboard snapshot (contracts/acq_api_contract.md v1.3,
`GET /api/acq/summary`), unmasked. The API Lambda masks the HR categories for
non-finance roles. Money is an exact decimal string; r is a JSON number.
"""

from __future__ import annotations

from decimal import Decimal

from gold_build import engine, funnel

DEF = {"first_payment": "user", "new_logo": "new_logo"}
SERIES = {"TOTAL": "total", "GROUP_PEOPLE": "people", "GROUP_MEDIA": "media", "GROUP_OTHER": "other"}


def _s(v) -> str | None:
    return None if v is None else str(v)


def _f(v) -> float | None:
    return None if v is None else float(v)


def _month(key: int) -> str:
    return f"{key // 100:04d}-{key % 100:02d}"


def build(res: dict, gcfg: dict, published_at: str | None = None) -> dict:
    T = res["tables"]
    dim_month = {r["month_key"]: r for r in T["dim_month"]}
    ind = {i["industry_key"]: i for i in gcfg["industries"]}
    scope_keys = res["ind_scope"]
    stages = [{"code": s["stage_code"], "label": s["stage_label"], "order": s["stage_key"]} for s in gcfg["stages"]]
    industries = [{"code": ind[k]["industry_code"], "label": ind[k]["industry_label_en"]} for k in scope_keys]
    cats = [c for c in gcfg["spend_categories"] if c["category_key"] > 0]
    spend_categories = [{"code": c["category_code"], "label": c["category_label_en"],
                         "hr_sensitive": c["is_hr_sensitive"], "group": c["spend_group"]} for c in cats]
    pre, post = engine.regime_ids(gcfg["params"]["regime_boundary"])
    b = gcfg["params"]["regime_boundary"]
    label_month = f"{['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][int(b[5:7]) - 1]} {b[:4]}"
    rep = [r for r in T["agg_acquisition_month"] if r["is_won_reportable"]]
    regimes = []
    for rid, label in ((pre, f"Before {label_month}"), (post, f"From {label_month}")):
        ms = [_month(r["month_key"]) for r in rep if dim_month[r["month_key"]]["sm_regime"] == rid]
        regimes.append({"id": rid, "label": label, "first_month": ms[0] if ms else None,
                        "last_month": ms[-1] if ms else None, "inferred": True})
    spend = {}
    code = {c["category_key"]: c["category_code"] for c in gcfg["spend_categories"]}
    for r in T["fact_sm_spend"]:
        spend.setdefault(r["month_key"], {})[code.get(r["category_key"], "UNMAPPED")] = r["spend_value"]
    by_mi = {(r["month_key"], r["industry_key"]): r["won_count"] for r in T["agg_won_month_industry"]}
    by_mi_nl = {(r["month_key"], r["industry_key"]): r["won_new_logo_count"] for r in T["agg_won_month_industry"]}
    dct = res["data_complete_through"]
    months = []
    for r in rep:
        m = _month(r["month_key"])
        has = r["spend_total_value"] is not None
        # v1.1: independent of the Won definition; the UI derives won_zero per definition
        reason = funnel.cost_null_reason(1, {"month": m, **r}, dct)
        months.append({
            "month": m, "regime": dim_month[r["month_key"]]["sm_regime"], "won": r["won_count"],
            "won_new_logo": r["won_new_logo_count"],
            "won_by_industry": {ind[k]["industry_code"]: by_mi.get((r["month_key"], k), 0) for k in scope_keys},
            "won_by_industry_new_logo": {ind[k]["industry_code"]: by_mi_nl.get((r["month_key"], k), 0)
                                         for k in scope_keys},
            "new_revenue_value": _s(r["new_revenue_value"]),
            "spend_value": {c["category_code"]: (_s(spend.get(r["month_key"], {}).get(c["category_code"]))
                                                 if has else None) for c in cats},
            "spend_people_value": _s(r["spend_people_value"]), "spend_total_value": _s(r["spend_total_value"]),
            "won_is_complete": r["won_is_complete"], "is_unit_tripwire": bool(r["is_unit_tripwire"]),
            "cost_null_reason": reason, "is_low_n": r["won_count"] < gcfg["params"]["low_n"]})
    won_by_ind = {}
    for f in T["fact_acquisition"]:
        won_by_ind[f["industry_key"]] = won_by_ind.get(f["industry_key"], 0) + 1
    profile = []
    for r in T["agg_industry_profile"]:
        k = r["industry_key"]
        won = won_by_ind.get(k, 0)  # v1.1: the industry's Won (user definition), the same on every scope row
        profile.append({
            "industry_code": ind[k]["industry_code"], "customer_scope": r["customer_scope"],
            "customers": r["customers"], "won": won,
            "avg_monthly_payment_value": _s(r["avg_monthly_payment_value"]),
            "avg_monthly_payment_excl_outliers_value": _s(r["avg_monthly_payment_ex_outlier_value"]),
            "avg_months_paying": _s(r["avg_months_paying"]),
            "paid_customer_months": r["paid_customer_months"],
            "median_monthly_payment_value": _s(r["median_monthly_payment_value"]),
            "outlier_customers": r["outlier_customers"], "avg_months_observable": _s(r["avg_months_observable"]),
            "share_of_observable_months_paid": _s(r["share_of_observable_months_paid"]), "is_low_n": r["is_low_n"]})
    corr = []
    for r in T["agg_won_spend_lag_corr"]:
        corr.append({"won_definition": DEF[r["won_definition"]],
                     "scope": "company" if r["scope_code"] == "ALL" else r["scope_code"],
                     "series": SERIES.get(r["spend_series"], r["spend_series"]), "lag": r["lag_months"],
                     "method": r["method"], "r": _f(r["r"]), "n": r["n_pairs"],
                     "r_critical_5pct": _f(r["r_critical_5pct"]), "is_signal": bool(r["is_signal_5pct"]),
                     "null_reason": r["null_reason"], "won_mean_per_month": _s(r["won_mean_per_month"]),
                     "is_low_volume": r["is_low_volume"]})
    summ = {}
    for r in T["agg_won_spend_lag_corr"]:
        k = (r["method"], DEF[r["won_definition"]], "company" if r["scope_code"] == "ALL" else "industry")
        s = summ.setdefault(k, {"tests": 0, "tests_with_r": 0, "signals": 0})
        s["tests"] += 1
        s["tests_with_r"] += r["r"] is not None
        s["signals"] += bool(r["is_signal_5pct"])
    signal_summary = [{"method": m, "won_definition": d, "scope_type": st, **v,
                       "expected_by_chance": float(Decimal("0.05") * v["tests_with_r"])}
                      for (m, d, st), v in sorted(summ.items())]
    status = T["gold_build_status"][0]
    return {
        "run": {"run_id": res["run_id"], "silver_run_id": res["silver_run_id"],
                "built_at": res["built_at"].strftime("%Y-%m-%dT%H:%M:%SZ"), "as_of_month": res["as_of_month"],
                "data_complete_through": dct, "gold_model_version": res["gold_model_version"],
                "base_rates_match_seed": status["base_rates_match_seed"]},
        "statuses": dict(res["statuses"]),
        "stages": stages, "industries": industries, "spend_categories": spend_categories, "regimes": regimes,
        "months": months, "industry_profile": profile, "correlations": corr, "signal_summary": signal_summary,
        "levers": lever_block(res, gcfg),
    }


def _row(r: dict, table: str | None, ind: dict, cols=None) -> dict:
    """A §16 table row as JSON (contract v1.3): the table's own column names, no lineage;
    decimals as strings at their column scale (money *_value at 2 dp, HALF_UP; the
    shift-share terms keep their 6-dp scale so the terms add up to the totals exactly);
    counts as integers; NULL as null. industry_code is added next to industry_key."""
    from gold_build import schemas
    types = dict(cols or schemas.TABLES[table])
    out = {}
    for c, t in types.items():
        v = r.get(c)
        if v is not None and t.startswith("decimal("):
            scale = int(t[8:-1].split(",")[1])
            if c.endswith("_value") and scale < 2 or (c.endswith("_value") and not c.endswith("_term_value")):
                scale = 2
            v = str(Decimal(v).quantize(Decimal(1).scaleb(-scale)))
        out[c] = v
        if c == "industry_key":
            out["industry_code"] = ind[v]["industry_code"] if v in ind else None
    return out


COHORT_HALF_COLS = [("won_definition", "string"), ("cohort_half", "string"), ("won_count", "int"),
                    ("run_rate_customers", "int"), ("run_rate_no_paid_customers", "int"),
                    ("run_rate_immature_customers", "int"), ("run_rate_mrr_per_won_value", "decimal(18,2)"),
                    ("paying_m6_eligible", "int"), ("paying_m6_count", "int"), ("paying_m6_share", "decimal(9,4)"),
                    ("paying_m12_eligible", "int"), ("paying_m12_count", "int"), ("paying_m12_share", "decimal(9,4)"),
                    ("outlier_customers", "int"), ("is_complete_m6", "boolean"), ("is_complete_m12", "boolean"),
                    ("is_complete_run_rate", "boolean")]


def lever_block(res: dict, gcfg: dict) -> dict:
    T = res["tables"]
    ind = {i["industry_key"]: i for i in gcfg["industries"]}
    return {"definitions_version": gcfg["params"]["levers"]["definitions_version"],
            "periods": [_row(r, "agg_acq_lever_period", ind) for r in T["agg_acq_lever_period"]],
            "industries": [_row(r, "agg_acq_lever_industry", ind) for r in T["agg_acq_lever_industry"]],
            "value_change": [_row(r, "agg_acq_value_change", ind) for r in T["agg_acq_value_change"]],
            "cohorts": [_row(r, None, ind, COHORT_HALF_COLS) for r in res["levers"]["cohort_half"]]}
