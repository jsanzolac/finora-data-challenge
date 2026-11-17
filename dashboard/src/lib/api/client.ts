/**
 * The one API client. Same origin, session in an HttpOnly cookie the frontend
 * never reads: every call is `fetch("/api/...", { credentials: "same-origin" })`.
 *
 * Two responses are handled centrally, whoever made the call:
 *   401                               -> the session is gone: go to /login
 *   403 `password_change_required`    -> go to the password-change screen
 * The auth provider registers the handlers; this module holds no React state.
 */
import type { ApiErrorBody, RecordsPage, RecordsQuery, Run, SessionResponse, Summary } from "./types";
import { MAX_PAGE_SIZE } from "./types";
import type { AcqSummary, ApiErrorDetail, SaveScenarioRequest, Scenario, ScenariosResponse } from "@/lib/acq/types";
import type { MovementsQuery, MrrMovementsPage, MrrSummary } from "@/lib/mrr/types";
import type { AgentResult, AgentSession } from "@/lib/voice/types";

export const PASSWORD_CHANGE_REQUIRED = "password_change_required";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  /** Per-check validation details (acquisition POST 400 `invalid_scenario`). Empty otherwise. */
  readonly details: ApiErrorDetail[];

  constructor(status: number, code: string, message: string, details: ApiErrorDetail[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export interface AuthHandlers {
  onUnauthorized?: () => void;
  onPasswordChangeRequired?: () => void;
}

let handlers: AuthHandlers = {};

export function setAuthHandlers(next: AuthHandlers): void {
  handlers = next;
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
  /**
   * A 401 on login means "wrong credentials" and a 401 on the first session
   * check means "not signed in yet". Neither is an expired session.
   */
  skipAuthHandlers?: boolean;
}

function defaultMessage(status: number): string {
  if (status === 401) return "Your session has ended. Sign in again.";
  if (status === 403) return "You don't have access to this.";
  if (status === 404) return "Not found.";
  if (status === 429) return "Too many attempts. Wait a few minutes and try again.";
  if (status >= 500) return "The server had a problem. Try again.";
  return "The request failed.";
}

/** `error.details: [{ check, field, message }]` (acquisition contract v1.1, POST 400 `invalid_scenario`). */
function errorDetails(payload: unknown): ApiErrorDetail[] {
  if (typeof payload !== "object" || payload === null) return [];
  const raw = (payload as { error?: { details?: unknown } }).error?.details;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item): item is { check?: unknown; field?: unknown; message?: unknown } => typeof item === "object" && item !== null)
    .map((item) => ({
      check: typeof item.check === "string" ? item.check : "",
      field: typeof item.field === "string" ? item.field : "",
      message: typeof item.message === "string" ? item.message : "",
    }));
}

function isErrorBody(payload: unknown): payload is ApiErrorBody {
  if (typeof payload !== "object" || payload === null) return false;
  const error = (payload as { error?: unknown }).error;
  return typeof error === "object" && error !== null && typeof (error as { code?: unknown }).code === "string";
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, skipAuthHandlers = false } = options;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      credentials: "same-origin",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "network_error", "Can't reach the server. Check your connection and try again.");
  }

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const code = isErrorBody(payload) ? payload.error.code : `http_${response.status}`;
    const message =
      isErrorBody(payload) && payload.error.message ? payload.error.message : defaultMessage(response.status);
    const error = new ApiError(response.status, code, message, errorDetails(payload));
    if (!skipAuthHandlers) {
      if (response.status === 401) handlers.onUnauthorized?.();
      else if (response.status === 403 && code === PASSWORD_CHANGE_REQUIRED) handlers.onPasswordChangeRequired?.();
    }
    throw error;
  }

  if (payload === null) {
    throw new ApiError(response.status, "bad_response", "The server sent a response the dashboard can't read.");
  }
  return payload as T;
}

/* ---------------------------------------------------------------- auth */

export function login(email: string, password: string): Promise<SessionResponse> {
  return request<SessionResponse>("/api/auth/login", {
    method: "POST",
    body: { email, password },
    skipAuthHandlers: true,
  });
}

export function logout(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/auth/logout", { method: "POST", skipAuthHandlers: true });
}

export function getSession(): Promise<SessionResponse> {
  return request<SessionResponse>("/api/auth/session", { skipAuthHandlers: true });
}

export function changePassword(current: string, next: string): Promise<SessionResponse> {
  return request<SessionResponse>("/api/auth/password", {
    method: "POST",
    body: { current, new: next },
    skipAuthHandlers: true,
  });
}

/* ------------------------------------------------------------------ dq */

export function getRuns(signal?: AbortSignal): Promise<Run[]> {
  return request<Run[]>("/api/dq/runs", { signal });
}

export function getSummary(run: string, signal?: AbortSignal): Promise<Summary> {
  return request<Summary>(`/api/dq/summary?run=${encodeURIComponent(run)}`, { signal });
}

export function recordsPath(query: RecordsQuery): string {
  const params = new URLSearchParams({
    run: query.run,
    page: String(Math.max(1, Math.floor(query.page))),
    page_size: String(Math.min(MAX_PAGE_SIZE, Math.max(1, Math.floor(query.pageSize)))),
  });
  if (query.q) params.set("q", query.q);
  return `/api/dq/rules/${encodeURIComponent(query.ruleId)}/datasets/${encodeURIComponent(query.datasetId)}/records?${params.toString()}`;
}

export function getRecords(query: RecordsQuery, signal?: AbortSignal): Promise<RecordsPage> {
  return request<RecordsPage>(recordsPath(query), { signal });
}

/* ----------------------------------------------------------------- acq */

export function getAcqSummary(run: string, signal?: AbortSignal): Promise<AcqSummary> {
  return request<AcqSummary>(`/api/acq/summary?run=${encodeURIComponent(run)}`, { signal });
}

export function getAcqScenarios(signal?: AbortSignal): Promise<ScenariosResponse> {
  return request<ScenariosResponse>("/api/acq/scenarios", { signal });
}

export function saveAcqScenario(body: SaveScenarioRequest): Promise<Scenario> {
  return request<Scenario>("/api/acq/scenarios", { method: "POST", body });
}

/* ----------------------------------------------------------------- mrr */

export function getMrrSummary(run: string, signal?: AbortSignal): Promise<MrrSummary> {
  return request<MrrSummary>(`/api/mrr/summary?run=${encodeURIComponent(run)}`, { signal });
}

export function mrrMovementsPath(query: MovementsQuery): string {
  const params = new URLSearchParams({
    from: query.from,
    to: query.to,
    run: query.run,
    sort: "abs_desc",
    page: String(Math.max(1, Math.floor(query.page))),
    page_size: String(Math.min(MAX_PAGE_SIZE, Math.max(1, Math.floor(query.pageSize)))),
  });
  for (const step of query.steps) params.append("step", step);
  return `/api/mrr/movements?${params.toString()}`;
}

export function getMrrMovements(query: MovementsQuery, signal?: AbortSignal): Promise<MrrMovementsPage> {
  return request<MrrMovementsPage>(mrrMovementsPath(query), { signal });
}

/* --------------------------------------------------------------- agent */

/** The signed URL and the short-lived agent token for one voice session. Never cached. */
export function postAgentSession(): Promise<AgentSession> {
  return request<AgentSession>("/api/agent-session", { method: "POST" });
}

export function getAgentResult(resultId: string, signal?: AbortSignal): Promise<AgentResult> {
  return request<AgentResult>(`/api/agent/results/${encodeURIComponent(resultId)}`, { signal });
}
