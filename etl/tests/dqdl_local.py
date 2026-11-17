"""A local stand-in for Glue Data Quality's EvaluateDataQuality.process_rows,
for the DQDL subset that common/dqdl.py generates. Glue DQ does not run outside
the Glue runtime; on AWS the real service evaluates the same rulesets and the
engine's reference predicates shadow it (any disagreement fails the run).

Supported: ColumnValues "c" matches|not matches "re", ColumnValues "c" in [...],
IsUnique "c", IsPrimaryKey "a" "b" ..., CustomSql "select source_line from primary ...".
Regexes run as Spark rlike (Java regex), as in Glue.
"""

from __future__ import annotations

import re

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

_RULE = re.compile(r'^(?P<body>.*?)(\s+labels=\[.*\])?,?$')
_STR = re.compile(r'"([^"]*)"')


def parse(ruleset: str) -> list[str]:
    body = ruleset[ruleset.index("Rules = [") + len("Rules = ["):ruleset.rindex("]")]
    out = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(_RULE.match(line).group("body").strip())
    return out


def _pass_col(frame: DataFrame, rule: str):
    spark = frame.sparkSession
    if rule.startswith("ColumnValues "):
        col, rest = _STR.match(rule[len("ColumnValues "):]).group(1), rule[len("ColumnValues "):]
        rest = rest[len(col) + 2:].strip()
        if rest.startswith("not matches "):
            return ~F.coalesce(F.col(col).rlike(_STR.search(rest).group(1)), F.lit(False))
        if rest.startswith("matches "):
            return F.coalesce(F.col(col).rlike(_STR.search(rest).group(1)), F.lit(False))
        if rest.startswith("in ["):
            return F.coalesce(F.col(col).isin(_STR.findall(rest)), F.lit(False))
    if rule.startswith("IsUnique ") or rule.startswith("IsPrimaryKey "):
        cols = _STR.findall(rule)
        n = F.count(F.lit(1)).over(Window.partitionBy(*cols))
        ok = n == 1
        for c in cols:
            ok = ok & F.col(c).isNotNull()
        return ok
    if rule.startswith("CustomSql "):
        sql = _STR.match(rule[len("CustomSql "):]).group(1)
        frame.createOrReplaceTempView("primary")
        passing = [r[0] for r in spark.sql(sql).collect()]
        return F.col("source_line").isin(passing)
    raise ValueError(f"unsupported DQDL rule in the local stand-in: {rule}")


def evaluate(ds: str, frame: DataFrame, ruleset: str):
    rules = parse(ruleset)
    cols = []
    for i, rule in enumerate(rules):
        cols.append(F.when(_pass_col(frame, rule), F.lit(None)).otherwise(F.lit(rule)).alias(f"_r{i}"))
    out = frame.select("source_line", *cols)
    fails = F.filter(F.array(*[F.col(f"_r{i}") for i in range(len(rules))]), lambda x: x.isNotNull())
    row_level = out.select("source_line", fails.alias("DataQualityRulesFail"))
    outcomes = []
    for i, rule in enumerate(rules):
        n_fail = out.filter(F.col(f"_r{i}").isNotNull()).count()
        outcomes.append({"Rule": rule, "Outcome": "Passed" if n_fail == 0 else "Failed", "failed_rows": n_fail})
    return row_level, outcomes
