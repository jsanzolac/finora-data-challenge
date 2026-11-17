"use client";

import { useCallback, useMemo, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { formatDateUtc, formatMonth } from "@/lib/format";
import { useAcqScenarios, useAcqSummary } from "@/lib/acq/queries";
import { periodOptions, periodTotals, resolvePeriod } from "@/lib/acq/periods";
import { Ratio } from "@/lib/acq/ratio";
import { useAcqUrlState } from "@/lib/acq/url-state";
import { BASE_SCENARIO_ID, type AcqRun } from "@/lib/acq/types";
import { AppHeader } from "@/components/layout/AppHeader";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Controls } from "./Controls";
import { FunnelWorkbench } from "./FunnelWorkbench";
import { GrowthLostSection } from "./GrowthLostSection";
import { LeversSection } from "./LeversSection";
import { IndustriesSection } from "./IndustriesSection";
import { MonthlySection } from "./MonthlySection";
import { SignalsSection } from "./SignalsSection";
import { TimeSection } from "./TimeSection";

function DataAsOf({ run }: { run: AcqRun }) {
  return (
    <p className="flex min-h-10 items-center px-3 text-[0.9375rem] text-ink-2" data-testid="acq-as-of">
      Data as of {formatMonth(run.as_of_month)} · updated {formatDateUtc(run.built_at)}
    </p>
  );
}

function SectionSkeleton({ rows = 4, title }: { rows?: number; title: string }) {
  return (
    <div className="flex flex-col gap-5" aria-hidden="true">
      <span className="text-xl font-semibold text-ink-3">{title}</span>
      <div className="card flex flex-col gap-3 p-6">
        {Array.from({ length: rows }, (_, index) => (
          <Skeleton key={index} className="h-7 rounded-md" />
        ))}
      </div>
    </div>
  );
}

export function AcquisitionScreen() {
  const { state, update } = useAcqUrlState();
  const summaryQuery = useAcqSummary(state.run);
  const scenariosQuery = useAcqScenarios();
  const summary = summaryQuery.data;
  const scenarios = scenariosQuery.data;
  // The funnel's rates are the planner's volume lever.
  const [volume, setVolume] = useState<Ratio>(Ratio.ONE);
  const onVolumeChange = useCallback((next: Ratio) => setVolume(next), []);

  const options = useMemo(() => (summary ? periodOptions(summary) : []), [summary]);
  const period = summary ? resolvePeriod(options, state.period) : null;
  const totals = summary && period ? periodTotals(summary, period, state.def) : null;
  const probablyActive = useMemo(() => {
    if (!summary) return 0;
    return summary.months
      .filter((month) => month.month <= summary.run.data_complete_through)
      .reduce((sum, month) => sum + month.won - month.won_new_logo, 0);
  }, [summary]);

  const base = scenarios?.scenarios.find((scenario) => scenario.scenario_id === BASE_SCENARIO_ID && scenario.status === "valid");
  const requested = scenarios?.scenarios.find((scenario) => scenario.scenario_id === state.scenario);
  const selected = requested && requested.status === "valid" ? requested : base;
  const invalid = scenarios?.scenarios.filter((scenario) => scenario.status !== "valid") ?? [];
  const fallbackNote =
    scenarios && state.scenario !== BASE_SCENARIO_ID && selected?.scenario_id !== state.scenario
      ? requested
        ? `“${requested.label}” can't be used, so the funnel shows Base. The reason is in the funnel's Details.`
        : `There are no saved rates called “${state.scenario}”, so the funnel shows Base.`
      : null;

  // Contract v1.1: 404 `no_gold_run` before the first gold publish, 404 `unknown_run` for a run id that doesn't exist.
  const errorCode = summaryQuery.error instanceof ApiError ? summaryQuery.error.code : null;
  const noGoldRun = errorCode === "no_gold_run";
  const unknownRun = errorCode === "unknown_run";

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only z-50 rounded-md bg-bg px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2">
        Skip to content
      </a>
      <AppHeader section="acq" aside={summary ? <DataAsOf run={summary.run} /> : <Skeleton className="h-10 w-full rounded-lg sm:w-72" />} />

      <main id="main" className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col px-5 py-10 md:px-8 md:py-14">
        <h1 className="sr-only">Acquisition</h1>
        {summaryQuery.isError && !summary ? (
          <ErrorState
            title={noGoldRun ? "No acquisition data yet" : unknownRun ? "No data for this run" : "Couldn't load the data"}
            message={
              noGoldRun
                ? "The acquisition model hasn't been published yet. It appears here after its first successful run."
                : unknownRun
                  ? "This run doesn't exist. The latest run is still available."
                  : summaryQuery.error instanceof Error
                    ? summaryQuery.error.message
                    : "The request failed."
            }
            onRetry={unknownRun ? undefined : () => void summaryQuery.refetch()}
            action={
              state.run && !noGoldRun ? (
                <button type="button" className="btn-secondary" onClick={() => update({ run: null })}>
                  Go to the latest run
                </button>
              ) : null
            }
          />
        ) : !summary || !period || !totals ? (
          <div className="flex flex-col gap-14" aria-busy="true">
            <p className="sr-only" role="status">
              Loading the acquisition data
            </p>
            <div className="flex flex-wrap gap-3" aria-hidden="true">
              <Skeleton className="h-16 w-72 rounded-lg" />
              <Skeleton className="h-16 w-72 rounded-lg" />
            </div>
            <SectionSkeleton title="Funnel" rows={7} />
            <SectionSkeleton title="New customers over time" rows={5} />
          </div>
        ) : (
          <div
            className={summaryQuery.isPlaceholderData ? "flex flex-col gap-14 opacity-60 transition-opacity" : "flex flex-col gap-14"}
            aria-busy={summaryQuery.isFetching || scenariosQuery.isFetching}
          >
            <div className="flex flex-col gap-3">
              <Controls
                options={options}
                period={period}
                onPeriod={(id) => update({ period: id })}
                scenarios={scenarios?.scenarios}
                scenarioId={selected?.scenario_id ?? BASE_SCENARIO_ID}
                onScenario={(id) => update({ scenario: id })}
                definition={state.def}
                onDefinition={(def) => update({ def }, "replace")}
                probablyActive={probablyActive}
              />
              {fallbackNote ? (
                <p className="text-[0.9375rem] text-ink-2" role="status" data-testid="scenario-fallback">
                  {fallbackNote}
                </p>
              ) : null}
            </div>

            <LeversSection summary={summary} definition={state.def} volume={volume} />
            <GrowthLostSection summary={summary} definition={state.def} />

            {scenariosQuery.isError && !scenarios ? (
              <section aria-labelledby="funnel-title" className="flex flex-col gap-5">
                <h2 id="funnel-title" className="text-xl font-semibold">
                  Funnel
                </h2>
                <ErrorState
                  title="Couldn't load the conversion rates"
                  message={scenariosQuery.error instanceof Error ? scenariosQuery.error.message : "The request failed."}
                  onRetry={() => void scenariosQuery.refetch()}
                />
              </section>
            ) : !scenarios ? (
              <section aria-labelledby="funnel-title" className="flex flex-col gap-5" aria-busy="true" data-testid="funnel-loading">
                <div className="flex flex-col gap-1">
                  <h2 id="funnel-title" className="text-xl font-semibold">
                    Funnel
                  </h2>
                  <p className="text-[0.9375rem] text-ink-2" role="status">
                    Loading the conversion rates. This takes a few seconds.
                  </p>
                </div>
                <div className="card flex flex-col gap-3 p-6" aria-hidden="true">
                  {Array.from({ length: 7 }, (_, index) => (
                    <Skeleton key={index} className="h-8 rounded-md" />
                  ))}
                </div>
              </section>
            ) : selected && base ? (
              <FunnelWorkbench
                key={`${selected.scenario_id}|${selected.changed_at}`}
                summary={summary}
                period={period}
                totals={totals}
                definition={state.def}
                scenario={selected}
                base={base}
                invalidScenarios={invalid}
                canEdit={scenarios.can_edit}
                onSaved={(id) => update({ scenario: id })}
                onVolumeChange={onVolumeChange}
              />
            ) : (
              <section aria-labelledby="funnel-title" className="flex flex-col gap-5">
                <h2 id="funnel-title" className="text-xl font-semibold">
                  Funnel
                </h2>
                <ErrorState title="No usable conversion rates" message="The Base rates are missing or invalid. Ask Finance or RevOps to fix them." />
              </section>
            )}

            <TimeSection summary={summary} definition={state.def} period={period} />
            <IndustriesSection summary={summary} />
            <div className="flex flex-col gap-4">
              <SignalsSection summary={summary} definition={state.def} />
              <MonthlySection summary={summary} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
