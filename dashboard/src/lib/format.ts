const intFormat = new Intl.NumberFormat("en-US");

export function formatInt(value: number): string {
  return intFormat.format(value);
}

/**
 * Percentages arrive as 0-100 with up to 2 decimals. Two decimals are always
 * shown so 99.95 and 100 line up, and a value is never rounded up to 100.00
 * unless it is exactly 100.
 */
export function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  if (value === 100) return "100%";
  const floored = Math.floor(value * 100 + 1e-9) / 100;
  return `${floored.toFixed(2)}%`;
}

/** Signed change in percentage points, e.g. "+0.12 pts" or "−2.94 pts". */
export function formatDeltaPts(delta: number): string {
  const abs = Math.abs(delta).toFixed(2);
  if (delta > 0) return `+${abs} pts`;
  if (delta < 0) return `−${abs} pts`;
  return "0.00 pts";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2024-10" -> "Oct 2024". Anything else is returned unchanged. */
export function formatMonth(month: string | null | undefined): string {
  if (!month) return "–";
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) return month;
  const name = MONTHS[Number(match[2]) - 1];
  return name ? `${name} ${match[1]}` : month;
}

/** ISO-8601 UTC -> "16 Nov 2026, 04:10 UTC". Shown in UTC so everyone reads the same time. */
export function formatDateTimeUtc(iso: string | null | undefined): string {
  if (!iso) return "–";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const day = date.getUTCDate();
  const month = MONTHS[date.getUTCMonth()];
  const year = date.getUTCFullYear();
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");
  return `${day} ${month} ${year}, ${hh}:${mm} UTC`;
}

/** `silver_quality` -> "Silver quality". Used for ids the UI has no label for. */
export function humanize(id: string): string {
  const text = id.replace(/[_-]+/g, " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : id;
}

/** Change in points with an arrow, e.g. "▲ 0.12 pts" or "▼ 2.94 pts". */
export function formatDeltaArrow(delta: number): string {
  const abs = Math.abs(delta).toFixed(2);
  return `${delta > 0 ? "▲" : "▼"} ${abs} pts`;
}

/** ISO-8601 -> "16 Nov 2026" (UTC). */
export function formatDateUtc(iso: string | null | undefined): string {
  if (!iso) return "–";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

/** "1 row" / "2 rows". */
export function plural(count: number, one: string, many: string): string {
  return `${formatInt(count)} ${count === 1 ? one : many}`;
}

/**
 * The first sentence of a rule description: up to the first ". " that is not
 * inside a `code span` and is followed by a capital, a quote, a backtick or "(".
 */
export function firstSentence(text: string): string {
  let inCode = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (char === "`") inCode = !inCode;
    if (inCode || char !== ".") continue;
    const rest = text.slice(i + 1);
    if (/^\s+[A-Z(`"]/.test(rest)) return text.slice(0, i + 1);
  }
  return text;
}

/** "data@finora.test" -> "DA", "new.analyst@x" -> "NA". */
export function initials(email: string): string {
  const local = email.split("@")[0] ?? "";
  const parts = local.split(/[._-]+/).filter(Boolean);
  const letters = parts.length >= 2 ? `${parts[0]?.[0] ?? ""}${parts[1]?.[0] ?? ""}` : local.slice(0, 2);
  return letters.toUpperCase() || "?";
}
