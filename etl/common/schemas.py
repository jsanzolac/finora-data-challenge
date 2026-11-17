"""Column schemas for the silver and DQ Iceberg tables.

One source of truth for the Glue Spark writer. Types are Spark/Glue type
strings. Money is DECIMAL, never float.
"""

from __future__ import annotations

LINEAGE = [("_run_id", "string"), ("_source_key", "string"), ("_source_sha256", "string"),
           ("_ingested_at", "string"), ("_rules_version", "string"), ("as_of_month", "string")]
LINE = [("_source_line", "int")]

SILVER: dict[str, list[tuple[str, str]]] = {
    "transactions": [
        ("customer_id", "int"), ("month", "string"), ("amount", "decimal(12,6)"),
        ("amount_value", "decimal(18,2)"), ("is_paying", "boolean"), ("is_negative_amount", "boolean"),
        ("is_restated", "boolean"), ("id_raw", "string"), ("month_raw", "string"), ("amount_raw", "string"),
    ] + LINEAGE + LINE,
    "industry": [
        ("customer_id", "int"), ("industry_code", "string"), ("industria_raw", "string"),
        ("industria_nfc", "string"), ("is_industry_unmapped", "boolean"), ("is_restated", "boolean"),
        ("id_raw", "string"),
    ] + LINEAGE + LINE,
    "sm_spend": [
        ("month", "string"), ("category", "string"), ("spend", "decimal(12,3)"),
        ("spend_value", "decimal(18,0)"), ("spend_raw", "string"), ("is_negative_spend", "boolean"),
        ("is_restated", "boolean"), ("is_unit_tripwire", "boolean"),
    ] + LINEAGE + LINE,
    "customer": [
        ("customer_id", "int"), ("industry_code", "string"), ("is_industry_unknown", "boolean"),
        ("is_industry_unmapped", "boolean"), ("in_transactions", "boolean"), ("cohort_month", "string"),
        ("cohort_censoring", "string"), ("is_new_logo", "boolean"), ("first_paid_amount", "decimal(12,6)"),
        ("next_paid_amount", "decimal(12,6)"), ("first_payment_ratio", "decimal(38,12)"),
        ("first_payment_multiple", "int"), ("implied_start_month", "string"),
        ("first_payment_band", "string"), ("is_first_month_spike", "boolean"),
        ("first_payment_hole_affected", "boolean"), ("paid_months", "int"), ("last_paid_month", "string"),
        ("median_paid_amount", "decimal(38,12)"), ("is_outlier_customer", "boolean"),
        ("outlier_source", "string"), ("outlier_multiple", "decimal(38,12)"),
        ("has_excluded_months", "boolean"), ("hole_months", "int"), ("_industry_source_sha256", "string"),
    ] + LINEAGE,
    "customer_month": [
        ("customer_id", "int"), ("month", "string"), ("amount", "decimal(12,6)"),
        ("amount_value", "decimal(18,2)"), ("is_hole", "boolean"), ("hole_reason", "string"),
        ("is_paying", "boolean"), ("lifecycle_state", "string"), ("is_churn_event", "boolean"),
        ("is_provisional", "boolean"), ("is_hole_affected", "boolean"), ("settlement_type", "string"),
        ("settlement_confidence", "string"),
        # SB-11 (2026-11-17): pair start month YYYY-MM on both pair rows, NULL elsewhere.
        # Added to existing tables by IcebergWriter.ensure() (nullable, at this position).
        ("uneven_split_start_month", "string"),
        ("is_catch_up", "boolean"), ("is_prepaid", "boolean"),
        ("amount_normalized", "decimal(18,6)"), ("expansion_amount", "decimal(18,6)"),
        ("contraction_amount", "decimal(18,6)"), ("amount_lag12", "decimal(18,6)"),
    ] + LINEAGE,
    "gap": [
        ("customer_id", "int"), ("p_month", "string"), ("q_month", "string"), ("gap_start_month", "string"),
        ("k", "int"), ("test_arrears", "boolean"), ("test_prepay", "boolean"), ("test_split", "boolean"),
        ("settlement_type", "string"), ("settlement_confidence", "string"),
        ("settlement_hole_affected", "boolean"), ("outcome", "string"),
    ] + LINEAGE,
    "month_control": [
        ("month", "string"), ("in_transactions", "boolean"), ("in_sm_spend", "boolean"),
        ("revenue_total", "decimal(18,6)"), ("revenue_value_total", "decimal(18,2)"), ("hole_count", "int"),
        ("revenue_is_complete", "boolean"), ("sm_total", "decimal(18,3)"), ("sm_value_total", "decimal(18,0)"),
        ("sm_to_revenue_ratio", "decimal(38,12)"), ("is_unit_tripwire", "boolean"), ("scope_status", "string"),
        ("paying_customers", "int"), ("new_logos", "int"), ("churn_events", "int"), ("reactivations", "int"),
        ("is_churn_confirmed", "boolean"), ("_sm_source_sha256", "string"),
    ] + LINEAGE,
    "source_status": [
        ("dataset_id", "string"), ("currency_code", "string"), ("currency_status", "string"),
        ("basis_status", "string"), ("basis_hint", "string"),
    ] + LINEAGE,
    "restatement_log": [
        ("dataset_id", "string"), ("key_json", "string"), ("column_name", "string"),
        ("old_value", "string"), ("new_value", "string"), ("previous_run_id", "string"),
    ] + LINEAGE,
}

# Tables partitioned by hr_sensitive (CDO-11): HR values sit only in the
# hr_sensitive=true partition (Iceberg identity partition, data/hr_sensitive=true/).
HR_PARTITIONED = {"sm_spend", "restatement_log"}

DQ: dict[str, list[tuple[str, str]]] = {
    "findings": [
        ("rule_id", "string"), ("dataset_id", "string"), ("action", "string"), ("source_line", "int"),
        ("key_json", "string"), ("failed_columns", "array<string>"), ("raw_values_json", "string"),
        ("reason", "string"),
    ] + LINEAGE,
    "excluded": [
        ("dataset_id", "string"), ("source_line", "int"), ("key_json", "string"), ("values_json", "string"),
        ("failed_rules", "array<string>"), ("reasons_json", "string"),
    ] + LINEAGE,
}


# Iceberg tables in the Glue Data Catalog: name -> (database, columns, partition columns).
# Each run is a full rebuild committed as one snapshot per table and tagged with
# its run_id; `_run_id` is on every row. Earlier runs are read by time travel.
HR = [("hr_sensitive", "boolean")]
ICEBERG: dict[str, tuple[str, list[tuple[str, str]], list[str]]] = {
    **{t: ("finora_silver", cols + (HR if t in HR_PARTITIONED else []),
           ["hr_sensitive"] if t in HR_PARTITIONED else [])
       for t, cols in SILVER.items()},
    "findings": ("finora_dq", DQ["findings"] + HR, ["hr_sensitive"]),
    "excluded_rows": ("finora_dq", DQ["excluded"] + HR, ["dataset_id", "hr_sensitive"]),
}
