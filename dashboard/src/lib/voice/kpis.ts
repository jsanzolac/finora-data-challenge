/**
 * The dashboard cards the agent can point at with `highlight_kpi`: the 32 `kpi_id`s of the
 * CDO's catalog (docs/semantic_layer.md §1.6, catalog `sl-2026-11-17`), 4 of them
 * parameterized. Each card carries `data-kpi-id`. The page of an id lets the agent
 * highlight a card on another page; an unknown id is ignored.
 */
import type { PageId } from "./types";

export interface KpiEntry {
  page: PageId;
  label_es: string;
}

export const CATALOG_VERSION = "sl-2026-11-17";

const FIXED: Record<string, KpiEntry> = {
  "acq.verdict": { page: "acquisition", label_es: "Qué mover" },
  "acq.plan.won": { page: "acquisition", label_es: "Clientes nuevos por mes" },
  "acq.plan.new_mrr": { page: "acquisition", label_es: "MRR nuevo por mes" },
  "acq.plan.payback": { page: "acquisition", label_es: "Recuperación" },
  "acq.lever.ticket": { page: "acquisition", label_es: "Palanca: ticket" },
  "acq.lever.mix": { page: "acquisition", label_es: "Palanca: mezcla de industrias" },
  "acq.lever.conversion": { page: "acquisition", label_es: "Palanca: tasas de conversión" },
  "acq.lever.spend": { page: "acquisition", label_es: "Palanca: gasto mensual" },
  "acq.lever.ranking": { page: "acquisition", label_es: "Palancas con más impacto" },
  "acq.lost.new_customers": { page: "acquisition", label_es: "Clientes nuevos por mes" },
  "acq.lost.starting_revenue": { page: "acquisition", label_es: "Ingreso inicial por cliente nuevo" },
  "acq.lost.ticket_by_cohort": { page: "acquisition", label_es: "Ingreso inicial por cohorte semestral" },
  "acq.lost.keep_paying": { page: "acquisition", label_es: "Clientes que siguen pagando" },
  "acq.lost.ticket_by_industry": { page: "acquisition", label_es: "Ingreso inicial por industria" },
  "acq.funnel.stages": { page: "acquisition", label_es: "Etapas del embudo" },
  "acq.funnel.won_cost": { page: "acquisition", label_es: "Costo por cliente ganado" },
  "acq.funnel.sensitivity": { page: "acquisition", label_es: "Un punto más en una tasa" },
  "acq.time.new_customers": { page: "acquisition", label_es: "Clientes nuevos en el tiempo" },
  "acq.signals": { page: "acquisition", label_es: "Gasto y clientes nuevos" },
  "acq.industries": { page: "acquisition", label_es: "Industrias" },
  "acq.monthly_table": { page: "acquisition", label_es: "Datos mensuales" },
  "mrr.why.hero": { page: "mrr", label_es: "Por qué cambió el MRR" },
  "mrr.trend": { page: "mrr", label_es: "MRR por mes" },
  "mrr.leakage": { page: "mrr", label_es: "Ingreso no capturado por descuentos" },
  "mrr.monthly_table": { page: "mrr", label_es: "Datos mensuales del MRR" },
  "mrr.bridge.opening": { page: "mrr", label_es: "MRR de apertura" },
  "mrr.bridge.closing": { page: "mrr", label_es: "MRR de cierre" },
  "mrr.bridge.timing": { page: "mrr", label_es: "Efecto del momento de cobro" },
};

const DRIVER_ES: Record<string, string> = { behaviour: "Comportamiento de clientes", pricing: "Precios", timing: "Momento de los pagos" };

/** The parameterized ids: dq.scorecard.<dataset_id>, dq.rule_cell.<rule_id>.<dataset_id>, mrr.why.driver.<key>, mrr.bridge.<line>. */
const PATTERNS: [RegExp, (match: RegExpExecArray) => KpiEntry][] = [
  [/^dq\.scorecard\.([a-z][a-z0-9_]*)$/, (m) => ({ page: "dq", label_es: `Departamento ${m[1]}` })],
  [/^dq\.rule_cell\.([A-Za-z0-9-]+)\.([a-z][a-z0-9_]*)$/, (m) => ({ page: "dq", label_es: `Regla ${m[1]} en ${m[2]}` })],
  [/^mrr\.why\.driver\.(behaviour|pricing|timing)$/, (m) => ({ page: "mrr", label_es: DRIVER_ES[m[1]!] ?? m[1]! })],
  [/^mrr\.bridge\.([a-z][a-z0-9_]*)$/, (m) => ({ page: "mrr", label_es: `Puente del MRR: ${m[1]!.replace(/_/g, " ")}` })],
];

export function kpiEntry(kpiId: string): KpiEntry | undefined {
  if (Object.prototype.hasOwnProperty.call(FIXED, kpiId)) return FIXED[kpiId];
  for (const [pattern, build] of PATTERNS) {
    const match = pattern.exec(kpiId);
    if (match) return build(match);
  }
  return undefined;
}

/** The fixed ids (the parameterized ones are matched by pattern). */
export const FIXED_KPI_IDS = Object.keys(FIXED);
