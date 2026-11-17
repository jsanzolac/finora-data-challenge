"""The gold views (gold_build/ddl.py) on local Spark 3.5 over the engine's
tables: §12.5 and §12.6 exactly, GC-12 (every row against the exact reference),
the rate-edit flow, one invalid scenario per GR check, the cost reasons of the
synthetic lake, v_acquisition_month(_finance), v_corr_signal_summary and
v_sm_spend_shared. The Athena (Trino) rendering of the same SQL is checked on
Athena with infra/gold_athena_ddl.py precheck before deploy."""

from __future__ import annotations

import tempfile
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

pytest.importorskip("pyspark")

from gold_build import funnel, gconfig  # noqa: E402
from gold_helpers import (SEED_TS, golden_gold, register, rows, scenario, seed,  # noqa: E402
                          synthetic_gold)
from spark_support import spark_session  # noqa: E402
from test_gold import gr_cases  # noqa: E402

D = Decimal
G = gconfig.load()


@pytest.fixture(scope="module")
def spark():
    s, _ = spark_session(Path(tempfile.mkdtemp(prefix="finora-gold-views-")))
    yield s


@pytest.fixture
def golden(spark):
    register(spark, golden_gold(), seed() + scenario("sql_demo_080", "SQL to Demo at 80%", {"SQL": "0.8000"}))
    return spark


def months_of(gold):
    dm = {r["month_key"]: r for r in gold["tables"]["dim_month"]}
    return [dict(r, month=dm[r["month_key"]]["month"], year_quarter=dm[r["month_key"]]["year_quarter"],
                 sm_regime=dm[r["month_key"]]["sm_regime"]) for r in gold["tables"]["agg_acquisition_month"]
            if r["is_won_reportable"]]


def test_12_5_base_funnel_full_period_and_months(golden):
    def stage(where):
        return {r["stage_code"]: (r["stage_count"], r["cost_per_unit_value"]) for r in rows(golden, f"""
            SELECT stage_code, stage_count, cost_per_unit_value FROM {where}""")}
    full = stage("v_funnel_period WHERE scenario_id='base' AND won_definition='first_payment' AND period_type='full'")
    assert full == {"NEW": (D("58928.571429"), D("128660.85")), "WORKING": (D("47142.857143"), D("160826.06")),
                    "ENGAGED": (D("18857.142857"), D("402065.15")), "SQL": (D("9428.571429"), D("804130.30")),
                    "DEMO": (D("6600.000000"), D("1148757.58")), "PROPOSAL": (D("3960.000000"), D("1914595.96")),
                    "WON": (D("1584.000000"), D("4786489.90"))}
    nl = stage("v_funnel_period WHERE scenario_id='base' AND won_definition='new_logo' AND period_type='full'")
    assert nl == {"NEW": (D("57328.869048"), D("132251.00")), "WORKING": (D("45863.095238"), D("165313.74")),
                  "ENGAGED": (D("18345.238095"), D("413284.36")), "SQL": (D("9172.619048"), D("826568.72")),
                  "DEMO": (D("6420.833333"), D("1180812.46")), "PROPOSAL": (D("3852.500000"), D("1968020.77")),
                  "WON": (D("1541.000000"), D("4920051.91"))}
    oct_ = stage("v_funnel_month WHERE scenario_id='base' AND won_definition='first_payment' AND month='2024-10'")
    assert oct_ == {"NEW": (D("1860.119048"), D("107520.00")), "WORKING": (D("1488.095238"), D("134400.00")),
                    "ENGAGED": (D("595.238095"), D("336000.00")), "SQL": (D("297.619048"), D("672000.00")),
                    "DEMO": (D("208.333333"), D("960000.00")), "PROPOSAL": (D("125.000000"), D("1600000.00")),
                    "WON": (D("50.000000"), D("4000000.00"))}
    sep = stage("v_funnel_month WHERE scenario_id='base' AND won_definition='first_payment' AND month='2022-09'")
    assert sep["NEW"] == (D("632.440476"), D("553411.76")) and sep["WON"][1] == D("20588235.29")
    feb = stage("v_funnel_month WHERE scenario_id='base' AND won_definition='first_payment' AND month='2022-02'")
    assert feb["NEW"] == (D("4017.857143"), D("57244.44")) and feb["WON"][1] == D("2129629.63")
    dp = {r["stage_code"]: r["downstream_rate_product"] for r in rows(golden, """SELECT stage_code,
        downstream_rate_product FROM v_funnel_period WHERE scenario_id='base' AND won_definition='first_payment'
        AND period_type='full'""")}
    assert dp == {"NEW": D("0.026880000000"), "WORKING": D("0.033600000000"), "ENGAGED": D("0.084000000000"),
                  "SQL": D("0.168000000000"), "DEMO": D("0.240000000000"), "PROPOSAL": D("0.400000000000"),
                  "WON": D("1.000000000000")}
    real = {r["stage_code"]: r["real_or_estimated"] for r in rows(golden, "SELECT DISTINCT stage_code, real_or_estimated "
                                                                         "FROM v_funnel_month")}
    assert real["WON"] == "Real" and {v for k, v in real.items() if k != "WON"} == {"Estimated"}


PERIODS = {("sm_regime", "pre_2023_06"): (16, 606, "37.875000", "4600900000", "287556250.00", "7592244.22", None),
           ("sm_regime", "from_2023_06"): (17, 978, "57.529412", "2980900000", "175347058.82", "3047955.01", None),
           ("year", "2022"): (11, 380, "34.545455", "3095600000", "281418181.82", "8146315.79", True),
           ("year", "2023"): (12, 650, "54.166667", "2510700000", "209225000.00", "3862615.38", False),
           ("year", "2024"): (10, 554, "55.400000", "1975500000", "197550000.00", "3565884.48", True)}
QUARTERS = {"2022-Q1": (138, "460000000", "3333333.33"), "2022-Q2": (90, "740200000", "8224444.44"),
            "2022-Q3": (75, "895100000", "11934666.67"), "2022-Q4": (77, "1000300000", "12990909.09"),
            "2023-Q1": (128, "865100000", "6758593.75"), "2023-Q2": (144, "820200000", "5695833.33"),
            "2023-Q3": (187, "410300000", "2194117.65"), "2023-Q4": (191, "415100000", "2173298.43"),
            "2024-Q1": (132, "560200000", "4243939.39"), "2024-Q2": (219, "660200000", "3014611.87"),
            "2024-Q3": (153, "555100000", "3628104.58"), "2024-Q4": (50, "200000000", "4000000.00")}


def test_12_5_periods_and_quarters(golden):
    got = {(r["period_type"], r["period_id"]): r for r in rows(golden, """SELECT * FROM v_funnel_period
        WHERE scenario_id='base' AND won_definition='first_payment' AND stage_code='WON'""")}
    for k, (n, won, wpm, sp, spm, cpw, partial) in PERIODS.items():
        r = got[k]
        assert (r["months_in_period"], r["won_count"], r["won_per_month"], r["spend_total_value"],
                r["spend_per_month_value"], r["cost_per_unit_value"], r["is_partial_period"]) == \
            (n, won, D(wpm), D(sp), D(spm), D(cpw), partial), k
    for q, (won, sp, cpw) in QUARTERS.items():
        r = got[("quarter", q)]
        assert (r["won_count"], r["spend_total_value"], r["cost_per_unit_value"]) == (won, D(sp), D(cpw)), q
    assert got[("quarter", "2022-Q1")]["months_in_period"] == 2 and got[("quarter", "2022-Q1")]["is_partial_period"]
    assert got[("quarter", "2024-Q4")]["months_in_period"] == 1
    assert got[("full", "full")]["first_month"] == "2022-02" and got[("full", "full")]["last_month"] == "2024-10"


def test_12_6_scenario_compare_and_sensitivity(golden):
    c = rows(golden, """SELECT * FROM v_funnel_scenario_compare WHERE scenario_id='sql_demo_080'
        AND won_definition='first_payment' AND period_type='full'""")[0]
    assert (c["overall_rate"], c["overall_rate_base"], c["new_estimated_base"], c["won_implied_same_new"],
            c["won_implied_delta"], c["won_implied_delta_pct"], c["new_required_same_won"], c["new_required_delta"],
            c["cost_per_won_implied_value"]) == \
        (D("0.030720000000"), D("0.026880000000"), D("58928.571429"), D("1810.285714"), D("226.285714"),
         D("14.285714"), D("51562.500000"), D("-7366.071429"), D("4188178.66"))
    assert c["basis"] == "assumption: stage volumes and rates are not observed"
    b = rows(golden, """SELECT cost_per_won_implied_value, won_implied_delta FROM v_funnel_scenario_compare
        WHERE scenario_id='base' AND won_definition='first_payment' AND period_type='full'""")[0]
    assert b == {"cost_per_won_implied_value": D("4786489.90"), "won_implied_delta": D("0E-6")}
    s = {r["from_stage_code"]: (r["rate"], r["won_pct_change_per_point"], r["won_change_per_point_full_period"])
         for r in rows(golden, """SELECT * FROM v_funnel_rate_sensitivity WHERE scenario_id='base'
                                  AND won_definition='first_payment'""")}
    assert s == {"NEW": (D("0.8000"), D("1.250000"), D("19.800000")),
                 "WORKING": (D("0.4000"), D("2.500000"), D("39.600000")),
                 "ENGAGED": (D("0.5000"), D("2.000000"), D("31.680000")),
                 "SQL": (D("0.7000"), D("1.428571"), D("22.628571")),
                 "DEMO": (D("0.6000"), D("1.666667"), D("26.400000")),
                 "PROPOSAL": (D("0.4000"), D("2.500000"), D("39.600000"))}


def test_gc12_every_view_row_equals_the_exact_reference(golden):
    g = golden_gold()
    ms = months_of(g)
    rates = funnel.valid_rates(seed() + scenario("sql_demo_080", "x", {"SQL": "0.8000"}), G, SEED_TS)
    got_m = {(r["scenario_id"], r["won_definition"], r["month"], r["stage_code"]): r
             for r in rows(golden, "SELECT * FROM v_funnel_month")}
    got_p = {(r["scenario_id"], r["won_definition"], r["period_type"], r["period_id"], r["stage_code"]): r
             for r in rows(golden, "SELECT * FROM v_funnel_period")}
    n = 0
    for sid, rt in rates.items():
        for d in G["won_definitions"]:
            for m, srows in funnel.funnel_month(ms, rt, d, "2024-10", G).items():
                exact = {r["stage_code"]: r["stage_count_exact"] for r in srows}
                for f, t in G["transitions"]:  # count(stage) x rate = count(next), before rounding
                    assert exact[f] * Fraction(rt[f]) == exact[t]
                for r in srows:
                    v = got_m[(sid, d, m, r["stage_code"])]
                    assert (v["stage_count"], v["cost_per_unit_value"], v["cost_null_reason"],
                            v["downstream_rate_product"]) == (r["stage_count"], r["cost_per_unit_value"],
                                                              r["cost_null_reason"], r["downstream_rate_product"])
                    n += 1
            for (pt, pid), (extra, srows) in funnel.funnel_period(ms, rt, d, "2024-10", G).items():
                for r in srows:
                    v = got_p[(sid, d, pt, pid, r["stage_code"])]
                    assert (v["stage_count"], v["cost_per_unit_value"], v["won_per_month"],
                            v["spend_per_month_value"]) == (r["stage_count"], r["cost_per_unit_value"],
                                                            extra["won_per_month"], extra["spend_per_month_value"])
                    n += 1
    assert n == len(got_m) + len(got_p) == 2 * 2 * 33 * 7 + 2 * 2 * 18 * 7


def test_rate_edit_changes_the_views_and_invalid_scenarios_yield_no_funnel_rows(spark):
    g = golden_gold()
    base = seed()
    register(spark, g, base)
    before = rows(spark, "SELECT stage_count FROM v_funnel_period WHERE scenario_id='base' AND "
                         "won_definition='first_payment' AND period_type='full' AND stage_code='NEW'")[0]
    assert before["stage_count"] == D("58928.571429")
    # a user inserts one row with a later changed_at: SQL -> DEMO at 0.80 in base
    edit = [dict(next(r for r in base if r["from_stage_code"] == "SQL"), rate=D("0.8000"),
                 changed_at=SEED_TS + timedelta(minutes=1), changed_by="dashboard:0123456789ab",
                 change_reason="What if demos are booked faster")]
    register(spark, g, base + edit)
    cur = {r["from_stage_code"]: r["rate"] for r in rows(spark, "SELECT * FROM v_funnel_rate_current "
                                                                "WHERE scenario_id='base'")}
    assert cur["SQL"] == D("0.8000") and len(cur) == 6
    after = rows(spark, "SELECT stage_count FROM v_funnel_period WHERE scenario_id='base' AND "
                        "won_definition='first_payment' AND period_type='full' AND stage_code='NEW'")[0]
    assert after["stage_count"] == D("51562.500000")
    # every GR check, one scenario each: listed as invalid with its check, no funnel rows anywhere
    cases = gr_cases()
    allrows = base + [r for rs in cases.values() for r in rs]
    # the cases share the id good_one: give each its own id (GR-01 keeps its bad id)
    allrows = base
    for check, rs in cases.items():
        sid = rs[0]["scenario_id"] if check == "GR-01" else f"case_{check[-2:]}"
        allrows = allrows + [dict(r, scenario_id=sid) for r in rs]
    register(spark, g, allrows)
    st = {r["scenario_id"]: r for r in rows(spark, "SELECT * FROM v_funnel_scenario_status")}
    want = {"Bad-ID": "GR-01", "case_02": "GR-02", "case_03": "GR-03", "case_04": "GR-04", "case_05": "GR-05",
            "case_06": "GR-06"}
    ref = funnel.scenario_status(allrows, G, SEED_TS + timedelta(hours=1))
    for sid, check in want.items():
        assert st[sid]["status"] == "invalid" and check in st[sid]["failed_checks"].split(","), (sid, st[sid])
        assert st[sid]["failed_checks"].split(",") == ref[sid]["failed_checks"]
    assert st["base"]["status"] == "valid" and st["base"]["failed_checks"] == ""
    for view in ("v_funnel_month", "v_funnel_period", "v_funnel_scenario_compare", "v_funnel_rate_sensitivity"):
        ids = {r["scenario_id"] for r in rows(spark, f"SELECT DISTINCT scenario_id FROM {view}")}
        assert ids == {"base"}, view
    # GR-06: a changed_at more than 5 minutes in the future is invalid until corrected
    from datetime import datetime, timezone
    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    register(spark, g, base + scenario("later", "x", ts=utc_now + timedelta(minutes=30)))
    assert rows(spark, "SELECT status, failed_checks FROM v_funnel_scenario_status WHERE scenario_id='later'")[0] == \
        {"status": "invalid", "failed_checks": "GR-06"}


def test_synthetic_cost_reasons_on_the_views(spark):
    g = synthetic_gold()
    register(spark, g, seed())
    got = {r["month"]: r["cost_null_reason"] for r in rows(spark, """SELECT month, cost_null_reason FROM v_funnel_month
        WHERE scenario_id='base' AND won_definition='first_payment' AND stage_code='NEW'""")}
    assert got == {"2022-02": None, "2022-03": "unit_tripwire", "2022-04": "won_zero", "2022-05": "spend_missing",
                   "2022-06": None, "2022-07": "won_incomplete", "2022-08": "won_incomplete"}
    zero = rows(spark, """SELECT stage_count, cost_per_unit_value FROM v_funnel_month WHERE scenario_id='base'
        AND won_definition='first_payment' AND month='2022-04'""")
    assert {(r["stage_count"], r["cost_per_unit_value"]) for r in zero} == {(D("0E-6"), None)}
    p = rows(spark, """SELECT period_type, period_id, cost_null_reason, spend_total_value FROM v_funnel_period
        WHERE scenario_id='base' AND won_definition='first_payment' AND stage_code='WON'""")
    assert {(r["period_type"], r["period_id"]): r["cost_null_reason"] for r in p}[("full", "full")] == "won_zero"
    assert {(r["period_type"], r["period_id"]): r["spend_total_value"] for r in p}[("full", "full")] is None
    ref = funnel.funnel_period(months_of(g), funnel.valid_rates(seed(), G, SEED_TS)["base"], "first_payment",
                               g["data_complete_through"], G)
    assert {k: v[1][-1]["cost_null_reason"] for k, v in ref.items()} == \
        {(r["period_type"], r["period_id"]): r["cost_null_reason"] for r in p}


def test_monthly_views_signal_summary_and_shared_spend(golden):
    g = golden_gold()
    am = rows(golden, "SELECT * FROM v_acquisition_month ORDER BY month_key")
    assert len(am) == 33 and am[0]["month"] == "2022-02" and sum(r["won_count"] for r in am) == 1584
    assert sum(r["won_restaurants"] for r in am) == 420 and sum(r["won_healthcare"] for r in am) == 110
    assert sum(r["won_unknown_industry"] for r in am) == 0
    assert sum(r["spend_total_value"] for r in am) == D("7581800000")
    assert not {"spend_team_value", "spend_freelance_value", "spend_payroll_expenses_value"} & set(am[0])
    fin = rows(golden, "SELECT * FROM v_acquisition_month_finance ORDER BY month_key")
    hr = {c["category_key"]: c["category_code"] for c in G["spend_categories"] if c["is_hr_sensitive"]
          and c["category_key"] > 0}
    sm = {(r["month_key"], r["category_key"]): r["spend_value"] for r in g["tables"]["fact_sm_spend"]}
    for r in fin:
        for k, code in hr.items():
            col = {"Freelance": "spend_freelance_value", "Team": "spend_team_value",
                   "PayrollExpenses": "spend_payroll_expenses_value"}[code]
            assert r[col] == sm[(r["month_key"], k)]
        assert r["spend_people_value"] == r["spend_freelance_value"] + r["spend_team_value"] + \
            r["spend_payroll_expenses_value"]
    summ = {(r["method"], r["won_definition"], r["scope_type"]): (r["tests"], r["tests_with_r"], r["signals"],
                                                                 r["expected_by_chance"])
            for r in rows(golden, "SELECT * FROM v_corr_signal_summary")}
    assert len(summ) == 12
    assert summ[("level", "first_payment", "company")] == (44, 44, 30, D("2.20"))
    assert summ[("level", "first_payment", "industry")] == (264, 264, 110, D("13.20"))
    assert summ[("diff", "first_payment", "company")][2] == 3 and summ[("within_regime", "first_payment", "industry")][2] == 17
    assert summ[("level", "new_logo", "industry")][2] == 123 and summ[("diff", "new_logo", "industry")][2] == 13
    shared = rows(golden, "SELECT * FROM v_sm_spend_shared")
    assert len(shared) == 136 and not {r["category_key"] for r in shared} & set(hr) and "hr_sensitive" not in shared[0]


def test_v_acq_cohort_half_equals_the_python_rollup(golden):
    got = {(r["won_definition"], r["cohort_half"]): r for r in rows(golden, "SELECT * FROM v_acq_cohort_half")}
    want = {(r["won_definition"], r["cohort_half"]): r for r in golden_gold()["levers"]["cohort_half"]}
    assert set(got) == set(want) and len(got) == 12
    for k, w in want.items():
        assert {c: got[k][c] for c in w} == w, k
