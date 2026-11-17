"""Glue 5.0 job finora-dl-bronze-ingest (driver-side Python; the shared code
comes from the --extra-py-files library zip).

Staging (read-only) -> bronze: byte-faithful CSV + `_ingested_at`, write-once
manifest per (dataset, SHA-256). Step Functions passes run_id, started_at and
the triggering event (S3 Object Created, {"keys": [...]} or {"all": true}).
The result is stored at bronze _runs/run_id=<id>/ingest.json for the failure
recorder.
"""

import json
import os
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

ARGS = ["JOB_NAME", "run_id", "started_at", "event", "STAGING_BUCKET", "BRONZE_BUCKET"]
args = getResolvedOptions(sys.argv, ARGS)
os.environ.update({k: args[k] for k in ARGS if k.endswith("_BUCKET")})
os.environ.setdefault("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-west-2"))
glue = GlueContext(SparkContext.getOrCreate())
job = Job(glue)
job.init(args["JOB_NAME"], args)

from bronze_ingest.handler import handler  # noqa: E402
from common.s3io import log, put_json  # noqa: E402

event = {**json.loads(args["event"]), "run_id": args["run_id"], "started_at": args["started_at"]}
out = handler(event)
put_json(os.environ["BRONZE_BUCKET"], f"_runs/run_id={out['run_id']}/ingest.json", out)
log("bronze.job_done", run_id=out["run_id"], datasets={k: v["status"] for k, v in out["ingested"].items()})
job.commit()
