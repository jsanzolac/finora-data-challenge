"""Local Spark 3.5 session for the Glue job tests: PySpark 3.5.4 (Glue 5.0's
Spark), Iceberg 1.7 runtime jar, a Hadoop catalog named glue_catalog in a temp
warehouse. Skips when PySpark or the jar is not available."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ETL = Path(__file__).resolve().parents[1]
JAR = Path(os.environ.get("ICEBERG_JAR", "/tmp/finora_envs/jars/iceberg-spark-runtime-3.5_2.12-1.7.1.jar"))


def spark_session(warehouse: Path):
    pyspark = pytest.importorskip("pyspark")
    if not JAR.exists():
        pytest.skip(f"Iceberg runtime jar not found at {JAR}")
    os.environ["PYTHONPATH"] = os.pathsep.join([str(ETL), str(ETL / "tests"), os.environ.get("PYTHONPATH", "")])
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    from pyspark.sql import SparkSession

    return (SparkSession.builder.master("local[2]").appName("finora-glue-tests")
            .config("spark.jars", str(JAR))
            .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
            .config("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog")
            .config("spark.sql.catalog.glue_catalog.type", "hadoop")
            .config("spark.sql.catalog.glue_catalog.warehouse", str(warehouse))
            .config("spark.sql.shuffle.partitions", "4")
            .config("spark.sql.session.timeZone", "UTC")
            .config("spark.ui.enabled", "false")
            .config("spark.driver.memory", "3g")
            .getOrCreate()), pyspark
