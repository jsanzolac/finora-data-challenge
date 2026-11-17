/**
 * Mock mode: a fetch adapter that answers `/api/*` from the fixtures.
 * Loaded only when NEXT_PUBLIC_DQ_MOCKS=1 (see src/components/providers/Providers.tsx).
 * It must never be part of the deployed build: scripts/check-no-mocks.mjs enforces that.
 */
import { MOCK_MARKER } from "./fixtures";
import { ACQ_MOCK_MARKER, SEED_RATE_ROWS, type RateRow } from "./acq/fixtures";
import { MRR_MOCK_MARKER } from "./mrr/fixtures";
import { VOICE_SDK_KEY, VOICE_UNAVAILABLE_KEY, installMockVoice } from "./voice";
import { handleMockRequest, type MockFlags, type MockSession, type RateStore, type SessionStore } from "./handler";

const STORAGE_KEY = "dq_mock_session";
const RATES_KEY = "acq_mock_rate_rows";
/** Set to "1" in sessionStorage to answer the latest acquisition summary with 404 `no_gold_run`. */
const NO_GOLD_RUN_KEY = "acq_mock_no_gold_run";
/** Set to "1" to answer the latest MRR summary with 404 `no_gold_run`. */
const NO_MRR_RUN_KEY = "mrr_mock_no_gold_run";

function mockFlags(): MockFlags {
  try {
    return {
      noGoldRun: window.sessionStorage.getItem(NO_GOLD_RUN_KEY) === "1",
      noMrrRun: window.sessionStorage.getItem(NO_MRR_RUN_KEY) === "1",
      voiceUnavailable: window.sessionStorage.getItem(VOICE_UNAVAILABLE_KEY) === "1",
      voiceSdk: window.sessionStorage.getItem(VOICE_SDK_KEY) === "1",
    };
  } catch {
    return {};
  }
}
const LATENCY_MS = 120;

/** The scenarios endpoint reads Athena live (2-5 s); the mock is slower there so the loading state shows. */
function latencyFor(method: string, path: string): number {
  if (path === "/api/acq/scenarios") return method === "POST" ? 900 : 1500;
  return LATENCY_MS;
}

/** sessionStorage keeps saved scenarios for the tab, like the session. */
const rateStore: RateStore = {
  get() {
    try {
      const raw = window.sessionStorage.getItem(RATES_KEY);
      return raw ? (JSON.parse(raw) as RateRow[]) : SEED_RATE_ROWS;
    } catch {
      return SEED_RATE_ROWS;
    }
  },
  set(rows) {
    try {
      window.sessionStorage.setItem(RATES_KEY, JSON.stringify(rows));
    } catch {
      /* private mode: saved scenarios last until the next request */
    }
  },
};

/** sessionStorage stands in for the HttpOnly cookie, so a reload keeps the mock session. */
const sessionStore: SessionStore = {
  get() {
    try {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as MockSession) : null;
    } catch {
      return null;
    }
  },
  set(session) {
    try {
      if (session) window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
      else window.sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* private mode: the mock session just does not persist */
    }
  },
};

type MockWindow = Window & { [MOCK_MARKER]?: boolean; [ACQ_MOCK_MARKER]?: boolean; [MRR_MOCK_MARKER]?: boolean };

export function installMockApi(): void {
  if (typeof window === "undefined") return;
  const target = window as MockWindow;
  if (target[MOCK_MARKER]) return;
  const realFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const href = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(href, window.location.origin);
    if (url.origin !== window.location.origin || !url.pathname.startsWith("/api/")) {
      return realFetch(input, init);
    }

    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    let body: unknown;
    if (typeof init?.body === "string") {
      try {
        body = JSON.parse(init.body);
      } catch {
        body = undefined;
      }
    }

    await new Promise((resolve) => setTimeout(resolve, latencyFor(method, url.pathname)));
    if (init?.signal?.aborted) throw new DOMException("The request was aborted.", "AbortError");

    const result = handleMockRequest({ method, path: url.pathname, query: url.searchParams, body }, sessionStore, rateStore, mockFlags());
    return new Response(JSON.stringify(result.body), {
      status: result.status,
      headers: { "Content-Type": "application/json" },
    });
  };

  target[MOCK_MARKER] = true;
  target[ACQ_MOCK_MARKER] = true;
  target[MRR_MOCK_MARKER] = true;
  installMockVoice();
  console.info("[dq] Mock mode is on: /api/* is answered from dashboard/mocks/.");
}
