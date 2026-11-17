/** The monthly MRR table (one row per month, every step from the API) and its CSV. */
import { csvField } from "@/lib/acq/monthly-table";
import { orderedSteps } from "./bridge";
import type { MrrSummary } from "./types";

export interface MrrColumn {
  key: string;
  label: string;
}

export interface MrrTable {
  columns: MrrColumn[];
  rows: { month: string; cells: (string | number | boolean | null)[] }[];
}

export function buildMrrTable(summary: MrrSummary): MrrTable {
  const steps = orderedSteps(summary.steps);
  const columns: MrrColumn[] = [
    { key: "month", label: "Month" },
    { key: "opening", label: "Opening MRR" },
    ...steps.map((step) => ({ key: step.code, label: step.label })),
    { key: "closing", label: "Closing MRR" },
    { key: "cash", label: "Cash" },
    { key: "timing", label: "Timing (cash − MRR)" },
    { key: "customers", label: "Customers at close" },
    { key: "provisional", label: "Provisional" },
  ];
  const rows = summary.months.map((month) => ({
    month: month.month,
    cells: [
      month.month,
      month.opening_mrr_value,
      ...steps.map((step) => month.step_value[step.code] ?? null),
      month.closing_mrr_value,
      month.cash_value,
      month.timing_value,
      month.customers_closing,
      month.is_provisional,
    ],
  }));
  return { columns, rows };
}

/** Exact values; a null (unknown) cell is "not available", never 0. */
export function mrrCsv(table: MrrTable): string {
  const lines = [table.columns.map((column) => csvField(column.label)).join(",")];
  for (const row of table.rows) {
    lines.push(
      row.cells
        .map((cell) => (cell === null ? "not available" : typeof cell === "boolean" ? (cell ? "yes" : "no") : csvField(String(cell))))
        .join(","),
    );
  }
  return `${lines.join("\r\n")}\r\n`;
}
