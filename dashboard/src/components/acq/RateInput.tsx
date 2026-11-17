"use client";

import { useId } from "react";
import clsx from "clsx";
import { Minus, Plus } from "lucide-react";
import { Ratio } from "@/lib/acq/ratio";
import { parsePercentDraft, percentText } from "@/lib/acq/scenario-form";

const POINT = Ratio.of(1n);
const FINE = Ratio.parse("0.1");
const HUNDRED = Ratio.of(100n);
const MIN = Ratio.parse("0.01");

function step(text: string, fallback: Ratio, delta: Ratio): string {
  const parsed = parsePercentDraft(text);
  const current = parsed.ok ? parsed.rate.mul(HUNDRED) : fallback.mul(HUNDRED);
  let next = current.add(delta);
  if (next.compare(MIN) < 0) next = MIN;
  if (next.compare(HUNDRED) > 0) next = HUNDRED;
  return percentText(next.div(HUNDRED));
}

/**
 * A conversion rate typed as a percent, with −/+ buttons of one point.
 * Arrow Up / Down step one point (with Shift, a tenth), Page Up / Down ten.
 * The field accepts free typing; the error shows under it and the funnel keeps
 * the last valid value until it is fixed.
 */
export function RateInput({
  fromLabel,
  toLabel,
  value,
  savedRate,
  onChange,
  error,
  testId,
}: {
  fromLabel: string;
  toLabel: string;
  /** The draft text, a percent. */
  value: string;
  /** The rate in the selected scenario, to mark the field as changed. */
  savedRate: Ratio;
  onChange: (text: string) => void;
  error: string | null;
  testId?: string;
}) {
  const errorId = useId();
  const parsed = parsePercentDraft(value);
  const effective = parsed.ok ? parsed.rate : savedRate;
  const changed = parsed.ok && !parsed.rate.equals(savedRate);
  const percent = effective.mul(HUNDRED);
  const label = `Conversion from ${fromLabel} to ${toLabel}, percent`;

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    const map: Record<string, Ratio> = {
      ArrowUp: event.shiftKey ? FINE : POINT,
      ArrowDown: (event.shiftKey ? FINE : POINT).neg(),
      PageUp: Ratio.of(10n),
      PageDown: Ratio.of(-10n),
    };
    const delta = map[event.key];
    if (!delta) return;
    event.preventDefault();
    onChange(step(value, savedRate, delta));
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1">
        <button
          type="button"
          tabIndex={-1}
          aria-hidden="true"
          disabled={percent.compare(Ratio.of(1n)) <= 0}
          onClick={() => onChange(step(value, savedRate, POINT.neg()))}
          className="flex size-8 items-center justify-center rounded-md text-ink-2 hover:bg-surface-3 hover:text-ink disabled:opacity-40"
        >
          <Minus size={14} />
        </button>
        <span
          className={clsx(
            "flex h-9 items-center rounded-md border bg-bg pr-2 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent",
            error ? "tone-fail border-[var(--tone)]" : changed ? "border-accent" : "border-line-strong",
          )}
        >
          <input
            type="text"
            inputMode="decimal"
            role="spinbutton"
            aria-label={label}
            aria-valuemin={0.01}
            aria-valuemax={100}
            aria-valuenow={Number(percent.toFixed(2))}
            aria-valuetext={`${percentText(effective)} percent`}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={onKeyDown}
            className="num w-14 bg-transparent px-2 text-right font-mono text-[0.9375rem] text-ink outline-none"
            data-testid={testId}
            data-changed={changed ? "true" : undefined}
          />
          <span aria-hidden="true" className="font-mono text-[0.9375rem] text-ink-2">
            %
          </span>
        </span>
        <button
          type="button"
          tabIndex={-1}
          aria-hidden="true"
          disabled={percent.compare(HUNDRED) >= 0}
          onClick={() => onChange(step(value, savedRate, POINT))}
          className="flex size-8 items-center justify-center rounded-md text-ink-2 hover:bg-surface-3 hover:text-ink disabled:opacity-40"
        >
          <Plus size={14} />
        </button>
      </div>
      {error ? (
        <p id={errorId} className="tone-fail text-tone text-sm" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
