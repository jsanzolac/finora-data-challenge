"use client";

import clsx from "clsx";
import { formatInt } from "@/lib/format";
import { formatCompact, formatMoney, formatSignedCompact } from "@/lib/acq/format";
import { Ratio } from "@/lib/acq/ratio";
import type { PeriodBridge, StepTotal } from "@/lib/mrr/bridge";
import type { MrrSummary } from "@/lib/mrr/types";
import { DetailItem, Disclosure } from "@/components/ui/Disclosure";
import { StatusDot } from "@/components/ui/StatusDot";
import { DRIVER_COLOR } from "./WhySection";

/** One floating bar on a 0..100% track; the zero line marks "no change". */
function Bar({ start, end, color, min, span }: { start: number; end: number; color: string; min: number; span: number }) {
  const pct = (value: number) => ((value - min) / span) * 100;
  const left = pct(Math.min(start, end));
  const width = Math.max(0.3, Math.abs(pct(end) - pct(start)));
  return (
    <span aria-hidden="true" className="relative block h-5">
      <span className="absolute inset-y-[-4px] w-px bg-line-strong" style={{ left: `${pct(0)}%` }} />
      <span
        className={clsx("absolute inset-y-0 rounded-[4px]", end === start && "opacity-0")}
        style={{ left: `${left}%`, width: `${width}%`, background: color }}
      />
    </span>
  );
}

interface Row {
  step: StepTotal;
  start: number;
  end: number;
}

/**
 * The MRR bridge as a horizontal waterfall: one row per step, in the API's order,
 * grouped by driver. Each bar floats from the running change before the step to the
 * running change after it, against a zero line (no change), so the scale stays
 * honest. Opening and closing are text rows. A driver the data can't show yet
 * (discounts today) is one "Not available" row, never a 0.
 */
export function BridgeSection({ summary, bridge }: { summary: MrrSummary; bridge: PeriodBridge }) {
  // Every driver that has bridge steps, in the order of its first step (the API's order).
  const groups = summary.drivers
    .map((driver) => ({ driver, steps: bridge.steps.filter((entry) => entry.step.driver === driver.code) }))
    .filter((group) => group.steps.length > 0)
    .sort((a, b) => (a.steps[0]?.step.order ?? 0) - (b.steps[0]?.step.order ?? 0));

  let running = 0;
  const rows = new Map<string, Row>();
  for (const group of groups) {
    if (!group.driver.available) continue;
    for (const entry of group.steps) {
      const value = entry.value?.toNumber() ?? 0;
      rows.set(entry.step.code, { step: entry, start: running, end: running + value });
      running += value;
    }
  }
  const net = bridge.change?.toNumber() ?? running;
  const extent = [0, net, ...[...rows.values()].flatMap((row) => [row.start, row.end])];
  const min = Math.min(...extent);
  const max = Math.max(...extent);
  const span = max - min || 1;

  const grid = "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 py-2 md:grid-cols-[13rem_minmax(0,1fr)_7rem]";

  return (
    <section aria-labelledby="bridge-title" className="flex flex-col gap-5" data-testid="bridge">
      <div className="flex flex-col gap-1">
        <h2 id="bridge-title" className="text-xl font-semibold">
          MRR bridge
        </h2>
        <p className="text-[0.9375rem] text-ink-2">From opening to closing MRR, step by step. Bars start at no change.</p>
      </div>

      <div className="card p-4 md:p-6">
        <div className={clsx(grid, "border-b border-line font-medium")} data-testid="bridge-opening" data-kpi-id="mrr.bridge.opening">
          <span>Opening MRR</span>
          <span className="hidden md:block" />
          <span className="num text-right font-mono">{bridge.opening ? formatCompact(bridge.opening.toNumber()) : "—"}</span>
        </div>

        {groups.map((group) => (
          <div key={group.driver.code} className="border-b border-line py-1" data-testid="bridge-group" data-driver={group.driver.code}>
            <p className="pt-2 text-sm text-ink-2">
              {group.driver.label}
              {group.driver.inferred ? " (inferred)" : ""}
            </p>
            {group.driver.available ? (
              <ul>
                {group.steps.map((entry) => {
                  const row = rows.get(entry.step.code);
                  return (
                    <li key={entry.step.code} className={grid} data-testid="bridge-step" data-step={entry.step.code} data-kpi-id={`mrr.bridge.${entry.step.code}`}>
                      <span className="text-base">{entry.step.label}</span>
                      <span className="col-span-2 row-start-2 md:col-span-1 md:row-start-auto">
                        {row ? (
                          <Bar start={row.start} end={row.end} color={DRIVER_COLOR[group.driver.code] ?? "var(--ink-3)"} min={min} span={span} />
                        ) : null}
                      </span>
                      <span className="num text-right font-mono text-base font-semibold" data-testid="bridge-step-value">
                        {entry.value ? formatSignedCompact(entry.value) : <span className="font-sans text-sm font-normal text-ink-2">Not available</span>}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className={clsx(grid, "text-ink-2")} data-testid="bridge-unavailable">
                <span className="flex items-center gap-2">
                  <StatusDot status="na" size={9} />
                  Not available until billing data
                </span>
                <span className="hidden md:block">
                  <span aria-hidden="true" className="block h-5 rounded-[4px] border border-dashed border-line-strong" />
                </span>
                <span className="text-right font-mono">—</span>
              </p>
            )}
          </div>
        ))}

        <div className={clsx(grid, "border-b border-line")} data-testid="bridge-net">
          <span className="text-base font-medium">Net change</span>
          <span className="col-span-2 row-start-2 md:col-span-1 md:row-start-auto">
            <Bar start={0} end={net} color="var(--viz-spend)" min={min} span={span} />
          </span>
          <span className="num text-right font-mono text-base font-semibold">{formatSignedCompact(bridge.change)}</span>
        </div>
        <div className={clsx(grid, "font-medium")} data-testid="bridge-closing" data-kpi-id="mrr.bridge.closing">
          <span>Closing MRR</span>
          <span className="hidden md:block" />
          <span className="num text-right font-mono">{bridge.closing ? formatCompact(bridge.closing.toNumber()) : "—"}</span>
        </div>
      </div>

      <Disclosure testId="bridge-details">
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Bridge table, scrolls sideways on small screens">
          <table className="w-full min-w-[30rem] border-separate border-spacing-0 text-[0.9375rem]" data-testid="bridge-table">
            <caption className="sr-only">The MRR bridge for the period: each step, its exact value and its customers</caption>
            <thead>
              <tr className="text-ink-2">
                <th scope="col" className="border-b border-line py-2 pr-3 text-left font-medium">Step</th>
                <th scope="col" className="border-b border-line py-2 pr-3 text-left font-medium">Driver</th>
                <th scope="col" className="border-b border-line py-2 pr-3 text-right font-medium">Value</th>
                <th scope="col" className="border-b border-line py-2 text-right font-medium">Customers</th>
              </tr>
            </thead>
            <tbody>
              <tr className="zebra-a">
                <th scope="row" className="py-2 pr-3 pl-1 text-left font-normal">Opening MRR</th>
                <td className="py-2 pr-3" />
                <td className="num py-2 pr-3 text-right font-mono">{formatMoney(bridge.opening)}</td>
                <td className="py-2" />
              </tr>
              {bridge.steps.map((entry, index) => {
                const driver = summary.drivers.find((candidate) => candidate.code === entry.step.driver);
                return (
                  <tr key={entry.step.code} className={index % 2 === 0 ? "zebra-b" : "zebra-a"}>
                    <th scope="row" className="py-2 pr-3 pl-1 text-left font-normal">{entry.step.label}</th>
                    <td className="py-2 pr-3 text-ink-2">{driver?.label ?? entry.step.driver}</td>
                    <td className="num py-2 pr-3 text-right font-mono">{entry.value ? formatMoney(entry.value) : "not available"}</td>
                    <td className="num py-2 pr-1 text-right font-mono">{entry.customers === null ? "—" : formatInt(entry.customers)}</td>
                  </tr>
                );
              })}
              <tr className="font-medium">
                <th scope="row" className="py-2 pr-3 pl-1 text-left">Closing MRR</th>
                <td className="py-2 pr-3" />
                <td className="num py-2 pr-3 text-right font-mono">{formatMoney(bridge.closing)}</td>
                <td className="py-2" />
              </tr>
            </tbody>
          </table>
        </div>
        <dl className="mt-3 divide-y divide-line border-t border-line">
          <DetailItem term="Customers">A customer counts once per month in each step, so a period can count the same customer in several months.</DetailItem>
          <DetailItem term="Exact values">
            Values are exact and in full units; the chart rounds to millions.{" "}
            {bridge.opening && bridge.closing
              ? `Opening ${formatMoney(bridge.opening)} plus the steps gives closing ${formatMoney(bridge.closing)}.`
              : ""}
          </DetailItem>
          {bridge.cashChange ? (
            <DetailItem term="Cash" kpiId="mrr.bridge.timing">
              Cash changed {formatSignedCompact(bridge.cashChange)}: the MRR change plus the timing of payments that MRR spreads out
              (catch-ups, prepayments, split payments, late price steps: {formatSignedCompact(bridge.timingChange ?? Ratio.ZERO)}).
            </DetailItem>
          ) : null}
        </dl>
      </Disclosure>
    </section>
  );
}
