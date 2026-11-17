"use client";

import { useCallback, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { MAX_PAGE_SIZE } from "@/lib/api/types";

/**
 * Everything a deep link needs lives in the query string:
 *   ?run=<id>&rule=<rule_id>&dataset=<dataset_id>&q=<search>&page=<n>&size=<n>
 * Defaults are left out, so the plain overview is just `/`.
 */
export interface UrlState {
  /** `null` means the latest run. */
  run: string | null;
  rule: string | null;
  dataset: string | null;
  q: string;
  page: number;
  size: number;
}

export const PAGE_SIZES = [25, 50, 100, MAX_PAGE_SIZE] as const;
export const DEFAULT_PAGE_SIZE = 50;

export const EMPTY_URL_STATE: UrlState = {
  run: null,
  rule: null,
  dataset: null,
  q: "",
  page: 1,
  size: DEFAULT_PAGE_SIZE,
};

function positiveInt(raw: string | null, fallback: number): number {
  if (raw === null || !/^\d+$/.test(raw)) return fallback;
  const value = Number(raw);
  return Number.isSafeInteger(value) && value >= 1 ? value : fallback;
}

export function parseUrlState(params: URLSearchParams): UrlState {
  const run = params.get("run");
  const rule = params.get("rule");
  const dataset = params.get("dataset");
  // A cell needs both halves. One without the other opens nothing.
  const hasCell = Boolean(rule) && Boolean(dataset);
  const size = positiveInt(params.get("size"), DEFAULT_PAGE_SIZE);
  return {
    run: run && run !== "latest" ? run : null,
    rule: hasCell ? rule : null,
    dataset: hasCell ? dataset : null,
    q: hasCell ? (params.get("q") ?? "") : "",
    page: hasCell ? positiveInt(params.get("page"), 1) : 1,
    size: hasCell && (PAGE_SIZES as readonly number[]).includes(size) ? size : DEFAULT_PAGE_SIZE,
  };
}

/** Canonical query string (no leading `?`). `parseUrlState(serializeUrlState(s))` returns `s`. */
export function serializeUrlState(state: UrlState): string {
  const params = new URLSearchParams();
  if (state.run && state.run !== "latest") params.set("run", state.run);
  if (state.rule && state.dataset) {
    params.set("rule", state.rule);
    params.set("dataset", state.dataset);
    if (state.q) params.set("q", state.q);
    if (state.page > 1) params.set("page", String(state.page));
    if (state.size !== DEFAULT_PAGE_SIZE) params.set("size", String(state.size));
  }
  return params.toString();
}

export function hrefFor(state: UrlState, pathname = "/"): string {
  const query = serializeUrlState(state);
  return query ? `${pathname}?${query}` : pathname;
}

export type UrlUpdateMode = "push" | "replace";

/**
 * Reads the state from the URL and writes it back with the History API.
 * Next's router picks up `pushState` / `replaceState`, so `useSearchParams`
 * stays in sync and the back button walks through cells, pages and searches
 * without a network request (this is a static export: there is no server).
 */
export function useUrlState(): {
  state: UrlState;
  update: (patch: Partial<UrlState>, mode?: UrlUpdateMode) => void;
  hrefWith: (patch: Partial<UrlState>) => string;
} {
  const searchParams = useSearchParams();
  const query = searchParams.toString();
  const state = useMemo(() => parseUrlState(new URLSearchParams(query)), [query]);

  const update = useCallback((patch: Partial<UrlState>, mode: UrlUpdateMode = "push") => {
    const current = parseUrlState(new URLSearchParams(window.location.search));
    const href = hrefFor({ ...current, ...patch }, window.location.pathname);
    if (href === window.location.pathname + window.location.search) return;
    if (mode === "push") window.history.pushState(null, "", href);
    else window.history.replaceState(null, "", href);
  }, []);

  const hrefWith = useCallback((patch: Partial<UrlState>) => hrefFor({ ...state, ...patch }), [state]);

  return { state, update, hrefWith };
}
