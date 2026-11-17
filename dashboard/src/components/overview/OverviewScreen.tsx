"use client";

import { useCallback, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { useRuns, useSummary } from "@/lib/api/queries";
import { rankDatasets } from "@/lib/ranking";
import { useUrlState } from "@/lib/url-state";
import { AppHeader, RunAside } from "@/components/layout/AppHeader";
import { RulesTable, RulesTableSkeleton, focusRuleCell } from "@/components/rules/RulesTable";
import { RecordsSheet } from "@/components/records/RecordsSheet";
import { ErrorState } from "@/components/ui/ErrorState";
import { Departments, DepartmentsSkeleton } from "./Departments";

export function OverviewScreen() {
  const { state, update, hrefWith } = useUrlState();
  const runs = useRuns();
  const summary = useSummary(state.run);
  const data = summary.data;
  const ranked = data ? rankDatasets(data.datasets) : [];
  const sheetOpen = Boolean(state.rule && state.dataset && data);
  // The sheet stays mounted after it closes, so Radix can hand focus back to the cell.
  const [lastCell, setLastCell] = useState<{ ruleId: string; datasetId: string } | null>(null);
  if (state.rule && state.dataset && (lastCell?.ruleId !== state.rule || lastCell.datasetId !== state.dataset)) {
    setLastCell({ ruleId: state.rule, datasetId: state.dataset });
  }
  const rule = data?.rules.find((entry) => entry.rule_id === lastCell?.ruleId);

  const selectRun = useCallback(
    (runId: string | null) => update({ run: runId, rule: null, dataset: null, q: "", page: 1 }, "push"),
    [update],
  );
  const openCell = useCallback(
    (ruleId: string, datasetId: string) => update({ rule: ruleId, dataset: datasetId, q: "", page: 1 }, "push"),
    [update],
  );
  const closeSheet = useCallback(() => update({ rule: null, dataset: null, q: "", page: 1 }, "push"), [update]);

  const notFound = summary.error instanceof ApiError && summary.error.status === 404;

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only z-50 rounded-md bg-bg px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2">
        Skip to content
      </a>
      <AppHeader section="dq" aside={<RunAside runs={runs.data} selectedRunId={data?.run.run_id} onSelectRun={selectRun} />} />

      <main id="main" className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col px-5 py-10 md:px-8 md:py-14">
        <h1 className="sr-only">Data quality</h1>
        {summary.isError && !data ? (
          <ErrorState
            title={notFound ? "No data for this run" : "Couldn't load the data"}
            message={
              notFound
                ? "This run failed or doesn't exist. The latest run is still available."
                : summary.error instanceof Error
                  ? summary.error.message
                  : "The request failed."
            }
            onRetry={notFound ? undefined : () => void summary.refetch()}
            action={
              state.run ? (
                <button type="button" className="btn-secondary" onClick={() => selectRun(null)}>
                  Go to the latest run
                </button>
              ) : null
            }
          />
        ) : (
          <div
            className={summary.isPlaceholderData ? "flex flex-col gap-14 opacity-60 transition-opacity" : "flex flex-col gap-14"}
            aria-busy={summary.isFetching}
          >
            <section aria-labelledby="departments-title" className="flex flex-col gap-5">
              <h2 id="departments-title" className="text-xl font-semibold">
                Departments
              </h2>
              {data ? (
                <Departments datasets={ranked} rules={data.rules} trend={data.trend} runId={data.run.run_id} />
              ) : (
                <DepartmentsSkeleton />
              )}
            </section>

            <section aria-labelledby="rules-title">
              {data ? (
                <RulesTable
                  rules={data.rules}
                  datasets={ranked}
                  selected={state.rule && state.dataset ? { ruleId: state.rule, datasetId: state.dataset } : null}
                  onOpen={openCell}
                />
              ) : (
                <div className="flex flex-col gap-5">
                  <h2 id="rules-title" className="text-xl font-semibold">
                    Rules
                  </h2>
                  <RulesTableSkeleton />
                </div>
              )}
            </section>
          </div>
        )}
      </main>

      {data && lastCell ? (
        <RecordsSheet
          open={sheetOpen}
          rule={rule}
          allRules={data.rules}
          ruleId={lastCell.ruleId}
          datasetId={lastCell.datasetId}
          datasets={ranked}
          runId={data.run.run_id}
          runs={runs.data}
          url={state}
          update={update}
          hrefWith={hrefWith}
          onClose={closeSheet}
          onCloseFocus={(ruleId, datasetId) => {
            if (!focusRuleCell(ruleId, datasetId)) document.getElementById("rules-title")?.focus();
          }}
        />
      ) : null}
    </div>
  );
}
