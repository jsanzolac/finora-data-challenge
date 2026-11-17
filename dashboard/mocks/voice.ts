/**
 * Mock voice session (MOCK BUILDS ONLY; scripts/check-no-mocks.mjs fails a real build that
 * contains its markers). POST /api/agent-session answers a `mock://` URL; the provider then
 * runs this script instead of ElevenLabs: the agent greets, answers a question, and calls
 * the three client tools in turn (show_chart, highlight_kpi, go_to_page).
 * The results are built from the real fixtures (acq levers, MRR bridge).
 */
import type { AcqSummary } from "../src/lib/acq/types";
import type { MrrSummary } from "../src/lib/mrr/types";
import type { AgentResult } from "../src/lib/voice/types";
import acqFixture from "./acq/summary.json";
import mrrFixture from "./mrr/summary.json";

export const MOCK_SIGNED_URL = "mock://finora-voice";
export const MOCK_AGENT_TOKEN = "mock-agent-token-not-a-secret";
export const VOICE_UNAVAILABLE_KEY = "voice_mock_unavailable";
/** Set to "1" to answer a real-looking ElevenLabs signed URL, so the real SDK path runs (the e2e mocks the socket). */
export const VOICE_SDK_KEY = "voice_mock_sdk";
export const MOCK_SDK_SIGNED_URL = "wss://api.elevenlabs.io/v1/convai/conversation?agent_id=mock-agent&conversation_signature=mock-signature";

const acq = acqFixture as unknown as AcqSummary;
const mrr = mrrFixture as unknown as MrrSummary;
const label = (code: string) => acq.industries.find((industry) => industry.code === code)?.label ?? code;

function result(partial: Omit<AgentResult, "sql_hash" | "run_id" | "created_at">): AgentResult {
  return { ...partial, sql_hash: "mock", run_id: acq.run.run_id, created_at: "2026-11-17T20:00:00Z" };
}

const industries = (acq.levers?.industries ?? [])
  .filter((row) => row.won_definition === "first_payment" && row.period_code === "from_2023_06")
  .sort((a, b) => Number(a.run_rate_mrr_per_won_value) - Number(b.run_rate_mrr_per_won_value));
const cohorts = (acq.levers?.cohorts ?? []).filter((row) => row.won_definition === "first_payment" && row.is_complete_run_rate);
const october = mrr.months.find((month) => month.month === "2024-10");

export const MOCK_RESULTS: Record<string, AgentResult> = {
  r_mock_ticket_by_industry: result({
    result_id: "r_mock_ticket_by_industry",
    question: "¿Qué industria bajó más su ticket?",
    title_es: "Ingreso inicial por cliente nuevo, por industria (jun 2023 – oct 2024)",
    chart: { type: "bar", x: "industria", y: ["ingreso_inicial"], unit: "money" },
    evidence: "observado",
    caveats_es: [
      "El ingreso inicial es el promedio de los meses 2 a 4 después del primer pago, solo de cohortes con esos tres meses en los datos.",
      "Antes y desde junio de 2023 son solo una línea base: no explican el cambio de ticket.",
    ],
    columns: ["industria", "ingreso_inicial"],
    rows: industries.map((row) => [label(row.industry_code), row.run_rate_mrr_per_won_value]),
  }),
  r_mock_ticket_by_cohort: result({
    result_id: "r_mock_ticket_by_cohort",
    question: "¿Cuándo empezó a bajar el ticket?",
    title_es: "Ingreso inicial por cliente nuevo, por cohorte semestral",
    chart: { type: "line", x: "cohorte", y: ["ingreso_inicial"], unit: "money" },
    columns: ["cohorte", "ingreso_inicial"],
    rows: cohorts.map((row) => [row.cohort_half, row.run_rate_mrr_per_won_value]),
  }),
  r_mock_mrr_bridge: result({
    result_id: "r_mock_mrr_bridge",
    question: "¿Por qué cambió el MRR en octubre?",
    title_es: "Puente del MRR, octubre de 2024",
    chart: { type: "table", x: "paso", y: ["valor"], unit: "money" },
    columns: ["paso", "valor"],
    rows: mrr.steps.filter((step) => october?.step_value[step.code] !== null).map((step) => [step.label, october?.step_value[step.code] ?? null]),
  }),
};

interface Tools {
  show_chart: (parameters: unknown) => Promise<string>;
  highlight_kpi: (parameters: unknown) => Promise<string>;
  go_to_page: (parameters: unknown) => Promise<string>;
}
interface Events {
  onStatus: (status: "connecting" | "connected" | "disconnected") => void;
  onMode: (mode: "speaking" | "listening") => void;
  onMessage: (role: "user" | "agent", text: string) => void;
}

/** Runs the scripted conversation; returns how to end it. */
export function startMockVoice(tools: Tools, events: Events): () => void {
  let cancelled = false;
  const timers: number[] = [];
  const wait = (ms: number) =>
    new Promise<void>((resolve) => {
      timers.push(window.setTimeout(resolve, ms));
    });
  const say = (text: string) => {
    events.onMode("speaking");
    events.onMessage("agent", text);
  };
  const hear = (text: string) => {
    events.onMode("listening");
    events.onMessage("user", text);
  };

  void (async () => {
    events.onStatus("connecting");
    await wait(300);
    if (cancelled) return;
    events.onStatus("connected");
    say("Hola, estoy cargando los números de hoy.");
    await wait(700);
    if (cancelled) return;
    hear("¿Qué industria bajó más su ticket?");
    await wait(700);
    if (cancelled) return;
    say("Retail fue la que más bajó: de 43.671 a 29.407 por cliente nuevo. Te muestro el gráfico.");
    await tools.show_chart({ result_id: "r_mock_ticket_by_industry" });
    await wait(900);
    if (cancelled) return;
    say("Es la tarjeta del ingreso inicial por cliente nuevo.");
    await tools.highlight_kpi({ kpi_id: "acq.lost.starting_revenue" });
    // Long enough for a person (and the e2e's axe scan) to look before the page changes.
    await wait(4500);
    if (cancelled) return;
    hear("Llévame al MRR.");
    await wait(600);
    if (cancelled) return;
    await tools.go_to_page({ page: "mrr" });
    say("Aquí está el MRR. ¿Te muestro el puente?");
    await wait(700);
    if (cancelled) return;
    events.onMode("listening");
  })();

  return () => {
    cancelled = true;
    timers.forEach((timer) => window.clearTimeout(timer));
    window.setTimeout(() => events.onStatus("disconnected"), 0);
  };
}

/** Called by installMockApi: the provider finds the driver here in mock builds. */
export function installMockVoice(): void {
  (window as unknown as Record<string, unknown>).__FINORA_VOICE_MOCK__ = { start: startMockVoice };
}
