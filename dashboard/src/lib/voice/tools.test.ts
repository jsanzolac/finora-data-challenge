/** The client tools of contracts/agent_api_contract.md, over injected dependencies. */
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { CATALOG_VERSION, FIXED_KPI_IDS, kpiEntry } from "./kpis";
import { createClientTools, pageOfPath, type ToolDeps } from "./tools";
import type { AgentResult, PageId } from "./types";

const RESULT: AgentResult = {
  result_id: "r_7f3a",
  question: "¿Qué industria bajó más su ticket?",
  title_es: "Ticket por cliente nuevo por industria",
  chart: { type: "bar", x: "industry", y: ["run_rate_value"], unit: "money" },
  columns: ["industry", "run_rate_value"],
  rows: [["Retail", "28733.00"]],
  sql_hash: "x",
  run_id: "r1",
  created_at: "2026-11-17T20:00:00Z",
};

function deps(page: PageId = "acquisition", overrides: Partial<ToolDeps> = {}) {
  const element = {} as HTMLElement;
  const base: ToolDeps = {
    fetchResult: vi.fn(async () => RESULT),
    openChart: vi.fn(),
    currentPage: () => page,
    navigate: vi.fn(),
    waitForKpi: vi.fn(async () => element),
    highlight: vi.fn(),
  };
  return { ...base, ...overrides, element };
}

describe("show_chart", () => {
  it("fetches the result with the user's session and opens the panel", async () => {
    const d = deps();
    const answer = await createClientTools(d).show_chart({ result_id: "r_7f3a" });
    expect(d.fetchResult).toHaveBeenCalledWith("r_7f3a");
    expect(d.openChart).toHaveBeenCalledWith(RESULT);
    expect(answer).toBe("Gráfico mostrado: Ticket por cliente nuevo por industria.");
  });

  it("rejects ids that are not opaque tokens, without fetching", async () => {
    const d = deps();
    const tools = createClientTools(d);
    expect(await tools.show_chart({ result_id: "../auth/session" })).toContain("no es válido");
    expect(await tools.show_chart({})).toContain("no es válido");
    expect(d.fetchResult).not.toHaveBeenCalled();
  });

  it("says why it couldn't: reload on 401, not available on 403/404", async () => {
    const unauthorized = deps("acquisition", { fetchResult: vi.fn(async () => Promise.reject(new ApiError(401, "unauthorized", "x"))) });
    expect(await createClientTools(unauthorized).show_chart({ result_id: "r1" })).toBe("Por favor recarga la página para continuar.");
    const forbidden = deps("acquisition", { fetchResult: vi.fn(async () => Promise.reject(new ApiError(403, "role_not_allowed", "x"))) });
    expect(await createClientTools(forbidden).show_chart({ result_id: "r1" })).toContain("no está disponible");
    expect(forbidden.openChart).not.toHaveBeenCalled();
  });
});

describe("highlight_kpi", () => {
  it("highlights a card on the current page", async () => {
    const d = deps("acquisition");
    const answer = await createClientTools(d).highlight_kpi({ kpi_id: "acq.lost.starting_revenue" });
    expect(d.navigate).not.toHaveBeenCalled();
    expect(d.highlight).toHaveBeenCalledWith(d.element, "acq.lost.starting_revenue");
    expect(answer).toBe("Resaltada: Ingreso inicial por cliente nuevo.");
  });

  it("goes to the card's page first when it is elsewhere", async () => {
    const d = deps("dq");
    await createClientTools(d).highlight_kpi({ kpi_id: "mrr.why.driver.behaviour" });
    expect(d.navigate).toHaveBeenCalledWith("/mrr/");
    expect(d.waitForKpi).toHaveBeenCalledWith("mrr.why.driver.behaviour");
  });

  it("answers plainly for an unknown id or a card that never appears", async () => {
    const d = deps();
    expect(await createClientTools(d).highlight_kpi({ kpi_id: "acq.nope" })).toBe("No encuentro esa tarjeta en el tablero.");
    const missing = deps("acquisition", { waitForKpi: vi.fn(async () => null) });
    expect(await createClientTools(missing).highlight_kpi({ kpi_id: "acq.funnel.stages" })).toContain("No encuentro la tarjeta");
    expect(missing.highlight).not.toHaveBeenCalled();
  });
});

describe("go_to_page", () => {
  it("navigates client-side to dq, acquisition or mrr", async () => {
    const d = deps("dq");
    const tools = createClientTools(d);
    expect(await tools.go_to_page({ page: "mrr" })).toBe("Página abierta: MRR.");
    expect(d.navigate).toHaveBeenCalledWith("/mrr/");
    expect(await tools.go_to_page({ page: "dq" })).toBe("Página abierta: Calidad de datos.");
    expect(d.navigate).toHaveBeenCalledTimes(1);
  });

  it("refuses other pages", async () => {
    const d = deps();
    expect(await createClientTools(d).go_to_page({ page: "https://evil.example" })).toContain("no existe");
    expect(d.navigate).not.toHaveBeenCalled();
  });
});

describe("KPI registry (catalog sl-2026-11-17)", () => {
  it("knows the fixed ids and the four parameterized families, each on one page", () => {
    expect(CATALOG_VERSION).toBe("sl-2026-11-17");
    expect(FIXED_KPI_IDS).toHaveLength(28);
    for (const id of FIXED_KPI_IDS) {
      const entry = kpiEntry(id)!;
      expect(id.startsWith(entry.page === "acquisition" ? "acq." : `${entry.page}.`), id).toBe(true);
    }
    expect(kpiEntry("dq.scorecard.sm_spend")?.page).toBe("dq");
    expect(kpiEntry("dq.rule_cell.SQ-07b.transactions")?.page).toBe("dq");
    expect(kpiEntry("mrr.why.driver.pricing")?.page).toBe("mrr");
    expect(kpiEntry("mrr.bridge.first_payment_multiple")?.page).toBe("mrr");
    expect(kpiEntry("mrr.why.driver.discount")).toBeUndefined();
    expect(kpiEntry("acq.run_rate_per_won")).toBeUndefined();
    expect([pageOfPath("/"), pageOfPath("/acquisition/"), pageOfPath("/mrr/")]).toEqual(["dq", "acquisition", "mrr"]);
  });
});
