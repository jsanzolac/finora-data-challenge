"""One failing fixture per active row or finding rule, plus the hole fixtures.

Each asserts the row is excluded or flagged and stored (DQ records and the DQ
store), that the file still loads (the other rows reach silver) and that every
run control still passes: no file content can fail a run."""

from pathlib import Path

import pytest

from common import dq
from golden_helpers import run

D = Path(__file__).resolve().parent / "fixtures" / "dirty"


def load(tx="clean_transactions.csv", ind="clean_industry.csv", sm="clean_sm_spend.csv", previous=None):
    data = {"transactions": (D / tx).read_bytes(), "industry": (D / ind).read_bytes(),
            "sm_spend": (D / sm).read_bytes()}
    res, cfg = run(data, previous=previous)
    assert not [c for c in res["controls"] if c["failed"]], res["controls"]
    recs = dq.records_for(res, cfg)
    store = dq.dq_store_rows(res, cfg, recs)
    return res, cfg, recs, store


def excluded_lines(store, ds):
    return sorted(r["source_line"] for r in store["excluded"][ds][False])


def test_clean_fixtures_have_no_failures():
    res, _, recs, store = load()
    assert all(not v for v in recs.values())
    assert len(res["silver"]["transactions"]) == 18 and len(res["silver"]["sm_spend"]) == 42


@pytest.mark.parametrize("fixture,rule,line,code", [
    ("tx_bad_month.csv", "SQ-06", 2, "BAD_MONTH"),
    ("tx_not_month_end.csv", "SQ-06", 6, "BAD_MONTH"),
    ("tx_non_numeric.csv", "SQ-07a", 3, "BAD_AMOUNT"),
    ("tx_seventh_decimal.csv", "CDO-05", 4, "PRECISION"),
    ("tx_bad_id.csv", "SQ-05", 8, "BAD_ID"),
    ("tx_wrong_field_count.csv", "SQ-01", 5, "FIELD_COUNT"),
    ("tx_undecodable.csv", "CDO-01", 6, "UNDECODABLE_LINE"),
    ("tx_control_char.csv", "CDO-01", 6, "CONTROL_CHAR"),
])
def test_transactions_row_is_excluded_stored_and_file_loads(fixture, rule, line, code):
    res, cfg, recs, store = load(tx=fixture)
    hit = [r for r in recs[(rule, "transactions")] if r["source_line"] == line]
    assert len(hit) == 1 and hit[0]["reason"].startswith(code + ":") and hit[0]["action"] == "exclude"
    assert line in excluded_lines(store, "transactions")
    assert len(res["silver"]["transactions"]) == 17  # the other 17 rows load
    s = dq.summarize(res, cfg, {})
    t = next(d for d in s["datasets"] if d["dataset_id"] == "transactions")
    assert t["rows_excluded"] == 1 and t["row_compliance_pct"] == 94.44
    rr = next(r for r in s["rules"] if r["rule_id"] == rule)["results"]["transactions"]
    assert rr["failed"] == 1 and rr["status"] == "fail"


def test_stage_a_failure_has_positional_values_and_all_columns_failed():
    _, _, recs, _ = load(tx="tx_wrong_field_count.csv")
    r = recs[("SQ-01", "transactions")][0]
    assert r["values"] == {"ID": "1", "month": "4/30/2022", "amount": "5,extra"}
    assert r["failed_columns"] == ["ID", "month", "amount"]
    _, _, recs, _ = load(tx="tx_undecodable.csv")
    assert recs[("CDO-01", "transactions")][0]["values"]["amount"] == "5�"


def test_duplicate_key_excludes_every_copy():
    res, _, recs, store = load(tx="tx_duplicate_key.csv")
    hits = recs[("SQ-05", "transactions")]
    assert sorted(r["source_line"] for r in hits) == [7, 20]
    assert all(r["reason"].startswith("DUPLICATE_KEY:") for r in hits)
    assert len(res["silver"]["transactions"]) == 17
    # the customer-month is now a hole with reason excluded, not a missing-row finding
    assert res["holes"] == {(1, "2022-06"): "excluded"}
    assert recs[("SQ-08", "transactions")] == []


def test_missing_customer_month_is_a_finding():
    res, cfg, recs, store = load(tx="tx_missing_month.csv")
    f = recs[("SQ-08", "transactions")]
    assert f == [{"source_line": None, "key": {"ID": "1", "month": "2022-04"}, "values": {}, "failed_columns": [],
                  "reason": "MISSING_CUSTOMER_MONTH: no source row carries this customer-month",
                  "action": "finding", "other_failed_rules": []}]
    assert any(x["action"] == "finding" for x in store["findings"][False])
    s = dq.summarize(res, cfg, {})
    rr = next(r for r in s["rules"] if r["rule_id"] == "SQ-08")["results"]["transactions"]
    assert (rr["evaluated"], rr["failed"]) == (18, 1)
    t = next(d for d in s["datasets"] if d["dataset_id"] == "transactions")
    assert t["row_compliance_pct"] == 100.0  # findings never change row compliance


def test_negative_amount_is_flagged_and_stays_in_silver():
    res, _, recs, _ = load(tx="tx_negative_amount.csv")
    assert [r["source_line"] for r in recs[("SQ-07b", "transactions")]] == [7]
    assert len(res["silver"]["transactions"]) == 18
    assert any(x["is_negative_amount"] for x in res["silver"]["transactions"])


def test_industry_empty_record():
    res, _, recs, store = load(ind="ind_empty_record.csv")
    assert [r["source_line"] for r in recs[("SQ-02", "industry")]] == [5]
    assert len(res["silver"]["industry"]) == 3 and excluded_lines(store, "industry") == [5]


def test_unmapped_industry_is_flagged():
    res, _, recs, _ = load(ind="ind_unmapped.csv")
    assert [r["source_line"] for r in recs[("SQ-04", "industry")]] == [3]
    c2 = next(c for c in res["silver"]["customer"] if c["customer_id"] == 2)
    assert c2["industry_code"] == "UNMAPPED" and c2["is_industry_unmapped"]


def test_bad_industry_id_excludes_and_raises_no_industry_row_finding():
    res, _, recs, _ = load(ind="ind_bad_id.csv")
    assert [r["source_line"] for r in recs[("SQ-03", "industry")]] == [3]
    assert [f["key"] for f in recs[("SQ-12", "industry")]] == [{"ID": "2"}]
    c2 = next(c for c in res["silver"]["customer"] if c["customer_id"] == 2)
    assert c2["industry_code"] == "UNKNOWN" and c2["is_industry_unknown"]
    assert len(res["silver"]["transactions"]) == 18  # revenue is never dropped


def test_duplicate_industry_excludes_all_copies():
    res, _, recs, _ = load(ind="ind_duplicate.csv")
    assert sorted(r["source_line"] for r in recs[("SQ-03", "industry")]) == [2, 5]
    assert len(res["silver"]["industry"]) == 2


def test_bad_spend_cell_excludes_the_whole_month_line():
    res, _, recs, store = load(sm="sm_bad_cell.csv")
    r = recs[("SQ-10", "sm_spend")]
    assert [x["source_line"] for x in r] == [4] and r[0]["failed_columns"] == ["PayrollExpenses"]
    assert "$" not in r[0]["reason"]
    assert len(res["silver"]["sm_spend"]) == 35  # 5 lines x 7; never zero-filled
    assert [f["key"] for f in recs[("SQ-13", "sm_spend")]] == [{"Month": "2022-03"}]
    assert recs[("SQ-09b", "sm_spend")] == []  # an excluded line still carries its month
    general = store["excluded"]["sm_spend"][False][0]
    assert '"PayrollExpenses": "__restricted__"' in general["values_json"]
    assert store["excluded"]["sm_spend"][True]  # HR values only in the hr_sensitive partition
    mc = next(m for m in res["silver"]["month_control"] if m["month"] == "2022-03")
    assert mc["sm_total"] is None and mc["sm_to_revenue_ratio"] is None and mc["is_unit_tripwire"] is None


def test_bad_sm_month():
    res, _, recs, _ = load(sm="sm_bad_month.csv")
    assert [x["source_line"] for x in recs[("SQ-09a", "sm_spend")]] == [7]


def test_sm_month_gap_is_a_finding():
    res, _, recs, _ = load(sm="sm_month_gap.csv")
    assert [f["key"] for f in recs[("SQ-09b", "sm_spend")]] == [{"Month": "2022-03"}]


def test_negative_spend_in_other_category():
    res, _, recs, _ = load(sm="sm_negative_other.csv")
    r = recs[("SB-10", "sm_spend")]
    assert [x["source_line"] for x in r] == [3] and r[0]["reason"].startswith("NEGATIVE_SPEND_OTHER_CATEGORY:")


# ---- holes ----------------------------------------------------------------------

def states(res, cid):
    return [x["lifecycle_state"] for x in res["silver"]["customer_month"] if x["customer_id"] == cid]


def test_hole_bad_amount_inside_a_gap():
    res, _, recs, _ = load(tx="tx_hole_bad_amount_in_gap.csv")
    # H5: the stretch right after the first payment is broken, so the cohort is unknown and
    # the first payment is `paying`, never `new` (H4/H5).
    assert states(res, 2) == ["pre_acquisition", "paying", "unknown", "unknown", "paying", "paying"]
    assert [f["key"] for f in recs[("CRO-07", "transactions")]] == [{"ID": "2"}]
    assert [r["source_line"] for r in recs[("SB-07", "transactions")]] == [12]
    assert {r["source_line"] for r in recs[("SB-05", "transactions")]} == {10}
    hole = next(x for x in res["silver"]["customer_month"] if x["customer_id"] == 2 and x["month"] == "2022-04")
    assert hole["is_hole"] and hole["hole_reason"] == "excluded" and hole["amount"] is None and hole["is_paying"] is None
    assert [f["key"] for f in recs[("SB-08", "transactions")]] == [{"ID": "2"}]


def test_hole_before_the_first_paid_month():
    res, _, recs, _ = load(tx="tx_hole_before_first_paid.csv")
    c2 = next(c for c in res["silver"]["customer"] if c["customer_id"] == 2)
    assert c2["cohort_censoring"] == "unknown" and not c2["is_new_logo"]
    assert [f["key"] for f in recs[("SB-04", "transactions")]] == [{"ID": "2"}]
    assert states(res, 2)[:2] == ["unknown", "paying"]


def test_hole_in_month_p_minus_1():
    res, _, recs, _ = load(tx="tx_hole_p_minus_1.csv")
    assert [f["key"] for f in recs[("SB-06", "transactions")]] == [{"ID": "4", "month": "2022-04"}]
    gap = next(g for g in res["silver"]["gap"] if g["customer_id"] == 4)
    assert gap["settlement_hole_affected"] and not gap["test_prepay"] and not gap["test_split"]
    assert [f["key"] for f in recs[("SQ-12", "industry")]] == [{"ID": "4"}]


def test_hole_in_the_last_month():
    res, _, recs, _ = load(tx="tx_hole_last_month.csv")
    assert states(res, 3)[-1] == "unknown"
    mc = next(m for m in res["silver"]["month_control"] if m["month"] == "2022-06")
    assert mc["hole_count"] == 1 and mc["revenue_is_complete"] is False


def test_cdo06_removed_keys_and_restated_values_against_the_previous_run():
    first, _, _, _ = load()
    prev = {"run_id": "r20261101T000000Z", "keys": first["keys"]}
    res, cfg, recs, _ = load(tx="tx_missing_month.csv", ind="ind_unmapped.csv", previous=prev)
    assert [f["key"] for f in recs[("CDO-06a", "transactions")]] == [{"ID": "1", "month": "2022-04"}]
    assert [r["source_line"] for r in recs[("CDO-06b", "industry")]] == [3]
    assert res["silver"]["restatement_log"][0]["column_name"] == "Industria"
    s = dq.summarize(res, cfg, {})
    rr = next(r for r in s["rules"] if r["rule_id"] == "CDO-06a")["results"]["transactions"]
    assert (rr["evaluated"], rr["failed"], rr["status"]) == (18, 1, "fail")


def test_empty_and_missing_files_still_load():
    res, cfg = run({"transactions": b"", "industry": b"\xef\xbb\xbfID,Industria", "sm_spend": b""})
    assert not [c for c in res["controls"] if c["failed"]]
    s = dq.summarize(res, cfg, {})
    assert all(d["rows_read"] == 0 and d["row_compliance_pct"] is None for d in s["datasets"])
