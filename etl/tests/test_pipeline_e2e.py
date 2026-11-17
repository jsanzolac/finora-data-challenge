"""bronze_ingest -> silver_build -> dq_publish on moto S3 with today's files,
as the Glue jobs call them. Mode "reference": engine predicates, in-process
lifecycle, no table writer (runs on any Python). Mode "glue": the Glue path with
local PySpark (DQDL row outcomes from the local Glue DQ stand-in, applyInPandas
lifecycle, Iceberg tables). Set FINORA_DUMP_SERVING=<dir> to keep the first
run's serving snapshot for scripts/compare_dq_runs.py."""

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from golden_helpers import FILES, ROOT

B = {"STAGING_BUCKET": "stg", "BRONZE_BUCKET": "brz", "SILVER_BUCKET": "slv", "SERVING_BUCKET": "srv"}


@pytest.fixture
def lake():
    os.environ.update({"AWS_DEFAULT_REGION": "us-west-2", "AWS_ACCESS_KEY_ID": "t", "AWS_SECRET_ACCESS_KEY": "t", **B})
    os.environ.pop("AWS_PROFILE", None)
    with mock_aws():
        from common import s3io
        s3io._s3 = s3io._s3_once = None
        s3 = boto3.client("s3")
        for b in B.values():
            s3.create_bucket(Bucket=b, CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
        for ds, (key, f) in FILES.items():
            s3.put_object(Bucket="stg", Key=key, Body=(ROOT / "data" / f).read_bytes())
        yield s3


@pytest.fixture(scope="module", params=["reference", "glue"])
def mode(request):
    if request.param == "reference":
        return {"name": "reference", "kw": {"write_tables": lambda res, store, rid: {}}}
    pytest.importorskip("pyspark")
    import dqdl_local
    from silver_build import glue_spark
    from spark_support import spark_session

    spark, _ = spark_session(Path(tempfile.mkdtemp(prefix="finora-e2e-")))
    writer = glue_spark.IcebergWriter(spark, "glue_catalog")
    return {"name": "glue", "spark": spark, "kw": {
        "write_tables": lambda res, store, rid: glue_spark.write_tables(writer, res, store, rid),
        "evaluate_dq": lambda inputs, cfg: glue_spark.evaluate_dq(spark, inputs, cfg, dqdl_local.evaluate),
        "lifecycle_map": glue_spark.spark_lifecycle_map(spark)}}


def run_pipeline(event, mode, run_id):
    from bronze_ingest.handler import handler as bronze
    from dq_publish.handler import handler as publish
    from silver_build import run as silver

    state = bronze({**event, "run_id": run_id, "started_at": "2026-11-17T00:00:00Z"})
    state["silver"] = silver.run({"run_id": run_id, "started_at": state["started_at"]}, **mode["kw"])
    state["publish"] = publish({"run_id": run_id})
    return state


def dump(s3, run_id, out: Path):
    for o in s3.list_objects_v2(Bucket="srv", Prefix=f"dq/runs/{run_id}/", MaxKeys=1000)["Contents"]:
        p = out / o["Key"][len(f"dq/runs/{run_id}/"):]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(s3.get_object(Bucket="srv", Key=o["Key"])["Body"].read())


def test_pipeline_end_to_end_and_idempotent(lake, mode):
    keys = [k for k, _ in FILES.values()]
    st = run_pipeline({"keys": keys}, mode, "r20261117T000001Z")
    assert {v["status"] for v in st["ingested"].values()} == {"ingested"}
    latest = json.loads(lake.get_object(Bucket="srv", Key="dq/latest.json")["Body"].read())
    assert latest["run_id"] == st["run_id"]
    summ = json.loads(lake.get_object(Bucket="srv", Key=f"dq/runs/{st['run_id']}/summary.json")["Body"].read())
    assert [d["dataset_id"] for d in summ["datasets"]] == ["transactions", "sm_spend", "industry"]
    assert len(summ["trend"]) == 1 and summ["run"]["finished_at"]
    page = json.loads(lake.get_object(Bucket="srv", Key=f"dq/runs/{st['run_id']}/records/SQ-02/industry/page-1.json")["Body"].read())
    assert page["total"] == 1 and page["records"][0]["source_line"] == 1963
    sb11 = json.loads(lake.get_object(Bucket="srv", Key=f"dq/runs/{st['run_id']}/records/SB-11/transactions/page-1.json")["Body"].read())
    assert (sb11["total"], sb11["page_count"], sb11["records"][0]["source_line"]) == (22, 1, 386)
    rule = next(r for r in summ["rules"] if r["rule_id"] == "SB-11")
    assert rule["results"]["transactions"] == {"evaluated": 66674, "failed": 22, "compliance_pct": 99.97, "status": "warn"}
    assert summ["datasets"][0]["rows_flagged"] == 22
    if os.environ.get("FINORA_DUMP_SERVING") and mode["name"] == "glue":
        dump(lake, st["run_id"], Path(os.environ["FINORA_DUMP_SERVING"]))
    # bronze object is byte-faithful + _ingested_at; the manifest holds the verbatim key
    sha = hashlib.sha256((ROOT / "data" / "S&M_spend.csv").read_bytes()).hexdigest()
    man = json.loads(lake.get_object(Bucket="brz", Key=f"_manifests/sm_spend/{sha}.json")["Body"].read())
    assert man["source_key"] == "s_and_m/S&M_spend.csv" and man["header_matches_registry"]
    assert man["control_totals"] == {"sum": "77.818", "unparsed_cells": 0}
    report = json.loads(lake.get_object(Bucket="slv", Key=f"_runs/run_id={st['run_id']}/report.json")["Body"].read())
    if mode["name"] == "glue":
        assert report["glue_dq"]["mismatch_count"] == 0
        assert report["written"]["transactions"] == 66674 and report["written"]["excluded_rows"] == 1
        assert all(v["tag"] == st["run_id"] and v["snapshot_id"] for v in report["iceberg"].values())
    # re-delivery of the same bytes: no new bronze object, a new full-rebuild run
    n_before = len(lake.list_objects_v2(Bucket="brz", Prefix="sm_spend/")["Contents"])
    time.sleep(1.1)
    st2 = run_pipeline({"detail": {"bucket": {"name": "stg"}, "object": {"key": "s_and_m/S%26M_spend.csv"}}}, mode,
                       "r20261117T000002Z")
    assert st2["ingested"]["sm_spend"]["status"] == "duplicate"
    assert len(lake.list_objects_v2(Bucket="brz", Prefix="sm_spend/")["Contents"]) == n_before
    runs = json.loads(lake.get_object(Bucket="srv", Key="dq/runs.json")["Body"].read())
    assert [r["run_id"] for r in runs] == [st2["run_id"], st["run_id"]]
    # CDO-06 now compares with the previous run: evaluated > 0, nothing removed or restated
    s2 = json.loads(lake.get_object(Bucket="srv", Key=f"dq/runs/{st2['run_id']}/summary.json")["Body"].read())
    r06 = next(r for r in s2["rules"] if r["rule_id"] == "CDO-06a")["results"]["transactions"]
    assert (r06["evaluated"], r06["failed"], r06["status"]) == (66674, 0, "pass")
    assert len(s2["trend"]) == 2


def test_failed_run_is_recorded_and_latest_untouched(lake):
    from bronze_ingest.handler import handler as bronze
    from dq_publish.handler import handler as publish
    from silver_build import run as silver

    st = bronze({"all": True, "run_id": "r20261117T000003Z", "started_at": "x"})
    silver.run({"run_id": st["run_id"]}, write_tables=lambda res, store, rid: {})
    publish({"run_id": st["run_id"]})
    publish({"mode": "failed", "run_id": "r20991231T000000Z", "started_at": "x", "ingested": {}})
    latest = json.loads(lake.get_object(Bucket="srv", Key="dq/latest.json")["Body"].read())
    assert latest["run_id"] == st["run_id"]
    runs = json.loads(lake.get_object(Bucket="srv", Key="dq/runs.json")["Body"].read())
    assert runs[0]["status"] == "failed"


def test_write_once_header_fallback_without_native_param(lake, monkeypatch):
    """Glue runtimes with an older botocore still get If-None-Match: * on manifests."""
    from common import s3io
    monkeypatch.setattr(s3io, "_native_if_none_match", lambda: False)
    assert s3io.put_bytes("brz", "_manifests/x/once.json", b"{}", "application/json", once=True) is True
    assert s3io.put_bytes("brz", "_manifests/x/once.json", b"{}", "application/json", once=True) is False
