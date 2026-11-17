"use client";

import { Fragment, useState } from "react";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";
import type { DqRecord } from "@/lib/api/types";
import { formatInt } from "@/lib/format";
import { RawValue } from "./CellValue";

export interface OtherRuleLink {
  ruleId: string;
  /** `null` when the rule is not in this run's summary: the chip is shown but does not link. */
  href: string | null;
  /** Plain title, when the run's summary has the rule. */
  title?: string;
}

interface RecordsTableProps {
  records: DqRecord[];
  /** Source columns in file order (`columns` from the API). */
  columns: string[];
  /** A finding has no source row: the table shows the `key` fields instead of the values. */
  finding: boolean;
  /** Status tone of the cell that opened the sheet: failing columns are highlighted in it. */
  tone?: string;
  /** Position of the first record on this page (0-based), for the accessible row index. */
  firstIndex: number;
  otherRuleLink: (ruleId: string) => OtherRuleLink;
  onOpenOtherRule: (ruleId: string) => void;
  caption: string;
}

function keyColumns(records: DqRecord[]): string[] {
  const out: string[] = [];
  for (const record of records) for (const column of Object.keys(record.key)) if (!out.includes(column)) out.push(column);
  return out;
}

/** "NEGATIVE_AMOUNT: the amount is below zero" -> a plain sentence, with the code kept small. */
function Reason({ reason }: { reason: string }) {
  const index = reason.indexOf(":");
  if (index <= 0 || !/^[A-Z0-9_]+$/.test(reason.slice(0, index))) return <span>{reason}</span>;
  const text = reason.slice(index + 1).trim();
  return (
    <span>
      {text.charAt(0).toUpperCase() + text.slice(1)}
      {/[.!?]$/.test(text) ? "" : "."} <span className="font-mono text-sm text-ink-2">({reason.slice(0, index)})</span>
    </span>
  );
}

/**
 * One page of non-compliant records (server-side search and paging, at most 200
 * rows): the source columns only, the failing cells highlighted, and the reason
 * one tap away in an expandable row.
 */
export function RecordsTable({
  records,
  columns,
  finding,
  tone = "fail",
  firstIndex,
  otherRuleLink,
  onOpenOtherRule,
  caption,
}: RecordsTableProps) {
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set());
  const shownColumns = finding ? keyColumns(records) : columns;
  const columnCount = shownColumns.length + 1;

  function toggle(index: number) {
    setOpen((previous) => {
      const next = new Set(previous);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  return (
    <div
      className={clsx(`tone-${tone}`, "max-h-[60dvh] min-h-48 overflow-auto rounded-lg border border-line")}
      data-testid="records-scroll"
      tabIndex={0}
      role="region"
      aria-label={caption}
    >
      <table className="w-full min-w-max border-separate border-spacing-0 text-[0.9375rem]" data-testid="records-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {shownColumns.map((column) => (
              <th
                key={column}
                scope="col"
                className="sticky top-0 z-10 border-b border-line-strong bg-surface px-4 py-3 text-left font-medium whitespace-nowrap text-ink-2"
              >
                {column}
              </th>
            ))}
            <th scope="col" className="sticky top-0 z-10 w-16 border-b border-line-strong bg-surface px-4 py-3 text-right font-medium text-ink-2">
              Why
            </th>
          </tr>
        </thead>
        <tbody>
          {records.map((record, index) => {
            const failed = new Set(record.failed_columns);
            const isOpen = open.has(index);
            const zebra = index % 2 === 0 ? "zebra-a" : "zebra-b";
            const reasonId = `reason-${firstIndex + index}`;
            const where = record.source_line !== null ? `line ${formatInt(record.source_line)}` : `item ${formatInt(firstIndex + index + 1)}`;
            return (
              <Fragment key={`${record.source_line ?? "f"}-${index}`}>
                <tr className={clsx(zebra, "hover:bg-row-hover")} data-testid="record-row">
                  {shownColumns.map((column) => {
                    const isFailed = !finding && failed.has(column);
                    return (
                      <td
                        key={column}
                        className={clsx("px-4 py-3 align-top", isFailed && "bg-[var(--tone-tint)] shadow-[inset_3px_0_0_var(--tone)]")}
                        data-failed={isFailed ? "true" : undefined}
                      >
                        <RawValue value={finding ? record.key[column] : record.values[column]} />
                        {isFailed ? <span className="sr-only"> (fails the rule)</span> : null}
                      </td>
                    );
                  })}
                  <td className="px-2 py-1.5 text-right align-top">
                    <button
                      type="button"
                      className="inline-flex size-9 items-center justify-center rounded-md text-ink-2 hover:bg-surface-3 hover:text-ink"
                      aria-expanded={isOpen}
                      aria-controls={reasonId}
                      aria-label={`Why ${where} fails`}
                      onClick={() => toggle(index)}
                      data-testid="reason-toggle"
                    >
                      <ChevronDown aria-hidden="true" size={18} className={clsx("transition-transform", isOpen && "rotate-180")} />
                    </button>
                  </td>
                </tr>
                <tr id={reasonId} hidden={!isOpen} className={zebra}>
                  <td colSpan={columnCount} className="px-4 pt-0 pb-4">
                    <div className="flex max-w-[60rem] flex-col gap-1.5 border-l-2 border-line-strong pl-3 whitespace-normal" data-testid="record-reason">
                      <p>
                        {record.source_line !== null ? <span className="text-ink-2">Line {formatInt(record.source_line)}: </span> : null}
                        <Reason reason={record.reason} />
                      </p>
                      {record.other_failed_rules.length > 0 ? (
                        <p className="flex flex-wrap items-center gap-1.5 text-ink-2">
                          Also fails:
                          {record.other_failed_rules.map((ruleId) => {
                            const link = otherRuleLink(ruleId);
                            const text = link.title ?? ruleId;
                            return link.href ? (
                              <a
                                key={ruleId}
                                href={link.href}
                                title={ruleId}
                                className="rounded-md border border-line-strong px-2 py-0.5 text-ink underline-offset-4 hover:underline"
                                onClick={(event) => {
                                  if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
                                  event.preventDefault();
                                  onOpenOtherRule(ruleId);
                                }}
                              >
                                {text}
                              </a>
                            ) : (
                              <span key={ruleId} title={ruleId} className="rounded-md border border-line px-2 py-0.5">
                                {text}
                              </span>
                            );
                          })}
                        </p>
                      ) : null}
                    </div>
                  </td>
                </tr>
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function RecordsTableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-px overflow-hidden rounded-lg border border-line" aria-hidden="true">
      <div className="h-11 bg-surface" />
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex h-12 items-center gap-4 px-4">
          <div className="h-3 w-16 rounded bg-surface-3 motion-safe:animate-pulse" />
          <div className="h-3 w-24 rounded bg-surface-3 motion-safe:animate-pulse" />
          <div className="h-3 flex-1 rounded bg-surface-3 motion-safe:animate-pulse" />
        </div>
      ))}
    </div>
  );
}
