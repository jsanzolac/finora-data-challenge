"use client";

import { scaleBand, scaleLinear, scalePoint } from "d3-scale";
import { line } from "d3-shape";
import clsx from "clsx";
import { ArrowDown, ArrowUp } from "lucide-react";
import { formatCompact, formatExact, groupDigits } from "@/lib/acq/format";
import { baselineOf, pctChange, periodRows, ticketStep, valueChange } from "@/lib/acq/planner";
import { Ratio } from "@/lib/acq/ratio";
import type { AcqSummary, LeverCohort, WonDefinition } from "@/lib/acq/types";
import { leverDefinition } from "@/lib/acq/types";
import { useElementWidth } from "@/lib/use-element-width";
import { DetailItem, Disclosure } from "@/components/ui/Disclosure";
import { shortMonth } from "./LeversSection";

const EARLIER = "var(--viz-spend)";
const LATER = "var(--viz-1)";

function abs(value: Ratio): Ratio {
  return value.sign() < 0 ? value.neg() : value;
}

function whole(value: Ratio | null): string {
  return value ? groupDigits(value.toFixed(0)) : "—";
}

function halfLabel(half: string): string {
  return `${half.endsWith("H1") ? "H1" : "H2"} ${half.slice(0, 4)}`;
}

function ChangeCard({ title, change, from, to, testId, kpiId }: { title: string; change: Ratio | null; from: string; to: string; testId: string; kpiId: string }) {
  const up = (change?.sign() ?? 0) > 0;
  const Icon = up ? ArrowUp : ArrowDown;
  return (
    <article className="card flex flex-col gap-2 p-6" data-testid={testId} data-kpi-id={kpiId}>
      <h3 className="text-base font-medium text-ink-2">{title}</h3>
      <p className={clsx("flex items-center gap-2 text-4xl leading-none font-semibold", up ? "text-pass-ink" : "text-fail-ink")}>
        <Icon aria-hidden="true" size={30} />
        <span className="num font-mono">{change ? `${up ? "+" : "−"}${formatExact(abs(change), 0)}%` : "—"}</span>
        <span className="sr-only">{up ? ", up" : ", down"}</span>
      </p>
      <p className="num font-mono text-[0.9375rem] text-ink-2">
        {from} → {to}
      </p>
    </article>
  );
}

/** Starting revenue per new customer by half-year cohort: columns, partial cohorts lighter. */
function TicketTrend({ cohorts }: { cohorts: LeverCohort[] }) {
  const [ref, width] = useElementWidth<HTMLDivElement>(500);
  const height = 170;
  const left = 44;
  const values = cohorts.map((c) => Ratio.tryParse(c.run_rate_mrr_per_won_value)?.toNumber() ?? null);
  const max = Math.max(...values.map((v) => v ?? 0), 1);
  const x = scaleBand<string>().domain(cohorts.map((c) => c.cohort_half)).range([left, Math.max(left + 10, width - 4)]).paddingInner(0.35).paddingOuter(0.15);
  const y = scaleLinear().domain([0, max]).nice(3).range([height - 22, 18]);
  const barWidth = Math.min(24, x.bandwidth());
  return (
    <div ref={ref} className="w-full min-w-0" data-testid="ticket-trend">
      <svg width={width} height={height} aria-hidden="true" focusable="false" className="block overflow-visible">
        {y.ticks(3).map((tick) => (
          <g key={tick}>
            <line x1={left} x2={width - 4} y1={y(tick)} y2={y(tick)} stroke={tick === 0 ? "var(--viz-axis)" : "var(--viz-grid)"} strokeWidth={1} />
            <text x={left - 8} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-[var(--ink-2)] font-mono text-[11px]">
              {formatCompact(tick)}
            </text>
          </g>
        ))}
        {cohorts.map((c, i) => {
          const value = values[i];
          if (value === null || value === undefined) return null;
          const bx = (x(c.cohort_half) ?? 0) + (x.bandwidth() - barWidth) / 2;
          const top = y(value);
          const r = Math.min(4, barWidth / 2);
          return (
            <g key={c.cohort_half} opacity={c.is_complete_run_rate ? 1 : 0.45}>
              <path
                d={`M${bx},${y(0)}V${top + r}Q${bx},${top} ${bx + r},${top}H${bx + barWidth - r}Q${bx + barWidth},${top} ${bx + barWidth},${top + r}V${y(0)}Z`}
                fill="var(--viz-1)"
              />
              <text x={bx + barWidth / 2} y={top - 5} textAnchor="middle" className="fill-[var(--ink)] font-mono text-[11px]">
                {formatCompact(value)}
              </text>
            </g>
          );
        })}
        {cohorts.map((c) => (
          <text key={c.cohort_half} x={(x(c.cohort_half) ?? 0) + x.bandwidth() / 2} y={height - 4} textAnchor="middle" className="fill-[var(--ink-2)] font-mono text-[11px]">
            {halfLabel(c.cohort_half)}
          </text>
        ))}
      </svg>
      <div className="sr-only">
        <table>
          <caption>Starting monthly revenue per new customer (months 2–4), by half-year cohort</caption>
          <thead>
            <tr>
              <th scope="col">Cohort</th>
              <th scope="col">Starting revenue</th>
            </tr>
          </thead>
          <tbody>
            {cohorts.map((c) => (
              <tr key={c.cohort_half}>
                <td>{halfLabel(c.cohort_half)}</td>
                <td>
                  {whole(Ratio.tryParse(c.run_rate_mrr_per_won_value))}
                  {c.is_complete_run_rate ? "" : " (partial)"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Month-6 and month-12 retention by half-year cohort; complete cohorts only. */
function RetentionTrend({ cohorts }: { cohorts: LeverCohort[] }) {
  const [ref, width] = useElementWidth<HTMLDivElement>(500);
  const height = 170;
  const left = 44;
  const right = 52;
  const pct = (share: string | null) => (share === null ? null : Number(share) * 100);
  const series = [
    { key: "m6", label: "Month 6", color: "var(--viz-1)", values: cohorts.map((c) => (c.is_complete_m6 ? pct(c.paying_m6_share) : null)) },
    { key: "m12", label: "Month 12", color: "var(--viz-2)", values: cohorts.map((c) => (c.is_complete_m12 ? pct(c.paying_m12_share) : null)) },
  ];
  const x = scalePoint<string>().domain(cohorts.map((c) => c.cohort_half)).range([left + 14, Math.max(left + 20, width - right)]);
  const y = scaleLinear().domain([70, 100]).range([height - 22, 10]);
  return (
    <div ref={ref} className="w-full min-w-0" data-testid="retention-trend">
      <ul className="mb-1 flex flex-wrap gap-x-4 text-sm text-ink-2" aria-label="Retention series">
        {series.map((entry) => (
          <li key={entry.key} className="flex items-center gap-2">
            <span aria-hidden="true" className="inline-block h-0.5 w-4 rounded-full" style={{ background: entry.color }} />
            Paying at {entry.label.toLowerCase()}
          </li>
        ))}
      </ul>
      <svg width={width} height={height} aria-hidden="true" focusable="false" className="block overflow-visible">
        {[70, 80, 90, 100].map((tick) => (
          <g key={tick}>
            <line x1={left} x2={width - right + 8} y1={y(tick)} y2={y(tick)} stroke="var(--viz-grid)" strokeWidth={1} />
            <text x={left - 8} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-[var(--ink-2)] font-mono text-[11px]">
              {tick}%
            </text>
          </g>
        ))}
        {series.map((entry) => {
          const points = cohorts.map((c, i) => ({ half: c.cohort_half, value: entry.values[i] ?? null }));
          const path = line<{ half: string; value: number | null }>()
            .defined((p) => p.value !== null)
            .x((p) => x(p.half) ?? 0)
            .y((p) => y(p.value ?? 0))(points) ?? "";
          const last = [...points].reverse().find((p) => p.value !== null);
          return (
            <g key={entry.key}>
              <path d={path} fill="none" stroke={entry.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {points.map((p) => (p.value === null ? null : <circle key={p.half} cx={x(p.half)} cy={y(p.value)} r={4} fill={entry.color} stroke="var(--surface)" strokeWidth={2} />))}
              {last && last.value !== null ? (
                <text x={(x(last.half) ?? 0) + 9} y={y(last.value)} dy="0.32em" className="fill-[var(--ink)] font-mono text-[11px]">
                  {last.value.toFixed(1)}%
                </text>
              ) : null}
            </g>
          );
        })}
        {cohorts.map((c) => (
          <text key={c.cohort_half} x={x(c.cohort_half)} y={height - 4} textAnchor="middle" className="fill-[var(--ink-2)] font-mono text-[11px]">
            {halfLabel(c.cohort_half)}
          </text>
        ))}
      </svg>
      <div className="sr-only">
        <table>
          <caption>Share of new customers still paying at month 6 and month 12, by half-year cohort</caption>
          <thead>
            <tr>
              <th scope="col">Cohort</th>
              <th scope="col">Month 6</th>
              <th scope="col">Month 12</th>
            </tr>
          </thead>
          <tbody>
            {cohorts.map((c) => (
              <tr key={c.cohort_half}>
                <td>{halfLabel(c.cohort_half)}</td>
                <td>{c.paying_m6_share ? `${(Number(c.paying_m6_share) * 100).toFixed(1)}%${c.is_complete_m6 ? "" : " (partial)"}` : "not observable yet"}</td>
                <td>{c.paying_m12_share ? `${(Number(c.paying_m12_share) * 100).toFixed(1)}%${c.is_complete_m12 ? "" : " (partial)"}` : "not observable yet"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function GrowthLostSection({ summary, definition }: { summary: AcqSummary; definition: WonDefinition }) {
  const levers = summary.levers;
  const change = valueChange(levers, definition);
  const rows = periodRows(levers, definition);
  const fromRow = rows.find((row) => row.period_code === change?.from);
  const toRow = rows.find((row) => row.period_code === change?.to);
  const before = baselineOf(fromRow);
  const after = baselineOf(toRow);
  if (!levers || !change || !fromRow || !toRow || !before || !after) return null;
  const cohorts = levers.cohorts.filter((c) => c.won_definition === leverDefinition(definition));
  const label = (code: string) => summary.industries.find((industry) => industry.code === code)?.label ?? code;
  const fromLabel = `${shortMonth(fromRow.first_month_key)} – ${shortMonth(fromRow.last_month_key)}`;
  const toLabel = `${shortMonth(toRow.first_month_key)} – ${shortMonth(toRow.last_month_key)}`;
  const withinShare = change.within.div(change.total).mul(Ratio.of(100n));
  const withinReverseShare = change.withinReverse.div(change.total).mul(Ratio.of(100n));
  const m6 = cohorts.filter((c) => c.is_complete_m6 && c.paying_m6_share).map((c) => Number(c.paying_m6_share) * 100);
  const held = m6.length >= 2 && m6[m6.length - 1]! >= Math.min(...m6.slice(0, -1)) - 2;
  const step = ticketStep(levers, definition);

  const dumbbell = change.rows
    .map((row) => {
      const a = Ratio.tryParse(row.value_from);
      const b = Ratio.tryParse(row.value_to);
      return { code: row.industry_code, a, b, change: pctChange(a, b) };
    })
    .filter((row): row is { code: string; a: Ratio; b: Ratio; change: Ratio } => Boolean(row.a && row.b && row.change))
    .sort((x, y) => x.change.compare(y.change));
  const max = Math.max(...dumbbell.flatMap((row) => [row.a.toNumber(), row.b.toNumber()]), 1);
  const at = (value: Ratio) => (value.toNumber() / (max * 1.05)) * 100;

  return (
    <section aria-labelledby="lost-title" className="flex flex-col gap-5" data-testid="growth-lost">
      <div className="flex flex-col gap-1">
        <h2 id="lost-title" className="text-xl font-semibold">
          Where growth is lost
        </h2>
        <p className="text-[0.9375rem] text-ink-2">
          {fromLabel} against {toLabel}.
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <ChangeCard title="New customers a month" change={pctChange(before.wonPerMonth, after.wonPerMonth)} from={formatExact(before.wonPerMonth, 1)} to={formatExact(after.wonPerMonth, 1)} testId="lost-customers" kpiId="acq.lost.new_customers" />
        <ChangeCard title="Starting revenue per new customer" change={pctChange(before.runRate, after.runRate)} from={whole(before.runRate)} to={whole(after.runRate)} testId="lost-revenue" kpiId="acq.lost.starting_revenue" />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card flex min-w-0 flex-col gap-3 p-4 md:p-6" data-kpi-id="acq.lost.ticket_by_cohort">
          <div className="flex flex-col gap-1">
            <h3 className="text-base font-medium">Starting revenue per new customer, by half-year cohort</h3>
            <p className="text-[0.9375rem] text-ink-2" data-testid="ticket-trend-line">
              {step ? `It stepped down between ${halfLabel(step.before.cohort_half)} and ${halfLabel(step.after.cohort_half)}. ` : ""}Lighter bars are cohorts
              still maturing.
            </p>
          </div>
          <TicketTrend cohorts={cohorts} />
        </div>
        <div className="card flex min-w-0 flex-col gap-3 p-4 md:p-6" data-kpi-id="acq.lost.keep_paying">
          <div className="flex flex-col gap-1">
            <h3 className="text-base font-medium">Do new customers keep paying?</h3>
            {m6.length > 0 ? (
              <p className="text-[0.9375rem] text-ink-2" data-testid="cohort-headline">
                Paying at month 6: {Math.min(...m6).toFixed(0)}–{Math.max(...m6).toFixed(0)}% in every complete cohort.{" "}
                {held ? "Churn didn't rise." : "The latest cohort keeps fewer customers."}
              </p>
            ) : null}
          </div>
          <RetentionTrend cohorts={cohorts} />
        </div>
      </div>

      <div className="card flex flex-col gap-3 p-4 md:p-6" data-kpi-id="acq.lost.ticket_by_industry">
        <div className="flex flex-col gap-1">
          <h3 className="text-base font-medium">Starting revenue per new customer, by industry</h3>
          <p className="text-[0.9375rem] text-ink-2" data-testid="within-share">
            About {formatExact(Ratio.of(BigInt(Math.min(Number(withinShare.toFixed(0)), Number(withinReverseShare.toFixed(0))))), 0)}% of the drop is inside each
            industry, whichever way it is split; the mix of industries explains the rest.
          </p>
        </div>
        <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-2" aria-label="Periods">
          <li className="flex items-center gap-2">
            <span aria-hidden="true" className="inline-block size-2.5 rounded-full" style={{ background: EARLIER }} />
            {fromLabel}
          </li>
          <li className="flex items-center gap-2">
            <span aria-hidden="true" className="inline-block size-2.5 rounded-full" style={{ background: LATER }} />
            {toLabel}
          </li>
        </ul>
        <ul className="flex flex-col" data-testid="industry-dumbbell">
          {dumbbell.map((row, index) => {
            const lo = Math.min(at(row.a), at(row.b));
            const hi = Math.max(at(row.a), at(row.b));
            return (
              <li
                key={row.code}
                className={clsx("grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 rounded-md px-2 py-2 md:grid-cols-[11rem_minmax(0,1fr)_10rem_4rem]", index % 2 === 0 ? "zebra-a" : "zebra-b")}
                data-testid="dumbbell-row"
                data-industry={row.code}
              >
                <span className="text-[0.9375rem]">{label(row.code)}</span>
                <span aria-hidden="true" className="relative col-span-2 row-start-2 block h-4 md:col-span-1 md:row-start-auto">
                  <span className="absolute top-1/2 h-0.5 -translate-y-1/2 rounded-full bg-line-strong" style={{ left: `${lo}%`, width: `${hi - lo}%` }} />
                  <span className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-[var(--surface)]" style={{ left: `${at(row.a)}%`, background: EARLIER }} />
                  <span className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-[var(--surface)]" style={{ left: `${at(row.b)}%`, background: LATER }} />
                </span>
                <span className="num hidden text-right font-mono text-sm text-ink-2 md:block">
                  {whole(row.a)} → {whole(row.b)}
                </span>
                <span className={clsx("num col-start-2 row-start-1 text-right font-mono font-semibold md:col-start-auto md:row-start-auto", row.change.sign() < 0 ? "text-fail-ink" : "text-ink")}>
                  {row.change.sign() < 0 ? "−" : "+"}
                  {formatExact(abs(row.change), 0)}%
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      <Disclosure testId="lost-details">
        <dl className="divide-y divide-line">
          <DetailItem term="Starting revenue">
            The average a new customer pays in months 2 to 4 after the first payment, over cohorts with all three months in the data. A cohort still maturing
            shows its partial value.
          </DetailItem>
          <DetailItem term="Mix and within">
            The change of {whole(change.total)} a month per new customer splits into the mix of industries ({whole(change.mix)}) and the change inside each
            industry ({whole(change.within)}). In the other order: {whole(change.mixReverse)} and {whole(change.withinReverse)}. Weights are each industry&apos;s
            share of customers with a starting revenue.
          </DetailItem>
          <DetailItem term="Retention">
            The share of a cohort&apos;s new customers paying in their 6th or 12th month, counting cash only (a gap settled later counts as not paying, so this is
            a lower bound). A cohort shows once every customer has reached that month.
          </DetailItem>
          <DetailItem term="The two periods">
            They are the two spend periods, inferred from the spend data, used only as a baseline.
            {step ? ` The ticket step came by the ${halfLabel(step.after.cohort_half)} cohorts, so the spend periods don't explain it.` : ""}
          </DetailItem>
          {[fromRow, toRow].some((row) => row.outlier_customers > 0) ? (
            <DetailItem term="Outliers">Outlier customers are included: {fromRow.outlier_customers + toRow.outlier_customers}.</DetailItem>
          ) : null}
        </dl>
      </Disclosure>
    </section>
  );
}
