#!/bin/zsh
# Read-only Athena checks of a published run against the golden figures.
# Usage: AWS_PROFILE=alegra-test ./verify_athena.sh <run_id>
RUN=$1
q() {
  local id=$(aws athena start-query-execution --region us-west-2 --work-group finora-dl \
    --query-string "$1" --query QueryExecutionId --output text)
  while true; do
    local st=$(aws athena get-query-execution --region us-west-2 --query-execution-id $id \
      --query QueryExecution.Status.State --output text)
    [[ $st == SUCCEEDED || $st == FAILED || $st == CANCELLED ]] && break
    sleep 1
  done
  [[ $st != SUCCEEDED ]] && { echo "$1 -> $st"; return; }
  echo "$1"
  aws athena get-query-results --region us-west-2 --query-execution-id $id \
    --query 'ResultSet.Rows[1:].Data[].VarCharValue' --output text
}
q "SELECT count(*), sum(amount), sum(amount_value) FROM finora_silver.transactions WHERE run_id='$RUN'"
q "SELECT count(*) FROM finora_silver.industry WHERE run_id='$RUN'"
q "SELECT count(*), sum(spend), sum(spend_value) FROM finora_silver.sm_spend WHERE run_id='$RUN'"
q "SELECT hr_sensitive, count(*) FROM finora_silver.sm_spend WHERE run_id='$RUN' GROUP BY hr_sensitive ORDER BY 1"
q "SELECT count(*), sum(CASE WHEN is_new_logo THEN 1 ELSE 0 END), sum(CASE WHEN cohort_censoring='probable_left' THEN 1 ELSE 0 END) FROM finora_silver.customer WHERE run_id='$RUN'"
q "SELECT lifecycle_state, count(*) FROM finora_silver.customer_month WHERE run_id='$RUN' GROUP BY 1 ORDER BY 2 DESC"
q "SELECT settlement_type, count(*) FROM finora_silver.gap WHERE run_id='$RUN' AND settlement_type IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"
q "SELECT array_join(array_agg(customer_id ORDER BY customer_id), ',') FROM finora_silver.customer WHERE run_id='$RUN' AND is_outlier_customer"
q "SELECT rule_id, dataset_id, action, count(*) FROM finora_dq.findings WHERE run_id='$RUN' AND hr_sensitive='false' GROUP BY 1,2,3 ORDER BY 1"
q "SELECT dataset, count(*), max(source_line) FROM finora_dq.excluded WHERE run_id='$RUN' AND hr_sensitive='false' GROUP BY 1"
