"""Spark side of the silver build (Glue 5.0 / Spark 3.5): the Glue Data Quality
input frames, the per-customer lifecycle on executors, and the Iceberg writer.

No awsglue import here, so the same code runs in local PySpark tests; the Glue
job script supplies the EvaluateDataQuality call (glue_jobs/silver_build_job.py).
"""

from __future__ import annotations

import unicodedata
from typing import Callable

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

from common import dqdl, exactjson, schemas
from common.dqdl import Predicates
from silver_build.engine import Counter, DatasetInput, lifecycle, parse_rows

# evaluate(dataset, frame, ruleset_text) -> (row-level frame with source_line and
# DataQualityRulesFail, [rule outcome dicts])
Evaluate = Callable[[str, DataFrame, str], "tuple[DataFrame, list[dict]]"]


# --------------------------------------------------------------------------- #
# Glue Data Quality                                                           #
# --------------------------------------------------------------------------- #

def dq_frame(spark: SparkSession, ds: str, staging: bytes, cfg: dict) -> DataFrame:
    """The rows that pass stage A, as strings exactly as received, keyed by
    source_line. Industry also carries Industria in NFC for SQ-04."""
    cols = cfg["datasets"][ds]["columns"]
    rows, _ = parse_rows(ds, staging, cols, Counter())
    extra = ["Industria_nfc"] if ds == "industry" else []
    data = []
    for r in rows:
        if r.stage_a_failed:
            continue
        vals = [r.values[c] for c in cols]
        if extra:
            vals.append(unicodedata.normalize("NFC", r.values["Industria"]))
        data.append((r.source_line, *vals))
    schema = T.StructType([T.StructField("source_line", T.IntegerType(), False)] +
                          [T.StructField(c, T.StringType(), False) for c in cols + extra])
    return spark.createDataFrame(data, schema)


def evaluate_dq(spark: SparkSession, inputs: dict[str, DatasetInput | None], cfg: dict,
                evaluate: Evaluate, rulesets: dict[str, str] | None = None) -> tuple[Predicates, dict]:
    """Run each dataset's DQDL ruleset with row-level outcomes and turn them
    into the engine's Predicates. Returns (predicates, report section)."""
    failed: dict[str, dict[str, set[int]]] = {}
    report: dict[str, dict] = {}
    for ds in cfg["dataset_order"]:
        text = (rulesets or {}).get(ds) or dqdl.ruleset(cfg, ds)
        inp = inputs.get(ds)
        frame = dq_frame(spark, ds, inp.staging if inp else b"", cfg)
        n = frame.count()
        if n == 0:  # nothing to evaluate: every check is vacuously passed
            failed[ds] = {c.key: set() for c in dqdl.checks(cfg)[ds]}
            report[ds] = {"ruleset": dqdl.ruleset_name(ds), "rows_evaluated": 0, "rule_outcomes": []}
            continue
        row_level, outcomes = evaluate(ds, frame, text)
        got = [(r["source_line"], list(r["DataQualityRulesFail"] or []))
               for r in row_level.select("source_line", "DataQualityRulesFail").collect()]
        if len(got) != n or len({g[0] for g in got}) != n:
            raise RuntimeError(f"Glue DQ returned {len(got)} row outcomes for {n} rows of {ds}")
        failed[ds] = dqdl.failed_lines(cfg, ds, got)
        report[ds] = {"ruleset": dqdl.ruleset_name(ds), "rows_evaluated": n,
                      "rows_failing_any": sum(1 for _, f in got if f),
                      "failed_by_check": {k: len(v) for k, v in failed[ds].items()},
                      "rule_outcomes": outcomes}
    return Predicates(failed), report


# --------------------------------------------------------------------------- #
# Lifecycle per customer on the executors                                     #
# --------------------------------------------------------------------------- #

def spark_lifecycle_map(spark: SparkSession, partitions: int = 8):
    """engine.lifecycle() per customer with groupBy().applyInPandas(). Cells and
    results cross the driver/executor boundary as exact-Decimal JSON."""

    def run(cells_by_c: dict, W: list[str], params: dict) -> dict:
        if not cells_by_c:
            return {}
        data = [(int(c), exactjson.dumps(cells)) for c, cells in cells_by_c.items()]
        df = spark.createDataFrame(data, "customer_id long, cells string").repartition(partitions, "customer_id")

        def per_customer(pdf):
            import pandas as pd

            out = [(int(c), exactjson.dumps(lifecycle(exactjson.loads(cj), W, params)))
                   for c, cj in zip(pdf["customer_id"], pdf["cells"])]
            return pd.DataFrame(out, columns=["customer_id", "life"])

        got = df.groupBy("customer_id").applyInPandas(per_customer, "customer_id long, life string").collect()
        return {int(r["customer_id"]): exactjson.loads(r["life"]) for r in got}

    return run


# --------------------------------------------------------------------------- #
# Iceberg                                                                     #
# --------------------------------------------------------------------------- #

def spark_type(t: str) -> T.DataType:
    if t.startswith("decimal("):
        p, s = t[8:-1].split(",")
        return T.DecimalType(int(p), int(s))
    return {"string": T.StringType(), "int": T.IntegerType(), "bigint": T.LongType(),
            "boolean": T.BooleanType(), "array<string>": T.ArrayType(T.StringType())}[t]


class IcebergWriter:
    """Full rebuild per run: one overwrite commit (one snapshot) per table,
    tagged with the run_id so the run is reproducible by time travel."""

    def __init__(self, spark: SparkSession, catalog: str = "glue_catalog",
                 location: Callable[[str, str], str] | None = None) -> None:
        self.spark, self.catalog, self.location = spark, catalog, location

    def fq(self, table: str) -> str:
        return f"{self.catalog}.{schemas.ICEBERG[table][0]}.{table}"

    def ensure(self, table: str) -> list[str]:
        """Create the table if needed, then evolve it to the declared schema.
        Returns the columns added (empty when the table already matches)."""
        db, cols, parts = schemas.ICEBERG[table]
        ddl = ", ".join(f"`{n}` {t}" for n, t in cols)
        part = f" PARTITIONED BY ({', '.join(f'`{p}`' for p in parts)})" if parts else ""
        loc = f" LOCATION '{self.location(db, table)}'" if self.location else ""
        self.spark.sql(f"CREATE TABLE IF NOT EXISTS {self.fq(table)} ({ddl}) USING iceberg{part}{loc} "
                       "TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd')")
        return self._evolve(table, cols)

    def _evolve(self, table: str, cols: list[tuple[str, str]]) -> list[str]:
        """Schema evolution for a full rebuild: add each declared column the
        existing table lacks, nullable and at its declared position. An Iceberg
        column addition is metadata only (no data rewrite, no new snapshot);
        earlier snapshots keep their own schema for time travel. Any other drift
        (an undeclared column or a changed type) is our defect: fail before any
        data is written."""
        fq = self.fq(table)
        have = {f.name: f.dataType for f in self.spark.table(fq).schema.fields}
        declared = {n for n, _ in cols}
        undeclared = sorted(set(have) - declared)
        changed = sorted(n for n, t in cols if n in have and have[n] != spark_type(t))
        if undeclared or changed:
            raise RuntimeError(f"{fq} schema drift: undeclared columns {undeclared}, changed types {changed}")
        added = []
        for i, (n, t) in enumerate(cols):
            if n in have:
                continue
            pos = f"AFTER `{cols[i - 1][0]}`" if i else "FIRST"
            self.spark.sql(f"ALTER TABLE {fq} ADD COLUMN `{n}` {t} {pos}")
            added.append(n)
        return added

    def _current(self, table: str):
        got = self.spark.sql(f"SELECT snapshot_id FROM {self.fq(table)}.refs WHERE name = 'main'").collect()
        return int(got[0]["snapshot_id"]) if got else None

    def write(self, table: str, rows: list[dict], run_id: str) -> dict:
        _, cols, _ = schemas.ICEBERG[table]
        schema = T.StructType([T.StructField(n, spark_type(t), True) for n, t in cols])
        data = [tuple(r.get(n) for n, _ in cols) for r in rows]
        # No Spark task may be empty: Iceberg's writer deletes the empty file an
        # empty task leaves, and the job role has no s3:DeleteObject (by design,
        # the ETL cannot destroy lake files). One task per table is plenty here.
        if data:
            df = self.spark.createDataFrame(data, schema).coalesce(1)
        else:
            df = self.spark.createDataFrame(self.spark.sparkContext.emptyRDD(), schema)
        self.ensure(table)
        before = self._current(table)
        df.writeTo(self.fq(table)).overwrite(F.lit(True))
        sid = self._current(table)
        if sid is not None:
            self.spark.sql(f"ALTER TABLE {self.fq(table)} CREATE OR REPLACE TAG `{run_id}` AS OF VERSION {sid}")
        return {"table": self.fq(table).split(".", 1)[1], "rows": len(rows), "snapshot_id": sid,
                "new_snapshot": sid is not None and sid != before, "tag": run_id if sid is not None else None}


def write_tables(writer: IcebergWriter, res: dict, store: dict, run_id: str) -> dict:
    """Silver tables, then the DQ store (findings, quarantine). Returns the
    per-table commit record for the run report.

    Every table's schema is created or evolved first, before the first data
    commit, so a schema defect fails the run with no table at the new run."""
    tables = list(res["silver"]) + ["findings", "excluded_rows"]
    added = {t: writer.ensure(t) for t in tables}
    out = {}
    for table, rows in res["silver"].items():
        out[table] = writer.write(table, rows, run_id)
    findings = [{**r, "hr_sensitive": hr} for hr in (False, True) for r in store["findings"][hr]]
    out["findings"] = writer.write("findings", findings, run_id)
    excluded = [{**r, "hr_sensitive": hr} for ds, parts in store["excluded"].items()
                for hr in (False, True) for r in parts[hr]]
    out["excluded_rows"] = writer.write("excluded_rows", excluded, run_id)
    for t in tables:
        out[t]["columns_added"] = added[t]
    return out
