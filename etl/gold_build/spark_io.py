"""Spark side of the gold build (Glue 5.0 / Spark 3.5, Iceberg 1.7): read silver
at its run tag, read the user-owned rates table (never write it), and write the
job-owned gold tables with write-audit-publish (§10):

  1. every table: CREATE OR REPLACE BRANCH audit_<run_id> from main, one
     overwrite commit on that branch;
  2. audit: read every branch back and compare it with what the engine built
     (row count and a digest of every row), plus the §5.8 metrics properties;
  3. publish: fast-forward main to the branch for every table
     (gold_build_status last), tag the snapshot <run_id>, drop the branch.

A failure before step 3 leaves main untouched on every table: the previous
gold build stays live. No awsglue import, so the same code runs in local tests.
Reads use plain scans and Python-side aggregation (no shuffles).
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

from gold_build import schemas

RUN_ID = re.compile(r"r[0-9]{8}T[0-9]{6}Z")
SILVER_TABLES = ("transactions", "industry", "sm_spend", "customer", "customer_month", "month_control",
                 "source_status")


def spark_type(t: str) -> T.DataType:
    if t.startswith("decimal("):
        p, s = t[8:-1].split(",")
        return T.DecimalType(int(p), int(s))
    return {"string": T.StringType(), "int": T.IntegerType(), "bigint": T.LongType(), "boolean": T.BooleanType(),
            "date": T.DateType(), "timestamp": T.TimestampType(), "timestamp_ntz": T.TimestampNTZType()}[t]


def _check_id(run_id: str) -> str:
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
    def __init__(self, spark: SparkSession, catalog: str = "glue_catalog", db: str = "finora_silver") -> None:
        self.spark, self.catalog, self.db = spark, catalog, db

    def fq(self, table: str) -> str:
        return f"{self.catalog}.{self.db}.{table}"

    def tag_snapshot(self, table: str, tag: str) -> int | None:
        got = self.spark.sql(f"SELECT snapshot_id FROM {self.fq(table)}.refs "
                             f"WHERE name = '{_check_id(tag)}' AND type = 'TAG'").collect()
        return int(got[0][0]) if got else None

    def read(self, table: str, tag: str) -> list[dict]:
        df = self.spark.sql(f"SELECT * FROM {self.fq(table)} VERSION AS OF '{_check_id(tag)}'")
        return [r.asDict() for r in df.collect()]

    def read_all(self, tag: str) -> tuple[dict[str, list[dict]], dict[str, int]]:
        snaps = {}
        for t in SILVER_TABLES:
            sid = self.tag_snapshot(t, tag)
            if sid is None:
                raise RuntimeError(f"silver table {t} has no tag {tag}")
            snaps[t] = sid
        return {t: self.read(t, tag) for t in SILVER_TABLES}, snaps


class GoldWriter:
    def __init__(self, spark: SparkSession, catalog: str = "glue_catalog", location=None, db: str = schemas.DB) -> None:
        self.spark, self.catalog, self.location, self.db = spark, catalog, location, db

    def fq(self, table: str) -> str:
        return f"{self.catalog}.{self.db}.{table}"

    def exists(self, table: str) -> bool:
        try:
            return bool(self.spark.sql(f"SHOW TABLES IN {self.catalog}.{self.db} LIKE '{table}'").collect())
        except Exception as err:  # noqa: BLE001 -- a missing namespace means no table
            if "NamespaceNotFound" in type(err).__name__ or "not found" in str(err).lower():
                return False
            raise

    def ensure(self, table: str) -> list[str]:
        if table == schemas.RATE_TABLE:
            raise PermissionError("the gold job never creates or changes the user-owned rates table")
        cols = schemas.COLUMNS[table]
        parts = schemas.PARTITIONS.get(table, [])
        props = {"format-version": "2", "write.parquet.compression-codec": "zstd",
                 **schemas.EXTRA_PROPERTIES.get(table, {})}
        ddl = ", ".join(f"`{n}` {t}" for n, t in cols)
        part = f" PARTITIONED BY ({', '.join(f'`{p}`' for p in parts)})" if parts else ""
        loc = f" LOCATION '{self.location(self.db, table)}'" if self.location else ""
        tp = ", ".join(f"'{k}'='{v}'" for k, v in props.items())
        self.spark.sql(f"CREATE TABLE IF NOT EXISTS {self.fq(table)} ({ddl}) USING iceberg{part}{loc} "
                       f"TBLPROPERTIES ({tp})")
        have = {f.name: f.dataType for f in self.spark.table(self.fq(table)).schema.fields}
        declared = {n for n, _ in cols}
        undeclared = sorted(set(have) - declared)
        changed = sorted(n for n, t in cols if n in have and have[n] != spark_type(t))
        if undeclared or changed:
            raise RuntimeError(f"{self.fq(table)} schema drift: undeclared {undeclared}, changed types {changed}")
        added = []
        for i, (n, t) in enumerate(cols):
            if n not in have:
                pos = f"AFTER `{cols[i - 1][0]}`" if i else "FIRST"
                self.spark.sql(f"ALTER TABLE {self.fq(table)} ADD COLUMN `{n}` {t} {pos}")
                added.append(n)
        missing = {k: v for k, v in schemas.EXTRA_PROPERTIES.get(table, {}).items()
                   if self.properties(table).get(k) != v}
        if missing:
            self.spark.sql(f"ALTER TABLE {self.fq(table)} SET TBLPROPERTIES "
                           f"({', '.join(f'{chr(39)}{k}{chr(39)}={chr(39)}{v}{chr(39)}' for k, v in missing.items())})")
        return added

    def properties(self, table: str) -> dict[str, str]:
        return {r["key"]: r["value"] for r in self.spark.sql(f"SHOW TBLPROPERTIES {self.fq(table)}").collect()}

    def ref(self, table: str, name: str = "main") -> int | None:
        got = self.spark.sql(f"SELECT snapshot_id FROM {self.fq(table)}.refs WHERE name = '{name}'").collect()
        return int(got[0][0]) if got else None

    def frame(self, table: str, rows: list[dict]):
        cols = schemas.COLUMNS[table]
        schema = T.StructType([T.StructField(n, spark_type(t), True) for n, t in cols])
        data = [tuple(r.get(n) for n, _ in cols) for r in rows]
        # No empty Spark task: Iceberg deletes the empty file an empty task leaves and
        # the job role has no s3:DeleteObject (as in silver). One task per table.
        if data:
            return self.spark.createDataFrame(data, schema).coalesce(1)
        return self.spark.createDataFrame(self.spark.sparkContext.emptyRDD(), schema)

    @staticmethod
    def branch(run_id: str) -> str:
        return f"audit_{_check_id(run_id)}"

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
        out = {"table": table, "rows": len(got), "digest_match": ok}
        if table in schemas.EXTRA_PROPERTIES:
            props = self.properties(table)
            out["metrics_properties"] = all(props.get(k) == v for k, v in schemas.EXTRA_PROPERTIES[table].items())
            ok = ok and out["metrics_properties"]
        out["passed"] = ok
        return out

    def publish(self, table: str, run_id: str) -> dict:
        b = self.branch(run_id)
        before = self.ref(table)
        ident = f"{self.db}.{table}"
        self.spark.sql(f"CALL {self.catalog}.system.fast_forward('{ident}', 'main', '{b}')").collect()
        sid = self.ref(table)
        self.spark.sql(f"ALTER TABLE {self.fq(table)} CREATE OR REPLACE TAG `{_check_id(run_id)}` AS OF VERSION {sid}")
        self.spark.sql(f"ALTER TABLE {self.fq(table)} DROP BRANCH IF EXISTS `{b}`")
        return {"table": f"{self.db}.{table}", "snapshot_id": sid, "previous_snapshot_id": before, "tag": run_id}

    # ---- the rates table: read only
    def rate_rows(self, snapshot_id: int | None = None) -> tuple[list[dict], int | None]:
        if not self.exists(schemas.RATE_TABLE):
            raise RuntimeError("finora_gold.funnel_conversion_rate does not exist: run the deploy step "
                               "infra/gold_athena_ddl.py rate-table first")
        sid = snapshot_id if snapshot_id is not None else self.ref(schemas.RATE_TABLE)
        if sid is None:
            return [], None
        return self.read_ref(schemas.RATE_TABLE, int(sid)), sid

    def previous_status(self) -> dict | None:
        if not self.exists("gold_build_status") or self.ref("gold_build_status") is None:
            return None
        rows = self.read_ref("gold_build_status", self.ref("gold_build_status"))
        return rows[0] if rows else None


def write_audit_publish(writer: GoldWriter, tables: dict[str, list[dict]], run_id: str) -> dict:
    """All tables staged, then all audited, then all published (gold_build_status last).
    Raises before any publish if a table fails its audit."""
    order = [t for t in schemas.ORDER if t != "gold_build_status"] + ["gold_build_status"]
    added = {t: writer.ensure(t) for t in order}
    staged = {t: writer.stage(t, tables[t], run_id) for t in order}
    audits = {t: writer.audit(t, tables[t], run_id) for t in order}
    bad = [t for t, a in audits.items() if not a["passed"]]
    if bad:
        raise RuntimeError(f"write-audit-publish: audit failed on {bad}; nothing published")
    published = {t: writer.publish(t, run_id) for t in order}
    return {t: {**published[t], "rows": audits[t]["rows"], "branch_snapshot_id": staged[t],
                "columns_added": added[t], "audit": audits[t]} for t in order}
