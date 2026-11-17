"""Glue 5.0 Spark job finora-dl-silver-build (--datalake-formats iceberg,
MaxConcurrentRuns=1, bookmarks off).

Bronze -> silver + DQ store as Iceberg tables in the Glue Data Catalog
(finora_silver, finora_dq; warehouse s3://al-test-dl-silver/iceberg/).
  1. Row-level quality rules that DQDL expresses run in Glue Data Quality
     (EvaluateDataQuality, row-level outcomes) with the deployed rulesets
     finora-dl-<dataset>; the engine's reference predicates shadow them and any
     disagreement fails the run.
  2. Lifecycle per customer runs on the executors (applyInPandas, exact Decimal).
  3. Findings, business rules and run controls run in the exact-Decimal engine.
  4. Every table is overwritten in one commit (one snapshot) tagged <run_id>.
"""

import os
import sys

from awsglue.context import GlueContext
from awsglue.dynamicframe import DynamicFrame
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark import SparkConf
from pyspark.context import SparkContext

ARGS = ["JOB_NAME", "run_id", "started_at", "iceberg_warehouse",
        "STAGING_BUCKET", "BRONZE_BUCKET", "SILVER_BUCKET", "SERVING_BUCKET"]
args = getResolvedOptions(sys.argv, ARGS)
os.environ.update({k: args[k] for k in ARGS if k.endswith("_BUCKET")})
os.environ.setdefault("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-west-2"))
WAREHOUSE = args["iceberg_warehouse"].rstrip("/") + "/"

conf = SparkConf()
for k, v in {
    "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
    "spark.sql.catalog.glue_catalog": "org.apache.iceberg.spark.SparkCatalog",
    "spark.sql.catalog.glue_catalog.catalog-impl": "org.apache.iceberg.aws.glue.GlueCatalog",
    "spark.sql.catalog.glue_catalog.io-impl": "org.apache.iceberg.aws.s3.S3FileIO",
    "spark.sql.catalog.glue_catalog.warehouse": WAREHOUSE,
    "spark.sql.shuffle.partitions": "8",
    "spark.sql.session.timeZone": "UTC",
}.items():
    conf.set(k, v)
sc = SparkContext.getOrCreate(conf=conf)
glue = GlueContext(sc)
spark = glue.spark_session
job = Job(glue)
job.init(args["JOB_NAME"], args)

import boto3  # noqa: E402
from awsgluedq.transforms import EvaluateDataQuality  # noqa: E402

from common import dqdl  # noqa: E402
from silver_build import glue_spark  # noqa: E402
from silver_build import run as silver_run  # noqa: E402


def deployed_rulesets(cfg: dict) -> dict:
    """The rulesets deployed by FinoraDlEtl. They must equal the ones generated
    from the packaged rules config (no console drift)."""
    api = boto3.client("glue")
    out = {}
    for ds in cfg["dataset_order"]:
        text = api.get_data_quality_ruleset(Name=dqdl.ruleset_name(ds))["Ruleset"]
        if text.strip() != dqdl.ruleset(cfg, ds).strip():
            raise RuntimeError(f"Glue DQ ruleset {dqdl.ruleset_name(ds)} differs from the packaged rules config")
        out[ds] = text
    return out


def evaluate(ds: str, frame, text: str):
    dyf = DynamicFrame.fromDF(frame, glue, f"dq_input_{ds}")
    res = EvaluateDataQuality().process_rows(
        frame=dyf, ruleset=text,
        publishing_options={"dataQualityEvaluationContext": dqdl.ruleset_name(ds),
                            "enableDataQualityCloudWatchMetrics": False,
                            "enableDataQualityResultsPublishing": True},
        additional_options={"performanceTuning.caching": "CACHE_NOTHING"})
    rows = res.select("rowLevelOutcomes").toDF()
    outcomes = [r.asDict(recursive=True) for r in res.select("ruleOutcomes").toDF().collect()]
    return rows, outcomes


writer = glue_spark.IcebergWriter(spark, "glue_catalog", location=lambda db, t: f"{WAREHOUSE}{db}/{t}")
silver_run.run(
    {"run_id": args["run_id"], "started_at": args["started_at"]},
    write_tables=lambda res, store, rid: glue_spark.write_tables(writer, res, store, rid),
    evaluate_dq=lambda inputs, cfg: glue_spark.evaluate_dq(spark, inputs, cfg, evaluate, deployed_rulesets(cfg)),
    lifecycle_map=glue_spark.spark_lifecycle_map(spark),
)
job.commit()
