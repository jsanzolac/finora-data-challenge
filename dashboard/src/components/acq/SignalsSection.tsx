"use client";

import { useState } from "react";
import clsx from "clsx";
import { CircleDot } from "lucide-react";
import { formatInt, humanize } from "@/lib/format";
import { formatR } from "@/lib/acq/format";
import { wonOf } from "@/lib/acq/periods";
import { noMeasurableLink } from "@/lib/acq/planner";
import { aboutChance, correlationGrid, findSummary, readSignals } from "@/lib/acq/signals";
import type { AcqSummary, WonDefinition } from "@/lib/acq/types";
import { DetailItem, Disclosure } from "@/components/ui/Disclosure";
import { PlainSelect } from "@/components/ui/PlainSelect";

const METHODS: { id: string; label: string; meaning: string }[] = [
  { id: "level", label: "Level", meaning: "Monthly new customers against monthly spend, as they are." },
  { id: "diff", label: "Month to month", meaning: "The change from one month to the next on both sides, which takes the shared trend out." },
  { id: "within_regime", label: "Within period", meaning: "Each month against the average of its spend period (before or from Jun 2023)." },
];

const GROUP_LABELS: Record<string, string> = {
  media: "Media (paid and offline)",
  other: "Travel and software",
  people: "People (team, payroll, freelance)",
  media_other: "Media and other",
  total: "Total spend",
  GROUP_MEDIA: "Media (paid and offline)",
  GROUP_OTHER: "Travel and software",
  GROUP_PEOPLE: "People (team, payroll, freelance)",
  TOTAL: "Total spend",
};

const NULL_REASONS: Record<string, string> = {
  too_few_pairs: "Fewer than 3 months to pair",
  constant_series: "One side never changes",
};

function lagLabel(lag: number): string {
  if (lag === 0) return "Same month";
  return `${lag} ${lag === 1 ? "month" : "months"} before`;
}

export function SignalsSection({ summary, definition }: { summary: AcqSummary; definition: WonDefinition }) {
  const [method, setMethod] = useState("level");
  const [scope, setScope] = useState("company");
  const reading = readSignals(summary.signal_summary, definition);
  const { level, diff } = reading;

  const seriesLabel = (series: string) =>
    summary.spend_categories.find((category) => category.code === series)?.label ?? GROUP_LABELS[series] ?? humanize(series);
  const grid = correlationGrid(summary.correlations, definition, scope, method);
  const companyFamily = findSummary(summary.signal_summary, method, definition, "company");
  const industryFamily = findSummary(summary.signal_summary, method, definition, "industry");
  const methodMeta = METHODS.find((entry) => entry.id === method);

  const complete = summary.months.filter((month) => month.month <= summary.run.data_complete_through);
  // `is_low_volume` comes with each correlation row: the scope averages under 10 new customers a month.
  const lowVolumeScopes = new Set(
    summary.correlations.filter((row) => row.won_definition === definition && row.is_low_volume).map((row) => row.scope),
  );
  const scopeIsLow = lowVolumeScopes.has(scope);
  const firstRow = grid.rows[0];

  return (
    <section aria-label="Spend and new customers" data-testid="signals" data-kpi-id="acq.signals">
      <Disclosure title="Spend and new customers" testId="signals-details" bodyClassName="flex flex-col gap-4">
        {level && diff ? (
          <p className="max-w-3xl text-base" data-testid="signals-line">
            {noMeasurableLink(summary.signal_summary) === false
              ? "Some de-trended tests show a link between spend and new customers; review them with the data team before using it"
              : "These files show no measurable link from spend to new customers"}
            : {level.signals} of {level.tests_with_r} tests look related, but {diff.signals} of {diff.tests_with_r} once the trend is removed (
            {aboutChance(diff.expected_by_chance)} by chance). Test spend with a holdout before changing it.
          </p>
        ) : null}
        <p className="max-w-3xl leading-relaxed text-ink-2">
          Most level correlations are negative because spend fell from Jun 2023 while new customers rose. Taking that shared shift out
          leaves about as many signals as chance gives, with no steady sign across neighbouring months. A signal is something to look at,
          not proof, and spend looks like a budget (round totals) rather than what was actually spent.
        </p>

        <div className="flex flex-wrap items-end gap-3">
          <div>
            <span className="mb-1 block text-sm text-ink-2" id="method-label">
              Method
            </span>
            <div role="group" aria-labelledby="method-label" className="inline-flex rounded-lg border border-line-strong p-0.5">
              {METHODS.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  aria-pressed={method === option.id}
                  onClick={() => setMethod(option.id)}
                  className={clsx(
                    "min-h-9 rounded-md px-3 text-[0.9375rem] font-medium",
                    method === option.id ? "bg-ink text-bg" : "text-ink-2 hover:bg-surface-3 hover:text-ink",
                  )}
                  data-testid={`method-${option.id}`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <PlainSelect
            label="Whose new customers"
            value={scope}
            onValueChange={setScope}
            groups={[
              { items: [{ value: "company", text: "Whole company" }] },
              {
                label: "One industry, against company spend",
                items: summary.industries.map((industry) => ({
                  value: industry.code,
                  text: industry.label,
                  note: lowVolumeScopes.has(industry.code) ? "Under 10 a month" : undefined,
                })),
              },
            ]}
            testId="signals-scope"
            className="w-full sm:w-72"
          />
        </div>

        <p className="text-ink-2">
          {methodMeta?.meaning}{" "}
          {companyFamily ? (
            <>
              Whole company: <span className="num font-mono text-ink">{companyFamily.signals}</span> of {companyFamily.tests_with_r} tests marked
              ({aboutChance(companyFamily.expected_by_chance)} by chance).
            </>
          ) : null}{" "}
          {industryFamily ? (
            <>
              Industries: <span className="num font-mono text-ink">{industryFamily.signals}</span> of {industryFamily.tests_with_r} (
              {aboutChance(industryFamily.expected_by_chance)} by chance).
            </>
          ) : null}
        </p>
        {scopeIsLow ? (
          <p className="text-ink-2">This industry has fewer than 10 new customers a month, so its correlations swing a lot by chance.</p>
        ) : null}

        <div className="overflow-x-auto rounded-lg border border-line" tabIndex={0} role="region" aria-label="Correlation grid, scrolls sideways on small screens">
          <table className="w-full min-w-[40rem] border-separate border-spacing-0 text-[0.9375rem]" data-testid="signals-grid">
            <caption className="sr-only">
              Correlation r between new customers and spend, by spend series and months before. Marked cells cross the 5% line.
            </caption>
            <thead>
              <tr>
                <th scope="col" className="border-b border-line-strong bg-surface px-4 py-2.5 text-left font-medium text-ink-2">
                  Spend
                </th>
                {grid.lags.map((lag, index) => {
                  const sample = firstRow?.cells[index];
                  return (
                    <th key={lag} scope="col" className="border-b border-line-strong bg-surface px-3 py-2.5 text-right font-medium text-ink-2">
                      <span className="block">{lagLabel(lag)}</span>
                      {sample ? (
                        <span className="num block font-mono text-xs font-normal">
                          {sample.n} months · |r| ≥ {sample.r_critical_5pct?.toFixed(2) ?? "—"}
                        </span>
                      ) : null}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {grid.rows.map((row, rowIndex) => (
                <tr key={row.series} className={rowIndex % 2 === 0 ? "zebra-a" : "zebra-b"}>
                  <th scope="row" className="px-4 py-2 text-left font-normal">
                    {seriesLabel(row.series)}
                  </th>
                  {row.cells.map((cell, index) => (
                    <td key={grid.lags[index]} className="px-2 py-1 text-right">
                      {cell && cell.r === null ? (
                        <span className="px-2 text-ink-2" title={NULL_REASONS[cell.null_reason ?? ""] ?? "Not computable"}>
                          —<span className="sr-only">, {NULL_REASONS[cell.null_reason ?? ""] ?? "not computable"}</span>
                        </span>
                      ) : cell ? (
                        <span
                          className={clsx(
                            "num inline-flex min-w-[5.5rem] items-center justify-end gap-1.5 rounded-md px-2 py-1 font-mono",
                            cell.is_signal ? "bg-signal-tint font-semibold text-ink" : "text-ink-2",
                          )}
                          data-signal={cell.is_signal ? "true" : undefined}
                        >
                          {cell.is_signal ? <CircleDot aria-hidden="true" size={14} className="text-accent" /> : null}
                          {formatR(cell.r)}
                          {cell.is_signal ? <span className="sr-only">, signal</span> : null}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="flex items-center gap-2 text-sm text-ink-2">
          <CircleDot aria-hidden="true" size={14} className="text-accent" />
          Crosses the 5% line for its number of months. With this many tests, some cross it by chance.
        </p>

        <dl className="divide-y divide-line border-t border-line">
          <DetailItem term="Who counts as new">
            {definition === "user" ? "Every first payment (your definition)." : "Without customers probably already active."} Total{" "}
            <span className="num font-mono">{formatInt(complete.reduce((sum, month) => sum + wonOf(month, definition), 0))}</span>.
          </DetailItem>
          <DetailItem term="“By chance”">
            Each test has a 5% chance of crossing the line with no real link. The page says there is no measurable link when, for the whole company,
            month-to-month and within-period signals are each at most twice what chance gives (CDO §16.6). Neighbouring months overlap, so treat this as a
            screen, not a test.
          </DetailItem>
        </dl>
      </Disclosure>
    </section>
  );
}
