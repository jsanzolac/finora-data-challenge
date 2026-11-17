/**
 * The user's monthly table (gold v_acquisition_month, plus the HR columns for
 * Finance) and its CSV download. The table holds only what the API returned for
 * this role: masked HR values stay "Restricted" in the CSV too.
 */
import { formatMonth } from "@/lib/format";
import { RESTRICTED_VALUE } from "@/lib/api/types";
import type { AcqSummary } from "./types";

export type MonthlyCell = { kind: "int"; value: number } | { kind: "money"; value: string | null } | { kind: "restricted" } | { kind: "text"; value: string };

export interface MonthlyColumn {
  key: string;
  label: string;
  numeric: boolean;
}

export interface MonthlyTable {
  columns: MonthlyColumn[];
  rows: { month: string; cells: MonthlyCell[] }[];
}

function money(value: string | null | undefined): MonthlyCell {
  if (value === RESTRICTED_VALUE) return { kind: "restricted" };
  return { kind: "money", value: value ?? null };
}

export function buildMonthlyTable(summary: AcqSummary): MonthlyTable {
  const columns: MonthlyColumn[] = [
    { key: "month", label: "Month", numeric: false },
    { key: "won", label: "Won", numeric: true },
    { key: "won_new_logo", label: "Won, without probably active", numeric: true },
    ...summary.industries.map((industry) => ({ key: `won_${industry.code}`, label: `Won, ${industry.label}`, numeric: true })),
    { key: "new_revenue_value", label: "New revenue", numeric: true },
    ...summary.spend_categories.map((category) => ({ key: `spend_${category.code}`, label: category.label, numeric: true })),
    { key: "spend_people_value", label: "People spend", numeric: true },
    { key: "spend_total_value", label: "Total spend", numeric: true },
  ];
  const rows = summary.months.map((month) => ({
    month: month.month,
    cells: [
      { kind: "text", value: month.month } as MonthlyCell,
      { kind: "int", value: month.won } as MonthlyCell,
      { kind: "int", value: month.won_new_logo } as MonthlyCell,
      ...summary.industries.map((industry) => ({ kind: "int", value: month.won_by_industry[industry.code] ?? 0 }) as MonthlyCell),
      money(month.new_revenue_value),
      ...summary.spend_categories.map((category) => money(month.spend_value[category.code])),
      money(month.spend_people_value),
      money(month.spend_total_value),
    ],
  }));
  return { columns, rows };
}

export function csvField(text: string): string {
  // Quote when needed, and neutralise spreadsheet formulas (a cell starting with = + - @).
  const safe = /^[=+@]/.test(text) || (/^-/.test(text) && !/^-\d/.test(text)) ? `'${text}` : text;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

/** CSV with exact values (no grouping, no rounding); masked cells read "Restricted". */
export function monthlyCsv(table: MonthlyTable): string {
  const lines = [table.columns.map((column) => csvField(column.label)).join(",")];
  for (const row of table.rows) {
    lines.push(
      row.cells
        .map((cell) => {
          if (cell.kind === "restricted") return "Restricted";
          if (cell.kind === "int") return String(cell.value);
          if (cell.kind === "money") return csvField(cell.value ?? "");
          return csvField(cell.value);
        })
        .join(","),
    );
  }
  return `${lines.join("\r\n")}\r\n`;
}

export function monthlyCsvFilename(summary: AcqSummary): string {
  return `finora-acquisition-monthly-${summary.run.as_of_month}.csv`;
}

export function monthLabel(month: string): string {
  return formatMonth(month);
}
