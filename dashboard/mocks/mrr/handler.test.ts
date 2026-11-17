/** The MRR mock API: sessions, 404 codes, movement filters, paging and invalid_query. */
import { describe, expect, it } from "vitest";
import type { MrrMovementsPage } from "../../src/lib/mrr/types";
import { MOCK_PASSWORD, handleMockRequest, memoryRateStore, type MockSession, type SessionStore } from "../handler";

const store: SessionStore = {
  get: (): MockSession => ({ email: "data@finora.test", role: "data", must_change_password: false, password: MOCK_PASSWORD }),
  set: () => undefined,
};

function get(path: string, flags = {}) {
  const [pathname, query = ""] = path.split("?");
  return handleMockRequest({ method: "GET", path: pathname!, query: new URLSearchParams(query) }, store, memoryRateStore(), flags);
}

describe("GET /api/mrr/*", () => {
  it("serves the summary, and 404 no_gold_run / unknown_run", () => {
    expect(get("/api/mrr/summary?run=latest").status).toBe(200);
    expect((get("/api/mrr/summary?run=r1").body as { error: { code: string } }).error.code).toBe("unknown_run");
    expect((get("/api/mrr/summary?run=latest", { noMrrRun: true }).body as { error: { code: string } }).error.code).toBe("no_gold_run");
    const none: SessionStore = { get: () => null, set: () => undefined };
    expect(handleMockRequest({ method: "GET", path: "/api/mrr/summary", query: new URLSearchParams() }, none).status).toBe(401);
  });

  it("filters, sorts by |change| and pages the movements", () => {
    const page = get("/api/mrr/movements?from=2024-10&to=2024-10&run=latest&sort=abs_desc&page=1&page_size=20").body as MrrMovementsPage;
    expect(page.movements).toHaveLength(20);
    expect(page.movements.every((row) => row.month === "2024-10")).toBe(true);
    const sizes = page.movements.map((row) => Math.abs(Number(row.change_value)));
    expect([...sizes].sort((a, b) => b - a)).toEqual(sizes);
    const churn = get("/api/mrr/movements?from=2024-01&to=2024-10&step=churn&page=1&page_size=50").body as MrrMovementsPage;
    expect(churn.movements.every((row) => row.step === "churn" && Number(row.change_value) < 0)).toBe(true);
    expect(churn.total).toBeGreaterThan(0);
  });

  it("answers 400 invalid_query with error.details {check, field, message}", () => {
    const response = get("/api/mrr/movements?from=2024&to=2024-10&step=nope&page=0&page_size=500");
    expect(response.status).toBe(400);
    const details = (response.body as { error: { code: string; details: { field: string }[] } }).error;
    expect(details.code).toBe("invalid_query");
    expect(details.details.map((detail) => detail.field)).toEqual(["from", "step", "page"]);
  });
});
