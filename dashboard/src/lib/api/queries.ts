"use client";

import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";
import { getRecords, getRuns, getSummary } from "./client";
import type { RecordsQuery, Run, Summary } from "./types";

const LATEST = "latest";
const FOREVER = Number.POSITIVE_INFINITY;

export function useRuns() {
  return useQuery({ queryKey: ["dq", "runs"], queryFn: ({ signal }) => getRuns(signal) });
}

/** `run === null` asks for the latest run. A summary for a named run never changes. */
export function useSummary(run: string | null) {
  const key = run ?? LATEST;
  return useQuery({
    queryKey: ["dq", "summary", key],
    queryFn: ({ signal }) => getSummary(key, signal),
    staleTime: run ? FOREVER : 60_000,
    // Hold the previous run on screen at reduced opacity while the next one loads.
    placeholderData: keepPreviousData,
  });
}

export function useRecords(query: RecordsQuery, enabled: boolean) {
  return useQuery({
    queryKey: ["dq", "records", query.run, query.ruleId, query.datasetId, query.page, query.pageSize, query.q],
    queryFn: ({ signal }) => getRecords(query, signal),
    enabled,
    staleTime: FOREVER,
    placeholderData: keepPreviousData,
  });
}

export interface RuleTrendPoint {
  runId: string;
  asOfMonth: string;
  value: number;
}

/** How many past runs the rule-level trend looks at. One cached summary call per run. */
export const RULE_TREND_RUNS = 8;

/**
 * Compliance of one rule in one department across recent runs.
 *
 * The contract has no per-rule history, so this reads the summaries of the
 * last few succeeded runs up to the selected one (they are immutable and
 * cached, and the selected run's summary is already loaded).
 */
export function useRuleTrend(
  runs: Run[] | undefined,
  selectedRunId: string | undefined,
  ruleId: string,
  datasetId: string,
  enabled: boolean,
): { points: RuleTrendPoint[]; loading: boolean } {
  const succeeded = (runs ?? []).filter((run) => run.status === "succeeded");
  const selectedIndex = succeeded.findIndex((run) => run.run_id === selectedRunId);
  // `runs` is newest first: take the selected run and the ones before it, oldest first.
  const window = selectedIndex >= 0 ? succeeded.slice(selectedIndex, selectedIndex + RULE_TREND_RUNS).reverse() : [];

  const results = useQueries({
    queries: window.map((run) => ({
      queryKey: ["dq", "summary", run.run_id],
      queryFn: ({ signal }: { signal: AbortSignal }) => getSummary(run.run_id, signal),
      staleTime: FOREVER,
      enabled,
    })),
  });

  const points: RuleTrendPoint[] = [];
  results.forEach((result, index) => {
    const run = window[index];
    const summary: Summary | undefined = result.data;
    if (!run || !summary) return;
    const pct = summary.rules.find((rule) => rule.rule_id === ruleId)?.results[datasetId]?.compliance_pct;
    if (typeof pct === "number") points.push({ runId: run.run_id, asOfMonth: run.as_of_month ?? "", value: pct });
  });

  return { points, loading: results.some((result) => result.isLoading) };
}
