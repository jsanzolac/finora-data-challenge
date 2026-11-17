#!/usr/bin/env python3
"""Builds dashboard/mocks/acq/summary.json, the mock GET /api/acq/summary payload (contract v1.1).

MOCK ONLY. Run it from the repo root with the infra venv (it only reads data/ and etl/):

    infra/.venv/bin/python -I dashboard/mocks/acq/generate_fixture.py

Every figure is today's real value, computed the way docs/gold_acquisition_model.md
§5 and §7.4 describe and checked against its §12 expected results, EXCEPT:

* SYNTHETIC: the three HR-sensitive spend categories (Team, PayrollExpenses,
  Freelance) are Finance-only (CDO-11). Their monthly values in the fixture are
  synthetic placeholders: the real people-group total (shared with all roles,
  gold decision A1) split 50 / 35 / 15. The real HR values are read in memory
  only, to compute the correlation r (dimensionless, shared, decision A2), and
  are never written.
* The run ids and the model hash are mock values.
"""
import hashlib
import json
import math
import sys
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from statistics import correlation

from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "summary.json"
sys.path.insert(0, str(ROOT / "etl"))

from common import config  # noqa: E402
from common.records import make_bronze, strip_bronze  # noqa: E402
from silver_build.engine import DatasetInput, build  # noqa: E402

FILES = {"transactions": ("transactions/Transactions.csv", "Transactions.csv"),
         "industry": ("industry/Industry.csv", "Industry.csv"),
         "sm_spend": ("s_and_m/S&M_spend.csv", "S&M_spend.csv")}
REVENUE_SCALE = Decimal(10_000)
LAGS = [0, 1, 2, 3]
BOUNDARY = "2023-06"

STAGES = [("NEW", "New"), ("WORKING", "Working"), ("ENGAGED", "Engaged"), ("SQL", "SQL"),
          ("DEMO", "Demo"), ("PROPOSAL", "Proposal"), ("WON", "Won")]
INDUSTRIES = [("RESTAURANTS", "Restaurants"), ("MANUFACTURING", "Manufacturing"), ("RETAIL", "Retail"),
              ("TECHNOLOGY", "Technology"), ("PROFESSIONAL_SERVICES", "Professional services"),
              ("HEALTHCARE", "Healthcare")]
CATEGORIES = [("PaidMedia", "Paid digital media", False, "media"),
              ("Travel", "Travel", False, "other"),
              ("PublicidadNoWeb", "Offline advertising", False, "media"),
              ("Freelance", "Freelance and contractors", True, "people"),
              ("SoftwareTools", "S&M software and tools", False, "other"),
              ("Team", "S&M team", True, "people"),
              ("PayrollExpenses", "Payroll-related expenses", True, "people")]
HR = [c for c, _, hr, _ in CATEGORIES if hr]
# SYNTHETIC split of the real people total, in this order. Not the real shares.
SYNTHETIC_HR_SHARE = {"Team": Decimal("0.50"), "PayrollExpenses": Decimal("0.35"), "Freelance": Decimal("0.15")}
GROUPS = {"media": ["PaidMedia", "PublicidadNoWeb"], "other": ["Travel", "SoftwareTools"],
          "people": ["Team", "PayrollExpenses", "Freelance"]}


def q(value, places):
    return Decimal(value).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def shift(month, k):
    y, m = map(int, month.split("-"))
    m -= k
    while m < 1:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


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


def r_critical(n):
    t = student_t.ppf(0.975, n - 2)
    return t / math.sqrt(t * t + n - 2)


# ------------------------------------------------------------------ levers (contract v1.3 = gold §16)
def half_year(month):
    return f"{month[:4]}-H{1 if int(month[5:7]) <= 6 else 2}"


def plus(month, k):
    y, m = map(int, month.split("-"))
    t = y * 12 + (m - 1) + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def month_key(month):
    return int(month.replace("-", ""))


def compute_levers(silver, months, regimes, dct):
    """docs/gold_acquisition_model.md §16: agg_acq_lever_period, agg_acq_lever_industry,
    agg_acq_value_change and v_acq_cohort_half, for both Won definitions (contract v1.3)."""
    keys = {code: i + 1 for i, (code, _) in enumerate(INDUSTRIES)}
    norm = defaultdict(dict)
    paid = defaultdict(dict)
    for r in silver["customer_month"]:
        norm[r["customer_id"]][r["month"]] = Decimal(r["amount_normalized"]) if r["amount_normalized"] is not None else None
        paid[r["customer_id"]][r["month"]] = r["amount"] is not None and Decimal(r["amount"]) > 0
    spend = {m["month"]: Decimal(m["spend_total_value"]) for m in months}
    reportable = [m["month"] for m in months if m["month"] <= dct]

    def customer_facts(c):
        cm = c["cohort_month"]
        if plus(cm, 3) > dct:
            status, value = "immature", None
        else:
            q_months = [norm[c["customer_id"]].get(plus(cm, k)) for k in (1, 2, 3)]
            q_months = [v for v in q_months if v is not None and v > 0]
            status = "ok" if q_months else "no_paid_month"
            value = q(sum(q_months) * REVENUE_SCALE / len(q_months), "0.000001") if q_months else None
        m6 = None if plus(cm, 5) > dct else paid[c["customer_id"]].get(plus(cm, 5), False)
        m12 = None if plus(cm, 11) > dct else paid[c["customer_id"]].get(plus(cm, 11), False)
        return {"c": c, "month": cm, "industry": c["industry_code"], "status": status, "value": value, "m6": m6, "m12": m12,
                "outlier": bool(c["is_outlier_customer"])}

    definitions = {
        "first_payment": [c for c in silver["customer"] if c["cohort_month"] and c["cohort_censoring"] != "left" and c["cohort_month"] <= dct],
        "new_logo": [c for c in silver["customer"] if c["is_new_logo"] and c["cohort_month"] <= dct],
    }

    def measures(facts):
        ok = [f for f in facts if f["status"] == "ok"]
        out = {
            "won_count": len(facts),
            "run_rate_customers": len(ok),
            "run_rate_no_paid_customers": sum(1 for f in facts if f["status"] == "no_paid_month"),
            "run_rate_immature_customers": sum(1 for f in facts if f["status"] == "immature"),
            "outlier_customers": sum(1 for f in facts if f["outlier"]),
        }
        for k in ("m6", "m12"):
            eligible = [f for f in facts if f[k] is not None]
            count = sum(1 for f in eligible if f[k])
            out[f"paying_{k}_eligible"] = len(eligible)
            out[f"paying_{k}_count"] = count
            out[f"paying_{k}_share"] = f"{q(Decimal(count) / len(eligible), '0.0001')}" if eligible else None
        mean = sum(f["value"] for f in ok) / len(ok) if ok else None
        return out, mean, ok

    periods, industries, value_change, cohorts = [], [], [], []
    by_period = {}
    for definition, cs in definitions.items():
        facts = [customer_facts(c) for c in cs]
        for regime in regimes:
            pm = [m for m in reportable if regime["first_month"] <= m <= regime["last_month"]]
            pf = [f for f in facts if f["month"] in pm]
            out, mean, ok = measures(pf)
            won_per_month = q(Decimal(len(pf)) / len(pm), "0.000001")
            rr = q(mean, "0.01") if mean is not None else None
            spend_total = sum((spend[m] for m in pm), Decimal(0))
            cost = q(spend_total / len(pf), "0.01") if pf else None
            last_ok = max((f["month"] for f in pf if f["status"] != "immature"), default=None)
            periods.append({
                "won_definition": definition, "period_code": regime["id"], "period_label": regime["label"], "is_inferred": True,
                "first_month_key": month_key(pm[0]), "last_month_key": month_key(pm[-1]), "months": len(pm),
                **{k: out[k] for k in ("won_count",)},
                "won_per_month": f"{won_per_month}",
                **{k: out[k] for k in ("run_rate_customers", "run_rate_no_paid_customers", "run_rate_immature_customers")},
                "run_rate_last_cohort_month_key": month_key(last_ok) if last_ok else None,
                "run_rate_mrr_per_won_value": None if rr is None else f"{rr}",
                "new_mrr_per_month_value": None if rr is None else f"{q(won_per_month * rr, '0.01')}",
                "spend_total_value": f"{q(spend_total, '0.01')}",
                "spend_per_month_value": f"{q(spend_total / len(pm), '0.01')}",
                "cost_per_won_value": None if cost is None else f"{cost}",
                "payback_months": None if cost is None or rr is None else f"{q(cost / rr, '0.1')}",
                "cost_null_reason": None,
                **{k: out[k] for k in ("paying_m6_eligible", "paying_m6_count", "paying_m6_share",
                                       "paying_m12_eligible", "paying_m12_count", "paying_m12_share", "outlier_customers")},
            })
            by_period[(definition, regime["id"])] = {"mean": mean, "ok": len(ok), "industries": {}}
            for code, _ in INDUSTRIES:
                fi = [f for f in pf if f["industry"] == code]
                iout, imean, iok = measures(fi)
                by_period[(definition, regime["id"])]["industries"][code] = (Decimal(len(iok)) / len(ok), imean)
                industries.append({
                    "won_definition": definition, "period_code": regime["id"], "industry_key": keys[code], "industry_code": code,
                    "won_count": iout["won_count"], "won_share": f"{q(Decimal(len(fi)) / len(pf), '0.0001')}",
                    **{k: iout[k] for k in ("run_rate_customers", "run_rate_no_paid_customers", "run_rate_immature_customers")},
                    "run_rate_share": f"{q(Decimal(len(iok)) / len(ok), '0.0001')}",
                    "run_rate_mrr_per_won_value": None if imean is None else f"{q(imean, '0.01')}",
                    **{k: iout[k] for k in ("paying_m6_eligible", "paying_m6_count", "paying_m6_share",
                                            "paying_m12_eligible", "paying_m12_count", "paying_m12_share", "outlier_customers")},
                    "is_low_n": iout["run_rate_customers"] < 10,
                    "is_small_cell": 0 < iout["won_count"] < 5,
                })
        a, b = by_period[(definition, regimes[0]["id"])], by_period[(definition, regimes[1]["id"])]
        for code, _ in INDUSTRIES:
            s0, v0 = a["industries"][code]
            s1, v1 = b["industries"][code]
            value_change.append({
                "won_definition": definition, "from_period_code": regimes[0]["id"], "to_period_code": regimes[1]["id"],
                "industry_key": keys[code], "industry_code": code,
                "share_from": f"{q(s0, '0.0001')}", "share_to": f"{q(s1, '0.0001')}",
                "value_from": f"{q(v0, '0.01')}", "value_to": f"{q(v1, '0.01')}",
                "mix_term_value": f"{q((s1 - s0) * v0, '0.000001')}", "within_term_value": f"{q(s1 * (v1 - v0), '0.000001')}",
                "mix_reverse_term_value": f"{q((s1 - s0) * v1, '0.000001')}", "within_reverse_term_value": f"{q(s0 * (v1 - v0), '0.000001')}",
                "null_reason": None,
            })
        for h in sorted({half_year(f["month"]) for f in facts}):
            hf = [f for f in facts if half_year(f["month"]) == h]
            out, mean, ok = measures(hf)
            sums = sum((f["value"] for f in ok), Decimal(0))
            cohorts.append({
                "won_definition": definition, "cohort_half": h, **out,
                "run_rate_mrr_per_won_value": f"{q(sums / len(ok), '0.01')}" if ok else None,
                "is_complete_m6": out["paying_m6_eligible"] == out["won_count"],
                "is_complete_m12": out["paying_m12_eligible"] == out["won_count"],
                "is_complete_run_rate": out["run_rate_immature_customers"] == 0,
            })
    return {"definitions_version": "cdo-s16-2026-11-17", "periods": periods, "industries": industries,
            "value_change": value_change, "cohorts": cohorts}, by_period

def main():
    silver, W = load_silver()
    window_start = W[0]
    as_of = silver["month_control"][0]["as_of_month"]
    months = [m for m in W if m != window_start and m <= as_of]
    mc = {r["month"]: r for r in silver["month_control"]}
    customers = silver["customer"]

    won_customers = [c for c in customers if c["cohort_month"] and c["cohort_censoring"] != "left"]
    won = {m: 0 for m in months}
    won_nl = {m: 0 for m in months}
    won_ind = {m: {code: 0 for code, _ in INDUSTRIES} for m in months}
    won_ind_nl = {m: {code: 0 for code, _ in INDUSTRIES} for m in months}
    new_rev = {m: Decimal(0) for m in months}
    unknown_cohort = defaultdict(int)
    for c in won_customers:
        m = c["cohort_month"]
        won[m] += 1
        won_ind[m][c["industry_code"]] += 1
        new_rev[m] += c["first_paid_amount"] * REVENUE_SCALE
        if c["is_new_logo"]:
            won_nl[m] += 1
            won_ind_nl[m][c["industry_code"]] += 1
        if c["cohort_censoring"] == "unknown":
            unknown_cohort[m] += 1

    spend = defaultdict(dict)  # category -> month -> Decimal (real, in memory only)
    for r in silver["sm_spend"]:
        spend[r["category"]][r["month"]] = Decimal(r["spend_value"])
    total = {m: sum(spend[c][m] for c, *_ in CATEGORIES) for m in W}
    series = {c: spend[c] for c, *_ in CATEGORIES}
    for g, cols in GROUPS.items():
        series[g] = {m: sum(spend[c][m] for c in cols) for m in W}
    series["total"] = total

    # ---------------------------------------------------------------- months
    out_months = []
    for m in months:
        people = series["people"][m]
        synthetic = {c: q(people * SYNTHETIC_HR_SHARE[c], "1E5") for c in HR}
        synthetic["Team"] += people - sum(synthetic.values())  # keep media + other + people = total
        spend_value = {}
        for code, _, hr, _ in CATEGORIES:
            spend_value[code] = str(int(synthetic[code] if hr else spend[code][m]))
        won_is_complete = bool(mc[m]["revenue_is_complete"]) and unknown_cohort[m] == 0
        out_months.append({
            "month": m,
            "regime": "pre_2023_06" if m < BOUNDARY else "from_2023_06",
            "won": won[m],
            "won_new_logo": won_nl[m],
            "won_by_industry": won_ind[m],
            "won_by_industry_new_logo": won_ind_nl[m],
            "new_revenue_value": f"{q(new_rev[m], '0.01')}",
            "spend_value": spend_value,
            "spend_people_value": str(int(people)),
            "spend_total_value": str(int(total[m])),
            "won_is_complete": won_is_complete,
            "is_unit_tripwire": bool(mc[m]["is_unit_tripwire"]),
            "cost_null_reason": None,
            "is_low_n": won[m] < 10,
        })

    # ---------------------------------------------------------- correlations
    reportable = set(months)
    regime = {m: ("pre_2023_06" if m < BOUNDARY else "from_2023_06") for m in W}

    def ok_month(m):
        return m in mc and not mc[m]["is_unit_tripwire"]

    def pairs(won_series, sp, lag, method):
        out = []
        for m in months:
            sm = shift(m, lag)
            if sm not in sp or not ok_month(m) or not ok_month(sm):
                continue
            if method == "diff":
                pm, psm = shift(m, 1), shift(sm, 1)
                if pm not in reportable or psm not in sp or not ok_month(pm) or not ok_month(psm):
                    continue
                out.append((m, Decimal(won_series[m] - won_series[pm]), sp[sm] - sp[psm]))
            else:
                out.append((m, Decimal(won_series[m]), sp[sm]))
        if method == "within_regime":
            groups = defaultdict(list)
            for p in out:
                groups[regime[p[0]]].append(p)
            centred = []
            for g in groups.values():
                mw = sum(p[1] for p in g) / len(g)
                ms = sum(p[2] for p in g) / len(g)
                centred += [(p[0], p[1] - mw, p[2] - ms) for p in g]
            out = centred
        return out

    defs = {"user": (won, won_ind), "new_logo": (won_nl, won_ind_nl)}
    scopes = ["company"] + [code for code, _ in INDUSTRIES]
    series_order = [c for c, *_ in CATEGORIES] + ["media", "people", "other", "total"]
    correlations = []
    for d, (w_all, w_ind) in defs.items():
        for scope in scopes:
            w = w_all if scope == "company" else {m: w_ind[m][scope] for m in months}
            for s in series_order:
                for lag in LAGS:
                    for method in ["level", "diff", "within_regime"]:
                        p = pairs(w, series[s], lag, method)
                        xs = [float(a) for _, a, _ in p]
                        ys = [float(b) for _, _, b in p]
                        n = len(p)
                        r = None
                        null_reason = None
                        if n < 3:
                            null_reason = "too_few_pairs"
                        elif len(set(xs)) < 2 or len(set(ys)) < 2:
                            null_reason = "constant_series"
                        else:
                            r = correlation(xs, ys)
                        crit = r_critical(n) if n >= 3 else None
                        # gold §5.12: mean Won of the scope over the paired months (levels, whatever the method).
                        paired = [m for m, _, _ in pairs(w, series[s], lag, "level")]
                        won_mean = sum(w[m] for m in paired) / len(paired) if paired else 0
                        correlations.append({
                            "won_definition": d, "scope": scope, "series": s, "lag": lag, "method": method,
                            "r": None if r is None else float(q(r, "0.0001")),
                            "n": n,
                            "r_critical_5pct": None if crit is None else float(q(crit, "0.0001")),
                            "is_signal": bool(r is not None and abs(r) >= crit),
                            "is_low_volume": won_mean < 10,
                            "null_reason": null_reason,
                        })

    summary = []
    for method in ["level", "diff", "within_regime"]:
        for d in defs:
            for scope_type in ["company", "industry"]:
                rows = [c for c in correlations if c["method"] == method and c["won_definition"] == d
                        and (c["scope"] == "company") == (scope_type == "company")]
                with_r = [c for c in rows if c["r"] is not None]
                summary.append({"method": method, "won_definition": d, "scope_type": scope_type,
                                "tests": len(rows), "tests_with_r": len(with_r),
                                "signals": sum(1 for c in rows if c["is_signal"]),
                                "expected_by_chance": float(q(Decimal("0.05") * len(with_r), "0.1"))})

    # ------------------------------------------------------ industry profile
    paid = defaultdict(list)
    for r in silver["customer_month"]:
        if r["amount"] is not None and r["amount"] > 0 and r["month"] <= as_of:
            paid[r["customer_id"]].append(Decimal(r["amount"]) * REVENUE_SCALE)
    def months_between(first, last):
        fy, fm = map(int, first.split("-"))
        ly, lm = map(int, last.split("-"))
        return (ly - fy) * 12 + (lm - fm) + 1

    def median(values):
        ordered = sorted(values)
        mid = len(ordered) // 2
        return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2

    profile = []
    for code, _ in INDUSTRIES:
        # v1.1: `won` is the industry's Won (user definition), the same on every scope row.
        industry_won = sum(1 for c in won_customers if c["industry_code"] == code and c["cohort_month"] in reportable)
        for scope in ["all", "won", "left_censored"]:
            cs = [c for c in customers if c["industry_code"] == code and paid[c["customer_id"]]]
            if scope == "won":
                cs = [c for c in cs if c["cohort_month"] and c["cohort_censoring"] != "left"]
            elif scope == "left_censored":
                cs = [c for c in cs if c["cohort_censoring"] == "left"]
            pays = [a for c in cs for a in paid[c["customer_id"]]]
            pays_ex = [a for c in cs if not c["is_outlier_customer"] for a in paid[c["customer_id"]]]
            paid_months = sum(c["paid_months"] for c in cs)
            observable = [months_between(max(c["cohort_month"] or window_start, window_start), as_of) for c in cs]
            profile.append({
                "industry_code": code, "customer_scope": scope, "customers": len(cs), "won": industry_won,
                "avg_monthly_payment_value": f"{q(sum(pays) / len(pays), '0.01')}",
                "avg_monthly_payment_excl_outliers_value": f"{q(sum(pays_ex) / len(pays_ex), '0.01')}",
                "median_monthly_payment_value": f"{q(median(pays), '0.01')}",
                "outlier_customers": sum(1 for c in cs if c["is_outlier_customer"]),
                "avg_months_paying": f"{q(Decimal(paid_months) / len(cs), '0.0001')}",
                "avg_months_observable": f"{q(Decimal(sum(observable)) / len(cs), '0.0001')}",
                "share_of_observable_months_paid": f"{q(Decimal(paid_months) / sum(observable), '0.0001')}",
                "is_low_n": len(cs) < 10,
            })

    # ------------------------------------------- checks against gold spec §12
    assert sum(won.values()) == 1584 and sum(won_nl.values()) == 1541, "§12.2 Won"
    assert q(sum(new_rev.values()), "0.01") == Decimal("105482511.96"), "§12.2 new revenue"
    assert sum(total[m] for m in months) == Decimal(7581800000), "§12.3 spend"
    assert won["2024-10"] == 50 and total["2024-10"] == Decimal(200000000), "§12.4 2024-10"

    def corr(d, scope, s, lag, method):
        return next(c for c in correlations if (c["won_definition"], c["scope"], c["series"], c["lag"], c["method"])
                    == (d, scope, s, lag, method))

    expected_812 = {("total", "level"): [-0.4795, -0.4964, -0.4190, -0.2609],
                    ("total", "diff"): [0.1412, -0.1790, -0.0895, 0.1377],
                    ("total", "within_regime"): [-0.1586, -0.2523, 0.0363, 0.2266],
                    ("SoftwareTools", "diff"): [-0.0252, -0.0589, -0.3765, 0.4157],
                    ("Team", "within_regime"): [-0.1688, -0.3078, 0.0305, 0.2309],
                    ("other", "within_regime"): [-0.1107, -0.3323, -0.0991, 0.3699]}
    for (s, method), values in expected_812.items():
        got = [corr("user", "company", s, lag, method)["r"] for lag in LAGS]
        assert got == values, f"§12.8 {s} {method}: {got}"
    assert [corr("user", "RESTAURANTS", "total", lag, "level")["r"] for lag in LAGS] == [-0.3217, -0.4725, -0.3806, -0.3315]
    assert [corr("new_logo", "company", "total", lag, "level")["r"] for lag in LAGS] == [-0.5508, -0.5401, -0.4143, -0.2609]
    assert [corr("user", "company", "total", lag, "diff")["n"] for lag in LAGS] == [32, 32, 31, 30]
    assert [corr("user", "company", "total", lag, "level")["r_critical_5pct"] for lag in LAGS] == [0.344, 0.344, 0.3494, 0.355]
    got_summary = {(s["method"], s["won_definition"], s["scope_type"]): s["signals"] for s in summary}
    assert got_summary == {
        ("level", "user", "company"): 30, ("level", "user", "industry"): 110,
        ("diff", "user", "company"): 3, ("diff", "user", "industry"): 11,
        ("within_regime", "user", "company"): 3, ("within_regime", "user", "industry"): 17,
        ("level", "new_logo", "company"): 32, ("level", "new_logo", "industry"): 123,
        ("diff", "new_logo", "company"): 3, ("diff", "new_logo", "industry"): 13,
        ("within_regime", "new_logo", "company"): 3, ("within_regime", "new_logo", "industry"): 14,
    }, got_summary
    rest = {p["customer_scope"]: p for p in profile if p["industry_code"] == "RESTAURANTS"}
    assert (rest["all"]["customers"], rest["all"]["avg_monthly_payment_value"],
            rest["all"]["avg_monthly_payment_excl_outliers_value"], rest["all"]["avg_months_paying"]) == \
        (529, "83208.03", "67499.22", "17.2250"), rest["all"]
    assert (rest["won"]["customers"], rest["won"]["avg_monthly_payment_value"]) == (420, "61846.98")
    assert [rest[k]["median_monthly_payment_value"] for k in ("all", "won", "left_censored")] == ["56516.25", "50421.00", "63000.00"]
    assert [rest[k]["avg_months_observable"] for k in ("all", "won", "left_censored")] == ["19.2420", "15.4119", "34.0000"]
    assert [rest[k]["share_of_observable_months_paid"] for k in ("all", "won", "left_censored")] == ["0.8952", "0.8990", "0.8886"]
    assert [rest[k]["outlier_customers"] for k in ("all", "won", "left_censored")] == [2, 0, 2]
    assert all(rest[k]["won"] == 420 for k in rest)
    health = {p["customer_scope"]: p for p in profile if p["industry_code"] == "HEALTHCARE"}
    assert [health[k]["share_of_observable_months_paid"] for k in ("all", "won", "left_censored")] == ["0.8789", "0.9219", "0.8175"]
    low = {c["scope"] for c in correlations if c["is_low_volume"] and c["won_definition"] == "user"}
    assert low == {"TECHNOLOGY", "PROFESSIONAL_SERVICES", "HEALTHCARE"}, low
    assert all(c["null_reason"] is None for c in correlations), "§12.1: no NULL r today"
    assert sum(sum(m["won_by_industry_new_logo"].values()) for m in out_months) == 1541
    assert len(correlations) == 1848

    regimes_out = [
        {"id": "pre_2023_06", "label": "Before Jun 2023", "first_month": months[0], "last_month": shift(BOUNDARY, 1), "inferred": True},
        {"id": "from_2023_06", "label": "From Jun 2023", "first_month": BOUNDARY, "last_month": months[-1], "inferred": True},
    ]
    levers, lever_means = compute_levers(silver, out_months, regimes_out, as_of)
    # --- docs/gold_acquisition_model.md §16.5 expected figures
    P = {(r["won_definition"], r["period_code"]): r for r in levers["periods"]}
    pre, post = P[("first_payment", "pre_2023_06")], P[("first_payment", "from_2023_06")]
    assert [pre[k] for k in ("months", "won_count", "won_per_month", "run_rate_customers", "run_rate_no_paid_customers", "run_rate_immature_customers")] == [16, 606, "37.875000", 590, 16, 0], pre
    assert [post[k] for k in ("months", "won_count", "won_per_month", "run_rate_customers", "run_rate_no_paid_customers", "run_rate_immature_customers")] == [17, 978, "57.529412", 809, 14, 155], post
    assert (pre["run_rate_last_cohort_month_key"], post["run_rate_last_cohort_month_key"]) == (202305, 202407)
    assert [pre[k] for k in ("run_rate_mrr_per_won_value", "new_mrr_per_month_value", "spend_per_month_value", "cost_per_won_value", "payback_months")] == [
        "55767.62", "2112198.61", "287556250.00", "7592244.22", "136.1"], pre
    assert [post[k] for k in ("run_rate_mrr_per_won_value", "new_mrr_per_month_value", "spend_per_month_value", "cost_per_won_value", "payback_months")] == [
        "42550.70", "2447916.75", "175347058.82", "3047955.01", "71.6"], post
    assert [pre[k] for k in ("paying_m6_count", "paying_m6_eligible", "paying_m6_share", "paying_m12_count", "paying_m12_eligible", "paying_m12_share")] == [563, 606, "0.9290", 528, 606, "0.8713"]
    assert [post[k] for k in ("paying_m6_count", "paying_m6_eligible", "paying_m6_share", "paying_m12_count", "paying_m12_eligible", "paying_m12_share")] == [656, 691, "0.9493", 332, 369, "0.8997"]
    npre = P[("new_logo", "pre_2023_06")]
    assert [npre[k] for k in ("won_count", "won_per_month", "run_rate_customers", "run_rate_mrr_per_won_value", "new_mrr_per_month_value", "cost_per_won_value", "payback_months")] == [
        563, "35.187500", 547, "55401.22", "1949430.43", "8172113.68", "147.5"], npre
    I = {(r["won_definition"], r["period_code"], r["industry_code"]): r for r in levers["industries"]}
    assert [I[("first_payment", "pre_2023_06", "RETAIL")][k] for k in ("won_count", "won_share", "run_rate_customers", "run_rate_share", "run_rate_mrr_per_won_value")] == [131, "0.2162", 130, "0.2203", "43671.05"]
    assert [I[("first_payment", "from_2023_06", "TECHNOLOGY")][k] for k in ("won_count", "won_share", "run_rate_customers", "run_rate_share", "run_rate_mrr_per_won_value")] == [98, "0.1002", 80, "0.0989", "53879.73"]
    assert I[("first_payment", "from_2023_06", "HEALTHCARE")]["run_rate_mrr_per_won_value"] == "60606.24"
    assert (I[("first_payment", "from_2023_06", "RESTAURANTS")]["paying_m12_count"], I[("first_payment", "from_2023_06", "RESTAURANTS")]["paying_m12_eligible"]) == (72, 86)
    def vc_total(definition, field):
        return q(sum(Decimal(r[field]) for r in levers["value_change"] if r["won_definition"] == definition), "0.01")
    assert (vc_total("first_payment", "mix_term_value"), vc_total("first_payment", "within_term_value")) == (Decimal("-558.82"), Decimal("-12658.10"))
    assert (vc_total("first_payment", "mix_reverse_term_value"), vc_total("first_payment", "within_reverse_term_value")) == (Decimal("-428.14"), Decimal("-12788.78"))
    assert (vc_total("new_logo", "mix_term_value"), vc_total("new_logo", "within_term_value")) == (Decimal("-618.47"), Decimal("-12232.04"))
    fp = lever_means
    assert q(fp[("first_payment", "from_2023_06")]["mean"] - fp[("first_payment", "pre_2023_06")]["mean"], "0.01") == Decimal("-13216.92")
    C = {(r["won_definition"], r["cohort_half"]): r for r in levers["cohorts"]}
    assert [C[("first_payment", h)]["run_rate_mrr_per_won_value"] for h in ("2022-H1", "2022-H2", "2023-H1", "2023-H2", "2024-H1", "2024-H2")] == [
        "62673.51", "61597.90", "45109.09", "39934.42", "44945.08", "43384.87"]
    c23 = C[("first_payment", "2023-H2")]
    assert (c23["paying_m12_count"], c23["paying_m12_eligible"], c23["is_complete_m12"], c23["paying_m6_share"]) == (294, 323, False, "0.9524")
    assert (C[("new_logo", "2022-H1")]["won_count"], C[("new_logo", "2022-H1")]["run_rate_mrr_per_won_value"]) == (185, "63209.80")
    assert len(levers["periods"]) == 4 and len(levers["industries"]) == 24 and len(levers["value_change"]) == 12

    payload = {
        "run": {
            "run_id": "r20261117T163000Z",
            "silver_run_id": "r20261117T150932Z",
            "built_at": "2026-11-17T16:36:00Z",
            "as_of_month": as_of,
            "data_complete_through": as_of,
            "gold_model_version": "sha256:mock-fixture-not-a-real-model-hash",
            "base_rates_match_seed": True,
        },
        "statuses": {"currency_status": "unconfirmed", "revenue_basis_status": "unconfirmed",
                     "spend_basis_status": "unconfirmed", "scope_status": "unconfirmed"},
        "stages": [{"code": c, "label": label, "order": i + 1} for i, (c, label) in enumerate(STAGES)],
        "industries": [{"code": c, "label": label} for c, label in INDUSTRIES],
        "spend_categories": [{"code": c, "label": label, "hr_sensitive": hr, "group": g}
                             for c, label, hr, g in CATEGORIES],
        "regimes": [
            {"id": "pre_2023_06", "label": "Before Jun 2023", "first_month": months[0],
             "last_month": shift(BOUNDARY, 1), "inferred": True},
            {"id": "from_2023_06", "label": "From Jun 2023", "first_month": BOUNDARY,
             "last_month": months[-1], "inferred": True},
        ],
        "months": out_months,
        "industry_profile": profile,
        "correlations": correlations,
        "signal_summary": summary,
        "levers": levers,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out_months)} months, {len(correlations)} correlations, "
          f"{len(profile)} profile rows; all §12 checks passed")


if __name__ == "__main__":
    main()
