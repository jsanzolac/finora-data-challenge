import type { CellStatus, Rule, RuleAction, RuleKind, RuleResult } from "@/lib/api/types";
import { humanize } from "@/lib/format";

export type StatusTone = "pass" | "warn" | "fail" | "na";

export interface StatusMeta {
  tone: StatusTone;
  /** Plain-language word shown next to the dot (and read by screen readers in every cell). */
  label: string;
  /** `na` cells are inert: they cannot be focused or opened. */
  interactive: boolean;
}

const STATUS_META: Record<CellStatus, StatusMeta> = {
  pass: { tone: "pass", label: "Good", interactive: true },
  warn: { tone: "warn", label: "Review", interactive: true },
  fail: { tone: "fail", label: "Action needed", interactive: true },
  na: { tone: "na", label: "Doesn't apply", interactive: false },
};

/** The status comes from the API (thresholds live in the approved data rules). An unknown value reads as N/A. */
export function statusMeta(status: string | null | undefined): StatusMeta {
  if (status && Object.prototype.hasOwnProperty.call(STATUS_META, status)) {
    return STATUS_META[status as CellStatus];
  }
  return STATUS_META.na;
}

export const NA_RESULT: RuleResult = { evaluated: 0, failed: 0, compliance_pct: null, status: "na" };

export function resultFor(rule: Rule, datasetId: string): RuleResult {
  return rule.results[datasetId] ?? NA_RESULT;
}

export function cellKey(ruleId: string, datasetId: string): string {
  return `${ruleId}|${datasetId}`;
}

interface BadgeMeta {
  label: string;
  meaning: string;
}

const ACTION_META: Record<RuleAction, BadgeMeta> = {
  exclude: { label: "Exclude", meaning: "the row is kept out of silver and stored for review" },
  flag: { label: "Flag", meaning: "the row stays in silver, marked for review" },
  finding: { label: "Finding", meaning: "something is missing or inconsistent across rows" },
};

export function actionMeta(action: string): BadgeMeta {
  return ACTION_META[action as RuleAction] ?? { label: humanize(action), meaning: humanize(action) };
}

const KIND_META: Record<RuleKind, string> = {
  row: "Row rule",
  finding: "Finding rule",
};

export function kindLabel(kind: string): string {
  return KIND_META[kind as RuleKind] ?? humanize(kind);
}

const SEVERITY: Record<StatusTone, number> = { na: 0, pass: 1, warn: 2, fail: 3 };

export function severity(status: string | null | undefined): number {
  return SEVERITY[statusMeta(status).tone];
}

/**
 * A department's status: the worst status the API gave any rule for it
 * (fail > warn > pass). The UI applies no threshold of its own. `na` when no
 * rule applies.
 */
export function datasetStatus(rules: Rule[], datasetId: string): StatusTone {
  let worst: StatusTone = "na";
  for (const rule of rules) {
    const tone = statusMeta(resultFor(rule, datasetId).status).tone;
    if (SEVERITY[tone] > SEVERITY[worst]) worst = tone;
  }
  return worst;
}
