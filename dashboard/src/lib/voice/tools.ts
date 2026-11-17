/**
 * The three client tools of contracts/agent_api_contract.md, as pure handlers over
 * injected dependencies (so they are unit-tested without a browser or the SDK).
 * Each returns a short Spanish string: that is what the agent hears back. The agent
 * only passes ids; the page fetches data itself with the user's own session.
 */
import { kpiEntry } from "./kpis";
import { PAGE_HREF, PAGE_LABEL_ES, RESULT_ID, type AgentResult, type PageId } from "./types";

export interface ToolDeps {
  fetchResult: (resultId: string) => Promise<AgentResult>;
  openChart: (result: AgentResult) => void;
  currentPage: () => PageId;
  navigate: (href: string) => void;
  /** Resolves with the card element once it is on screen, or null after a timeout. */
  waitForKpi: (kpiId: string) => Promise<HTMLElement | null>;
  highlight: (element: HTMLElement, kpiId: string) => void;
}

function param(parameters: unknown, name: string): string | null {
  if (typeof parameters !== "object" || parameters === null) return null;
  const value = (parameters as Record<string, unknown>)[name];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function isPage(value: string | null): value is PageId {
  return value === "dq" || value === "acquisition" || value === "mrr";
}

export function createClientTools(deps: ToolDeps) {
  return {
    async show_chart(parameters: unknown): Promise<string> {
      const resultId = param(parameters, "result_id");
      if (!resultId || !RESULT_ID.test(resultId)) return "No pude mostrar el gráfico: el identificador no es válido.";
      try {
        const result = await deps.fetchResult(resultId);
        deps.openChart(result);
        return `Gráfico mostrado: ${result.title_es}.`;
      } catch (error) {
        const status = (error as { status?: number }).status;
        if (status === 401) return "Por favor recarga la página para continuar.";
        if (status === 403 || status === 404) return "Ese resultado no está disponible para este usuario.";
        return "No pude mostrar el gráfico ahora.";
      }
    },

    async highlight_kpi(parameters: unknown): Promise<string> {
      const kpiId = param(parameters, "kpi_id");
      const entry = kpiId ? kpiEntry(kpiId) : undefined;
      if (!kpiId || !entry) return "No encuentro esa tarjeta en el tablero.";
      if (deps.currentPage() !== entry.page) deps.navigate(PAGE_HREF[entry.page]);
      const element = await deps.waitForKpi(kpiId);
      if (!element) return `No encuentro la tarjeta «${entry.label_es}» en la página.`;
      deps.highlight(element, kpiId);
      return `Resaltada: ${entry.label_es}.`;
    },

    async go_to_page(parameters: unknown): Promise<string> {
      const page = param(parameters, "page");
      if (!isPage(page)) return "Esa página no existe. Las páginas son dq, acquisition y mrr.";
      if (deps.currentPage() !== page) deps.navigate(PAGE_HREF[page]);
      return `Página abierta: ${PAGE_LABEL_ES[page]}.`;
    },
  };
}

export type ClientToolHandlers = ReturnType<typeof createClientTools>;

/** "/acquisition/" -> "acquisition". */
export function pageOfPath(pathname: string): PageId {
  if (pathname.startsWith("/acquisition")) return "acquisition";
  if (pathname.startsWith("/mrr")) return "mrr";
  return "dq";
}
