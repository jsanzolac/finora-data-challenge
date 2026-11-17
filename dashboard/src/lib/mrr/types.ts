/**
 * Types written from contracts/mrr_api_contract.md (v1). Definitions:
 * docs/mrr_discounts_model.md (CDO). Driver and step codes, labels and order come
 * from the API: the UI hard-codes none of them, except styling the `discount`
 * driver as "Not available" while `drivers[].available` is false.
 */

/** A decimal string in full units, or null when unknown. Null never means 0. */
export type MrrMoney = string | null;

export interface MrrRun {
  run_id: string;
  silver_run_id: string;
  built_at: string;
  as_of_month: string;
  data_complete_through: string;
  churn_confirmed_through: string;
  gold_model_version: string;
  /** `cash_proxy` until billing data lands, then `net_mrr`. */
  mrr_basis: string;
}

export interface MrrDriver {
  code: string;
  label: string;
  inferred: boolean;
  available: boolean;
  /** False for timing: it reconciles MRR to cash and is not part of MRR. */
  in_mrr?: boolean;
}

export interface MrrStep {
  code: string;
  label: string;
  driver: string;
  order: number;
}

export interface MrrMonth {
  month: string;
  opening_mrr_value: MrrMoney;
  closing_mrr_value: MrrMoney;
  cash_value: MrrMoney;
  /** The level cash − MRR for the month, not a change. */
  timing_value: MrrMoney;
  step_value: Record<string, MrrMoney>;
  step_customers: Record<string, number | null>;
  customers_opening: number;
  customers_closing: number;
  list_mrr_value: MrrMoney;
  discount_value: MrrMoney;
  is_provisional: boolean;
  is_complete: boolean;
  null_reason: Record<string, string> | null;
}

export interface MrrSummary {
  run: MrrRun;
  statuses: Record<string, string>;
  drivers: MrrDriver[];
  steps: MrrStep[];
  months: MrrMonth[];
}

export interface MrrMovement {
  customer_id: number;
  month: string;
  step: string;
  driver: string;
  inferred: boolean;
  industry_code: string | null;
  mrr_before_value: MrrMoney;
  mrr_after_value: MrrMoney;
  change_value: MrrMoney;
  list_before_value: MrrMoney;
  list_after_value: MrrMoney;
  discount_before_value: MrrMoney;
  discount_after_value: MrrMoney;
  settlement_type: string | null;
  flags: string[];
}

export interface MrrMovementsPage {
  run_id: string;
  total: number;
  page: number;
  page_size: number;
  movements: MrrMovement[];
}

export interface MovementsQuery {
  from: string;
  to: string;
  run: string;
  steps: string[];
  page: number;
  pageSize: number;
}

export const TIMING_DRIVER = "timing";
