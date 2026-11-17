"use client";

import { useMemo, useState } from "react";
import clsx from "clsx";
import { scaleBand, scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { formatInt, formatMonth } from "@/lib/format";
import { formatCompact, formatMoney } from "@/lib/acq/format";
import { wonOf, type PeriodOption } from "@/lib/acq/periods";
import { Ratio } from "@/lib/acq/ratio";
import type { AcqSummary, WonDefinition } from "@/lib/acq/types";
import { useElementWidth } from "@/lib/use-element-width";
import { DetailItem, Disclosure } from "@/components/ui/Disclosure";

const INDUSTRY_COLORS = ["var(--viz-1)", "var(--viz-2)", "var(--viz-3)", "var(--viz-4)", "var(--viz-5)", "var(--viz-6)"];
const LEFT = 48;
const RIGHT = 8;
const BAR_MAX = 24;
const GAP = 2;

interface MonthPoint {
  month: string;
  won: number;
  byIndustry: number[];
  spend: number | null;
  costPerWon: Ratio | null;
  inPeriod: boolean;
}

/** A column with a 4px rounded data end and a square base. */
function columnPath(x: number, y: number, width: number, height: number, rounded: boolean): string {
  if (height <= 0) return "";
  const r = rounded ? Math.min(4, width / 2, height) : 0;
  return `M${x},${y + height}V${y + r}${r ? `Q${x},${y} ${x + r},${y}` : ""}H${x + width - r}${r ? `Q${x + width},${y} ${x + width},${y + r}` : ""}V${y + height}Z`;
}

function niceTicks(max: number, count: number): number[] {
  return scaleLinear().domain([0, max]).nice(count).ticks(count);
}

function yearLabels(months: string[]): { month: string; label: string }[] {
  const seen = new Set<string>();
  const out: { month: string; label: string }[] = [];
  for (const month of months) {
    const year = month.slice(0, 4);
    if (!seen.has(year)) {
      seen.add(year);
      out.push({ month, label: year });
    }
  }
  return out;
}

export function TimeSection({
  summary,
  definition,
  period,
}: {
  summary: AcqSummary;
  definition: WonDefinition;
  period: PeriodOption;
}) {
  const [split, setSplit] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const [announce, setAnnounce] = useState("");
  const [ref, width] = useElementWidth<HTMLDivElement>(900);
  const showSplit = split;
  const highlight = period.kind !== "full";

  const points: MonthPoint[] = useMemo(
    () =>
      summary.months.map((month) => {
        const won = wonOf(month, definition);
        const spend = Ratio.tryParse(month.spend_total_value);
        return {
          month: month.month,
          won,
          byIndustry: summary.industries.map(
            (industry) => (definition === "new_logo" ? month.won_by_industry_new_logo : month.won_by_industry)?.[industry.code] ?? 0,
          ),
          spend: spend ? spend.toNumber() : null,
          costPerWon: spend && won > 0 && !month.cost_null_reason ? spend.div(Ratio.of(BigInt(won))) : null,
          inPeriod: period.months.includes(month.month),
        };
      }),
    [summary, definition, period],
  );

  const months = points.map((point) => point.month);
  const x = scaleBand<string>()
    .domain(months)
    .range([LEFT, Math.max(LEFT + 10, width - RIGHT)])
    .paddingInner(0.25)
    .paddingOuter(0.1);
  const barWidth = Math.min(BAR_MAX, x.bandwidth());
  const barX = (month: string) => (x(month) ?? 0) + (x.bandwidth() - barWidth) / 2;
  const center = (month: string) => (x(month) ?? 0) + x.bandwidth() / 2;

  const wonHeight = 190;
  const spendHeight = 120;
  const pad = { top: 10, bottom: 6 };
  const wonTicks = niceTicks(Math.max(...points.map((point) => point.won), 1), 4);
  const yWon = scaleLinear()
    .domain([0, wonTicks[wonTicks.length - 1] ?? 1])
    .range([wonHeight - pad.bottom, pad.top]);
  const spendTicks = niceTicks(Math.max(...points.map((point) => point.spend ?? 0), 1), 3);
  const ySpend = scaleLinear()
    .domain([0, spendTicks[spendTicks.length - 1] ?? 1])
    .range([spendHeight - pad.bottom, pad.top]);

  const boundaries = [...summary.regimes]
    .sort((a, b) => a.first_month.localeCompare(b.first_month))
    .slice(1)
    .map((regime) => regime.first_month)
    .filter((month) => months.includes(month));
  const boundaryX = (month: string) => (x(month) ?? 0) - (x.step() * x.paddingInner()) / 2;

  const shown = hover !== null ? points[hover] : undefined;

  function readout(point: MonthPoint): string {
    const parts = [`${formatMonth(point.month)}: ${formatInt(point.won)} new customers`];
    parts.push(point.spend === null ? "spend unavailable" : `spend ${formatMoney(Ratio.of(BigInt(Math.round(point.spend))))}`);
    if (point.costPerWon) parts.push(`spend per new customer ${formatMoney(point.costPerWon)}`);
    return parts.join(", ");
  }

  function moveTo(index: number) {
    const clamped = Math.max(0, Math.min(points.length - 1, index));
    setHover(clamped);
    const point = points[clamped];
    if (point) setAnnounce(readout(point));
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const keys: Record<string, () => void> = {
      ArrowRight: () => moveTo((hover ?? -1) + 1),
      ArrowLeft: () => moveTo((hover ?? points.length) - 1),
      Home: () => moveTo(0),
      End: () => moveTo(points.length - 1),
      Escape: () => setHover(null),
    };
    const action = keys[event.key];
    if (!action) return;
    event.preventDefault();
    action();
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - rect.left;
    if (px < LEFT - 4) {
      setHover(null);
      return;
    }
    const firstCenter = center(months[0] ?? "");
    const index = Math.round((px - firstCenter) / x.step());
    setHover(Math.max(0, Math.min(points.length - 1, index)));
  }

  const tooltipLeft = shown ? Math.min(Math.max(center(shown.month), 110), Math.max(110, width - 110)) : 0;

  return (
    <section aria-labelledby="time-title" className="flex flex-col gap-5" data-testid="time-section" data-kpi-id="acq.time.new_customers">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="flex max-w-2xl flex-col gap-1">
          <h2 id="time-title" className="text-xl font-semibold">
            New customers over time
          </h2>

        </div>
        <button
          type="button"
          aria-pressed={showSplit}
          onClick={() => setSplit((value) => !value)}
          className="btn-secondary"
          data-testid="split-industry"
        >
          {showSplit ? "Hide industries" : "Split by industry"}
        </button>
      </div>

      <div className="card p-4 md:p-6">
        {showSplit ? (
          <ul className="mb-4 flex flex-wrap gap-x-5 gap-y-1.5" aria-label="Industries" data-testid="industry-legend">
            {summary.industries.map((industry, index) => (
              <li key={industry.code} className="flex items-center gap-2 text-sm text-ink-2">
                <span aria-hidden="true" className="inline-block size-2.5 rounded-sm" style={{ background: INDUSTRY_COLORS[index % INDUSTRY_COLORS.length] }} />
                {industry.label}
              </li>
            ))}
          </ul>
        ) : null}

        <div
          ref={ref}
          className="relative outline-offset-4"
          tabIndex={0}
          role="group"
          aria-label="New customers and spend by month. Use the left and right arrow keys to read each month. The monthly data table below has every value."
          onKeyDown={onKeyDown}
          onPointerMove={onPointerMove}
          onPointerLeave={() => setHover(null)}
          onBlur={() => setHover(null)}
          data-testid="time-charts"
        >
          <p className="mb-1 text-sm text-ink-2" aria-hidden="true">
            New customers a month
          </p>
          <svg width={width} height={wonHeight} aria-hidden="true" focusable="false" className="block overflow-visible">
            {wonTicks.map((tick) => (
              <g key={tick}>
                <line x1={LEFT} x2={width - RIGHT} y1={yWon(tick)} y2={yWon(tick)} stroke={tick === 0 ? "var(--viz-axis)" : "var(--viz-grid)"} strokeWidth={1} />
                <text x={LEFT - 8} y={yWon(tick)} dy="0.32em" textAnchor="end" className="fill-[var(--ink-2)] font-mono text-[11px]">
                  {formatInt(tick)}
                </text>
              </g>
            ))}
            {boundaries.map((month) => (
              <line key={month} x1={boundaryX(month)} x2={boundaryX(month)} y1={pad.top - 6} y2={wonHeight - pad.bottom} stroke="var(--ink-3)" strokeWidth={1} />
            ))}
            {points.map((point) => {
              const bx = barX(point.month);
              const opacity = highlight && !point.inPeriod ? 0.28 : 1;
              if (!showSplit) {
                const top = yWon(point.won);
                return (
                  <path key={point.month} d={columnPath(bx, top, barWidth, yWon(0) - top, true)} fill="var(--viz-1)" opacity={opacity} />
                );
              }
              let base = yWon(0);
              const lastIndex = point.byIndustry.reduce((last, value, index) => (value > 0 ? index : last), -1);
              return (
                <g key={point.month} opacity={opacity}>
                  {point.byIndustry.map((value, index) => {
                    if (value <= 0) return null;
                    const h = yWon(0) - yWon(value);
                    const y = base - h;
                    base = y;
                    const drawn = index === lastIndex ? h : Math.max(0, h - GAP);
                    return (
                      <path
                        key={index}
                        d={columnPath(bx, y + (h - drawn), barWidth, drawn, index === lastIndex)}
                        fill={INDUSTRY_COLORS[index % INDUSTRY_COLORS.length]}
                      />
                    );
                  })}
                </g>
              );
            })}
            {shown ? (
              <line x1={center(shown.month)} x2={center(shown.month)} y1={0} y2={wonHeight} stroke="var(--ink-2)" strokeWidth={1} />
            ) : null}
          </svg>

          <p className="mt-4 mb-1 text-sm text-ink-2" aria-hidden="true">
            S&amp;M spend a month
          </p>
          <svg width={width} height={spendHeight + 22} aria-hidden="true" focusable="false" className="block overflow-visible">
            {spendTicks.map((tick) => (
              <g key={tick}>
                <line x1={LEFT} x2={width - RIGHT} y1={ySpend(tick)} y2={ySpend(tick)} stroke={tick === 0 ? "var(--viz-axis)" : "var(--viz-grid)"} strokeWidth={1} />
                <text x={LEFT - 8} y={ySpend(tick)} dy="0.32em" textAnchor="end" className="fill-[var(--ink-2)] font-mono text-[11px]">
                  {formatCompact(tick)}
                </text>
              </g>
            ))}
            {boundaries.map((month) => (
              <g key={month}>
                <line x1={boundaryX(month)} x2={boundaryX(month)} y1={0} y2={spendHeight - pad.bottom} stroke="var(--ink-3)" strokeWidth={1} />
                <text x={boundaryX(month) + 5} y={8} className="fill-[var(--ink-2)] text-[11px]" data-testid="regime-marker">
                  {formatMonth(month)}
                </text>
              </g>
            ))}
            {points.map((point) => {
              if (point.spend === null) return null;
              const top = ySpend(Math.max(0, point.spend));
              return (
                <path
                  key={point.month}
                  d={columnPath(barX(point.month), top, barWidth, ySpend(0) - top, true)}
                  fill="var(--viz-spend)"
                  opacity={highlight && !point.inPeriod ? 0.28 : 1}
                />
              );
            })}
            {yearLabels(months).map(({ month, label }) => (
              <text key={label} x={x(month) ?? 0} y={spendHeight + 16} className="fill-[var(--ink-2)] font-mono text-[11px]">
                {label}
              </text>
            ))}
            {shown ? (
              <line x1={center(shown.month)} x2={center(shown.month)} y1={0} y2={spendHeight - pad.bottom} stroke="var(--ink-2)" strokeWidth={1} />
            ) : null}
          </svg>

          {shown ? (
            <div
              className="pointer-events-none absolute top-6 z-10 w-52 -translate-x-1/2 rounded-lg border border-line-strong bg-bg px-3 py-2 text-sm shadow-panel"
              style={{ left: tooltipLeft }}
              data-testid="time-tooltip"
            >
              <p className="mb-1 font-medium">{formatMonth(shown.month)}</p>
              <p className="flex justify-between gap-3">
                <span className="text-ink-2">New customers</span>
                <span className="num font-mono font-semibold">{formatInt(shown.won)}</span>
              </p>
              {showSplit
                ? summary.industries.map((industry, index) => (
                    <p key={industry.code} className="flex items-center justify-between gap-3 pl-1">
                      <span className="flex items-center gap-2 text-ink-2">
                        <span aria-hidden="true" className="inline-block h-0.5 w-3 rounded-full" style={{ background: INDUSTRY_COLORS[index % INDUSTRY_COLORS.length] }} />
                        {industry.label}
                      </span>
                      <span className="num font-mono">{formatInt(shown.byIndustry[index] ?? 0)}</span>
                    </p>
                  ))
                : null}
              <p className="flex justify-between gap-3">
                <span className="text-ink-2">Spend</span>
                <span className="num font-mono">{shown.spend === null ? "—" : formatCompact(shown.spend)}</span>
              </p>
              <p className="flex justify-between gap-3">
                <span className="text-ink-2">Per new customer</span>
                <span className="num font-mono">{shown.costPerWon ? formatCompact(shown.costPerWon.toNumber()) : "—"}</span>
              </p>
            </div>
          ) : null}
          <p className="sr-only" aria-live="polite">
            {announce}
          </p>
        </div>
      </div>

      <Disclosure testId="time-details">
        <dl className="divide-y divide-line">
          <DetailItem term="Spend per new customer">
            <CostLine points={points} />
          </DetailItem>
          <DetailItem term="Jun 2023">
            Spend a month fell sharply from Jun 2023 while new customers rose. The two spend periods are inferred from the spend data; the
            cause of the change is unknown.
          </DetailItem>
          <DetailItem term="Industries">
            Spend is company-wide. It is never split by industry, so there is no spend per new customer by industry.
          </DetailItem>
        </dl>
      </Disclosure>
    </section>
  );
}

/** Spend per new customer by month: one thin line, its own scale, with a table for screen readers. */
function CostLine({ points }: { points: MonthPoint[] }) {
  const [ref, width] = useElementWidth<HTMLDivElement>(600);
  const height = 120;
  const valid = points.filter((point) => point.costPerWon);
  const values = valid.map((point) => point.costPerWon!.toNumber());
  const ticks = niceTicks(Math.max(...values, 1), 3);
  const x = scaleLinear()
    .domain([0, Math.max(1, points.length - 1)])
    .range([LEFT, Math.max(LEFT + 10, width - RIGHT)]);
  const y = scaleLinear()
    .domain([0, ticks[ticks.length - 1] ?? 1])
    .range([height - 6, 8]);
  const index = new Map(points.map((point, i) => [point.month, i]));
  const path =
    line<MonthPoint>()
      .defined((point) => point.costPerWon !== null)
      .x((point) => x(index.get(point.month) ?? 0))
      .y((point) => y(point.costPerWon?.toNumber() ?? 0))(points) ?? "";
  const last = valid[valid.length - 1];

  return (
    <div ref={ref} className="flex flex-col gap-1" data-testid="cost-line">
      <svg width={width} height={height} aria-hidden="true" focusable="false" className="block overflow-visible">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={LEFT} x2={width - RIGHT} y1={y(tick)} y2={y(tick)} stroke={tick === 0 ? "var(--viz-axis)" : "var(--viz-grid)"} strokeWidth={1} />
            <text x={LEFT - 8} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-[var(--ink-2)] font-mono text-[11px]">
              {formatCompact(tick)}
            </text>
          </g>
        ))}
        <path d={path} fill="none" stroke="var(--viz-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {last ? (
          <circle cx={x(index.get(last.month) ?? 0)} cy={y(last.costPerWon!.toNumber())} r={4} fill="var(--viz-1)" stroke="var(--surface)" strokeWidth={2} />
        ) : null}
      </svg>
      {last ? (
        <p className={clsx("text-sm text-ink-2")}>
          {formatMonth(points[0]?.month)} – {formatMonth(last.month)}. Latest {formatMonth(last.month)}:{" "}
          <span className="num font-mono text-ink">{formatMoney(last.costPerWon)}</span>.
        </p>
      ) : null}
      <div className="sr-only">
        <table>
          <caption>Spend per new customer by month</caption>
          <thead>
            <tr>
              <th scope="col">Month</th>
              <th scope="col">Spend per new customer</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.month}>
                <td>{formatMonth(point.month)}</td>
                <td>{point.costPerWon ? formatMoney(point.costPerWon) : "unavailable"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
