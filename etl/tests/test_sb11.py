"""SB-11 "Uneven split of a two-month total" (approved_data_rules.md, SB-11;
docs/etl_discussion/round3/cdo_uneven_split.md § 11).

- lifecycle() unit cases with exact Decimal inputs,
- the CDO's fixtures F1-F18 through the full build (tx_uneven_split.csv:
  customer 100 + N is case FN, W = 2022-01 -> 2023-06),
- the CDO's invariants on the fixture and on the golden files,
- the golden run with and without SB-11: only the named customer_month cells,
  the SB-11 rule result and transactions.rows_flagged may differ.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

from common import config, dq, dqdl
from common.dec import month_add, month_range
from golden_helpers import run
from silver_build import engine

D = Path(__file__).resolve().parent / "fixtures" / "dirty"
FIXTURE_W = month_range("2022-01", "2023-06")
TAGGED = {  # customer -> pair start months (fixture)
    101: ["2022-03"], 102: ["2022-02"], 106: ["2022-03"], 110: ["2022-02", "2022-05"],
    115: ["2022-02"], 116: ["2022-02"], 117: ["2022-02"], 118: ["2022-02"],
}
GOLDEN_PAIRS = [  # (customer, m, source_line of m, source_line of m+1): approved_data_rules.md § Records
    (12, "2022-11", 386, 387), (34, "2022-05", 1128, 1129), (78, "2022-05", 2624, 2625),
    (93, "2023-07", 3148, 3149), (191, "2022-05", 6466, 6467), (336, "2022-06", 11397, 11398),
    (336, "2023-02", 11405, 11406), (370, "2022-02", 12549, 12550), (437, "2024-01", 14850, 14851),
    (576, "2024-03", 19578, 19579), (651, "2023-02", 22115, 22116),
]
CM_CHANGED = ("settlement_type", "settlement_confidence", "amount_normalized", "uneven_split_start_month",
              "expansion_amount", "contraction_amount", "amount_lag12")


def params(cfg: dict) -> dict:
    r = cfg["rules_by_id"]
    bp = {**r["SB-06"]["params"], **r["SB-05"]["params"], **r["SB-04"]["params"], **r["CRO-07"]["params"]}
    bp["censoring_multiples"] = r["SB-04"]["params"]["censoring_multiples"]
    return bp


def life(amounts: list[str | None]) -> dict:
    cells = [Decimal(a) if a is not None else None for a in amounts]
    return engine.lifecycle(cells, month_range("2022-01", month_add("2022-01", len(cells) - 1)), params(config.load()))


def no_sb11(cells, W, paid, state, stype, sconf, norm):
    return [None] * len(W), []


def reason(m: str) -> str:
    return (f"UNEVEN_SPLIT: {m} and {month_add(m, 1)} sum to twice the amount of "
            f"{month_add(m, -1)} and {month_add(m, 2)}")


def fixture_data() -> dict:
    return {"transactions": (D / "tx_uneven_split.csv").read_bytes(),
            "industry": (D / "clean_industry.csv").read_bytes(),
            "sm_spend": (D / "clean_sm_spend.csv").read_bytes()}


def by_customer(rows: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = defaultdict(list)
    for x in rows:
        out[x["customer_id"]].append(x)
    for v in out.values():
        v.sort(key=lambda x: x["month"])
    return out


def line(cid: int, i: int) -> int:
    return 2 + (cid - 101) * 18 + i  # fixture layout: 18 rows per customer, header is line 1


@pytest.fixture(scope="module")
def fx():
    res, cfg = run(fixture_data())
    assert not [c for c in res["controls"] if c["failed"]], res["controls"]
    recs = dq.records_for(res, cfg)
    return res, cfg, recs, by_customer(res["silver"]["customer_month"])


@pytest.fixture(scope="module")
def golden_pair():
    with_sb11, cfg = run()
    mp = pytest.MonkeyPatch()
    mp.setattr(engine, "_uneven_splits", no_sb11)
    try:
        without, _ = run()
    finally:
        mp.undo()
    return with_sb11, without, cfg


# --------------------------------------------------------------------------- #
# Config and placement                                                        #
# --------------------------------------------------------------------------- #

def test_config_catalog_entry_matches_the_implementation():
    cfg = config.load()
    r = cfg["rules_by_id"]["SB-11"]
    assert len(cfg["rule_catalog"]) == 44
    assert (r["layer"], r["kind"], r["action"], r["applies_to"], r["inferred"], r["counts_toward_compliance"]) == \
        ("silver_business", "row", "flag", ["transactions"], True, False)
    assert r["params"] == {"window_months": 4, "pair_months": 2, "sum_test": "exact",
                           "settlement_type": "uneven_split", "settlement_confidence": "high",
                           "pair_column": "uneven_split_start_month", "reason_codes": ["UNEVEN_SPLIT"]}
    assert r["title"] == "Uneven split of a two-month total" and r["description"].startswith("Two consecutive")
    assert "Each month of an uneven split (SB-11) equals its baseline b." in cfg["rules_by_id"]["CRO-03"]["description"]
    ids = [x["id"] for x in dq.dashboard_rules(cfg)]
    assert ids.index("SB-10") + 1 == ids.index("SB-11") == ids.index("CDO-08") - 1


def test_sb11_is_a_spark_business_rule_not_a_dqdl_rule():
    cfg = config.load()
    assert all(c.rule_id != "SB-11" for cs in dqdl.checks(cfg).values() for c in cs)
    assert all("SB-11" not in dqdl.ruleset(cfg, ds) for ds in cfg["dataset_order"])


# --------------------------------------------------------------------------- #
# lifecycle() unit cases                                                       #
# --------------------------------------------------------------------------- #

def test_unit_customer_12_pattern():
    L = life(["6.72", "6.72", "7.154784", "6.285216", "6.72", "6.72"])
    assert L["pairs"] == [2]
    assert L["stype"] == [None, None, "uneven_split", "uneven_split", None, None]
    assert L["sconf"] == [None, None, "high", "high", None, None]
    assert L["us_start"] == [None, None, "2022-03", "2022-03", None, None]
    assert L["norm"][2] == L["norm"][3] == Decimal("6.72")
    assert [L["exp"][i] for i in (2, 3, 4)] == [Decimal(0)] * 3 and [L["con"][i] for i in (2, 3, 4)] == [Decimal(0)] * 3
    assert L["state"][1:5] == ["paying"] * 4 and not any(L["catch"]) and not any(L["prepaid"])


def test_unit_sum_off_by_one_millionth_is_not_tagged():
    assert life(["6.72", "7.154784", "6.285217", "6.72"])["pairs"] == []


def test_unit_unquantized_decimals_compare_by_value():
    L = life(["6.72", "7.154784", "6.285216", "6.720000"])  # F17 without the parser's quantize
    assert L["pairs"] == [1] and L["norm"][1] == L["norm"][2] == Decimal("6.72")


def test_unit_window_shorter_than_four_months_and_a_pair_at_the_edge():
    assert life(["6.72", "7.154784", "6.285216"])["pairs"] == []
    assert life(["6.72", "6.72", "7.154784", "6.285216"])["pairs"] == []  # m+2 not delivered yet


def test_unit_retroactive_tagging_once_m_plus_2_is_delivered():
    before = life(["6.72", "6.72", "7.154784", "6.285216"])
    after = life(["6.72", "6.72", "7.154784", "6.285216", "6.72"])
    assert before["pairs"] == [] and after["pairs"] == [2]


def test_unit_settlement_baseline_blocks_and_tagged_months_are_never_baselines():
    # F9: month 2 is the catch-up month q of an arrears gap; window 2..5 matches (3)-(5) otherwise.
    L = life(["6", "0", "12", "14", "10", "12"])
    assert L["stype"][:3] == [None, "arrears", "arrears"] and L["pairs"] == []
    x = [Decimal(v) for v in ("12", "14", "10", "12")]
    assert x[3] == x[0] and x[1] != x[0] and x[1] + x[2] == 2 * x[0]


# --------------------------------------------------------------------------- #
# F1-F18 through the full build (tx_uneven_split.csv)                          #
# --------------------------------------------------------------------------- #

def test_exactly_the_expected_months_are_tagged(fx):
    res, _, _, cm = fx
    got = {c: sorted({x["uneven_split_start_month"] for x in rows if x["uneven_split_start_month"]})
           for c, rows in cm.items()}
    assert {c: v for c, v in got.items() if v} == TAGGED
    for c, rows in cm.items():
        starts = set(TAGGED.get(c, []))
        months = starts | {month_add(m, 1) for m in starts}
        for x in rows:
            tagged = x["month"] in months
            assert (x["settlement_type"] == "uneven_split") == tagged, (c, x["month"])
            assert (x["uneven_split_start_month"] is not None) == tagged, (c, x["month"])
    assert res["figures"]["uneven_split_pairs"] == 9 and res["figures"]["uneven_split_customers"] == 8


def test_f1_customer_12_pattern(fx):
    _, _, recs, cm = fx
    rows = cm[101]
    for i in (2, 3):
        x = rows[i]
        assert (x["settlement_type"], x["settlement_confidence"], x["uneven_split_start_month"]) == \
            ("uneven_split", "high", "2022-03")
        assert x["amount_normalized"] == Decimal("6.72") and x["lifecycle_state"] == "paying"
        assert not x["is_catch_up"] and not x["is_prepaid"]
    assert rows[2]["amount"] == Decimal("7.154784") and rows[3]["amount"] == Decimal("6.285216")  # never restated
    for i in (2, 3, 4):
        assert rows[i]["expansion_amount"] == 0 and rows[i]["contraction_amount"] == 0
    got = [r for r in recs[("SB-11", "transactions")] if r["key"]["ID"] == "101"]
    assert [r["source_line"] for r in got] == [line(101, 2), line(101, 3)]
    assert all(r["reason"] == reason("2022-03") == "UNEVEN_SPLIT: 2022-03 and 2022-04 sum to twice the amount "
               "of 2022-02 and 2022-05" for r in got)
    assert all(r["failed_columns"] == ["amount"] and r["action"] == "flag" and r["other_failed_rules"] == []
               for r in got)
    assert [r["values"]["amount"] for r in got] == ["7.154784", "6.285216"]


def test_f2_first_month_below_b(fx):
    rows = fx[3][102]
    assert [rows[i]["amount_normalized"] for i in (1, 2)] == [Decimal("9.45")] * 2
    assert rows[1]["amount"] < Decimal("9.45") < rows[2]["amount"]


@pytest.mark.parametrize("cid", [103, 104, 105, 111, 112, 113, 114])
def test_f3_f4_f5_f11_f12_f13_f14_are_not_tagged(fx, cid):
    _, _, recs, cm = fx
    assert all(x["settlement_type"] != "uneven_split" and x["uneven_split_start_month"] is None for x in cm[cid])
    assert not [r for r in recs[("SB-11", "transactions")] if r["key"]["ID"] == str(cid)]


def test_f5_m_plus_2_unpaid_and_pair_in_the_last_two_months(fx):
    rows = fx[3][105]
    assert rows[3]["amount"] == 0 and rows[3]["lifecycle_state"] == "paused"
    assert rows[16]["amount"] + rows[17]["amount"] == 2 * rows[15]["amount"]  # would pair, m+2 not delivered


def test_f6_m_minus_1_is_the_first_paid_month(fx):
    res, _, _, cm = fx
    rows = cm[106]
    assert rows[1]["lifecycle_state"] == "new" and [rows[i]["lifecycle_state"] for i in (2, 3, 4)] == ["paying"] * 3
    assert [rows[i]["settlement_type"] for i in (2, 3)] == ["uneven_split"] * 2
    for i in (2, 3, 4):
        assert rows[i]["expansion_amount"] == 0 and rows[i]["contraction_amount"] == 0
    c = next(x for x in res["silver"]["customer"] if x["customer_id"] == 106)
    assert c["cohort_month"] == "2022-02" and c["is_new_logo"] and c["first_paid_amount"] == Decimal("6.72")


def test_f7_hole_at_m_plus_2(fx):
    _, _, recs, cm = fx
    rows = cm[107]
    assert rows[3]["is_hole"] and rows[3]["hole_reason"] == "excluded"
    assert all(x["uneven_split_start_month"] is None for x in rows)
    assert not [r for r in recs[("SB-11", "transactions")] if r["key"]["ID"] == "107"]
    mv = [r["source_line"] for r in recs[("CRO-05", "transactions")] if r["key"]["ID"] == "107"]
    assert mv == [line(107, 4), line(107, 15)]  # t-1 and t-12 are the hole, as today
    assert rows[4]["expansion_amount"] is None and rows[4]["contraction_amount"] is None


def test_f8_hole_at_m_minus_1(fx):
    rows = fx[3][108]
    assert rows[1]["is_hole"] and all(x["uneven_split_start_month"] is None for x in rows)


def test_f9_baseline_is_an_arrears_catch_up_month(fx):
    rows = fx[3][109]
    assert [x["settlement_type"] for x in rows[:3]] == [None, "arrears", "arrears"] and rows[2]["is_catch_up"]
    assert all(x["settlement_type"] != "uneven_split" for x in rows)


def test_f10_two_pairs_share_an_untagged_baseline(fx):
    rows = fx[3][110]
    assert [x["uneven_split_start_month"] for x in rows[:7]] == \
        [None, "2022-02", "2022-02", None, "2022-05", "2022-05", None]
    assert rows[3]["settlement_type"] is None and rows[3]["amount_normalized"] == rows[3]["amount"]


def test_f14_negative_amount_keeps_its_flag(fx):
    _, _, recs, _ = fx
    assert [r["source_line"] for r in recs[("SQ-07b", "transactions")]] == [line(114, 2)]


def test_f15_left_censored_customer(fx):
    res, _, _, cm = fx
    assert [x["uneven_split_start_month"] for x in cm[115][:4]] == [None, "2022-02", "2022-02", None]
    c = next(x for x in res["silver"]["customer"] if x["customer_id"] == 115)
    assert c["cohort_censoring"] == "left" and c["cohort_month"] == "2022-01" and not c["is_new_logo"]


def test_f16_lag12_reads_b(fx):
    rows = fx[3][116]
    assert rows[1]["amount"] != Decimal("5.25") and rows[2]["amount"] != Decimal("5.25")
    assert rows[13]["amount_lag12"] == rows[14]["amount_lag12"] == Decimal("5.25")


def test_f17_6_72_equals_6_720000(fx):
    res, _, recs, cm = fx
    assert [x["uneven_split_start_month"] for x in cm[117][:4]] == [None, "2022-02", "2022-02", None]
    raw = {x["month"]: x["amount_raw"] for x in res["silver"]["transactions"] if x["customer_id"] == 117}
    assert raw["2022-01"] == "6.72" and raw["2022-04"] == "6.720000"
    assert {r["reason"] for r in recs[("SB-11", "transactions")] if r["key"]["ID"] == "117"} == {reason("2022-02")}


def test_f18_outlier_with_a_pair(fx):
    res, _, _, cm = fx
    assert [x["settlement_type"] for x in cm[118][1:3]] == ["uneven_split"] * 2
    c = next(x for x in res["silver"]["customer"] if x["customer_id"] == 118)
    assert c["is_outlier_customer"] and c["outlier_source"] == "rule" and c["median_paid_amount"] == Decimal("400")
    assert 118 in res["outliers"]


def test_fixture_dq_result_is_a_flag_that_never_fails(fx):
    res, cfg, recs, _ = fx
    s = dq.summarize(res, cfg, {})
    r = next(x for x in s["rules"] if x["rule_id"] == "SB-11")
    included = len(res["included"]["transactions"])
    assert included == 322  # 324 lines, 2 bad amounts (F7, F8) excluded
    assert r["results"]["transactions"] == {"evaluated": 322, "failed": 18, "compliance_pct": 94.41, "status": "warn"}
    assert r["results"]["industry"]["status"] == r["results"]["sm_spend"]["status"] == "na"
    assert len(recs[("SB-11", "transactions")]) == 18


def test_fixture_with_and_without_sb11_only_customer_month_moves(fx):
    res, _, _, _ = fx
    mp = pytest.MonkeyPatch()
    mp.setattr(engine, "_uneven_splits", no_sb11)
    try:
        base, _ = run(fixture_data())
    finally:
        mp.undo()
    for t in res["silver"]:
        if t != "customer_month":
            assert res["silver"][t] == base["silver"][t], t
    for a, b in zip(res["silver"]["customer_month"], base["silver"]["customer_month"]):
        assert {k for k in a if a[k] != b.get(k)} <= set(CM_CHANGED)


# --------------------------------------------------------------------------- #
# Invariants (CDO § 11) on the fixture and on the golden files                 #
# --------------------------------------------------------------------------- #

def check_invariants(res: dict) -> None:
    cm = res["silver"]["customer_month"]
    per = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for x in cm:
        if x["amount"] is not None:
            per[x["customer_id"]][0] += x["amount"]
            per[x["customer_id"]][1] += x["amount_normalized"]
    assert all(a == b for a, b in per.values())  # CRO-03 identity per customer
    tagged = [x for x in cm if x["settlement_type"] == "uneven_split"]
    assert all(x["lifecycle_state"] == "paying" and x["settlement_confidence"] == "high" for x in tagged)
    assert all(x["uneven_split_start_month"] is None for x in cm if x["settlement_type"] != "uneven_split")
    pairs = defaultdict(list)
    for x in tagged:
        pairs[(x["customer_id"], x["uneven_split_start_month"])].append(x)
    for (c, m), rows in pairs.items():
        assert sorted(x["month"] for x in rows) == [m, month_add(m, 1)], (c, m)
        assert rows[0]["amount_normalized"] == rows[1]["amount_normalized"]
        assert rows[0]["amount"] + rows[1]["amount"] == 2 * rows[0]["amount_normalized"]
    flagged = [h for r in res["included"]["transactions"] for h in r.hits if h.rule_id == "SB-11"]
    assert len(flagged) == len(tagged)
    cnt = res["counter"]
    assert cnt.ev[("SB-11", "transactions")] == len(res["included"]["transactions"])
    assert cnt.fail[("SB-11", "transactions")] == len(tagged)


def test_invariants_on_the_fixture(fx):
    check_invariants(fx[0])


def test_invariants_and_effect_on_the_golden_files(golden_pair):
    res, base, cfg = golden_pair
    check_invariants(res)
    cm, cm0 = res["silver"]["customer_month"], base["silver"]["customer_month"]
    tagged = sorted((x["customer_id"], x["uneven_split_start_month"]) for x in cm if x["uneven_split_start_month"])
    assert sorted(set(tagged)) == [(c, m) for c, m, _, _ in sorted(GOLDEN_PAIRS)] and len(tagged) == 22
    # Σ amount per month and every other silver table are unchanged
    per_month = lambda rows: {m: sum(x["amount"] or 0 for x in rows if x["month"] == m) for m in res["W"]}  # noqa: E731
    assert per_month(cm) == per_month(cm0)
    for t in res["silver"]:
        if t != "customer_month":
            assert res["silver"][t] == base["silver"][t], t
    # customer_month: only the named cells move, by the named counts
    diff = defaultdict(int)
    for a, b in zip(cm, cm0):
        assert (a["customer_id"], a["month"]) == (b["customer_id"], b["month"])
        for k in a:
            if a[k] != b.get(k):
                diff[k] += 1
    assert dict(diff) == {"settlement_type": 22, "settlement_confidence": 22, "amount_normalized": 22,
                          "uneven_split_start_month": 22, "expansion_amount": 18, "contraction_amount": 15,
                          "amount_lag12": 18}
    tot = lambda rows, k: sum(x[k] or 0 for x in rows)  # noqa: E731
    pos = lambda rows, k: sum(1 for x in rows if (x[k] or 0) > 0)  # noqa: E731
    assert (tot(cm0, "expansion_amount"), tot(cm0, "contraction_amount")) == \
        (Decimal("3582.386454"), Decimal("4739.020784"))
    assert (tot(cm, "expansion_amount"), tot(cm, "contraction_amount")) == \
        (Decimal("3499.903452"), Decimal("4656.537782"))
    assert (pos(cm0, "expansion_amount"), pos(cm0, "contraction_amount")) == (1230, 969)
    assert (pos(cm, "expansion_amount"), pos(cm, "contraction_amount")) == (1212, 954)
    assert tot(cm, "expansion_amount") - tot(cm, "contraction_amount") == \
        tot(cm0, "expansion_amount") - tot(cm0, "contraction_amount") == Decimal("-1156.634330")
    # DQ: only the SB-11 result and transactions.rows_flagged differ
    s, s0 = dq.summarize(res, cfg, {}), dq.summarize(base, cfg, {})
    for a, b in zip(s["rules"], s0["rules"]):
        if a["rule_id"] == "SB-11":
            assert a["results"]["transactions"]["failed"] == 22 and b["results"]["transactions"]["failed"] == 0
        else:
            assert a == b, a["rule_id"]
    for a, b in zip(s["datasets"], s0["datasets"]):
        assert {k for k in a if a[k] != b[k]} == ({"rows_flagged"} if a["dataset_id"] == "transactions" else set())
    assert {k: v for k, v in res["figures"].items() if not k.startswith("uneven_split_")} == \
        {k: v for k, v in base["figures"].items() if not k.startswith("uneven_split_")}
