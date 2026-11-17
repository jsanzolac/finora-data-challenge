"""Gold acquisition model engine (docs/gold_acquisition_model.md §5, §7.4, §10).

Pure Python, exact Decimal: silver rows in, gold table rows out, plus the run
controls GC-01..GC-11 and the run findings. The Glue Spark job reads silver at
its run tag and writes these rows through write-audit-publish (spark_io.py);
the tests call build() directly on the silver engine's output.
"""

from __future__ import annotations

import calendar
import statistics
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction

from gold_build import funnel, levers, schemas, stats

Q2, Q0 = Decimal("0.01"), Decimal("1")
REV, SPEND = Decimal(10000), Decimal(100000000)
SERIES_GROUPS = (("GROUP_MEDIA", "media"), ("GROUP_PEOPLE", "people"), ("GROUP_OTHER", "other"))
METHODS = ("level", "diff", "within_regime")


class GoldControlError(RuntimeError):
    pass


def mkey(m: str) -> int:
    return int(m[:4]) * 100 + int(m[5:7])


def midx(m: str) -> int:
    return int(m[:4]) * 12 + int(m[5:7]) - 1


def madd(m: str, k: int) -> str:
    t = midx(m) + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def snake(code: str) -> str:
    out = ""
    for ch in code:
        out += ("_" + ch.lower()) if ch.isupper() and out else ch.lower()
    return out


def spend_col(code: str) -> str:
    return f"spend_{snake(code)}_value"


def regime_ids(boundary: str) -> tuple[str, str]:
    b = boundary.replace("-", "_")
    return f"pre_{b}", f"from_{b}"


def regime_labels(boundary: str) -> dict[str, str]:
    pre, post = regime_ids(boundary)
    mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(boundary[5:7]) - 1]
    return {pre: f"Before {mon} {boundary[:4]}", post: f"From {mon} {boundary[:4]}"}


def _uniform(rows: list[dict], col: str, what: str):
    vals = {r[col] for r in rows}
    if len(vals) > 1:
        raise GoldControlError(f"input: silver {what} rows carry more than one {col}: {sorted(map(str, vals))}")
    return next(iter(vals)) if vals else None


def build(silver: dict[str, list[dict]], gcfg: dict, meta: dict) -> dict:
    """meta: run_id, silver_run_id, built_at (aware UTC datetime), gold_model_version,
    rate (dict from rate_state(): snapshot_id, rows_sha256, base_match, findings)."""
    p = gcfg["params"]
    run_id, silver_run_id = meta["run_id"], meta["silver_run_id"]
    for t, rows in silver.items():
        rid = _uniform(rows, "_run_id", t)
        if rows and rid != silver_run_id:
            raise GoldControlError(f"input: silver {t} rows are from run {rid}, not {silver_run_id}")
    rules_version = _uniform([r for rows in silver.values() for r in rows], "_rules_version", "input")
    as_of = _uniform(silver["customer"] + silver["month_control"], "as_of_month", "customer/month_control")
    sha = {"transactions": _uniform(silver["transactions"], "_source_sha256", "transactions"),
           "industry": _uniform(silver["industry"], "_source_sha256", "industry"),
           "sm_spend": _uniform(silver["sm_spend"], "_source_sha256", "sm_spend")}

    mc = {r["month"]: r for r in silver["month_control"]}
    W = sorted(mc)
    if not W:
        raise GoldControlError("input: silver month_control is empty")
    ws = W[0]
    sm_months = sorted({r["month"] for r in silver["sm_spend"]})
    spend_through = max((m for m in sm_months if mc.get(m, {}).get("in_sm_spend")), default=None)
    data_through = min(as_of, spend_through) if as_of and spend_through else None
    pre, post = regime_ids(p["regime_boundary"])
    src = {r["dataset_id"]: r for r in silver["source_status"]}
    tx_s, sm_s = src.get("transactions", {}), src.get("sm_spend", {})
    cur_statuses = {s.get("currency_status") for s in (tx_s, sm_s) if s}
    statuses = {"currency_status": "unconfirmed" if (not cur_statuses or cur_statuses != {"confirmed"})
                else "confirmed",
                "revenue_basis_status": tx_s.get("basis_status") or "unconfirmed",
                "spend_basis_status": sm_s.get("basis_status") or "unconfirmed"}
    scopes = {r["scope_status"] for r in silver["month_control"]}
    statuses["scope_status"] = scopes.pop() if len(scopes) == 1 else "unconfirmed"
    built_at = meta["built_at"]

    def lin(table: str) -> dict:
        uses = schemas.USES[table]
        return {"_run_id": run_id, "_silver_run_id": silver_run_id, "_rules_version": rules_version,
                "_gold_model_version": meta["gold_model_version"],
                "_transactions_sha256": sha["transactions"] if "transactions" in uses else None,
                "_industry_sha256": sha["industry"] if "industry" in uses else None,
                "_sm_spend_sha256": sha["sm_spend"] if "sm_spend" in uses else None,
                "as_of_month": as_of, "_built_at": built_at}

    findings: list[dict] = list(meta.get("rate", {}).get("findings", []))
    T: dict[str, list[dict]] = {t: [] for t in schemas.ORDER}

    # ---- dim_month
    reportable = {}
    L = lin("dim_month")
    for i, m in enumerate(W):
        y, mo = int(m[:4]), int(m[5:7])
        r = mc[m]
        rep = (m != ws) and as_of is not None and m <= as_of
        reportable[m] = rep
        T["dim_month"].append({
            "month_key": mkey(m), "month": m, "month_start_date": date(y, mo, 1),
            "month_end_date": date(y, mo, calendar.monthrange(y, mo)[1]), "year": y, "quarter": (mo - 1) // 3 + 1,
            "year_quarter": f"{y}-Q{(mo - 1) // 3 + 1}", "month_index": i, "is_window_start": m == ws,
            "is_won_reportable": rep, "sm_regime": pre if m < p["regime_boundary"] else post,
            "in_transactions": r["in_transactions"], "in_sm_spend": r["in_sm_spend"],
            "revenue_is_complete": r["revenue_is_complete"], "is_unit_tripwire": r["is_unit_tripwire"], **L})
    dim_month = {r["month"]: r for r in T["dim_month"]}

    # ---- dim_industry (seed, checked against silver)
    L = lin("dim_industry")
    ind_key = {}
    for i in gcfg["industries"]:
        T["dim_industry"].append({k: i[k] for k in ("industry_key", "industry_code", "industry_label_es",
                                                    "industry_label_en", "chart_label", "is_unknown_member",
                                                    "sort_order")} | L)
        ind_key[i["industry_code"]] = i["industry_key"]
    unmapped_codes = sorted({r["industry_code"] for r in silver["industry"]} - set(ind_key))
    if unmapped_codes:
        findings.append({"finding": "UNKNOWN_INDUSTRY_CODE", "detail": f"{len(unmapped_codes)} silver codes "
                         "not in the dim_industry seed map to UNMAPPED (-2)"})

    def ikey(code):
        return ind_key.get(code, -2)

    # ---- dim_spend_category (seed)
    L = lin("dim_spend_category")
    cat_key, cat_hr = {}, {}
    for c in gcfg["spend_categories"]:
        T["dim_spend_category"].append({k: c[k] for k in ("category_key", "category_code", "category_label_en",
                                                         "spend_group", "channel_class", "is_hr_sensitive")} | L)
        cat_key[c["category_code"]], cat_hr[c["category_code"]] = c["category_key"], c["is_hr_sensitive"]
    groups = {g: [c["category_code"] for c in gcfg["spend_categories"] if c["spend_group"] == g]
              for _, g in SERIES_GROUPS}
    categories = [c["category_code"] for c in gcfg["spend_categories"] if c["category_key"] > 0]

    # ---- dim_funnel_stage (seed)
    L = lin("dim_funnel_stage")
    for s in gcfg["stages"]:
        T["dim_funnel_stage"].append({k: s[k] for k in ("stage_key", "stage_code", "stage_label",
                                                       "next_stage_code", "is_observed", "basis")} | L)

    # ---- dim_customer
    L = lin("dim_customer")
    cust = {r["customer_id"]: r for r in silver["customer"]}
    for c in silver["customer"]:
        won = c["cohort_month"] is not None and c["cohort_censoring"] != "left"
        T["dim_customer"].append({
            "customer_id": c["customer_id"], "industry_key": ikey(c["industry_code"]),
            "cohort_month_key": mkey(c["cohort_month"]) if c["cohort_month"] else None,
            "cohort_censoring": c["cohort_censoring"], "is_won": won, "is_new_logo": c["is_new_logo"],
            "paid_months": c["paid_months"],
            "last_paid_month_key": mkey(c["last_paid_month"]) if c["last_paid_month"] else None,
            "is_outlier_customer": c["is_outlier_customer"], "outlier_source": c["outlier_source"],
            "has_excluded_months": c["has_excluded_months"], "in_transactions": c["in_transactions"], **L})
    dcust = {r["customer_id"]: r for r in T["dim_customer"]}

    # ---- facts
    tx = {(r["customer_id"], r["month"]): r for r in silver["transactions"]}
    L = lin("fact_acquisition")
    for c in silver["customer"]:
        if not dcust[c["customer_id"]]["is_won"]:
            continue
        m = c["cohort_month"]
        line = tx.get((c["customer_id"], m))
        if line is None:
            raise GoldControlError(f"GC-10: no silver transactions row at the first payment of customer {c['customer_id']}")
        first_v = (c["first_paid_amount"] * REV).quantize(Q2)
        mult = c["first_payment_multiple"]
        if mult is not None and c["next_paid_amount"] is None:
            raise GoldControlError(f"input: customer {c['customer_id']} has a first-payment multiple and no next payment")
        rr = (c["next_paid_amount"] * REV).quantize(Q2) if mult is not None else first_v
        cens = c["cohort_censoring"]
        T["fact_acquisition"].append({
            "customer_id": c["customer_id"], "won_month_key": mkey(m), "industry_key": ikey(c["industry_code"]),
            "won_count": 1, "first_paid_amount": c["first_paid_amount"], "first_paid_amount_value": first_v,
            "run_rate_amount_value": rr, "first_payment_multiple": mult, "is_first_payment_multiple": mult is not None,
            "first_payment_ratio": c["first_payment_ratio"], "first_payment_band": c["first_payment_band"],
            "is_first_month_spike": c["is_first_month_spike"], "implied_start_month": c["implied_start_month"],
            "cohort_censoring": cens, "is_new_logo": cens == "none", "is_probable_left": cens == "probable_left",
            "is_cohort_unknown": cens == "unknown", "first_payment_hole_affected": c["first_payment_hole_affected"],
            "is_outlier_customer": c["is_outlier_customer"], "_source_key": line["_source_key"],
            "_ingested_at": line["_ingested_at"], "_source_line": line["_source_line"], **L})

    L = lin("fact_customer_month_revenue")
    for r in silver["customer_month"]:
        c = cust.get(r["customer_id"])
        if c is None:
            raise GoldControlError(f"GC-07: customer_month customer {r['customer_id']} is not in silver customer")
        if r["month"] not in dim_month:
            raise GoldControlError(f"GC-07: customer_month month {r['month']} is not in W")
        line = tx.get((r["customer_id"], r["month"]))
        coh = c["cohort_month"]
        since = midx(r["month"]) - midx(coh) if coh and r["month"] >= coh else None
        an = r["amount_normalized"]
        T["fact_customer_month_revenue"].append({
            "customer_id": r["customer_id"], "month_key": mkey(r["month"]), "industry_key": ikey(c["industry_code"]),
            "cohort_month_key": mkey(coh) if coh else None, "months_since_cohort": since,
            "amount": r["amount"], "amount_value": r["amount_value"], "amount_normalized": an,
            "amount_normalized_value": (an * REV).quantize(Q2) if an is not None else None,
            "is_paying": r["is_paying"], "is_negative_amount": line["is_negative_amount"] if line else None,
            "is_first_paid_month": coh is not None and r["month"] == coh, "is_hole": r["is_hole"],
            "hole_reason": r["hole_reason"], "lifecycle_state": r["lifecycle_state"],
            "is_provisional": r["is_provisional"], "settlement_type": r["settlement_type"],
            "settlement_confidence": r["settlement_confidence"],
            "uneven_split_start_month": r.get("uneven_split_start_month"), "is_catch_up": r["is_catch_up"],
            "is_prepaid": r["is_prepaid"], "expansion_amount": r["expansion_amount"],
            "contraction_amount": r["contraction_amount"], "amount_lag12": r["amount_lag12"],
            "_source_key": r["_source_key"], "_ingested_at": r["_ingested_at"],
            "_source_line": line["_source_line"] if line else None, **L})

    L = lin("fact_sm_spend")
    spend = defaultdict(dict)  # month -> category -> spend_value
    for r in silver["sm_spend"]:
        k = cat_key.get(r["category"], -2)
        if k == -2:
            findings.append({"finding": "UNKNOWN_SPEND_CATEGORY", "detail": "a silver S&M category is not in the seed"})
        hr = cat_hr.get(r["category"], True)
        if r["month"] not in dim_month:
            raise GoldControlError(f"GC-07: sm_spend month {r['month']} is not in W")
        T["fact_sm_spend"].append({
            "month_key": mkey(r["month"]), "category_key": k, "spend": r["spend"], "spend_value": r["spend_value"],
            "is_negative_spend": r["is_negative_spend"], "is_restated": r["is_restated"],
            "is_unit_tripwire": r["is_unit_tripwire"], "hr_sensitive": hr, "_source_key": r["_source_key"],
            "_ingested_at": r["_ingested_at"], "_source_line": r["_source_line"], **L})
        spend[r["month"]][r["category"]] = r["spend_value"]

    # ---- agg_acquisition_month
    L = lin("agg_acquisition_month")
    won_by_m = defaultdict(list)
    for f in T["fact_acquisition"]:
        won_by_m[f["won_month_key"]].append(f)
    month_spend = {}  # month -> {series: value}, only months whose spend is usable
    for m in W:
        rep, fs, r = reportable[m], won_by_m.get(mkey(m), []), mc[m]
        has_sm = bool(r["in_sm_spend"]) and spend_through is not None and m <= spend_through and m in spend
        sp = spend.get(m, {}) if has_sm else {}
        tot = sum(sp.values(), Decimal(0)) if has_sm else None
        grp = {g: (sum((sp[c] for c in cs if c in sp), Decimal(0)) if has_sm else None) for g, cs in groups.items()}
        if has_sm:
            month_spend[m] = {**{c: sp.get(c) for c in categories}, **{f"GROUP_{g.upper()}": v for g, v in grp.items()},
                              "TOTAL": tot}
        unknown = any(f["cohort_censoring"] == "unknown" for f in fs)

        def won_sum(pred, rep=rep, fs=fs):
            return sum(1 for f in fs if pred(f)) if rep else None

        def rev_sum(col, pred=lambda f: True, rep=rep, fs=fs):
            return sum((f[col] for f in fs if pred(f)), Decimal("0.00")) if rep else None

        row = {"month_key": mkey(m), "is_won_reportable": rep, "won_count": won_sum(lambda f: True),
               "won_new_logo_count": won_sum(lambda f: f["is_new_logo"]),
               "won_probable_left_count": won_sum(lambda f: f["is_probable_left"]),
               "won_cohort_unknown_count": won_sum(lambda f: f["is_cohort_unknown"]),
               "won_first_payment_multiple_count": won_sum(lambda f: f["is_first_payment_multiple"]),
               "won_is_complete": bool(r["revenue_is_complete"]) and not unknown,
               "new_revenue_value": rev_sum("first_paid_amount_value"),
               "new_revenue_new_logo_value": rev_sum("first_paid_amount_value", lambda f: f["is_new_logo"]),
               "new_revenue_multiple_value": rev_sum("first_paid_amount_value", lambda f: f["is_first_payment_multiple"]),
               "new_revenue_run_rate_value": rev_sum("run_rate_amount_value"),
               "spend_media_value": grp["media"], "spend_other_value": grp["other"],
               "spend_people_value": grp["people"], "spend_total_value": tot,
               "has_negative_spend_cell": any(v < 0 for v in sp.values()) if has_sm else None,
               "in_sm_spend": r["in_sm_spend"], "is_unit_tripwire": r["is_unit_tripwire"],
               **statuses, "scope_status": r["scope_status"] or statuses["scope_status"]}
        for c in categories:
            if not cat_hr[c]:
                row[spend_col(c)] = sp.get(c) if has_sm else None
        T["agg_acquisition_month"].append(row | L)
    agg_m = {r["month_key"]: r for r in T["agg_acquisition_month"]}

    # ---- agg_won_month_industry
    L = lin("agg_won_month_industry")
    registered = [i["industry_key"] for i in gcfg["industries"] if not i["is_unknown_member"]]
    unknown_with_won = sorted({f["industry_key"] for f in T["fact_acquisition"]} - set(registered), reverse=True)
    ind_scope = registered + unknown_with_won
    by_mi = defaultdict(list)
    for f in T["fact_acquisition"]:
        by_mi[(f["won_month_key"], f["industry_key"])].append(f)
    for m in W:
        if not reportable[m]:
            continue
        for k in ind_scope:
            fs = by_mi.get((mkey(m), k), [])
            n = len(fs)
            T["agg_won_month_industry"].append({
                "month_key": mkey(m), "industry_key": k, "won_count": n,
                "won_new_logo_count": sum(1 for f in fs if f["is_new_logo"]),
                "new_revenue_value": sum((f["first_paid_amount_value"] for f in fs), Decimal("0.00")),
                "new_revenue_new_logo_value": sum((f["first_paid_amount_value"] for f in fs if f["is_new_logo"]),
                                                  Decimal("0.00")),
                "is_low_n": n < p["low_n"], "is_small_cell": 0 < n < p["small_cell"], **L})
    for k in unknown_with_won:
        findings.append({"finding": "WON_ON_UNKNOWN_MEMBER", "detail": f"industry_key {k} has Won customers"})

    # ---- agg_industry_profile
    L = lin("agg_industry_profile")
    paid = defaultdict(list)
    for r in T["fact_customer_month_revenue"]:
        if r["amount"] is not None and r["amount"] > 0 and r["month_key"] <= mkey(as_of):
            paid[r["customer_id"]].append(r["amount_value"])
    prof_keys = registered + sorted({dcust[c]["industry_key"] for c in paid} - set(registered), reverse=True)
    for k in prof_keys:
        for scope in ("all", "won", "left_censored"):
            cs = [c for c in silver["customer"] if ikey(c["industry_code"]) == k and paid.get(c["customer_id"])
                  and (scope == "all" or (scope == "won") == dcust[c["customer_id"]]["is_won"])
                  and (scope != "left_censored" or c["cohort_censoring"] == "left")]
            vals = [v for c in cs for v in paid[c["customer_id"]]]
            vals_ex = [v for c in cs if not c["is_outlier_customer"] for v in paid[c["customer_id"]]]
            obs = [midx(as_of) - midx(c["cohort_month"]) + 1 for c in cs]
            n = len(cs)
            med = None
            if vals:
                sv, h = sorted(vals), len(vals) // 2
                med = stats.qfrac((Fraction(sv[h - 1]) + Fraction(sv[h])) / 2 if len(sv) % 2 == 0 else Fraction(sv[h]),
                                  "0.01")
            T["agg_industry_profile"].append({
                "industry_key": k, "customer_scope": scope, "customers": n, "paid_customer_months": len(vals),
                "avg_monthly_payment_value": stats.qfrac(Fraction(sum(vals)) / len(vals), "0.01") if vals else None,
                "avg_monthly_payment_ex_outlier_value": (stats.qfrac(Fraction(sum(vals_ex)) / len(vals_ex), "0.01")
                                                         if vals_ex else None),
                "median_monthly_payment_value": med,
                "outlier_customers": sum(1 for c in cs if c["is_outlier_customer"]),
                "avg_months_paying": stats.qfrac(Fraction(sum(c["paid_months"] for c in cs), n), "0.0001") if n else None,
                "avg_months_observable": stats.qfrac(Fraction(sum(obs), n), "0.0001") if n else None,
                "share_of_observable_months_paid": (stats.qfrac(Fraction(sum(c["paid_months"] for c in cs), sum(obs)),
                                                                "0.0001") if n else None),
                "is_low_n": n < p["low_n"], **L})

    # ---- §16 decision levers (fact_acquisition columns + four aggregates)
    fcm_by = {(r["customer_id"], r["month_key"]): r for r in T["fact_customer_month_revenue"]}
    levers.customer_columns(T["fact_acquisition"], fcm_by, data_through, p)
    lev = levers.build(T, gcfg, {"W": W, "reportable": reportable, "dim_month": dim_month,
                                 "data_through": data_through, "ind_scope": ind_scope, "agg_m": agg_m,
                                 "statuses": {k: statuses[k] for k in ("currency_status", "revenue_basis_status",
                                                                        "spend_basis_status", "scope_status")},
                                 "regime_labels": regime_labels(p["regime_boundary"])}, lin)
    T.update(lev["tables"])

    # ---- agg_won_spend_lag_corr
    L = lin("agg_won_spend_lag_corr")
    won_ok = {m for m in W if reportable[m] and data_through and m <= data_through
              and agg_m[mkey(m)]["won_is_complete"] and not mc[m]["is_unit_tripwire"]}
    spend_ok = {m for m in month_spend if not mc[m]["is_unit_tripwire"] and agg_m[mkey(m)]["won_is_complete"]}
    won_months = [m for m in W if reportable[m] and data_through and m <= data_through]
    series_list = categories + [g for g, _ in SERIES_GROUPS] + ["TOTAL"]
    scope_list = [("ALL", None)] + [(next(i["industry_code"] for i in gcfg["industries"] if i["industry_key"] == k), k)
                                     for k in ind_scope]
    by_mi_def = {}
    for d in gcfg["won_definitions"]:
        for scope, k in scope_list:
            ser = {}
            for m in won_months:
                if k is None:
                    a = agg_m[mkey(m)]
                    ser[m] = a["won_count"] if d == "first_payment" else a["won_new_logo_count"]
                else:
                    fs = by_mi.get((mkey(m), k), [])
                    ser[m] = len(fs) if d == "first_payment" else sum(1 for f in fs if f["is_new_logo"])
            by_mi_def[(d, scope)] = ser
    regime = {m: dim_month[m]["sm_regime"] for m in W}
    corr_check = []
    for d in gcfg["won_definitions"]:
        for scope, k in scope_list:
            won = by_mi_def[(d, scope)]
            for s in series_list:
                for lag in p["lags"]:
                    for method in METHODS:
                        pairs = []
                        for m in won_months:
                            sm = madd(m, -lag)
                            if m not in won_ok or sm not in spend_ok or sm < ws or month_spend[sm].get(s) is None:
                                continue
                            if method == "diff":
                                m1, sm1 = madd(m, -1), madd(sm, -1)
                                if (m1 not in won_ok or m1 not in won or sm1 not in spend_ok or sm1 < ws
                                        or month_spend[sm1].get(s) is None):
                                    continue
                                pairs.append((m, won[m] - won[m1], month_spend[sm][s] - month_spend[sm1][s], won[m]))
                            else:
                                pairs.append((m, won[m], month_spend[sm][s], won[m]))
                        n = len(pairs)
                        xs = [Fraction(x) for _, x, _, _ in pairs]
                        ys = [Fraction(y) for _, _, y, _ in pairs]
                        if method == "within_regime" and n:
                            for reg in {regime[m] for m, _, _, _ in pairs}:
                                idx = [i for i, (m, _, _, _) in enumerate(pairs) if regime[m] == reg]
                                mx = sum(xs[i] for i in idx) / len(idx)
                                my = sum(ys[i] for i in idx) / len(idx)
                                for i in idx:
                                    xs[i] -= mx
                                    ys[i] -= my
                        r, reason = None, None
                        if n < p["min_pairs"]:
                            reason = "too_few_pairs"
                        else:
                            r = stats.pearson(xs, ys)
                            if r is None:
                                reason = "constant_series"
                        crit = stats.r_critical(n, float(p["alpha_two_sided"])) if n >= p["min_pairs"] else None
                        mean = stats.qfrac(Fraction(sum(w for _, _, _, w in pairs), n), "0.0001") if n else None
                        row = {"won_definition": d, "scope_code": scope, "industry_key": k, "spend_series": s,
                               "category_key": cat_key.get(s), "lag_months": lag, "method": method,
                               "r": stats.q(r, "0.0001"), "n_pairs": n,
                               "r_critical_5pct": stats.q(Decimal(repr(crit)), "0.0001") if crit is not None else None,
                               "is_signal_5pct": (abs(r) >= Decimal(repr(crit))) if r is not None else None,
                               "won_mean_per_month": mean, "is_low_volume": mean < p["low_volume"] if mean is not None else None,
                               "first_won_month_key": mkey(pairs[0][0]) if n else None,
                               "last_won_month_key": mkey(pairs[-1][0]) if n else None, "null_reason": reason, **L}
                        T["agg_won_spend_lag_corr"].append(row)
                        corr_check.append((row, [float(x) for x in xs], [float(y) for y in ys]))

    # ---- gold_build_status
    rate = meta.get("rate") or {}
    T["gold_build_status"].append({
        "window_start_month": ws, "revenue_complete_through": as_of, "spend_complete_through": spend_through,
        "data_complete_through": data_through, "currency_code": tx_s.get("currency_code"), **statuses,
        "base_rates_match_seed": rate.get("base_match"), "rate_table_snapshot_id": rate.get("snapshot_id"),
        "rate_table_rows_sha256": rate.get("rows_sha256"), "controls_passed": True, **lin("gold_build_status")})

    res = {"run_id": run_id, "silver_run_id": silver_run_id, "tables": T, "findings": findings,
           "W": W, "window_start": ws, "as_of_month": as_of, "spend_complete_through": spend_through,
           "data_complete_through": data_through, "statuses": statuses, "rules_version": rules_version,
           "sha": sha, "built_at": built_at, "gold_model_version": meta["gold_model_version"],
           "rate": rate, "series": series_list, "categories": categories, "cat_hr": cat_hr,
           "ind_scope": ind_scope, "levers": lev}
    res["controls"] = controls(res, silver, gcfg, corr_check) + levers.controls(T, lev)
    res["figures"] = figures(res)
    return res


# --------------------------------------------------------------------------- #
# Run controls (§10)                                                          #
# --------------------------------------------------------------------------- #

def controls(res: dict, silver: dict, gcfg: dict, corr_check: list) -> list[dict]:
    T = res["tables"]
    out = []

    def check(cid: str, ok: bool, detail: str = "") -> None:
        out.append({"id": cid, "passed": bool(ok), "detail": "" if ok else detail})

    cust = silver["customer"]
    won_c = [c for c in cust if c["cohort_month"] is not None and c["cohort_censoring"] != "left"]
    agg = [r for r in T["agg_acquisition_month"] if r["is_won_reportable"]]
    per_m = defaultdict(int)
    for c in won_c:
        per_m[mkey(c["cohort_month"])] += 1
    per_m_ind = defaultdict(int)
    for r in T["agg_won_month_industry"]:
        per_m_ind[r["month_key"]] += r["won_count"]
    check("GC-01", len(T["fact_acquisition"]) == len(won_c) == sum(r["won_count"] for r in agg)
          == sum(r["won_count"] for r in T["agg_won_month_industry"])
          and all(r["won_count"] == per_m.get(r["month_key"], 0) == per_m_ind.get(r["month_key"], 0) for r in agg)
          and sum(per_m.values()) == len(won_c), "Won counts differ between fact, aggregates and silver")
    new_logo = sum(1 for c in cust if c["is_new_logo"])
    check("GC-02", sum(r["won_new_logo_count"] for r in agg) == new_logo
          == sum(r["new_logos"] or 0 for r in silver["month_control"])
          == sum(1 for r in silver["customer_month"] if r["lifecycle_state"] == "new"), "new-logo counts differ")
    check("GC-03", len(won_c) + sum(1 for c in cust if c["cohort_censoring"] == "left")
          == sum(1 for c in cust if c["cohort_month"] is not None), "Won + left != payers")
    fcm = {(r["customer_id"], r["month_key"]): r for r in T["fact_customer_month_revenue"]}
    rev_total = sum((c["first_paid_amount"] * REV for c in won_c), Decimal(0))
    rev_m = defaultdict(Decimal)
    for c in won_c:
        rev_m[mkey(c["cohort_month"])] += c["first_paid_amount"] * REV
    check("GC-04", sum(r["new_revenue_value"] for r in agg) == rev_total
          and all(r["new_revenue_value"] == rev_m.get(r["month_key"], Decimal(0)) for r in agg)
          and all(f["first_paid_amount_value"] == fcm[(f["customer_id"], f["won_month_key"])]["amount_value"]
                  for f in T["fact_acquisition"]), "new revenue differs from silver")
    sil_sp = {(mkey(r["month"]), r["category"]): r["spend_value"] for r in silver["sm_spend"]}
    code = {c["category_key"]: c["category_code"] for c in gcfg["spend_categories"]}
    mc = {mkey(r["month"]): r for r in silver["month_control"]}
    sums = defaultdict(Decimal)
    for r in T["fact_sm_spend"]:
        sums[r["month_key"]] += r["spend_value"]
    agg_all = {r["month_key"]: r for r in T["agg_acquisition_month"]}
    check("GC-05", len(T["fact_sm_spend"]) == len(silver["sm_spend"])
          and all(sil_sp.get((r["month_key"], code.get(r["category_key"]))) == r["spend_value"] for r in T["fact_sm_spend"])
          and all(sums[k] == mc[k]["sm_value_total"] == (agg_all[k]["spend_total_value"]
                                                         if agg_all[k]["spend_total_value"] is not None else sums[k])
                  for k in sums)
          and all(a["spend_total_value"] == a["spend_media_value"] + a["spend_other_value"] + a["spend_people_value"]
                  for a in T["agg_acquisition_month"] if a["spend_total_value"] is not None),
          "spend differs from silver or groups do not add up")
    sum_amt = defaultdict(Decimal)
    sum_norm = defaultdict(Decimal)
    for r in T["fact_customer_month_revenue"]:
        if r["amount"] is not None:
            sum_amt[r["customer_id"]] += r["amount"]
        if r["amount_normalized"] is not None:
            sum_norm[r["customer_id"]] += r["amount_normalized"]
    check("GC-06", len(T["fact_customer_month_revenue"]) == len(silver["customer_month"])
          and sum(r["amount_value"] or 0 for r in T["fact_customer_month_revenue"])
          == sum(r["amount_value"] for r in silver["transactions"])
          and all(sum_amt[c] == sum_norm[c] for c in set(sum_amt) | set(sum_norm)), "revenue fact differs from silver")
    months = {r["month_key"] for r in T["dim_month"]}
    custs = {r["customer_id"] for r in T["dim_customer"]}
    inds = {r["industry_key"] for r in T["dim_industry"]}
    cats = {r["category_key"] for r in T["dim_spend_category"]}
    fk = (all(r["won_month_key"] in months and r["customer_id"] in custs and r["industry_key"] in inds
              for r in T["fact_acquisition"])
          and all(r["month_key"] in months and r["customer_id"] in custs and r["industry_key"] in inds
                  for r in T["fact_customer_month_revenue"])
          and all(r["month_key"] in months and r["category_key"] in cats for r in T["fact_sm_spend"])
          and all(r["month_key"] in months and r["industry_key"] in inds for r in T["agg_won_month_industry"]))
    check("GC-07", fk and len(T["dim_customer"]) == len(cust) and [r["month"] for r in T["dim_month"]] == res["W"],
          "a foreign key does not resolve or a dimension is incomplete")
    hr_codes = {c["category_key"] for c in gcfg["spend_categories"] if c["is_hr_sensitive"]}
    check("GC-08", all(r["hr_sensitive"] == (r["category_key"] in hr_codes) for r in T["fact_sm_spend"]),
          "an HR category is outside the hr_sensitive=true partition")
    viol = lineage_violations(gcfg)
    check("GC-09", not viol, f"CDO-10 violations: {viol}")
    bad = []
    for t, rows in T.items():
        uses = schemas.USES[t]
        req = ["_run_id", "_silver_run_id", "_rules_version", "_gold_model_version", "as_of_month", "_built_at"]
        req += [f"_{d}_sha256" for d in ("transactions", "industry", "sm_spend") if d in uses]
        cols = {c for c, _ in schemas.COLUMNS[t]}
        if "_source_key" in cols:
            req += ["_source_key", "_ingested_at"]
        for r in rows:
            if any(r.get(c) is None for c in req) or ("_source_line" in cols and r["_source_line"] is None
                                                      and not r.get("is_hole")):
                bad.append(t)
                break
    check("GC-10", not bad, f"lineage NULL in {bad}")
    mism = 0
    for row, xs, ys in corr_check:
        if row["r"] is None:
            continue
        ref = statistics.correlation(xs, ys)
        if abs(Decimal(repr(ref)) - row["r"]) > Decimal("0.00005") or row["n_pairs"] != len(xs):
            mism += 1
    check("GC-11", mism == 0, f"{mism} stored r differ from statistics.correlation")
    return out


def lineage_violations(gcfg: dict) -> list[str]:
    """GC-09 / CDO-10 (§8.12): no object holds a monetary measure derived from
    spend at a grain that includes a customer, industry or cohort key. Reads the
    declared lineage, not column names."""
    seg = set(gcfg["segment_keys"])
    out = []
    for obj, lin in gcfg["lineage"].items():
        if lin["spend_money"] and seg & set(lin["grain"]):
            out.append(obj)
        cols = {c for c, _ in schemas.COLUMNS.get(obj, [])}
        if cols and lin["spend_money"] and seg & cols:
            out.append(obj)
    return sorted(set(out))


def assert_controls(res: dict) -> None:
    failed = [c for c in res["controls"] if not c["passed"]]
    if failed:
        raise GoldControlError("; ".join(f"{c['id']}: {c['detail']}" for c in failed))


def figures(res: dict) -> dict:
    """Non-sensitive headline figures for the run report (no HR category value)."""
    T = res["tables"]
    agg = [r for r in T["agg_acquisition_month"] if r["is_won_reportable"]]
    return {"rows": {t: len(rows) for t, rows in T.items()},
            "won": sum(r["won_count"] for r in agg), "won_new_logo": sum(r["won_new_logo_count"] for r in agg),
            "new_revenue_value": str(sum(r["new_revenue_value"] for r in agg)),
            "spend_total_won_months_value": str(sum(r["spend_total_value"] for r in agg
                                                    if r["spend_total_value"] is not None)),
            "corr_signals": sum(1 for r in T["agg_won_spend_lag_corr"] if r["is_signal_5pct"])}


# --------------------------------------------------------------------------- #
# The rates table: read-only state for this run (§6.4)                        #
# --------------------------------------------------------------------------- #

def rate_state(rows: list[dict], snapshot_id: int | None, gcfg: dict, now: datetime,
               previous: dict | None, previous_rows: list[dict] | None, previous_error: str | None = None) -> dict:
    """previous: the last published gold_build_status row (or None on the first
    build); previous_rows: the rate table read at its snapshot id."""
    findings = []
    for sid, s in sorted(funnel.scenario_status(rows, gcfg, now).items(), key=lambda kv: str(kv[0])):
        if s["status"] == "invalid":
            findings.append({"finding": "INVALID_SCENARIO", "scenario_id": sid, "failed_checks": s["failed_checks"]})
    base_match = funnel.base_matches_seed(rows, gcfg)
    if not base_match:
        findings.append({"finding": "BASE_DIFFERS_FROM_SEED",
                         "detail": "the current base rates are not the user's 2026-11-17 seed"})
    rewritten = None
    if previous and previous.get("rate_table_snapshot_id") is not None:
        if previous_rows is None:
            rewritten = f"the snapshot {previous['rate_table_snapshot_id']} is no longer readable ({previous_error})"
        else:
            missing = funnel.history_missing(previous_rows, rows)
            if missing:
                rewritten = f"{missing} rows of snapshot {previous['rate_table_snapshot_id']} are missing"
            elif funnel.rows_sha256(previous_rows) != previous.get("rate_table_rows_sha256"):
                rewritten = "the earlier snapshot no longer hashes to the stored rate_table_rows_sha256"
    if rewritten:
        findings.append({"finding": "RATE_HISTORY_REWRITTEN", "detail": rewritten})
    return {"snapshot_id": snapshot_id, "rows_sha256": funnel.rows_sha256(rows), "base_match": base_match,
            "findings": findings, "row_count": len(rows), "history_rewritten": bool(rewritten)}
