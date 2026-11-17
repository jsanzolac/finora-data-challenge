/**
 * The mock API: a pure function from a request to a contract-shaped response.
 * It reproduces what the real API Lambda does on top of the serving store:
 * session and role checks, HR masking, `q` filtering and paging.
 */
import type { DqRecord, RecordsPage, Role, User } from "../src/lib/api/types";
import { DATASETS, RUNS, datasetDef, isStageAFailure, recordsFor, resolveRunId, summaryFor } from "./fixtures";
import type { AcqSummary } from "../src/lib/acq/types";
import { SEED_RATE_ROWS, acqSummaryFor, saveScenario, scenariosFrom, type RateRow } from "./acq/fixtures";
import { mrrMovementsFor, mrrSummaryFor } from "./mrr/fixtures";
import { MOCK_AGENT_TOKEN, MOCK_RESULTS, MOCK_SDK_SIGNED_URL, MOCK_SIGNED_URL } from "./voice";

export interface MockRequest {
  method: string;
  path: string;
  query: URLSearchParams;
  body?: unknown;
}

export interface MockResponse {
  status: number;
  body: unknown;
}

export interface MockSession {
  email: string;
  role: Role;
  must_change_password: boolean;
  password: string;
}

/** Where the mock keeps its "cookie". The real one is HttpOnly and invisible to the page. */
export interface SessionStore {
  get(): MockSession | null;
  set(session: MockSession | null): void;
}

/** Where the mock keeps the append-only rate table (finora_gold.funnel_conversion_rate). */
export interface RateStore {
  get(): RateRow[];
  set(rows: RateRow[]): void;
}

export function memoryRateStore(initial: RateRow[] = SEED_RATE_ROWS): RateStore {
  let rows = [...initial];
  return {
    get: () => rows,
    set: (next) => {
      rows = [...next];
    },
  };
}

const defaultRateStore = memoryRateStore();

/** Mock-only switches, for states today's data never reaches. */
export interface MockFlags {
  /** Answer GET /api/acq/summary?run=latest with 404 `no_gold_run`, as before the first gold publish. */
  noGoldRun?: boolean;
  /** The same for GET /api/mrr/summary. */
  noMrrRun?: boolean;
  /** Answer POST /api/agent-session with 503 `voice_unavailable`. */
  voiceUnavailable?: boolean;
  /** Answer a wss://api.elevenlabs.io signed URL, so the real SDK path runs. */
  voiceSdk?: boolean;
}

function handleAgent(request: MockRequest, session: MockSession, flags: MockFlags): MockResponse {
  if (request.method === "POST" && request.path === "/api/agent-session") {
    if (flags.voiceUnavailable) return error(503, "voice_unavailable", "La voz no está disponible ahora.");
    return {
      status: 200,
      body: {
        signed_url: flags.voiceSdk ? MOCK_SDK_SIGNED_URL : MOCK_SIGNED_URL,
        agent_id: "mock-agent",
        agent_token: MOCK_AGENT_TOKEN,
        expires_at: new Date(Date.now() + 45 * 60 * 1000).toISOString().replace(/\.\d{3}Z$/, "Z"),
        dynamic_variables: { user_role: session.role, as_of_month: "2024-10" },
      },
    };
  }
  const match = /^\/api\/agent\/results\/([^/]+)$/.exec(request.path);
  if (request.method === "GET" && match) {
    const found = MOCK_RESULTS[decodeURIComponent(match[1] ?? "")];
    return found ? { status: 200, body: found } : error(404, "result_not_found", "Unknown result.");
  }
  return error(404, "not_found", "Unknown route.");
}

function handleMrr(request: MockRequest, flags: MockFlags): MockResponse {
  if (request.method !== "GET") return error(404, "not_found", "Unknown route.");
  if (request.path === "/api/mrr/summary") {
    const run = request.query.get("run");
    if ((!run || run === "latest") && flags.noMrrRun) return error(404, "no_gold_run", "No MRR run has been published yet.");
    const summary = mrrSummaryFor(run);
    return summary ? { status: 200, body: summary } : error(404, "unknown_run", "Unknown run.");
  }
  if (request.path === "/api/mrr/movements") return mrrMovementsFor(request.query);
  return error(404, "not_found", "Unknown route.");
}

/** Mock sign-ins. They exist only in mock builds. */
export const MOCK_PASSWORD = "finora-demo-2026";

export const MOCK_USERS: { email: string; role: Role; must_change_password: boolean }[] = [
  { email: "data@finora.test", role: "data", must_change_password: false },
  { email: "finance@finora.test", role: "finance", must_change_password: false },
  { email: "revops@finora.test", role: "revops", must_change_password: false },
  { email: "new.analyst@finora.test", role: "data", must_change_password: true },
];

const RATE_LIMITED_EMAIL = "locked@finora.test";
const RESTRICTED = "__restricted__";
const DEFAULT_PAGE_SIZE = 50;
const MAX_PAGE_SIZE = 200;

function error(status: number, code: string, message: string): MockResponse {
  return { status, body: { error: { code, message } } };
}

function publicUser(session: MockSession): User {
  return { email: session.email, role: session.role, must_change_password: session.must_change_password };
}

function field(body: unknown, name: string): string {
  if (typeof body !== "object" || body === null) return "";
  const value = (body as Record<string, unknown>)[name];
  return typeof value === "string" ? value : "";
}

function toInt(raw: string | null, fallback: number): number {
  const value = raw === null ? Number.NaN : Number.parseInt(raw, 10);
  return Number.isFinite(value) && value >= 1 ? value : fallback;
}

/**
 * Finance sees everything. Everyone else gets "__restricted__" for the
 * HR-sensitive columns, and for every value of a record that failed a
 * stage-A rule (its column positions cannot be trusted).
 */
export function maskRecord(record: DqRecord, restrictedColumns: string[], role: Role): DqRecord {
  if (role === "finance" || restrictedColumns.length === 0) return record;
  const all = isStageAFailure(record);
  const mask = (source: Record<string, string>) => {
    const out: Record<string, string> = {};
    for (const [column, value] of Object.entries(source)) {
      out[column] = all || restrictedColumns.includes(column) ? RESTRICTED : value;
    }
    return out;
  };
  return { ...record, key: mask(record.key), values: mask(record.values) };
}

/** Case-insensitive substring match over the key, the values and the reason. */
export function matchesQuery(record: DqRecord, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  const haystack = [...Object.values(record.key), ...Object.values(record.values), record.reason];
  return haystack.some((text) => text !== RESTRICTED && text.toLowerCase().includes(needle));
}

function handleAuth(request: MockRequest, store: SessionStore): MockResponse {
  const session = store.get();
  const route = `${request.method} ${request.path}`;

  if (route === "POST /api/auth/login") {
    const email = field(request.body, "email").trim().toLowerCase();
    const password = field(request.body, "password");
    if (email === RATE_LIMITED_EMAIL) {
      return error(429, "rate_limited", "Too many attempts. Wait a few minutes and try again.");
    }
    const user = MOCK_USERS.find((candidate) => candidate.email === email);
    const previous = session && session.email === email ? session : null;
    const expected = previous?.password ?? MOCK_PASSWORD;
    if (!user || password !== expected) {
      return error(401, "invalid_credentials", "Email or password is incorrect.");
    }
    const next: MockSession = { ...user, ...(previous ?? {}), password: expected };
    store.set(next);
    return { status: 200, body: { user: publicUser(next) } };
  }

  if (route === "POST /api/auth/logout") {
    store.set(null);
    return { status: 200, body: { ok: true } };
  }

  if (route === "GET /api/auth/session") {
    if (!session) return error(401, "unauthorized", "No session.");
    return { status: 200, body: { user: publicUser(session) } };
  }

  if (route === "POST /api/auth/password") {
    if (!session) return error(401, "unauthorized", "No session.");
    const current = field(request.body, "current");
    const next = field(request.body, "new");
    if (current !== session.password) return error(400, "wrong_password", "The current password is incorrect.");
    if (next.length < 12) return error(400, "weak_password", "The new password needs at least 12 characters.");
    if (next === current) return error(400, "same_password", "The new password must be different from the current one.");
    const updated: MockSession = { ...session, password: next, must_change_password: false };
    store.set(updated);
    return { status: 200, body: { user: publicUser(updated) } };
  }

  return error(404, "not_found", "Unknown route.");
}

function handleDq(request: MockRequest, session: MockSession): MockResponse {
  if (request.method !== "GET") return error(404, "not_found", "Unknown route.");

  if (request.path === "/api/dq/runs") return { status: 200, body: RUNS };

  if (request.path === "/api/dq/summary") {
    const runId = resolveRunId(request.query.get("run"));
    const summary = runId ? summaryFor(runId) : null;
    if (!summary) return error(404, "run_not_found", "Unknown run, or the run has no summary.");
    return { status: 200, body: summary };
  }

  const match = /^\/api\/dq\/rules\/([^/]+)\/datasets\/([^/]+)\/records$/.exec(request.path);
  if (match) {
    const ruleId = decodeURIComponent(match[1] ?? "");
    const datasetId = decodeURIComponent(match[2] ?? "");
    const runId = resolveRunId(request.query.get("run"));
    const dataset = datasetDef(datasetId);
    const all = runId ? recordsFor(runId, ruleId, datasetId) : null;
    if (!runId || !dataset || !all) return error(404, "not_found", "Unknown run, rule or dataset.");

    const page = toInt(request.query.get("page"), 1);
    const pageSize = Math.min(MAX_PAGE_SIZE, toInt(request.query.get("page_size"), DEFAULT_PAGE_SIZE));
    const q = request.query.get("q") ?? "";
    const visible = all
      .map((record) => maskRecord(record, dataset.restrictedColumns, session.role))
      .filter((record) => matchesQuery(record, q));
    const start = (page - 1) * pageSize;
    const body: RecordsPage = {
      rule_id: ruleId,
      dataset_id: datasetId,
      run_id: runId,
      total: visible.length,
      page,
      page_size: pageSize,
      columns: dataset.columns,
      records: visible.slice(start, start + pageSize),
    };
    return { status: 200, body };
  }

  return error(404, "not_found", "Unknown route.");
}

/** Finance sees every spend category; everyone else gets "__restricted__" for the HR ones. */
export function maskAcqSummary(summary: AcqSummary, role: Role): AcqSummary {
  if (role === "finance") return summary;
  const hr = summary.spend_categories.filter((category) => category.hr_sensitive).map((category) => category.code);
  return {
    ...summary,
    months: summary.months.map((month) => ({
      ...month,
      spend_value: Object.fromEntries(
        Object.entries(month.spend_value).map(([code, value]) => [code, hr.includes(code) ? RESTRICTED : value]),
      ),
    })),
  };
}

function handleAcq(request: MockRequest, session: MockSession, rates: RateStore, flags: MockFlags): MockResponse {
  const route = `${request.method} ${request.path}`;
  if (route === "GET /api/acq/summary") {
    const run = request.query.get("run");
    const latest = !run || run === "latest";
    if (latest && flags.noGoldRun) return error(404, "no_gold_run", "No acquisition run has been published yet.");
    const summary = acqSummaryFor(run);
    if (!summary) return error(404, "unknown_run", "Unknown run.");
    return { status: 200, body: maskAcqSummary(summary, session.role) };
  }
  if (route === "GET /api/acq/scenarios") {
    return { status: 200, body: { can_edit: session.role !== "data", scenarios: scenariosFrom(rates.get()) } };
  }
  if (route === "POST /api/acq/scenarios") {
    if (session.role === "data") return error(403, "role_not_allowed", "Your role can't change conversion rates.");
    const result = saveScenario(rates.get(), request.body, session.email, new Date().toISOString().replace(/\.\d{3}Z$/, "Z"));
    if (result.rows) rates.set(result.rows);
    return { status: result.status, body: result.body };
  }
  return error(404, "not_found", "Unknown route.");
}

export function handleMockRequest(
  request: MockRequest,
  store: SessionStore,
  rates: RateStore = defaultRateStore,
  flags: MockFlags = {},
): MockResponse {
  if (request.path.startsWith("/api/auth/")) return handleAuth(request, store);

  if (request.path === "/api/agent-session" || request.path.startsWith("/api/agent/")) {
    const session = store.get();
    if (!session) return error(401, "unauthorized", "No session.");
    if (session.must_change_password) {
      return error(403, "password_change_required", "Change your password to continue.");
    }
    return handleAgent(request, session, flags);
  }

  if (request.path.startsWith("/api/mrr/")) {
    const session = store.get();
    if (!session) return error(401, "unauthorized", "No session.");
    if (session.must_change_password) {
      return error(403, "password_change_required", "Change your password to continue.");
    }
    return handleMrr(request, flags);
  }

  if (request.path.startsWith("/api/acq/")) {
    const session = store.get();
    if (!session) return error(401, "unauthorized", "No session.");
    if (session.must_change_password) {
      return error(403, "password_change_required", "Change your password to continue.");
    }
    return handleAcq(request, session, rates, flags);
  }

  if (request.path.startsWith("/api/dq/")) {
    const session = store.get();
    if (!session) return error(401, "unauthorized", "No session.");
    if (session.must_change_password) {
      return error(403, "password_change_required", "Change your password to continue.");
    }
    return handleDq(request, session);
  }

  return error(404, "not_found", "Unknown route.");
}

export const MOCK_DATASET_IDS = DATASETS.map((dataset) => dataset.id);
