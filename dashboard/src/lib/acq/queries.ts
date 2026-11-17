"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getAcqScenarios, getAcqSummary, saveAcqScenario } from "@/lib/api/client";
import { BASE_SCENARIO_ID, type SaveScenarioRequest, type Scenario, type ScenariosResponse } from "./types";

const LATEST = "latest";
const SCENARIOS_KEY = ["acq", "scenarios"] as const;

/** `run === null` asks for the latest gold run. A named run never changes. */
export function useAcqSummary(run: string | null) {
  const key = run ?? LATEST;
  return useQuery({
    queryKey: ["acq", "summary", key],
    queryFn: ({ signal }) => getAcqSummary(key, signal),
    staleTime: run ? Number.POSITIVE_INFINITY : 60_000,
    placeholderData: keepPreviousData,
  });
}

/** Read live from Athena by the API: about 2-5 s. */
export function useAcqScenarios() {
  return useQuery({
    queryKey: SCENARIOS_KEY,
    queryFn: ({ signal }) => getAcqScenarios(signal),
    staleTime: 30_000,
  });
}

/** Base first, then the rest in the order the API listed them, with the saved one replaced or appended. */
export function mergeScenario(current: ScenariosResponse, saved: Scenario): ScenariosResponse {
  const exists = current.scenarios.some((scenario) => scenario.scenario_id === saved.scenario_id);
  const scenarios = exists
    ? current.scenarios.map((scenario) => (scenario.scenario_id === saved.scenario_id ? saved : scenario))
    : [...current.scenarios, saved];
  scenarios.sort((a, b) => Number(b.scenario_id === BASE_SCENARIO_ID) - Number(a.scenario_id === BASE_SCENARIO_ID));
  return { ...current, scenarios };
}

export function useSaveScenario() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SaveScenarioRequest) => saveAcqScenario(body),
    onSuccess: (saved) => {
      // The 201 body is the scenario as GET lists it, read back after the insert: show it now
      // instead of waiting another Athena round trip, then refresh quietly.
      queryClient.setQueryData<ScenariosResponse>(SCENARIOS_KEY, (current) => (current ? mergeScenario(current, saved) : current));
      void queryClient.invalidateQueries({ queryKey: SCENARIOS_KEY, refetchType: "none" });
    },
  });
}
