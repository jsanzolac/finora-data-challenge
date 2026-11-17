"""The gold job path on local Spark 3.5 + Iceberg 1.7 (Hadoop catalog) and moto S3:
silver read at its run tag, write-audit-publish (branch, audit, fast-forward,
tag), the run report and the acquisition serving snapshot (acq/latest.json
last), and the user-owned rates table: a rebuild never alters user rate rows,
a history rewrite is detected, and a failed control or audit publishes nothing.
"""

from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

pytest.importorskip("pyspark")

from gold_build import ddl, engine, funnel, gconfig, schemas, spark_io  # noqa: E402
from gold_build import run as gold_run  # noqa: E402
from gold_helpers import SILVER_RUN, golden_silver  # noqa: E402
from spark_support import spark_session  # noqa: E402

G = gconfig.load()
SILVER = ("transactions", "industry", "sm_spend", "customer", "customer_month", "month_control", "source_status")
DQ_LATEST = {"run_id": SILVER_RUN, "published_at": "2026-11-17T15:15:15Z"}


@pytest.fixture(scope="module")
def spark():
    s, _ = spark_session(Path(tempfile.mkdtemp(prefix="finora-gold-e2e-")))
    # Local only: Iceberg's Arrow-vectorized Parquet reader crashes this Mac's JVM
    # (HotSpot SIGSEGV in a G1 barrier, JDK 11, macOS 26) on full-table scans; the
    # row reader gives the same rows. Glue keeps the default (vectorized).
    s.conf.set("spark.sql.iceberg.vectorization.enabled", "false")
    yield s


@pytest.fixture(scope="module")
def lake(spark):
    """Silver tables tagged SILVER_RUN (plus a later failed partial write that must
    never be read), and the rates table created and seeded as the deploy step does."""
    from silver_build import glue_spark

    w = glue_spark.IcebergWriter(spark, "glue_catalog")
    res = golden_silver()
    for t in SILVER:
        w.write(t, res["silver"][t], SILVER_RUN)
    bad = [dict(r, _run_id="r20261117T170000Z") for r in res["silver"]["customer"][:5]]
    w.write("customer", bad, "r20261117T170000Z")  # untagged-as-succeeded partial write on main
    cols = ", ".join(f"{n} {'timestamp_ntz' if t == 'timestamp' else t}" for n, t in schemas.RATE_COLUMNS)
    spark.sql(f"CREATE TABLE IF NOT EXISTS glue_catalog.finora_gold.{schemas.RATE_TABLE} ({cols}) USING iceberg "
              "TBLPROPERTIES ('format-version'='2')")
    vals = ", ".join(f"('{r['scenario_id']}', '{r['scenario_label']}', '{r['from_stage_code']}', '{r['to_stage_code']}', "
                     f"CAST('{r['rate']}' AS DECIMAL(5,4)), CAST(current_timestamp() AS TIMESTAMP_NTZ), "
                     f"'{r['changed_by']}', '{r['change_reason']}')" for r in ddl.seed_rows(G))
    spark.sql(f"INSERT INTO glue_catalog.finora_gold.{schemas.RATE_TABLE} VALUES {vals}")
    return spark


@pytest.fixture
def s3():
    os.environ.update({"AWS_DEFAULT_REGION": "us-west-2", "AWS_ACCESS_KEY_ID": "t", "AWS_SECRET_ACCESS_KEY": "t",
                       "GOLD_BUCKET": "gold", "SERVING_BUCKET": "srv"})
    os.environ.pop("AWS_PROFILE", None)
    with mock_aws():
        from common import s3io
        s3io._s3 = s3io._s3_once = None
        c = boto3.client("s3")
        for b in ("gold", "srv"):
            c.create_bucket(Bucket=b, CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
        c.put_object(Bucket="srv", Key="dq/runs.json", Body=json.dumps(
            [{"run_id": "r20261117T170000Z", "status": "failed"}, {"run_id": SILVER_RUN, "status": "succeeded"},
             {"run_id": "r20261117T040928Z", "status": "failed"}]).encode())
        c.put_object(Bucket="srv", Key="dq/latest.json", Body=json.dumps(DQ_LATEST).encode())
        yield c


def get(c, bucket, key):
    return json.loads(c.get_object(Bucket=bucket, Key=key)["Body"].read())


def keys(c, bucket):
    return sorted(o["Key"] for o in c.list_objects_v2(Bucket=bucket).get("Contents", []))


def mains(w):
    return {t: w.ref(t) for t in schemas.ORDER if w.exists(t)}


def rate_snapshots(spark):
    return [r[0] for r in spark.sql(f"SELECT snapshot_id FROM glue_catalog.finora_gold.{schemas.RATE_TABLE}.snapshots"
                                    ).collect()]


def go(spark, run_id, alerts=None):
    reader = spark_io.SilverReader(spark, "glue_catalog")
    writer = spark_io.GoldWriter(spark, "glue_catalog")
    return gold_run.run({"run_id": run_id, "started_at": "x"}, reader=reader, writer=writer,
                        alert=(lambda s, m: alerts.append((s, m))) if alerts is not None else None)


def test_first_build_then_rebuilds_never_touch_user_rates(lake, s3):
    spark = lake
    w = spark_io.GoldWriter(spark, "glue_catalog")
    rate_before, rate_snaps = w.rate_rows()[0], rate_snapshots(spark)
    out = go(spark, "r20261117T180000Z")
    assert out == {"status": "succeeded", "run_id": "r20261117T180000Z", "silver_run_id": SILVER_RUN}
    rep = get(s3, "gold", "_runs/run_id=r20261117T180000Z/gold_report.json")
    assert rep["status"] == "succeeded" and rep["silver_run_id"] == SILVER_RUN and rep["findings"] == []
    assert all(c["passed"] for c in rep["controls"]) and rep["previous_gold_run_id"] is None
    assert rep["figures"]["rows"]["fact_customer_month_revenue"] == 66674
    for t in schemas.ORDER:  # one snapshot per table at main, tagged, audited, branch dropped
        refs = {r["name"]: (r["type"], r["snapshot_id"]) for r in
                spark.sql(f"SELECT name, type, snapshot_id FROM {w.fq(t)}.refs").collect()}
        assert refs["r20261117T180000Z"] == ("TAG", refs["main"][1]) and set(refs) == {"main", "r20261117T180000Z"}
        assert rep["iceberg"][t]["audit"]["digest_match"] and rep["iceberg"][t]["rows"] == rep["figures"]["rows"][t]
    # read back through Iceberg: silver read at the succeeded tag only (not the later partial write)
    status = w.read_ref("gold_build_status", "main")[0]
    assert status["_silver_run_id"] == SILVER_RUN and status["base_rates_match_seed"] is True
    assert status["rate_table_snapshot_id"] == rate_snaps[-1]
    assert status["rate_table_rows_sha256"] == funnel.rows_sha256(rate_before)
    dc = w.read_ref("dim_customer", "main")
    assert len(dc) == 1961 and {r["_run_id"] for r in dc} == {"r20261117T180000Z"}
    # HR partition and no spend bounds in the manifests (§5.8)
    files = spark.sql(f"SELECT partition, record_count, readable_metrics FROM {w.fq('fact_sm_spend')}.files").collect()
    by = {}
    for f in files:
        by[f[0]["hr_sensitive"]] = by.get(f[0]["hr_sensitive"], 0) + f[1]
        for col in ("spend", "spend_value"):
            m = f[2][col]
            assert m["lower_bound"] is None and m["upper_bound"] is None
    assert by == {False: 136, True: 102}
    assert w.properties("fact_sm_spend")["write.metadata.metrics.column.spend_value"] == "none"
    # serving: summary then acq/latest.json; dq/* untouched
    latest = get(s3, "srv", "acq/latest.json")
    assert latest["run_id"] == "r20261117T180000Z"
    p = get(s3, "srv", "acq/runs/r20261117T180000Z/summary.json")
    assert p["run"]["run_id"] == "r20261117T180000Z" and len(p["months"]) == 33
    assert get(s3, "srv", "dq/latest.json") == DQ_LATEST
    assert [k for k in keys(s3, "srv") if k.startswith("dq/")] == ["dq/latest.json", "dq/runs.json"]
    # the job never wrote the rates table
    assert rate_snapshots(spark) == rate_snaps and w.rate_rows()[0] == rate_before

    # a user adds a scenario (append-only), then the next full rebuild
    spark.sql(f"""INSERT INTO glue_catalog.finora_gold.{schemas.RATE_TABLE}
        SELECT 'sql_demo_080', 'SQL to Demo at 80%', from_stage_code, to_stage_code,
               CASE WHEN from_stage_code = 'SQL' THEN CAST('0.8000' AS DECIMAL(5,4)) ELSE rate END,
               CAST(current_timestamp() AS TIMESTAMP_NTZ), 'dashboard:0123456789ab', 'What if demos are booked faster'
        FROM glue_catalog.finora_gold.{schemas.RATE_TABLE} WHERE scenario_id = 'base'""")
    user_rows, user_snaps = w.rate_rows()[0], rate_snapshots(spark)
    assert len(user_rows) == 12
    go(spark, "r20261117T190000Z")
    rep2 = get(s3, "gold", "_runs/run_id=r20261117T190000Z/gold_report.json")
    assert rep2["status"] == "succeeded" and rep2["findings"] == [] and rep2["previous_gold_run_id"] == "r20261117T180000Z"
    assert rate_snapshots(spark) == user_snaps
    assert funnel.rows_sha256(w.rate_rows()[0]) == funnel.rows_sha256(user_rows)
    st2 = w.read_ref("gold_build_status", "main")[0]
    assert st2["rate_table_snapshot_id"] == user_snaps[-1] and st2["_run_id"] == "r20261117T190000Z"
    # the earlier build stays readable by its tag
    assert w.read_ref("gold_build_status", "r20261117T180000Z")[0]["_run_id"] == "r20261117T180000Z"
    assert get(s3, "srv", "acq/latest.json")["run_id"] == "r20261117T190000Z"
    with pytest.raises(PermissionError):
        w.ensure(schemas.RATE_TABLE)


def test_a_history_rewrite_is_detected_and_alerted(lake, s3):
    spark = lake
    w = spark_io.GoldWriter(spark, "glue_catalog")
    if not w.exists("gold_build_status") or w.ref("gold_build_status") is None:
        go(spark, "r20261117T200000Z")
    # someone rewrites history: the base NEW row is replaced in place
    spark.sql(f"""INSERT OVERWRITE glue_catalog.finora_gold.{schemas.RATE_TABLE}
        SELECT scenario_id, scenario_label, from_stage_code, to_stage_code,
               CASE WHEN scenario_id = 'base' AND from_stage_code = 'NEW' THEN CAST('0.9000' AS DECIMAL(5,4)) ELSE rate END,
               changed_at, changed_by, change_reason
        FROM glue_catalog.finora_gold.{schemas.RATE_TABLE}""")
    alerts: list = []
    go(spark, "r20261117T210000Z", alerts)
    rep = get(s3, "gold", "_runs/run_id=r20261117T210000Z/gold_report.json")
    found = {f["finding"] for f in rep["findings"]}
    assert {"RATE_HISTORY_REWRITTEN", "BASE_DIFFERS_FROM_SEED"} <= found and rep["status"] == "succeeded"
    assert alerts and "RATE_HISTORY_REWRITTEN" in alerts[0][0]
    assert w.read_ref("gold_build_status", "main")[0]["base_rates_match_seed"] is False


@pytest.mark.parametrize("failure", ["control", "audit", "silver_missing"])
def test_a_failed_control_or_audit_publishes_nothing(lake, s3, monkeypatch, failure):
    spark = lake
    w = spark_io.GoldWriter(spark, "glue_catalog")
    if not w.exists("gold_build_status") or w.ref("gold_build_status") is None:
        go(spark, "r20261117T220000Z")
    s3.put_object(Bucket="srv", Key="acq/latest.json", Body=json.dumps({"run_id": "r20261117T220000Z"}).encode())
    before = mains(w)
    if failure == "control":
        real = engine.controls
        monkeypatch.setattr(engine, "controls", lambda *a: real(*a) + [{"id": "GC-05", "passed": False,
                                                                         "detail": "planted"}])
    elif failure == "audit":
        real_audit = spark_io.GoldWriter.audit
        monkeypatch.setattr(spark_io.GoldWriter, "audit", lambda self, t, rows, rid: {
            **real_audit(self, t, rows, rid), **({"passed": False} if t == "fact_sm_spend" else {})})
    else:
        s3.put_object(Bucket="srv", Key="dq/runs.json", Body=json.dumps(
            [{"run_id": "r20261117T230000Z", "status": "succeeded"}]).encode())  # no such silver tag
    with pytest.raises(Exception):
        go(spark, "r20261117T235900Z")
    assert mains(w) == before  # main untouched on every table: the previous build stays live
    rep = get(s3, "gold", "_runs/run_id=r20261117T235900Z/gold_report.json")
    assert rep["status"] == "failed"
    assert get(s3, "srv", "acq/latest.json") == {"run_id": "r20261117T220000Z"}
    assert "acq/runs/r20261117T235900Z/summary.json" not in keys(s3, "srv")
    assert get(s3, "srv", "dq/latest.json") == DQ_LATEST


def test_existing_fact_acquisition_gains_the_lever_columns(lake, monkeypatch):
    """The deploy case: finora_gold.fact_acquisition exists without the §16.4(a) columns.
    ensure() adds them (nullable, at their declared position) before the next write."""
    spark = lake
    new = ["cohort_half", "run_rate_status", "run_rate_m2_4_months", "run_rate_m2_4_value", "paying_m6", "paying_m12"]
    cols = schemas.COLUMNS["fact_acquisition"]
    old = [c for c in cols if c[0] not in new]
    w = spark_io.GoldWriter(spark, "glue_catalog", db="evo_gold")
    monkeypatch.setitem(schemas.COLUMNS, "fact_acquisition", old)
    w.ensure("fact_acquisition")
    assert not set(new) & set(spark.table(w.fq("fact_acquisition")).columns)
    monkeypatch.setitem(schemas.COLUMNS, "fact_acquisition", cols)
    assert w.ensure("fact_acquisition") == new
    assert spark.table(w.fq("fact_acquisition")).columns == [n for n, _ in cols]
    assert w.ensure("fact_acquisition") == []
