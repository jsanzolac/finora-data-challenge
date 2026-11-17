"""Build etl/config/gold_acquisition.yaml (+ .json) from docs/gold_acquisition_model.md (read only).

The CDO's spec is authoritative. This script copies its seeds verbatim from the
spec's tables (dim_industry §5.2, dim_spend_category §5.4, dim_funnel_stage
§5.5, the base-rate seed §6.1), checks that the parameters of §14.2 are the ones
the spec states, and adds the rounding rules and the column lineage that the
CDO-10 test (§8.12, GC-09) reads. `_gold_model_version` is the SHA-256 of the
generated YAML. Re-run it whenever the spec changes:

    python etl/config/build_gold_yaml.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "gold_acquisition_model.md"
OUT = Path(__file__).resolve().parent / "gold_acquisition.yaml"


def _section(md: str, start: str, end: str) -> str:
    i = md.index(start)
    j = md.index(end, i + len(start))
    return md[i:j]


def _rows(block: str) -> list[list[str]]:
    out = []
    for line in block.splitlines():
        if not line.startswith("| ") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        out.append(cells)
    return out


def _clean(v: str):
    v = v.replace("**", "").replace("`", "").strip()
    if v == "NULL":
        return None
    return v


def _bool(v: str) -> bool:
    v = _clean(v) or ""
    if v.startswith("true"):
        return True
    if v.startswith("false"):
        return False
    raise ValueError(f"not a boolean cell: {v!r}")


def _key(v: str) -> int:
    return int(_clean(v).replace("−", "-"))


def industries(md: str) -> list[dict]:
    rows = _rows(_section(md, "### 5.2 `dim_industry`", "### 5.3"))
    hdr = [_clean(c) for c in rows[0]]
    assert hdr == ["industry_key", "industry_code", "industry_label_es (as stored)", "industry_label_en",
                   "chart_label", "is_unknown_member"], hdr
    out = []
    for i, r in enumerate(rows[1:]):
        out.append({"industry_key": _key(r[0]), "industry_code": _clean(r[1]), "industry_label_es": _clean(r[2]),
                    "industry_label_en": _clean(r[3]), "chart_label": _clean(r[4]),
                    "is_unknown_member": _bool(r[5]), "sort_order": i + 1})
    assert [x["industry_key"] for x in out] == [1, 2, 3, 4, 5, 6, -1, -2]
    return out


def categories(md: str) -> list[dict]:
    rows = _rows(_section(md, "### 5.4 `dim_spend_category`", "### 5.5"))
    hdr = [_clean(c) for c in rows[0]]
    assert hdr == ["category_key", "category_code", "category_label_en", "spend_group", "channel_class",
                   "is_hr_sensitive"], hdr
    out = [{"category_key": _key(r[0]), "category_code": _clean(r[1]), "category_label_en": _clean(r[2]),
            "spend_group": _clean(r[3]), "channel_class": _clean(r[4]), "is_hr_sensitive": _bool(r[5])}
           for r in rows[1:]]
    assert [x["category_key"] for x in out] == [1, 2, 3, 4, 5, 6, 7, -2]
    return out


def stages(md: str) -> list[dict]:
    rows = _rows(_section(md, "### 5.5 `dim_funnel_stage`", "### 5.6"))
    hdr = [_clean(c) for c in rows[0]]
    assert hdr == ["stage_key", "stage_code", "stage_label", "next_stage_code", "is_observed", "basis"], hdr
    out = []
    prev_basis = None
    for r in rows[1:]:
        basis = _clean(r[5])
        if basis == "same":  # "same" in the spec repeats the row above
            basis = prev_basis
        prev_basis = basis
        out.append({"stage_key": _key(r[0]), "stage_code": _clean(r[1]), "stage_label": _clean(r[2]),
                    "next_stage_code": _clean(r[3]), "is_observed": _bool(r[4]), "basis": basis})
    codes = [s["stage_code"] for s in out]
    assert codes == ["NEW", "WORKING", "ENGAGED", "SQL", "DEMO", "PROPOSAL", "WON"], codes
    for a, b in zip(out, out[1:]):
        assert a["next_stage_code"] == b["stage_code"]
    return out


def base_rates(md: str, stage_rows: list[dict]) -> dict:
    sec = _section(md, "### 6.1 The table: `funnel_conversion_rate`", "### 6.2")
    rows = _rows(sec)
    hdr = next(r for r in rows if r[0] == "from → to")
    base = next(r for r in rows if _clean(r[0]) == "base")
    pairs = []
    for h, v in zip(hdr[1:7], base[1:7]):
        f, t = h.split("→")
        pairs.append({"from_stage_code": f.strip(), "to_stage_code": t.strip(), "rate": _clean(v)})
    expect = [(s["stage_code"], s["next_stage_code"]) for s in stage_rows if s["next_stage_code"]]
    assert [(p["from_stage_code"], p["to_stage_code"]) for p in pairs] == expect
    m = re.search(r"`changed_by` = `(\w+)`, and `change_reason` = `([^`]+)`", sec)
    assert m, "seed changed_by / change_reason not found in §6.1"
    pattern = re.search(r"`scenario_id` \| STRING \| `(\^[^`]+\$)`", sec).group(1)
    overall = _clean(base[7]).split(" ")[0]
    return {"scenario_id": "base", "scenario_label": "Base (user rates 2026-11-17)",
            "changed_by": m.group(1), "change_reason": m.group(2), "rates": pairs,
            "overall_rate": overall, "scenario_id_pattern": pattern}


def params(md: str) -> dict:
    sec = _section(md, "### 14.2 Gold config", "### 14.3")
    want = {"lags `[0,1,2,3]`": None, "α 0.05 two-sided": None, "`low_n` 10": None, "small cell 5": None,
            "`low_volume` 10": None, "regime boundary `2023-06`": None, "rate point 0.01": None}
    for w in want:
        if w not in sec:
            sys.exit(f"parameter text {w!r} not found in §14.2; update build_gold_yaml.py")
    return {"lags": [0, 1, 2, 3], "alpha_two_sided": "0.05", "low_n": 10, "small_cell": 5, "low_volume": 10,
            "regime_boundary": "2023-06", "rate_point": "0.01", "future_tolerance_minutes": 5,
            "label_max": 200, "reason_max": 500, "min_pairs": 3,
            # §16.2 decision levers
            "levers": {"definitions_version": "cdo-s16-2026-11-17", "run_rate_window": [1, 2, 3],
                       "paying_months": {"m6": 5, "m12": 11}, "low_n": 10, "small_cell": 5,
                       "value_change": [["pre_2023_06", "from_2023_06"]]}}


ROUNDING = {
    "mode": "HALF_UP",
    "revenue_native": "decimal(12,6)", "revenue_value": "decimal(18,2)",
    "spend_native": "decimal(12,3)", "spend_value": "decimal(18,0)",
    "averages_and_costs": "decimal(18,2)", "stage_counts": "decimal(38,6)",
    "rate_product": "decimal(38,12)", "correlation": "decimal(5,4)", "means_of_counts": "decimal(9,4)",
    "note": "Every stored figure is rounded once, HALF_UP, from unrounded operands (§2).",
}

# Column lineage for the CDO-10 test (§8.12, GC-09). For every gold object: the
# keys that define its grain, and the columns that are monetary measures derived
# from S&M spend. The test fails when an object has both a spend-money column
# and a customer, industry or cohort key in its grain.
SEGMENT_KEYS = ["customer_id", "industry_key", "industry_code", "cohort_month_key", "won_month_key", "scope_code"]
LINEAGE = {
    "dim_month": {"grain": ["month_key"], "spend_money": []},
    "dim_industry": {"grain": ["industry_key"], "spend_money": []},
    "dim_customer": {"grain": ["customer_id"], "spend_money": []},
    "dim_spend_category": {"grain": ["category_key"], "spend_money": []},
    "dim_funnel_stage": {"grain": ["stage_key"], "spend_money": []},
    "fact_acquisition": {"grain": ["customer_id"], "spend_money": []},
    "fact_customer_month_revenue": {"grain": ["customer_id", "month_key"], "spend_money": []},
    "fact_sm_spend": {"grain": ["month_key", "category_key"], "spend_money": ["spend", "spend_value"]},
    "agg_acquisition_month": {"grain": ["month_key"], "spend_money": [
        "spend_paid_media_value", "spend_travel_value", "spend_publicidad_no_web_value",
        "spend_software_tools_value", "spend_media_value", "spend_other_value", "spend_people_value",
        "spend_total_value"]},
    "agg_won_month_industry": {"grain": ["month_key", "industry_key"], "spend_money": []},
    "agg_industry_profile": {"grain": ["industry_key", "customer_scope"], "spend_money": []},
    "agg_won_spend_lag_corr": {"grain": ["won_definition", "scope_code", "spend_series", "lag_months", "method"],
                               "spend_money": [], "spend_statistic": ["r"]},
    "gold_build_status": {"grain": ["_run_id"], "spend_money": []},
    # §16 decision levers. Spend enters only at period grain (CDO-10 holds, GC-09 extended).
    "agg_acq_cohort_quality": {"grain": ["won_definition", "won_month_key", "industry_key"], "spend_money": []},
    "agg_acq_lever_period": {"grain": ["won_definition", "period_code"],
                             "spend_money": ["spend_total_value", "spend_per_month_value", "cost_per_won_value"]},
    "agg_acq_lever_industry": {"grain": ["won_definition", "period_code", "industry_key"], "spend_money": []},
    "agg_acq_value_change": {"grain": ["won_definition", "from_period_code", "to_period_code", "industry_key"],
                             "spend_money": []},
    "v_acq_cohort_half": {"grain": ["won_definition", "cohort_half"], "spend_money": []},
    "funnel_conversion_rate": {"grain": ["scenario_id", "from_stage_code", "changed_at"], "spend_money": []},
    "v_funnel_rate_current": {"grain": ["scenario_id", "from_stage_code"], "spend_money": []},
    "v_funnel_scenario_status": {"grain": ["scenario_id"], "spend_money": []},
    "v_funnel_month": {"grain": ["scenario_id", "won_definition", "month_key", "stage_code"],
                       "spend_money": ["spend_total_value", "cost_per_unit_value"]},
    "v_funnel_period": {"grain": ["scenario_id", "won_definition", "period_type", "period_id", "stage_code"],
                        "spend_money": ["spend_total_value", "spend_per_month_value", "cost_per_unit_value"]},
    "v_funnel_scenario_compare": {"grain": ["scenario_id", "won_definition", "period_type", "period_id"],
                                  "spend_money": ["spend_total_value", "cost_per_won_implied_value"]},
    "v_funnel_rate_sensitivity": {"grain": ["scenario_id", "won_definition", "from_stage_code"], "spend_money": []},
    "v_acquisition_month": {"grain": ["month_key"], "spend_money": [
        "spend_paid_media_value", "spend_travel_value", "spend_publicidad_no_web_value",
        "spend_software_tools_value", "spend_people_value", "spend_total_value"]},
    "v_acquisition_month_finance": {"grain": ["month_key"], "spend_money": [
        "spend_paid_media_value", "spend_travel_value", "spend_publicidad_no_web_value",
        "spend_software_tools_value", "spend_people_value", "spend_total_value", "spend_freelance_value",
        "spend_team_value", "spend_payroll_expenses_value"]},
    "v_corr_signal_summary": {"grain": ["method", "won_definition", "scope_type"], "spend_money": []},
    "v_sm_spend_shared": {"grain": ["month_key", "category_key"], "spend_money": ["spend", "spend_value"]},
}


def build() -> dict:
    md = DOC.read_text(encoding="utf-8")
    st = stages(md)
    return {
        "version": 1,
        "model_doc": "docs/gold_acquisition_model.md",
        "database": "finora_gold",
        "won_definitions": ["first_payment", "new_logo"],
        "industries": industries(md),
        "spend_categories": categories(md),
        "stages": st,
        "base_seed": base_rates(md, st),
        "params": params(md),
        "rounding": ROUNDING,
        "segment_keys": SEGMENT_KEYS,
        "lineage": LINEAGE,
    }


def main() -> None:
    cfg = build()
    header = ("# GENERATED by etl/config/build_gold_yaml.py from docs/gold_acquisition_model.md.\n"
              "# Do not edit by hand: change the spec and re-run the script.\n")
    text = header + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=10_000)
    OUT.write_text(text, encoding="utf-8")
    cfg["gold_model_version"] = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    OUT.with_suffix(".json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({cfg['gold_model_version']})")


if __name__ == "__main__":
    main()
