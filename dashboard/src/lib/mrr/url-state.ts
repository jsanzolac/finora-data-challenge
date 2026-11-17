"use client";

import { useCallback, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { LAST_12 } from "./bridge";

/** /mrr/?period=<id>&run=<run_id>. Defaults (last 12 months, latest run) are left out. */
export interface MrrUrlState {
  period: string;
  run: string | null;
}

const TOKEN = /^[A-Za-z0-9_-]{1,64}$/;

export function parseMrrUrlState(params: URLSearchParams): MrrUrlState {
  const period = params.get("period");
  const run = params.get("run");
  return {
    period: period && TOKEN.test(period) ? period : LAST_12,
    run: run && run !== "latest" && TOKEN.test(run) ? run : null,
  };
}

export function serializeMrrUrlState(state: MrrUrlState): string {
  const params = new URLSearchParams();
  if (state.period !== LAST_12) params.set("period", state.period);
  if (state.run) params.set("run", state.run);
  return params.toString();
}

export function useMrrUrlState(): { state: MrrUrlState; update: (patch: Partial<MrrUrlState>) => void } {
  const searchParams = useSearchParams();
  const query = searchParams.toString();
  const state = useMemo(() => parseMrrUrlState(new URLSearchParams(query)), [query]);
  const update = useCallback((patch: Partial<MrrUrlState>) => {
    const current = parseMrrUrlState(new URLSearchParams(window.location.search));
    const next = serializeMrrUrlState({ ...current, ...patch });
    const href = next ? `${window.location.pathname}?${next}` : window.location.pathname;
    if (href !== window.location.pathname + window.location.search) window.history.pushState(null, "", href);
  }, []);
  return { state, update };
}
