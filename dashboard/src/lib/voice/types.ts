/** Types from contracts/agent_api_contract.md (v1). */

export interface AgentSession {
  signed_url: string;
  agent_id: string;
  /** Short-lived, read-only. Passed to ElevenLabs as `secret__agent_token`; never stored. */
  agent_token: string;
  expires_at: string;
  dynamic_variables: Record<string, string | number | boolean>;
}

export type ResultChartType = "bar" | "line" | "table";

export interface AgentResult {
  result_id: string;
  question: string;
  title_es: string;
  chart: { type: ResultChartType | string; x: string; y: string[]; unit: string };
  columns: string[];
  /** Cells are strings (exact decimals for money) or numbers; "__restricted__" for masked values. */
  rows: (string | number | null)[][];
  sql_hash: string;
  run_id: string;
  created_at: string;
  /** observado / inferido / supuesto / no probado (contract v1.1, semantic layer). */
  evidence?: string | null;
  /** The mandatory caveats, in Spanish. */
  caveats_es?: string[];
}

export type PageId = "dq" | "acquisition" | "mrr";

export const PAGE_HREF: Record<PageId, string> = { dq: "/", acquisition: "/acquisition/", mrr: "/mrr/" };

export const PAGE_LABEL_ES: Record<PageId, string> = { dq: "Calidad de datos", acquisition: "Adquisición", mrr: "MRR" };

/** Result ids are opaque: letters, digits, `_` and `-` only, so they are safe in a path. */
export const RESULT_ID = /^[A-Za-z0-9_-]{1,80}$/;
