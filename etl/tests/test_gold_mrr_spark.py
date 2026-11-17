"""The gold MRR job path on local Spark 3.5 + Iceberg 1.7 (Hadoop catalog) and moto S3:
silver read at its succeeded run tag, write-audit-publish of the four MRR tables
(branch, audit, fast-forward, tag), the run report and the serving snapshot
(movement pages and summary, mrr/latest.json last), re-runs, and a failed control
or audit that publishes nothing. An acquisition gold table in the same database
is never touched, and dq/* and acq/* stay as they were.
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

from gold_helpers import SILVER_RUN, golden_silver  # noqa: E402
from gold_mrr import engine, iceberg_io, schemas  # noqa: E402
from gold_mrr import run as mrr_run  # noqa: E402
from spark_support import spark_session  # noqa: E402

DQ_LATEST = {"run_id": SILVER_RUN, "published_at": "2026-11-17T15:15:15Z"}
ACQ_LATEST = {"run_id": "r20261117T190113Z", "published_at": "2026-11-17T19:11:03Z"}


@pytest.fixture(scope="module")
def spark():
    s, _ = spark_session(Path(tempfile.mkdtemp(prefix="finora-gold-mrr-")))
    # Local only (as in test_gold_spark): the vectorized Parquet reader crashes this Mac's JVM.
    s.conf.set("spark.sql.iceberg.vectorization.enabled", "false")
    yield s


@pytest.fixture(scope="module")
def lake(spark):
    from silver_build import glue_spark

    w = glue_spark.IcebergWriter(spark, "glue_catalog")
    res = golden_silver()
    for t in schemas.SILVER_INPUTS:
        w.write(t, res["silver"][t], SILVER_RUN)
    bad = [dict(r, _run_id="r20261117T170000Z") for r in res["silver"]["customer"][:5]]
    w.write("customer", bad, "r20261117T170000Z")  # a later partial write on main: never read
    # an acquisition gold table in the same database, which the MRR job must never touch
    spark.sql("CREATE TABLE IF NOT EXISTS glue_catalog.finora_gold.fact_customer_month_revenue (customer_id INT) "
              "USING iceberg TBLPROPERTIES ('format-version'='2')")
    spark.sql("INSERT INTO glue_catalog.finora_gold.fact_customer_month_revenue VALUES (1)")
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
            [{"run_id": "r20261117T170000Z", "status": "failed"}, {"run_id": SILVER_RUN, "status": "succeeded"}]).encode())
        c.put_object(Bucket="srv", Key="dq/latest.json", Body=json.dumps(DQ_LATEST).encode())
        c.put_object(Bucket="srv", Key="acq/latest.json", Body=json.dumps(ACQ_LATEST).encode())
        yield c


def get(c, bucket, key):
    return json.loads(c.get_object(Bucket=bucket, Key=key)["Body"].read())


def keys(c, bucket, prefix=""):
    out, tok = [], None
    while True:
        kw = {"Bucket": bucket, "Prefix": prefix, **({"ContinuationToken": tok} if tok else {})}
        r = c.list_objects_v2(**kw)
        out += [o["Key"] for o in r.get("Contents", [])]
        if not r.get("IsTruncated"):
            return sorted(out)
        tok = r["NextContinuationToken"]


def acq_snapshots(spark):
    return [r[0] for r in spark.sql("SELECT snapshot_id FROM glue_catalog.finora_gold.fact_customer_month_revenue"
                                    ".snapshots").collect()]


def mains(w):
    return {t: w.ref(t) for t in schemas.ORDER}


def go(spark, run_id, order=None, monkeypatch=None):
    if order is not None:
        real = mrr_run.put_json
        monkeypatch.setattr(mrr_run, "put_json", lambda b, k, o, **kw: (order.append(k), real(b, k, o, **kw))[1])
    return mrr_run.run({"run_id": run_id, "started_at": "x"}, reader=iceberg_io.SilverReader(spark, "glue_catalog"),
                       writer=iceberg_io.MrrWriter(spark, "glue_catalog"))


def test_build_publish_and_rebuild(lake, s3, monkeypatch):
    spark = lake
    w = iceberg_io.MrrWriter(spark, "glue_catalog")
    acq_before = acq_snapshots(spark)
    order: list = []
    out = go(spark, "r20261117T200000Z", order, monkeypatch)
    assert out == {"status": "succeeded", "run_id": "r20261117T200000Z", "silver_run_id": SILVER_RUN}
    rep = get(s3, "gold", "_runs/run_id=r20261117T200000Z/mrr_report.json")
    assert rep["status"] == "succeeded" and rep["contract_checks"] == "passed"
    assert all(c["passed"] for c in rep["controls"])
    assert rep["figures"]["rows"] == {"dim_movement_type": 24, "fact_customer_month_mrr": 66674,
                                      "fact_mrr_movement": 4589, "agg_mrr_bridge_month": 792}
    for t in schemas.ORDER:
        refs = {r["name"]: (r["type"], r["snapshot_id"]) for r in
                spark.sql(f"SELECT name, type, snapshot_id FROM {w.fq(t)}.refs").collect()}
        assert refs["r20261117T200000Z"] == ("TAG", refs["main"][1]) and set(refs) == {"main", "r20261117T200000Z"}
        assert rep["iceberg"][t]["audit"]["digest_match"]
    # read back through Iceberg: exact decimals and the 2024-10 fixture
    b = {r["line"]: r for r in w.read_ref("agg_mrr_bridge_month", "r20261117T200000Z") if r["month_key"] == 202410}
    assert b["opening"]["amount"] == Decimal("9274.712517") and b["closing"]["amount"] == Decimal("9636.064683")
    assert b["collected"]["amount"] == Decimal("9700.744683") and b["discount_start"]["amount"] is None
    mv = w.read_ref("fact_mrr_movement", "main")
    assert len(mv) == 4589 and sum(r["amount"] for r in mv) == Decimal("6136.033848")
    assert {r["_silver_run_id"] for r in mv} == {SILVER_RUN}
    # serving: pages, then summary, then latest LAST; dq/* and acq/* untouched
    srv = [k for k in order if not k.startswith("_runs/")]
    assert srv[-1] == "mrr/latest.json" and srv[-2] == "mrr/runs/r20261117T200000Z/summary.json"
    assert len([k for k in srv if "/movements/page-" in k]) == 23
    assert order[0] == "_runs/run_id=r20261117T200000Z/mrr_report.json"
    p = get(s3, "srv", "mrr/runs/r20261117T200000Z/summary.json")
    assert p["run"]["mrr_basis"] == "cash_proxy" and len(p["months"]) == 33
    assert p["months"][-1]["closing_mrr_value"] == "96360646.83"
    pg = get(s3, "srv", "mrr/runs/r20261117T200000Z/movements/page-1.json")
    assert pg["total"] == 4589 and pg["page_size"] == 200 and len(pg["movements"]) == 200
    assert get(s3, "srv", "dq/latest.json") == DQ_LATEST and get(s3, "srv", "acq/latest.json") == ACQ_LATEST
    assert keys(s3, "srv", "dq/") == ["dq/latest.json", "dq/runs.json"] and keys(s3, "srv", "acq/") == ["acq/latest.json"]
    assert acq_snapshots(spark) == acq_before
    # a rebuild: new tag, the earlier one stays readable
    go(spark, "r20261117T210000Z")
    assert get(s3, "srv", "mrr/latest.json")["run_id"] == "r20261117T210000Z"
    assert {r["_run_id"] for r in w.read_ref("agg_mrr_bridge_month", "r20261117T200000Z")} == {"r20261117T200000Z"}
    assert {r["_run_id"] for r in w.read_ref("agg_mrr_bridge_month", "main")} == {"r20261117T210000Z"}
    assert acq_snapshots(spark) == acq_before


@pytest.mark.parametrize("failure", ["control", "audit", "silver_missing"])
def test_a_failure_publishes_nothing(lake, s3, monkeypatch, failure):
    spark = lake
    w = iceberg_io.MrrWriter(spark, "glue_catalog")
    if w.ref("agg_mrr_bridge_month") is None:
        go(spark, "r20261117T220000Z")
    s3.put_object(Bucket="srv", Key="mrr/latest.json", Body=json.dumps({"run_id": "r20261117T220000Z"}).encode())
    before, acq_before = mains(w), acq_snapshots(spark)
    if failure == "control":
        real = engine.controls
        monkeypatch.setattr(engine, "controls", lambda *a: real(*a) + [{"control": "GC-MRR-3", "passed": False,
                                                                         "detail": "planted"}])
    elif failure == "audit":
        real_audit = iceberg_io.MrrWriter.audit
        monkeypatch.setattr(iceberg_io.MrrWriter, "audit", lambda self, t, rows, rid: {
            **real_audit(self, t, rows, rid), **({"passed": False} if t == "fact_mrr_movement" else {})})
    else:
        s3.put_object(Bucket="srv", Key="dq/runs.json", Body=json.dumps(
            [{"run_id": "r20261117T230000Z", "status": "succeeded"}]).encode())
    with pytest.raises(Exception):
        go(spark, "r20261117T235900Z")
    assert mains(w) == before and acq_snapshots(spark) == acq_before
    assert get(s3, "gold", "_runs/run_id=r20261117T235900Z/mrr_report.json")["status"] == "failed"
    assert get(s3, "srv", "mrr/latest.json") == {"run_id": "r20261117T220000Z"}
    assert keys(s3, "srv", "mrr/runs/r20261117T235900Z/") == []
    assert get(s3, "srv", "dq/latest.json") == DQ_LATEST and get(s3, "srv", "acq/latest.json") == ACQ_LATEST
