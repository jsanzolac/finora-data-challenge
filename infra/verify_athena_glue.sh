#!/bin/zsh
# Read-only Athena checks of the Iceberg tables against the golden figures.
# Usage: AWS_PROFILE=alegra-test ./verify_athena_glue.sh <run_id> [<snapshot_id of finora_silver.transactions for time travel>]
RUN=$1
SNAP=$2
q() {
  local id=$(aws athena start-query-execution --region us-west-2 --work-group finora-dl \
    --query-string "$1" --query QueryExecutionId --output text)
  while true; do
    local st=$(aws athena get-query-execution --region us-west-2 --query-execution-id $id \
      --query QueryExecution.Status.State --output text)
    [[ $st == SUCCEEDED || $st == FAILED || $st == CANCELLED ]] && break
    sleep 1
  done
  [[ $st != SUCCEEDED ]] && { echo "$1 -> $st $(aws athena get-query-execution --region us-west-2 --query-execution-id $id --query QueryExecution.Status.StateChangeReason --output text)"; return; }
  echo "$1"
  aws athena get-query-results --region us-west-2 --query-execution-id $id \
    --query 'ResultSet.Rows[1:].Data[].VarCharValue' --output text
}
q "SELECT _run_id, count(*), sum(amount), sum(amount_value) FROM finora_silver.transactions GROUP BY 1"
q "SELECT count(*) FROM finora_silver.industry WHERE _run_id='$RUN'"
q "SELECT count(*), sum(spend), sum(spend_value) FROM finora_silver.sm_spend WHERE _run_id='$RUN'"
q "SELECT hr_sensitive, count(*) FROM finora_silver.sm_spend GROUP BY hr_sensitive ORDER BY 1"
q "SELECT count(*), sum(CASE WHEN is_new_logo THEN 1 ELSE 0 END), sum(CASE WHEN cohort_censoring='probable_left' THEN 1 ELSE 0 END) FROM finora_silver.customer"
q "SELECT lifecycle_state, count(*) FROM finora_silver.customer_month GROUP BY 1 ORDER BY 2 DESC"
q "SELECT settlement_type, count(*) FROM finora_silver.gap WHERE settlement_type IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"
# SB-11 (expected on today's files: uneven_split high 22 rows, 10 customers, 11 pairs; 3499.903452 / 4656.537782 / 1212 / 954)
q "SELECT settlement_type, settlement_confidence, count(*), count(DISTINCT customer_id), count(DISTINCT cast(customer_id AS varchar) || '|' || uneven_split_start_month) FROM finora_silver.customer_month WHERE uneven_split_start_month IS NOT NULL GROUP BY 1, 2"
q "SELECT sum(expansion_amount), sum(contraction_amount), sum(CASE WHEN expansion_amount > 0 THEN 1 ELSE 0 END), sum(CASE WHEN contraction_amount > 0 THEN 1 ELSE 0 END) FROM finora_silver.customer_month"
q "SELECT array_join(array_agg(customer_id ORDER BY customer_id), ',') FROM finora_silver.customer WHERE is_outlier_customer"
q "SELECT rule_id, dataset_id, action, count(*) FROM finora_dq.findings WHERE NOT hr_sensitive GROUP BY 1,2,3 ORDER BY 1"
q "SELECT dataset_id, count(*), max(source_line), array_join(max(failed_rules), ',') FROM finora_dq.excluded_rows WHERE NOT hr_sensitive GROUP BY 1"
q "SELECT name, type, snapshot_id FROM \"finora_silver\".\"transactions\$refs\" ORDER BY name"
q "SELECT count(*) FROM \"finora_silver\".\"transactions\$snapshots\""
[[ -n $SNAP ]] && q "SELECT _run_id, count(*) FROM finora_silver.transactions FOR VERSION AS OF $SNAP GROUP BY 1"
