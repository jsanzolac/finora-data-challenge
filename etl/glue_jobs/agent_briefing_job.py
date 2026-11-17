"""Glue 5.0 job finora-dl-agent-briefing (driver-side Python, like dq-publish): the voice
agent's briefing of each gold refresh (docs/semantic_layer.md §4, contract v1.1).

KPI table by code (compiled specs on the run's pinned gold snapshot, in Athena workgroup
finora-dl, plus the DQ snapshot of the same silver run) -> Kimi K3 on Bedrock us-east-1
(tool use) -> the §4.4 number check -> §4.5 fallback -> s3://<serving>/agent/briefing/<run_id>.json,
then agent/briefing/latest.json LAST. It reads gold and serving and writes only
agent/briefing/*: it can never alter dq/*, acq/* or mrr/*, and Step Functions catches its
failure in its own Fail state after every publish.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

ARGS = ["JOB_NAME", "run_id", "GOLD_BUCKET", "SERVING_BUCKET", "ATHENA_WORKGROUP", "BEDROCK_MODEL_ID", "BEDROCK_REGION"]
args = getResolvedOptions(sys.argv, ARGS)
os.environ.update({k: args[k] for k in ARGS if k not in ("JOB_NAME", "run_id")})
os.environ.setdefault("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-west-2"))
glue = GlueContext(SparkContext.getOrCreate())
job = Job(glue)
job.init(args["JOB_NAME"], args)

import boto3  # noqa: E402

from agentlib import ask as A  # noqa: E402
from agentlib import briefing as B  # noqa: E402
from agentlib import compiler as K  # noqa: E402
from agentlib import context as CTX  # noqa: E402


def log(event, **kw):
    print(json.dumps({"event": event, "run_id": args["run_id"], **kw}, ensure_ascii=False, default=str))


run_id = args["run_id"]
if not K.RUN_ID_RE.fullmatch(run_id):
    raise SystemExit("bad run_id")
ctx = CTX.load(run_id)
dq = CTX.dq_snapshot(ctx)


def run(spec):
    comp = K.compile_spec(K.validate(spec), "data", ctx)  # role data: no HR value can compile
    return A.run_sync(comp, ctx, time.monotonic() + 120, lambda: dq)


t0 = time.monotonic()
cands = B.build_kpi_table(ctx, run, dq)
log("briefing_kpi_table", candidates=[c.candidate_id for c in cands], s=round(time.monotonic() - t0, 1))
b = B.generate(cands, log=log)
refreshed = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
doc = B.document(b, ctx, refreshed)
s3 = boto3.client("s3")
bucket = os.environ["SERVING_BUCKET"]
s3.put_object(Bucket=bucket, Key=f"agent/briefing/{run_id}.json", ContentType="application/json",
              Body=json.dumps(doc, ensure_ascii=False).encode())
s3.put_object(Bucket=bucket, Key="agent/briefing/latest.json", ContentType="application/json",
              Body=json.dumps({"run_id": run_id, "as_of_month": doc["as_of_month"], "refreshed_at": refreshed,
                               "status": doc["status"]}).encode())
log("briefing_published", status=doc["status"], facts=len(doc["facts"]), stats=b.stats)
job.commit()
