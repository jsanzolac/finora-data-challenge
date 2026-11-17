/**
 * Period presets for the acquisition page, built from the months and regimes
 * the API returns: the full period, calendar years, quarters, the inferred
 * spend regimes and single months.
 *
 * Multi-month periods hold only the months up to `data_complete_through`, as in
 * finora_gold.v_funnel_period. A single month is always its own period, so a
 * month beyond the watermark can still be inspected (its cost shows as
 * unavailable, with the reason).
 */
import { formatMonth } from "@/lib/format";
import { Ratio } from "./ratio";
import type { AcqMonth, AcqSummary, WonDefinition } from "./types";

export type PeriodKind = "full" | "regime" | "year" | "quarter" | "month";

export interface PeriodOption {
  id: string;
  kind: PeriodKind;
  label: string;
  /** Months in the period, oldest first. */
  months: string[];
  /** A year or quarter with fewer months than the calendar has. */
  partial: boolean;
}

export const FULL_PERIOD = "full";

function quarterOf(month: string): string {
  const [year, mm] = month.split("-");
  return `${year}-Q${Math.ceil(Number(mm) / 3)}`;
}

/** "2022-Q1" -> "Q1 2022". */
export function quarterLabel(id: string): string {
  const [year, quarter] = id.split("-");
  return `${quarter} ${year}`;
}

export function rangeLabel(months: string[]): string {
  if (months.length === 0) return "No months";
  const first = months[0]!;
  const last = months[months.length - 1]!;
  return first === last ? formatMonth(first) : `${formatMonth(first)} – ${formatMonth(last)}`;
}

/** The minimal shape the presets need, so the MRR page can reuse them. */
export interface PeriodSource {
  months: { month: string }[];
  regimes: { id: string; label: string; first_month: string; last_month: string }[];
  run: { data_complete_through: string };
}

export function periodOptions(summary: PeriodSource): PeriodOption[] {
  const all = summary.months.map((month) => month.month);
  const complete = all.filter((month) => month <= summary.run.data_complete_through);
  const options: PeriodOption[] = [{ id: FULL_PERIOD, kind: "full", label: "Full period", months: complete, partial: false }];

  for (const regime of summary.regimes) {
    const months = complete.filter((month) => month >= regime.first_month && month <= regime.last_month);
    if (months.length > 0) options.push({ id: regime.id, kind: "regime", label: regime.label, months, partial: false });
  }

  const years = [...new Set(complete.map((month) => month.slice(0, 4)))];
  for (const year of years) {
    const months = complete.filter((month) => month.startsWith(year));
    options.push({ id: year, kind: "year", label: year, months, partial: months.length < 12 });
  }

  const quarters = [...new Set(complete.map(quarterOf))];
  for (const quarter of quarters) {
    const months = complete.filter((month) => quarterOf(month) === quarter);
    options.push({ id: quarter, kind: "quarter", label: quarterLabel(quarter), months, partial: months.length < 3 });
  }

  for (const month of [...all].reverse()) {
    options.push({ id: month, kind: "month", label: formatMonth(month), months: [month], partial: false });
  }
  return options;
}

export function resolvePeriod(options: PeriodOption[], id: string | null): PeriodOption {
  return options.find((option) => option.id === id) ?? options[0]!;
}

export function wonOf(month: AcqMonth, definition: WonDefinition): number {
  return definition === "new_logo" ? month.won_new_logo : month.won;
}

export interface PeriodTotals {
  months: AcqMonth[];
  won: Ratio;
  /** Null when any month has no total spend. */
  spend: Ratio | null;
  /** First non-null month `cost_null_reason`. */
  costNullReason: string | null;
  lowN: boolean;
}

export function periodTotals(summary: Pick<AcqSummary, "months">, period: PeriodOption, definition: WonDefinition): PeriodTotals {
  const months = summary.months.filter((month) => period.months.includes(month.month));
  let won = 0;
  let spend: Ratio | null = Ratio.ZERO;
  let costNullReason: string | null = null;
  for (const month of months) {
    won += wonOf(month, definition);
    const value = Ratio.tryParse(month.spend_total_value);
    spend = spend && value ? spend.add(value) : null;
    if (costNullReason === null && month.cost_null_reason) costNullReason = month.cost_null_reason;
  }
  return { months, won: Ratio.of(BigInt(won)), spend: months.length > 0 ? spend : null, costNullReason, lowN: won < 10 };
}
