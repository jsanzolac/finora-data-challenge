"""Spark side of the gold MRR build (Glue 5.0 / Spark 3.5, Iceberg 1.7).

Same write-audit-publish discipline as the acquisition gold job
(etl/gold_build/spark_io.py), but self-contained and parametrized by the MRR
schemas, so this job never imports, writes or changes an acquisition table:

  1. every MRR table: CREATE OR REPLACE BRANCH audit_<run_id> from main, one
     overwrite commit on that branch;
  2. audit: read every branch back and compare it with what the engine built
     (row count and a digest of every row);
  3. publish: fast-forward main to the branch for every table (the status
     table last), tag the snapshot <run_id>, drop the branch.

A failure before step 3 leaves main untouched on every MRR table. Reads use
plain scans (no shuffles). No awsglue import, so local tests run the same code.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

from gold_mrr import schemas

RUN_ID = re.compile(r"r[0-9]{8}T[0-9]{6}Z")


def spark_type(t: str) -> T.DataType:
    if t.startswith("decimal("):
        p, s = t[8:-1].split(",")
        return T.DecimalType(int(p), int(s))
    return {"string": T.StringType(), "int": T.IntegerType(), "bigint": T.LongType(), "boolean": T.BooleanType(),
            "date": T.DateType(), "timestamp": T.TimestampType()}[t]


def check_id(run_id: str) -> str:
    if not RUN_ID.fullmatch(run_id or ""):
        raise ValueError(f"not a run id: {run_id!r}")
    return run_id


def canon(v, t: str):
    if v is None:
        return None
    if t.startswith("decimal("):
        s = int(t[8:-1].split(",")[1])
        return str(Decimal(v).quantize(Decimal(1).scaleb(-s)))
    if t == "timestamp":
        return round(v.timestamp() * 1_000_000)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def digest(rows: list[dict], cols: list[tuple[str, str]]) -> str:
    lines = sorted(repr(tuple(canon(r.get(c), t) for c, t in cols)) for r in rows)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


class SilverReader:
    """Reads the silver tables the MRR model needs, at a succeeded run's tag."""

    def __init__(self, spark: SparkSession, catalog: str = "glue_catalog", db: str = "finora_silver") -> None:
        self.spark, self.catalog, self.db = spark, catalog, db

    def fq(self, table: str) -> str:
        return f"{self.catalog}.{self.db}.{table}"

    def tag_snapshot(self, table: str, tag: str) -> int | None:
        got = self.spark.sql(f"SELECT snapshot_id FROM {self.fq(table)}.refs "
                             f"WHERE name = '{check_id(tag)}' AND type = 'TAG'").collect()
        return int(got[0][0]) if got else None

    def read(self, table: str, tag: str) -> list[dict]:
        df = self.spark.sql(f"SELECT * FROM {self.fq(table)} VERSION AS OF '{check_id(tag)}'")
        return [r.asDict() for r in df.collect()]

    def read_all(self, tag: str) -> tuple[dict[str, list[dict]], dict[str, int]]:
        snaps = {}
        for t in schemas.SILVER_INPUTS:
            sid = self.tag_snapshot(t, tag)
            if sid is None:
                raise RuntimeError(f"silver table {t} has no tag {tag}")
            snaps[t] = sid
        return {t: self.read(t, tag) for t in schemas.SILVER_INPUTS}, snaps


class MrrWriter:
    def __init__(self, spark: SparkSession, catalog: str = "glue_catalog", location=None, db: str = schemas.DB) -> None:
        self.spark, self.catalog, self.location, self.db = spark, catalog, location, db

    def fq(self, table: str) -> str:
        if table not in schemas.COLUMNS:
            raise PermissionError(f"{table} is not an MRR table; the MRR job writes only its own tables")
        return f"{self.catalog}.{self.db}.{table}"

    def ensure(self, table: str) -> list[str]:
        cols = schemas.COLUMNS[table]
        parts = schemas.PARTITIONS.get(table, [])
        props = {"format-version": "2", "write.parquet.compression-codec": "zstd"}
        ddl = ", ".join(f"`{n}` {t}" for n, t in cols)
        part = f" PARTITIONED BY ({', '.join(f'`{p}`' for p in parts)})" if parts else ""
        loc = f" LOCATION '{self.location(self.db, table)}'" if self.location else ""
        tp = ", ".join(f"'{k}'='{v}'" for k, v in props.items())
        self.spark.sql(f"CREATE TABLE IF NOT EXISTS {self.fq(table)} ({ddl}) USING iceberg{part}{loc} "
                       f"TBLPROPERTIES ({tp})")
        have = {f.name: f.dataType for f in self.spark.table(self.fq(table)).schema.fields}
        undeclared = sorted(set(have) - {n for n, _ in cols})
        changed = sorted(n for n, t in cols if n in have and have[n] != spark_type(t))
        if undeclared or changed:
            raise RuntimeError(f"{self.fq(table)} schema drift: undeclared {undeclared}, changed types {changed}")
        added = []
        for i, (n, t) in enumerate(cols):
            if n not in have:
                pos = f"AFTER `{cols[i - 1][0]}`" if i else "FIRST"
                self.spark.sql(f"ALTER TABLE {self.fq(table)} ADD COLUMN `{n}` {t} {pos}")
                added.append(n)
        return added

    def ref(self, table: str, name: str = "main") -> int | None:
        got = self.spark.sql(f"SELECT snapshot_id FROM {self.fq(table)}.refs WHERE name = '{name}'").collect()
        return int(got[0][0]) if got else None

    def frame(self, table: str, rows: list[dict]):
        cols = schemas.COLUMNS[table]
        schema = T.StructType([T.StructField(n, spark_type(t), True) for n, t in cols])
        data = [tuple(r.get(n) for n, _ in cols) for r in rows]
        # No empty Spark task: Iceberg deletes the empty file an empty task leaves and the
        # role has no s3:DeleteObject (as in silver and acquisition gold). One task per table.
        if data:
            return self.spark.createDataFrame(data, schema).coalesce(1)
        return self.spark.createDataFrame(self.spark.sparkContext.emptyRDD(), schema)

    @staticmethod
    def branch(run_id: str) -> str:
        return f"audit_{check_id(run_id)}"

    def stage(self, table: str, rows: list[dict], run_id: str) -> int:
        b = self.branch(run_id)
        self.spark.sql(f"ALTER TABLE {self.fq(table)} CREATE OR REPLACE BRANCH `{b}`")
        self.frame(table, rows).writeTo(f"{self.fq(table)}.branch_{b}").overwrite(F.lit(True))
        return self.ref(table, b)

    def read_ref(self, table: str, ref: str | int) -> list[dict]:
        v = f"'{ref}'" if isinstance(ref, str) else str(int(ref))
        return [r.asDict() for r in self.spark.sql(f"SELECT * FROM {self.fq(table)} VERSION AS OF {v}").collect()]

    def audit(self, table: str, rows: list[dict], run_id: str) -> dict:
        got = self.read_ref(table, self.branch(run_id))
        cols = schemas.COLUMNS[table]
        ok = len(got) == len(rows) and digest(got, cols) == digest(rows, cols)
        return {"table": table, "rows": len(got), "digest_match": ok, "passed": ok}

    def publish(self, table: str, run_id: str) -> dict:
        b = self.branch(run_id)
        before = self.ref(table)
        self.spark.sql(f"CALL {self.catalog}.system.fast_forward('{self.db}.{table}', 'main', '{b}')").collect()
        sid = self.ref(table)
        self.spark.sql(f"ALTER TABLE {self.fq(table)} CREATE OR REPLACE TAG `{check_id(run_id)}` AS OF VERSION {sid}")
        self.spark.sql(f"ALTER TABLE {self.fq(table)} DROP BRANCH IF EXISTS `{b}`")
        return {"table": f"{self.db}.{table}", "snapshot_id": sid, "previous_snapshot_id": before, "tag": run_id}


def write_audit_publish(writer: MrrWriter, tables: dict[str, list[dict]], run_id: str) -> dict:
    """All MRR tables staged, then all audited, then all published (the status table
    last, as the commit marker). Raises before any publish if a table fails its audit."""
    order = [t for t in schemas.ORDER if t != schemas.MARKER] + [schemas.MARKER]
    added = {t: writer.ensure(t) for t in order}
    staged = {t: writer.stage(t, tables[t], run_id) for t in order}
    audits = {t: writer.audit(t, tables[t], run_id) for t in order}
    bad = [t for t, a in audits.items() if not a["passed"]]
    if bad:
        raise RuntimeError(f"write-audit-publish: audit failed on {bad}; nothing published")
    published = {t: writer.publish(t, run_id) for t in order}
    return {t: {**published[t], "rows": audits[t]["rows"], "branch_snapshot_id": staged[t],
                "columns_added": added[t], "audit": audits[t]} for t in order}
