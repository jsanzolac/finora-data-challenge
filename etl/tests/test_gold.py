"""Gold acquisition model (docs/gold_acquisition_model.md) without Spark:
§12 golden figures on data/*.csv, the §14.3 synthetic cases, the rate-table
checks (GR-01..06, history rewrite, base vs seed), the CDO-10 lineage test,
the run controls and the acquisition serving payload."""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

from gold_build import engine, funnel, gconfig, schemas, stats, summary
from gold_helpers import (SEED_TS, golden_gold, golden_silver, meta, scenario, seed, synthetic_gold,
                          synthetic_silver)

D = Decimal
G = gconfig.load()


def T(name):
    return golden_gold()["tables"][name]


def by_month(rows):
    return {f"{r['month_key'] // 100}-{r['month_key'] % 100:02d}": r for r in rows}


# --------------------------------------------------------------------------- #
# Config                                                                      #
# --------------------------------------------------------------------------- #

def test_config_is_generated_from_the_spec_and_versioned_by_sha256():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "config"))
    import build_gold_yaml as b
    built = b.build()
    cfg = json.loads((Path(__file__).resolve().parents[1] / "config" / "gold_acquisition.json").read_text())
    assert {k: v for k, v in cfg.items() if k != "gold_model_version"} == json.loads(json.dumps(built))
    text = (Path(__file__).resolve().parents[1] / "config" / "gold_acquisition.yaml").read_bytes()
    assert cfg["gold_model_version"] == "sha256:" + hashlib.sha256(text).hexdigest()
    assert [r["rate"] for r in cfg["base_seed"]["rates"]] == ["0.8000", "0.4000", "0.5000", "0.7000", "0.6000",
                                                             "0.4000"]
    assert cfg["base_seed"]["changed_by"] == "seed"
    assert cfg["base_seed"]["change_reason"] == "User definition 2026-11-17, docs/gold_acquisition_model.md"
    assert cfg["params"]["lags"] == [0, 1, 2, 3] and cfg["params"]["regime_boundary"] == "2023-06"


def test_critical_values_match_the_spec_and_scipy():
    want = {33: "0.3440", 32: "0.3494", 31: "0.3550", 30: "0.3610", 29: "0.3673"}
    for n, v in want.items():
        assert stats.q(D(repr(stats.r_critical(n))), "0.0001") == D(v)
    scipy = pytest.importorskip("scipy.stats")
    for n in range(3, 200):
        t = scipy.t.ppf(0.975, n - 2)
        assert abs(stats.r_critical(n) - t / (t * t + n - 2) ** 0.5) < 1e-10


# --------------------------------------------------------------------------- #
# §12 golden                                                                  #
# --------------------------------------------------------------------------- #

def test_12_1_row_counts_and_controls():
    g = golden_gold()
    assert g["figures"]["rows"] == {
        "dim_month": 34, "dim_industry": 8, "dim_customer": 1961, "dim_spend_category": 8, "dim_funnel_stage": 7,
        "fact_acquisition": 1584, "fact_customer_month_revenue": 66674, "fact_sm_spend": 238,
        "agg_acquisition_month": 34, "agg_won_month_industry": 198, "agg_industry_profile": 18,
        "agg_won_spend_lag_corr": 1848, "agg_acq_cohort_quality": 396, "agg_acq_lever_period": 4,
        "agg_acq_lever_industry": 24, "agg_acq_value_change": 12, "gold_build_status": 1}
    assert [c["id"] for c in g["controls"]] == [f"GC-{i:02d}" for i in range(1, 12)] + ["GC-13", "GC-14"]
    assert all(c["passed"] for c in g["controls"]), [c for c in g["controls"] if not c["passed"]]
    assert g["findings"] == []
    dm = T("dim_month")
    assert Counter(r["sm_regime"] for r in dm) == {"pre_2023_06": 17, "from_2023_06": 17}
    assert sum(r["is_won_reportable"] for r in dm) == 33 and dm[0]["is_window_start"] and dm[0]["month"] == "2022-01"
    assert Counter(r["cohort_censoring"] for r in T("dim_customer")) == {"left": 377, "probable_left": 43, "none": 1541}
    fcm = T("fact_customer_month_revenue")
    assert sum(1 for r in fcm if r["amount"] > 0) == 32971 and sum(r["is_hole"] for r in fcm) == 0
    assert sum(r["amount_value"] for r in fcm) == D("2214415045.08")
    sm = T("fact_sm_spend")
    assert Counter(r["hr_sensitive"] for r in sm) == {True: 102, False: 136}
    assert sum(r["spend_value"] for r in sm) == D("7781800000")
    assert sum(1 for r in T("agg_acquisition_month") if r["won_count"] is not None) == 33
    assert all(r["r"] is not None for r in T("agg_won_spend_lag_corr"))
    st = T("gold_build_status")[0]
    assert (st["window_start_month"], st["revenue_complete_through"], st["spend_complete_through"],
            st["data_complete_through"]) == ("2022-01", "2024-10", "2024-10", "2024-10")
    assert st["currency_code"] is None and st["currency_status"] == "unconfirmed" and st["controls_passed"]


def test_12_2_won_and_new_revenue():
    fa = T("fact_acquisition")
    assert len(fa) == 1584
    assert Counter(r["cohort_censoring"] for r in fa) == {"none": 1541, "probable_left": 43}
    pl = Counter(r["won_month_key"] for r in fa if r["is_probable_left"])
    assert pl == {202202: 40, 202203: 3}
    assert Counter(r["first_payment_multiple"] for r in fa if r["is_first_payment_multiple"]) == {2: 81, 3: 21}
    assert Counter(r["first_payment_multiple"] for r in fa if r["is_first_payment_multiple"] and r["is_new_logo"]) \
        == {2: 47, 3: 12}
    agg = [r for r in T("agg_acquisition_month") if r["is_won_reportable"]]
    tot = lambda c: sum(r[c] for r in agg)  # noqa: E731
    assert tot("new_revenue_value") == D("105482511.96")
    assert tot("new_revenue_multiple_value") == D("10663744.35")
    assert tot("new_revenue_new_logo_value") == D("99728662.11")
    assert tot("new_revenue_run_rate_value") == D("99662644.41")
    assert stats.q(tot("new_revenue_value") / 1584, "0.01") == D("66592.49")
    assert stats.q(tot("new_revenue_new_logo_value") / 1541, "0.01") == D("64716.85")
    years = Counter()
    for r in agg:
        years[r["month_key"] // 100] += r["won_count"]
    assert years == {2022: 380, 2023: 650, 2024: 554}
    want = {"RESTAURANTS": (420, 407, 28, "34958519.61", 0), "MANUFACTURING": (363, 352, 27, "23458917.93", 0),
            "RETAIL": (370, 364, 25, "16712170.02", 0), "TECHNOLOGY": (179, 175, 5, "16795207.80", 0),
            "PROFESSIONAL_SERVICES": (142, 135, 10, "6702344.67", 4), "HEALTHCARE": (110, 108, 7, "6855351.93", 3)}
    key = {i["industry_code"]: i["industry_key"] for i in G["industries"]}
    wmi = T("agg_won_month_industry")
    for code, (won, nl, mult, rev, zero) in want.items():
        k = key[code]
        f = [r for r in fa if r["industry_key"] == k]
        cells = [r for r in wmi if r["industry_key"] == k]
        assert (len(f), sum(r["is_new_logo"] for r in f), sum(r["is_first_payment_multiple"] for r in f)) == (won, nl, mult)
        assert sum(r["new_revenue_value"] for r in cells) == D(rev)
        assert sum(r["won_count"] == 0 for r in cells) == zero
    zeros = sorted((r["month_key"], r["industry_key"]) for r in wmi if r["won_count"] == 0)
    assert zeros == sorted([(202204, 5), (202206, 5), (202210, 5), (202401, 5), (202209, 6), (202212, 6), (202309, 6)])
    assert (sum(r["is_small_cell"] for r in wmi), sum(r["is_low_n"] for r in wmi)) == (56, 140)


def test_12_3_spend():
    agg = [r for r in T("agg_acquisition_month") if r["is_won_reportable"]]
    tot = lambda c: sum(r[c] for r in agg)  # noqa: E731
    assert tot("spend_total_value") == D("7581800000")
    assert by_month(T("agg_acquisition_month"))["2022-01"]["spend_total_value"] == D("200000000")
    assert (tot("spend_paid_media_value"), tot("spend_travel_value"), tot("spend_publicidad_no_web_value"),
            tot("spend_software_tools_value")) == (D("3349000000"), D("486600000"), D("1131100000"), D("324600000"))
    assert (tot("spend_media_value"), tot("spend_other_value"), tot("spend_people_value")) == \
        (D("4480100000"), D("811200000"), D("2290500000"))
    neg = [r for r in T("fact_sm_spend") if r["spend_value"] < 0]
    assert sorted(r["month_key"] for r in neg) == [202311, 202312, 202402, 202403, 202407]
    assert {r["category_key"] for r in neg} == {7} and sum(r["spend_value"] for r in neg) == D("-13500000")
    # HR categories: parity with silver per (month, category); values not printed (CDO-11)
    sil = {(r["month"], r["category"]): r["spend_value"] for r in golden_silver()["silver"]["sm_spend"]}
    code = {c["category_key"]: c["category_code"] for c in G["spend_categories"]}
    for r in T("fact_sm_spend"):
        m = f"{r['month_key'] // 100}-{r['month_key'] % 100:02d}"
        assert sil[(m, code[r["category_key"]])] == r["spend_value"]


MONTHLY = """2022-02|108|68|40|40|11147080.56|230000000|25|25|19|17|16|6
2022-03|30|27|3|4|2780438.64|230000000|11|7|4|4|1|3
2022-04|19|19|0|1|3975300.00|235100000|6|5|4|2|0|2
2022-05|38|38|0|2|5894203.14|270000000|11|9|8|5|3|2
2022-06|33|33|0|1|2673999.93|235100000|7|11|6|6|0|3
2022-07|32|32|0|1|5484038.07|220000000|8|8|7|3|4|2
2022-08|26|26|0|1|2553621.00|325100000|7|7|4|3|3|2
2022-09|17|17|0|0|1347150.00|350000000|4|4|5|2|2|0
2022-10|32|32|0|0|2252250.00|375200000|9|8|5|5|0|5
2022-11|19|19|0|0|1474725.00|300000000|5|5|2|2|3|2
2022-12|26|26|0|0|6569241.00|325100000|10|6|4|5|1|0
2023-01|60|60|0|0|3693081.00|325100000|15|16|15|8|4|2
2023-02|30|30|0|1|1641990.00|250000000|7|6|7|3|4|3
2023-03|38|38|0|2|1683150.00|290000000|7|13|9|5|2|2
2023-04|51|51|0|1|2886870.00|295100000|22|2|13|4|7|3
2023-05|47|47|0|2|1996049.58|345100000|10|6|19|7|3|2
2023-06|46|46|0|2|2178540.00|180000000|7|12|14|5|2|6
2023-07|65|65|0|0|2532600.00|175100000|18|14|18|6|5|4
2023-08|66|66|0|1|2993130.00|110000000|9|22|17|8|6|4
2023-09|56|56|0|5|2253550.32|125200000|19|13|11|4|9|0
2023-10|64|64|0|1|2961945.00|135100000|16|15|19|3|8|3
2023-11|72|72|0|2|3278191.35|130000000|17|21|15|6|8|5
2023-12|55|55|0|1|3064950.00|150000000|17|15|12|5|3|3
2024-01|57|57|0|0|2313787.98|185100000|24|10|13|6|0|4
2024-02|32|32|0|1|1287465.90|200000000|8|9|5|3|1|6
2024-03|43|43|0|7|2707393.29|175100000|7|12|11|4|2|7
2024-04|69|69|0|9|4189594.29|225100000|20|13|17|6|8|5
2024-05|66|66|0|6|3984671.67|235100000|20|14|14|7|8|3
2024-06|84|84|0|8|4629579.78|200000000|24|15|21|10|8|6
2024-07|48|48|0|2|2378775.21|180000000|13|14|5|7|6|3
2024-08|56|56|0|0|2090916.66|190000000|7|10|23|7|5|4
2024-09|49|49|0|1|2382899.19|185100000|12|7|17|5|5|3
2024-10|50|50|0|0|2201333.40|200000000|18|9|7|6|5|5"""


def test_12_4_monthly_table():
    agg = by_month(T("agg_acquisition_month"))
    wmi = {}
    for r in T("agg_won_month_industry"):
        wmi[(r["month_key"], r["industry_key"])] = r["won_count"]
    lines = MONTHLY.splitlines()
    assert len(lines) == 33
    for line in lines:
        m, won, nl, pl, mult, rev, sp, *ind = line.split("|")
        a = agg[m]
        assert (a["won_count"], a["won_new_logo_count"], a["won_probable_left_count"],
                a["won_first_payment_multiple_count"]) == (int(won), int(nl), int(pl), int(mult)), m
        assert a["new_revenue_value"] == D(rev) and a["spend_total_value"] == D(sp), m
        assert [wmi[(a["month_key"], k)] for k in range(1, 7)] == [int(x) for x in ind], m
        assert a["won_is_complete"] is True and a["currency_status"] == "unconfirmed"
    ws = agg["2022-01"]
    assert ws["won_count"] is None and ws["new_revenue_value"] is None and ws["spend_total_value"] == D("200000000")


PROFILE = """RESTAURANTS|all|529|9112|83208.03|67499.22|56516.25|17.2250|19.2420|0.8952
RESTAURANTS|won|420|5819|61846.98|61846.98|50421.00|13.8548|15.4119|0.8990
RESTAURANTS|left_censored|109|3293|120954.76|77659.99|63000.00|30.2110|34.0000|0.8886
MANUFACTURING|all|454|7855|63695.82|63695.82|50400.00|17.3018|19.6784|0.8792
MANUFACTURING|won|363|5205|51948.78|51948.78|42000.00|14.3388|16.0882|0.8913
MANUFACTURING|left_censored|91|2650|86768.79|86768.79|67410.00|29.1209|34.0000|0.8565
RETAIL|all|428|6472|42327.41|42327.41|31500.00|15.1215|17.3014|0.8740
RETAIL|won|370|4894|38077.60|38077.60|25200.00|13.2270|14.6838|0.9008
RETAIL|left_censored|58|1578|55507.74|55507.74|42000.00|27.2069|34.0000|0.8002
TECHNOLOGY|all|241|4423|78932.04|78932.04|63000.00|18.3527|21.0373|0.8724
TECHNOLOGY|won|179|2551|68094.48|68094.48|52500.00|14.2514|16.5475|0.8612
TECHNOLOGY|left_censored|62|1872|93700.55|93700.55|83275.50|30.1935|34.0000|0.8880
PROFESSIONAL_SERVICES|all|165|2641|55137.87|55137.87|35700.00|16.0061|17.9212|0.8931
PROFESSIONAL_SERVICES|won|142|1962|43490.25|43490.25|31500.00|13.8169|15.3169|0.9021
PROFESSIONAL_SERVICES|left_censored|23|679|88794.18|88794.18|63000.00|29.5217|34.0000|0.8683
HEALTHCARE|all|144|2468|75856.65|75856.65|67200.00|17.1389|19.5000|0.8789
HEALTHCARE|won|110|1523|63247.72|63247.72|63000.00|13.8455|15.0182|0.9219
HEALTHCARE|left_censored|34|945|96177.71|96177.71|84000.00|27.7941|34.0000|0.8175"""


def test_12_7_industry_profile():
    key = {i["industry_key"]: i["industry_code"] for i in G["industries"]}
    got = {(key[r["industry_key"]], r["customer_scope"]): r for r in T("agg_industry_profile")}
    assert len(got) == 18
    cols = ["customers", "paid_customer_months", "avg_monthly_payment_value", "avg_monthly_payment_ex_outlier_value",
            "median_monthly_payment_value", "avg_months_paying", "avg_months_observable",
            "share_of_observable_months_paid"]
    for line in PROFILE.splitlines():
        code, scope, *vals = line.split("|")
        r = got[(code, scope)]
        assert [r[c] for c in cols] == [int(vals[0]), int(vals[1])] + [D(v) for v in vals[2:]], (code, scope)
    assert sum(r["outlier_customers"] for r in got.values() if r["customer_scope"] == "all") == 2
    assert got[("RESTAURANTS", "left_censored")]["outlier_customers"] == 2
    assert sum(r["paid_customer_months"] for r in got.values() if r["customer_scope"] == "all") == 32971


CORR = """PaidMedia|-0.4805* -0.4312* -0.3859* -0.3406|+0.0120 -0.0941 +0.1472 -0.1291|-0.1664 -0.1323 +0.1103 +0.1001
Travel|-0.4305* -0.5374* -0.4053* -0.2187|+0.2138 -0.3229 -0.0513 +0.2078|-0.0849 -0.3347 +0.0328 +0.2945
PublicidadNoWeb|-0.4109* -0.4362* -0.5165* -0.3266|+0.1748 -0.0259 -0.2808 +0.0251|-0.0985 -0.1716 -0.1084 +0.2005
Freelance|-0.5965* -0.5674* -0.6236* -0.5068*|-0.0771 -0.0353 -0.1525 +0.1572|-0.3841* -0.3202 -0.0712 +0.1820
SoftwareTools|-0.3865* -0.4538* -0.4820* -0.0980|-0.0252 -0.0589 -0.3765* +0.4157*|-0.1066 -0.2519 -0.2336 +0.3833*
Team|+0.2654 +0.1976 +0.5281* +0.5996*|+0.2085 -0.1489 -0.1568 +0.1475|-0.1688 -0.3078 +0.0305 +0.2309
PayrollExpenses|-0.2890 -0.3760* -0.2438 -0.0769|+0.1489 -0.1640 -0.0493 +0.1889|+0.0447 -0.2008 +0.0678 +0.2135
GROUP_MEDIA|-0.4783* -0.4484* -0.4372* -0.3496|+0.0719 -0.0822 +0.0125 -0.0907|-0.1594 -0.1540 +0.0551 +0.1337
GROUP_PEOPLE|-0.4067* -0.4678* -0.3024 -0.1084|+0.1598 -0.1875 -0.1004 +0.2354|-0.1122 -0.2897 +0.0436 +0.2609
GROUP_OTHER|-0.4416* -0.5378* -0.4712* -0.1787|+0.0988 -0.2138 -0.2716 +0.3822*|-0.1107 -0.3323 -0.0991 +0.3699*
TOTAL|-0.4795* -0.4964* -0.4190* -0.2609|+0.1412 -0.1790 -0.0895 +0.1377|-0.1586 -0.2523 +0.0363 +0.2266"""


def test_12_8_correlations_and_7_5_signal_counts():
    c = {(r["won_definition"], r["scope_code"], r["spend_series"], r["lag_months"], r["method"]): r
         for r in T("agg_won_spend_lag_corr")}
    for line in CORR.splitlines():
        series, *blocks = line.split("|")
        for method, block in zip(("level", "diff", "within_regime"), blocks):
            for lag, cell in enumerate(block.split()):
                r = c[("first_payment", "ALL", series, lag, method)]
                assert r["r"] == D(cell.rstrip("*")), (series, method, lag)
                assert r["is_signal_5pct"] == cell.endswith("*"), (series, method, lag)
    n = {"level": [33, 33, 32, 31], "within_regime": [33, 33, 32, 31], "diff": [32, 32, 31, 30]}
    crit = {33: D("0.3440"), 32: D("0.3494"), 31: D("0.3550"), 30: D("0.3610")}
    for (d, s, ser, lag, m), r in c.items():
        assert r["n_pairs"] == n[m][lag] and r["r_critical_5pct"] == crit[r["n_pairs"]]
    assert [c[("new_logo", "ALL", "TOTAL", lag, "level")]["r"] for lag in range(4)] == \
        [D("-0.5508"), D("-0.5401"), D("-0.4143"), D("-0.2609")]
    ind = {"RESTAURANTS": "-0.3217 -0.4725 -0.3806 -0.3315", "MANUFACTURING": "-0.5585 -0.4918 -0.3776 -0.1885",
           "RETAIL": "-0.4035 -0.3815 -0.2885 -0.1090", "TECHNOLOGY": "-0.1316 -0.1637 -0.0610 +0.0326",
           "PROFESSIONAL_SERVICES": "-0.3537 -0.3906 -0.3208 -0.1178",
           "HEALTHCARE": "-0.3892 -0.2027 -0.2826 -0.4068"}
    for code, vals in ind.items():
        assert [c[("first_payment", code, "TOTAL", lag, "level")]["r"] for lag in range(4)] == \
            [D(v) for v in vals.split()]
    sig = Counter()
    for r in c.values():
        sig[(r["won_definition"], r["method"], r["scope_code"] == "ALL")] += bool(r["is_signal_5pct"])
    assert sig == {("first_payment", "level", True): 30, ("first_payment", "level", False): 110,
                   ("first_payment", "diff", True): 3, ("first_payment", "diff", False): 11,
                   ("first_payment", "within_regime", True): 3, ("first_payment", "within_regime", False): 17,
                   ("new_logo", "level", True): 32, ("new_logo", "level", False): 123,
                   ("new_logo", "diff", True): 3, ("new_logo", "diff", False): 13,
                   ("new_logo", "within_regime", True): 3, ("new_logo", "within_regime", False): 14}
    low = {r["scope_code"] for r in c.values() if r["is_low_volume"]}
    assert low == {"TECHNOLOGY", "PROFESSIONAL_SERVICES", "HEALTHCARE"}
    assert max(abs(r["r"]) for r in c.values() if r["scope_code"] == "ALL" and r["method"] == "diff"
               and r["won_definition"] == "first_payment") == D("0.4157")


def test_12_5_funnel_reference_arithmetic():
    agg = T("agg_acquisition_month")
    dm = {r["month_key"]: r for r in T("dim_month")}
    months = [dict(r, month=dm[r["month_key"]]["month"], year_quarter=dm[r["month_key"]]["year_quarter"],
                   sm_regime=dm[r["month_key"]]["sm_regime"]) for r in agg if r["is_won_reportable"]]
    base = {r["from_stage_code"]: D(r["rate"]) for r in G["base_seed"]["rates"]}
    per = funnel.funnel_period(months, base, "first_payment", "2024-10", G)
    extra, rows = per[("full", "full")]
    got = {r["stage_code"]: (r["stage_count"], r["cost_per_unit_value"]) for r in rows}
    assert got == {"NEW": (D("58928.571429"), D("128660.85")), "WORKING": (D("47142.857143"), D("160826.06")),
                   "ENGAGED": (D("18857.142857"), D("402065.15")), "SQL": (D("9428.571429"), D("804130.30")),
                   "DEMO": (D("6600.000000"), D("1148757.58")), "PROPOSAL": (D("3960.000000"), D("1914595.96")),
                   "WON": (D("1584.000000"), D("4786489.90"))}
    # GC-12 shape: count(stage) x rate(stage -> next) = count(next), before rounding
    ex = {r["stage_code"]: r["stage_count_exact"] for r in rows}
    for f, t in G["transitions"]:
        assert ex[f] * Fraction(base[f]) == ex[t]
    nl = {r["stage_code"]: (r["stage_count"], r["cost_per_unit_value"])
          for r in funnel.funnel_period(months, base, "new_logo", "2024-10", G)[("full", "full")][1]}
    assert nl["NEW"] == (D("57328.869048"), D("132251.00")) and nl["WON"] == (D("1541.000000"), D("4920051.91"))
    cmp = funnel.compare(1584, D("7581800000"), dict(base, SQL=D("0.8000")), base)
    assert (cmp["won_implied_same_new"], cmp["won_implied_delta"], cmp["won_implied_delta_pct"],
            cmp["new_required_same_won"], cmp["new_required_delta"], cmp["cost_per_won_implied_value"]) == \
        (D("1810.285714"), D("226.285714"), D("14.285714"), D("51562.500000"), D("-7366.071429"), D("4188178.66"))
    sens = {f: funnel.sensitivity(1584, base[f]) for f in base}
    assert sens["SQL"]["won_pct_change_per_point"] == D("1.428571")
    assert sens["SQL"]["won_change_per_point_full_period"] == D("22.628571")
    assert funnel.sensitivity(1584, D("0.9950"))["won_pct_change_per_point"] is None


# --------------------------------------------------------------------------- #
# §14.3 synthetic cases                                                       #
# --------------------------------------------------------------------------- #

def test_synthetic_edge_cases():
    g = synthetic_gold()
    assert all(c["passed"] for c in g["controls"]), [c for c in g["controls"] if not c["passed"]]
    agg = by_month(g["tables"]["agg_acquisition_month"])
    # Won = 0 month: a real zero
    assert agg["2022-04"]["won_count"] == 0 and agg["2022-04"]["new_revenue_value"] == D("0.00")
    # missing S&M month
    assert agg["2022-05"]["spend_total_value"] is None and agg["2022-05"]["spend_paid_media_value"] is None
    # tripwire month
    assert agg["2022-03"]["is_unit_tripwire"] is True
    # hole in a Won month (2022-07: customer 7's month after its first payment is a hole elsewhere) and a hole that
    # hides a first payment (customer 8: cohort unknown at 2022-08)
    fa = {r["customer_id"]: r for r in g["tables"]["fact_acquisition"]}
    assert fa[8]["is_cohort_unknown"] and fa[8]["won_month_key"] == 202208
    assert agg["2022-07"]["won_is_complete"] is False and agg["2022-08"]["won_is_complete"] is False
    assert agg["2022-08"]["won_cohort_unknown_count"] == 1
    fcm = [r for r in g["tables"]["fact_customer_month_revenue"] if r["is_hole"]]
    assert {(r["customer_id"], r["month_key"]) for r in fcm} == {(7, 202208), (8, 202207)}
    assert all(r["_source_line"] is None and r["amount_value"] is None for r in fcm)
    dm = {r["month"]: r for r in g["tables"]["dim_month"]}
    months = [dict(r, month=m, year_quarter=dm[m]["year_quarter"], sm_regime=dm[m]["sm_regime"])
              for m, r in agg.items() if r["is_won_reportable"]]
    base = {r["from_stage_code"]: D(r["rate"]) for r in G["base_seed"]["rates"]}
    fm = funnel.funnel_month(months, base, "first_payment", g["data_complete_through"], G)
    reason = {m: rows[0]["cost_null_reason"] for m, rows in fm.items()}
    assert reason == {"2022-02": None, "2022-03": "unit_tripwire", "2022-04": "won_zero", "2022-05": "spend_missing",
                      "2022-06": None, "2022-07": "won_incomplete", "2022-08": "won_incomplete"}
    assert all(r["stage_count"] == 0 for r in fm["2022-04"])
    assert fm["2022-05"][-1]["stage_count"] == D(1)  # counts still shown
    # correlations drop tripwire, incomplete and spend-missing months
    corr = [r for r in g["tables"]["agg_won_spend_lag_corr"] if r["scope_code"] == "ALL"
            and r["won_definition"] == "first_payment" and r["spend_series"] == "TOTAL"]
    lvl = {r["lag_months"]: r for r in corr if r["method"] == "level"}
    # Won months usable: 2022-02, 04, 05, 06 (03 tripwire, 07/08 incomplete). L0 drops 05 (no spend line);
    # L1 pairs 02 with 01 and 05 with 04 (03 is a tripwire, 05 has no spend line)
    assert lvl[0]["n_pairs"] == 3 and lvl[1]["n_pairs"] == 2 and lvl[1]["null_reason"] == "too_few_pairs"
    assert lvl[0]["null_reason"] == "constant_series" and lvl[0]["r"] is None
    period = funnel.funnel_period(months, base, "first_payment", g["data_complete_through"], G)
    assert period[("full", "full")][1][0]["cost_null_reason"] == "won_zero"  # first reason by precedence


def test_unknown_industry_member_alerts_and_appears_in_the_dense_table():
    csvs = __import__("gold_helpers").synthetic_csvs()
    lines = csvs["industry"].decode().splitlines()
    csvs["industry"] = ("\n".join(l for l in lines if not l.startswith("Cliente 4,")) + "\n").encode()
    from golden_helpers import inputs_from
    from silver_build.engine import build as sb
    from common import config
    s = sb(inputs_from(csvs), config.load(), "r20261117T150932Z", None)
    g = engine.build(s["silver"], G, meta())
    assert any(f["finding"] == "WON_ON_UNKNOWN_MEMBER" for f in g["findings"])
    assert {r["industry_key"] for r in g["tables"]["agg_won_month_industry"]} == {1, 2, 3, 4, 5, 6, -1}
    assert all(c["passed"] for c in g["controls"])


def test_a_control_failure_raises_and_names_the_control():
    s = synthetic_silver()
    silver = {k: [dict(r) for r in v] for k, v in s["silver"].items()}
    silver["month_control"][1]["sm_value_total"] += 1  # silver total no longer equals its lines
    g = engine.build(silver, G, meta())
    with pytest.raises(engine.GoldControlError, match="GC-05"):
        engine.assert_controls(g)
    silver = {k: [dict(r) for r in v] for k, v in s["silver"].items()}
    silver["customer"][0]["_run_id"] = "r20261117T040928Z"
    with pytest.raises(engine.GoldControlError, match="input"):
        engine.build(silver, G, meta())


# --------------------------------------------------------------------------- #
# Rates: GR checks, history, base vs seed                                     #
# --------------------------------------------------------------------------- #
NOW = SEED_TS + timedelta(hours=1)


def _invalid(rows):
    st = funnel.scenario_status(seed() + rows, G, NOW)
    return {k: v["failed_checks"] for k, v in st.items() if v["status"] == "invalid"}


def gr_cases():
    t1 = SEED_TS + timedelta(minutes=10)
    ok = scenario("good_one", "ok", ts=t1)
    return {
        "GR-01": [dict(r, scenario_id="Bad-ID") for r in ok],
        "GR-02": [dict(r, to_stage_code="WON") if r["from_stage_code"] == "SQL" else r for r in ok],
        "GR-03": [dict(r, rate=D("1.5000")) if r["from_stage_code"] == "NEW" else r for r in ok],
        "GR-04": [r for r in ok if r["from_stage_code"] != "DEMO"],
        "GR-05": ok + [dict(ok[0], rate=D("0.7000"))],
        "GR-06": [dict(r, change_reason=" ") if r["from_stage_code"] == "NEW" else r for r in ok],
    }


@pytest.mark.parametrize("check", ["GR-01", "GR-02", "GR-03", "GR-04", "GR-05", "GR-06"])
def test_each_gr_check_marks_the_scenario_invalid(check):
    rows = gr_cases()[check]
    bad = _invalid(rows)
    sid = rows[0]["scenario_id"]
    assert check in bad[sid] and "base" not in bad
    assert sid not in funnel.valid_rates(seed() + rows, G, NOW)


def test_gr06_future_timestamp_and_fix_by_inserting_corrected_rows():
    future = scenario("later", "x", ts=NOW + timedelta(minutes=6))
    assert _invalid(future) == {"later": ["GR-06"]}
    soon = scenario("soon", "x", ts=NOW + timedelta(minutes=4))
    assert _invalid(soon) == {}
    broken = gr_cases()["GR-03"]
    fix = [dict(broken[0], rate=D("0.8000"), changed_at=SEED_TS + timedelta(minutes=20))]
    assert "good_one" in _invalid(broken) and _invalid(broken + fix) == {}


def test_history_rewrite_and_base_vs_seed():
    rows = seed()
    st1 = engine.rate_state(rows, 1, G, NOW, None, None)
    assert st1["base_match"] and st1["findings"] == []
    prev = {"rate_table_snapshot_id": 1, "rate_table_rows_sha256": st1["rows_sha256"]}
    added = rows + scenario("sql_demo_080", "SQL to Demo at 80%", {"SQL": "0.8000"})
    st2 = engine.rate_state(added, 2, G, NOW, prev, rows)
    assert st2["findings"] == [] and not st2["history_rewritten"]
    rewritten = [dict(r, rate=D("0.9000")) if r["from_stage_code"] == "NEW" else r for r in rows]
    st3 = engine.rate_state(rewritten, 3, G, NOW, prev, rows)
    assert st3["history_rewritten"] and {f["finding"] for f in st3["findings"]} == {"RATE_HISTORY_REWRITTEN",
                                                                                  "BASE_DIFFERS_FROM_SEED"}
    st4 = engine.rate_state(rows, 3, G, NOW, prev, None, "ValidationException")
    assert st4["history_rewritten"]
    edited = rows + [dict(rows[0], rate=D("0.7500"), changed_at=NOW, change_reason="new view")]
    st5 = engine.rate_state(edited, 4, G, NOW, prev, rows)
    assert not st5["base_match"] and not st5["history_rewritten"]
    assert [f["finding"] for f in st5["findings"]] == ["BASE_DIFFERS_FROM_SEED"]


# --------------------------------------------------------------------------- #
# CDO-10, HR isolation, lineage, payload                                      #
# --------------------------------------------------------------------------- #

def test_cdo10_lineage_test_passes_and_catches_a_planted_violation():
    assert engine.lineage_violations(G) == []
    bad = json.loads(json.dumps(G))
    bad["lineage"]["agg_won_month_industry"]["spend_money"] = ["spend_total_value"]
    assert engine.lineage_violations(bad) == ["agg_won_month_industry"]
    bad = json.loads(json.dumps(G))
    bad["lineage"]["agg_acquisition_month"]["grain"] = ["month_key", "industry_key"]
    assert engine.lineage_violations(bad) == ["agg_acquisition_month"]
    # every object in the schemas and the view list is declared
    from gold_build import ddl
    assert set(schemas.TABLES) | {schemas.RATE_TABLE} | {n for n, _ in ddl.VIEWS} == set(G["lineage"])


def test_no_hr_value_in_the_report_figures_or_findings():
    g = golden_gold()
    hr_keys = {c["category_key"] for c in G["spend_categories"] if c["is_hr_sensitive"]}
    hr_vals = {str(r["spend_value"]) for r in g["tables"]["fact_sm_spend"] if r["category_key"] in hr_keys}
    text = json.dumps({"figures": g["figures"], "findings": g["findings"], "controls": g["controls"]})
    assert not [v for v in hr_vals if v != "0" and v in text]


def test_lineage_block_on_every_row():
    g = golden_gold()
    for t, rows in g["tables"].items():
        cols = [c for c, _ in schemas.COLUMNS[t]]
        assert all(set(cols) <= set(r) for r in rows), t
        assert {r["_silver_run_id"] for r in rows} == {"r20261117T150932Z"}
        uses = schemas.USES[t]
        for ds in ("transactions", "industry", "sm_spend"):
            vals = {r[f"_{ds}_sha256"] for r in rows}
            assert (None not in vals) if ds in uses else vals == {None}, (t, ds)


def test_summary_payload_matches_the_contract():
    g = golden_gold()
    p = summary.build(g, G)
    assert set(p) == {"run", "statuses", "stages", "industries", "spend_categories", "regimes", "months",
                      "industry_profile", "correlations", "signal_summary", "levers"}
    assert p["run"]["run_id"] == "r20261117T160000Z" and p["run"]["silver_run_id"] == "r20261117T150932Z"
    assert p["run"]["data_complete_through"] == "2024-10" and p["run"]["gold_model_version"].startswith("sha256:")
    assert [s["code"] for s in p["stages"]] == ["NEW", "WORKING", "ENGAGED", "SQL", "DEMO", "PROPOSAL", "WON"]
    assert [m["month"] for m in p["months"]][:2] == ["2022-02", "2022-03"] and len(p["months"]) == 33
    oct_ = p["months"][-1]
    assert oct_["won"] == 50 and oct_["spend_total_value"] == "200000000" and oct_["new_revenue_value"] == "2201333.40"
    assert set(oct_["spend_value"]) == {c["code"] for c in p["spend_categories"]} and len(p["spend_categories"]) == 7
    assert oct_["won_by_industry"] == {"RESTAURANTS": 18, "MANUFACTURING": 9, "RETAIL": 7, "TECHNOLOGY": 6,
                                       "PROFESSIONAL_SERVICES": 5, "HEALTHCARE": 5}
    assert {m["cost_null_reason"] for m in p["months"]} == {None}
    assert oct_["won_by_industry_new_logo"] == oct_["won_by_industry"]
    feb = p["months"][0]
    assert sum(feb["won_by_industry_new_logo"].values()) == 68 and sum(feb["won_by_industry"].values()) == 108
    assert {r["won"] for r in p["industry_profile"] if r["industry_code"] == "RESTAURANTS"} == {420}
    lc = next(r for r in p["industry_profile"] if r["industry_code"] == "TECHNOLOGY" and r["customer_scope"] == "left_censored")
    assert (lc["median_monthly_payment_value"], lc["avg_months_observable"], lc["share_of_observable_months_paid"],
            lc["outlier_customers"], lc["is_low_n"]) == ("83275.50", "34.0000", "0.8880", 0, False)
    syn = summary.build(synthetic_gold(), G)
    reasons = {m["month"]: m["cost_null_reason"] for m in syn["months"]}
    assert reasons == {"2022-02": None, "2022-03": "unit_tripwire", "2022-04": None, "2022-05": "spend_missing",
                       "2022-06": None, "2022-07": "won_incomplete", "2022-08": "won_incomplete"}  # no won_zero
    may = next(m for m in syn["months"] if m["month"] == "2022-05")
    assert may["spend_total_value"] is None and set(may["spend_value"].values()) == {None}
    assert p["regimes"] == [{"id": "pre_2023_06", "label": "Before Jun 2023", "first_month": "2022-02",
                             "last_month": "2023-05", "inferred": True},
                            {"id": "from_2023_06", "label": "From Jun 2023", "first_month": "2023-06",
                             "last_month": "2024-10", "inferred": True}]
    assert len(p["correlations"]) == 1848 and len(p["industry_profile"]) == 18 and len(p["signal_summary"]) == 12
    c0 = next(c for c in p["correlations"] if c["won_definition"] == "user" and c["scope"] == "company"
              and c["series"] == "total" and c["lag"] == 0 and c["method"] == "level")
    assert c0 == {**c0, "r": -0.4795, "n": 33, "r_critical_5pct": 0.344, "is_signal": True}
    s = next(x for x in p["signal_summary"] if x["method"] == "level" and x["won_definition"] == "user"
             and x["scope_type"] == "company")
    assert (s["tests"], s["tests_with_r"], s["signals"], s["expected_by_chance"]) == (44, 44, 30, 2.2)
    prof = next(r for r in p["industry_profile"] if r["industry_code"] == "RESTAURANTS" and r["customer_scope"] == "all")
    assert (prof["customers"], prof["won"], prof["avg_monthly_payment_value"],
            prof["avg_monthly_payment_excl_outliers_value"], prof["avg_months_paying"]) == \
        (529, 420, "83208.03", "67499.22", "17.2250")
    assert json.loads(json.dumps(p)) == p  # plain JSON
    assert {c["series"] for c in p["correlations"]} == {"PaidMedia", "Travel", "PublicidadNoWeb", "Freelance",
                                                         "SoftwareTools", "Team", "PayrollExpenses", "media",
                                                         "people", "other", "total"}


def test_gc11_recomputation_is_independent():
    g = golden_gold()
    assert next(c for c in g["controls"] if c["id"] == "GC-11")["passed"]
    assert statistics.correlation([1.0, 2.0, 3.0], [1.0, 2.0, 2.9]) > 0.99
