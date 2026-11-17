"""The governed catalog `sl-2026-11-17` (docs/semantic_layer.md, CDO), as code.

Everything the compiler may emit is here: the sources (gold tables and views, their
allowed joins, §2.3 rule 2), the dimensions and their columns per source, and the
metric bindings (the SQL fragments are catalog text, owned and reviewed like code;
no model text ever becomes SQL). The DQ metrics bind to the DQ serving snapshot
(§1.3), not to SQL. Where this file and docs/semantic_layer.md disagree, the doc
wins and this file is the one to fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VERSION = "sl-2026-11-17"
ROLES = ("data", "finance", "revops")
GOLD_DB = "finora_gold"
EVIDENCE_ORDER = ["observado", "inferido", "supuesto", "no probado"]  # weakest last
EVIDENCE_SPOKEN = {"observado": "según los datos", "inferido": "es una estimación a partir de los pagos",
                   "supuesto": "con las tasas supuestas, no observadas",
                   "no probado": "no está probado con estos datos"}

# ---------------------------------------------------------------------------- #
# Dimension members (§1.2)                                                      #
# ---------------------------------------------------------------------------- #

INDUSTRIES = {"RESTAURANTS": "Restaurantes", "MANUFACTURING": "Producción", "RETAIL": "Retail",
              "TECHNOLOGY": "Tecnología", "PROFESSIONAL_SERVICES": "Servicios profesionales",
              "HEALTHCARE": "Salud", "UNKNOWN": "Sin industria", "UNMAPPED": "Sin industria"}
SPEND_CATEGORIES = {"PaidMedia": "medios digitales pagados", "PublicidadNoWeb": "publicidad no web",
                    "Travel": "viajes", "SoftwareTools": "herramientas de software",
                    "Team": "equipo", "PayrollExpenses": "gastos de nómina", "Freelance": "freelance"}
HR_CATEGORIES = {"Team", "PayrollExpenses", "Freelance"}
SPEND_GROUPS = {"media": "medios", "other": "otros", "people": "personas"}
STAGES = {"NEW": "nuevo", "WORKING": "en gestión", "ENGAGED": "comprometido", "SQL": "SQL", "DEMO": "demo",
          "PROPOSAL": "propuesta", "WON": "ganado"}
DATASETS = {"transactions": "Transacciones", "industry": "Industria", "sm_spend": "Gasto S&M"}
MRR_LINES = {"opening": "MRR inicial", "new": "nuevos", "reactivation": "reactivaciones", "expansion": "expansión",
             "contraction": "contracción", "churn": "bajas", "pause": "pausas", "resume": "reanudaciones",
             "grace_drop": "en gracia", "list_price_change": "cambio de precio de lista",
             "inferred_price_step": "cambio de precio inferido", "discount_start": "inicio de descuento",
             "discount_change": "cambio de descuento", "discount_base_effect": "efecto base de descuento",
             "discount_end": "fin de descuento", "discount_released_on_churn": "descuento liberado por baja",
             "first_payment_multiple": "primer pago múltiple", "closing": "MRR al cierre",
             "timing_arrears": "pagos atrasados", "timing_prepay": "pagos adelantados",
             "timing_split": "pagos repartidos", "timing_uneven_split": "pagos repartidos desiguales",
             "timing_late_price_step": "cambio de precio tardío", "collected": "cobrado"}
MRR_LINES_NA = {"list_price_change", "discount_start", "discount_change", "discount_base_effect", "discount_end",
                "discount_released_on_churn"}  # lines 9, 11-15: NULL on cash_proxy -> OOS-03
DRIVERS = {"behaviour": "comportamiento de clientes", "pricing": "precios (inferido)", "timing": "tiempo de cobro",
           "discount": "descuentos"}
CUSTOMER_SCOPES = {"won": "clientes ganados desde feb 2022", "left_censored": "clientes que ya pagaban en ene 2022",
                   "all": "todos"}
PERIODS = {"pre_2023_06": "feb 2022 – may 2023", "from_2023_06": "jun 2023 – oct 2024"}
RULE_STATUS_ES = {"pass": "pasa", "warn": "advertencia", "fail": "falla", "na": "no aplica"}

DIMENSIONS = {
    "month": "mes", "quarter": "trimestre", "year": "año", "period": "periodo", "cohort_half": "cohorte semestral",
    "industry": "industria", "spend_category": "categoría de gasto", "spend_group": "grupo de gasto",
    "funnel_stage": "etapa del embudo", "rule": "regla", "dataset": "conjunto de datos",
    "mrr_line": "línea del puente de MRR", "driver": "causa del cambio", "customer_scope": "grupo de clientes",
}
TIME_DIMS = ("month", "quarter", "year")

# ---------------------------------------------------------------------------- #
# Sources (§2.3 rule 2: allowed joins only)                                     #
# ---------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Source:
    id: str
    table: str                       # finora_gold.<table>
    alias: str
    view: bool = False               # views cannot be pinned with FOR VERSION AS OF
    joins: tuple = ()                # (table, alias, on_sql, is_view)
    extra_from: str = ""             # e.g. a CROSS JOIN UNNEST owned by the catalog
    time: str = "none"               # month | period | funnel_period | cohort | none
    dims: dict = field(default_factory=dict)      # dim_id -> (code_expr, label_expr | None)
    filters: dict = field(default_factory=dict)   # filter key -> column expr
    grain: tuple = ()                # pre-aggregated grain: these dims are always in the output
    won_col: str | None = None       # the won_definition column (lever, funnel, correlation tables)
    mandatory: tuple = ()            # conditions the spec cannot remove (catalog text)
    customer_grain: bool = False


_MONTH_JOIN = lambda a: ("dim_month", "m", f"{a}.month_key = m.month_key", False)  # noqa: E731
_IND_JOIN = lambda a: ("dim_industry", "i", f"{a}.industry_key = i.industry_key", False)  # noqa: E731
_MONTH_DIMS = {"month": ("m.month", None), "quarter": ("m.year_quarter", None), "year": ("m.year", None),
               "period": ("m.sm_regime", None)}
_IND_DIM = {"industry": ("i.industry_code", "i.industry_label_es")}

SOURCES = {s.id: s for s in [
    Source("acqm", "agg_acquisition_month", "a", joins=(_MONTH_JOIN("a"),), time="month", dims=dict(_MONTH_DIMS)),
    Source("acqg", "agg_acquisition_month", "a", joins=(_MONTH_JOIN("a"),), time="month",
           extra_from="CROSS JOIN UNNEST(ARRAY['media', 'other', 'people'], "
                      "ARRAY[a.spend_media_value, a.spend_other_value, a.spend_people_value]) AS g(spend_group, spend_value)",
           dims={**_MONTH_DIMS, "spend_group": ("g.spend_group", None)}, filters={"spend_group": "g.spend_group"}),
    Source("wmi", "agg_won_month_industry", "w", joins=(_MONTH_JOIN("w"), _IND_JOIN("w")), time="month",
           dims={**_MONTH_DIMS, **_IND_DIM}, filters={"industry": "i.industry_code"}),
    Source("lp", "agg_acq_lever_period", "p", time="period", dims={"period": ("p.period_code", None)},
           grain=("period",), won_col="p.won_definition"),
    Source("li", "agg_acq_lever_industry", "li", joins=(_IND_JOIN("li"),), time="period",
           dims={"period": ("li.period_code", None), **_IND_DIM}, filters={"industry": "i.industry_code"},
           grain=("period", "industry"), won_col="li.won_definition"),
    Source("vc", "agg_acq_value_change", "v", joins=(_IND_JOIN("v"),), time="none", dims=dict(_IND_DIM),
           filters={"industry": "i.industry_code"}, won_col="v.won_definition",
           mandatory=("v.from_period_code = 'pre_2023_06'", "v.to_period_code = 'from_2023_06'")),
    Source("ip", "agg_industry_profile", "ip", joins=(_IND_JOIN("ip"),), time="none",
           dims={**_IND_DIM, "customer_scope": ("ip.customer_scope", None)},
           filters={"industry": "i.industry_code", "customer_scope": "ip.customer_scope"},
           grain=("industry", "customer_scope")),
    Source("cq", "v_acq_cohort_half", "c", view=True, time="cohort", dims={"cohort_half": ("c.cohort_half", None)},
           grain=("cohort_half",), won_col="c.won_definition"),
    # Shared spend: the view is fact_sm_spend partition hr_sensitive = false (rule 5, last bullet).
    Source("ss", "v_sm_spend_shared", "s", view=True,
           joins=(_MONTH_JOIN("s"), ("dim_spend_category", "sc", "s.category_key = sc.category_key", False)),
           time="month", dims={**_MONTH_DIMS, "spend_category": ("sc.category_code", None)},
           filters={"spend_category": "sc.category_code"}, mandatory=("sc.is_hr_sensitive = false",)),
    Source("fp", "v_funnel_period", "f", view=True, time="funnel_period",
           dims={"funnel_stage": ("f.stage_code", None), "period": ("f.period_id", None),
                 "year": ("f.period_id", None), "quarter": ("f.period_id", None)},
           filters={"funnel_stage": "f.stage_code", "scenario_id": "f.scenario_id"}, won_col="f.won_definition"),
    Source("fm", "v_funnel_month", "f", view=True, joins=(_MONTH_JOIN("f"),), time="month",
           dims={**_MONTH_DIMS, "funnel_stage": ("f.stage_code", None)},
           filters={"funnel_stage": "f.stage_code", "scenario_id": "f.scenario_id"}, won_col="f.won_definition"),
    Source("sens", "v_funnel_rate_sensitivity", "r", view=True, time="none",
           dims={"funnel_stage": ("r.from_stage_code", None)}, filters={"funnel_stage": "r.from_stage_code",
                                                                        "scenario_id": "r.scenario_id"},
           grain=("funnel_stage",), won_col="r.won_definition"),
    Source("corr", "v_corr_signal_summary", "cs", view=True, time="none", dims={}, grain=(),
           won_col="cs.won_definition", mandatory=("cs.scope_type = 'company'",)),
    Source("mb", "agg_mrr_bridge_month", "b", joins=(_MONTH_JOIN("b"),), time="month",
           dims={**_MONTH_DIMS, "mrr_line": ("b.line", None), "driver": ("b.driver", None)},
           filters={"mrr_line": "b.line", "driver": "b.driver"}),
    Source("cm", "fact_customer_month_mrr", "f", joins=(_MONTH_JOIN("f"), _IND_JOIN("f")), time="month",
           dims={**_MONTH_DIMS, **_IND_DIM}, filters={"industry": "i.industry_code"}, customer_grain=True),
    Source("mv", "fact_mrr_movement", "mv", joins=(_MONTH_JOIN("mv"), _IND_JOIN("mv")), time="month",
           dims={**_MONTH_DIMS, **_IND_DIM, "mrr_line": ("mv.movement_type", None), "driver": ("mv.driver", None)},
           filters={"industry": "i.industry_code", "mrr_line": "mv.movement_type", "driver": "mv.driver"},
           customer_grain=True),
]}

# Objects the agent role may read (IAM and the compiler's post-check use the same list).
ALLOWED_TABLES = sorted({s.table for s in SOURCES.values()} | {j[0] for s in SOURCES.values() for j in s.joins})
# Gold tables the views above read (Athena needs them for the views; IAM grants them read).
VIEW_BASE_TABLES = ["fact_sm_spend", "dim_funnel_stage", "funnel_conversion_rate", "agg_acquisition_month",
                    "agg_won_spend_lag_corr", "agg_acq_cohort_quality", "dim_month", "dim_spend_category"]

# ---------------------------------------------------------------------------- #
# Metrics (§1.3-1.5)                                                            #
# ---------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Binding:
    source: str
    cols: tuple                      # ((column_name, sql_expr), ...): the first is the metric's value
    kind: str = "flow"               # flow | stock | value (a pre-aggregated row) | ratio | share
    reportable: bool = False         # adds m.is_won_reportable = true (Won metrics)
    needs: tuple = ()                # time modes or dims this binding requires
    customers: str | None = None     # expr counting customers behind a money value (small cells)
    line_filter: str | None = None   # mandatory row filter for this metric (catalog text)


@dataclass(frozen=True)
class Metric:
    id: str
    name_es: str
    definition_es: str
    fmt: str
    unit: str                        # money | count | pct | share | months | dec | label
    evidence: str
    kpi_id: str
    bindings: tuple = ()
    caveats: tuple = ()
    status: str = "available"        # available | not_available | hr | dq
    domain: str = "acquisition"


W = "{won}"  # replaced by won_count / won_new_logo_count (and the revenue twins) per won_definition


def _m(*a, **k) -> Metric:
    return Metric(*a, **k)


METRICS_LIST = [
    # ---- Data quality (§1.3): the DQ snapshot of the same silver run; JSON lookup in code
    _m("dq.row_compliance_pct", "cumplimiento de filas", "Porcentaje de filas del archivo que pasan las reglas que cuentan para el cumplimiento.", "pct_dq", "pct", "observado", "dq.scorecard.<dataset_id>", status="dq", domain="dq"),
    _m("dq.rows_read", "filas leídas", "Filas recibidas en el archivo de esta corrida.", "int", "count", "observado", "dq.scorecard.<dataset_id>", status="dq", domain="dq"),
    _m("dq.rows_excluded", "filas excluidas", "Filas que no entraron a silver por una regla de exclusión.", "int", "count", "observado", "dq.scorecard.<dataset_id>", status="dq", domain="dq"),
    _m("dq.rows_flagged", "filas marcadas", "Filas que siguen en silver con una marca de una regla.", "int", "count", "observado", "dq.scorecard.<dataset_id>", status="dq", domain="dq"),
    _m("dq.rules_failing", "reglas con hallazgos", "Reglas con estado advertencia o falla en el archivo.", "int", "count", "observado", "dq.scorecard.<dataset_id>", status="dq", domain="dq"),
    _m("dq.rule_failed_count", "casos por regla", "Filas o hallazgos que no cumplen una regla, por archivo.", "int", "count", "observado", "dq.rule_cell.<rule_id>.<dataset_id>", status="dq", domain="dq"),
    _m("dq.rule_compliance_pct", "cumplimiento de la regla", "Porcentaje evaluado que cumple la regla.", "pct_dq", "pct", "observado", "dq.rule_cell.<rule_id>.<dataset_id>", status="dq", domain="dq"),
    _m("dq.rule_status", "estado de la regla", "Pasa, advertencia, falla o no aplica, según los umbrales aprobados.", "label", "label", "observado", "dq.rule_cell.<rule_id>.<dataset_id>", status="dq", domain="dq"),
    _m("dq.compliance_trend", "tendencia de calidad", "Cumplimiento de filas de cada archivo en las últimas corridas exitosas.", "pct_dq", "pct", "observado", "dq.scorecard.<dataset_id>", status="dq", domain="dq"),

    # ---- Acquisition (§1.4)
    _m("acq.won_count", "clientes nuevos", "Clientes cuyo primer pago cae en el mes; no cuenta a quienes ya pagaban en enero de 2022.", "int", "count", "observado", "acq.time.new_customers", bindings=(
        Binding("acqm", (("won_count", f"SUM(a.{W})"),), reportable=True),
        Binding("wmi", (("won_count", f"SUM(w.{W})"),), reportable=True),
        Binding("lp", (("won_count", "MAX(p.won_count)"),), kind="value"),
        Binding("li", (("won_count", "MAX(li.won_count)"),), kind="value"),
        Binding("cq", (("won_count", "MAX(c.won_count)"),), kind="value"))),
    _m("acq.won_per_month", "clientes nuevos al mes", "Clientes nuevos divididos por los meses del periodo.", "dec1", "dec", "observado", "acq.lost.new_customers", bindings=(
        Binding("lp", (("won_per_month", "MAX(p.won_per_month)"),), kind="value"),
        Binding("acqm", (("won_per_month", f"ROUND(CAST(SUM(a.{W}) AS DECIMAL(18, 6)) / NULLIF(COUNT_IF(m.is_won_reportable), 0), 6)"),),
                kind="ratio", reportable=True))),
    _m("acq.won_share", "mezcla de industrias", "Parte de los clientes nuevos del periodo que es de cada industria.", "share_pct1", "share", "observado", "acq.lever.mix", bindings=(
        Binding("li", (("won_share", "MAX(li.won_share)"), ("won_count", "MAX(li.won_count)")), kind="value"),)),
    _m("acq.new_revenue", "ingreso nuevo", "Suma de los primeros pagos de los clientes nuevos, tal como se pagaron.", "money", "money", "observado", "acq.monthly_table", caveats=("C-MULT",), bindings=(
        Binding("acqm", (("new_revenue_value", "SUM(a.{rev})"),), reportable=True),
        Binding("wmi", (("new_revenue_value", "SUM(w.{rev})"), ("won_count", f"SUM(w.{W})")), reportable=True,
                customers=f"SUM(w.{W})"))),
    _m("acq.new_revenue_multiple", "primeros pagos múltiples", "Parte del ingreso nuevo que viene de primeros pagos de 2 o 3 meses juntos.", "money", "money", "inferido", "acq.monthly_table", bindings=(
        Binding("acqm", (("new_revenue_multiple_value", "SUM(a.new_revenue_multiple_value)"),), reportable=True),)),
    _m("acq.new_revenue_per_won", "primer pago promedio", "Ingreso nuevo dividido por clientes nuevos.", "money", "money", "observado", "acq.monthly_table", bindings=(
        Binding("acqm", (("new_revenue_per_won_value", f"ROUND(SUM(a.{{rev}}) / NULLIF(SUM(a.{W}), 0), 2)"),), kind="ratio", reportable=True),
        Binding("wmi", (("new_revenue_per_won_value", f"ROUND(SUM(w.{{rev}}) / NULLIF(SUM(w.{W}), 0), 2)"),
                        ("won_count", f"SUM(w.{W})")), kind="ratio", reportable=True, customers=f"SUM(w.{W})"))),
    _m("acq.run_rate_per_won", "ticket inicial", "Pago mensual promedio de un cliente nuevo en sus meses 2 a 4.", "money", "money", "observado", "acq.lost.starting_revenue", caveats=("C-IMMATURE",), bindings=(
        Binding("lp", (("run_rate_value", "MAX(p.run_rate_mrr_per_won_value)"), ("run_rate_customers", "MAX(p.run_rate_customers)")), kind="value"),
        Binding("li", (("run_rate_value", "MAX(li.run_rate_mrr_per_won_value)"), ("run_rate_customers", "MAX(li.run_rate_customers)")),
                kind="value", customers="MAX(li.run_rate_customers)"),
        Binding("cq", (("run_rate_value", "MAX(c.run_rate_mrr_per_won_value)"), ("run_rate_customers", "MAX(c.run_rate_customers)")),
                kind="value", customers="MAX(c.run_rate_customers)"))),
    _m("acq.ticket_change_mix", "efecto mezcla", "Parte del cambio del ticket que viene de cambiar la mezcla de industrias.", "money", "money", "observado", "acq.lost.ticket_by_industry", bindings=(
        Binding("vc", (("mix_value", "ROUND(SUM(v.mix_term_value), 2)"),)),)),
    _m("acq.ticket_change_within", "efecto dentro de cada industria", "Parte del cambio del ticket que ocurre dentro de cada industria.", "money", "money", "observado", "acq.lost.ticket_by_industry", bindings=(
        Binding("vc", (("within_value", "ROUND(SUM(v.within_term_value), 2)"),)),)),
    _m("acq.new_mrr_per_month", "MRR nuevo al mes", "Clientes nuevos al mes por su ticket inicial; es un tope superior, no ingreso facturado.", "money", "money", "inferido", "acq.plan.new_mrr", bindings=(
        Binding("lp", (("new_mrr_per_month_value", "MAX(p.new_mrr_per_month_value)"),), kind="value"),)),
    _m("acq.paying_m6_share", "retención a 6 meses", "De los clientes nuevos observables, cuántos pagan en su sexto mes.", "share_pct1", "share", "observado", "acq.lost.keep_paying", caveats=("C-RETENTION",), bindings=(
        Binding("lp", (("paying_m6_share", "MAX(p.paying_m6_share)"), ("paying_m6_count", "MAX(p.paying_m6_count)"), ("paying_m6_eligible", "MAX(p.paying_m6_eligible)")), kind="value"),
        Binding("li", (("paying_m6_share", "MAX(li.paying_m6_share)"), ("paying_m6_count", "MAX(li.paying_m6_count)"), ("paying_m6_eligible", "MAX(li.paying_m6_eligible)")), kind="value"),
        Binding("cq", (("paying_m6_share", "MAX(c.paying_m6_share)"), ("paying_m6_count", "MAX(c.paying_m6_count)"), ("paying_m6_eligible", "MAX(c.paying_m6_eligible)")), kind="value"))),
    _m("acq.paying_m12_share", "retención a 12 meses", "De los clientes nuevos observables, cuántos pagan en su mes 12.", "share_pct1", "share", "observado", "acq.lost.keep_paying", caveats=("C-RETENTION",), bindings=(
        Binding("lp", (("paying_m12_share", "MAX(p.paying_m12_share)"), ("paying_m12_count", "MAX(p.paying_m12_count)"), ("paying_m12_eligible", "MAX(p.paying_m12_eligible)")), kind="value"),
        Binding("li", (("paying_m12_share", "MAX(li.paying_m12_share)"), ("paying_m12_count", "MAX(li.paying_m12_count)"), ("paying_m12_eligible", "MAX(li.paying_m12_eligible)")), kind="value"),
        Binding("cq", (("paying_m12_share", "MAX(c.paying_m12_share)"), ("paying_m12_count", "MAX(c.paying_m12_count)"), ("paying_m12_eligible", "MAX(c.paying_m12_eligible)")), kind="value"))),
    _m("acq.spend_total", "gasto S&M", "Gasto mensual de ventas y marketing, suma de las 7 categorías, con negativos.", "money", "money", "observado", "acq.time.new_customers", bindings=(
        Binding("acqm", (("spend_total_value", "SUM(a.spend_total_value)"),)),
        Binding("lp", (("spend_total_value", "MAX(p.spend_total_value)"),), kind="value"))),
    _m("acq.spend_per_month", "gasto S&M al mes", "Gasto del periodo dividido por sus meses.", "money", "money", "observado", "acq.lever.spend", bindings=(
        Binding("lp", (("spend_per_month_value", "MAX(p.spend_per_month_value)"),), kind="value"),
        Binding("fp", (("spend_per_month_value", "MAX(f.spend_per_month_value)"),), kind="value", line_filter="f.stage_code = 'WON'"))),
    _m("acq.spend_category", "gasto por categoría", "Gasto de una categoría no sensible.", "money", "money", "observado", "acq.monthly_table", bindings=(
        Binding("ss", (("spend_value", "SUM(s.spend_value)"),)),)),
    _m("acq.spend_group", "gasto por grupo", "Gasto sumado por grupo.", "money", "money", "observado", "acq.monthly_table", bindings=(
        Binding("acqg", (("spend_value", "SUM(g.spend_value)"),)),)),
    _m("acq.spend_hr_category", "gasto de equipo, nómina o freelance", "Gasto de una categoría de personal (sensible).", "money", "money", "observado", "acq.monthly_table", status="hr"),
    _m("acq.cost_per_won", "costo por cliente nuevo", "Gasto S&M del periodo dividido por los clientes nuevos del mismo periodo.", "money", "money", "observado", "acq.funnel.won_cost", caveats=("C-NOT-CAC",), bindings=(
        Binding("lp", (("cost_per_won_value", "MAX(p.cost_per_won_value)"),), kind="value"),
        Binding("fp", (("cost_per_won_value", "MAX(f.cost_per_unit_value)"),), kind="value", line_filter="f.stage_code = 'WON'"),
        Binding("fm", (("cost_per_won_value", "MAX(f.cost_per_unit_value)"),), kind="value", line_filter="f.stage_code = 'WON'", needs=("month",)))),
    _m("acq.payback_months", "payback", "Meses de ticket inicial necesarios para cubrir el gasto S&M por cliente nuevo; ingreso, no margen.", "months1", "months", "inferido", "acq.plan.payback", caveats=("C-PAYBACK",), bindings=(
        Binding("lp", (("payback_months", "MAX(p.payback_months)"),), kind="value"),)),
    _m("acq.avg_monthly_payment", "pago mensual promedio", "Promedio de lo pagado en los meses con pago, por industria y grupo de clientes.", "money", "money", "observado", "acq.industries", bindings=(
        Binding("ip", (("avg_monthly_payment_value", "MAX(ip.avg_monthly_payment_value)"),
                       ("avg_monthly_payment_ex_outlier_value", "MAX(ip.avg_monthly_payment_ex_outlier_value)"),
                       ("customers", "MAX(ip.customers)")), kind="value", customers="MAX(ip.customers)"),)),
    _m("acq.share_months_paid", "constancia de pago", "Meses pagados sobre meses observables; comparable entre cohortes.", "share_pct1", "share", "observado", "acq.industries", bindings=(
        Binding("ip", (("share_months_paid", "MAX(ip.share_of_observable_months_paid)"),), kind="value"),)),
    _m("acq.funnel_stage_count", "clientes por etapa", "Volumen estimado de una etapa: clientes ganados divididos por las tasas supuestas.", "dec1", "dec", "supuesto", "acq.funnel.stages", caveats=("C-FUNNEL",), bindings=(
        Binding("fp", (("stage_count", "MAX(f.stage_count)"),), kind="value"),
        Binding("fm", (("stage_count", "MAX(f.stage_count)"),), kind="value", needs=("month",)))),
    _m("acq.funnel_cost_per_stage", "costo por etapa", "Gasto del periodo dividido por el volumen estimado de la etapa.", "money", "money", "supuesto", "acq.funnel.stages", caveats=("C-FUNNEL",), bindings=(
        Binding("fp", (("cost_per_unit_value", "MAX(f.cost_per_unit_value)"),), kind="value"),
        Binding("fm", (("cost_per_unit_value", "MAX(f.cost_per_unit_value)"),), kind="value", needs=("month",)))),
    _m("acq.rate_sensitivity", "sensibilidad de tasas", "Clientes ganados extra por cada punto de una tasa, por álgebra.", "dec1", "dec", "supuesto", "acq.funnel.sensitivity", caveats=("C-FUNNEL",), bindings=(
        Binding("sens", (("won_change_per_point", "MAX(r.won_change_per_point_full_period)"),
                         ("won_pct_change_per_point", "MAX(r.won_pct_change_per_point)")), kind="value"),)),
    _m("acq.corr_signals", "relación gasto–clientes", "Cuántas pruebas de correlación superan el umbral del 5 %, frente a las esperadas por azar.", "int", "count", "observado", "acq.signals", caveats=("C-CORR",), bindings=(
        Binding("corr", (("signals", "MAX(cs.signals)"), ("tests_with_r", "MAX(cs.tests_with_r)"),
                         ("expected_by_chance", "MAX(cs.expected_by_chance)")), kind="value"),)),

    # ---- MRR (§1.5): every entry carries C-MRR-PROXY
    _m("mrr.closing", "MRR", "Ingreso recurrente mensual al cierre del mes, estimado a partir de los pagos.", "money", "money", "inferido", "mrr.bridge.closing", domain="mrr", bindings=(
        Binding("mb", (("mrr_closing_value", "MAX_BY(b.amount_value, b.month_key) FILTER (WHERE b.line = 'closing')"),), kind="stock"),
        Binding("cm", (("mrr_closing_value", "SUM(f.mrr_value) FILTER (WHERE f.mrr_value > 0)"),), kind="stock",
                customers="COUNT(*) FILTER (WHERE f.mrr_value > 0)"))),
    _m("mrr.opening", "MRR inicial", "MRR al cierre del mes anterior.", "money", "money", "inferido", "mrr.bridge.opening", domain="mrr", bindings=(
        Binding("mb", (("mrr_opening_value", "MIN_BY(b.amount_value, b.month_key) FILTER (WHERE b.line = 'opening')"),), kind="stock"),)),
    _m("mrr.net_change", "cambio del MRR", "MRR de cierre del último mes menos MRR de apertura del primero.", "money", "money", "inferido", "mrr.why.hero", domain="mrr", bindings=(
        Binding("mb", (("mrr_opening_value", "MIN_BY(b.amount_value, b.month_key) FILTER (WHERE b.line = 'opening')"),
                       ("mrr_closing_value", "MAX_BY(b.amount_value, b.month_key) FILTER (WHERE b.line = 'closing')")), kind="stock"),)),
    _m("mrr.line_amount", "movimiento de MRR", "Suma de una línea del puente de MRR en el periodo.", "money", "money", "observado", "mrr.bridge.<line>", domain="mrr", bindings=(
        Binding("mb", (("line_amount_value", "SUM(b.amount_value)"),), line_filter="b.line_order BETWEEN 1 AND 16"),
        Binding("mv", (("line_amount_value", "SUM(mv.amount_value)"), ("customers", "COUNT(DISTINCT mv.customer_id)")),
                customers="COUNT(DISTINCT mv.customer_id)"))),
    _m("mrr.line_events", "número de movimientos", "Número de movimientos de esa línea.", "int", "count", "observado", "mrr.bridge.<line>", domain="mrr", bindings=(
        Binding("mb", (("line_events", "SUM(b.events)"),), line_filter="b.line_order BETWEEN 1 AND 16"),
        Binding("mv", (("line_events", "COUNT(*)"),)))),
    _m("mrr.driver_amount", "cambio por causa", "Cambio del MRR separado por causa.", "money", "money", "inferido", "mrr.why.driver.<driver>", domain="mrr", bindings=(
        Binding("mb", (("driver_amount_value", "SUM(b.amount_value)"),), line_filter="b.line_order BETWEEN 1 AND 16"),)),
    _m("mrr.paying_customers", "clientes pagando", "Clientes con MRR mayor que cero al cierre del mes.", "int", "count", "inferido", "mrr.bridge.closing", domain="mrr", bindings=(
        Binding("mb", (("paying_customers", "MAX_BY(b.events, b.month_key) FILTER (WHERE b.line = 'closing')"),), kind="stock"),
        Binding("cm", (("paying_customers", "COUNT(*) FILTER (WHERE f.mrr_value > 0)"),), kind="stock"))),
    _m("mrr.per_paying_customer", "MRR por cliente", "MRR de cierre dividido por los clientes pagando.", "money", "money", "inferido", "mrr.trend", domain="mrr", bindings=(
        Binding("mb", (("mrr_per_customer_value", "ROUND(MAX_BY(b.amount_value, b.month_key) FILTER (WHERE b.line = 'closing') / "
                                                  "NULLIF(MAX_BY(b.events, b.month_key) FILTER (WHERE b.line = 'closing'), 0), 2)"),), kind="stock"),
        Binding("cm", (("mrr_per_customer_value", "ROUND(SUM(f.mrr_value) FILTER (WHERE f.mrr_value > 0) / "
                                                  "NULLIF(COUNT(*) FILTER (WHERE f.mrr_value > 0), 0), 2)"),
                       ("mrr_closing_value", "SUM(f.mrr_value) FILTER (WHERE f.mrr_value > 0)"),
                       ("paying_customers", "COUNT(*) FILTER (WHERE f.mrr_value > 0)")), kind="stock",
                customers="COUNT(*) FILTER (WHERE f.mrr_value > 0)"))),
    _m("mrr.collected", "cobrado", "Lo pagado en el mes, tal como llegó.", "money", "money", "observado", "mrr.monthly_table", domain="mrr", bindings=(
        Binding("mb", (("collected_value", "SUM(b.amount_value) FILTER (WHERE b.line = 'collected')"),)),)),
    _m("mrr.timing_adjustment", "efecto de tiempo de cobro", "Diferencia entre lo cobrado y el MRR, por pagos atrasados, adelantados o repartidos.", "money", "money", "inferido", "mrr.bridge.timing", domain="mrr", bindings=(
        Binding("mb", (("timing_value", "SUM(b.amount_value)"),), line_filter="b.line_order BETWEEN 20 AND 24"),)),
    _m("mrr.temporary_dip", "caídas temporales", "Contracciones que vuelven al monto anterior en 1 a 3 meses: la huella que dejaría un descuento.", "money", "money", "inferido", "mrr.bridge.contraction", domain="mrr", bindings=(
        Binding("mv", (("temporary_dip_value", "SUM(mv.amount_value)"), ("temporary_dip_events", "COUNT(*)"),
                       ("customers", "COUNT(DISTINCT mv.customer_id)")),
                customers="COUNT(DISTINCT mv.customer_id)", line_filter="mv.is_temporary_dip = true"),)),
    _m("mrr.one_off_spike", "picos puntuales", "Expansiones que vuelven al monto anterior en 1 a 3 meses.", "money", "money", "inferido", "mrr.bridge.expansion", domain="mrr", bindings=(
        Binding("mv", (("one_off_spike_value", "SUM(mv.amount_value)"), ("one_off_spike_events", "COUNT(*)"),
                       ("customers", "COUNT(DISTINCT mv.customer_id)")),
                customers="COUNT(DISTINCT mv.customer_id)", line_filter="mv.is_one_off_spike = true"),)),
    _m("mrr.discount_leakage", "fuga por descuentos", "Precio de lista menos lo cobrado por descuentos.", "money", "money", "inferido", "mrr.leakage", status="not_available", domain="mrr"),
    _m("mrr.list_mrr", "MRR de lista", "Valor de suscripción a precio de lista.", "money", "money", "inferido", "mrr.leakage", status="not_available", domain="mrr"),
    _m("mrr.net_mrr", "MRR neto", "Valor de suscripción después de descuentos.", "money", "money", "inferido", "mrr.leakage", status="not_available", domain="mrr"),
]
METRICS = {m.id: m for m in METRICS_LIST}

# Spoken synonyms for Kimi's catalog view (§1.3-1.5 "Nombre (sinónimos)").
SYNONYMS = {
    "dq.row_compliance_pct": "calidad, salud de los datos, % de filas buenas", "dq.rows_excluded": "descartadas, en cuarentena",
    "dq.rule_failed_count": "errores, hallazgos", "dq.rule_status": "verde, amarillo, rojo",
    "dq.compliance_trend": "evolución, últimas corridas",
    "acq.won_count": "ganados, altas, nuevos clientes, adquisiciones, logos nuevos", "acq.won_per_month": "ritmo de altas, promedio mensual",
    "acq.won_share": "participación, peso de cada industria", "acq.new_revenue": "primeros pagos, ingreso de clientes nuevos",
    "acq.new_revenue_multiple": "pagos dobles o triples al entrar", "acq.new_revenue_per_won": "ingreso nuevo por cliente",
    "acq.run_rate_per_won": "pago mensual de un cliente nuevo, ticket, cuánto paga un cliente nuevo",
    "acq.ticket_change_mix": "cambio por mezcla de industrias", "acq.new_mrr_per_month": "ingreso recurrente nuevo mensual",
    "acq.paying_m6_share": "siguen pagando al mes 6", "acq.paying_m12_share": "siguen pagando al año",
    "acq.spend_total": "gasto de ventas y marketing, inversión comercial, presupuesto de marketing",
    "acq.spend_category": "pauta, publicidad offline, viajes, software", "acq.spend_group": "medios, personas, otros",
    "acq.cost_per_won": "gasto S&M por cliente ganado, CAC (se responde con esta métrica y C-NOT-CAC)",
    "acq.payback_months": "meses para recuperar, recuperación de la inversión", "acq.avg_monthly_payment": "ARPPU por industria, ticket promedio de la base",
    "acq.share_months_paid": "porcentaje de meses pagados", "acq.funnel_stage_count": "leads, SQL, demos, propuestas estimadas",
    "acq.funnel_cost_per_stage": "costo por lead, por SQL", "acq.rate_sensitivity": "qué tasa mueve más",
    "acq.corr_signals": "correlaciones, señales", "mrr.closing": "ingreso recurrente mensual, MRR al cierre, cuánto factura la base al mes",
    "mrr.net_change": "crecimiento, cuánto creció", "mrr.line_amount": "MRR nuevo, perdido por bajas, expansión, contracción",
    "mrr.line_events": "cuántas bajas, cuántas altas", "mrr.driver_amount": "comportamiento, precios, tiempo de cobro",
    "mrr.paying_customers": "base activa, clientes con MRR", "mrr.per_paying_customer": "ticket promedio de la base, ARPPU",
    "mrr.collected": "caja del mes, pagos recibidos", "mrr.timing_adjustment": "pagos atrasados o adelantados",
    "mrr.temporary_dip": "bajas de pago que vuelven", "mrr.one_off_spike": "cobros extra que no se repiten",
}

# ---------------------------------------------------------------------------- #
# Out-of-scope rules (§3) and caveats (§2.3 rule 8)                            #
# ---------------------------------------------------------------------------- #

OOS = {
    "causal_spend_won": ("OOS-01", "Con estos datos no se puede medir cuántos clientes trae el gasto: no hay datos por canal ni campaña, y las correlaciones sin tendencia salen al nivel del azar.",
                         "Puedo mostrarte cómo cambiaría el costo por cliente nuevo y el payback si cambia el gasto, con los clientes nuevos fijos, o la prueba de correlaciones: {signals} de {tests} pruebas, frente a {expected} esperadas por azar."),
    "funnel_stage_observed": ("OOS-02", "No hay datos de etapas antes del primer pago: solo se observa 'ganado'. Las etapas del embudo son estimaciones con tasas supuestas.",
                              "Puedo mostrarte el embudo estimado con las tasas supuestas, o qué tasa movería más clientes por álgebra, marcado como supuesto."),
    "discounts_billing": ("OOS-03", "Los descuentos aún no se pueden medir: faltan los datos de facturación con precio de lista y descuento.",
                          "Puedo darte las caídas temporales de pago que vuelven al monto anterior en 1 a 3 meses, que es la huella que dejaría un descuento, marcado como inferido{dip}."),
    "currency": ("OOS-04", "La moneda no está confirmada por Finanzas; los montos están en unidades completas y no los puedo convertir.",
                 "Puedo darte la misma cifra en unidades completas, o una medida sin moneda como el payback en meses o el cambio en porcentaje."),
    "single_person_pay": ("OOS-05", "No tengo datos por persona y no doy montos que puedan revelar el pago de alguien.",
                          "Puedo darte el gasto total de S&M o el de medios."),
    "beyond_data_complete_through": ("OOS-06", "Los datos llegan hasta {dct_es}; no tengo {asked_es} todavía.",
                                     "Puedo darte {dct_es}, el último mes completo, o la tendencia de los últimos 12 meses.{latest}"),
    "customer_level": ("OOS-07", "Por privacidad no doy datos de clientes individuales.",
                       "Puedo darte el MRR promedio por cliente o el reparto por industria{per_customer}. El detalle por cliente está en la tabla 'Top movers' de la página de MRR, con tu sesión."),
    "dq_record_level": ("OOS-08", "No leo registros individuales; contienen datos de origen.",
                        "Te digo cuántos casos tiene la regla y abro la tabla de reglas para que veas los registros."),
    "hr_restricted": ("OOS-09", "Ese gasto es información de personal y solo Finanzas puede verlo.",
                      "Puedo darte el gasto total de S&M, el de medios o el total de personal sin desglose."),
    "forecast": ("OOS-10", "No hago proyecciones: solo respondo con datos observados o con escenarios de las palancas.",
                 "Puedo calcular un escenario con las palancas de ticket, mezcla o gasto sobre el periodo actual."),
    "outside_catalog": ("OOS-11", "Ese dato no está en el modelo: {falta}.",
                        "Puedo darte {closest}."),
}
OOS_HR_FINANCE_ALT = "Puedo darte el gasto total de S&M o el total de personal sin desglose; el detalle ábrelo en la tabla mensual de Adquisición."
OOS_PAY_FINANCE_ALT = "Puedo mostrarte el gasto total de personal de S&M en el gráfico."

CAVEATS = {
    "C-CUR": "Los montos están en unidades completas; la moneda no está confirmada.",
    "C-MRR-PROXY": "El MRR se calcula a partir de los pagos, no de la facturación.",
    "C-PROV": "Las bajas de los dos últimos meses son provisionales.",
    "C-FUNNEL": "Las etapas antes de 'ganado' son estimaciones con tasas supuestas; no están en los datos.",
    "C-NOT-CAC": "Es gasto de S&M por cliente nuevo, no un CAC: el gasto parece presupuesto y no se asigna por canal.",
    "C-PAYBACK": "Es un payback simple sobre ingreso, no sobre margen, y supone que el cliente no se va.",
    "C-REGIME": "El corte de junio de 2023 es una referencia inferida, no la causa del cambio.",
    "C-IMMATURE": "Los clientes de los últimos 3 meses aún no tienen ticket medible.",
    "C-MULT": "Incluye primeros pagos dobles o triples; son el {mult_pct} del ingreso nuevo.",
    "C-RETENTION": "Cuenta solo a quien pagó ese mes; es un mínimo, no la tasa de bajas.",
    "C-CORR": "Una correlación no prueba causa.",
    "C-PEOPLE": "Es el total de personal; no se desglosa por categoría.",
    "C-LOWN": "Hay pocos casos (menos de 10); tómalo con cautela.",
    "C-OUTLIER": "Dos clientes atípicos suben el promedio de Restaurantes; sin ellos es {ex_outlier}.",
    "C-PARTIAL": "{partial}",
    "C-MIX": "Supone que cada industria mantiene su ticket y que ese volumen se gana al mismo costo.",
}
CAVEAT_ORDER = list(CAVEATS)  # the order of the doc's table; C-CUR is moved last when spoken
