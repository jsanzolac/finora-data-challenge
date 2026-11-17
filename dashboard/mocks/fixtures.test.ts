import { describe, expect, it } from "vitest";
import { RUNS, compliancePct, recordsFor, statusFor, summaryFor } from "./fixtures";
import { handleMockRequest, MOCK_PASSWORD, type MockSession, type SessionStore } from "./handler";

function memoryStore(initial: MockSession | null = null): SessionStore {
  let session = initial;
  return { get: () => session, set: (next) => void (session = next) };
}

const latest = summaryFor(RUNS.find((run) => run.status === "succeeded")!.run_id)!;

describe("mock fixtures follow the contract and the approved rules", () => {
  it("has at least 6 succeeded runs for the trend, newest first, with a failed run", () => {
    expect(RUNS.filter((run) => run.status === "succeeded").length).toBeGreaterThanOrEqual(6);
    expect(RUNS.some((run) => run.status === "failed")).toBe(true);
    const starts = RUNS.map((run) => run.started_at);
    expect([...starts].sort().reverse()).toEqual(starts);
    expect(latest.trend.length).toBeGreaterThanOrEqual(6);
  });

  it("ranks three departments with different compliance levels", () => {
    expect(latest.datasets.map((d) => d.rank)).toEqual([1, 2, 3]);
    const pcts = latest.datasets.map((d) => d.row_compliance_pct);
    expect(new Set(pcts).size).toBe(3);
    expect([...pcts].sort((a, b) => b - a)).toEqual(pcts);
  });

  it("covers row and finding rules, exclude and flag actions, and na cells, with no run controls", () => {
    const kinds = new Set(latest.rules.map((rule) => rule.kind));
    const actions = new Set(latest.rules.map((rule) => rule.action));
    expect([...kinds].sort()).toEqual(["finding", "row"]);
    expect([...actions].sort()).toEqual(["exclude", "finding", "flag"]);
    const statuses = new Set(latest.rules.flatMap((rule) => Object.values(rule.results).map((r) => r.status)));
    expect([...statuses].sort()).toEqual(["fail", "na", "pass", "warn"]);
    for (const rule of latest.rules) {
      for (const [datasetId, result] of Object.entries(rule.results)) {
        if (!rule.applies_to.includes(datasetId)) {
          expect(result).toEqual({ evaluated: 0, failed: 0, compliance_pct: null, status: "na" });
        }
      }
    }
  });

  it("has a rule with more than 200 failing records", () => {
    const big = latest.rules.some((rule) => Object.values(rule.results).some((r) => r.failed > 200));
    expect(big).toBe(true);
  });

  it("applies the CDO's rounding and status thresholds", () => {
    expect(compliancePct(1962, 1)).toBe(99.95);
    expect(compliancePct(100000, 1)).toBe(99.99);
    expect(compliancePct(0, 0)).toBeNull();
    expect(statusFor(1962, 1, true)).toBe("warn");
    expect(statusFor(34, 2, true)).toBe("fail");
    expect(statusFor(34, 5, false)).toBe("warn");
    expect(statusFor(0, 0, true)).toBe("na");
  });

  it("stores the empty Industry record exactly as the rules document expects", () => {
    const records = recordsFor(latest.run.run_id, "SQ-02", "industry")!;
    expect(records).toHaveLength(1);
    expect(records[0]).toMatchObject({
      source_line: 1963,
      key: { ID: "" },
      values: { ID: "", Industria: "" },
      failed_columns: ["ID", "Industria"],
      reason: "EMPTY_RECORD: every source column is empty",
    });
  });
});

describe("mock API", () => {
  const finance: MockSession = { email: "f@x.test", role: "finance", must_change_password: false, password: MOCK_PASSWORD };
  const data: MockSession = { ...finance, email: "d@x.test", role: "data" };
  const run = latest.run.run_id;
  const query = (params: Record<string, string>) => new URLSearchParams({ run, ...params });

  it("answers 401 without a session and 403 password_change_required while a change is pending", () => {
    const path = "/api/dq/summary";
    expect(handleMockRequest({ method: "GET", path, query: query({}) }, memoryStore()).status).toBe(401);
    const pending = memoryStore({ ...data, must_change_password: true });
    const response = handleMockRequest({ method: "GET", path, query: query({}) }, pending);
    expect(response.status).toBe(403);
    expect(response.body).toEqual({ error: { code: "password_change_required", message: expect.any(String) } });
  });

  it("masks HR-sensitive S&M values for non-finance roles and never matches them in q", () => {
    const path = "/api/dq/rules/SB-10/datasets/sm_spend/records";
    const asData = handleMockRequest({ method: "GET", path, query: query({}) }, memoryStore(data));
    const asFinance = handleMockRequest({ method: "GET", path, query: query({}) }, memoryStore(finance));
    const dataRecord = (asData.body as { records: { values: Record<string, string> }[] }).records[0]!;
    const financeRecord = (asFinance.body as { records: { values: Record<string, string> }[] }).records[0]!;
    expect(dataRecord.values.PayrollExpenses).toBe("__restricted__");
    expect(dataRecord.values.Team).toBe("__restricted__");
    expect(dataRecord.values.PaidMedia).toBe(financeRecord.values.PaidMedia);
    expect(financeRecord.values.PayrollExpenses).toMatch(/^-\$/);

    const probe = financeRecord.values.PayrollExpenses!;
    const probed = handleMockRequest({ method: "GET", path, query: query({ q: probe }) }, memoryStore(data));
    expect((probed.body as { total: number }).total).toBe(0);
  });

  it("pages with page_size capped at 200 and filters with q", () => {
    const path = "/api/dq/rules/SQ-07b/datasets/transactions/records";
    const page = handleMockRequest({ method: "GET", path, query: query({ page_size: "500", page: "2" }) }, memoryStore(data));
    const body = page.body as { total: number; page_size: number; records: unknown[] };
    expect(body.page_size).toBe(200);
    expect(body.total).toBeGreaterThan(200);
    expect(body.records.length).toBe(Math.min(200, body.total - 200));
    const filtered = handleMockRequest({ method: "GET", path, query: query({ q: "Cliente" }) }, memoryStore(data));
    expect((filtered.body as { total: number }).total).toBe(0);
  });
});
