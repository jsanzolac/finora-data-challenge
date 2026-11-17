"""Column schemas of the gold MRR Iceberg tables (docs/mrr_discounts_model.md §6).

Types are Spark/Glue type strings. Money is DECIMAL, never float: native
DECIMAL(18,6), `_value` = native x 10,000 as DECIMAL(18,2). Iceberg has no
SMALLINT, so the spec's SMALLINT columns (industry_key, line_order,
discount_reason_key) are INT, as in the acquisition model. Every row carries
the gold lineage block of docs/gold_acquisition_model.md §2.

These tables are owned by finora-dl-gold-mrr only; the acquisition tables are
never written by this job (iceberg_io.MrrWriter refuses any other name, and the
job role can write only these prefixes).
"""

from __future__ import annotations

DB = "finora_gold"
SILVER_INPUTS = ("customer_month", "customer", "month_control", "source_status")

LINEAGE = [("_run_id", "string"), ("_silver_run_id", "string"), ("_rules_version", "string"),
           ("_gold_model_version", "string"), ("_transactions_sha256", "string"), ("_industry_sha256", "string"),
           ("_sm_spend_sha256", "string"), ("as_of_month", "string"), ("_built_at", "timestamp")]

N, V = "decimal(18,6)", "decimal(18,2)"


def money(name: str) -> list[tuple[str, str]]:
    return [(name, N), (f"{name}_value", V)]


TABLES: dict[str, list[tuple[str, str]]] = {
    # §6.4 line / movement_type domain (the dim_movement_type the spec references)
    "dim_movement_type": [
        ("line", "string"), ("line_order", "int"), ("section", "string"), ("driver", "string"),
        ("label", "string"), ("is_movement", "boolean"), ("is_observable_on_cash_proxy", "boolean"),
        ("is_inferred", "boolean"), ("inference_rule", "string"),
    ],
    # §6.1 customer x month, dense panel
    "fact_customer_month_mrr": [
        ("customer_id", "int"), ("month_key", "int"), ("industry_key", "int"), ("cohort_month_key", "int"),
        ("lifecycle_state", "string"), ("mrr_basis", "string"),
    ] + money("collected_amount") + money("mrr_proxy") + money("list_mrr") + money("discount_mrr")
      + money("net_mrr") + money("billed_amount") + money("mrr") + money("timing_adjustment") + [
        ("timing_type", "string"), ("is_inferred_price_step", "boolean"), ("price_step_start_month", "string"),
        ("is_hole", "boolean"), ("is_provisional", "boolean"), ("currency_status", "string"),
        ("_source_key", "string"), ("_ingested_at", "string"),
    ],
    # §6.2 customer x month x movement, non-zero movements only
    "fact_mrr_movement": [
        ("customer_id", "int"), ("month_key", "int"), ("industry_key", "int"), ("cohort_month_key", "int"),
        ("movement_type", "string"), ("driver", "string"), ("amount", N), ("amount_value", V),
        ("prior_state", "string"), ("state", "string"), ("is_inferred", "boolean"), ("inference_rule", "string"),
        ("cro05_covered", "boolean"), ("is_one_off_spike", "boolean"), ("is_temporary_dip", "boolean"),
        ("is_outlier_customer", "boolean"), ("is_provisional", "boolean"), ("mrr_basis", "string"),
        ("item_id", "string"), ("discount_id", "string"), ("price_book_version", "string"),
        ("discount_reason_key", "int"),
    ],
    # §6.3 month x line
    "agg_mrr_bridge_month": [
        ("month_key", "int"), ("section", "string"), ("line", "string"), ("line_order", "int"),
        ("driver", "string"), ("amount", N), ("amount_value", V), ("events", "int"), ("mrr_basis", "string"),
        ("is_provisional", "boolean"),
    ],
}

COLUMNS: dict[str, list[tuple[str, str]]] = {t: cols + LINEAGE for t, cols in TABLES.items()}
PARTITIONS: dict[str, list[str]] = {}
# The bridge is published last: it is the table the dashboard and the controls read,
# so it is the commit marker of a run (a reader that sees its tag sees the whole run).
MARKER = "agg_mrr_bridge_month"
ORDER = list(TABLES)
TABLE_NAMES = list(TABLES)
