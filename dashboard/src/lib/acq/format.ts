/**
 * Display formats for the acquisition page. Exact values (Ratio) are rounded
 * HALF_UP here, at display time only:
 * - estimated counts: 1 decimal ("58,928.6");
 * - money and costs: whole units ("4,786,490"); the currency is not stated, so no symbol;
 * - rates: percent with up to 2 decimals ("80%", "81.25%").
 */
import { Ratio } from "./ratio";

const DASH = "—";
const MINUS = "−";

/** "1234567.5" -> "1,234,567.5". Keeps a leading "-" as a real minus sign. */
export function groupDigits(fixed: string): string {
  const negative = fixed.startsWith("-");
  const body = negative ? fixed.slice(1) : fixed;
  const [whole = "0", fraction] = body.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${negative ? MINUS : ""}${grouped}${fraction !== undefined ? `.${fraction}` : ""}`;
}

export function formatExact(value: Ratio | null | undefined, places: number): string {
  if (!value) return DASH;
  return groupDigits(value.toFixed(places));
}

/** Estimated stage counts: 1 decimal. */
export function formatCount(value: Ratio | null | undefined): string {
  return formatExact(value, 1);
}

/** Money in whole units. */
export function formatMoney(value: Ratio | null | undefined): string {
  return formatExact(value, 0);
}

/** A decimal string from the API, in whole units, or "—". */
export function formatMoneyString(value: string | null | undefined): string {
  return formatMoney(Ratio.tryParse(value ?? null));
}

/** Short money for axes and headlines: 8,146,316 -> "8.1M", 200,000,000 -> "200M", 67,499 -> "67.5K". */
export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  const absolute = Math.abs(value);
  const sign = value < 0 ? MINUS : "";
  const units: [number, string][] = [
    [1e9, "B"],
    [1e6, "M"],
    [1e3, "K"],
  ];
  for (const [size, suffix] of units) {
    if (absolute >= size) {
      const scaled = absolute / size;
      const text = scaled >= 100 ? scaled.toFixed(0) : scaled.toFixed(1).replace(/\.0$/, "");
      return `${sign}${text}${suffix}`;
    }
  }
  return `${sign}${absolute.toFixed(0)}`;
}

/** A rate (0..1) as a percent with up to 2 decimals: 0.8 -> "80", 0.8125 -> "81.25". */
export function ratePercentText(rate: Ratio): string {
  return rate.mul(Ratio.of(100n)).toFixed(2).replace(/\.?0+$/, "");
}

/** Signed with a real minus: "+226.3", "−7,366.1". */
export function formatSigned(value: Ratio | null | undefined, places: number): string {
  if (!value) return DASH;
  const text = formatExact(value, places);
  return value.sign() > 0 ? `+${text}` : text;
}

/** Signed percent: "+14.3%". */
export function formatSignedPct(value: Ratio | null | undefined, places = 1): string {
  if (!value) return DASH;
  return `${formatSigned(value, places)}%`;
}

/** Correlation r with its sign and 2 decimals: "+0.53", "−0.48". */
export function formatR(r: number | null | undefined): string {
  if (r === null || r === undefined || !Number.isFinite(r)) return DASH;
  const text = Math.abs(r).toFixed(2);
  if (Number(text) === 0) return "0.00";
  return `${r < 0 ? MINUS : "+"}${text}`;
}

const COST_REASONS: Record<string, string> = {
  won_zero: "No new customers in this period, so nothing can be worked back from Won.",
  spend_missing: "Spend is missing for at least one month in this period.",
  beyond_data_complete_through: "This period goes past the last month with complete data.",
  unit_tripwire: "A month in this period failed the unit check on spend.",
  won_incomplete: "New customers are incomplete for at least one month in this period.",
};

export function costReasonText(reason: string | null | undefined): string {
  if (!reason) return "";
  return COST_REASONS[reason] ?? `Cost unavailable (${reason}).`;
}

/** Signed short money for a change: "+5.3M", "−1.7M", "0". */
export function formatSignedCompact(value: Ratio | null | undefined): string {
  if (!value) return DASH;
  if (value.isZero()) return "0";
  const text = formatCompact(Math.abs(value.toNumber()));
  return `${value.sign() > 0 ? "+" : MINUS}${text}`;
}
