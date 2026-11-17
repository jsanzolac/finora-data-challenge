"""DQDL generation: every Glue DQ rule is named after its catalog id, and each
generated regex decides exactly like the engine's reference predicate."""

import calendar
import re
from pathlib import Path

import pytest

from common import config, dqdl
from silver_build import engine

ROOT = Path(__file__).resolve().parents[2]
D = Path(__file__).resolve().parent / "fixtures" / "dirty"


def corpus():
    vals = set()
    for f in list((ROOT / "data").glob("*.csv")) + list(D.glob("*.csv")):
        for line in f.read_bytes().decode("utf-8", "replace").splitlines():
            vals.update(line.lstrip("﻿").split(","))
    vals.update(["", " ", "0", "-0", "-0.000", "007", "1e3", "NaN", "+5", ".5", "5.", "1,5", "0.0000001",
                 "1234567", "123456.1234560000", "0001234.5", "-$0.016", "$-0.016", "$1234567.000",
                 "$1.00", "-$000001.000", "Cliente 01", "Cliente 0", "Cliente  1", "cliente 1",
                 "2/29/2024", "2/29/2023", "2/28/2023", "12/31/0000", "12/31/0001", "02/28/2023",
                 "4/31/2024", "4/30/2024", "13/31/2024", "2024-13", "2024-00", "2024-1", "Producción",
                 "Producción", "Tecnología", "Retail ", "1\n", "12٠"])
    return sorted(vals)


def ref_month_end(s: str) -> bool:
    m = engine.G_TX_MONTH.fullmatch(s)
    if not m:
        return False
    mo, day, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return yr >= 1 and calendar.monthrange(yr, mo)[1] == day


@pytest.fixture(scope="module")
def cfg():
    return config.load()


def test_rulesets_name_every_rule_after_its_catalog_id(cfg):
    want = {"transactions": {"SQ-05:id_grammar", "SQ-05:key_unique", "SQ-06:month_end_date", "SQ-07a:amount_grammar",
                             "CDO-05:amount_precision", "SQ-07b:amount_not_negative"},
            "industry": {"SQ-03:id_grammar", "SQ-03:id_unique", "SQ-04:industry_domain"},
            "sm_spend": {"SQ-09a:month_grammar", "SQ-09a:month_unique"} |
                        {f"SQ-10:{c}" for c in cfg["rules_by_id"]["SQ-10"]["params"]["spend_columns"]}}
    for ds, keys in want.items():
        cs = dqdl.checks(cfg)[ds]
        assert {c.key for c in cs} == keys
        text = dqdl.ruleset(cfg, ds)
        assert text.count("\n    # ") == len(cs) and dqdl.ruleset_name(ds) == f"finora-dl-{ds}"
        for c in cs:
            assert f'labels=["rule_id"="{c.rule_id}", "check"="{c.check}"]' in text
            assert c.rule_id in cfg["rules_by_id"]
        assert "\\" not in text  # no escaping ambiguity in DQDL strings
    assert sum(len(v) for v in dqdl.checks(cfg).values()) == 18


def test_regexes_decide_like_the_engine(cfg):
    cs = {c.key: c for ds in dqdl.checks(cfg).values() for c in ds}
    pat = {k: re.compile(re.search(r'matches "([^"]*)"', c.dqdl).group(1)) for k, c in cs.items()
           if " matches " in c.dqdl}
    # DQDL sees only rows that passed stage A, so no cell holds a C0 control
    # character (CDO-01); that is what makes "^...$" equal to fullmatch (a "$"
    # would otherwise match before a final "\n").
    for v in [v for v in corpus() if not any(ord(ch) < 0x20 for ch in v)]:
        assert bool(pat["SQ-05:id_grammar"].search(v)) == bool(engine.G_ID.fullmatch(v)), v
        assert bool(pat["SQ-03:id_grammar"].search(v)) == bool(engine.G_INDUSTRY_ID.fullmatch(v)), v
        assert bool(pat["SQ-07a:amount_grammar"].search(v)) == bool(engine.G_AMOUNT.fullmatch(v)), v
        assert bool(pat["SQ-09a:month_grammar"].search(v)) == bool(engine.G_SM_MONTH.fullmatch(v)), v
        assert bool(pat["SQ-10:Team"].search(v)) == bool(engine.G_SPEND.fullmatch(v)), v
        if engine.G_AMOUNT.fullmatch(v):  # CDO-05 and SQ-07b are evaluated on valid amounts only
            assert bool(pat["CDO-05:amount_precision"].search(v)) == engine._precision_ok(v, 6, 6), v
            from decimal import Decimal
            assert bool(pat["SQ-07b:amount_not_negative"].search(v)) == (Decimal(v) < 0), v


def test_month_end_sql_matches_the_engine(cfg):
    pyspark = pytest.importorskip("pyspark")  # noqa: F841
    from spark_support import spark_session
    import tempfile

    spark, _ = spark_session(Path(tempfile.mkdtemp()))
    vals = corpus()
    df = spark.createDataFrame([(i, v) for i, v in enumerate(vals)], "source_line int, month string")
    df.createOrReplaceTempView("primary")
    sql = dqdl.month_end_sql(cfg["rules_by_id"]["SQ-06"]["params"]["month_pattern"])
    passing = {r[0] for r in spark.sql(sql).collect()}
    for i, v in enumerate(vals):
        assert (i in passing) == ref_month_end(v), v


def test_failed_lines_maps_outcomes_with_or_without_labels(cfg):
    cs = dqdl.checks(cfg)["industry"]
    rows = [(2, []), (3, [cs[0].dqdl]), (4, [dqdl._labelled(cs[1]), "  " + cs[2].dqdl.replace(" ", "  ")])]
    got = dqdl.failed_lines(cfg, "industry", rows)
    assert got == {"SQ-03:id_grammar": {3}, "SQ-03:id_unique": {4}, "SQ-04:industry_domain": {4}}
    with pytest.raises(ValueError):
        dqdl.failed_lines(cfg, "industry", [(5, ['IsComplete "ID"'])])


def test_predicates_record_disagreements_and_keep_the_reference(cfg):
    p = dqdl.Predicates({"industry": {"SQ-03:id_grammar": {7}}})
    assert p.fails("industry", "SQ-03:id_grammar", 7, True) is True
    assert p.fails("industry", "SQ-03:id_grammar", 8, True) is True  # disagreement: reference kept
    assert p.mismatches == [{"dataset": "industry", "check": "SQ-03:id_grammar", "source_line": 8,
                             "glue_dq_failed": False, "reference_failed": True}]
    with pytest.raises(KeyError):
        p.fails("industry", "SQ-03:id_unique", 7, False)
    assert dqdl.Predicates().fails("x", "y", 1, True) is True
