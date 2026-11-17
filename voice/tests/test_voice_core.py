"""Compiler safety (catalog only, injection-safe, HR and customer rules, one SELECT over
governed gold), and the number checks of the briefing and the summaries. No AWS."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentlib import ask as A  # noqa: E402
from agentlib import briefing as B  # noqa: E402
from agentlib import catalog as C  # noqa: E402
from agentlib import compiler as K  # noqa: E402
from agentlib import fmt as F  # noqa: E402
from agentlib import numbers as N  # noqa: E402

CTX = K.Context(gold_run_id="r20261117T201211Z", dq_run_id="r20261117T201211Z", data_complete_through="2024-10",
                window_start_month="2022-01", churn_confirmed_through="2024-08",
                snapshots={"agg_acquisition_month": 111, "dim_month": 222, "agg_mrr_bridge_month": 333,
                           "fact_customer_month_mrr": 444, "dim_industry": 555})


def spec(**k):
    s = {"catalog_version": C.VERSION, "intent": "answer", "domain": "acquisition", "metrics": ["acq.won_count"],
         "dimensions": [], "filters": {"time": {}}, "chart": {"type": "kpi"}}
    s.update(k)
    return s


def compiled(role="revops", **k):
    return K.compile_spec(K.validate(spec(**k)), role, CTX)


def test_unknown_metric_dimension_and_op_are_rejected():
    for bad in (spec(metrics=["acq.ltv"]), spec(dimensions=["customer_id"]),
                spec(derived=[{"op": "sql", "of": "acq.won_count"}]), spec(catalog_version="v0"),
                spec(filters={"time": {}, "industry": ["RETAIL'; DROP TABLE x; --"]}),
                spec(filters={"time": {"from": "2024-10' OR '1'='1"}}), spec(limit=10_000)):
        with pytest.raises(K.CompileError):
            K.validate(bad)


def test_values_are_parameters_and_only_governed_objects_appear():
    c = compiled(dimensions=["industry"], filters={"time": {"year": 2023}, "industry": ["RETAIL", "HEALTHCARE"]})
    assert "RETAIL" not in c.sql and "HEALTHCARE" not in c.sql and "2023" not in c.sql
    assert c.params.count("'RETAIL'") == 1 and c.sql.count("?") == len(c.params)
    assert c.sql.upper().startswith("SELECT") and "LIMIT" in c.sql
    assert "FOR VERSION AS OF 222" in c.sql  # pinned to the run's snapshot
    with pytest.raises(K.CompileError):
        K.guard("SELECT * FROM finora_silver.customer LIMIT 1")
    with pytest.raises(K.CompileError):
        K.guard("SELECT customer_id FROM finora_gold.fact_mrr_movement LIMIT 1")
    with pytest.raises(K.CompileError):
        K.guard("SELECT 1 FROM finora_gold.dim_month LIMIT 1; DROP TABLE finora_gold.dim_month")


def test_param_alphabet_is_closed():
    p = K._Params()
    with pytest.raises(ValueError):
        p.add("x' OR 1=1 --")


@pytest.mark.parametrize("role", ["finance", "revops", "data"])
def test_hr_values_are_out_of_scope_for_every_role(role):
    with pytest.raises(K.OutOfScope) as e:
        compiled(role, metrics=["acq.spend_hr_category"], filters={"time": {"year": 2023}})
    assert e.value.reason_code == "hr_restricted"
    with pytest.raises(K.OutOfScope):
        compiled(role, metrics=["acq.spend_category"], filters={"time": {}, "spend_category": ["Team"]})


def test_shared_spend_never_reads_hr_rows():
    c = compiled(metrics=["acq.spend_category"], dimensions=["spend_category"])
    assert "v_sm_spend_shared" in c.sql and "is_hr_sensitive = FALSE" in c.sql.replace("false", "FALSE")


def test_beyond_data_and_not_available_route_deterministically():
    with pytest.raises(K.OutOfScope) as e:
        compiled(filters={"time": {"from": "2024-11", "to": "2024-11"}})
    assert e.value.reason_code == "beyond_data_complete_through"
    with pytest.raises(K.OutOfScope) as e:
        compiled(domain="mrr", metrics=["mrr.discount_leakage"])
    assert e.value.reason_code == "discounts_billing"


def test_customer_grain_is_aggregate_only_and_stocks_are_not_summed():
    c = compiled(domain="mrr", metrics=["mrr.closing", "mrr.paying_customers"], dimensions=["industry"],
                 filters={"time": {"relative": "latest_month"}})
    assert c.source == "cm" and "customers" in c.sql.lower()
    assert "GROUP BY" in c.sql and "m.month BETWEEN ? AND ?" in c.sql
    with pytest.raises(K.CompileError):
        compiled(domain="mrr", metrics=["mrr.closing"], dimensions=["industry", "year"])
    q = compiled(domain="mrr", metrics=["mrr.closing"], dimensions=["year"])
    assert "MAX_BY" in q.sql  # a year takes its last month


def test_flat_model_output_becomes_the_section_2_1_spec():
    raw = {"catalog_version": C.VERSION, "intent": "answer", "domain": "acquisition", "metrics": ["acq.run_rate_per_won"],
           "derived_op": "growth", "derived_of": "acq.run_rate_per_won", "from_period": "pre_2023_06",
           "to_period": "from_2023_06"}
    s = K.validate(A.to_spec(raw))
    assert s["derived"] == [{"op": "growth", "of": "acq.run_rate_per_won", "from_period": "pre_2023_06",
                             "to_period": "from_2023_06"}]


def test_display_formats_follow_section_1_1():
    assert F.display("42550.70", "money") == "42.551"
    assert F.display("3047955.01", "money") == "3,05 millones"
    assert F.display("96360646.83", "money") == "96,4 millones"
    assert F.display("99.95", "pct_dq") == "99,95 %" and F.display("100.0", "pct_dq") == "100 %"
    assert F.display("0.8997", "share_pct1") == "90,0 %"


def _cand():
    return B.Candidate("B06", "mrr_level", "state", "mrr", ["mrr.bridge.closing"], "inferido",
                       [B.Value("closing", "mrr.bridge.closing", "96360646.83", "money", "money"),
                        B.Value("customers", "mrr.bridge.closing", "1678", "int", "count")],
                       "El MRR cerró octubre de 2024 en 96,4 millones, con 1.678 clientes pagando.",
                       dates=["octubre de 2024"])


def test_briefing_number_check():
    c = _cand()
    ok = B._template_fact(c)
    assert B.check_fact(ok, c) == []
    wrong = {**ok, "text_es": "El MRR cerró octubre de 2024 en 97,0 millones, con 1.678 clientes pagando."}
    assert any("97,0" in e for e in B.check_fact(wrong, c))
    hidden = {**ok, "text_es": "El MRR cerró octubre de 2024 en 96,4 millones."}
    assert any("not in the text" in e for e in B.check_fact(hidden, c))
    fake = {**ok, "numbers": ok["numbers"] + [{"kpi_id": "mrr.bridge.closing", "value": "5", "unit": "count"}]}
    assert any("not a value of the KPI table" in e for e in B.check_fact(fake, c))
    words = {**ok, "text_es": "El MRR cerró octubre de 2024 en 96,4 millones, con 1.678 clientes pagando y dos más."}
    assert any("digits" in e for e in B.check_fact(words, c))
    date = {**ok, "text_es": "El MRR cerró marzo de 2023 en 96,4 millones, con 1.678 clientes pagando."}
    assert any("date" in e for e in B.check_fact(date, c))


def test_briefing_direction_check():
    c = B.Candidate("B08", "mrr_last_month", "state", "mrr", ["mrr.why.hero"], "inferido",
                    [B.Value("change", "mrr.why.hero", "3613521.66", "money", "money", True)], "")
    good = {"candidate_id": "B08", "page": "mrr", "kpi_ids": ["mrr.why.hero"], "text_es": "El MRR subió 3,61 millones.",
            "numbers": [{"kpi_id": "mrr.why.hero", "value": "3613521.66", "unit": "money"}]}
    assert B.check_fact(good, c) == []
    bad = {**good, "text_es": "El MRR bajó 3,61 millones."}
    assert any("direction" in e for e in B.check_fact(bad, c))


def test_briefing_falls_back_to_templates_and_never_publishes_a_mismatch():
    c = _cand()

    def model(system, user):
        return {"facts": [{"candidate_id": "B06", "page": "mrr", "kpi_ids": ["mrr.bridge.closing"],
                           "text_es": "El MRR cerró en 99 millones.", "numbers": []}]}
    b = B.generate([c], ask_model=model)
    assert b.facts[0]["source"] == "template" and b.facts[0]["text_es"] == c.template_es
    assert b.stats["regenerated"] == 1 and b.stats["replaced"] == 1 and b.status == "degraded"


def test_summary_check_and_exemptions():
    assert A.check_summary("En 2022: 380 clientes nuevos.", ["380"]) == []
    assert A.check_summary("En 2022: 381 clientes nuevos.", ["380"]) == ["381"]
    assert [s.text for s in N.extract("SB-11 Transacciones 22; el trimestre 2022-Q1; meses 2 a 4")] == ["22"]
