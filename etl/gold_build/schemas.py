"""Column schemas of the gold Iceberg tables (docs/gold_acquisition_model.md §5).

Types are Spark/Glue type strings. Money is DECIMAL, never float. Iceberg has
no SMALLINT, so the spec's SMALLINT keys (industry_key, category_key) are INT
(the narrowest Iceberg integer type).
"""

from __future__ import annotations

DB = "finora_gold"

LINEAGE = [("_run_id", "string"), ("_silver_run_id", "string"), ("_rules_version", "string"),
           ("_gold_model_version", "string"), ("_transactions_sha256", "string"), ("_industry_sha256", "string"),
           ("_sm_spend_sha256", "string"), ("as_of_month", "string"), ("_built_at", "timestamp")]
ROW_LINEAGE = [("_source_key", "string"), ("_ingested_at", "string"), ("_source_line", "int")]
STATUSES = [("currency_status", "string"), ("revenue_basis_status", "string"), ("spend_basis_status", "string"),
            ("scope_status", "string")]

# Which silver datasets each table uses (§2: the sha columns are NULL otherwise).
USES = {
    "dim_month": {"transactions", "sm_spend"},
    "dim_industry": {"industry"},
    "dim_customer": {"transactions", "industry"},
    "dim_spend_category": {"sm_spend"},
    "dim_funnel_stage": set(),
    "fact_acquisition": {"transactions", "industry"},
    "fact_customer_month_revenue": {"transactions", "industry"},
    "fact_sm_spend": {"sm_spend"},
    "agg_acquisition_month": {"transactions", "sm_spend"},
    "agg_won_month_industry": {"transactions", "industry"},
    "agg_industry_profile": {"transactions", "industry"},
    "agg_won_spend_lag_corr": {"transactions", "industry", "sm_spend"},
    "gold_build_status": {"transactions", "industry", "sm_spend"},
    "agg_acq_cohort_quality": {"transactions", "industry"},
    "agg_acq_lever_period": {"transactions", "sm_spend"},
    "agg_acq_lever_industry": {"transactions", "industry"},
    "agg_acq_value_change": {"transactions", "industry"},
}

TABLES: dict[str, list[tuple[str, str]]] = {
    "dim_month": [
        ("month_key", "int"), ("month", "string"), ("month_start_date", "date"), ("month_end_date", "date"),
        ("year", "int"), ("quarter", "int"), ("year_quarter", "string"), ("month_index", "int"),
        ("is_window_start", "boolean"), ("is_won_reportable", "boolean"), ("sm_regime", "string"),
        ("in_transactions", "boolean"), ("in_sm_spend", "boolean"), ("revenue_is_complete", "boolean"),
        ("is_unit_tripwire", "boolean"),
    ],
    "dim_industry": [
        ("industry_key", "int"), ("industry_code", "string"), ("industry_label_es", "string"),
        ("industry_label_en", "string"), ("chart_label", "string"), ("is_unknown_member", "boolean"),
        ("sort_order", "int"),
    ],
    "dim_customer": [
        ("customer_id", "int"), ("industry_key", "int"), ("cohort_month_key", "int"), ("cohort_censoring", "string"),
        ("is_won", "boolean"), ("is_new_logo", "boolean"), ("paid_months", "int"), ("last_paid_month_key", "int"),
        ("is_outlier_customer", "boolean"), ("outlier_source", "string"), ("has_excluded_months", "boolean"),
        ("in_transactions", "boolean"),
    ],
    "dim_spend_category": [
        ("category_key", "int"), ("category_code", "string"), ("category_label_en", "string"),
        ("spend_group", "string"), ("channel_class", "string"), ("is_hr_sensitive", "boolean"),
    ],
    "dim_funnel_stage": [
        ("stage_key", "int"), ("stage_code", "string"), ("stage_label", "string"), ("next_stage_code", "string"),
        ("is_observed", "boolean"), ("basis", "string"),
    ],
    "fact_acquisition": [
        ("customer_id", "int"), ("won_month_key", "int"), ("industry_key", "int"), ("won_count", "int"),
        ("first_paid_amount", "decimal(12,6)"), ("first_paid_amount_value", "decimal(18,2)"),
        ("run_rate_amount_value", "decimal(18,2)"), ("first_payment_multiple", "int"),
        ("is_first_payment_multiple", "boolean"), ("first_payment_ratio", "decimal(38,12)"),
        ("first_payment_band", "string"), ("is_first_month_spike", "boolean"), ("implied_start_month", "string"),
        ("cohort_censoring", "string"), ("is_new_logo", "boolean"), ("is_probable_left", "boolean"),
        ("is_cohort_unknown", "boolean"), ("first_payment_hole_affected", "boolean"),
        ("is_outlier_customer", "boolean"),
        # §16.4(a) decision levers (added to the existing table by schema evolution)
        ("cohort_half", "string"), ("run_rate_status", "string"), ("run_rate_m2_4_months", "int"),
        ("run_rate_m2_4_value", "decimal(18,6)"), ("paying_m6", "boolean"), ("paying_m12", "boolean"),
    ] + ROW_LINEAGE,
    "fact_customer_month_revenue": [
        ("customer_id", "int"), ("month_key", "int"), ("industry_key", "int"), ("cohort_month_key", "int"),
        ("months_since_cohort", "int"), ("amount", "decimal(12,6)"), ("amount_value", "decimal(18,2)"),
        ("amount_normalized", "decimal(18,6)"), ("amount_normalized_value", "decimal(18,2)"),
        ("is_paying", "boolean"), ("is_negative_amount", "boolean"), ("is_first_paid_month", "boolean"),
        ("is_hole", "boolean"), ("hole_reason", "string"), ("lifecycle_state", "string"),
        ("is_provisional", "boolean"), ("settlement_type", "string"), ("settlement_confidence", "string"),
        ("uneven_split_start_month", "string"), ("is_catch_up", "boolean"), ("is_prepaid", "boolean"),
        ("expansion_amount", "decimal(18,6)"), ("contraction_amount", "decimal(18,6)"),
        ("amount_lag12", "decimal(18,6)"),
    ] + ROW_LINEAGE,
    "fact_sm_spend": [
        ("month_key", "int"), ("category_key", "int"), ("spend", "decimal(12,3)"), ("spend_value", "decimal(18,0)"),
        ("is_negative_spend", "boolean"), ("is_restated", "boolean"), ("is_unit_tripwire", "boolean"),
    ] + ROW_LINEAGE + [("hr_sensitive", "boolean")],
    "agg_acquisition_month": [
        ("month_key", "int"), ("is_won_reportable", "boolean"), ("won_count", "int"), ("won_new_logo_count", "int"),
        ("won_probable_left_count", "int"), ("won_cohort_unknown_count", "int"),
        ("won_first_payment_multiple_count", "int"), ("won_is_complete", "boolean"),
        ("new_revenue_value", "decimal(18,2)"), ("new_revenue_new_logo_value", "decimal(18,2)"),
        ("new_revenue_multiple_value", "decimal(18,2)"), ("new_revenue_run_rate_value", "decimal(18,2)"),
        ("spend_paid_media_value", "decimal(18,0)"), ("spend_travel_value", "decimal(18,0)"),
        ("spend_publicidad_no_web_value", "decimal(18,0)"), ("spend_software_tools_value", "decimal(18,0)"),
        ("spend_media_value", "decimal(18,0)"), ("spend_other_value", "decimal(18,0)"),
        ("spend_people_value", "decimal(18,0)"), ("spend_total_value", "decimal(18,0)"),
        ("has_negative_spend_cell", "boolean"), ("in_sm_spend", "boolean"), ("is_unit_tripwire", "boolean"),
    ] + STATUSES,
    "agg_won_month_industry": [
        ("month_key", "int"), ("industry_key", "int"), ("won_count", "int"), ("won_new_logo_count", "int"),
        ("new_revenue_value", "decimal(18,2)"), ("new_revenue_new_logo_value", "decimal(18,2)"),
        ("is_low_n", "boolean"), ("is_small_cell", "boolean"),
    ],
    "agg_industry_profile": [
        ("industry_key", "int"), ("customer_scope", "string"), ("customers", "int"),
        ("paid_customer_months", "int"), ("avg_monthly_payment_value", "decimal(18,2)"),
        ("avg_monthly_payment_ex_outlier_value", "decimal(18,2)"), ("median_monthly_payment_value", "decimal(18,2)"),
        ("outlier_customers", "int"), ("avg_months_paying", "decimal(9,4)"), ("avg_months_observable", "decimal(9,4)"),
        ("share_of_observable_months_paid", "decimal(9,4)"), ("is_low_n", "boolean"),
    ],
    "agg_won_spend_lag_corr": [
        ("won_definition", "string"), ("scope_code", "string"), ("industry_key", "int"), ("spend_series", "string"),
        ("category_key", "int"), ("lag_months", "int"), ("method", "string"), ("r", "decimal(5,4)"),
        ("n_pairs", "int"), ("r_critical_5pct", "decimal(5,4)"), ("is_signal_5pct", "boolean"),
        ("won_mean_per_month", "decimal(9,4)"), ("is_low_volume", "boolean"), ("first_won_month_key", "int"),
        ("last_won_month_key", "int"), ("null_reason", "string"),
    ],
    # §16.4 decision levers
    "agg_acq_cohort_quality": [
        ("won_definition", "string"), ("won_month_key", "int"), ("industry_key", "int"), ("cohort_half", "string"),
        ("won_count", "int"), ("run_rate_customers", "int"), ("run_rate_no_paid_customers", "int"),
        ("run_rate_immature_customers", "int"), ("run_rate_m2_4_sum_value", "decimal(38,6)"),
        ("paying_m6_eligible", "int"), ("paying_m6_count", "int"), ("paying_m12_eligible", "int"),
        ("paying_m12_count", "int"), ("outlier_customers", "int"), ("is_low_n", "boolean"), ("is_small_cell", "boolean"),
    ],
    "agg_acq_lever_period": [
        ("won_definition", "string"), ("period_code", "string"), ("period_label", "string"), ("is_inferred", "boolean"),
        ("first_month_key", "int"), ("last_month_key", "int"), ("months", "int"), ("won_count", "int"),
        ("won_per_month", "decimal(18,6)"), ("run_rate_customers", "int"), ("run_rate_no_paid_customers", "int"),
        ("run_rate_immature_customers", "int"), ("run_rate_last_cohort_month_key", "int"),
        ("run_rate_mrr_per_won_value", "decimal(18,2)"), ("new_mrr_per_month_value", "decimal(18,2)"),
        ("spend_total_value", "decimal(18,0)"), ("spend_per_month_value", "decimal(18,2)"),
        ("cost_per_won_value", "decimal(18,2)"), ("payback_months", "decimal(9,1)"), ("cost_null_reason", "string"),
        ("paying_m6_eligible", "int"), ("paying_m6_count", "int"), ("paying_m6_share", "decimal(9,4)"),
        ("paying_m12_eligible", "int"), ("paying_m12_count", "int"), ("paying_m12_share", "decimal(9,4)"),
        ("outlier_customers", "int"),
    ] + STATUSES,
    "agg_acq_lever_industry": [
        ("won_definition", "string"), ("period_code", "string"), ("industry_key", "int"), ("won_count", "int"),
        ("won_share", "decimal(9,4)"), ("run_rate_customers", "int"), ("run_rate_no_paid_customers", "int"),
        ("run_rate_immature_customers", "int"), ("run_rate_share", "decimal(9,4)"),
        ("run_rate_mrr_per_won_value", "decimal(18,2)"), ("paying_m6_eligible", "int"), ("paying_m6_count", "int"),
        ("paying_m6_share", "decimal(9,4)"), ("paying_m12_eligible", "int"), ("paying_m12_count", "int"),
        ("paying_m12_share", "decimal(9,4)"), ("outlier_customers", "int"), ("is_low_n", "boolean"),
        ("is_small_cell", "boolean"),
    ],
    "agg_acq_value_change": [
        ("won_definition", "string"), ("from_period_code", "string"), ("to_period_code", "string"),
        ("industry_key", "int"), ("share_from", "decimal(9,4)"), ("share_to", "decimal(9,4)"),
        ("value_from", "decimal(18,2)"), ("value_to", "decimal(18,2)"), ("mix_term_value", "decimal(18,6)"),
        ("within_term_value", "decimal(18,6)"), ("mix_reverse_term_value", "decimal(18,6)"),
        ("within_reverse_term_value", "decimal(18,6)"), ("null_reason", "string"),
    ],
    "gold_build_status": [
        ("window_start_month", "string"), ("revenue_complete_through", "string"),
        ("spend_complete_through", "string"), ("data_complete_through", "string"), ("currency_code", "string"),
    ] + STATUSES + [
        ("base_rates_match_seed", "boolean"), ("rate_table_snapshot_id", "bigint"),
        ("rate_table_rows_sha256", "string"), ("controls_passed", "boolean"),
    ],
}

# Every materialized table carries the lineage block, after its own columns.
COLUMNS: dict[str, list[tuple[str, str]]] = {t: cols + LINEAGE for t, cols in TABLES.items()}
PARTITIONS = {"fact_sm_spend": ["hr_sensitive"]}
# §5.8 / §9.4: no min/max of spend values in the manifests (readable by every reader of the table).
EXTRA_PROPERTIES = {"fact_sm_spend": {"write.metadata.metrics.column.spend": "none",
                                      "write.metadata.metrics.column.spend_value": "none"}}
ORDER = list(TABLES)  # write order; gold_build_status is published last (the commit marker)

# The user-owned rates table: created and seeded once by the deploy step
# (infra/gold_athena_ddl.py), never written by the gold job (§6.5).
RATE_TABLE = "funnel_conversion_rate"
RATE_COLUMNS = [("scenario_id", "string"), ("scenario_label", "string"), ("from_stage_code", "string"),
                ("to_stage_code", "string"), ("rate", "decimal(5,4)"), ("changed_at", "timestamp"),
                ("changed_by", "string"), ("change_reason", "string")]
