/**
 * Types written from contracts/dq_api_contract.md (v1).
 * Dataset ids, labels, rule ids, layers and columns all come from the API:
 * nothing about a specific rule or department is hard-coded in the UI.
 */

export type Role = "data" | "finance" | "revops";

export interface User {
  email: string;
  role: Role;
  must_change_password: boolean;
}

export interface SessionResponse {
  user: User;
}

export interface ApiErrorBody {
  error: { code: string; message: string };
}

export type RunStatus = "succeeded" | "failed";

export interface RunDataset {
  source_key: string;
  sha256: string;
  rows_read: number;
}

export interface Run {
  run_id: string;
  started_at: string;
  /** The contract does not say whether a failed run has these. The UI tolerates null. */
  finished_at: string | null;
  as_of_month: string | null;
  status: RunStatus;
  datasets: Record<string, RunDataset>;
}

export interface DatasetSummary {
  dataset_id: string;
  label: string;
  rows_read: number;
  rows_excluded: number;
  rows_flagged: number;
  row_compliance_pct: number;
  rules_evaluated: number;
  rules_failing: number;
  rank: number;
}

export type CellStatus = "pass" | "warn" | "fail" | "na";
export type RuleKind = "row" | "finding";
export type RuleAction = "exclude" | "flag" | "finding";

export interface RuleResult {
  evaluated: number;
  failed: number;
  compliance_pct: number | null;
  status: CellStatus;
}

export interface Rule {
  rule_id: string;
  title: string;
  description: string;
  /** `bronze` | `silver_quality` | `silver_business` today. Kept open so a new layer still renders. */
  layer: string;
  kind: RuleKind;
  action: RuleAction;
  inferred: boolean;
  counts_toward_compliance: boolean;
  applies_to: string[];
  results: Record<string, RuleResult>;
}

/** `{ run_id, as_of_month, <dataset_id>: row_compliance_pct }` */
export type TrendPoint = { run_id: string; as_of_month: string } & Record<string, string | number | null>;

export interface Summary {
  run: Run;
  datasets: DatasetSummary[];
  rules: Rule[];
  trend: TrendPoint[];
}

/** The API returns this in place of an HR-sensitive value for every role except finance. */
export const RESTRICTED_VALUE = "__restricted__";

export interface DqRecord {
  /** 1-based line in the source file (the header is line 1). `null` for a finding. */
  source_line: number | null;
  key: Record<string, string>;
  /** Raw strings exactly as in the source. `{}` for a finding. */
  values: Record<string, string>;
  failed_columns: string[];
  reason: string;
  action: RuleAction;
  other_failed_rules: string[];
}

export interface RecordsPage {
  rule_id: string;
  dataset_id: string;
  run_id: string;
  total: number;
  page: number;
  page_size: number;
  columns: string[];
  records: DqRecord[];
}

export interface RecordsQuery {
  ruleId: string;
  datasetId: string;
  run: string;
  page: number;
  pageSize: number;
  q: string;
}

export const MAX_PAGE_SIZE = 200;
