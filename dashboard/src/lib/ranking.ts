import type { DatasetSummary, Rule, TrendPoint } from "@/lib/api/types";
import { resultFor, severity } from "@/lib/status";

/**
 * Departments from most to least compliant. The API's `rank` decides; row
 * compliance, then the label, break a tie or stand in for a missing rank.
 */
export function rankDatasets(datasets: DatasetSummary[]): DatasetSummary[] {
  return [...datasets].sort((a, b) => {
    const ra = Number.isFinite(a.rank) ? a.rank : Number.POSITIVE_INFINITY;
    const rb = Number.isFinite(b.rank) ? b.rank : Number.POSITIVE_INFINITY;
    if (ra !== rb) return ra - rb;
    if (a.row_compliance_pct !== b.row_compliance_pct) return b.row_compliance_pct - a.row_compliance_pct;
    return a.label.localeCompare(b.label);
  });
}

export function trendValue(point: TrendPoint, datasetId: string): number | null {
  const value = point[datasetId];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export interface TrendSeriesPoint {
  runId: string;
  asOfMonth: string;
  value: number;
}

/** One department's trend, oldest first, skipping runs where it has no value. */
export function trendSeries(trend: TrendPoint[], datasetId: string): TrendSeriesPoint[] {
  const points: TrendSeriesPoint[] = [];
  for (const point of trend) {
    const value = trendValue(point, datasetId);
    if (value !== null) points.push({ runId: point.run_id, asOfMonth: point.as_of_month, value });
  }
  return points;
}

export interface Delta {
  value: number;
  direction: "up" | "down" | "flat";
  previousRunId: string;
}

/**
 * Change in row compliance against the run before `runId` in the trend
 * (percentage points). `null` when the run is the first one or is not in the trend.
 */
export function deltaVsPrevious(trend: TrendPoint[], runId: string, datasetId: string): Delta | null {
  const series = trendSeries(trend, datasetId);
  const index = series.findIndex((p) => p.runId === runId);
  if (index <= 0) return null;
  const current = series[index];
  const previous = series[index - 1];
  if (!current || !previous) return null;
  const value = Math.round((current.value - previous.value) * 100) / 100;
  return { value, direction: value > 0 ? "up" : value < 0 ? "down" : "flat", previousRunId: previous.runId };
}

/* ------------------------------------------------------------- rules */

/** A rule has an issue in a department when the API status there is warn or fail, or it has failures. */
export function hasIssueIn(rule: Rule, datasetId: string): boolean {
  const result = resultFor(rule, datasetId);
  return result.status === "warn" || result.status === "fail" || result.failed > 0;
}

export function hasIssue(rule: Rule, datasetIds: string[]): boolean {
  return datasetIds.some((id) => hasIssueIn(rule, id));
}

/** Lowest compliance across the departments the rule applies to. `null` when it applies to none. */
export function worstCompliance(rule: Rule, datasetIds: string[]): number | null {
  let worst: number | null = null;
  for (const id of datasetIds) {
    const pct = resultFor(rule, id).compliance_pct;
    if (pct === null || pct === undefined) continue;
    if (worst === null || pct < worst) worst = pct;
  }
  return worst;
}

function worstSeverity(rule: Rule, datasetIds: string[]): number {
  return Math.max(0, ...datasetIds.map((id) => severity(resultFor(rule, id).status)));
}

/**
 * Worst first: the worst API status in any department (fail, then warn, then
 * pass), then the lowest compliance, then the API's own order. Never mutates.
 */
export function sortWorstFirst(rules: Rule[], datasetIds: string[]): Rule[] {
  return rules
    .map((rule, index) => ({ rule, index, sev: worstSeverity(rule, datasetIds), pct: worstCompliance(rule, datasetIds) }))
    .sort((a, b) => {
      if (a.sev !== b.sev) return b.sev - a.sev;
      if (a.pct !== b.pct) {
        if (a.pct === null) return 1;
        if (b.pct === null) return -1;
        return a.pct - b.pct;
      }
      return a.index - b.index;
    })
    .map((entry) => entry.rule);
}

/** What the rules table shows: issues only (the default) or every rule, worst first either way. */
export function visibleRules(rules: Rule[], datasetIds: string[], issuesOnly: boolean): Rule[] {
  const kept = issuesOnly ? rules.filter((rule) => hasIssue(rule, datasetIds)) : rules;
  return sortWorstFirst(kept, datasetIds);
}
