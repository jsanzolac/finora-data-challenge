"""Shared fixtures for the gold tests: the golden gold build on data/*.csv, a
synthetic lake for the §14.3 edge cases, rate-table rows and local Spark views."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

from golden_helpers import inputs_from, run
from gold_build import ddl, engine, gconfig, schemas
from silver_build.engine import build as silver_build
from common import config

SILVER_RUN = "r20261117T150932Z"
GOLD_RUN = "r20261117T160000Z"
BUILT = datetime(2026, 11, 17, 16, 0, tzinfo=timezone.utc)
SEED_TS = datetime(2026, 11, 17, 16, 0)
RATE_COLS = [(n, "timestamp_ntz" if t == "timestamp" else t) for n, t in schemas.RATE_COLUMNS]


def meta(rate=None, run_id=GOLD_RUN, silver_run_id=SILVER_RUN):
    g = gconfig.load()
    return {"run_id": run_id, "silver_run_id": silver_run_id, "built_at": BUILT,
            "gold_model_version": g["gold_model_version"], "rate": rate or {}}


@lru_cache(maxsize=1)
def golden_silver():
    res, _ = run(run_id=SILVER_RUN)
    return res


@lru_cache(maxsize=1)
def golden_gold():
    return engine.build(golden_silver()["silver"], gconfig.load(), meta())


def seed(ts=SEED_TS) -> list[dict]:
    return [dict(r, rate=Decimal(r["rate"]), changed_at=ts) for r in ddl.seed_rows(gconfig.load())]


def scenario(sid, label, rates: dict | None = None, ts=SEED_TS, by="t.user", reason="test") -> list[dict]:
    out = []
    for r in ddl.seed_rows(gconfig.load()):
        rate = Decimal((rates or {}).get(r["from_stage_code"], r["rate"]))
        out.append(dict(r, scenario_id=sid, scenario_label=label, rate=rate, changed_at=ts, changed_by=by,
                        change_reason=reason))
    return out


# --------------------------------------------------------------------------- #
# Synthetic lake (§14.3)                                                      #
# --------------------------------------------------------------------------- #
MONTHS = ["2022-01", "2022-02", "2022-03", "2022-04", "2022-05", "2022-06", "2022-07", "2022-08"]
END = {"2022-01": "1/31/2022", "2022-02": "2/28/2022", "2022-03": "3/31/2022", "2022-04": "4/30/2022",
       "2022-05": "5/31/2022", "2022-06": "6/30/2022", "2022-07": "7/31/2022", "2022-08": "8/31/2022"}
# customer -> amounts per month (None = the row is malformed: excluded, a hole)
SYN_TX = {
    1: ["5", "5", "5", "5", "5", "5", "5", "5"],          # left (paying at the window start)
    2: ["3", "3", "3", "3", "3", "3", "3", "3"],          # left
    3: ["0", "4", "4", "4", "4", "4", "4", "4"],          # Won 2022-02
    4: ["0", "6", "6", "6", "6", "6", "6", "6"],          # Won 2022-02
    5: ["0", "0", "2", "2", "2", "2", "2", "2"],          # Won 2022-03 (the tripwire month)
    6: ["0", "0", "0", "0", "7", "7", "7", "7"],          # Won 2022-05 (no S&M line)
    7: ["0", "0", "0", "0", "0", "3", "3", None],         # Won 2022-06; hole in 2022-08
    8: ["0", "0", "0", "0", "0", "0", None, "4"],         # hole in its first-payment month: cohort unknown 2022-08
    9: ["0", "0", "0", "0", "0", "5", "5", "5"],          # Won 2022-06
    10: ["0", "0", "0", "0", "0", "0", "2", "2"],         # Won 2022-07
    11: ["0", "0", "0", "0", "0", "0", "0", "0"],         # never paid
}
SYN_IND = {1: "Restaurantes", 2: "Retail", 3: "Restaurantes", 4: "Salud", 5: "Retail", 6: "Restaurantes",
           7: "Retail", 8: "Producción", 9: "Retail", 10: "Tecnología", 11: "Restaurantes"}
SM_NORMAL, SM_TRIP = "$0.001", "$1.000"   # 7 x 100,000 = 700,000 per month; tripwire month 700,000,000


def synthetic_csvs(sm_missing=("2022-05",), trip=("2022-03",)) -> dict[str, bytes]:
    tx = ["﻿ID,month,amount"]
    for c, amts in SYN_TX.items():
        for m, a in zip(MONTHS, amts):
            tx.append(f"{c},{END[m]},{'bad' if a is None else a}")
    ind = ["﻿ID,Industria"] + [f"Cliente {c},{v}" for c, v in SYN_IND.items()]
    sm = ["﻿Month,PaidMedia,Travel,PublicidadNoWeb,Freelance,SoftwareTools,Team,PayrollExpenses"]
    for m in MONTHS:
        if m in sm_missing:
            continue
        v = SM_TRIP if m in trip else SM_NORMAL
        sm.append(",".join([m] + [v] * 7))
    return {"transactions": ("\n".join(tx) + "\n").encode(), "industry": ("\n".join(ind) + "\n").encode(),
            "sm_spend": ("\n".join(sm) + "\n").encode()}


def synthetic_silver(**kw):
    return silver_build(inputs_from(synthetic_csvs(**kw)), config.load(), SILVER_RUN, None)


def synthetic_gold(**kw):
    return engine.build(synthetic_silver(**kw)["silver"], gconfig.load(), meta())


# --------------------------------------------------------------------------- #
# Local Spark views                                                           #
# --------------------------------------------------------------------------- #
VIEW_TABLES = ("agg_acquisition_month", "dim_month", "gold_build_status", "dim_funnel_stage",
               "agg_won_month_industry", "agg_won_spend_lag_corr", "fact_sm_spend", "agg_acq_cohort_quality")


def register(spark, gold: dict, rate_rows: list[dict]) -> None:
    from pyspark.sql import types as T

    from gold_build import spark_io

    w = spark_io.GoldWriter(spark, "glue_catalog")
    for t in VIEW_TABLES:
        w.frame(t, gold["tables"][t]).createOrReplaceTempView(t)
    sch = T.StructType([T.StructField(n, spark_io.spark_type(t)) for n, t in RATE_COLS])
    spark.createDataFrame([tuple(r.get(n) for n, _ in RATE_COLS) for r in rate_rows], sch) \
        .createOrReplaceTempView(schemas.RATE_TABLE)
    for name, sql in ddl.views(gconfig.load(), "spark"):
        spark.sql(f"CREATE OR REPLACE TEMP VIEW {name} AS " + ddl.resolve(sql, lambda n: n))


def rows(spark, sql: str) -> list[dict]:
    return [r.asDict() for r in spark.sql(sql).collect()]
