"use client";

import { useMemo, useState } from "react";
import clsx from "clsx";
import { ChevronLeft, ChevronRight, Download } from "lucide-react";
import { formatInt, formatMonth, humanize } from "@/lib/format";
import { formatMoneyString, formatSignedCompact } from "@/lib/acq/format";
import { Ratio } from "@/lib/acq/ratio";
import { buildMrrTable, mrrCsv } from "@/lib/mrr/monthly";
import { orderedSteps } from "@/lib/mrr/bridge";
import { useMrrMovements } from "@/lib/mrr/queries";
import type { MrrSummary } from "@/lib/mrr/types";
import { Disclosure } from "@/components/ui/Disclosure";
import { ErrorState } from "@/components/ui/ErrorState";
import { PlainSelect } from "@/components/ui/PlainSelect";
import { Skeleton } from "@/components/ui/Skeleton";

const PAGE_SIZE = 20;
const ALL = "all";

const FLAG_TEXT: Record<string, string> = {
  candidate_list_price_change: "Possible list-price change",
  temporary_dip: "Comes back within 3 months",
  one_off_spike: "One-off, comes back within 3 months",
  late_price_step: "Price step billed a month late",
};

/** Customer-level movements, largest first, filtered and paged by the API. Loaded only when opened. */
export function TopMovers({ summary, from, to, run }: { summary: MrrSummary; from: string; to: string; run: string | null }) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(ALL);
  const [page, setPage] = useState(1);
  const query = { from, to, run: run ?? "latest", steps: step === ALL ? [] : [step], page, pageSize: PAGE_SIZE };
  const movements = useMrrMovements(query, open);
  const data = movements.data;
  const steps = orderedSteps(summary.steps).filter((entry) => summary.drivers.find((driver) => driver.code === entry.driver)?.available);
  const label = (code: string) => summary.steps.find((entry) => entry.code === code)?.label ?? humanize(code);
  const driverLabel = (code: string) => summary.drivers.find((entry) => entry.code === code)?.label ?? humanize(code);
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <Disclosure title="Top movers" testId="movers-details" onToggle={setOpen} bodyClassName="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <PlainSelect
          label="Movement"
          value={step}
          onValueChange={(value) => {
            setStep(value);
            setPage(1);
          }}
          groups={[{ items: [{ value: ALL, text: "All movements" }, ...steps.map((entry) => ({ value: entry.code, text: entry.label }))] }]}
          testId="movers-step"
          className="w-full sm:w-64"
        />
        <p className="text-sm text-ink-2" data-testid="movers-range">
          {data ? `${formatInt(data.total)} movements, ${formatMonth(from)} – ${formatMonth(to)}, largest first` : "Loading the movements"}
        </p>
      </div>
      {movements.isError && !data ? (
        <ErrorState title="Couldn't load the movements" message={movements.error instanceof Error ? movements.error.message : "The request failed."} onRetry={() => void movements.refetch()} />
      ) : !data ? (
        <div className="flex flex-col gap-2" aria-hidden="true">
          {Array.from({ length: 5 }, (_, index) => (
            <Skeleton key={index} className="h-9 rounded-md" />
          ))}
        </div>
      ) : (
        <div className={clsx("overflow-x-auto rounded-lg border border-line", movements.isPlaceholderData && "opacity-60")} tabIndex={0} role="region" aria-label="Top movers table, scrolls sideways on small screens">
          <table className="w-full min-w-[46rem] border-separate border-spacing-0 text-[0.9375rem]" data-testid="movers-table">
            <caption className="sr-only">Customer movements in the period, largest change first</caption>
            <thead>
              <tr className="text-ink-2">
                {["Customer", "Month", "Movement", "Driver", "Before → after", "Change", "Note"].map((head, index) => (
                  <th key={head} scope="col" className={clsx("border-b border-line-strong bg-surface px-3 py-2.5 font-medium", index >= 4 && index <= 5 ? "text-right" : "text-left")}>
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.movements.map((row, index) => (
                <tr key={`${row.customer_id}-${row.month}-${row.step}`} className={index % 2 === 0 ? "zebra-a" : "zebra-b"} data-testid="mover-row">
                  <th scope="row" className="num px-3 py-2 text-left font-mono font-normal">#{row.customer_id}</th>
                  <td className="px-3 py-2 whitespace-nowrap">{formatMonth(row.month)}</td>
                  <td className="px-3 py-2">{label(row.step)}</td>
                  <td className="px-3 py-2 text-ink-2">
                    {driverLabel(row.driver)}
                    {row.inferred ? " (inferred)" : ""}
                  </td>
                  <td className="num px-3 py-2 text-right font-mono whitespace-nowrap">
                    {formatMoneyString(row.mrr_before_value)} → {formatMoneyString(row.mrr_after_value)}
                  </td>
                  <td className="num px-3 py-2 text-right font-mono font-semibold whitespace-nowrap">{formatSignedCompact(Ratio.tryParse(row.change_value))}</td>
                  <td className="px-3 py-2 text-sm text-ink-2">{row.flags.map((flag) => FLAG_TEXT[flag] ?? humanize(flag)).join("; ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && data.total > PAGE_SIZE ? (
        <nav className="flex items-center justify-end gap-2" aria-label="Movement pages">
          <span className="text-sm text-ink-2" data-testid="movers-page">
            Page {page} of {formatInt(pages)}
          </span>
          <button type="button" className="btn-secondary px-2.5" disabled={page <= 1} onClick={() => setPage((value) => value - 1)} aria-label="Previous page">
            <ChevronLeft aria-hidden="true" size={16} />
          </button>
          <button type="button" className="btn-secondary px-2.5" disabled={page >= pages} onClick={() => setPage((value) => value + 1)} aria-label="Next page" data-testid="movers-next">
            <ChevronRight aria-hidden="true" size={16} />
          </button>
        </nav>
      ) : null}
    </Disclosure>
  );
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

/** The bridge for every month, with CSV download. Null values read "not available". */
export function MonthlyMrr({ summary }: { summary: MrrSummary }) {
  const table = useMemo(() => buildMrrTable(summary), [summary]);
  return (
    <Disclosure title="Monthly data" testId="mrr-monthly-details" kpiId="mrr.monthly_table" flush bodyClassName="flex flex-col gap-3 pt-4">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4">
        <p className="text-ink-2">One row per month: the bridge, cash and timing.</p>
        <button type="button" className="btn-secondary" onClick={() => download(mrrCsv(table), `finora-mrr-monthly-${summary.run.as_of_month}.csv`)} data-testid="mrr-download-csv">
          <Download aria-hidden="true" size={16} />
          Download CSV
        </button>
      </div>
      <div className="max-h-[32rem] overflow-auto rounded-b-lg border-t border-line" tabIndex={0} role="region" aria-label="Monthly MRR table, scrolls in both directions">
        <table className="w-max min-w-full border-separate border-spacing-0 text-[0.9375rem]" data-testid="mrr-monthly-table">
          <caption className="sr-only">MRR bridge by month</caption>
          <thead>
            <tr>
              {table.columns.map((column, index) => (
                <th key={column.key} scope="col" className={clsx("sticky top-0 z-10 max-w-32 border-b border-line-strong bg-surface px-3 py-2.5 align-bottom font-medium text-ink-2", index === 0 ? "left-0 z-20 text-left" : "text-right")}>
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
                    <th key={index} scope="row" className={clsx("sticky left-0 px-3 py-2 text-left font-normal whitespace-nowrap", rowIndex % 2 === 0 ? "zebra-a" : "zebra-b")}>
                      {formatMonth(String(cell))}
                    </th>
                  ) : (
                    <td key={index} className="num px-3 py-2 text-right font-mono whitespace-nowrap">
                      {cell === null ? (
                        <span className="font-sans text-sm text-ink-2">n/a</span>
                      ) : typeof cell === "boolean" ? (
                        <span className="font-sans">{cell ? "Yes" : "No"}</span>
                      ) : typeof cell === "number" ? (
                        formatInt(cell)
                      ) : (
                        formatMoneyString(cell)
                      )}
                    </td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Disclosure>
  );
}
