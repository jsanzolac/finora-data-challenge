"use client";

import { useEffect, useId, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ChevronDown, ChevronLeft, ChevronRight, Link2, Search, X } from "lucide-react";
import clsx from "clsx";
import type { DatasetSummary, Rule, RuleResult, Run } from "@/lib/api/types";
import { MAX_PAGE_SIZE } from "@/lib/api/types";
import { useRecords, useRuleTrend } from "@/lib/api/queries";
import { firstSentence, formatInt, formatMonth, formatPct, humanize } from "@/lib/format";
import { actionMeta, kindLabel, resultFor, statusMeta } from "@/lib/status";
import { PAGE_SIZES, type UrlState, type UrlUpdateMode } from "@/lib/url-state";
import { ErrorState } from "@/components/ui/ErrorState";
import { RichText } from "@/components/ui/RichText";
import { StatusDot } from "@/components/ui/StatusDot";
import { Sparkline } from "@/components/overview/Sparkline";
import { RecordsTable, RecordsTableSkeleton, type OtherRuleLink } from "./RecordsTable";

const SEARCH_DEBOUNCE_MS = 300;

interface RecordsSheetProps {
  open: boolean;
  rule: Rule | undefined;
  /** Every rule in the run, for the plain titles of "Also fails" links. */
  allRules: Rule[];
  ruleId: string;
  datasetId: string;
  /** Departments in ranked order, with their API labels. */
  datasets: DatasetSummary[];
  runId: string;
  runs: Run[] | undefined;
  url: UrlState;
  update: (patch: Partial<UrlState>, mode?: UrlUpdateMode) => void;
  hrefWith: (patch: Partial<UrlState>) => string;
  onClose: () => void;
  /** Called after the sheet has closed, to put focus back where it came from. */
  onCloseFocus: (ruleId: string, datasetId: string) => void;
}

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/**
 * A search icon that opens a search box. Types freely and writes `q` to the URL
 * after a pause (replace, so the back button is not flooded). Escape in a
 * non-empty box clears it; in an empty box it closes the sheet.
 */
function RecordSearch({ q, onCommit }: { q: string; onCommit: (value: string) => void }) {
  const [expanded, setExpanded] = useState(Boolean(q));
  const [draft, setDraft] = useState(q);
  const [synced, setSynced] = useState(q);
  const inputRef = useRef<HTMLInputElement>(null);
  // The URL changed from outside (back button, a link): show what the URL says.
  if (q !== synced) {
    setSynced(q);
    setDraft(q);
    if (q && !expanded) setExpanded(true);
  }
  const debounced = useDebounced(draft, SEARCH_DEBOUNCE_MS);
  const commitRef = useRef(onCommit);
  useEffect(() => {
    commitRef.current = onCommit;
  });
  useEffect(() => {
    if (debounced.trim() !== synced.trim()) commitRef.current(debounced.trim());
  }, [debounced, synced]);

  if (!expanded) {
    return (
      <button
        type="button"
        className="btn-ghost size-10 px-0"
        aria-label="Search records"
        aria-expanded={false}
        onClick={() => {
          setExpanded(true);
          window.setTimeout(() => inputRef.current?.focus(), 0);
        }}
        data-testid="records-search-toggle"
      >
        <Search aria-hidden="true" size={18} />
      </button>
    );
  }

  return (
    <label className="relative w-full sm:w-72">
      <span className="sr-only">Search records</span>
      <Search aria-hidden="true" size={16} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3" />
      <input
        ref={inputRef}
        type="search"
        className="field pl-9"
        placeholder="Search these records"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape" && draft) {
            event.stopPropagation();
            event.preventDefault();
            setDraft("");
          }
        }}
        data-testid="records-search"
      />
    </label>
  );
}

function CopyLinkButton() {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  useEffect(() => {
    if (state === "idle") return;
    const timer = window.setTimeout(() => setState("idle"), 2500);
    return () => window.clearTimeout(timer);
  }, [state]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setState("copied");
    } catch {
      setState("failed");
    }
  }

  return (
    <>
      <button type="button" className="btn-secondary" onClick={() => void copy()} data-testid="copy-link">
        <Link2 aria-hidden="true" size={16} />
        {state === "copied" ? "Link copied" : "Copy link"}
      </button>
      <span className="sr-only" role="status" aria-live="polite">
        {state === "copied" ? "Link copied to the clipboard" : state === "failed" ? "Couldn't copy. Copy the address bar instead." : ""}
      </span>
    </>
  );
}

/** "252 of 66,659 rows fail · 99.62%" */
function countLine(rule: Rule, result: RuleResult): string {
  const unit = rule.kind === "finding" ? "checks" : "rows";
  if (result.failed === 0) return `No ${unit} fail · ${formatPct(result.compliance_pct)}`;
  const verb = result.failed === 1 ? "fails" : "fail";
  return `${formatInt(result.failed)} of ${formatInt(result.evaluated)} ${unit} ${verb} · ${formatPct(result.compliance_pct)}`;
}

function DetailRow({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-[12rem_minmax(0,1fr)] sm:gap-4">
      <dt className="text-ink-2">{term}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

export function RecordsSheet({
  open,
  rule,
  allRules,
  ruleId,
  datasetId,
  datasets,
  runId,
  runs,
  url,
  update,
  hrefWith,
  onClose,
  onCloseFocus,
}: RecordsSheetProps) {
  const titleId = useId();
  const headingRef = useRef<HTMLDivElement>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const dataset = datasets.find((entry) => entry.dataset_id === datasetId);
  const result = rule ? resultFor(rule, datasetId) : undefined;
  const meta = statusMeta(result?.status);
  const applicable = Boolean(rule && dataset && meta.interactive);
  const pageSize = Math.min(MAX_PAGE_SIZE, url.size);

  const records = useRecords({ ruleId, datasetId, run: runId, page: url.page, pageSize, q: url.q }, open && applicable);
  const trend = useRuleTrend(runs, runId, ruleId, datasetId, open && applicable && detailsOpen);

  const page = records.data;
  const total = page?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (url.page - 1) * pageSize + 1;
  const to = Math.min(total, url.page * pageSize);
  const isFinding = rule?.kind === "finding";
  const labelOf = (id: string) => datasets.find((entry) => entry.dataset_id === id)?.label ?? humanize(id);

  // A page past the end (the data changed, or a hand-edited link) goes to the last page.
  useEffect(() => {
    if (page && total > 0 && url.page > pages) update({ page: pages }, "replace");
  }, [page, total, url.page, pages, update]);

  const otherRuleLink = (otherId: string): OtherRuleLink => {
    const other = allRules.find((entry) => entry.rule_id === otherId);
    return {
      ruleId: otherId,
      href: other ? hrefWith({ rule: otherId, dataset: datasetId, q: "", page: 1 }) : null,
      title: other?.title,
    };
  };
  const openOtherRule = (otherId: string) => update({ rule: otherId, dataset: datasetId, q: "", page: 1 }, "push");

  return (
    <Dialog.Root open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay-enter fixed inset-0 z-40 bg-overlay" />
        <Dialog.Content
          aria-labelledby={titleId}
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            headingRef.current?.focus();
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            onCloseFocus(ruleId, datasetId);
          }}
          className="sheet-enter fixed inset-0 z-50 flex flex-col bg-bg shadow-panel outline-none md:inset-y-0 md:right-0 md:left-auto md:w-[min(60rem,94vw)] md:border-l md:border-line-strong"
          data-testid="records-sheet"
        >
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
            <div className="flex items-start gap-4 px-5 pt-6 pb-5 md:px-8">
              <div ref={headingRef} tabIndex={-1} className="flex min-w-0 flex-1 flex-col gap-2 outline-none">
                <Dialog.Title id={titleId} className="text-2xl leading-tight font-semibold">
                  {rule ? rule.title : "Rule not found"}
                  {dataset ? <span className="font-normal text-ink-2"> · {dataset.label}</span> : null}
                </Dialog.Title>
                {rule ? (
                  <p className="max-w-[65ch] text-base leading-relaxed text-ink-2" data-testid="rule-sentence">
                    <RichText text={firstSentence(rule.description)} />
                  </p>
                ) : null}
                {rule && result && applicable ? (
                  <p className={clsx(`tone-${meta.tone}`, "text-tone num flex items-center gap-2 text-lg font-semibold")} data-testid="records-summary">
                    <StatusDot status={result.status} size={10} />
                    {countLine(rule, result)}
                    <span className="sr-only">, {meta.label}</span>
                  </p>
                ) : null}
              </div>
              <Dialog.Close asChild>
                <button type="button" className="btn-ghost size-10 shrink-0 px-0" aria-label="Close" data-testid="close-sheet">
                  <X aria-hidden="true" size={20} />
                </button>
              </Dialog.Close>
            </div>

            <div className="flex flex-col gap-4 px-5 pb-8 md:px-8">
              {!rule || !dataset ? (
                <ErrorState
                  title="Nothing to show"
                  message={!rule ? `This rule (${ruleId}) is not in the selected run.` : `This department (${datasetId}) is not in the selected run.`}
                  action={
                    <Dialog.Close asChild>
                      <button type="button" className="btn-secondary">
                        Back to the overview
                      </button>
                    </Dialog.Close>
                  }
                />
              ) : !applicable || !result ? (
                <div className="card p-5">
                  <p className="text-base">
                    This rule doesn&apos;t apply to {dataset.label}
                    {rule.applies_to.length > 0 ? `. It applies to ${rule.applies_to.map(labelOf).join(", ")}.` : "."}
                  </p>
                </div>
              ) : (
                <section aria-label="Records" className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <RecordSearch key={`${ruleId}|${datasetId}`} q={url.q} onCommit={(value) => update({ q: value, page: 1 }, "replace")} />
                    <label className="flex items-center gap-2 text-[0.9375rem] text-ink-2">
                      Rows per page
                      <select
                        className="field min-h-10 w-auto py-1"
                        value={pageSize}
                        onChange={(event) => update({ size: Number(event.target.value), page: 1 }, "replace")}
                        data-testid="page-size"
                      >
                        {PAGE_SIZES.map((size) => (
                          <option key={size} value={size}>
                            {size}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  {records.isError ? (
                    <ErrorState
                      title="Couldn't load the records"
                      message={records.error instanceof Error ? records.error.message : "The request failed."}
                      onRetry={() => void records.refetch()}
                    />
                  ) : !page ? (
                    <RecordsTableSkeleton />
                  ) : total === 0 && !url.q ? (
                    <div className="card flex items-center gap-3 p-6" data-testid="records-empty">
                      <StatusDot status="pass" size={10} />
                      <p className="text-base">Nothing to review: no {isFinding ? "checks" : "rows"} fail this rule.</p>
                    </div>
                  ) : total === 0 ? (
                    <div className="card flex flex-col items-start gap-3 p-6" data-testid="records-no-match">
                      <p className="text-base">Nothing matches “{url.q}”.</p>
                      <button type="button" className="btn-secondary" onClick={() => update({ q: "", page: 1 }, "replace")}>
                        Clear search
                      </button>
                    </div>
                  ) : (
                    <div className={clsx("transition-opacity", records.isPlaceholderData && "opacity-60")}>
                      <RecordsTable
                        key={`${ruleId}|${datasetId}|${url.page}|${pageSize}|${url.q}`}
                        records={page.records}
                        columns={page.columns}
                        finding={isFinding || page.records.every((record) => record.source_line === null)}
                        firstIndex={from - 1}
                        tone={meta.tone}
                        otherRuleLink={otherRuleLink}
                        onOpenOtherRule={openOtherRule}
                        caption={`Records that fail ${rule.title} in ${dataset.label}`}
                      />
                    </div>
                  )}

                  {page && total > 0 ? (
                    <nav aria-label="Pages" className="flex flex-wrap items-center justify-between gap-3">
                      <p className="num text-[0.9375rem] text-ink-2" role="status" data-testid="records-range">
                        {records.isPlaceholderData ? (
                          "Updating…"
                        ) : (
                          <>
                            Showing {formatInt(from)}–{formatInt(to)} of {formatInt(total)}
                            {url.q ? ` matching “${url.q}”` : ""}
                          </>
                        )}
                      </p>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          className="btn-secondary"
                          disabled={url.page <= 1}
                          onClick={() => update({ page: url.page - 1 }, "push")}
                          data-testid="prev-page"
                        >
                          <ChevronLeft aria-hidden="true" size={16} />
                          Previous
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          disabled={url.page >= pages}
                          onClick={() => update({ page: url.page + 1 }, "push")}
                          data-testid="next-page"
                        >
                          Next
                          <ChevronRight aria-hidden="true" size={16} />
                        </button>
                      </div>
                    </nav>
                  ) : null}
                </section>
              )}

              {rule && dataset ? (
                <details
                  className="group mt-4 rounded-lg border border-line"
                  onToggle={(event) => setDetailsOpen(event.currentTarget.open)}
                  data-testid="details"
                >
                  <summary className="flex min-h-12 list-none items-center gap-2 px-4 text-base font-medium [&::-webkit-details-marker]:hidden">
                    <ChevronDown aria-hidden="true" size={18} className="-rotate-90 text-ink-2 transition-transform group-open:rotate-0" />
                    Details
                  </summary>
                  <dl className="divide-y divide-line border-t border-line px-4 text-[0.9375rem]">
                    <DetailRow term="Rule id">
                      <span className="font-mono">{rule.rule_id}</span>
                    </DetailRow>
                    <DetailRow term="Full description">
                      <span className="leading-relaxed">
                        <RichText text={rule.description} />
                      </span>
                    </DetailRow>
                    <DetailRow term="Action">
                      {actionMeta(rule.action).label}: {actionMeta(rule.action).meaning}
                    </DetailRow>
                    <DetailRow term="Kind">{kindLabel(rule.kind)}</DetailRow>
                    <DetailRow term="Inferred">
                      {rule.inferred ? "Yes: derived from the data, not stated by the data owner" : "No: stated by the data owner"}
                    </DetailRow>
                    <DetailRow term="Counts toward compliance">
                      {rule.counts_toward_compliance ? "Yes" : "No: informational only"}
                    </DetailRow>
                    <DetailRow term="Applies to">
                      <span className="flex flex-wrap gap-2">
                        {datasets.map((entry) => {
                          const cell = resultFor(rule, entry.dataset_id);
                          const cellMeta = statusMeta(cell.status);
                          if (!rule.applies_to.includes(entry.dataset_id) || !cellMeta.interactive) {
                            return (
                              <span key={entry.dataset_id} className="rounded-md border border-line px-2.5 py-1 text-ink-2">
                                {entry.label}: doesn&apos;t apply
                              </span>
                            );
                          }
                          const current = entry.dataset_id === datasetId;
                          return (
                            <button
                              key={entry.dataset_id}
                              type="button"
                              aria-pressed={current}
                              disabled={current}
                              onClick={() => update({ dataset: entry.dataset_id, q: "", page: 1 }, "replace")}
                              className={clsx(
                                "inline-flex items-center gap-2 rounded-md border px-2.5 py-1",
                                current ? "cursor-default border-ink font-semibold" : "border-line-strong hover:bg-surface-3",
                              )}
                            >
                              <StatusDot status={cell.status} />
                              {entry.label} <span className="num font-mono">{formatPct(cell.compliance_pct)}</span>
                            </button>
                          );
                        })}
                      </span>
                    </DetailRow>
                    {applicable ? (
                      <DetailRow term="Compliance by run">
                        {trend.loading && trend.points.length < 2 ? (
                          <span className="text-ink-2">Loading…</span>
                        ) : (
                          <span className="flex max-w-80 flex-col gap-1">
                            <Sparkline
                              points={trend.points}
                              activeRunId={runId}
                              height={40}
                              caption={`${rule.title} in ${dataset.label}: compliance by run, oldest first`}
                            />
                            {trend.points.length >= 2 ? (
                              <span className="num text-sm text-ink-2">
                                {formatMonth(trend.points[0]?.asOfMonth)} – {formatMonth(trend.points[trend.points.length - 1]?.asOfMonth)}
                              </span>
                            ) : null}
                          </span>
                        )}
                      </DetailRow>
                    ) : null}
                  </dl>
                  <div className="border-t border-line px-4 py-3">
                    <CopyLinkButton />
                  </div>
                </details>
              ) : null}
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
