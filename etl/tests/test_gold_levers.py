"""§16 decision levers on today's files: §16.5 expected figures (periods, industries,
value change, half-year cohorts, planner fixtures), the fact_acquisition columns,
GC-13 / GC-14 and the v1.3 snapshot rows."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from gold_build import gconfig, levers, summary
from gold_helpers import golden_gold, synthetic_gold

D = Decimal
G = gconfig.load()


def T(n):
    return golden_gold()["tables"][n]


def key(code):
    return next(i["industry_key"] for i in G["industries"] if i["industry_code"] == code)


PERIODS = {  # §16.5: months, Won, wpm, rr cust/no paid/immature, last cohort, rr, new MRR, spend/month, cost, payback,
    # m6 count/eligible/share, m12 count/eligible/share
    ("first_payment", "pre_2023_06"): (16, 606, "37.875000", 590, 16, 0, 202305, "55767.62", "2112198.61",
                                       "287556250.00", "7592244.22", "136.1", 563, 606, "0.9290", 528, 606, "0.8713"),
    ("first_payment", "from_2023_06"): (17, 978, "57.529412", 809, 14, 155, 202407, "42550.70", "2447916.75",
                                        "175347058.82", "3047955.01", "71.6", 656, 691, "0.9493", 332, 369, "0.8997"),
    ("new_logo", "pre_2023_06"): (16, 563, "35.187500", 547, 16, 0, 202305, "55401.22", "1949430.43",
                                  "287556250.00", "8172113.68", "147.5", 523, 563, "0.9290", 489, 563, "0.8686"),
    ("new_logo", "from_2023_06"): (17, 978, "57.529412", 809, 14, 155, 202407, "42550.70", "2447916.75",
                                   "175347058.82", "3047955.01", "71.6", 656, 691, "0.9493", 332, 369, "0.8997"),
}
COLS = ("months", "won_count", "won_per_month", "run_rate_customers", "run_rate_no_paid_customers",
        "run_rate_immature_customers", "run_rate_last_cohort_month_key", "run_rate_mrr_per_won_value",
        "new_mrr_per_month_value", "spend_per_month_value", "cost_per_won_value", "payback_months",
        "paying_m6_count", "paying_m6_eligible", "paying_m6_share", "paying_m12_count", "paying_m12_eligible",
        "paying_m12_share")


def norm(v):
    return D(v) if isinstance(v, str) else v


def test_16_5_periods():
    got = {(r["won_definition"], r["period_code"]): r for r in T("agg_acq_lever_period")}
    assert len(got) == 4
    for k, want in PERIODS.items():
        assert tuple(got[k][c] for c in COLS) == tuple(norm(v) for v in want), k
        assert got[k]["spend_total_value"] == (D("4600900000") if k[1] == "pre_2023_06" else D("2980900000"))
        assert got[k]["outlier_customers"] == 0 and got[k]["cost_null_reason"] is None and got[k]["is_inferred"]
    pre, post = got[("first_payment", "pre_2023_06")], got[("first_payment", "from_2023_06")]
    assert post["new_mrr_per_month_value"] - pre["new_mrr_per_month_value"] == D("335718.14")
    assert post["run_rate_mrr_per_won_value"] - pre["run_rate_mrr_per_won_value"] == D("-13216.92")


IND = {  # pre: Won, won share, rr cust, rr share, rr | from: same | m12 pre / from | m6 pre / from
    "RESTAURANTS": ((164, "0.2706", 156, "0.2644", "63081.55"), (256, "0.2618", 214, "0.2645", "47442.30"),
                    (143, 164, 72, 86), (148, 164, 170, 182)),
    "MANUFACTURING": ((138, "0.2277", 136, "0.2305", "53180.27"), (225, "0.2301", 195, "0.2410", "42684.42"),
                      (124, 138, 86, 97), (129, 138, 160, 170)),
    "RETAIL": ((131, "0.2162", 130, "0.2203", "43671.05"), (239, "0.2444", 191, "0.2361", "29406.94"),
               (112, 131, 85, 94), (127, 131, 161, 166)),
    "TECHNOLOGY": ((81, "0.1337", 76, "0.1288", "68409.85"), (98, "0.1002", 80, "0.0989", "53879.73"),
                   (66, 81, 31, 32), (72, 81, 59, 63)),
    "PROFESSIONAL_SERVICES": ((53, "0.0875", 53, "0.0898", "49363.76"), (89, "0.0910", 71, "0.0878", "35283.63"),
                              (48, 53, 36, 38), (49, 53, 57, 60)),
    "HEALTHCARE": ((39, "0.0644", 39, "0.0661", "59922.86"), (71, "0.0726", 58, "0.0717", "60606.24"),
                   (35, 39, 22, 22), (38, 39, 49, 50)),
}


def test_16_5_industries():
    got = {(r["period_code"], r["industry_key"]): r for r in T("agg_acq_lever_industry")
           if r["won_definition"] == "first_payment"}
    assert len(T("agg_acq_lever_industry")) == 24
    cols = ("won_count", "won_share", "run_rate_customers", "run_rate_share", "run_rate_mrr_per_won_value")
    for code, (pre, post, m12, m6) in IND.items():
        a, b = got[("pre_2023_06", key(code))], got[("from_2023_06", key(code))]
        assert tuple(a[c] for c in cols) == tuple(norm(v) for v in pre), code
        assert tuple(b[c] for c in cols) == tuple(norm(v) for v in post), code
        assert (a["paying_m12_count"], a["paying_m12_eligible"], b["paying_m12_count"], b["paying_m12_eligible"]) == m12
        assert (a["paying_m6_count"], a["paying_m6_eligible"], b["paying_m6_count"], b["paying_m6_eligible"]) == m6
        assert not a["is_low_n"] and not b["is_low_n"]
    for r in T("agg_acq_lever_industry"):
        assert not {"spend_total_value", "cost_per_won_value", "payback_months"} & set(r)  # CDO-10


def test_16_5_value_change_and_ticket_reference():
    g = golden_gold()
    for d, (tot, mix, within, mix_r, within_r) in {
            "first_payment": ("-13216.92", "-558.82", "-12658.10", "-428.14", "-12788.78"),
            "new_logo": ("-12850.52", "-618.47", "-12232.04", None, None)}.items():
        rows = [r for r in T("agg_acq_value_change") if r["won_definition"] == d]
        assert len(rows) == 6 and {r["null_reason"] for r in rows} == {None}
        q = lambda c: sum(r[c] for r in rows).quantize(D("0.01"), ROUND_HALF_UP)  # noqa: E731
        assert (q("mix_term_value") + q("within_term_value")) == D(tot) or q("mix_term_value") + q(
            "within_term_value") - D(tot) in (D("0.01"), D("-0.01"))
        assert (q("mix_term_value"), q("within_term_value")) == (D(mix), D(within))
        e = g["levers"]["exact_vc"][(d, "pre_2023_06", "from_2023_06")]
        assert qd(e["total"]) == D(tot) and e["mix"] + e["within"] == e["total"]
        if mix_r:
            assert (q("mix_reverse_term_value"), q("within_reverse_term_value")) == (D(mix_r), D(within_r))
    rows = [r for r in T("agg_acq_lever_industry") if r["won_definition"] == "first_payment"]
    pre = {r["industry_key"]: r for r in rows if r["period_code"] == "pre_2023_06"}
    post = [r for r in rows if r["period_code"] == "from_2023_06"]
    n = sum(r["run_rate_customers"] for r in post)
    ref = sum(Fraction(r["run_rate_customers"], n) * Fraction(pre[r["industry_key"]]["run_rate_mrr_per_won_value"])
              for r in post)
    assert qd(ref) == D("55208.80")  # each industry at its pre ticket, today's mix
    assert qd(Fraction(ref) / Fraction(D("42550.70")) - 1, "0.001") == D("0.297")  # the +29.7% reference


def qd(f, places="0.01"):
    from gold_build.stats import qfrac
    return qfrac(Fraction(f), places)


COHORTS = {"2022-H1": (228, 223, 5, 0, "62673.51", 214, 228, 200, 228),
           "2022-H2": (152, 144, 8, 0, "61597.90", 138, 152, 128, 152),
           "2023-H1": (272, 269, 3, 0, "45109.09", 256, 272, 238, 272),
           "2023-H2": (378, 374, 4, 0, "39934.42", 360, 378, 294, 323),
           "2024-H1": (351, 342, 9, 0, "44945.08", 251, 267, 0, 0),
           "2024-H2": (203, 47, 1, 155, "43384.87", 0, 0, 0, 0)}


def test_16_5_half_year_cohorts():
    ch = {(r["won_definition"], r["cohort_half"]): r for r in golden_gold()["levers"]["cohort_half"]}
    cols = ("won_count", "run_rate_customers", "run_rate_no_paid_customers", "run_rate_immature_customers",
            "run_rate_mrr_per_won_value", "paying_m6_count", "paying_m6_eligible", "paying_m12_count",
            "paying_m12_eligible")
    for h, want in COHORTS.items():
        assert tuple(ch[("first_payment", h)][c] for c in cols) == tuple(norm(v) for v in want), h
    pct = {h: (ch[("first_payment", h)]["paying_m6_share"], ch[("first_payment", h)]["paying_m12_share"]) for h in COHORTS}
    assert [None if v[0] is None else (v[0] * 100).quantize(D("0.1"), ROUND_HALF_UP) for v in pct.values()] == \
        [D("93.9"), D("90.8"), D("94.1"), D("95.2"), D("94.0"), None]
    assert ch[("first_payment", "2023-H2")]["is_complete_m6"] and not ch[("first_payment", "2023-H2")]["is_complete_m12"]
    assert not ch[("first_payment", "2024-H2")]["is_complete_run_rate"]
    nl = ch[("new_logo", "2022-H1")]
    assert (nl["won_count"], nl["run_rate_mrr_per_won_value"], nl["paying_m6_count"], nl["paying_m12_count"]) == \
        (185, D("63209.80"), 174, 161)
    for h in ("2022-H2", "2023-H1", "2023-H2", "2024-H1", "2024-H2"):
        assert {k: v for k, v in ch[("new_logo", h)].items() if k != "won_definition"} == \
            {k: v for k, v in ch[("first_payment", h)].items() if k != "won_definition"}


def planner(base, f=Fraction(1), dmix=Fraction(0), t=Fraction(0), g=Fraction(0)):
    q = lambda x, p: qd(x, p)  # noqa: E731
    won = q(Fraction(base["won_per_month"]) * f, "0.000001")
    rr = q((Fraction(base["run_rate_mrr_per_won_value"]) + dmix) * (1 + t), "0.01")
    mrr = q(Fraction(won) * Fraction(rr), "0.01")
    cost = q(Fraction(base["cost_per_won_value"]) * (1 + g) / f, "0.01")
    return won, rr, mrr, cost, q(Fraction(cost) / Fraction(rr), "0.1")


def test_16_5_planner_fixtures():
    base = next(r for r in T("agg_acq_lever_period") if r["won_definition"] == "first_payment"
                and r["period_code"] == "from_2023_06")
    ind = {r["industry_key"]: r for r in T("agg_acq_lever_industry") if r["won_definition"] == "first_payment"
           and r["period_code"] == "from_2023_06"}
    dmix = qd(Fraction(10, 100) * (Fraction(ind[key("TECHNOLOGY")]["run_rate_mrr_per_won_value"])
                                   - Fraction(ind[key("RETAIL")]["run_rate_mrr_per_won_value"])))
    assert dmix == D("2447.28")
    want = {"none": ("57.529412", "42550.70", "2447916.75", "3047955.01", "71.6"),
            "ticket": ("57.529412", "46805.77", "2692708.43", "3047955.01", "65.1"),
            "mix": ("57.529412", "44997.98", "2588707.33", "3047955.01", "67.7"),
            "spend": ("57.529412", "42550.70", "2447916.75", "2438364.01", "57.3"),
            "conv": ("60.405883", "42550.70", "2570312.61", "2902814.30", "68.2")}
    got = {"none": planner(base), "ticket": planner(base, t=Fraction(1, 10)),
           "mix": planner(base, dmix=Fraction(dmix)), "spend": planner(base, g=Fraction(-1, 5)),
           "conv": planner(base, f=Fraction(105, 100))}
    for k, w in want.items():
        assert got[k] == tuple(D(x) for x in w), k


def test_fact_acquisition_lever_columns():
    fa = T("fact_acquisition")
    from collections import Counter
    assert Counter(f["run_rate_status"] for f in fa) == {"ok": 590 + 809, "no_paid_month": 16 + 14, "immature": 155}
    assert all((f["run_rate_m2_4_value"] is None) == (f["run_rate_status"] != "ok") for f in fa)
    assert all(f["run_rate_m2_4_months"] is None for f in fa if f["run_rate_status"] == "immature")
    assert sum(f["paying_m6"] is not None for f in fa) == 606 + 691
    assert {f["cohort_half"] for f in fa} == set(COHORTS)


def test_gc13_gc14_pass_and_catch_a_break():
    g = golden_gold()
    assert {c["id"]: c["passed"] for c in g["controls"]}["GC-13"] and {c["id"]: c["passed"] for c in g["controls"]}["GC-14"]
    import copy
    Tb = copy.deepcopy(g["tables"])
    Tb["agg_acq_lever_period"][0]["payback_months"] += D("0.1")
    Tb["agg_acq_cohort_quality"][0]["won_count"] += 1
    c = {x["id"]: x["passed"] for x in levers.controls(Tb, g["levers"])}
    assert c == {"GC-13": False, "GC-14": False}


def test_synthetic_levers_are_censored_and_controls_hold():
    s = synthetic_gold()
    assert all(c["passed"] for c in s["controls"]), [c for c in s["controls"] if not c["passed"]]
    fa = {f["customer_id"]: f for f in s["tables"]["fact_acquisition"]}
    assert fa[10]["run_rate_status"] == "immature"  # Won 2022-07, data through 2022-08
    assert fa[3]["run_rate_status"] == "ok" and fa[3]["run_rate_m2_4_months"] == 3
    per = s["tables"]["agg_acq_lever_period"]
    assert {p["cost_null_reason"] for p in per} <= {"won_zero", "spend_missing", "unit_tripwire", "won_incomplete"}
    assert all(p["cost_per_won_value"] is None and p["payback_months"] is None for p in per)


def test_snapshot_levers_block_v13():
    L = summary.build(golden_gold(), G)["levers"]
    assert set(L) == {"definitions_version", "periods", "industries", "value_change", "cohorts"}
    assert L["definitions_version"] == "cdo-s16-2026-11-17"
    assert (len(L["periods"]), len(L["industries"]), len(L["value_change"]), len(L["cohorts"])) == (4, 24, 12, 12)
    p = next(r for r in L["periods"] if r["won_definition"] == "first_payment" and r["period_code"] == "pre_2023_06")
    assert (p["cost_per_won_value"], p["spend_per_month_value"], p["run_rate_mrr_per_won_value"], p["payback_months"],
            p["won_per_month"], p["paying_m6_share"], p["won_count"]) == \
        ("7592244.22", "287556250.00", "55767.62", "136.1", "37.875000", "0.9290", 606)
    assert p["spend_total_value"] == "4600900000.00" and "_run_id" not in p
    i = next(r for r in L["industries"] if r["industry_code"] == "RETAIL" and r["period_code"] == "from_2023_06"
             and r["won_definition"] == "first_payment")
    assert (i["industry_key"], i["won_share"], i["run_rate_mrr_per_won_value"]) == (3, "0.2444", "29406.94")
    v = [r for r in L["value_change"] if r["won_definition"] == "first_payment"]
    assert sum(D(r["mix_term_value"]) for r in v).quantize(D("0.01"), ROUND_HALF_UP) == D("-558.82")
    assert all(len(r["mix_term_value"].split(".")[1]) == 6 and len(r["value_from"].split(".")[1]) == 2 for r in v)
    c = next(r for r in L["cohorts"] if r["cohort_half"] == "2024-H1" and r["won_definition"] == "first_payment")
    assert (c["paying_m12_share"], c["is_complete_m6"], c["run_rate_mrr_per_won_value"]) == (None, False, "44945.08")
    assert "agg_acq_cohort_quality" not in str(L.keys())
