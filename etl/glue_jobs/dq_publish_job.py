"""Glue 5.0 job finora-dl-dq-publish (driver-side Python): the DQ serving
refresh. --mode published writes dq/runs/<run_id>/... then runs.json, trend.json
and dq/latest.json LAST, exactly per contracts/dq_api_contract.md. --mode failed
only records the failed run in runs.json (latest.json untouched)."""

import os
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

ARGS = ["JOB_NAME", "run_id", "started_at", "mode", "BRONZE_BUCKET", "SILVER_BUCKET", "SERVING_BUCKET"]
args = getResolvedOptions(sys.argv, ARGS)
os.environ.update({k: args[k] for k in ARGS if k.endswith("_BUCKET")})
os.environ.setdefault("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-west-2"))
glue = GlueContext(SparkContext.getOrCreate())
job = Job(glue)
job.init(args["JOB_NAME"], args)

from common.s3io import get_json  # noqa: E402
from dq_publish.handler import handler  # noqa: E402

if args["mode"] == "failed":
    ingest = get_json(os.environ["BRONZE_BUCKET"], f"_runs/run_id={args['run_id']}/ingest.json") or {}
    handler({"mode": "failed", "run_id": args["run_id"], "started_at": args["started_at"],
             "ingested": ingest.get("ingested") or {}})
else:
    handler({"run_id": args["run_id"]})
job.commit()
