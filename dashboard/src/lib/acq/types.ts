/**
 * Types written from contracts/acq_api_contract.md (v1.2). Conventions (auth,
 * errors, roles, "__restricted__") are those of contracts/dq_api_contract.md.
 *
 * Stage, industry, category and regime codes and labels come from the API.
 * The UI hard-codes none of them.
 */

/** A decimal string in full units (owner scale applied), or "__restricted__" for a masked HR value. */
export type MoneyString = string;

export type WonDefinition = "user" | "new_logo";
export type CorrelationMethod = "level" | "diff" | "within_regime";

/** Sent by the API, independent of the Won definition. */
export type MonthCostNullReason = "spend_missing" | "beyond_data_complete_through" | "unit_tripwire" | "won_incomplete";

/** What the UI shows: the API reasons, plus `won_zero`, which the UI derives for the selected definition. */
export type CostNullReason = MonthCostNullReason | "won_zero";

export interface AcqRun {
  run_id: string;
  silver_run_id: string;
  built_at: string;
  as_of_month: string;
  data_complete_through: string;
  gold_model_version: string;
  base_rates_match_seed: boolean;
}

export interface AcqStatuses {
  currency_status: string;
  revenue_basis_status: string;
  spend_basis_status: string;
  scope_status: string;
}

export interface FunnelStage {
  code: string;
  label: string;
  order: number;
}

export interface Industry {
  code: string;
  label: string;
}

export interface SpendCategory {
  code: string;
  label: string;
  hr_sensitive: boolean;
  group: string;
}

export interface Regime {
  id: string;
  label: string;
  first_month: string;
  last_month: string;
  inferred: boolean;
}

export interface AcqMonth {
  month: string;
  regime: string;
  won: number;
  won_new_logo: number;
  won_by_industry: Record<string, number>;
  /** The same split for the `new_logo` definition. */
  won_by_industry_new_logo: Record<string, number>;
  new_revenue_value: MoneyString | null;
  /** Every category in `spend_categories`. HR categories are "__restricted__" for non-finance roles. */
  spend_value: Record<string, MoneyString | null>;
  spend_people_value: MoneyString | null;
  /** Null when the month has no S&M line. */
  spend_total_value: MoneyString | null;
  won_is_complete: boolean;
  is_unit_tripwire: boolean;
  /** Never `won_zero`: the UI derives that one per definition. */
  cost_null_reason: MonthCostNullReason | string | null;
  is_low_n: boolean;
}

export type CustomerScope = "all" | "won" | "left_censored";

export interface IndustryProfileRow {
  industry_code: string;
  customer_scope: CustomerScope | string;
  customers: number;
  /** The industry's Won (user definition), the same on every scope row of the industry. */
  won: number;
  avg_monthly_payment_value: MoneyString | null;
  avg_monthly_payment_excl_outliers_value: MoneyString | null;
  median_monthly_payment_value: MoneyString | null;
  outlier_customers: number;
  /** 4-dp decimal strings; shown with 1 dp. */
  avg_months_paying: string | null;
  avg_months_observable: string | null;
  share_of_observable_months_paid: string | null;
  is_low_n: boolean;
}

export interface CorrelationRow {
  won_definition: WonDefinition | string;
  /** `company` or an industry code. */
  scope: string;
  /** A spend category code, a group (`people`, ...) or `total`. */
  series: string;
  lag: number;
  method: CorrelationMethod | string;
  r: number | null;
  n: number;
  r_critical_5pct: number | null;
  is_signal: boolean;
  /** The scope's mean Won over the paired months is under 10. */
  is_low_volume: boolean;
  /** Why `r` is null: `too_few_pairs` or `constant_series`. */
  null_reason: string | null;
}

export interface SignalSummaryRow {
  method: CorrelationMethod | string;
  won_definition: WonDefinition | string;
  scope_type: "company" | "industry" | string;
  tests: number;
  tests_with_r: number;
  signals: number;
  expected_by_chance: number;
}

/**
 * v1.3 `levers`: the rows of the gold §16 tables, with their column names
 * (docs/gold_acquisition_model.md §16.4). Rows exist for both `won_definition`
 * values (`first_payment` = the user's Won, `new_logo`).
 */
interface RetentionCounts {
  paying_m6_eligible: number;
  paying_m6_count: number;
  /** 4 dp, or null when nobody is eligible. */
  paying_m6_share: string | null;
  paying_m12_eligible: number;
  paying_m12_count: number;
  paying_m12_share: string | null;
  outlier_customers: number;
}

/** agg_acq_lever_period */
export interface LeverPeriod extends RetentionCounts {
  won_definition: string;
  period_code: string;
  period_label: string;
  is_inferred: boolean;
  first_month_key: number;
  last_month_key: number;
  months: number;
  won_count: number;
  /** 6 dp. */
  won_per_month: string;
  run_rate_customers: number;
  run_rate_no_paid_customers: number;
  run_rate_immature_customers: number;
  run_rate_last_cohort_month_key: number | null;
  run_rate_mrr_per_won_value: MoneyString | null;
  new_mrr_per_month_value: MoneyString | null;
  spend_total_value: MoneyString | null;
  spend_per_month_value: MoneyString | null;
  cost_per_won_value: MoneyString | null;
  /** 1 dp. */
  payback_months: string | null;
  cost_null_reason: string | null;
}

/** agg_acq_lever_industry (no spend-derived column, CDO-10). */
export interface LeverIndustry extends RetentionCounts {
  won_definition: string;
  period_code: string;
  industry_key: number;
  industry_code: string;
  won_count: number;
  won_share: string;
  run_rate_customers: number;
  run_rate_no_paid_customers: number;
  run_rate_immature_customers: number;
  run_rate_share: string;
  run_rate_mrr_per_won_value: MoneyString | null;
  is_low_n: boolean;
  is_small_cell: boolean;
}

/** agg_acq_value_change: one row per industry; totals = Σ terms, HALF_UP 2 dp. */
export interface ValueChangeRow {
  won_definition: string;
  from_period_code: string;
  to_period_code: string;
  industry_key: number;
  industry_code: string;
  share_from: string;
  share_to: string;
  value_from: MoneyString | null;
  value_to: MoneyString | null;
  mix_term_value: string | null;
  within_term_value: string | null;
  mix_reverse_term_value: string | null;
  within_reverse_term_value: string | null;
  null_reason: string | null;
}

/** v_acq_cohort_half */
export interface LeverCohort extends RetentionCounts {
  won_definition: string;
  cohort_half: string;
  won_count: number;
  run_rate_customers: number;
  run_rate_no_paid_customers: number;
  run_rate_immature_customers: number;
  run_rate_mrr_per_won_value: MoneyString | null;
  is_complete_m6: boolean;
  is_complete_m12: boolean;
  is_complete_run_rate: boolean;
}

export interface Levers {
  definitions_version: string;
  periods: LeverPeriod[];
  industries: LeverIndustry[];
  value_change: ValueChangeRow[];
  cohorts: LeverCohort[];
}

/** The page's Won definition as the lever tables name it. */
export function leverDefinition(definition: WonDefinition): string {
  return definition === "new_logo" ? "new_logo" : "first_payment";
}

export interface AcqSummary {
  run: AcqRun;
  statuses: AcqStatuses;
  stages: FunnelStage[];
  industries: Industry[];
  spend_categories: SpendCategory[];
  regimes: Regime[];
  months: AcqMonth[];
  industry_profile: IndustryProfileRow[];
  correlations: CorrelationRow[];
  signal_summary: SignalSummaryRow[];
  /** v1.2. Optional so a v1.1 payload still renders (the planner then hides). */
  levers?: Levers;
}

export interface ScenarioRate {
  from_stage: string;
  to_stage: string;
  /** 4-decimal string, 0 < rate <= 1. */
  rate: string;
}

export interface Scenario {
  scenario_id: string;
  label: string;
  status: "valid" | "invalid" | string;
  failed_checks: string[];
  rates: ScenarioRate[];
  changed_at: string;
  changed_by: string;
  change_reason: string;
}

export interface ScenariosResponse {
  can_edit: boolean;
  scenarios: Scenario[];
}

export interface SaveScenarioRequest {
  scenario_id: string;
  label: string;
  change_reason: string;
  rates: ScenarioRate[];
}

/** One item of `error.details` in a 400 `invalid_scenario`. */
export interface ApiErrorDetail {
  /** A GR id, or LABEL_LENGTH / REASON_LENGTH. */
  check: string;
  /** `scenario_id`, `label`, `change_reason` or `rates`. */
  field: string;
  message: string;
}

export const BASE_SCENARIO_ID = "base";
export const SCENARIO_ID_PATTERN = /^[a-z][a-z0-9_]{0,39}$/;
export const LABEL_MAX = 200;
export const REASON_MAX = 500;
