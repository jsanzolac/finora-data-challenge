"use client";

import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { ArrowDown, Lock, RotateCcw, Save } from "lucide-react";
import { formatDateTimeUtc, formatInt } from "@/lib/format";
import { computeFunnel, overallRate, sensitivities, transitionsFor, type FunnelResult, type Transition } from "@/lib/acq/funnel";
import { costReasonText, formatCount, formatExact, formatMoney, formatSigned, formatSignedPct } from "@/lib/acq/format";
import { rangeLabel, type PeriodOption, type PeriodTotals } from "@/lib/acq/periods";
import { Ratio } from "@/lib/acq/ratio";
import { parsePercentDraft, percentText } from "@/lib/acq/scenario-form";
import { BASE_SCENARIO_ID, type AcqSummary, type Scenario, type WonDefinition } from "@/lib/acq/types";
import { DetailItem, Disclosure } from "@/components/ui/Disclosure";
import { StatusDot } from "@/components/ui/StatusDot";
import { RateInput } from "./RateInput";
import { SaveScenarioDialog } from "./SaveScenarioDialog";

const CHECK_TEXT: Record<string, string> = {
  "GR-01": "the id isn't in the allowed format",
  "GR-02": "a rate skips or repeats a stage",
  "GR-03": "a rate is 0% or less, or above 100%",
  "GR-04": "it doesn't have exactly the 6 rates",
  "GR-05": "two changes share the same time",
  "GR-06": "a change has no editor, reason or time",
};

function checkText(check: string): string {
  return CHECK_TEXT[check] ? `${CHECK_TEXT[check]} (${check})` : check;
}

type Drafts = Record<string, string>;

function draftsFor(transitions: Transition[]): Drafts {
  return Object.fromEntries(transitions.map((transition) => [transition.from, percentText(transition.rate)]));
}

/** Funnel and "If we change these rates": they share the rate drafts. Keyed by scenario, so a new one starts clean. */
export function FunnelWorkbench({
  summary,
  period,
  totals,
  definition,
  scenario,
  base,
  invalidScenarios,
  canEdit,
  onSaved,
  onVolumeChange,
}: {
  summary: AcqSummary;
  period: PeriodOption;
  totals: PeriodTotals;
  definition: WonDefinition;
  scenario: Scenario;
  base: Scenario;
  invalidScenarios: Scenario[];
  canEdit: boolean;
  onSaved: (scenarioId: string) => void;
  /** overall(current rates) ÷ overall(base): the volume lever of the planner. */
  onVolumeChange?: (volume: Ratio) => void;
}) {
  const saved = useMemo(() => transitionsFor(summary.stages, scenario.rates), [summary.stages, scenario.rates]);
  const baseTransitions = useMemo(() => transitionsFor(summary.stages, base.rates), [summary.stages, base.rates]);
  const [drafts, setDrafts] = useState<Drafts>(() => (saved ? draftsFor(saved) : {}));
  const [saveOpen, setSaveOpen] = useState(false);

  // Report the volume factor of the rates on screen (saved scenario plus valid drafts).
  const volume = useMemo(() => {
    if (!saved || !baseTransitions) return Ratio.ONE;
    const current = saved.map((transition) => {
      const draft = parsePercentDraft(drafts[transition.from] ?? percentText(transition.rate));
      return draft.ok ? { ...transition, rate: draft.rate } : transition;
    });
    return overallRate(current).div(overallRate(baseTransitions));
  }, [saved, baseTransitions, drafts]);
  const volumeKey = volume.toFixed(12);
  useEffect(() => {
    onVolumeChange?.(volume);
    // The key captures every change of the exact value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [volumeKey, onVolumeChange]);

  if (!saved || !baseTransitions) {
    return (
      <section aria-labelledby="funnel-title" className="flex flex-col gap-3">
        <h2 id="funnel-title" className="text-xl font-semibold">
          Funnel
        </h2>
        <p className="card p-6 text-ink-2">These conversion rates can&apos;t be used. Pick another set of rates.</p>
      </section>
    );
  }

  const parsed = saved.map((transition) => parsePercentDraft(drafts[transition.from] ?? percentText(transition.rate)));
  const effective: Transition[] = saved.map((transition, index) => {
    const draft = parsed[index]!;
    return draft.ok ? { ...transition, rate: draft.rate } : transition;
  });
  const errors = parsed.map((draft) => (draft.ok ? null : draft.message));
  const hasErrors = errors.some(Boolean);
  // An invalid draft counts as a change too, so Reset stays in reach while the error shows.
  const modified = hasErrors || effective.some((transition, index) => !transition.rate.equals(saved[index]!.rate));

  const funnel = computeFunnel({
    stages: summary.stages,
    transitions: effective,
    won: totals.won,
    spend: totals.spend,
    costNullReason: totals.costNullReason,
  });

  return (
    <>
      <FunnelSection
        summary={summary}
        period={period}
        totals={totals}
        definition={definition}
        funnel={funnel}
        saved={saved}
        drafts={drafts}
        errors={errors}
        modified={modified}
        hasErrors={hasErrors}
        canEdit={canEdit}
        scenario={scenario}
        invalidScenarios={invalidScenarios}
        effective={effective}
        onDraft={(from, text) => setDrafts((current) => ({ ...current, [from]: text }))}
        onReset={() => setDrafts(draftsFor(saved))}
        onSave={() => setSaveOpen(true)}
      />

      {canEdit ? (
        <SaveScenarioDialog
          open={saveOpen}
          onOpenChange={setSaveOpen}
          scenario={scenario}
          transitions={effective}
          onSaved={(id) => {
            setSaveOpen(false);
            onSaved(id);
          }}
        />
      ) : null}
    </>
  );
}

function FunnelSection({
  summary,
  period,
  totals,
  definition,
  funnel,
  saved,
  drafts,
  errors,
  modified,
  hasErrors,
  canEdit,
  scenario,
  invalidScenarios,
  effective,
  onDraft,
  onReset,
  onSave,
}: {
  summary: AcqSummary;
  period: PeriodOption;
  totals: PeriodTotals;
  definition: WonDefinition;
  funnel: FunnelResult;
  saved: Transition[];
  drafts: Drafts;
  errors: (string | null)[];
  modified: boolean;
  hasErrors: boolean;
  canEdit: boolean;
  scenario: Scenario;
  invalidScenarios: Scenario[];
  effective: Transition[];
  onDraft: (from: string, text: string) => void;
  onReset: () => void;
  onSave: () => void;
}) {
  const max = funnel.stages[0]?.count.toNumber() ?? 0;
  const labelOf = (code: string) => summary.stages.find((stage) => stage.code === code)?.label ?? code;

  return (
    <section aria-labelledby="funnel-title" className="flex flex-col gap-5" data-testid="funnel">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="flex max-w-2xl flex-col gap-1">
          <h2 id="funnel-title" className="text-xl font-semibold">
            Funnel
          </h2>
          <p className="text-[0.9375rem] text-ink-2">
            Only Won is measured. The other stages are worked back from Won with these rates, so the funnel has the same shape every
            month. The rates are the volume lever in the planner above.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2" aria-live="polite">
          {modified ? (
            <>
              <span className="mr-1 flex items-center gap-2 text-[0.9375rem] font-medium" data-testid="modified">
                <StatusDot status="warn" size={10} />
                Modified
              </span>
              <button type="button" className="btn-secondary" onClick={onReset} data-testid="reset-rates">
                <RotateCcw aria-hidden="true" size={16} />
                Reset
              </button>
              {canEdit ? (
                <button type="button" className="btn-primary" onClick={onSave} disabled={hasErrors} data-testid="save-scenario">
                  <Save aria-hidden="true" size={16} />
                  Save as scenario
                </button>
              ) : null}
            </>
          ) : null}
          {modified && !canEdit ? (
            <span className="flex basis-full items-center justify-end gap-1.5 text-sm text-ink-2" data-testid="not-saved-note">
              <Lock aria-hidden="true" size={14} />
              Not saved. Finance and RevOps can save rates.
            </span>
          ) : null}
        </div>
      </div>

      <div className="card p-4 md:p-6" data-kpi-id="acq.funnel.stages">
        <div
          aria-hidden="true"
          className="hidden grid-cols-[9.5rem_minmax(0,1fr)_7.5rem_8.5rem] gap-x-4 border-b border-line pb-2 text-sm text-ink-2 md:grid"
        >
          <span>Stage</span>
          <span />
          <span className="text-right">Count</span>
          <span className="text-right">Cost per unit</span>
        </div>
        <p aria-hidden="true" className="flex justify-end gap-4 border-b border-line pb-2 text-sm text-ink-2 md:hidden">
          <span>Count</span>
          <span>Cost per unit</span>
        </p>
        <ol className="flex flex-col" aria-label="Funnel stages, New to Won">
          {funnel.stages.map((stage, index) => {
            const width = max > 0 ? Math.max(0.4, (stage.count.toNumber() / max) * 100) : 0;
            const transition = saved[index];
            return (
              <li key={stage.code} className="flex flex-col" data-testid="funnel-stage" data-stage={stage.code}>
                <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-4 gap-y-1.5 py-2 md:grid-cols-[9.5rem_minmax(0,1fr)_7.5rem_8.5rem]">
                  <span className="flex flex-col leading-tight">
                    <span className="text-base font-medium">{stage.label}</span>
                    <span className={clsx("text-sm", stage.real ? "font-medium text-ink-2" : "text-ink-3")} data-testid="stage-basis">
                      {stage.real ? "Real" : "Estimated"}
                    </span>
                  </span>
                  <span aria-hidden="true" className="col-span-3 row-start-2 h-5 md:col-span-1 md:row-start-auto">
                    <span
                      className="block h-full rounded-r-[4px] transition-[width] duration-200"
                      style={{ width: `${width}%`, background: stage.real ? "var(--viz-real)" : "var(--viz-est)" }}
                    />
                  </span>
                  <span className="num text-right font-mono text-base font-semibold md:text-lg" data-testid="stage-count">
                    <span className="sr-only">Count: </span>
                    {stage.real ? formatExact(stage.count, 0) : formatCount(stage.count)}
                  </span>
                  <span
                    className="num text-right font-mono text-[0.9375rem] text-ink-2"
                    data-testid="stage-cost"
                    data-kpi-id={stage.real ? "acq.funnel.won_cost" : undefined}
                  >
                    <span className="sr-only">Cost per unit: </span>
                    {stage.costPerUnit ? (
                      formatMoney(stage.costPerUnit)
                    ) : (
                      <span title={costReasonText(funnel.costUnavailable)}>
                        —<span className="sr-only"> unavailable</span>
                      </span>
                    )}
                  </span>
                </div>
                {transition ? (
                  <div className="flex items-center gap-3 border-l-2 border-line py-0.5 pl-3 md:ml-1" data-testid="rate-row">
                    <ArrowDown aria-hidden="true" size={15} className="text-ink-3" />
                    <RateInput
                      fromLabel={labelOf(transition.from)}
                      toLabel={labelOf(transition.to)}
                      value={drafts[transition.from] ?? percentText(transition.rate)}
                      savedRate={transition.rate}
                      onChange={(text) => onDraft(transition.from, text)}
                      error={errors[index] ?? null}
                      testId={`rate-${transition.from}`}
                    />
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>

        {funnel.costUnavailable || totals.lowN ? (
          <div className="mt-3 flex flex-col gap-1.5 border-t border-line pt-3 text-[0.9375rem]">
            {funnel.costUnavailable ? (
              <p className="flex items-start gap-2" data-testid="cost-unavailable">
                <span className="mt-1.5">
                  <StatusDot status="warn" size={9} />
                </span>
                <span>
                  <span className="font-medium">Cost per unit unavailable.</span> {costReasonText(funnel.costUnavailable)}
                </span>
              </p>
            ) : null}
            {totals.lowN && !totals.won.isZero() ? (
              <p className="flex items-start gap-2" data-testid="low-n">
                <span className="mt-1.5">
                  <StatusDot status="warn" size={9} />
                </span>
                <span>
                  <span className="font-medium">Fewer than 10 new customers.</span> Treat these figures with care.
                </span>
              </p>
            ) : null}
          </div>
        ) : null}
      </div>

      <Disclosure testId="funnel-details">
        <dl className="divide-y divide-line">
          <DetailItem term="How it is worked out">
            Won counts customers whose first payment fell in the period
            {definition === "new_logo" ? ", without those probably already active" : ""}. Each earlier stage is the next stage divided by
            the rate between them. Cost per unit is the period&apos;s total S&amp;M spend divided by the stage count. Because the rates are
            assumptions, the estimated stages restate Won and add no information about where customers are lost.
          </DetailItem>
          <DetailItem term="Period">
            {rangeLabel(period.months)}, {formatInt(period.months.length)} {period.months.length === 1 ? "month" : "months"}
            {period.kind === "regime" ? ". The spend periods are inferred from the spend data; the cause of the change is unknown" : ""}.
            Won <span className="num font-mono">{formatExact(totals.won, 0)}</span>, total S&amp;M spend{" "}
            <span className="num font-mono">{totals.spend ? formatMoney(totals.spend) : "unavailable"}</span>.
          </DetailItem>
          <DetailItem term="+1 point on one rate">
            <ul className="flex flex-col gap-0.5" data-testid="sensitivity" data-kpi-id="acq.funnel.sensitivity">
              {sensitivities(totals.won, effective).map((row) => (
                <li key={row.from} data-testid="sensitivity-row">
                  {labelOf(row.from)} → {labelOf(row.to)}:{" "}
                  {row.wonPctPerPoint ? (
                    <>
                      <span className="num font-mono">{formatSignedPct(row.wonPctPerPoint)}</span> new customers (
                      <span className="num font-mono">{formatSigned(row.wonPerPoint, 1)}</span>)
                    </>
                  ) : (
                    "can't rise a point"
                  )}
                </li>
              ))}
            </ul>
            <p className="mt-1 text-ink-2">
              The lowest rate always gives the most per point. That is arithmetic, not evidence that it is the easiest rate to move.
            </p>
          </DetailItem>
          <DetailItem term="These rates">
            {scenario.label}. Last changed {formatDateTimeUtc(scenario.changed_at)} by {scenario.changed_by}: “{scenario.change_reason}”.
            {scenario.scenario_id === BASE_SCENARIO_ID
              ? summary.run.base_rates_match_seed
                ? " Base still holds the rates set on 17 Nov 2026."
                : " Base has been changed since the rates set on 17 Nov 2026."
              : ""}
          </DetailItem>
          {invalidScenarios.length > 0 ? (
            <DetailItem term="Not usable">
              <ul className="flex flex-col gap-1" data-testid="invalid-scenarios">
                {invalidScenarios.map((entry) => (
                  <li key={entry.scenario_id}>
                    <span className="font-medium">{entry.label}</span>: {entry.failed_checks.map(checkText).join("; ") || "invalid"}.
                  </li>
                ))}
              </ul>
            </DetailItem>
          ) : null}
          {!canEdit ? (
            <DetailItem term="Your access">
              You can try other rates here; they stay on this screen. Finance and RevOps can save them for everyone.
            </DetailItem>
          ) : null}
        </dl>
      </Disclosure>
    </section>
  );
}
