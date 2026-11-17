/**
 * The plain-words reading of the spend vs new-customers correlations.
 *
 * The first thing to read is finora_gold.v_corr_signal_summary (gold model
 * §7.4): how many tests cross the 5% line, against how many would by chance.
 * Level correlations share a trend and a June-2023 break with Won, so the
 * reading uses the company-level tests once the trend is removed (`diff`) and
 * within each spend period (`within_regime`).
 *
 * "More than chance" is a one-sided binomial tail at 5%: P(X ≥ signals) with
 * X ~ Binomial(tests with r, 0.05). The tests are not independent (adjacent lags
 * overlap), so this is a screen for the headline, not a significance claim.
 */
import type { CorrelationRow, SignalSummaryRow, WonDefinition } from "./types";

export const CHANCE_ALPHA = 0.05;

/** P(X ≥ k) for X ~ Binomial(n, p). */
export function binomialTail(n: number, k: number, p: number): number {
  if (k <= 0) return 1;
  if (k > n) return 0;
  let below = 0;
  let term = Math.pow(1 - p, n); // P(X = 0)
  for (let i = 0; i < k; i += 1) {
    below += term;
    term = (term * (n - i) * p) / ((i + 1) * (1 - p));
  }
  return Math.max(0, 1 - below);
}

export function aboveChance(row: Pick<SignalSummaryRow, "tests_with_r" | "signals">): boolean {
  return row.tests_with_r > 0 && binomialTail(row.tests_with_r, row.signals, CHANCE_ALPHA) < CHANCE_ALPHA;
}

export function findSummary(
  rows: SignalSummaryRow[],
  method: string,
  definition: WonDefinition,
  scopeType: "company" | "industry",
): SignalSummaryRow | undefined {
  return rows.find((row) => row.method === method && row.won_definition === definition && row.scope_type === scopeType);
}

export interface SignalReading {
  /** True when no company-level test family beyond the raw levels has more signals than chance gives. */
  noUsableRelationship: boolean;
  level?: SignalSummaryRow;
  diff?: SignalSummaryRow;
  withinRegime?: SignalSummaryRow;
}

export function readSignals(rows: SignalSummaryRow[], definition: WonDefinition): SignalReading {
  const level = findSummary(rows, "level", definition, "company");
  const diff = findSummary(rows, "diff", definition, "company");
  const withinRegime = findSummary(rows, "within_regime", definition, "company");
  const detrended = [diff, withinRegime].filter((row): row is SignalSummaryRow => Boolean(row));
  return {
    noUsableRelationship: detrended.length > 0 && detrended.every((row) => !aboveChance(row)),
    level,
    diff,
    withinRegime,
  };
}

/** "about 2" for 2.2; "about 13" for 13.2. */
export function aboutChance(expected: number): string {
  return `about ${Math.round(expected)}`;
}

export interface GridRow {
  series: string;
  cells: (CorrelationRow | undefined)[];
}

/** Series × lag grid for one definition, scope and method, in the order the series first appear. */
export function correlationGrid(
  rows: CorrelationRow[],
  definition: WonDefinition,
  scope: string,
  method: string,
): { lags: number[]; rows: GridRow[] } {
  const subset = rows.filter((row) => row.won_definition === definition && row.scope === scope && row.method === method);
  const lags = [...new Set(subset.map((row) => row.lag))].sort((a, b) => a - b);
  const series = [...new Set(subset.map((row) => row.series))];
  return {
    lags,
    rows: series.map((name) => ({
      series: name,
      cells: lags.map((lag) => subset.find((row) => row.series === name && row.lag === lag)),
    })),
  };
}
