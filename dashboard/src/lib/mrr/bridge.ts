/**
 * The contract's period rule (contracts/mrr_api_contract.md v1, "Period rule (UI)"):
 * opening = the first month's opening, closing = the last month's closing, each step =
 * the exact Σ over the months (null if any month is null), timing change = timing(last)
 * − timing(month before first), leakage = the mean discount over the months.
 * The only other arithmetic is grouping steps by driver and the closing − opening change.
 */
import { Ratio } from "@/lib/acq/ratio";
import { periodOptions, type PeriodOption } from "@/lib/acq/periods";
import type { MrrDriver, MrrMonth, MrrStep, MrrSummary } from "./types";
import { TIMING_DRIVER } from "./types";

export const LAST_12 = "last12";

/** "Last 12 months" first (the default), then the Acquisition presets (full, years, quarters, months). */
export function mrrPeriodOptions(summary: MrrSummary): PeriodOption[] {
  const base = periodOptions({ months: summary.months, regimes: [], run: summary.run });
  const complete = base[0]?.months ?? [];
  const last12: PeriodOption = { id: LAST_12, kind: "full", label: "Last 12 months", months: complete.slice(-12), partial: false };
  const full = { ...base[0]!, label: "Full period" };
  return [last12, full, ...base.slice(1)];
}

function money(value: string | null | undefined): Ratio | null {
  return Ratio.tryParse(value ?? null);
}

/** Exact Σ of a nullable money field; null when any value is null (null never means 0). */
export function sumOrNull(values: (string | null | undefined)[]): Ratio | null {
  let total = Ratio.ZERO;
  for (const value of values) {
    const parsed = money(value);
    if (!parsed) return null;
    total = total.add(parsed);
  }
  return total;
}

export function orderedSteps(steps: MrrStep[]): MrrStep[] {
  return [...steps].sort((a, b) => a.order - b.order);
}

export interface StepTotal {
  step: MrrStep;
  value: Ratio | null;
  /** Σ of the monthly customer counts (a customer can count in several months). */
  customers: number | null;
}

export interface DriverTotal {
  driver: MrrDriver;
  /** Σ of the driver's known steps; null when all of them are null. */
  value: Ratio | null;
}

export interface PeriodBridge {
  months: MrrMonth[];
  opening: Ratio | null;
  closing: Ratio | null;
  change: Ratio | null;
  steps: StepTotal[];
  drivers: DriverTotal[];
  timingChange: Ratio | null;
  /** cash(last) − cash(month before first) = Σ steps + the cash timing change. */
  cashChange: Ratio | null;
  leakage: Ratio | null;
  provisionalMonths: string[];
  incomplete: boolean;
}

export function periodBridge(summary: MrrSummary, period: PeriodOption): PeriodBridge {
  const months = summary.months.filter((month) => period.months.includes(month.month));
  const first = months[0];
  const last = months[months.length - 1];
  const firstIndex = first ? summary.months.indexOf(first) : -1;
  const before = firstIndex > 0 ? summary.months[firstIndex - 1] : undefined;
  const incomplete = months.some((month) => !month.is_complete);

  const opening = incomplete ? null : money(first?.opening_mrr_value);
  const closing = incomplete ? null : money(last?.closing_mrr_value);
  const steps: StepTotal[] = orderedSteps(summary.steps).map((step) => {
    const counts = months.map((month) => month.step_customers[step.code] ?? null);
    return {
      step,
      value: incomplete ? null : sumOrNull(months.map((month) => month.step_value[step.code])),
      customers: counts.some((count) => count === null) ? null : counts.reduce<number>((sum, count) => sum + (count ?? 0), 0),
    };
  });

  const timingLast = money(last?.timing_value);
  const timingBefore = money(before?.timing_value);
  const timingChange = timingLast && timingBefore ? timingLast.sub(timingBefore) : null;
  const cashLast = money(last?.cash_value);
  const cashBefore = money(before?.cash_value);

  // A driver is the Σ of its known steps, and null only when every step is null (unobservable,
  // e.g. discounts on cash_proxy). Pricing today = the inferred price steps; list-price changes are null.
  // A driver with no steps at all (timing in contract v1's example) falls back to the cash timing change.
  const drivers: DriverTotal[] = summary.drivers.map((driver) => {
    const own = steps.filter((entry) => entry.step.driver === driver.code);
    if (own.length === 0) return { driver, value: driver.code === TIMING_DRIVER ? timingChange : null };
    const known = own.filter((entry) => entry.value !== null);
    return { driver, value: known.length === 0 ? null : known.reduce((sum, entry) => sum.add(entry.value!), Ratio.ZERO) };
  });

  const discounts = sumOrNull(months.map((month) => month.discount_value));
  return {
    months,
    opening,
    closing,
    change: opening && closing ? closing.sub(opening) : null,
    steps,
    drivers,
    timingChange,
    cashChange: cashLast && cashBefore ? cashLast.sub(cashBefore) : null,
    leakage: discounts && months.length > 0 ? discounts.div(Ratio.of(BigInt(months.length))) : null,
    provisionalMonths: months.filter((month) => month.is_provisional).map((month) => month.month),
    incomplete,
  };
}

/** The bridge closes when opening + Σ known steps = closing. Used by the tests and shown in Details. */
export function bridgeCloses(bridge: PeriodBridge): boolean {
  if (!bridge.opening || !bridge.closing) return false;
  const known = bridge.steps.reduce((sum, entry) => (entry.value ? sum.add(entry.value) : sum), Ratio.ZERO);
  return bridge.opening.add(known).equals(bridge.closing);
}
