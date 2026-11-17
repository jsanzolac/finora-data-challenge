"""Golden run over data/: must reproduce every figure in approved_data_rules.md
§ Expected results on today's files."""

import hashlib
from decimal import Decimal

import pytest

from common import dq
from golden_helpers import FILES, ROOT, run

SHA = {"transactions": "2dcbe59e9ac497c441f3c019963b11e9848ce4916e5773d257a36f83d953ae95",
       "industry": "b4330fc6d7df60429849b3b176746f5389c65931f281308eb8224c8efd440ff5",
       "sm_spend": "41fbb6499f2b0ad4565ccc0e96ec490c72599e15fd46d64086fd98e3443c4c13"}

DEPARTMENTS = {  # rows_read, excluded, flagged, pct, rules_evaluated, rules_failing, rank
    "transactions": (66674, 0, 22, 100.0, 8, 0, 1),
    "sm_spend": (34, 0, 5, 100.0, 7, 0, 2),
    "industry": (1962, 1, 0, 99.95, 4, 1, 3),
}

NA = None
RULES = {
    "CDO-01": {"transactions": (66674, 0, 100.0, "pass"), "industry": (1962, 0, 100.0, "pass"), "sm_spend": (34, 0, 100.0, "pass")},
    "SQ-02": {"transactions": (66674, 0, 100.0, "pass"), "industry": (1962, 1, 99.95, "warn"), "sm_spend": (34, 0, 100.0, "pass")},
    "SQ-01": {"transactions": (66674, 0, 100.0, "pass"), "industry": (1961, 0, 100.0, "pass"), "sm_spend": (34, 0, 100.0, "pass")},
    "SQ-03": {"industry": (1961, 0, 100.0, "pass")},
    "SQ-04": {"industry": (1961, 0, 100.0, "pass")},
    "SQ-05": {"transactions": (66674, 0, 100.0, "pass")},
    "SQ-06": {"transactions": (66674, 0, 100.0, "pass")},
    "SQ-07a": {"transactions": (66674, 0, 100.0, "pass")},
    "SQ-07b": {"transactions": (66674, 0, 100.0, "pass")},
    "SQ-08": {"transactions": (66674, 0, 100.0, "pass")},
    "SQ-09a": {"sm_spend": (34, 0, 100.0, "pass")},
    "SQ-09b": {"sm_spend": (34, 0, 100.0, "pass")},
    "SQ-10": {"sm_spend": (34, 0, 100.0, "pass")},
    "SQ-12": {"industry": (1961, 0, 100.0, "pass")},
    "SQ-13": {"transactions": (34, 0, 100.0, "pass"), "sm_spend": (34, 0, 100.0, "pass")},
    "CDO-05": {"transactions": (66674, 0, 100.0, "pass"), "sm_spend": (34, 0, 100.0, "pass")},
    "CDO-06a": {}, "CDO-06b": {},
    "SB-04": {"transactions": (1961, 0, 100.0, "pass")},
    "SB-05": {"transactions": (66674, 0, 100.0, "pass")},
    "SB-06": {"transactions": (468, 0, 100.0, "pass")},
    "SB-07": {"transactions": (468, 0, 100.0, "pass")},
    "SB-08": {"transactions": (1961, 0, 100.0, "pass")},
    "SB-10": {"sm_spend": (34, 5, 85.29, "warn")},
    "SB-11": {"transactions": (66674, 22, 99.97, "warn")},
    "CDO-08": {"sm_spend": (34, 0, 100.0, "pass")},
    "CRO-05": {"transactions": (66674, 0, 100.0, "pass")},
    "CRO-07": {"transactions": (1961, 0, 100.0, "pass")},
}


@pytest.fixture(scope="module")
def golden():
    res, cfg = run()
    return res, cfg, dq.summarize(res, cfg, {"run_id": res["run_id"]}), dq.records_for(res, cfg)


def test_sha256_of_todays_files():
    for ds, (_, f) in FILES.items():
        assert hashlib.sha256((ROOT / "data" / f).read_bytes()).hexdigest() == SHA[ds]


def test_department_table(golden):
    _, _, s, _ = golden
    got = {d["dataset_id"]: (d["rows_read"], d["rows_excluded"], d["rows_flagged"], d["row_compliance_pct"],
                             d["rules_evaluated"], d["rules_failing"], d["rank"]) for d in s["datasets"]}
    assert got == DEPARTMENTS
    assert [d["dataset_id"] for d in s["datasets"]] == ["transactions", "sm_spend", "industry"]


def test_rule_table(golden):
    _, _, s, _ = golden
    assert {r["rule_id"] for r in s["rules"]} == set(RULES)
    for r in s["rules"]:
        for ds, v in r["results"].items():
            exp = RULES[r["rule_id"]].get(ds)
            if exp is None:
                assert v == {"evaluated": 0, "failed": 0, "compliance_pct": None, "status": "na"}, (r["rule_id"], ds)
            else:
                assert (v["evaluated"], v["failed"], v["compliance_pct"], v["status"]) == exp, (r["rule_id"], ds)


def test_all_16_run_controls_pass(golden):
    res, _, _, _ = golden
    assert not [c for c in res["controls"] if c["failed"]]
    assert {c["rule_id"] for c in res["controls"]} >= {"CDO-04", "CTO-06", "SB-01", "SB-02", "SB-03", "SB-09",
                                                       "CDO-07", "CRO-03", "CFO-03", "CFO-05", "CDO-11"}


def test_the_one_excluded_industry_record(golden):
    _, _, _, recs = golden
    assert recs[("SQ-02", "industry")] == [{
        "source_line": 1963, "key": {"ID": ""}, "values": {"ID": "", "Industria": ""},
        "failed_columns": ["ID", "Industria"], "reason": "EMPTY_RECORD: every source column is empty",
        "action": "exclude", "other_failed_rules": []}]


def test_the_five_flagged_sm_rows(golden):
    _, _, _, recs = golden
    got = recs[("SB-10", "sm_spend")]
    assert [r["source_line"] for r in got] == [24, 25, 27, 28, 32]
    assert [r["key"]["Month"] for r in got] == ["2023-11", "2023-12", "2024-02", "2024-03", "2024-07"]
    assert all(r["failed_columns"] == ["PayrollExpenses"] and r["reason"].startswith("NEGATIVE_SPEND:") for r in got)
    assert all("$" not in r["reason"] for r in got)  # no HR value in a reason
    total = sum(Decimal(r["values"]["PayrollExpenses"].replace("$", "")) * 100000000 for r in got)
    assert total == Decimal(-13500000)


SB11_PAIRS = [  # (customer, m, source_line of m, source_line of m+1): § Records, SB-11
    (12, "2022-11", 386, 387), (34, "2022-05", 1128, 1129), (78, "2022-05", 2624, 2625),
    (93, "2023-07", 3148, 3149), (191, "2022-05", 6466, 6467), (336, "2022-06", 11397, 11398),
    (336, "2023-02", 11405, 11406), (370, "2022-02", 12549, 12550), (437, "2024-01", 14850, 14851),
    (576, "2024-03", 19578, 19579), (651, "2023-02", 22115, 22116),
]


def test_the_22_sb11_flagged_transactions_records(golden):
    from common.dec import month_add

    _, _, _, recs = golden
    got = recs[("SB-11", "transactions")]
    want = []
    for c, m, l1, l2 in SB11_PAIRS:
        why = (f"UNEVEN_SPLIT: {m} and {month_add(m, 1)} sum to twice the amount of "
               f"{month_add(m, -1)} and {month_add(m, 2)}")
        want += [(l1, str(c), why), (l2, str(c), why)]
    assert [(r["source_line"], r["key"]["ID"], r["reason"]) for r in got] == sorted(want)
    assert all(r["failed_columns"] == ["amount"] and r["action"] == "flag" and r["other_failed_rules"] == []
               for r in got)
    assert got[0]["reason"] == "UNEVEN_SPLIT: 2022-11 and 2022-12 sum to twice the amount of 2022-10 and 2023-01"
    assert got[0]["values"] == {"ID": "12", "month": "11/30/2022", "amount": "7.154784"}
    assert got[1]["values"]["amount"] == "6.285216"
    assert sum(1 for v in recs.values() for r in v if r["action"] == "flag") == 27  # 5 SB-10 + 22 SB-11


def test_no_findings(golden):
    res, _, _, _ = golden
    assert res["findings"] == []


def test_business_figures(golden):
    res, _, _, _ = golden
    f, s = res["figures"], res["silver"]
    assert len(s["transactions"]) == 66674 and res["W"][0] == "2022-01" and len(res["W"]) == 34
    assert res["as_of_month"] == "2024-10" and res["churn_confirmed_through"] == "2024-08"
    assert sum(x["amount"] for x in s["transactions"]) == Decimal("221441.504508")
    assert sum(x["amount_value"] for x in s["transactions"]) == Decimal("2214415045.08")
    assert sum(1 for x in s["transactions"] if x["amount"] == 0) == 33703
    assert sum(1 for x in s["transactions"] if x["amount"] > 0) == 32971
    assert not res["holes"]
    mix = {}
    for x in s["industry"]:
        mix[x["industry_code"]] = mix.get(x["industry_code"], 0) + 1
    assert mix == {"RESTAURANTS": 529, "MANUFACTURING": 454, "RETAIL": 428, "TECHNOLOGY": 241,
                   "PROFESSIONAL_SERVICES": 165, "HEALTHCARE": 144}
    assert len(s["industry"]) == 1961
    assert len(s["sm_spend"]) == 238
    assert sum(x["spend"] for x in s["sm_spend"]) == Decimal("77.818")
    assert sum(x["spend_value"] for x in s["sm_spend"]) == Decimal("7781800000")
    neg = [x for x in s["sm_spend"] if x["spend"] < 0]
    assert len(neg) == 5 and {x["category"] for x in neg} == {"PayrollExpenses"}
    assert (f["cens_left"], f["cens_probable_left"], f["cens_none"], f.get("cens_unknown", 0)) == (377, 43, 1541, 0)
    pl = [c for c in s["customer"] if c["cohort_censoring"] == "probable_left"]
    assert sum(1 for c in pl if c["cohort_month"] == "2022-02") == 40
    assert sum(1 for c in pl if c["cohort_month"] == "2022-03") == 3
    assert f["new_logos"] == 1541
    assert sum(1 for c in s["customer"] if c["is_new_logo"] and c["cohort_month"] == "2022-02") == 68
    states = {k[6:]: v for k, v in f.items() if k.startswith("state_")}
    assert states == {"paying": 31366, "pre_acquisition": 29321, "churned": 3811, "new": 1541,
                      "settled_gap": 281, "paused": 231, "reactivated": 64, "grace": 59}
    assert (f["gaps"], f["gap_settled"], f["settled_arrears"], f["settled_prepay"], f["settled_split"]) == \
        (468, 211, 155, 47, 9)
    assert (f["gap_paused"], f["reactivations"], f["reactivated_customers"]) == (193, 64, 60)
    assert (f["open_churn"], f["grace_customers"], f["provisional"]) == (237, 46, 5399)
    assert res["portfolio_median"] == Decimal("5.25")
    assert res["outliers"] == [94, 322]
    mult = {c["customer_id"]: c["outlier_multiple"] for c in s["customer"] if c["is_outlier_customer"]}
    assert round(mult[94], 1) == Decimal("60.0") and round(mult[322], 1) == Decimal("31.7")
    assert (f["spike_19"], f["spike_3"]) == (116, 64)
    lo, hi = res["sm_ratio_range"]
    assert round(lo, 2) == Decimal("1.61") and round(hi, 2) == Decimal("7.62")
    assert not any(m["is_unit_tripwire"] for m in s["month_control"])
    per = {}
    for x in s["customer_month"]:
        a = per.setdefault(x["customer_id"], [Decimal(0), Decimal(0)])
        a[0] += x["amount"]
        a[1] += x["amount_normalized"]
    assert len(per) == 1961 and all(a == b for a, b in per.values())
    # SB-11 (uneven splits) and the CRO-05 movement totals it changes
    cm = s["customer_month"]
    us = [x for x in cm if x["settlement_type"] == "uneven_split"]
    assert (f["uneven_split_pairs"], f["uneven_split_customers"], len(us)) == (11, 10, 22)
    assert all(x["settlement_confidence"] == "high" and x["lifecycle_state"] == "paying" for x in us)
    firsts = [x for x in us if x["month"] == x["uneven_split_start_month"]]
    assert sum(1 for x in firsts if x["amount"] > x["amount_normalized"]) == 7
    assert sum(1 for x in firsts if x["amount"] < x["amount_normalized"]) == 4
    exp = sum(x["expansion_amount"] or 0 for x in cm)
    con = sum(x["contraction_amount"] or 0 for x in cm)
    assert (exp, con, exp - con) == (Decimal("3499.903452"), Decimal("4656.537782"), Decimal("-1156.634330"))
    assert sum(1 for x in cm if (x["expansion_amount"] or 0) > 0) == 1212
    assert sum(1 for x in cm if (x["contraction_amount"] or 0) > 0) == 954
    pair_months = {(x["customer_id"], x["month"]): x["amount_normalized"] for x in us}
    from common.dec import month_add
    lag_b = [x for x in cm if (x["customer_id"], month_add(x["month"], -12)) in pair_months]
    assert len(lag_b) == 18 and all(
        x["amount_lag12"] == pair_months[(x["customer_id"], month_add(x["month"], -12))] for x in lag_b)


def test_reconciliation_bronze_equals_silver_plus_excluded(golden):
    res, _, _, _ = golden
    for ds, n in (("transactions", 66674), ("industry", 1962), ("sm_spend", 34)):
        assert len(res["rows"][ds]) == n == len(res["included"][ds]) + sum(r.excluded for r in res["rows"][ds])
