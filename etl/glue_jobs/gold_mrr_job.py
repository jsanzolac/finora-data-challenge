"""Glue 5.0 Spark job finora-dl-gold-mrr (--datalake-formats iceberg,
MaxConcurrentRuns=1, bookmarks off, no retries).

Silver (read at the latest succeeded run's tag) -> the gold MRR model in
finora_gold (docs/mrr_discounts_model.md §6; warehouse s3://al-test-dl-gold/iceberg/),
write-audit-publish, then the MRR serving snapshot (mrr/latest.json last).
Step Functions runs it after the acquisition gold build; it never writes an
acquisition table, dq/* or acq/*.
"""

import os
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark import SparkConf
from pyspark.context import SparkContext

ARGS = ["JOB_NAME", "run_id", "started_at", "iceberg_warehouse", "GOLD_BUCKET", "SERVING_BUCKET"]
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

from gold_mrr import iceberg_io  # noqa: E402
from gold_mrr import run as mrr_run  # noqa: E402

reader = iceberg_io.SilverReader(spark, "glue_catalog")
writer = iceberg_io.MrrWriter(spark, "glue_catalog", location=lambda db, t: f"{WAREHOUSE}{db}/{t}")
mrr_run.run({"run_id": args["run_id"], "started_at": args["started_at"], "expected_silver_run_id": args["run_id"]},
            reader=reader, writer=writer)
job.commit()
