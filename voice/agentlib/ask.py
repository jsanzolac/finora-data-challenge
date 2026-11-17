"""POST /api/agent/ask, end to end, minus HTTP (docs/semantic_layer.md §2-3, contract v1.1).

question -> Kimi K3 (Bedrock us-east-1, tool `submit_query_spec`, never SQL; it gets
the question, the catalog and the previous spec + summary_es, never rows) -> validate
-> compile (one retry with the validator's errors) -> Athena (workgroup finora-dl) or
the DQ snapshot -> derived ops and a templated, number-checked summary_es.
Out-of-scope answers use the §3 templates; their alternative's figures are computed by
running the alternative spec, never written by the model.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable

import boto3

from . import bedrock
from . import catalog as C
from . import compiler as K
from . import fmt as F
from . import numbers as N
from . import post as P

QUESTION_MAX = 500
POLL_S = 0.25


def clean_question(v: Any) -> str:
    if not isinstance(v, str):
        return ""
    s = "".join(ch if ch.isprintable() else " " for ch in v)
    return " ".join(s.split())[:QUESTION_MAX]


def normalize(q: str) -> str:
    s = unicodedata.normalize("NFD", q.casefold())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s%-]", " ", s).split())


# ---------------------------------------------------------------------------- #
# Kimi K3: the tool and the prompt                                              #
# ---------------------------------------------------------------------------- #

def _metric_dims(m: C.Metric) -> list[str]:
    if m.status == "dq":
        return ["dataset", "rule"]
    dims = set()
    for b in m.bindings:
        dims |= set(C.SOURCES[b.source].dims)
    return sorted(dims)


def tool_schema() -> dict:
    """§2.1 for Bedrock tool use: the same constraints, $refs inlined, if/then
    enforced in code (compiler.validate)."""
    month = {"type": "string", "pattern": "^20[0-9]{2}-(0[1-9]|1[0-2])$"}
    arr = lambda enum: {"type": "array", "items": {"type": "string", "enum": sorted(enum)}}  # noqa: E731
    return {
        "type": "object", "additionalProperties": False, "required": ["catalog_version", "intent"],
        "properties": {
            "catalog_version": {"type": "string", "enum": [C.VERSION]},
            "intent": {"type": "string", "enum": ["answer", "out_of_scope"]},
            "domain": {"type": "string", "enum": ["dq", "acquisition", "mrr"]},
            "metrics": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string",
                                                                                  "enum": sorted(C.METRICS)}},
            # derived is flattened for the model (Kimi K3 loops on nested arrays in tool input);
            # to_spec() rebuilds the §2.1 shape before validation.
            "derived_op": {"type": "string", "enum": ["ratio", "share", "growth", "rank", "lever_scenario"]},
            "derived_of": {"type": "string"}, "derived_over": {"type": "string"},
            "from_period": {"type": "string"}, "to_period": {"type": "string"},
            "baseline_period": {"type": "string", "enum": ["pre_2023_06", "from_2023_06"]},
            "ticket_pct": {"type": "number"}, "spend_pct": {"type": "number"},
            "mix_from_industry": {"type": "string", "enum": sorted(C.INDUSTRIES)},
            "mix_to_industry": {"type": "string", "enum": sorted(C.INDUSTRIES)},
            "mix_points": {"type": "number"},
            "dimensions": {"type": "array", "maxItems": 2, "items": {"type": "string", "enum": sorted(C.DIMENSIONS)}},
            "filters": {"type": "object", "required": ["time"], "properties": {
                "time": {"type": "object", "properties": {
                    "from": month, "to": month, "year": {"type": "integer", "minimum": 2020, "maximum": 2035},
                    "quarter": {"type": "string", "pattern": "^20[0-9]{2}-Q[1-4]$"},
                    "period_code": {"type": "string", "enum": ["pre_2023_06", "from_2023_06", "full"]},
                    "relative": {"type": "string", "enum": sorted(K.RELATIVE)}}},
                "industry": arr(C.INDUSTRIES), "spend_category": arr(C.SPEND_CATEGORIES),
                "spend_group": arr(C.SPEND_GROUPS), "funnel_stage": arr(C.STAGES),
                "scenario_id": {"type": "string"}, "rule_id": {"type": "array", "items": {"type": "string"}},
                "dataset_id": arr(C.DATASETS), "rule_status": arr({"pass", "warn", "fail", "na"}),
                "mrr_line": arr(C.MRR_LINES), "driver": arr(C.DRIVERS),
                "customer_scope": {"type": "string", "enum": sorted(C.CUSTOMER_SCOPES)}}},
            "won_definition": {"type": "string", "enum": ["first_payment", "new_logo"]},
            "sort": {"type": "object", "required": ["by", "dir"], "properties": {
                "by": {"type": "string"}, "dir": {"type": "string", "enum": ["asc", "desc"]}}},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            "chart": {"type": "object", "required": ["type"], "properties": {
                "type": {"type": "string", "enum": ["kpi", "bar", "line", "table"]}}},
            "out_of_scope": {"type": "object", "required": ["reason_code"], "properties": {
                "reason_code": {"type": "string", "enum": sorted(C.OOS)},
                "slots": {"type": "object", "additionalProperties": {"type": "string", "maxLength": 40}}}}}}


_PROMPT: str | None = None


def system_prompt(ctx: K.Context) -> str:
    global _PROMPT
    if _PROMPT is None:
        lines = []
        for m in C.METRICS_LIST:
            if m.status in ("not_available",):
                tag = " [NO DISPONIBLE: siempre out_of_scope discounts_billing]"
            elif m.status == "hr":
                tag = " [PERSONAL: siempre out_of_scope hr_restricted]"
            else:
                tag = ""
            syn = C.SYNONYMS.get(m.id, "")
            lines.append(f"- {m.id}: {m.name_es}" + (f" ({syn})" if syn else "") + f". {m.definition_es} "
                         f"Dimensiones: {', '.join(_metric_dims(m)) or 'ninguna'}. Evidencia: {m.evidence}.{tag}")
        oos = "\n".join(f"- {code} ({rid})" for code, (rid, _, _) in C.OOS.items())
        _PROMPT = PROMPT_TEMPLATE.replace("{CATALOG}", "\n".join(lines)).replace("{OOS}", oos) \
            .replace("{VERSION}", C.VERSION)
    dct = ctx.data_complete_through
    return (_PROMPT.replace("{DCT}", dct).replace("{DCT_ES}", F.month_es(dct))
            .replace("{LAST_YEAR}", str(int(dct[:4]) - 1)).replace("{DCT_YEAR}", dct[:4])
            .replace("{CCT}", ctx.churn_confirmed_through).replace("{WS}", ctx.window_start_month))


PROMPT_TEMPLATE = """Eres el traductor de preguntas habladas en español a una especificación de consulta (query spec) del catálogo gobernado {VERSION} de Finora, un SaaS B2B de software financiero para pymes. Llamas SIEMPRE a la herramienta submit_query_spec exactamente una vez. Nunca escribes SQL, nunca escribes números de resultados y nunca inventas métricas: solo usas los ids de abajo.

CONTEXTO (lo resuelve el sistema, no lo inventes):
- Los datos llegan hasta {DCT} ({DCT_ES}). La ventana empieza en {WS}; los clientes nuevos (Won) empiezan en el mes siguiente.
- "hoy", "ahora", "el último mes", "este mes cerrado" = relative latest_month. "el año pasado" = year {LAST_YEAR}. "este año" = year {DCT_YEAR}.
- "desde junio de 2023", "el periodo actual" = period_code from_2023_06; "antes", "antes de junio de 2023" = pre_2023_06. Si la pregunta compara "hoy" con "antes" sobre ticket, clientes al mes, costo o payback, usa el periodo (no meses).
- Las bajas confirmadas llegan hasta {CCT}; los meses posteriores son provisionales.
- Nunca inventes un mes posterior a {DCT}: si lo piden ("noviembre de 2024", "2025", "este mes" en curso), escríbelo tal cual en filters.time y el sistema responderá que no hay datos.

CATÁLOGO (metric_id: nombre (sinónimos). definición. dimensiones permitidas. evidencia):
{CATALOG}

DIMENSIONES: month, quarter, year, period (pre_2023_06 | from_2023_06), cohort_half (2022-H1…2024-H2), industry (RESTAURANTS Restaurantes, MANUFACTURING Producción, RETAIL Retail/comercio, TECHNOLOGY Tecnología, PROFESSIONAL_SERVICES Servicios profesionales, HEALTHCARE Salud, UNKNOWN/UNMAPPED sin industria), spend_category (PaidMedia, PublicidadNoWeb, Travel, SoftwareTools; Team, PayrollExpenses y Freelance son de personal), spend_group (media, other, people), funnel_stage (NEW … WON), rule, dataset (transactions, industry, sm_spend), mrr_line (new, reactivation, expansion, contraction, churn = bajas, pause, resume, grace_drop, inferred_price_step, first_payment_multiple, timing_*), driver (behaviour, pricing, timing), customer_scope (won, left_censored, all).

REGLAS DE LA SPEC:
1. intent "answer": domain, metrics (1 a 3, del mismo dominio y la misma fuente), dimensions (0 a 2), filters con time (puede ser {}), chart {type}. won_definition "first_payment" salvo que digan "nuevos logos", "sin los que ya estaban activos", "sin los que probablemente ya estaban activos" o "definición canónica": entonces "new_logo".
2. Calidad de datos (domain dq): time {"relative": "latest_run"}. Por archivo: dimensions [dataset]. Por regla: metrics [dq.rule_failed_count], dimensions [rule, dataset], filtro rule_status. "peor calidad" = sort asc por dq.row_compliance_pct, limit 1.
3. Derivadas (campos planos, máximo una): derived_op "growth" + derived_of + from_period + to_period para comparar dos periodos del mismo tipo (pre_2023_06→from_2023_06, "2023"→"2024", "2024-09"→"2024-10"); derived_op "share" + derived_of + derived_over (una dimensión) para "qué parte" o "cuánto aporta"; derived_op "ratio" + derived_of + derived_over; derived_op "lever_scenario" + baseline_period + (mix_from_industry, mix_to_industry, mix_points | ticket_pct | spend_pct) para "¿qué pasa si…?" con palancas (mezcla, ticket, gasto). Ranking: sort {by: metric_id, dir} + limit ("la que más bajó" = sort asc por la métrica con growth, limit 1; "la que más aporta" = sort desc).
7. Métricas acompañantes (inclúyelas siempre): MRR de un mes o por industria = [mrr.closing, mrr.paying_customers]; MRR perdido o ganado por una línea (bajas, expansión…) = [mrr.line_amount, mrr.line_events] con filtro mrr_line; "peor/mejor calidad" de un archivo = [dq.row_compliance_pct, dq.rows_excluded]; escenario de palancas = [acq.new_mrr_per_month, acq.run_rate_per_won, acq.payback_months]; "payback y cuánto cuesta" = [acq.payback_months, acq.cost_per_won]. "¿Qué X aporta más…?", "qué parte", "participación" = además derived_op "share" con derived_of la métrica principal y derived_over la dimensión, y sort desc.
4. Stocks (mrr.closing, mrr.opening, mrr.paying_customers) nunca se suman en el tiempo. MRR por industria: dimensions [industry] con un mes (latest_month si dicen "hoy").
5. Seguimientos ("¿y en Retail?", "¿y sin los que ya estaban activos?", "¿y el año anterior?"): parte de la spec anterior y cambia solo lo que el usuario cambió.
6. "CAC" se responde con acq.cost_per_won. "ticket", "cuánto paga un cliente nuevo al mes" = acq.run_rate_per_won. "pago mensual promedio de la base por industria" = acq.avg_monthly_payment.

FUERA DE ALCANCE (intent "out_of_scope", out_of_scope.reason_code; slots solo con etiquetas del catálogo, nunca números):
{OOS}
- causal_spend_won: "si invertimos/gastamos más… ¿cuántos clientes?", "¿el gasto trae clientes?", "qué canal funciona", "retorno de la pauta", "atribución".
- funnel_stage_observed: "¿en qué etapa perdemos…?", conversión real entre etapas, "¿cuántos leads tuvimos?", tiempo por etapa. Solo si piden explícitamente "el embudo estimado" o "con las tasas supuestas" respondes con acq.funnel_stage_count o acq.rate_sensitivity.
- discounts_billing: descuentos, promociones, fuga, precio de lista, MRR neto, "cuánto regalamos".
- currency: "¿en qué moneda?", "en dólares", "en pesos", "tipo de cambio", "convertir".
- single_person_pay: "¿cuánto gana…?", salario o sueldo de una persona o cargo, pago de un freelance.
- beyond_data_complete_through: cualquier mes o periodo posterior a {DCT}.
- customer_level: "el cliente N", "¿quién paga más?", "¿cuál es el cliente que…?", lista de clientes, "¿qué clientes se fueron?".
- dq_record_level: "muéstrame la fila…", "¿qué registros fallaron?", el valor exacto de un registro.
- hr_restricted: gasto de equipo (Team), nómina (PayrollExpenses) o freelance, para cualquier rol.
- forecast: "¿cuántos tendremos…?", proyección, pronóstico, meta del próximo año.
- outside_catalog: leads, CRM, NPS, uso del producto, motivos de baja, márgenes, LTV o cualquier dato que no esté arriba. slots.falta = qué falta (palabras), slots.closest = el metric_id más cercano.

EJEMPLOS (no son las preguntas reales):
- "¿Cuánto MRR teníamos en junio de 2024?" -> {"catalog_version":"{VERSION}","intent":"answer","domain":"mrr","metrics":["mrr.closing","mrr.paying_customers"],"dimensions":[],"filters":{"time":{"from":"2024-06","to":"2024-06"}},"chart":{"type":"kpi"}}
- "¿Cuántos clientes nuevos ganamos por trimestre en 2023?" -> {"catalog_version":"{VERSION}","intent":"answer","domain":"acquisition","metrics":["acq.won_count"],"dimensions":["quarter"],"filters":{"time":{"year":2023}},"chart":{"type":"bar"}}
- "¿Subió el costo por cliente nuevo desde junio de 2023?" -> {"catalog_version":"{VERSION}","intent":"answer","domain":"acquisition","metrics":["acq.cost_per_won"],"derived_op":"growth","derived_of":"acq.cost_per_won","from_period":"pre_2023_06","to_period":"from_2023_06","dimensions":[],"filters":{"time":{}},"chart":{"type":"bar"}}
- "¿Qué cohorte semestral retiene mejor a 6 meses?" -> {"catalog_version":"{VERSION}","intent":"answer","domain":"acquisition","metrics":["acq.paying_m6_share"],"dimensions":["cohort_half"],"filters":{"time":{}},"sort":{"by":"acq.paying_m6_share","dir":"desc"},"limit":1,"chart":{"type":"bar"}}
- "¿Qué pasa con el payback si subimos el ticket 10 %?" -> {"catalog_version":"{VERSION}","intent":"answer","domain":"acquisition","metrics":["acq.new_mrr_per_month","acq.run_rate_per_won","acq.payback_months"],"derived_op":"lever_scenario","baseline_period":"from_2023_06","ticket_pct":10,"dimensions":[],"filters":{"time":{}},"chart":{"type":"table"}}
- "¿Cuál es nuestro LTV?" -> {"catalog_version":"{VERSION}","intent":"out_of_scope","out_of_scope":{"reason_code":"outside_catalog","slots":{"falta":"el LTV","closest":"acq.run_rate_per_won"}}}
"""


def _user_text(question: str, prev: dict | None, errors: list[str] | None, prev_spec: dict | None) -> str:
    parts = [f"Pregunta: {question}"]
    if prev_spec:
        parts.append("Spec anterior: " + json.dumps(prev_spec, ensure_ascii=False))
        if prev and prev.get("summary_es"):
            parts.append("Resumen anterior (sin filas): " + prev["summary_es"][:400])
    if errors:
        parts.append("Tu spec anterior fue rechazada por el validador. Errores: " + "; ".join(errors)[:800] +
                     ". Corrígela usando solo el catálogo.")
    return "\n".join(parts)


FLAT = ("derived_op", "derived_of", "derived_over", "from_period", "to_period", "baseline_period", "ticket_pct",
        "spend_pct", "mix_from_industry", "mix_to_industry", "mix_points")


def to_spec(raw: Any) -> Any:
    """The model's flat derived fields -> the §2.1 `derived` array (nothing else changes)."""
    if not isinstance(raw, dict):
        return raw
    out = {k: v for k, v in raw.items() if k not in FLAT}
    for k in ("filters", "sort", "chart", "out_of_scope", "derived", "metrics", "dimensions"):
        if isinstance(out.get(k), str):  # a JSON-encoded member
            try:
                out[k] = json.loads(out[k])
            except ValueError:
                pass
    op = raw.get("derived_op")
    if op:
        d: dict[str, Any] = {"op": op}
        for src, dst in (("derived_of", "of"), ("derived_over", "over"), ("from_period", "from_period"),
                         ("to_period", "to_period"), ("baseline_period", "baseline_period"),
                         ("ticket_pct", "ticket_pct"), ("spend_pct", "spend_pct")):
            if raw.get(src) not in (None, ""):
                d[dst] = raw[src]
        if raw.get("mix_from_industry"):
            d["mix"] = {"from_industry": raw.get("mix_from_industry"), "to_industry": raw.get("mix_to_industry"),
                        "points": raw.get("mix_points")}
        if op == "rank":  # rank is expressed with sort + limit (§2.2)
            out.setdefault("sort", {"by": d.get("of") or (raw.get("metrics") or [""])[0], "dir": "desc"})
        else:
            out["derived"] = [d]
    if out.get("intent") == "answer":
        out.setdefault("filters", {"time": {}})
        if isinstance(out.get("filters"), dict):
            out["filters"].setdefault("time", {})
        out.setdefault("chart", {"type": "table"})
    return out


def ask_kimi(question: str, ctx: K.Context, prev: dict | None, prev_spec: dict | None, timeout_s: float,
             errors: list[str] | None = None) -> dict:
    tool = bedrock.tool_spec("submit_query_spec", "Envía la query spec de la pregunta (o out_of_scope).",
                             tool_schema())
    return bedrock.call_tool(system_prompt(ctx), _user_text(question, prev, errors, prev_spec), tool,
                             max_tokens=3000, timeout_s=timeout_s, log_event="kimi.spec")


# ---------------------------------------------------------------------------- #
# Plan: spec -> compiled, out of scope, or error                                #
# ---------------------------------------------------------------------------- #

@dataclass
class Outcome:
    status: str                      # answer | out_of_scope | error
    spec: dict | None = None
    compiled: K.Compiled | None = None
    reason_code: str | None = None
    slots: dict = field(default_factory=dict)
    reason_es: str = ""
    kimi_calls: int = 0
    errors: list = field(default_factory=list)


ERROR_REPHRASE = "No pude armar esa consulta; ¿puedes decirlo de otra forma?"


def plan(question: str, role: str, ctx: K.Context, prev: dict | None, deadline: float,
         spec_source: Callable | None = None) -> Outcome:
    """Kimi -> validate -> compile, with one retry on a validator error (§2.3 rule 1)."""
    source = spec_source or ask_kimi
    prev_spec = json.loads(prev["spec"]) if prev and prev.get("spec") else None
    errors: list[str] | None = None
    calls = 0
    for attempt in range(2):
        left = deadline - time.monotonic()
        if left < 4:
            break
        try:
            raw = to_spec(source(question, ctx, prev, prev_spec, min(14.0, left - 3), errors))
            calls += 1
        except bedrock.ModelError as err:
            return Outcome("error", reason_es="No pude interpretar la pregunta ahora. Intenta de nuevo en un momento.",
                           kimi_calls=calls + 1, errors=[err.kind])
        try:
            spec = K.validate(raw)
        except K.CompileError as err:
            errors = err.errors
            continue
        try:
            comp = K.compile_spec(spec, role, ctx)
            return Outcome("answer", spec=spec, compiled=comp, kimi_calls=calls)
        except K.OutOfScope as oos:
            return Outcome("out_of_scope", spec=spec, reason_code=oos.reason_code, slots=oos.slots, kimi_calls=calls)
        except K.CompileError as err:
            errors = err.errors
            continue
    return Outcome("error", reason_es=ERROR_REPHRASE, kimi_calls=calls, errors=errors or ["timeout"])


# ---------------------------------------------------------------------------- #
# Execution: Athena (workgroup finora-dl) or the DQ snapshot                    #
# ---------------------------------------------------------------------------- #

class AthenaError(Exception):
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


_athena = None


def athena():
    global _athena
    if _athena is None:
        _athena = boto3.client("athena")
    return _athena


def start_query(comp: K.Compiled) -> str:
    kw: dict[str, Any] = {"QueryString": comp.sql, "WorkGroup": os.environ.get("ATHENA_WORKGROUP", "finora-dl"),
                          "QueryExecutionContext": {"Database": C.GOLD_DB}}
    if comp.params:
        kw["ExecutionParameters"] = comp.params
    try:
        return athena().start_query_execution(**kw)["QueryExecutionId"]
    except Exception as err:  # noqa: BLE001
        print(json.dumps({"event": "athena_start_failed", "kind": type(err).__name__}))
        raise AthenaError(type(err).__name__) from None


def wait_query(qid: str, deadline: float) -> str:
    """SUCCEEDED, FAILED (or CANCELLED) or RUNNING when the deadline passes."""
    while True:
        st = athena().get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        state = st["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            if state != "SUCCEEDED":
                print(json.dumps({"event": "athena_failed", "state": state,
                                  "reason": (st.get("StateChangeReason") or "")[:300]}))
            return state
        if time.monotonic() >= deadline:
            return "RUNNING"
        time.sleep(POLL_S)


def fetch_rows(qid: str, max_rows: int = K.MAX_ROWS + 1) -> tuple[list[str], list[list]]:
    rows: list[list] = []
    token = None
    while True:
        kw = {"QueryExecutionId": qid, "MaxResults": 1000}
        if token:
            kw["NextToken"] = token
        res = athena().get_query_results(**kw)
        rows += [[c.get("VarCharValue") for c in r["Data"]] for r in res["ResultSet"]["Rows"]]
        token = res.get("NextToken")
        if not token or len(rows) > max_rows:
            break
    if not rows:
        return [], []
    return [h.lower() for h in rows[0]], rows[1: max_rows + 1]


def run_sync(comp: K.Compiled, ctx: K.Context, deadline: float, dq_snapshot: Callable[[], dict]) -> P.Table | None:
    """Run a compiled spec to the end before `deadline` (None if it is still running)."""
    if comp.kind == "dq":
        snap = dq_snapshot()
        _exclusion_rules(comp, snap)
        return P.to_table(comp, comp.columns, K.run_dq(comp, snap))
    qid = start_query(comp)
    if wait_query(qid, deadline) != "SUCCEEDED":
        return None
    header, rows = fetch_rows(qid)
    return P.to_table(comp, header, rows)


def _exclusion_rules(comp: K.Compiled, snap: dict) -> None:
    out: dict[str, list[str]] = {}
    for r in snap.get("rules", []):
        if r.get("action") != "exclude":
            continue
        for ds, res in (r.get("results") or {}).items():
            if (res.get("failed") or 0) > 0:
                out.setdefault(ds, []).append(r["rule_id"])
    comp.plan["exclusion_rules"] = out


# ---------------------------------------------------------------------------- #
# Answer assembly: summary, number check, caveats, evidence                     #
# ---------------------------------------------------------------------------- #

def check_summary(text: str, displays: list[str]) -> list[str]:
    """Every figure in `text` must be one of the displays the template put in
    (plus the fixed "5" of "menos de 5 clientes")."""
    allowed = {F.core(d) for d in displays} | {("5", "")}
    bad = []
    for sp in N.extract(text):
        c = F.core(sp.text)
        if c not in allowed and (c[0], "") not in allowed:
            bad.append(sp.text)
    return bad


def answer_payload(comp: K.Compiled, table: P.Table, ctx: K.Context) -> dict:
    s = P.summarize(comp, table, ctx)
    bad = check_summary(s.text, s.displays)
    if bad:
        print(json.dumps({"event": "summary_number_check_failed", "tokens": bad[:5], "spec_hash": comp.spec_hash}))
        s = P.Summary(text="Ya tengo el resultado; te lo muestro en el gráfico.", displays=[], source="fallback",
                      caveats_es=s.caveats_es)
    return {"summary_es": s.text, "summary_source": s.source, "caveats_es": s.caveats_es,
            "evidence": comp.evidence, "kpi_ids": kpi_ids_of(comp, table)}


def kpi_ids_of(comp: K.Compiled, table: P.Table) -> list[str]:
    """DQ cards are per dataset / per rule cell: taken from the rows the answer cites."""
    if comp.kind != "dq":
        return comp.kpi_ids
    rows = [dict(zip(table.columns, r)) for r in table.rows][:6]
    if comp.plan.get("family") == "rule":
        return [f"dq.rule_cell.{r['rule']}.{r['dataset']}" for r in rows]
    return list(dict.fromkeys(f"dq.scorecard.{r['dataset']}" for r in rows))


def oos_payload(outcome: Outcome, role: str, ctx: K.Context, run_alt: Callable[[dict], P.Table | None]) -> dict:
    """reason_es + alternative_es from the §3 templates. Figures in the alternative
    come from running its spec (run_alt), never from the model."""
    code = outcome.reason_code
    rid, reason, alt = C.OOS[code]
    slots = outcome.slots or {}
    dct_es = F.month_es(ctx.data_complete_through)
    fill: dict[str, str] = {"dct_es": dct_es}
    if code == "beyond_data_complete_through":
        asked = str(slots.get("asked") or "")
        fill["asked_es"] = F.month_es(asked) if K.MONTH.fullmatch(asked) else (asked or "ese periodo")
        fill["latest"] = ""
        spec = outcome.spec or {}
        if spec.get("metrics") and all(m in C.METRICS for m in spec["metrics"]):
            alt_spec = {**{k: v for k, v in spec.items() if k != "out_of_scope"}, "intent": "answer",
                        "catalog_version": C.VERSION}
            alt_spec["filters"] = {**(spec.get("filters") or {}), "time": {"relative": "latest_month"}}
            alt_spec.pop("derived", None)
            alt_spec.setdefault("chart", {"type": "kpi"})
            alt_spec.setdefault("dimensions", [])
            alt_spec.setdefault("domain", C.METRICS[spec["metrics"][0]].domain)
            try:
                comp = K.compile_spec(K.validate(alt_spec), role, ctx)
                table = run_alt(comp)
                if table is not None and table.rows:
                    s = P.summarize(comp, table, ctx)
                    if not check_summary(s.text, s.displays):
                        fill["latest"] = " " + s.text
            except (K.CompileError, K.OutOfScope, AthenaError):
                pass
    if code == "causal_spend_won":
        fill.update({"signals": "", "tests": "", "expected": ""})
        alt_text = alt
        try:
            comp = K.compile_spec(K.validate({"catalog_version": C.VERSION, "intent": "answer", "domain": "acquisition",
                                              "metrics": ["acq.corr_signals"], "dimensions": [],
                                              "filters": {"time": {}}, "chart": {"type": "table"}}), role, ctx)
            table = run_alt(comp)
            row = next((dict(zip(table.columns, r)) for r in (table.rows if table else [])
                        if dict(zip(table.columns, r)).get("method") == "diff"), None)
            if row:
                fill.update({"signals": F.display(row["signals"], "int"), "tests": F.display(row["tests_with_r"], "int"),
                             "expected": F.display(row["expected_by_chance"], "dec1")})
        except (K.CompileError, K.OutOfScope, AthenaError):
            row = None
        if not row:
            alt_text = "Puedo mostrarte cómo cambiaría el costo por cliente nuevo y el payback si cambia el gasto, con los clientes nuevos fijos, o la prueba de correlaciones."
        alt = alt_text
    if code == "discounts_billing":
        fill["dip"] = ""
        try:
            comp = K.compile_spec(K.validate({"catalog_version": C.VERSION, "intent": "answer", "domain": "mrr",
                                              "metrics": ["mrr.temporary_dip"], "dimensions": [],
                                              "filters": {"time": {}}, "chart": {"type": "kpi"}}), role, ctx)
            table = run_alt(comp)
            if table and table.rows:
                r = dict(zip(table.columns, table.rows[0]))
                fill["dip"] = (f": {F.display(r['temporary_dip_events'], 'int')} caídas temporales que suman "
                               f"{F.display(abs(F.dec(r['temporary_dip_value'])), 'money')}")
        except (K.CompileError, K.OutOfScope, AthenaError):
            pass
    if code == "customer_level":
        fill["per_customer"] = ""
        try:
            comp = K.compile_spec(K.validate({"catalog_version": C.VERSION, "intent": "answer", "domain": "mrr",
                                              "metrics": ["mrr.per_paying_customer"], "dimensions": ["industry"],
                                              "filters": {"time": {"relative": "latest_month"}},
                                              "chart": {"type": "bar"}}), role, ctx)
            table = run_alt(comp)
            rows = [dict(zip(table.columns, r)) for r in (table.rows if table else [])]
            if rows:
                tot_mrr = sum(F.dec(r["mrr_closing_value"]) or 0 for r in rows)
                tot_n = sum(F.dec(r["paying_customers"]) or 0 for r in rows)
                named = [r for r in rows if r.get("industry") not in ("UNKNOWN", "UNMAPPED") and
                         r.get("is_small_cell") != "true" and r.get("mrr_per_customer_value")]
                top = max(named, key=lambda r: F.dec(r["mrr_per_customer_value"])) if named else None
                if tot_n:
                    fill["per_customer"] = f": el MRR por cliente es {F.display(F.q(tot_mrr / tot_n, 2), 'money')}"
                    if top:
                        fill["per_customer"] += (f" y la industria con el promedio más alto es "
                                                 f"{C.INDUSTRIES[top['industry']]}, con "
                                                 f"{F.display(top['mrr_per_customer_value'], 'money')}")
        except (K.CompileError, K.OutOfScope, AthenaError):
            pass
    if code == "outside_catalog":
        closest = str(slots.get("closest") or "")
        fill["falta"] = str(slots.get("falta") or "ese dato")
        fill["closest"] = C.METRICS[closest].name_es if closest in C.METRICS else \
            "una métrica del catálogo, como los clientes nuevos, el ticket inicial o el MRR"
    if code == "hr_restricted" and role == "finance":
        alt = C.OOS_HR_FINANCE_ALT
    if code == "single_person_pay" and role == "finance":
        alt = C.OOS_PAY_FINANCE_ALT
    reason_es = _fill(reason, fill)
    alternative_es = _fill(alt, fill)
    for txt in (reason_es, alternative_es):
        if re.search(r"\{[a-z_]+\}", txt):
            raise ValueError("unfilled slot")
    return {"reason_code": code, "rule_id": rid, "reason_es": reason_es, "alternative_es": alternative_es,
            "evidence": "no probado" if code == "causal_spend_won" else
            "supuesto" if code == "funnel_stage_observed" else "inferido" if code == "discounts_billing" else
            "observado"}


def _fill(t: str, fill: dict) -> str:
    out = t
    for k, v in fill.items():
        out = out.replace("{" + k + "}", v)
    return out
