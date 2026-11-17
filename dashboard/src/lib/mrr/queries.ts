"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getMrrMovements, getMrrSummary } from "@/lib/api/client";
import type { MovementsQuery } from "./types";

export function useMrrSummary(run: string | null) {
  const key = run ?? "latest";
  return useQuery({
    queryKey: ["mrr", "summary", key],
    queryFn: ({ signal }) => getMrrSummary(key, signal),
    staleTime: run ? Number.POSITIVE_INFINITY : 60_000,
    placeholderData: keepPreviousData,
  });
}

export function useMrrMovements(query: MovementsQuery, enabled: boolean) {
  return useQuery({
    queryKey: ["mrr", "movements", query.run, query.from, query.to, query.steps.join(","), query.page, query.pageSize],
    queryFn: ({ signal }) => getMrrMovements(query, signal),
    enabled,
    staleTime: Number.POSITIVE_INFINITY,
    placeholderData: keepPreviousData,
  });
}
