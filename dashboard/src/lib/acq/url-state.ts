"use client";

import { useCallback, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { BASE_SCENARIO_ID, type WonDefinition } from "./types";
import { FULL_PERIOD } from "./periods";

/**
 * Deep links for the acquisition page:
 *   /acquisition/?period=<id>&scenario=<id>&def=new_logo&run=<run_id>
 * Defaults are left out (full period, base scenario, the user's Won definition,
 * the latest gold run), so the plain page is just /acquisition/.
 * Unknown values are resolved against the API data by the screen, not here.
 */
export interface AcqUrlState {
  period: string;
  scenario: string;
  def: WonDefinition;
  /** `null` means the latest gold run. */
  run: string | null;
}

export const DEFAULT_ACQ_STATE: AcqUrlState = { period: FULL_PERIOD, scenario: BASE_SCENARIO_ID, def: "user", run: null };

const TOKEN = /^[A-Za-z0-9_-]{1,64}$/;

function token(raw: string | null, fallback: string): string {
  return raw && TOKEN.test(raw) ? raw : fallback;
}

export function parseAcqUrlState(params: URLSearchParams): AcqUrlState {
  const run = params.get("run");
  return {
    period: token(params.get("period"), FULL_PERIOD),
    scenario: token(params.get("scenario"), BASE_SCENARIO_ID),
    def: params.get("def") === "new_logo" ? "new_logo" : "user",
    run: run && run !== "latest" && TOKEN.test(run) ? run : null,
  };
}

/** Canonical query string (no leading `?`). */
export function serializeAcqUrlState(state: AcqUrlState): string {
  const params = new URLSearchParams();
  if (state.period !== FULL_PERIOD) params.set("period", state.period);
  if (state.scenario !== BASE_SCENARIO_ID) params.set("scenario", state.scenario);
  if (state.def !== "user") params.set("def", state.def);
  if (state.run) params.set("run", state.run);
  return params.toString();
}

export function useAcqUrlState(): {
  state: AcqUrlState;
  update: (patch: Partial<AcqUrlState>, mode?: "push" | "replace") => void;
} {
  const searchParams = useSearchParams();
  const query = searchParams.toString();
  const state = useMemo(() => parseAcqUrlState(new URLSearchParams(query)), [query]);

  const update = useCallback((patch: Partial<AcqUrlState>, mode: "push" | "replace" = "push") => {
    const current = parseAcqUrlState(new URLSearchParams(window.location.search));
    const next = serializeAcqUrlState({ ...current, ...patch });
    const href = next ? `${window.location.pathname}?${next}` : window.location.pathname;
    if (href === window.location.pathname + window.location.search) return;
    if (mode === "push") window.history.pushState(null, "", href);
    else window.history.replaceState(null, "", href);
  }, []);

  return { state, update };
}
