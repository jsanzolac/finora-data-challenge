"use client";

import { useMemo } from "react";
import { ApiError } from "@/lib/api/client";
import { formatDateUtc, formatMonth } from "@/lib/format";
import { rangeLabel, resolvePeriod } from "@/lib/acq/periods";
import { mrrPeriodOptions, periodBridge } from "@/lib/mrr/bridge";
import { useMrrSummary } from "@/lib/mrr/queries";
import { useMrrUrlState } from "@/lib/mrr/url-state";
import { AppHeader } from "@/components/layout/AppHeader";
import { ErrorState } from "@/components/ui/ErrorState";
import { PlainSelect, type SelectGroup } from "@/components/ui/PlainSelect";
import { Skeleton } from "@/components/ui/Skeleton";
import { BridgeSection } from "./BridgeSection";
import { MonthlyMrr, TopMovers } from "./DetailsSections";
import { LeakageSection } from "./LeakageSection";
import { TrendSection } from "./TrendSection";
import { WhySection } from "./WhySection";

export function MrrScreen() {
  const { state, update } = useMrrUrlState();
  const query = useMrrSummary(state.run);
  const summary = query.data;
  const options = useMemo(() => (summary ? mrrPeriodOptions(summary) : []), [summary]);
  const period = summary ? resolvePeriod(options, state.period) : null;
  const bridge = useMemo(() => (summary && period ? periodBridge(summary, period) : null), [summary, period]);

  const code = query.error instanceof ApiError ? query.error.code : null;
  const groups: SelectGroup[] = [
    { items: options.filter((option) => option.kind === "full").map((option) => ({ value: option.id, text: option.label, note: rangeLabel(option.months) })) },
    { label: "Years", items: options.filter((option) => option.kind === "year").map((option) => ({ value: option.id, text: option.label, note: option.partial ? `${option.months.length} months` : undefined })) },
    { label: "Quarters", items: options.filter((option) => option.kind === "quarter").map((option) => ({ value: option.id, text: option.label, note: option.partial ? `${option.months.length} months` : undefined })) },
    { label: "Months", items: options.filter((option) => option.kind === "month").map((option) => ({ value: option.id, text: option.label })) },
  ].filter((group) => group.items.length > 0);

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only z-50 rounded-md bg-bg px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2">
        Skip to content
      </a>
      <AppHeader
        section="mrr"
        aside={
          summary ? (
            <p className="flex min-h-10 items-center px-3 text-[0.9375rem] text-ink-2" data-testid="mrr-as-of">
              Data as of {formatMonth(summary.run.as_of_month)} · updated {formatDateUtc(summary.run.built_at)}
            </p>
          ) : (
            <Skeleton className="h-10 w-full rounded-lg sm:w-72" />
          )
        }
      />
      <main id="main" className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col px-5 py-10 md:px-8 md:py-14">
        <h1 className="sr-only">MRR</h1>
        {query.isError && !summary ? (
          <ErrorState
            title={code === "no_gold_run" ? "No MRR data yet" : code === "unknown_run" ? "No data for this run" : "Couldn't load the data"}
            message={
              code === "no_gold_run"
                ? "The MRR model hasn't been published yet. It appears here after its first successful run."
                : code === "unknown_run"
                  ? "This run doesn't exist. The latest run is still available."
                  : query.error instanceof Error
                    ? query.error.message
                    : "The request failed."
            }
            onRetry={code === "unknown_run" ? undefined : () => void query.refetch()}
            action={
              state.run && code !== "no_gold_run" ? (
                <button type="button" className="btn-secondary" onClick={() => update({ run: null })}>
                  Go to the latest run
                </button>
              ) : null
            }
          />
        ) : !summary || !period || !bridge ? (
          <div className="flex flex-col gap-14" aria-busy="true">
            <p className="sr-only" role="status">
              Loading the MRR data
            </p>
            <Skeleton className="h-16 w-72 rounded-lg" />
            <div className="grid gap-4 md:grid-cols-3" aria-hidden="true">
              {[0, 1, 2].map((index) => (
                <Skeleton key={index} className="h-36 rounded-xl" />
              ))}
            </div>
            <Skeleton className="h-96 rounded-xl" />
          </div>
        ) : (
          <div className={query.isPlaceholderData ? "flex flex-col gap-14 opacity-60 transition-opacity" : "flex flex-col gap-14"} aria-busy={query.isFetching}>
            <section aria-label="Filters" className="flex flex-wrap items-end gap-3">
              <PlainSelect
                label="Period"
                value={period.id}
                onValueChange={(id) => update({ period: id })}
                groups={groups}
                triggerText={`${period.label} · ${rangeLabel(period.months)}`}
                testId="mrr-period-select"
                className="w-full sm:w-80"
              />
            </section>
            <WhySection summary={summary} bridge={bridge} />
            <BridgeSection summary={summary} bridge={bridge} />
            <LeakageSection summary={summary} bridge={bridge} />
            <TrendSection summary={summary} period={period} />
            <div className="flex flex-col gap-4">
              <TopMovers
                key={period.id}
                summary={summary}
                from={period.months[0] ?? summary.run.as_of_month}
                to={period.months[period.months.length - 1] ?? summary.run.as_of_month}
                run={state.run}
              />
              <MonthlyMrr summary={summary} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
