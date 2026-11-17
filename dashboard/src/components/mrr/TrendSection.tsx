"use client";

import { useMemo, useState } from "react";
import { scaleBand, scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { formatMonth } from "@/lib/format";
import { formatCompact } from "@/lib/acq/format";
import type { PeriodOption } from "@/lib/acq/periods";
import { Ratio } from "@/lib/acq/ratio";
import type { MrrSummary } from "@/lib/mrr/types";
import { useElementWidth } from "@/lib/use-element-width";
import { DRIVER_COLOR } from "./WhySection";

const LEFT = 52;
const RIGHT = 12;

interface Point {
  month: string;
  closing: number | null;
  /** Per shown driver: its change in the month (null when unknown). */
  values: (number | null)[];
  provisional: boolean;
  inPeriod: boolean;
}

function columnPath(x: number, y0: number, y1: number, width: number): string {
  const top = Math.min(y0, y1);
  const height = Math.abs(y1 - y0);
  if (height <= 0) return "";
  const r = Math.min(3, width / 2, height);
  const up = y1 < y0;
  // Round the data end only (top for an increase, bottom for a decrease).
  return up
    ? `M${x},${top + height}V${top + r}Q${x},${top} ${x + r},${top}H${x + width - r}Q${x + width},${top} ${x + width},${top + r}V${top + height}Z`
    : `M${x},${top}V${top + height - r}Q${x},${top + height} ${x + r},${top + height}H${x + width - r}Q${x + width},${top + height} ${x + width},${top + height - r}V${top}Z`;
}

export function TrendSection({ summary, period }: { summary: MrrSummary; period: PeriodOption }) {
  const [ref, width] = useElementWidth<HTMLDivElement>(900);
  const [hover, setHover] = useState<number | null>(null);
  const [announce, setAnnounce] = useState("");
  const shown = useMemo(() => summary.drivers.filter((driver) => driver.available), [summary.drivers]);

  const points: Point[] = useMemo(
    () =>
      summary.months.map((month) => ({
        month: month.month,
        closing: Ratio.tryParse(month.closing_mrr_value)?.toNumber() ?? null,
        // Σ of the driver's known steps in the month (null when all are null), as in the bridge.
        values: shown.map((driver) => {
          const known = summary.steps
            .filter((entry) => entry.driver === driver.code)
            .map((entry) => Ratio.tryParse(month.step_value[entry.code]))
            .filter((value): value is Ratio => value !== null);
          return known.length === 0 ? null : known.reduce((sum, value) => sum.add(value), Ratio.ZERO).toNumber();
        }),
        provisional: month.is_provisional,
        inPeriod: period.months.includes(month.month),
      })),
    [summary, shown, period],
  );

  const months = points.map((point) => point.month);
  const x = scaleBand<string>().domain(months).range([LEFT, Math.max(LEFT + 10, width - RIGHT)]).paddingInner(0.25).paddingOuter(0.1);
  const barWidth = Math.min(24, x.bandwidth());
  const center = (month: string) => (x(month) ?? 0) + x.bandwidth() / 2;
  const highlight = period.kind !== "full" || period.months.length < months.length;

  const lineHeight = 150;
  const closings = points.map((point) => point.closing).filter((value): value is number => value !== null);
  const yLine = scaleLinear()
    .domain([Math.min(...closings) * 0.95, Math.max(...closings) * 1.02])
    .nice(4)
    .range([lineHeight - 6, 10]);
  const path =
    line<Point>()
      .defined((point) => point.closing !== null)
      .x((point) => center(point.month))
      .y((point) => yLine(point.closing ?? 0))(points) ?? "";

  const barHeight = 170;
  const ups = points.map((point) => point.values.reduce<number>((sum, value) => sum + Math.max(0, value ?? 0), 0));
  const downs = points.map((point) => point.values.reduce<number>((sum, value) => sum + Math.min(0, value ?? 0), 0));
  const yBar = scaleLinear()
    .domain([Math.min(0, ...downs), Math.max(0, ...ups)])
    .nice(4)
    .range([barHeight - 6, 8]);

  const active = hover !== null ? points[hover] : undefined;
  const lastClosing = [...points].reverse().find((point) => point.closing !== null);

  function readout(point: Point): string {
    const parts = [`${formatMonth(point.month)}: MRR ${point.closing === null ? "not available" : formatCompact(point.closing)}`];
    shown.forEach((driver, index) => {
      const value = point.values[index];
      parts.push(`${driver.label} ${value === null || value === undefined ? "not available" : `${value >= 0 ? "+" : "−"}${formatCompact(Math.abs(value))}`}`);
    });
    if (point.provisional) parts.push("provisional");
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
    const px = event.clientX - event.currentTarget.getBoundingClientRect().left;
    if (px < LEFT - 4) return setHover(null);
    const index = Math.round((px - center(months[0] ?? "")) / x.step());
    setHover(Math.max(0, Math.min(points.length - 1, index)));
  }

  const years: { month: string; label: string }[] = [];
  for (const month of months) if (!years.some((entry) => entry.label === month.slice(0, 4))) years.push({ month, label: month.slice(0, 4) });
  const lineTicks = yLine.ticks(3);
  const barTicks = yBar.ticks(4);

  return (
    <section aria-labelledby="trend-title" className="flex flex-col gap-5" data-testid="trend" data-kpi-id="mrr.trend">
      <h2 id="trend-title" className="text-xl font-semibold">
        MRR by month
      </h2>
      <div className="card p-4 md:p-6">
        <ul className="mb-4 flex flex-wrap gap-x-5 gap-y-1.5" aria-label="Drivers" data-testid="trend-legend">
          {shown.map((driver) => (
            <li key={driver.code} className="flex items-center gap-2 text-sm text-ink-2">
              <span aria-hidden="true" className="inline-block size-2.5 rounded-sm" style={{ background: DRIVER_COLOR[driver.code] ?? "var(--ink-3)" }} />
              {driver.label}
              {driver.inferred ? " (inferred)" : ""}
            </li>
          ))}
        </ul>
        <div
          ref={ref}
          className="relative outline-offset-4"
          tabIndex={0}
          role="group"
          aria-label="MRR and its change by driver, by month. Use the left and right arrow keys to read each month. The monthly data table below has every value."
          onKeyDown={onKeyDown}
          onPointerMove={onPointerMove}
          onPointerLeave={() => setHover(null)}
          onBlur={() => setHover(null)}
          data-testid="trend-charts"
        >
          <p className="mb-1 text-sm text-ink-2" aria-hidden="true">
            MRR at month end
          </p>
          <svg width={width} height={lineHeight} aria-hidden="true" focusable="false" className="block overflow-visible">
            {lineTicks.map((tick) => (
              <g key={tick}>
                <line x1={LEFT} x2={width - RIGHT} y1={yLine(tick)} y2={yLine(tick)} stroke="var(--viz-grid)" strokeWidth={1} />
                <text x={LEFT - 8} y={yLine(tick)} dy="0.32em" textAnchor="end" className="fill-[var(--ink-2)] font-mono text-[11px]">
                  {formatCompact(tick)}
                </text>
              </g>
            ))}
            <path d={path} fill="none" stroke="var(--ink)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {lastClosing && lastClosing.closing !== null ? (
              <circle cx={center(lastClosing.month)} cy={yLine(lastClosing.closing)} r={4} fill="var(--ink)" stroke="var(--surface)" strokeWidth={2} />
            ) : null}
            {active ? <line x1={center(active.month)} x2={center(active.month)} y1={0} y2={lineHeight} stroke="var(--ink-3)" strokeWidth={1} /> : null}
          </svg>

          <p className="mt-4 mb-1 text-sm text-ink-2" aria-hidden="true">
            Change by driver
          </p>
          <svg width={width} height={barHeight + 22} aria-hidden="true" focusable="false" className="block overflow-visible">
            {barTicks.map((tick) => (
              <g key={tick}>
                <line x1={LEFT} x2={width - RIGHT} y1={yBar(tick)} y2={yBar(tick)} stroke={tick === 0 ? "var(--viz-axis)" : "var(--viz-grid)"} strokeWidth={1} />
                <text x={LEFT - 8} y={yBar(tick)} dy="0.32em" textAnchor="end" className="fill-[var(--ink-2)] font-mono text-[11px]">
                  {tick === 0 ? "0" : `${tick > 0 ? "+" : "−"}${formatCompact(Math.abs(tick))}`}
                </text>
              </g>
            ))}
            {points.map((point) => {
              let up = 0;
              let down = 0;
              const bx = (x(point.month) ?? 0) + (x.bandwidth() - barWidth) / 2;
              const opacity = highlight && !point.inPeriod ? 0.28 : point.provisional ? 0.6 : 1;
              return (
                <g key={point.month} opacity={opacity} data-provisional={point.provisional ? "true" : undefined}>
                  {point.values.map((value, index) => {
                    if (value === null || value === 0) return null;
                    const driver = shown[index]!;
                    const from = value > 0 ? up : down;
                    const to = from + value;
                    if (value > 0) up = to;
                    else down = to;
                    const gap = 1;
                    const y0 = yBar(from) + (value > 0 ? -gap : gap) * (from === 0 ? 0 : 1);
                    return <path key={driver.code} d={columnPath(bx, y0, yBar(to), barWidth)} fill={DRIVER_COLOR[driver.code] ?? "var(--ink-3)"} />;
                  })}
                </g>
              );
            })}
            {years.map(({ month, label }) => (
              <text key={label} x={x(month) ?? 0} y={barHeight + 16} className="fill-[var(--ink-2)] font-mono text-[11px]">
                {label}
              </text>
            ))}
            {active ? <line x1={center(active.month)} x2={center(active.month)} y1={0} y2={barHeight} stroke="var(--ink-3)" strokeWidth={1} /> : null}
          </svg>

          {active ? (
            <div
              className="pointer-events-none absolute top-6 z-10 w-56 -translate-x-1/2 rounded-lg border border-line-strong bg-bg px-3 py-2 text-sm shadow-panel"
              style={{ left: Math.min(Math.max(center(active.month), 120), Math.max(120, width - 120)) }}
              data-testid="trend-tooltip"
            >
              <p className="mb-1 font-medium">
                {formatMonth(active.month)}
                {active.provisional ? <span className="font-normal text-ink-2"> · provisional</span> : null}
              </p>
              <p className="flex justify-between gap-3">
                <span className="text-ink-2">MRR</span>
                <span className="num font-mono font-semibold">{active.closing === null ? "—" : formatCompact(active.closing)}</span>
              </p>
              {shown.map((driver, index) => {
                const value = active.values[index];
                return (
                  <p key={driver.code} className="flex items-center justify-between gap-3">
                    <span className="flex items-center gap-2 text-ink-2">
                      <span aria-hidden="true" className="inline-block h-0.5 w-3 rounded-full" style={{ background: DRIVER_COLOR[driver.code] ?? "var(--ink-3)" }} />
                      {driver.label}
                    </span>
                    <span className="num font-mono">
                      {value === null || value === undefined ? "—" : `${value >= 0 ? "+" : "−"}${formatCompact(Math.abs(value))}`}
                    </span>
                  </p>
                );
              })}
            </div>
          ) : null}
          <p className="sr-only" aria-live="polite">
            {announce}
          </p>
        </div>
        <p className="mt-3 text-sm text-ink-2">The last months are lighter while their churn is provisional.</p>
      </div>
    </section>
  );
}
