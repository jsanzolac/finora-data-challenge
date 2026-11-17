"use client";

import { useMemo } from "react";
import clsx from "clsx";
import { Download, Lock } from "lucide-react";
import { formatInt, formatMonth } from "@/lib/format";
import { formatMoneyString } from "@/lib/acq/format";
import { buildMonthlyTable, monthlyCsv, monthlyCsvFilename, type MonthlyCell } from "@/lib/acq/monthly-table";
import type { AcqSummary } from "@/lib/acq/types";
import { Disclosure } from "@/components/ui/Disclosure";

function Cell({ cell }: { cell: MonthlyCell }) {
  if (cell.kind === "restricted") {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-md border border-line-strong bg-surface-2 px-1.5 py-px font-sans text-sm text-ink-2"
        title="HR-sensitive values are visible to Finance only"
        data-testid="restricted-value"
      >
        <Lock aria-hidden="true" size={12} />
        Restricted
      </span>
    );
  }
  if (cell.kind === "int") return <>{formatInt(cell.value)}</>;
  if (cell.kind === "money") return <>{formatMoneyString(cell.value)}</>;
  return <>{formatMonth(cell.value)}</>;
}

function download(text: string, filename: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function MonthlySection({ summary }: { summary: AcqSummary }) {
  const table = useMemo(() => buildMonthlyTable(summary), [summary]);
  const restricted = table.rows.some((row) => row.cells.some((cell) => cell.kind === "restricted"));

  return (
    <section aria-label="Monthly data" data-testid="monthly" data-kpi-id="acq.monthly_table">
      <Disclosure title="Monthly data" testId="monthly-details" flush bodyClassName="flex flex-col gap-3 pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4">
          <p className="text-ink-2">
            {restricted
              ? "One row per month. S&M team, payroll and freelance amounts are visible to Finance only."
              : "One row per month."}
          </p>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => download(monthlyCsv(table), monthlyCsvFilename(summary))}
            data-testid="download-csv"
          >
            <Download aria-hidden="true" size={16} />
            Download CSV
          </button>
        </div>
        <div className="max-h-[32rem] overflow-auto rounded-b-lg border-t border-line" tabIndex={0} role="region" aria-label="Monthly data table, scrolls in both directions">
          <table className="w-max min-w-full border-separate border-spacing-0 text-[0.9375rem]" data-testid="monthly-table">
            <caption className="sr-only">Acquisition by month: new customers, new revenue and S&amp;M spend</caption>
            <thead>
              <tr>
                {table.columns.map((column, index) => (
                  <th
                    key={column.key}
                    scope="col"
                    className={clsx(
                      "sticky top-0 z-10 max-w-36 border-b border-line-strong bg-surface px-3 py-2.5 align-bottom font-medium text-ink-2",
                      column.numeric ? "text-right" : "text-left",
                      index === 0 && "left-0 z-20",
                    )}
                  >
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, rowIndex) => (
                <tr key={row.month} className={rowIndex % 2 === 0 ? "zebra-a" : "zebra-b"}>
                  {row.cells.map((cell, index) =>
                    index === 0 ? (
                      <th
                        key={index}
                        scope="row"
                        className={clsx("sticky left-0 px-3 py-2 text-left font-normal whitespace-nowrap", rowIndex % 2 === 0 ? "zebra-a" : "zebra-b")}
                      >
                        <Cell cell={cell} />
                      </th>
                    ) : (
                      <td key={index} className="num px-3 py-2 text-right font-mono whitespace-nowrap">
                        <Cell cell={cell} />
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Disclosure>
    </section>
  );
}
