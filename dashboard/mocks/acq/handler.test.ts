/** The acquisition mock API behaves like the contract: roles, masking, scenarios, POST validation. */
import { describe, expect, it } from "vitest";
import type { AcqSummary, Scenario, ScenariosResponse } from "../../src/lib/acq/types";
import { MOCK_PASSWORD, handleMockRequest, memoryRateStore, type MockSession, type SessionStore } from "../handler";
import { PLANTED_RUN_ID } from "./fixtures";

function session(email: string, role: MockSession["role"]): SessionStore {
  let current: MockSession | null = { email, role, must_change_password: false, password: MOCK_PASSWORD };
  return { get: () => current, set: (next) => void (current = next) };
}

function call(store: SessionStore, method: string, path: string, body?: unknown, rates = memoryRateStore()) {
  const [pathname, query = ""] = path.split("?");
  return handleMockRequest({ method, path: pathname!, query: new URLSearchParams(query), body }, store, rates);
}

const BASE_RATES = [
  ["NEW", "WORKING", "0.8000"],
  ["WORKING", "ENGAGED", "0.4000"],
  ["ENGAGED", "SQL", "0.5000"],
  ["SQL", "DEMO", "0.7000"],
  ["DEMO", "PROPOSAL", "0.6000"],
  ["PROPOSAL", "WON", "0.4000"],
].map(([from_stage, to_stage, rate]) => ({ from_stage: from_stage!, to_stage: to_stage!, rate: rate! }));

describe("GET /api/acq/summary", () => {
  it("masks the HR categories for non-finance roles only", () => {
    const revops = call(session("revops@finora.test", "revops"), "GET", "/api/acq/summary?run=latest").body as AcqSummary;
    const finance = call(session("finance@finora.test", "finance"), "GET", "/api/acq/summary?run=latest").body as AcqSummary;
    const october = (summary: AcqSummary) => summary.months.find((month) => month.month === "2024-10")!;
    expect(october(revops).spend_value.Team).toBe("__restricted__");
    expect(october(revops).spend_value.PaidMedia).not.toBe("__restricted__");
    expect(october(revops).spend_total_value).toBe("200000000");
    expect(october(finance).spend_value.Team).not.toBe("__restricted__");
    expect(revops.months).toHaveLength(33);
    expect(revops.correlations).toHaveLength(1848);
  });

  it("serves a planted run with a cost_null_reason month, and 404 for an unknown run", () => {
    const planted = call(session("data@finora.test", "data"), "GET", `/api/acq/summary?run=${PLANTED_RUN_ID}`).body as AcqSummary;
    const november = planted.months.find((month) => month.month === "2024-11")!;
    expect(november.cost_null_reason).toBe("spend_missing");
    expect(planted.run.data_complete_through).toBe("2024-10");
    const unknown = call(session("data@finora.test", "data"), "GET", "/api/acq/summary?run=r1");
    expect([unknown.status, (unknown.body as { error: { code: string } }).error.code]).toEqual([404, "unknown_run"]);
  });

  it("answers 404 no_gold_run for the latest run before the first publish", () => {
    const store = session("data@finora.test", "data");
    const response = handleMockRequest(
      { method: "GET", path: "/api/acq/summary", query: new URLSearchParams("run=latest"), body: undefined },
      store,
      memoryRateStore(),
      { noGoldRun: true },
    );
    expect([response.status, (response.body as { error: { code: string } }).error.code]).toEqual([404, "no_gold_run"]);
  });

  it("needs a session, and a changed password", () => {
    const none: SessionStore = { get: () => null, set: () => undefined };
    expect(call(none, "GET", "/api/acq/summary").status).toBe(401);
    const pending: SessionStore = {
      get: () => ({ email: "new.analyst@finora.test", role: "data", must_change_password: true, password: MOCK_PASSWORD }),
      set: () => undefined,
    };
    expect(call(pending, "GET", "/api/acq/scenarios").status).toBe(403);
  });
});

describe("scenarios", () => {
  it("lists base first, an invalid scenario with its checks, and can_edit by role", () => {
    const data = call(session("data@finora.test", "data"), "GET", "/api/acq/scenarios").body as ScenariosResponse;
    expect(data.can_edit).toBe(false);
    expect(data.scenarios[0]!.scenario_id).toBe("base");
    const typo = data.scenarios.find((scenario) => scenario.scenario_id === "q4_typo")!;
    expect([typo.status, typo.failed_checks]).toEqual(["invalid", ["GR-03"]]);
    const finance = call(session("finance@finora.test", "finance"), "GET", "/api/acq/scenarios").body as ScenariosResponse;
    expect(finance.can_edit).toBe(true);
  });

  it("refuses POST for the data role", () => {
    const response = call(session("data@finora.test", "data"), "POST", "/api/acq/scenarios", {});
    expect(response.status).toBe(403);
  });

  it("validates, appends only the changed transitions, and reports no_change", () => {
    const rates = memoryRateStore();
    const finance = session("finance@finora.test", "finance");
    const bad = call(finance, "POST", "/api/acq/scenarios", { scenario_id: "Bad id", label: "", change_reason: "", rates: [] }, rates);
    expect(bad.status).toBe(400);
    const details = (bad.body as { error: { details: { check: string; field: string }[] } }).error.details;
    expect(details.map((detail) => [detail.check, detail.field])).toEqual([
      ["GR-01", "scenario_id"],
      ["LABEL_LENGTH", "label"],
      ["REASON_LENGTH", "change_reason"],
      ["GR-04", "rates"],
    ]);

    const body = {
      scenario_id: "demo_090",
      label: "Demo to Proposal at 90%",
      change_reason: "Test",
      rates: BASE_RATES.map((rate) => (rate.from_stage === "DEMO" ? { ...rate, rate: "0.9000" } : rate)),
    };
    const created = call(finance, "POST", "/api/acq/scenarios", body, rates);
    expect(created.status).toBe(201);
    const scenario = created.body as Scenario;
    expect(scenario.status).toBe("valid");
    expect(scenario.changed_by).toMatch(/^dashboard:[0-9a-f]{12}$/);
    expect(scenario.changed_by).not.toContain("finance@");
    expect(rates.get().filter((row) => row.scenario_id === "demo_090")).toHaveLength(6);

    expect(call(finance, "POST", "/api/acq/scenarios", body, rates).status).toBe(400);
    const changed = { ...body, rates: body.rates.map((rate) => (rate.from_stage === "NEW" ? { ...rate, rate: "0.8500" } : rate)) };
    expect(call(finance, "POST", "/api/acq/scenarios", changed, rates).status).toBe(201);
    expect(rates.get().filter((row) => row.scenario_id === "demo_090")).toHaveLength(7);
  });
});
