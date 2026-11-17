"use client";

import { useMemo, useRef, useState } from "react";
import clsx from "clsx";
import type { DatasetSummary, Rule, RuleResult } from "@/lib/api/types";
import { formatPct } from "@/lib/format";
import { hasIssue, hasIssueIn, visibleRules } from "@/lib/ranking";
import { cellKey, resultFor, statusMeta } from "@/lib/status";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusDot } from "@/components/ui/StatusDot";

interface RulesTableProps {
  rules: Rule[];
  /** Departments in ranked order: they become the columns. */
  datasets: DatasetSummary[];
  /** The cell whose records are open, if any. */
  selected: { ruleId: string; datasetId: string } | null;
  onOpen: (ruleId: string, datasetId: string) => void;
}

/** "● 99.95%": the dot, and the number in the status colour when it isn't Good. */
function CellFigure({ result }: { result: RuleResult }) {
  const meta = statusMeta(result.status);
  return (
    <span className="flex items-center gap-2.5">
      <StatusDot status={result.status} />
      <span className={clsx("num font-mono text-base", meta.tone === "pass" ? "text-ink" : "text-tone font-semibold")}>
        {formatPct(result.compliance_pct)}
      </span>
    </span>
  );
}

/** A faint dash for a rule that doesn't apply. Drawn, not text, so it never competes with the numbers. */
function NotApplicable() {
  return (
    <span className="flex items-center px-3" data-status="na">
      <span aria-hidden="true" className="inline-block h-0.5 w-3.5 rounded-full bg-line-strong" />
      <span className="sr-only">Doesn&apos;t apply</span>
    </span>
  );
}

function cellLabel(rule: Rule, datasetLabel: string, result: RuleResult): string {
  return `${rule.title}, ${datasetLabel}: ${formatPct(result.compliance_pct)}, ${statusMeta(result.status).label}. Show the records`;
}

export function RulesTable({ rules, datasets, selected, onOpen }: RulesTableProps) {
  const [issuesOnly, setIssuesOnly] = useState(true);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const cellRefs = useRef(new Map<string, HTMLButtonElement>());

  const datasetIds = useMemo(() => datasets.map((dataset) => dataset.dataset_id), [datasets]);
  const issueCount = useMemo(() => rules.filter((rule) => hasIssue(rule, datasetIds)).length, [rules, datasetIds]);
  const shown = useMemo(() => visibleRules(rules, datasetIds, issuesOnly), [rules, datasetIds, issuesOnly]);

  function isOpenable(row: number, column: number): boolean {
    const rule = shown[row];
    const datasetId = datasetIds[column];
    return Boolean(rule && datasetId && statusMeta(resultFor(rule, datasetId).status).interactive);
  }

  function isShownOpenable(key: string | null): boolean {
    if (key === null) return false;
    return shown.some((rule, row) => datasetIds.some((id, column) => cellKey(rule.rule_id, id) === key && isOpenable(row, column)));
  }

  // Roving tabindex: the table is one tab stop and the arrow keys move between cells.
  let firstKey: string | null = null;
  outer: for (let row = 0; row < shown.length; row += 1) {
    for (let column = 0; column < datasetIds.length; column += 1) {
      const rule = shown[row];
      const datasetId = datasetIds[column];
      if (rule && datasetId && isOpenable(row, column)) {
        firstKey = cellKey(rule.rule_id, datasetId);
        break outer;
      }
    }
  }
  const selectedKey = selected ? cellKey(selected.ruleId, selected.datasetId) : null;
  const tabStopKey = isShownOpenable(activeKey) ? activeKey : isShownOpenable(selectedKey) ? selectedKey : firstKey;

  function focusCell(row: number, column: number) {
    const rule = shown[row];
    const datasetId = datasetIds[column];
    if (!rule || !datasetId) return;
    const key = cellKey(rule.rule_id, datasetId);
    setActiveKey(key);
    cellRefs.current.get(key)?.focus();
  }

  /** Next openable cell from (row, column) in a direction, skipping cells that don't apply. */
  function scan(row: number, column: number, dRow: number, dColumn: number): [number, number] | null {
    let r = row + dRow;
    let c = column + dColumn;
    while (r >= 0 && r < shown.length && c >= 0 && c < datasetIds.length) {
      if (isOpenable(r, c)) return [r, c];
      r += dRow;
      c += dColumn;
    }
    return null;
  }

  function onGridKeyDown(event: React.KeyboardEvent<HTMLTableElement>) {
    const cell = (event.target as HTMLElement).closest<HTMLElement>("[data-cell-key]");
    if (!cell) return;
    const row = shown.findIndex((rule) => rule.rule_id === cell.dataset.rule);
    const column = datasetIds.indexOf(cell.dataset.dataset ?? "");
    if (row < 0 || column < 0) return;
    let next: [number, number] | null = null;
    switch (event.key) {
      case "ArrowRight":
        next = scan(row, column, 0, 1);
        break;
      case "ArrowLeft":
        next = scan(row, column, 0, -1);
        break;
      case "ArrowDown":
        next = scan(row, column, 1, 0);
        break;
      case "ArrowUp":
        next = scan(row, column, -1, 0);
        break;
      case "Home":
        next = event.ctrlKey || event.metaKey ? scan(-1, column, 1, 0) : scan(row, -1, 0, 1);
        break;
      case "End":
        next = event.ctrlKey || event.metaKey ? scan(shown.length, column, -1, 0) : scan(row, datasetIds.length, 0, -1);
        break;
      default:
        return;
    }
    event.preventDefault();
    if (next) focusCell(next[0], next[1]);
  }

  const toggle = (
    <div role="group" aria-label="Which rules to show" className="inline-flex rounded-lg border border-line-strong p-0.5">
      {[
        { value: true, text: `Issues (${issueCount})`, testId: "show-issues" },
        { value: false, text: `All rules (${rules.length})`, testId: "show-all" },
      ].map((option) => (
        <button
          key={option.testId}
          type="button"
          aria-pressed={issuesOnly === option.value}
          onClick={() => setIssuesOnly(option.value)}
          className={clsx(
            "num min-h-9 rounded-md px-3.5 text-[0.9375rem] font-medium",
            issuesOnly === option.value ? "bg-ink text-bg" : "text-ink-2 hover:bg-surface-3 hover:text-ink",
          )}
          data-testid={option.testId}
        >
          {option.text}
        </button>
      ))}
    </div>
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="flex flex-col gap-1">
          <h2 id="rules-title" tabIndex={-1} className="text-xl font-semibold outline-none">
            Rules
          </h2>
          <p className="text-[0.9375rem] text-ink-2">Tap a number to see the records.</p>
        </div>
        {toggle}
      </div>

      {shown.length === 0 ? (
        <div className="card flex items-center gap-3 p-6" data-testid="rules-empty" role="status">
          <StatusDot status="pass" size={10} />
          <p className="text-base">All rules pass in every department.</p>
        </div>
      ) : (
        <>
          {/* Wide screens: rule × department table. Rows alternate black / soft grey (white / soft grey in light). */}
          <div className="card hidden overflow-clip md:block">
            <table
              role="grid"
              aria-label="Rules by department. Arrow keys move between numbers, Enter shows the records."
              className="w-full table-fixed border-separate border-spacing-0"
              onKeyDown={onGridKeyDown}
              data-testid="matrix"
            >
              <colgroup>
                <col />
                {datasets.map((dataset) => (
                  <col key={dataset.dataset_id} className="w-[19%]" />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th scope="col" className="sticky top-0 z-10 border-b border-line-strong bg-surface px-5 py-3.5 text-left text-[0.9375rem] font-medium text-ink-2">
                    Rule
                  </th>
                  {datasets.map((dataset) => (
                    <th
                      key={dataset.dataset_id}
                      scope="col"
                      className="sticky top-0 z-10 border-b border-line-strong bg-surface px-4 py-3.5 text-left text-[0.9375rem] font-medium text-ink-2"
                    >
                      {dataset.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map((rule, rowIndex) => (
                  <tr key={rule.rule_id} className={rowIndex % 2 === 0 ? "zebra-a" : "zebra-b"} data-rule-row={rule.rule_id}>
                    <th scope="row" className="px-5 py-2 text-left align-middle font-normal">
                      <span className="text-base leading-snug text-ink" title={rule.rule_id}>
                        {rule.title}
                      </span>
                    </th>
                    {datasets.map((dataset) => {
                      const result = resultFor(rule, dataset.dataset_id);
                      const meta = statusMeta(result.status);
                      if (!meta.interactive) {
                        return (
                          <td key={dataset.dataset_id} className="px-1 py-2">
                            <NotApplicable />
                          </td>
                        );
                      }
                      const key = cellKey(rule.rule_id, dataset.dataset_id);
                      const isSelected = selected?.ruleId === rule.rule_id && selected.datasetId === dataset.dataset_id;
                      return (
                        <td key={dataset.dataset_id} className="px-1 py-2">
                          <button
                            type="button"
                            ref={(element) => {
                              if (element) cellRefs.current.set(key, element);
                              else cellRefs.current.delete(key);
                            }}
                            tabIndex={key === tabStopKey ? 0 : -1}
                            data-cell-key={key}
                            data-kpi-id={`dq.rule_cell.${rule.rule_id}.${dataset.dataset_id}`}
                            data-rule={rule.rule_id}
                            data-dataset={dataset.dataset_id}
                            data-status={result.status}
                            aria-label={cellLabel(rule, dataset.label, result)}
                            title={meta.label}
                            onFocus={() => setActiveKey(key)}
                            onClick={() => onOpen(rule.rule_id, dataset.dataset_id)}
                            className={clsx(
                              `tone-${meta.tone}`,
                              "flex h-11 w-full items-center rounded-md px-3 text-left hover:bg-row-hover hover:underline hover:decoration-line-strong hover:underline-offset-4",
                              isSelected && "ring-2 ring-accent",
                            )}
                          >
                            <CellFigure result={result} />
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Narrow screens: one list per department. */}
          <div className="flex flex-col gap-6 md:hidden">
            {datasets.map((dataset) => {
              const items = shown.filter((rule) => {
                const meta = statusMeta(resultFor(rule, dataset.dataset_id).status);
                return meta.interactive && (!issuesOnly || hasIssueIn(rule, dataset.dataset_id));
              });
              return (
                <section key={dataset.dataset_id} aria-label={dataset.label} data-testid="dept-list" data-dataset={dataset.dataset_id}>
                  <h3 className="mb-2 text-base font-semibold">{dataset.label}</h3>
                  {items.length === 0 ? (
                    <p className="text-[0.9375rem] text-ink-2">No issues.</p>
                  ) : (
                    <ul className="card overflow-clip">
                      {items.map((rule, index) => {
                        const result = resultFor(rule, dataset.dataset_id);
                        const meta = statusMeta(result.status);
                        return (
                          <li key={rule.rule_id} className={index % 2 === 0 ? "zebra-a" : "zebra-b"}>
                            <button
                              type="button"
                              data-cell-key={cellKey(rule.rule_id, dataset.dataset_id)}
                              data-kpi-id={`dq.rule_cell.${rule.rule_id}.${dataset.dataset_id}`}
                              data-rule={rule.rule_id}
                              data-dataset={dataset.dataset_id}
                              data-status={result.status}
                              onClick={() => onOpen(rule.rule_id, dataset.dataset_id)}
                              className={clsx(`tone-${meta.tone}`, "flex min-h-14 w-full items-center justify-between gap-4 px-4 py-3 text-left hover:bg-row-hover")}
                            >
                              <span className="text-base leading-snug">{rule.title}</span>
                              <span className="sr-only">, {dataset.label}: </span>
                              <CellFigure result={result} />
                              <span className="sr-only">, {meta.label}. Show the records</span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </section>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

export function RulesTableSkeleton() {
  return (
    <div className="card flex flex-col gap-2 p-4" aria-hidden="true">
      {Array.from({ length: 6 }, (_, index) => (
        <Skeleton key={index} className="h-11 w-full rounded-md" />
      ))}
    </div>
  );
}

/**
 * Moves focus to the cell for a rule and department (the visible one: the table
 * on wide screens, the list on narrow ones). Returns false when it is not on screen.
 */
export function focusRuleCell(ruleId: string, datasetId: string): boolean {
  const key = cellKey(ruleId, datasetId);
  for (const element of document.querySelectorAll<HTMLElement>("[data-cell-key]")) {
    if (element.dataset.cellKey === key && element.getClientRects().length > 0) {
      element.focus();
      return true;
    }
  }
  return false;
}
