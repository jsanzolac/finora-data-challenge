"""The Glue Spark path (DQDL row outcomes + applyInPandas lifecycle + Iceberg)
gives exactly the reference engine's results: the golden run and every dirty
and hole fixture. Runs on local PySpark 3.5 (skipped when it is not installed)."""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("pyspark")

from common import config, dq  # noqa: E402
from golden_helpers import golden_inputs, inputs_from  # noqa: E402
from silver_build.engine import build  # noqa: E402
from spark_support import spark_session  # noqa: E402

D = Path(__file__).resolve().parent / "fixtures" / "dirty"
CLEAN = {"transactions": "clean_transactions.csv", "industry": "clean_industry.csv", "sm_spend": "clean_sm_spend.csv"}
DIRTY = sorted(p.name for p in D.glob("*.csv") if not p.name.startswith("clean_"))
PREFIX = {"tx": "transactions", "ind": "industry", "sm": "sm_spend"}


@pytest.fixture(scope="module")
def spark():
    s, _ = spark_session(Path(tempfile.mkdtemp(prefix="finora-iceberg-")))
    yield s


def outputs(res, cfg):
    recs = dq.records_for(res, cfg)
    return {"summary": dq.summarize(res, cfg, {"run_id": res["run_id"]}), "records": recs,
            "store": dq.dq_store_rows(res, cfg, recs), "silver": res["silver"], "controls": res["controls"],
            "figures": res["figures"], "findings": res["findings"]}


def glue_path(spark, inputs, cfg, run_id="r20261116T041000Z", previous=None):
    import dqdl_local
    from silver_build import glue_spark

    pred, report = glue_spark.evaluate_dq(spark, inputs, cfg, dqdl_local.evaluate)
    res = build(inputs, cfg, run_id, previous, predicates=pred, lifecycle_map=glue_spark.spark_lifecycle_map(spark))
    return res, pred, report


def test_golden_run_is_identical_on_the_glue_path(spark):
    cfg = config.load()
    ref = build(golden_inputs(), cfg, "r20261116T041000Z")
    got, pred, report = glue_path(spark, golden_inputs(), cfg)
    assert pred.mismatches == [] and sum(pred.consulted.values()) > 66674 * 5
    assert outputs(got, cfg) == outputs(ref, cfg)
    assert report["industry"]["rows_evaluated"] == 1961 and report["transactions"]["rows_evaluated"] == 66674
    assert report["sm_spend"]["failed_by_check"] == {k: 0 for k in report["sm_spend"]["failed_by_check"]}


@pytest.mark.parametrize("fixture", DIRTY)
def test_dirty_fixture_outcomes_are_identical(spark, fixture):
    cfg = config.load()
    files = dict(CLEAN)
    files[PREFIX[fixture.split("_")[0]]] = fixture
    data = {ds: (D / f).read_bytes() for ds, f in files.items()}
    ref = build(inputs_from(data), cfg, "r20261116T041000Z")
    got, pred, _ = glue_path(spark, inputs_from(data), cfg)
    assert pred.mismatches == []
    assert not [c for c in got["controls"] if c["failed"]]
    assert outputs(got, cfg) == outputs(ref, cfg)


def test_iceberg_full_rebuild_snapshot_per_table_tag_and_time_travel(spark):
    from silver_build import glue_spark

    cfg = config.load()
    writer = glue_spark.IcebergWriter(spark, "glue_catalog")
    tables = {}
    for rid in ("r20260101T000000Z", "r20260102T000000Z"):
        res = build(golden_inputs(), cfg, rid)
        recs = dq.records_for(res, cfg)
        tables[rid] = glue_spark.write_tables(writer, res, dq.dq_store_rows(res, cfg, recs), rid)
    a, b = tables["r20260101T000000Z"], tables["r20260102T000000Z"]
    assert set(a) == {"transactions", "industry", "sm_spend", "customer", "customer_month", "gap", "month_control",
                      "source_status", "restatement_log", "findings", "excluded_rows"}
    for t in a:
        if a[t]["rows"]:
            assert b[t]["new_snapshot"] and a[t]["snapshot_id"] != b[t]["snapshot_id"], t
    # Read back through Iceberg metadata and plain scans only: on this Mac's JVMs a
    # shuffle over an Iceberg scan hits a HotSpot SIGSEGV (JDK 11 and 17, macOS 26);
    # aggregates are verified on AWS with Athena instead.
    fq = writer.fq("transactions")
    refs = {r["name"]: r["snapshot_id"] for r in spark.sql(f"SELECT name, snapshot_id FROM {fq}.refs").collect()}
    assert refs["r20260101T000000Z"] == a["transactions"]["snapshot_id"]
    assert refs["r20260102T000000Z"] == refs["main"] == b["transactions"]["snapshot_id"]
    assert spark.sql(f"SELECT count(*) FROM {fq}.snapshots").collect()[0][0] == 2  # one commit per run
    old = spark.sql(f"SELECT _run_id, amount FROM {fq} VERSION AS OF 'r20260101T000000Z' LIMIT 3").collect()
    cur = spark.sql(f"SELECT _run_id, amount FROM {fq} LIMIT 3").collect()
    assert {r[0] for r in old} == {"r20260101T000000Z"} and {r[0] for r in cur} == {"r20260102T000000Z"}
    assert all(isinstance(r[1], Decimal) for r in cur)
    assert dict(spark.table(fq).dtypes)["amount"] == "decimal(12,6)"
    files = spark.sql(f"SELECT partition, record_count FROM {writer.fq('sm_spend')}.files").collect()
    by_part = {}
    for r in files:
        by_part[r[0]["hr_sensitive"]] = by_part.get(r[0]["hr_sensitive"], 0) + r[1]
    assert by_part == {False: 136, True: 102}
    ex = spark.sql(f"SELECT dataset_id, source_line, failed_rules FROM {writer.fq('excluded_rows')}").collect()
    assert [(r[0], r[1], list(r[2])) for r in ex] == [("industry", 1963, ["SQ-02"])]


def test_customer_month_gains_the_sb11_column_on_an_existing_table(spark, monkeypatch):
    """The deploy case: finora_silver.customer_month already exists without
    uneven_split_start_month. The next full rebuild adds the column (nullable, at
    its declared position) before writing, with one snapshot per run, and the
    pre-SB-11 snapshot stays readable by its tag with its own schema."""
    from common import schemas
    from silver_build import glue_spark

    cfg = config.load()
    data = {"transactions": (D / "tx_uneven_split.csv").read_bytes(),
            "industry": (D / CLEAN["industry"]).read_bytes(), "sm_spend": (D / CLEAN["sm_spend"]).read_bytes()}
    res = build(inputs_from(data), cfg, "r20260201T000000Z")
    db, cols, parts = schemas.ICEBERG["customer_month"]
    old_cols = [c for c in cols if c[0] != "uneven_split_start_month"]
    writer = glue_spark.IcebergWriter(spark, "glue_catalog")
    monkeypatch.setitem(schemas.ICEBERG, "customer_month", ("evo_silver", old_cols, parts))
    first = writer.write("customer_month", res["silver"]["customer_month"], "r20260201T000000Z")
    fq = writer.fq("customer_month")
    assert "uneven_split_start_month" not in spark.table(fq).columns
    monkeypatch.setitem(schemas.ICEBERG, "customer_month", ("evo_silver", cols, parts))
    assert writer.ensure("customer_month") == ["uneven_split_start_month"]
    assert writer.ensure("customer_month") == []  # idempotent
    second = writer.write("customer_month", res["silver"]["customer_month"], "r20260202T000000Z")
    assert spark.table(fq).columns == [n for n, _ in cols]  # declared order, as a fresh table would have
    assert dict(spark.table(fq).dtypes)["uneven_split_start_month"] == "string"
    assert spark.sql(f"SELECT count(*) FROM {fq}.snapshots").collect()[0][0] == 2  # the ALTER adds no snapshot
    assert first["snapshot_id"] != second["snapshot_id"] and second["new_snapshot"]
    got = spark.sql(f"SELECT customer_id, month, uneven_split_start_month FROM {fq} "
                    "WHERE uneven_split_start_month IS NOT NULL").collect()
    want = {(x["customer_id"], x["month"], x["uneven_split_start_month"])
            for x in res["silver"]["customer_month"] if x["uneven_split_start_month"]}
    assert {(r[0], r[1], r[2]) for r in got} == want and len(want) == 18
    old = spark.sql(f"SELECT * FROM {fq} VERSION AS OF 'r20260201T000000Z' LIMIT 1")
    assert "uneven_split_start_month" not in old.columns and old.collect()[0]["_run_id"] == "r20260201T000000Z"
    # Drift that is not a declared addition fails before any data is written
    monkeypatch.setitem(schemas.ICEBERG, "customer_month", ("evo_silver", old_cols, parts))
    with pytest.raises(RuntimeError, match="schema drift"):
        writer.ensure("customer_month")
