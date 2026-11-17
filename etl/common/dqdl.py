"""Glue Data Quality (DQDL) rulesets generated from the approved rules config,
and the arbiter that feeds their row-level outcomes to the engine.

Which rules run in Glue DQ: every row rule whose test is a pure function of the
row's cells (regex grammars, allowed values) or of the dataset's rows
(uniqueness), evaluated on the rows that passed stage A. Stage A itself
(CDO-01 bytes are valid UTF-8, SQ-02 empty record, SQ-01 field count) decides
what a row and its cells are, so it stays in the byte-level parser; findings,
lifecycle and business rules stay in Spark/Python.

Every DQDL rule carries its approved_data_rules.md id in a label and a comment,
so Glue DQ results in the console map to the catalog. Patterns come from the
rule params (`\\.` and `\\$` are written as `[.]` and `[$]`, the same regex
without backslashes, so no DQDL escaping is involved).
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

RULESET_PREFIX = "finora-dl-"
LABELS = True  # DQDL rule labels (Glue ETL); set False if a runtime rejects them


@dataclass(frozen=True)
class Check:
    dataset: str
    rule_id: str
    check: str          # short name, unique per dataset
    columns: tuple      # source columns the check reads
    dqdl: str           # the rule, without labels

    @property
    def key(self) -> str:
        return f"{self.rule_id}:{self.check}"


def _safe(pattern: str) -> str:
    out = pattern.replace("\\.", "[.]").replace("\\$", "[$]")
    if "\\" in out or '"' in out:
        raise ValueError(f"pattern needs DQDL escaping: {pattern!r}")
    return out


def _q(value: str) -> str:
    if '"' in value or "\\" in value:
        raise ValueError(f"value needs DQDL escaping: {value!r}")
    return f'"{value}"'


def precision_pattern(max_int: int, max_frac: int) -> str:
    """CDO-05 for a G-AMOUNT string: after dropping leading integer zeros and
    trailing fractional zeros, at most max_int integer and max_frac fractional
    digits (the engine's _precision_ok)."""
    return f"^-?0*([1-9][0-9]{{0,{max_int - 1}}})?([.][0-9]{{0,{max_frac}}}0*)?$"


def month_end_sql(month_pattern: str) -> str:
    """SQ-06: G-TX-MONTH, a real date, the last day of its month, year >= 1.
    Rows the query returns pass (Glue DQ row-level CustomSql)."""
    p = _safe(month_pattern)
    y, m, d = ("cast(split(month, '/')[2] as int)", "cast(split(month, '/')[0] as int)",
               "cast(split(month, '/')[1] as int)")
    return (f"select source_line from primary where month rlike '{p}' and {y} >= 1 "
            f"and dayofmonth(last_day(make_date({y}, {m}, 1))) = {d}")


def checks(cfg: dict) -> dict[str, list[Check]]:
    r = cfg["rules_by_id"]
    amt = r["CDO-05"]["params"]["amount"]
    max_int, max_frac = amt["precision"] - amt["scale"], amt["scale"]
    domain = sorted(unicodedata.normalize("NFC", k) for k in r["SQ-04"]["params"]["domain"])
    out = {
        "transactions": [
            Check("transactions", "SQ-05", "id_grammar", ("ID",),
                  f'ColumnValues "ID" matches {_q(_safe(r["SQ-05"]["params"]["id_pattern"]))}'),
            Check("transactions", "SQ-06", "month_end_date", ("month",),
                  f'CustomSql {_q(month_end_sql(r["SQ-06"]["params"]["month_pattern"]))}'),
            Check("transactions", "SQ-07a", "amount_grammar", ("amount",),
                  f'ColumnValues "amount" matches {_q(_safe(r["SQ-07a"]["params"]["amount_pattern"]))}'),
            Check("transactions", "CDO-05", "amount_precision", ("amount",),
                  f'ColumnValues "amount" matches {_q(precision_pattern(max_int, max_frac))}'),
            Check("transactions", "SQ-05", "key_unique", ("ID", "month"), 'IsPrimaryKey "ID" "month"'),
            Check("transactions", "SQ-07b", "amount_not_negative", ("amount",),
                  'ColumnValues "amount" not matches "^-.*[1-9].*$"'),
        ],
        "industry": [
            Check("industry", "SQ-03", "id_grammar", ("ID",),
                  f'ColumnValues "ID" matches {_q(_safe(r["SQ-03"]["params"]["id_pattern"]))}'),
            Check("industry", "SQ-03", "id_unique", ("ID",), 'IsUnique "ID"'),
            Check("industry", "SQ-04", "industry_domain", ("Industria",),
                  'ColumnValues "Industria_nfc" in [' + ", ".join(_q(v) for v in domain) + "]"),
        ],
        "sm_spend": [
            Check("sm_spend", "SQ-09a", "month_grammar", ("Month",),
                  f'ColumnValues "Month" matches {_q(_safe(r["SQ-09a"]["params"]["month_pattern"]))}'),
            Check("sm_spend", "SQ-09a", "month_unique", ("Month",), 'IsUnique "Month"'),
        ] + [
            Check("sm_spend", "SQ-10", c, (c,), f'ColumnValues "{c}" matches {_q(_safe(r["SQ-10"]["params"]["cell_pattern"]))}')
            for c in r["SQ-10"]["params"]["spend_columns"]
        ],
    }
    return out


def ruleset_name(ds: str) -> str:
    return f"{RULESET_PREFIX}{ds}"


def _labelled(c: Check) -> str:
    if not LABELS:
        return c.dqdl
    return f'{c.dqdl} labels=["rule_id"="{c.rule_id}", "check"="{c.check}"]'


def ruleset(cfg: dict, ds: str) -> str:
    lines = [f"# {ruleset_name(ds)}: Glue Data Quality rules for {ds}, generated from etl/config/dl_rules.json",
             f"# rules_version {cfg['rules_version']}. Evaluated on the rows that pass stage A (CDO-01, SQ-02, SQ-01).",
             "Rules = ["]
    cs = checks(cfg)[ds]
    for i, c in enumerate(cs):
        lines.append(f"    # {c.rule_id} {c.check}")
        lines.append(f"    {_labelled(c)}" + ("," if i < len(cs) - 1 else ""))
    lines.append("]")
    return "\n".join(lines) + "\n"


_LABELS_RE = re.compile(r"\s*labels\s*=\s*\[.*\]\s*$", re.S)


def _norm(rule_text: str) -> str:
    return re.sub(r"\s+", "", _LABELS_RE.sub("", rule_text))


def index(cfg: dict, ds: str) -> dict[str, Check]:
    return {_norm(c.dqdl): c for c in checks(cfg)[ds]}


def failed_lines(cfg: dict, ds: str, rows: list[tuple[int, list[str] | None]]) -> dict[str, set[int]]:
    """Row-level outcomes [(source_line, DataQualityRulesFail)] -> {check key: failed lines}.
    A failure string that maps to no generated rule is a defect: raise."""
    idx = index(cfg, ds)
    out: dict[str, set[int]] = {c.key: set() for c in idx.values()}
    unknown = set()
    for line, fails in rows:
        for f in fails or ():
            c = idx.get(_norm(f))
            if c is None:
                unknown.add(f)
                continue
            out[c.key].add(int(line))
    if unknown:
        raise ValueError(f"Glue DQ returned rules this pipeline did not generate: {sorted(unknown)[:3]}")
    return out


class Predicates:
    """Decides the row-level checks for the engine.

    Without outcomes (unit tests, the reference build) the engine's own
    predicate decides. With Glue DQ outcomes, the Glue DQ outcome decides and
    the engine's predicate is the shadow: every disagreement is recorded, and
    the job fails the run on any (a pipeline defect, never file content). On a
    disagreement the reference value is used so the build stays total; nothing
    from such a run is published.
    """

    def __init__(self, failed: dict[str, dict[str, set[int]]] | None = None) -> None:
        self.failed = failed
        self.mismatches: list[dict] = []
        self.consulted: dict[str, int] = defaultdict(int)

    @property
    def glue_dq(self) -> bool:
        return self.failed is not None

    def fails(self, ds: str, check: str, line: int, reference_fails: bool) -> bool:
        if self.failed is None:
            return reference_fails
        got = line in self.failed[ds][check]  # KeyError = a check Glue DQ did not run: a defect
        self.consulted[f"{ds}/{check}"] += 1
        if got != reference_fails:
            self.mismatches.append({"dataset": ds, "check": check, "source_line": line,
                                    "glue_dq_failed": got, "reference_failed": reference_fails})
            return reference_fails
        return got
