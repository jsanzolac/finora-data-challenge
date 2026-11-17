"use client";

import { useEffect, useRef } from "react";
import clsx from "clsx";
import { scaleLinear, scalePoint } from "d3-scale";
import { line } from "d3-shape";
import { X } from "lucide-react";
import { RESTRICTED_VALUE } from "@/lib/api/types";
import { formatCompact, formatMoneyString } from "@/lib/acq/format";
import { Ratio } from "@/lib/acq/ratio";
import { useElementWidth } from "@/lib/use-element-width";
import type { AgentResult } from "@/lib/voice/types";
import { StatusDot } from "@/components/ui/StatusDot";
import { useVoice } from "./VoiceProvider";

/** Evidence levels of the semantic layer, as status tones (always shown with the word). */
const EVIDENCE_TONE: Record<string, string> = { observado: "pass", inferido: "warn", supuesto: "warn", "no probado": "na" };

type Cell = string | number | null;

/** "ingreso_inicial" -> "Ingreso inicial". The results carry field names, not labels. */
function columnLabel(column: string): string {
  const text = column.replace(/_/g, " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : column;
}

function cellText(cell: Cell, unit: string, numeric: boolean): string {
  if (cell === null || cell === undefined) return "—";
  if (cell === RESTRICTED_VALUE) return "Restringido";
  if (!numeric) return String(cell);
  if (unit === "money") return formatMoneyString(String(cell));
  if (unit === "pct") return `${Number(cell).toFixed(1)}%`;
  return Ratio.tryParse(String(cell)) ? Number(cell).toLocaleString("es") : String(cell);
}

function numberOf(cell: Cell): number | null {
  if (cell === null || cell === RESTRICTED_VALUE) return null;
  const value = Ratio.tryParse(String(cell));
  return value ? value.toNumber() : null;
}

/** Horizontal bars, one hue, value at the bar end (dataviz rules: ≤ 24px, 4px rounded end). */
function Bars({ result }: { result: AgentResult }) {
  const xIndex = Math.max(0, result.columns.indexOf(result.chart.x));
  const yIndex = Math.max(0, result.columns.indexOf(result.chart.y[0] ?? ""));
  const values = result.rows.map((row) => numberOf(row[yIndex] ?? null));
  const max = Math.max(...values.map((value) => Math.abs(value ?? 0)), 1);
  return (
    <ul className="flex flex-col gap-1.5" aria-hidden="true">
      {result.rows.map((row, index) => (
        <li key={index} className="grid grid-cols-[7rem_minmax(0,1fr)_5.5rem] items-center gap-2 text-sm">
          <span className="truncate">{String(row[xIndex] ?? "")}</span>
          <span className="h-4">
            <span className="block h-full rounded-r-[4px]" style={{ width: `${(Math.abs(values[index] ?? 0) / max) * 100}%`, background: "var(--viz-1)" }} />
          </span>
          <span className="num text-right font-mono">{values[index] === null ? "—" : formatCompact(values[index])}</span>
        </li>
      ))}
    </ul>
  );
}

/** One line, 2px, end-point label. */
function Line({ result }: { result: AgentResult }) {
  const [ref, width] = useElementWidth<HTMLDivElement>(360);
  const xIndex = Math.max(0, result.columns.indexOf(result.chart.x));
  const yIndex = Math.max(0, result.columns.indexOf(result.chart.y[0] ?? ""));
  const points = result.rows.map((row) => ({ x: String(row[xIndex] ?? ""), y: numberOf(row[yIndex] ?? null) }));
  const ys = points.map((point) => point.y).filter((value): value is number => value !== null);
  const height = 160;
  const x = scalePoint<string>().domain(points.map((point) => point.x)).range([44, Math.max(60, width - 44)]);
  const y = scaleLinear().domain([0, Math.max(...ys, 1)]).nice(3).range([height - 22, 10]);
  const path = line<{ x: string; y: number | null }>().defined((point) => point.y !== null).x((point) => x(point.x) ?? 0).y((point) => y(point.y ?? 0))(points) ?? "";
  const last = [...points].reverse().find((point) => point.y !== null);
  return (
    <div ref={ref} className="w-full min-w-0" aria-hidden="true">
      <svg width={width} height={height} focusable="false" className="block overflow-visible">
        {y.ticks(3).map((tick) => (
          <g key={tick}>
            <line x1={44} x2={width - 8} y1={y(tick)} y2={y(tick)} stroke={tick === 0 ? "var(--viz-axis)" : "var(--viz-grid)"} strokeWidth={1} />
            <text x={36} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-[var(--ink-2)] font-mono text-[11px]">
              {formatCompact(tick)}
            </text>
          </g>
        ))}
        <path d={path} fill="none" stroke="var(--viz-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {points.map((point) =>
          point.y === null ? null : <circle key={point.x} cx={x(point.x)} cy={y(point.y)} r={4} fill="var(--viz-1)" stroke="var(--bg)" strokeWidth={2} />,
        )}
        {last && last.y !== null ? (
          <text x={(x(last.x) ?? 0) + 8} y={y(last.y) - 8} className="fill-[var(--ink)] font-mono text-[11px]">
            {formatCompact(last.y)}
          </text>
        ) : null}
        {points.map((point) => (
          <text key={point.x} x={x(point.x)} y={height - 4} textAnchor="middle" className="fill-[var(--ink-2)] font-mono text-[10px]">
            {point.x}
          </text>
        ))}
      </svg>
    </div>
  );
}

/** The table twin: every value, zebra rows. */
function ResultTable({ result }: { result: AgentResult }) {
  const numeric = result.columns.map((column) => result.chart.y.includes(column));
  return (
    <div className="max-h-72 overflow-auto rounded-lg border border-line" tabIndex={0} role="region" aria-label={`Tabla: ${result.title_es}`}>
      <table className="w-full border-separate border-spacing-0 text-sm" data-testid="agent-table">
        <caption className="sr-only">{result.title_es}</caption>
        <thead>
          <tr>
            {result.columns.map((column, index) => (
              <th key={column} scope="col" className={clsx("sticky top-0 border-b border-line-strong bg-surface px-3 py-2 font-medium text-ink-2", numeric[index] ? "text-right" : "text-left")}>
                {columnLabel(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, rowIndex) => (
            <tr key={rowIndex} className={rowIndex % 2 === 0 ? "zebra-a" : "zebra-b"}>
              {row.map((cell, index) => (
                <td key={index} className={clsx("px-3 py-1.5", numeric[index] ? "num text-right font-mono" : "")}>
                  {cellText(cell, result.chart.unit, numeric[index] ?? false)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * "Gráfico del analista": a non-modal side panel below the header (the page and the voice
 * control stay usable while the conversation goes on). Dismissible with the close button or
 * Escape; keeps the last few charts.
 */
export function AgentChartPanel() {
  const voice = useVoice();
  const panelRef = useRef<HTMLElement>(null);
  const active = voice.charts.find((chart) => chart.result_id === voice.activeChartId) ?? voice.charts[0];
  const { closePanel, panelOpen } = voice;

  useEffect(() => {
    if (!panelOpen) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && panelRef.current?.contains(document.activeElement)) closePanel();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [panelOpen, closePanel]);

  if (!panelOpen || !active) return null;
  return (
    <aside
      ref={panelRef}
      lang="es"
      aria-label="Gráfico del analista"
      className="sheet-enter fixed inset-x-0 bottom-0 z-30 flex max-h-[70dvh] flex-col border-t border-line-strong bg-bg shadow-panel sm:inset-x-auto sm:top-[65px] sm:right-0 sm:max-h-none sm:w-[26rem] sm:border-t-0 sm:border-l"
      data-testid="agent-panel"
    >
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
        <h2 className="text-base font-semibold">Gráfico del analista</h2>
        <button type="button" onClick={closePanel} className="btn-ghost px-2" aria-label="Cerrar el gráfico" data-testid="agent-panel-close">
          <X aria-hidden="true" size={18} />
        </button>
      </div>
      <div className="flex flex-col gap-4 overflow-y-auto px-5 py-4">
        <div className="flex flex-col gap-1">
          <h3 className="text-[0.9375rem] font-semibold" data-testid="agent-chart-title">
            {active.title_es}
          </h3>
          <p className="text-sm text-ink-2">«{active.question}»</p>
        </div>
        {active.chart.type === "bar" ? <Bars result={active} /> : active.chart.type === "line" ? <Line result={active} /> : null}
        {active.evidence || (active.caveats_es && active.caveats_es.length > 0) ? (
          <div className="flex flex-col gap-1.5 text-sm" data-testid="agent-caveats">
            {active.evidence ? (
              <p className="flex items-center gap-2">
                <StatusDot status={EVIDENCE_TONE[active.evidence] ?? "na"} size={8} />
                <span className="font-medium">Evidencia: {active.evidence}</span>
              </p>
            ) : null}
            {active.caveats_es?.length ? (
              <ul className="flex list-disc flex-col gap-1 pl-5 text-ink-2">
                {active.caveats_es.map((caveat) => (
                  <li key={caveat}>{caveat}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        <ResultTable result={active} />
        {voice.charts.length > 1 ? (
          <nav aria-label="Gráficos anteriores" className="flex flex-col gap-1.5">
            <h3 className="text-sm font-medium text-ink-2">Anteriores</h3>
            <ul className="flex flex-col gap-1">
              {voice.charts
                .filter((chart) => chart.result_id !== active.result_id)
                .map((chart) => (
                  <li key={chart.result_id}>
                    <button type="button" onClick={() => voice.selectChart(chart.result_id)} className="w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-3" data-testid="agent-history-item">
                      {chart.title_es}
                    </button>
                  </li>
                ))}
            </ul>
          </nav>
        ) : null}
      </div>
    </aside>
  );
}

/** The last two or three turns, for people who can't hear or follow the voice. On by default. */
export function VoiceCaptions() {
  const voice = useVoice();
  const active = voice.state === "listening" || voice.state === "speaking" || voice.state === "connecting";
  if (!voice.captions || !active || voice.turns.length === 0) return null;
  return (
    <div
      lang="es"
      role="log"
      aria-live="polite"
      aria-label="Subtítulos de la conversación"
      className="fixed bottom-4 left-1/2 z-20 w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 rounded-xl border border-line-strong bg-bg px-4 py-3 shadow-panel"
      data-testid="voice-captions"
    >
      <ul className="flex flex-col gap-1 text-[0.9375rem]">
        {voice.turns.map((turn) => (
          <li key={turn.id} className={turn.role === "agent" ? "text-ink" : "text-ink-2"}>
            <span className="font-semibold">{turn.role === "agent" ? "Analista" : "Tú"}:</span> {turn.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
