"use client";

import { useState } from "react";
import { extent } from "d3-array";
import { scaleLinear } from "d3-scale";
import { curveMonotoneX, line } from "d3-shape";
import { formatMonth, formatPct } from "@/lib/format";
import { useElementWidth } from "@/lib/use-element-width";

export interface SparkPoint {
  runId: string;
  asOfMonth: string;
  value: number;
}

/**
 * Trend sparkline (D3 scales and line generator, rendered by React).
 * The line is neutral and the selected run is the one marked point: the
 * figure next to it carries the value, and a screen-reader table carries
 * every point, so nothing is readable by hover alone.
 */
export function Sparkline({
  points,
  activeRunId,
  caption,
  height = 44,
}: {
  points: SparkPoint[];
  activeRunId: string;
  caption: string;
  height?: number;
}) {
  const [ref, width] = useElementWidth<HTMLDivElement>(240);
  const [hover, setHover] = useState<number | null>(null);

  if (points.length < 2) {
    return (
      <div ref={ref} className="flex items-center text-sm text-ink-2" style={{ height }}>
        Not enough runs yet
      </div>
    );
  }

  const pad = 7;
  const x = scaleLinear()
    .domain([0, points.length - 1])
    .range([pad, Math.max(pad + 1, width - pad)]);
  const [lo = 0, hi = 100] = extent(points, (point) => point.value);
  const span = hi - lo || 0.2;
  const y = scaleLinear()
    .domain([lo - span * 0.2, hi + span * 0.2])
    .range([height - pad, pad]);
  const path =
    line<SparkPoint>()
      .x((_, index) => x(index))
      .y((point) => y(point.value))
      .curve(curveMonotoneX)(points) ?? "";

  const found = points.findIndex((point) => point.runId === activeRunId);
  const activeIndex = found >= 0 ? found : points.length - 1;
  const shownIndex = hover ?? activeIndex;
  const shown = points[shownIndex];

  function onMove(event: React.PointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const index = Math.round(x.invert(event.clientX - rect.left));
    setHover(Math.min(points.length - 1, Math.max(0, index)));
  }

  return (
    <div ref={ref} className="relative" onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
      <svg width={width} height={height} aria-hidden="true" focusable="false" className="block overflow-visible">
        <path d={path} fill="none" stroke="var(--chart-line)" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" />
        {hover !== null && shown ? (
          <line x1={x(shownIndex)} x2={x(shownIndex)} y1={0} y2={height} stroke="var(--line-strong)" strokeWidth={1} />
        ) : null}
        {shown ? (
          <circle cx={x(shownIndex)} cy={y(shown.value)} r={4.5} fill="var(--accent)" stroke="var(--bg)" strokeWidth={2} />
        ) : null}
      </svg>
      {hover !== null && shown ? (
        <div
          className="num pointer-events-none absolute z-10 -translate-x-1/2 rounded-md border border-line-strong bg-bg px-2 py-1 font-mono text-xs whitespace-nowrap shadow-panel"
          style={{ left: Math.min(Math.max(x(shownIndex), 56), Math.max(56, width - 56)), bottom: height + 4 }}
        >
          <span className="text-ink-2">{formatMonth(shown.asOfMonth)}</span>{" "}
          <span className="font-semibold">{formatPct(shown.value)}</span>
        </div>
      ) : null}
      {/* A table ignores width: 1px, so the wrapper is what hides it (and keeps it from widening the page). */}
      <div className="sr-only">
        <table>
          <caption>{caption}</caption>
          <thead>
            <tr>
              <th scope="col">As of</th>
              <th scope="col">Compliance</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.runId}>
                <td>{formatMonth(point.asOfMonth)}</td>
                <td>{formatPct(point.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
