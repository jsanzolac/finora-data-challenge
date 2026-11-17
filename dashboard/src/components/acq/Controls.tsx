"use client";

import { useId, useState } from "react";
import clsx from "clsx";
import { ChevronDown } from "lucide-react";
import { formatInt } from "@/lib/format";
import { rangeLabel, type PeriodOption } from "@/lib/acq/periods";
import type { Scenario, WonDefinition } from "@/lib/acq/types";
import { PlainSelect, type SelectGroup } from "@/components/ui/PlainSelect";
import { Skeleton } from "@/components/ui/Skeleton";

function periodNote(option: PeriodOption): string | undefined {
  if (option.kind === "full") return rangeLabel(option.months);
  if (option.partial) return `${option.months.length} ${option.months.length === 1 ? "month" : "months"}`;
  if (option.kind === "regime") return rangeLabel(option.months);
  return undefined;
}

function periodGroups(options: PeriodOption[]): SelectGroup[] {
  const kinds: { kind: PeriodOption["kind"]; label?: string }[] = [
    { kind: "full" },
    { kind: "regime", label: "Spend periods" },
    { kind: "year", label: "Years" },
    { kind: "quarter", label: "Quarters" },
    { kind: "month", label: "Months" },
  ];
  return kinds
    .map(({ kind, label }) => ({
      label,
      items: options
        .filter((option) => option.kind === kind)
        .map((option) => ({ value: option.id, text: option.label, note: periodNote(option) })),
    }))
    .filter((group) => group.items.length > 0);
}

export function periodTriggerText(option: PeriodOption): string {
  const note = periodNote(option);
  return note ? `${option.label} · ${note}` : option.label;
}

export function Controls({
  options,
  period,
  onPeriod,
  scenarios,
  scenarioId,
  onScenario,
  definition,
  onDefinition,
  probablyActive,
}: {
  options: PeriodOption[];
  period: PeriodOption;
  onPeriod: (id: string) => void;
  /** Undefined while the scenarios load (2-5 s). */
  scenarios: Scenario[] | undefined;
  scenarioId: string;
  onScenario: (id: string) => void;
  definition: WonDefinition;
  onDefinition: (definition: WonDefinition) => void;
  /** Won customers the canonical new-logo count leaves out over the full period. */
  probablyActive: number;
}) {
  const [open, setOpen] = useState(definition !== "user");
  const panelId = useId();
  const radioName = useId();

  const scenarioGroups: SelectGroup[] = scenarios
    ? [
        {
          items: scenarios.map((scenario) => ({
            value: scenario.scenario_id,
            text: scenario.label,
            note: scenario.status === "valid" ? undefined : "Invalid, see Details",
            disabled: scenario.status !== "valid",
          })),
        },
      ]
    : [];

  const definitions: { value: WonDefinition; title: string; hint: string }[] = [
    { value: "user", title: "Every first payment", hint: "Your definition. Customers whose first payment falls in the month." },
    {
      value: "new_logo",
      title: "Without customers probably already active",
      hint: `Leaves out ${formatInt(probablyActive)} customers whose first payment looks like it covers earlier months, so they were probably customers already.`,
    },
  ];

  return (
    <section aria-label="Filters" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <PlainSelect
          label="Period"
          value={period.id}
          onValueChange={onPeriod}
          groups={periodGroups(options)}
          triggerText={periodTriggerText(period)}
          testId="period-select"
          className="w-full sm:w-72"
        />
        {scenarios ? (
          <PlainSelect
            label="Conversion rates"
            value={scenarioId}
            onValueChange={onScenario}
            groups={scenarioGroups}
            testId="scenario-select"
            className="w-full sm:w-72"
          />
        ) : (
          <div className="w-full sm:w-72" role="status" aria-live="polite" data-testid="scenarios-loading">
            <span className="mb-1 block text-sm text-ink-2">Conversion rates</span>
            <div className="flex min-h-10 items-center gap-2 rounded-lg border border-line px-3">
              <Skeleton className="h-4 w-36 rounded" />
              <span className="sr-only">Loading the saved scenarios</span>
            </div>
          </div>
        )}
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
          className="btn-ghost min-h-10"
          data-testid="definition-toggle"
        >
          <ChevronDown aria-hidden="true" size={18} className={clsx("transition-transform", open ? "rotate-0" : "-rotate-90")} />
          Details
          {definition !== "user" ? <span className="text-ink">· without probably active</span> : null}
        </button>
      </div>

      <div id={panelId} hidden={!open} className="rounded-lg border border-line p-4">
        <fieldset>
          <legend className="mb-2 text-[0.9375rem] font-medium">Who counts as a new customer (Won)</legend>
          <div className="flex flex-col gap-2 md:flex-row md:gap-6">
            {definitions.map((option) => (
              <label key={option.value} className="flex max-w-md cursor-pointer items-start gap-3 rounded-md p-1">
                <input
                  type="radio"
                  name={radioName}
                  value={option.value}
                  checked={definition === option.value}
                  onChange={() => onDefinition(option.value)}
                  className="mt-1 size-4 accent-[var(--accent)]"
                  data-testid={`definition-${option.value}`}
                />
                <span className="flex flex-col">
                  <span className="text-[0.9375rem] text-ink">{option.title}</span>
                  <span className="text-sm text-ink-2">{option.hint}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      </div>
    </section>
  );
}
