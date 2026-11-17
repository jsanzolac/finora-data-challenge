"use client";

import clsx from "clsx";
import type { DatasetSummary, Rule, TrendPoint } from "@/lib/api/types";
import { formatDeltaArrow, formatInt, formatPct, plural } from "@/lib/format";
import { deltaVsPrevious } from "@/lib/ranking";
import { datasetStatus, statusMeta } from "@/lib/status";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusDot } from "@/components/ui/StatusDot";

/** "1 row excluded · 5 flagged", zero parts left out. */
function rowsLine(dataset: DatasetSummary, status: string): string {
  const parts: string[] = [];
  if (dataset.rows_excluded > 0) parts.push(`${plural(dataset.rows_excluded, "row", "rows")} excluded`);
  if (dataset.rows_flagged > 0) {
    parts.push(parts.length > 0 ? `${formatInt(dataset.rows_flagged)} flagged` : `${plural(dataset.rows_flagged, "row", "rows")} flagged`);
  }
  if (parts.length > 0) return parts.join(" · ");
  return status === "pass" ? "No issues" : "No rows excluded or flagged";
}

function DepartmentCard({
  dataset,
  position,
  rules,
  trend,
  runId,
}: {
  dataset: DatasetSummary;
  position: number;
  rules: Rule[];
  trend: TrendPoint[];
  runId: string;
}) {
  const status = datasetStatus(rules, dataset.dataset_id);
  const meta = statusMeta(status);
  const delta = deltaVsPrevious(trend, runId, dataset.dataset_id);
  const showDelta = delta !== null && delta.value !== 0;

  return (
    <article
      className={clsx(`tone-${status}`, "card flex h-full flex-col gap-3 p-6")}
      data-testid="scorecard"
      data-kpi-id={`dq.scorecard.${dataset.dataset_id}`}
      data-dataset={dataset.dataset_id}
      data-rank={position}
      data-status={status}
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-base font-medium text-ink-2">{dataset.label}</h3>
        {showDelta && delta ? (
          <span
            className={clsx("num font-mono text-sm whitespace-nowrap", delta.value > 0 ? "text-pass-ink" : "text-fail-ink")}
            title="Change since the previous run"
            data-testid="delta"
          >
            <span className="sr-only">{delta.value > 0 ? "Up" : "Down"} since the previous run: </span>
            {formatDeltaArrow(delta.value)}
          </span>
        ) : null}
      </div>
      <p className="text-tone num font-mono text-5xl leading-none font-semibold tracking-[-0.06em] md:text-[3.5rem]" data-testid="row-compliance">
        {formatPct(dataset.row_compliance_pct)}
      </p>
      <p className="text-tone flex items-center gap-2 text-base font-semibold" data-status-word={status}>
        <StatusDot status={status} size={10} />
        {meta.label}
      </p>
      <p className="text-[0.9375rem] text-ink-2" data-testid="rows-line">
        {rowsLine(dataset, status)}
      </p>
    </article>
  );
}

/** Three equal cards, most compliant first. Nothing else in the row. */
export function Departments({
  datasets,
  rules,
  trend,
  runId,
}: {
  /** Already ranked, most compliant first. */
  datasets: DatasetSummary[];
  rules: Rule[];
  trend: TrendPoint[];
  runId: string;
}) {
  return (
    <ol className="grid gap-4 md:grid-cols-3" aria-label="Departments, most compliant first">
      {datasets.map((dataset, index) => (
        <li key={dataset.dataset_id} className="min-w-0">
          <DepartmentCard dataset={dataset} position={index + 1} rules={rules} trend={trend} runId={runId} />
        </li>
      ))}
    </ol>
  );
}

export function DepartmentsSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-3" aria-hidden="true">
      {[0, 1, 2].map((index) => (
        <div key={index} className="card flex flex-col gap-4 p-6">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-14 w-48" />
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-5 w-40" />
        </div>
      ))}
    </div>
  );
}
