"use client";

import clsx from "clsx";
import { ChevronDown } from "lucide-react";

/**
 * The "Details" disclosure: technical detail stays one tap away and off the
 * main surface. A native <details>, so it works with the keyboard and screen
 * readers with no script.
 */
export function Disclosure({
  title = "Details",
  children,
  className,
  testId,
  onToggle,
  bodyClassName,
  flush = false,
  kpiId,
}: {
  title?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  testId?: string;
  onToggle?: (open: boolean) => void;
  bodyClassName?: string;
  /** No body padding (for a full-width table). */
  flush?: boolean;
  /** `data-kpi-id` for the voice agent's highlight_kpi (docs/semantic_layer.md §1.6). */
  kpiId?: string;
}) {
  return (
    <details
      className={clsx("group rounded-lg border border-line", className)}
      data-testid={testId}
      data-kpi-id={kpiId}
      onToggle={(event) => onToggle?.(event.currentTarget.open)}
    >
      <summary className="flex min-h-11 list-none items-center gap-2 px-4 text-[0.9375rem] font-medium text-ink-2 hover:text-ink [&::-webkit-details-marker]:hidden">
        <ChevronDown aria-hidden="true" size={18} className="-rotate-90 transition-transform group-open:rotate-0" />
        {title}
      </summary>
      <div className={clsx("border-t border-line text-[0.9375rem] text-ink", !flush && "px-4 py-4", bodyClassName)}>{children}</div>
    </details>
  );
}

/** A term and its explanation inside a Details body. */
export function DetailItem({ term, children, kpiId }: { term: React.ReactNode; children: React.ReactNode; kpiId?: string }) {
  return (
    <div className="grid gap-1 py-2.5 sm:grid-cols-[12rem_1fr] sm:gap-4" data-kpi-id={kpiId}>
      <dt className="text-ink-2">{term}</dt>
      <dd className="leading-relaxed">{children}</dd>
    </div>
  );
}
