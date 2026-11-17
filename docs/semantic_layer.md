# Semantic layer for the voice agent (catalog `sl-2026-11-17`)

Owner: CDO. Date: 2026-11-17. Status: **approved by the CDO for the CTO to build**. It is the governed catalog behind `contracts/agent_api_contract.md` (v1), §§ "POST /api/agent/ask" and "GET /api/agent/briefing". It follows the reference (`docs/aws_architecture/data-lake-voice-dashboard-architecture.html`, §§ 05, 06, 09, 10), with **Kimi K3 on Bedrock (us-east-1, `us.moonshotai.kimi-k3`)** in place of Claude, the ElevenLabs-hosted conversation LLM, and **Spanish only**.

**Sources of meaning.** Owner definitions `docs/data_semantics/owner_definitions.md` (revenue × 10,000; S&M × 100,000,000; currency not stated). Gold acquisition `docs/gold_acquisition_model.md` (§3 definitions, §5 tables, §7 views, §9 access, §16 levers). Gold MRR `docs/mrr_discounts_model.md` §6 (proposed; built with `mrr_basis = 'cash_proxy'`). DQ `contracts/dq_api_contract.md` and the serving snapshot. Nothing here changes a definition in those documents. Where this file and one of them disagree, the source document wins and this file is the one to fix.

**Verification.** Every expected figure was checked on 2026-11-17 in two ways. First, with the local golden build: the silver engine `etl/tests/golden_helpers.py` `run()`, then the gold engines `gold_build.engine` and `gold_mrr.engine` through `etl/tests/gold_helpers.py` on `data/*.csv`. Second, against the live run reports of gold run `r20261117T201211Z` (`s3://al-test-dl-gold/_runs/…/gold_report.json` and `mrr_report.json`) and the DQ snapshot `s3://al-test-dl-serving/dq/runs/r20261117T201211Z/summary.json`, both read-only. They match: Won 1,584, new logos 1,541, new revenue 105,482,511.96, Won-month spend 7,581,800,000, MRR opening 3,500.030835 and closing 9,636.064683 native. No HR-sensitive amount is reproduced in this file.

---

## 0. Principles (what the layer guarantees)

1. **No model writes SQL.** Kimi K3 fills the query spec (§2) through one tool-use schema. Code validates the spec and compiles it (sqlglot, Trino dialect) into **one SELECT** over the sources named in this catalog.
2. **No number comes from the model.** Every figure in `summary_es` and in the briefing is formatted by code from a result row or a KPI-table value. Kimi chooses and phrases; code fills the numbers and checks them (§4.4).
3. **No rows go to the agent.** The agent (ElevenLabs) receives `summary_es`, the IDs, the caveats and the evidence level. Rows go only to the browser, through `GET /api/agent/results/{id}` with the user's own session.
4. **What Kimi receives.** It gets the question, the matching catalog entries (§1), and the previous result's spec and `summary_es`. It never receives rows, customer IDs or HR-sensitive values.
5. **Access is enforced in the compiler, from the token's role, never from the prompt.** The roles are `data`, `finance` and `revops` (CDO-11(1)). HR-sensitive amounts (Team, PayrollExpenses, Freelance) are Finance-only. They are **never spoken and never in the briefing** (§2.3 rule 7).
6. **Third-party minimization.** ElevenLabs stores transcripts and tool results, so whatever reaches the agent is retained outside AWS. The agent therefore receives only company-level or segment aggregates. It never receives a customer-level value, a cell built from fewer than 5 customers, or an HR amount. Retention stays at the plan minimum (contract).

**Evidence levels** (labels used in every entry, and spoken with the reference's decision-first rules, `docs/gold_acquisition_model.md` §16):

| Level | Meaning | Spoken as |
|---|---|---|
| `observado` | Counted or summed directly from the files (Won, spend, DQ counts) | "según los datos" |
| `inferido` | Derived by an approved but inferred rule: settlements (SB-06/CRO-03), cash-proxy MRR, the `sm_regime` periods, the GLD-MRR rules | "es una estimación a partir de los pagos" |
| `supuesto` | Arithmetic on user-owned assumptions: funnel stages before Won, conversion lever | "con las tasas supuestas, no observadas" |
| `no probado` | A relationship the data does not support: spend → Won | "no está probado con estos datos" |

---

## 1. The governed catalog

### 1.0 Global context (resolved by the compiler, never by the model)

| Item | Source | Today |
|---|---|---|
| `gold_run_id` | `finora_gold.gold_build_status._run_id` of the published build | `r20261117T201211Z` |
| `dq_run_id` | `gold_build_status._silver_run_id`. DQ answers use the DQ snapshot of the **same** silver run, so gold and DQ answers never mix runs | `r20261117T201211Z` |
| `data_complete_through` | `gold_build_status.data_complete_through` | `2024-10` |
| `window_start_month` | `gold_build_status.window_start_month` | `2022-01` (Won excludes it: left-censored) |
| `churn_confirmed_through` | silver SB-05 (`as_of_month` − 2) | `2024-08`. 2024-09 and 2024-10 are provisional |
| Statuses | `currency_status`, `revenue_basis_status`, `spend_basis_status`, `scope_status` | all `unconfirmed`; `mrr_basis` = `cash_proxy`; `discount_data_status` = `not_available` |

### 1.1 Display formats (`fmt`), used by summaries, the briefing and the number check

All rounding is HALF_UP from the exact decimal string. The thousands separator is "." and the decimal separator is ",". Years and month names are never separated or checked as numbers.

| `fmt` | Rule | Examples |
|---|---|---|
| `int` | Integer, "." thousands | 1.584 · 50 |
| `dec1` | 1 decimal | 57,5 · 71,6 |
| `money` | \|x\| < 1.000.000: whole units ("42.551"). 1.000.000 ≤ \|x\| < 10.000.000: millions with 2 decimals. \|x\| ≥ 10.000.000: millions with 1 decimal. **Spoken and in `text_es`/`summary_es`: "millones". Chart labels and `title_es`: "M"** | 42.551 · 3,05 millones · 96,4 millones · 1.975,5 millones (chart: 96,4 M) |
| `pct0` | Whole percent, a space then "%" | 52 % |
| `pct1` | 1 decimal | 90,0 % · 24,4 % |
| `pct_dq` | Up to 2 decimals, trailing zeros removed | 99,95 % · 100 % |
| `share_pct1` | A 0–1 share × 100, 1 decimal | 0,8997 → 90,0 % |
| `months1` | 1 decimal + "meses" | 71,6 meses |
| `r4` | Correlation, 4 decimals, sign kept | −0,4795 |

Negative amounts are spoken as their absolute value with a direction word: bajó, cayó, restó, perdimos, salió. The sign is carried by that verb (§4.4 check 4).

### 1.2 Dimensions (shared and domain)

| `dim_id` | Nombre (sinónimos hablados) | Source column | Allowed values (Spanish label = how the agent says it) | Notes |
|---|---|---|---|---|
| `month` | mes (mensual, por mes) | `dim_month.month` (`month_key` for joins) | `2022-01` → `data_complete_through` | Won metrics start at 2022-02 (`is_won_reportable`) |
| `quarter` | trimestre (Q1…Q4) | `dim_month.year_quarter` | `2022-Q1` … | 2022-Q1 has 2 Won months; 2024-Q4 has 1 (partial: caveat C-PARTIAL) |
| `year` | año (anual) | `dim_month.year` | 2022 (11 Won months), 2023, 2024 (10) | Partial years carry C-PARTIAL |
| `period` | periodo (antes / desde junio de 2023; "el periodo actual" = `from_2023_06`) | `period_code` of the lever tables; `v_funnel_period.period_type = 'sm_regime'` | `pre_2023_06` "feb 2022 – may 2023", `from_2023_06` "jun 2023 – oct 2024" | **Inferred** (CMO-08, §8.11): a baseline, never a cause. Caveat C-REGIME |
| `cohort_half` | cohorte semestral (primer/segundo semestre) | `v_acq_cohort_half.cohort_half` | `2022-H1` … `2024-H2` | 2024-H2 is immature for the run-rate (C-IMMATURE) |
| `industry` | industria (sector, rubro, vertical, segmento, tipo de negocio) | `dim_industry.industry_key`; label `industry_label_es` | RESTAURANTS "Restaurantes" (restaurantes, comida); MANUFACTURING "Producción" (manufactura, fábricas, industria manufacturera); RETAIL "Retail" (comercio, tiendas, minoristas); TECHNOLOGY "Tecnología" (tech, software); PROFESSIONAL_SERVICES "Servicios profesionales" (consultoras, despachos); HEALTHCARE "Salud" (clínicas, consultorios); UNKNOWN / UNMAPPED "Sin industria" | Codes and English labels are inferred conventions (SQ-04). Never joined to spend (CDO-10) |
| `spend_category` | categoría de gasto (rubro de gasto, partida) | `dim_spend_category.category_code` | PaidMedia "medios digitales pagados" (pauta, ads, anuncios en línea); PublicidadNoWeb "publicidad no web" (offline, ATL, radio, vallas); Travel "viajes"; SoftwareTools "herramientas de software"; **HR (Finance only):** Team "equipo", PayrollExpenses "gastos de nómina", Freelance "freelance" | Hierarchy inferred (GLD-04). `is_hr_sensitive` drives access |
| `spend_group` | grupo de gasto | `dim_spend_category.spend_group` | `media` "medios", `other` "otros", `people` "personas" | `people` is the **total** of the HR categories: all three roles may read it (decision A1). It is never in the briefing |
| `funnel_stage` | etapa del embudo (fase, paso) | `dim_funnel_stage.stage_code` | NEW "nuevo/lead", WORKING "en gestión", ENGAGED "comprometido", SQL "SQL", DEMO "demo", PROPOSAL "propuesta", WON "ganado" | Only WON is observed. Every other stage is `supuesto` (§3 OOS-02) |
| `rule` | regla (control, validación, chequeo) | DQ `rules[].rule_id` and `title` | The 28 rule ids of the run (for example SQ-02 "Empty records", SB-10 "Negative spend") | Spoken with the id and a Spanish gloss of the title |
| `dataset` | conjunto de datos (fuente, archivo, tabla) | DQ `datasets[].dataset_id` | `transactions` "Transacciones" (pagos, ingresos), `industry` "Industria", `sm_spend` "Gasto S&M" (gasto comercial) | Labels as in the DQ contract (from config) |
| `mrr_line` | línea del puente de MRR | `agg_mrr_bridge_month.line`, `dim_movement_type` | new "nuevos", reactivation "reactivaciones", expansion "expansión", contraction "contracción", churn "bajas", pause "pausas", resume "reanudaciones", grace_drop "en gracia", inferred_price_step "cambio de precio inferido", first_payment_multiple "primer pago múltiple", timing_* "efecto de tiempo de cobro" | Lines 9 and 11–15 (list price, discounts) are NULL on `cash_proxy` and route to OOS-03 |
| `driver` | causa del cambio (motor) | `agg_mrr_bridge_month.driver` | behaviour "comportamiento de clientes", pricing "precios (inferido)", timing "tiempo de cobro", discount "descuentos" (not available) | |
| `customer_scope` | grupo de clientes | `agg_industry_profile.customer_scope` | `won` "clientes ganados desde feb 2022", `left_censored` "clientes que ya pagaban en ene 2022", `all` "todos" | |

`won_definition` is a parameter, not a dimension. `first_payment` (default) is "todos los primeros pagos". `new_logo` is "sin los clientes probablemente ya activos" (synonyms: nuevos logos, solo logos nuevos, definición canónica).

### 1.3 Data quality (`finora_dq` and the DQ serving snapshot)

**Source:** `s3://al-test-dl-serving/dq/runs/<dq_run_id>/summary.json` (the snapshot; JSON lookup in code, no SQL). Fallback: `finora_dq.findings` in Athena, aggregated by `rule_id` × dataset. **Never** `records/…` pages or `finora_dq.excluded_rows` (raw source lines, unmasked: OOS-08). Access: `data`, `finance`, `revops`; no value here is HR-sensitive. Grain: run × dataset, or run × rule × dataset. Evidence: `observado`.

| `metric_id` | Nombre (sinónimos) | Definición (es) | Expression | Dims / filters | `fmt` | `kpi_id` |
|---|---|---|---|---|---|---|
| `dq.row_compliance_pct` | cumplimiento de filas (calidad, salud de los datos, % de filas buenas) | Porcentaje de filas del archivo que pasan las reglas que cuentan para el cumplimiento. | `datasets[].row_compliance_pct` | dataset; run | `pct_dq` | `dq.scorecard.<dataset_id>` |
| `dq.rows_read` | filas leídas (registros recibidos) | Filas recibidas en el archivo de esta corrida. | `datasets[].rows_read` | dataset | `int` | `dq.scorecard.<dataset_id>` |
| `dq.rows_excluded` | filas excluidas (descartadas, en cuarentena) | Filas que no entraron a silver por una regla de exclusión. | `datasets[].rows_excluded` | dataset | `int` | `dq.scorecard.<dataset_id>` |
| `dq.rows_flagged` | filas marcadas (con alerta, señaladas) | Filas que siguen en silver con una marca de una regla. | `datasets[].rows_flagged` | dataset | `int` | `dq.scorecard.<dataset_id>` |
| `dq.rules_failing` | reglas con hallazgos (reglas en rojo o amarillo) | Reglas con estado advertencia o falla en el archivo. | `datasets[].rules_failing` | dataset | `int` | `dq.scorecard.<dataset_id>` |
| `dq.rule_failed_count` | casos por regla (errores, hallazgos) | Filas o hallazgos que no cumplen una regla, por archivo. | `rules[].results[ds].failed` | rule × dataset; filters `rule_id`, `dataset_id`, `rule_status`, `layer` | `int` | `dq.rule_cell.<rule_id>.<dataset_id>` |
| `dq.rule_compliance_pct` | cumplimiento de la regla | Porcentaje evaluado que cumple la regla. | `rules[].results[ds].compliance_pct` | rule × dataset | `pct_dq` | `dq.rule_cell.<rule_id>.<dataset_id>` |
| `dq.rule_status` | estado de la regla (verde, amarillo, rojo) | Pasa, advertencia, falla o no aplica, según los umbrales aprobados. | `rules[].results[ds].status` | rule × dataset | label: pasa / advertencia / falla / no aplica | `dq.rule_cell.<rule_id>.<dataset_id>` |
| `dq.compliance_trend` | tendencia de calidad (evolución, últimas corridas) | Cumplimiento de filas de cada archivo en las últimas corridas exitosas. | `trend[]` (up to 24 runs) | run × dataset | `pct_dq` | `dq.scorecard.<dataset_id>` |

A rule's `inferred` flag is spoken: "regla inferida" means the rule is a business convention, not an owner definition.

### 1.4 Acquisition (`finora_gold`, including the §16 lever tables)

Access: `data`, `finance`, `revops` unless stated otherwise (§9.1 of the gold model). Every money value carries C-CUR. `won_definition` applies to every Won-based metric (default `first_payment`).

| `metric_id` | Nombre (sinónimos) | Definición (es) | Source · expression | Grain · dims · filters | `fmt` | Evidence | Access | `kpi_id` |
|---|---|---|---|---|---|---|---|---|
| `acq.won_count` | clientes nuevos (ganados, altas, nuevos clientes, adquisiciones, logos nuevos) | Clientes cuyo primer pago cae en el mes; no cuenta a quienes ya pagaban en enero de 2022. | `agg_acquisition_month.won_count` (`won_new_logo_count` for `new_logo`); by industry `agg_won_month_industry` | month; sum to quarter/year/period; industry; time | `int` | observado | D F R | `acq.time.new_customers` |
| `acq.won_per_month` | clientes nuevos al mes (ritmo de altas, promedio mensual) | Clientes nuevos divididos por los meses del periodo. | `agg_acq_lever_period.won_per_month`; otherwise Σ won ÷ reportable months (6 dp) | period, year, quarter | `dec1` | observado | D F R | `acq.lost.new_customers`; planner `acq.plan.won` |
| `acq.won_share` | mezcla de industrias (participación, peso de cada industria) | Parte de los clientes nuevos del periodo que es de cada industria. | `agg_acq_lever_industry.won_share` | period × industry | `share_pct1` | observado | D F R | `acq.lever.mix` |
| `acq.new_revenue` | ingreso nuevo (primeros pagos, ingreso de clientes nuevos) | Suma de los primeros pagos de los clientes nuevos, tal como se pagaron. | `agg_acquisition_month.new_revenue_value` (`new_revenue_new_logo_value`); `agg_won_month_industry.new_revenue_value` | month → year; industry | `money` | observado (C-MULT) | D F R | `acq.monthly_table` |
| `acq.new_revenue_multiple` | primeros pagos múltiples (pagos dobles o triples al entrar) | Parte del ingreso nuevo que viene de primeros pagos de 2 o 3 meses juntos. | `agg_acquisition_month.new_revenue_multiple_value` | month → year | `money` | inferido (SB-04) | D F R | `acq.monthly_table` |
| `acq.new_revenue_per_won` | primer pago promedio (ingreso nuevo por cliente) | Ingreso nuevo dividido por clientes nuevos. | ratio(`acq.new_revenue`, `acq.won_count`), 2 dp | year, period, industry | `money` | observado | D F R | `acq.monthly_table` |
| `acq.run_rate_per_won` | ticket inicial (pago mensual de un cliente nuevo, ticket, cuánto paga un cliente nuevo) | Pago mensual promedio de un cliente nuevo en sus meses 2 a 4. | `agg_acq_lever_period.run_rate_mrr_per_won_value`; `agg_acq_lever_industry.run_rate_mrr_per_won_value`; `v_acq_cohort_half.run_rate_mrr_per_won_value` | period; period × industry; cohort_half | `money` | observado (settlement adjustment inferred, §16.2; C-IMMATURE) | D F R | `acq.lost.starting_revenue`; by cohort `acq.lost.ticket_by_cohort`; by industry `acq.lost.ticket_by_industry` |
| `acq.ticket_change_mix` | efecto mezcla (cambio por mezcla de industrias) | Parte del cambio del ticket que viene de cambiar la mezcla de industrias. | Σ `agg_acq_value_change.mix_term_value`, 2 dp | from → to period; industry | `money` | observado (arithmetic) | D F R | `acq.lost.ticket_by_industry` |
| `acq.ticket_change_within` | efecto dentro de cada industria | Parte del cambio del ticket que ocurre dentro de cada industria. | Σ `within_term_value`, 2 dp | from → to period; industry | `money` | observado (arithmetic) | D F R | `acq.lost.ticket_by_industry` |
| `acq.new_mrr_per_month` | MRR nuevo al mes (ingreso recurrente nuevo mensual) | Clientes nuevos al mes por su ticket inicial; es un tope superior, no ingreso facturado. | `agg_acq_lever_period.new_mrr_per_month_value` | period | `money` | inferido | D F R | `acq.plan.new_mrr` |
| `acq.paying_m6_share` | retención a 6 meses (siguen pagando al mes 6) | De los clientes nuevos observables, cuántos pagan en su sexto mes. | `agg_acq_lever_period` / `_industry` / `v_acq_cohort_half`: `paying_m6_share` (+ count, eligible) | period; industry; cohort_half | `share_pct1` | observado (strict cash, a lower bound; C-RETENTION) | D F R | `acq.lost.keep_paying` |
| `acq.paying_m12_share` | retención a 12 meses (siguen pagando al año) | Igual, en su mes 12. | `paying_m12_share` (+ count, eligible) | as above | `share_pct1` | observado (C-RETENTION) | D F R | `acq.lost.keep_paying` |
| `acq.spend_total` | gasto S&M (gasto de ventas y marketing, inversión comercial, presupuesto de marketing) | Gasto mensual de ventas y marketing, suma de las 7 categorías, con negativos. | `agg_acquisition_month.spend_total_value` | month → quarter/year/period; **no industry** | `money` | observado (budget-like; C-CUR) | D F R (A1) | `acq.time.new_customers` |
| `acq.spend_per_month` | gasto S&M al mes | Gasto del periodo dividido por sus meses. | `agg_acq_lever_period.spend_per_month_value`; `v_funnel_period.spend_per_month_value` | period, year, quarter | `money` | observado | D F R | `acq.lever.spend` |
| `acq.spend_category` | gasto por categoría (pauta, publicidad offline, viajes, software) | Gasto de una categoría no sensible. | `v_sm_spend_shared` (= `fact_sm_spend` partition `hr_sensitive=false`), Σ `spend_value` | month → year; spend_category ∈ {PaidMedia, PublicidadNoWeb, Travel, SoftwareTools} | `money` | observado | D F R | `acq.monthly_table` |
| `acq.spend_group` | gasto por grupo (medios, personas, otros) | Gasto sumado por grupo. | `agg_acquisition_month.spend_media_value`, `spend_other_value`, `spend_people_value` | month → year; spend_group | `money` | observado (grouping inferred, GLD-04; C-PEOPLE) | D F R (A1) | `acq.monthly_table` |
| `acq.spend_hr_category` | gasto de equipo, nómina o freelance | Gasto de una categoría de personal (sensible). | `v_acquisition_month_finance.spend_team_value`, `spend_payroll_expenses_value`, `spend_freelance_value` | month → year | `money`, **chart only, never in `summary_es`** | observado | **F only**, Finance workgroup (§2.3 rule 7) | `acq.monthly_table` |
| `acq.cost_per_won` | costo por cliente nuevo (gasto S&M por cliente ganado; "CAC" is answered with this metric and C-NOT-CAC) | Gasto S&M del periodo dividido por los clientes nuevos del mismo periodo. | `agg_acq_lever_period.cost_per_won_value`; `v_funnel_period` / `v_funnel_month` stage WON `cost_per_unit_value` (scenario `base`) | period, year, quarter, month; **no industry** (CDO-10) | `money` | observado ratio (C-NOT-CAC) | D F R | `acq.funnel.won_cost` |
| `acq.payback_months` | payback (meses para recuperar, recuperación de la inversión) | Meses de ticket inicial necesarios para cubrir el gasto S&M por cliente nuevo; ingreso, no margen. | `agg_acq_lever_period.payback_months` | period | `months1` | inferido (C-PAYBACK) | D F R | `acq.plan.payback` |
| `acq.avg_monthly_payment` | pago mensual promedio (ARPPU por industria, ticket promedio de la base) | Promedio de lo pagado en los meses con pago, por industria y grupo de clientes. | `agg_industry_profile.avg_monthly_payment_value` (`_ex_outlier_value`, `median_monthly_payment_value`) | industry × customer_scope | `money` | observado (C-OUTLIER on Restaurantes all/left_censored) | D F R | `acq.industries` |
| `acq.share_months_paid` | constancia de pago (porcentaje de meses pagados) | Meses pagados sobre meses observables; comparable entre cohortes. | `agg_industry_profile.share_of_observable_months_paid` | industry × customer_scope | `share_pct1` | observado | D F R | `acq.industries` |
| `acq.funnel_stage_count` | clientes por etapa (leads, SQL, demos, propuestas estimadas) | Volumen estimado de una etapa: clientes ganados divididos por las tasas supuestas. | `v_funnel_period` / `v_funnel_month.stage_count`, `scenario_id` (default `base`) | funnel_stage × period/year/quarter/month | `dec1` (WON `int`) | **supuesto** (C-FUNNEL) | D F R | `acq.funnel.stages` |
| `acq.funnel_cost_per_stage` | costo por etapa (costo por lead, por SQL) | Gasto del periodo dividido por el volumen estimado de la etapa. | `cost_per_unit_value` of the same views | as above | `money` | **supuesto** (C-FUNNEL) | D F R | `acq.funnel.stages` |
| `acq.rate_sensitivity` | sensibilidad de tasas (qué tasa mueve más) | Clientes ganados extra por cada punto de una tasa, por álgebra. | `v_funnel_rate_sensitivity` | transition; scenario | `pct1`, `dec1` | **supuesto** | D F R | `acq.funnel.sensitivity` |
| `acq.corr_signals` | relación gasto–clientes (correlaciones, señales) | Cuántas pruebas de correlación superan el umbral del 5 %, frente a las esperadas por azar. | `v_corr_signal_summary` (`signals`, `tests_with_r`, `expected_by_chance`); detail `agg_won_spend_lag_corr.r` | method × won_definition × scope type | `int`, `dec1`, `r4` | observado as counts; any causal reading is **no probado** (C-CORR) | D F R | `acq.signals` |

### 1.5 MRR (`finora_gold` MRR tables, `docs/mrr_discounts_model.md` §6)

Every entry carries **C-MRR-PROXY** (MRR built from payments, `mrr_basis = 'cash_proxy'`) and C-CUR. Months after `churn_confirmed_through` carry C-PROV. Access: `data`, `finance`, `revops` (Confidential-Financial). Customer-grain sources are aggregate-only (§2.3 rule 3).

| `metric_id` | Nombre (sinónimos) | Definición (es) | Source · expression | Grain · dims · filters | `fmt` | Evidence | `kpi_id` |
|---|---|---|---|---|---|---|---|
| `mrr.closing` | MRR (ingreso recurrente mensual, MRR al cierre, cuánto factura la base al mes) | Ingreso recurrente mensual al cierre del mes, estimado a partir de los pagos. | `agg_mrr_bridge_month.amount_value` where `line='closing'`; by industry Σ `fact_customer_month_mrr.mrr_value` where `mrr_value > 0` | month (a stock: a quarter or year takes its **last** month, never the sum); industry | `money` | inferido | `mrr.bridge.closing`; hero `mrr.why.hero` |
| `mrr.opening` | MRR inicial (de apertura) | MRR al cierre del mes anterior. | `line='opening'` | month | `money` | inferido | `mrr.bridge.opening` |
| `mrr.net_change` | cambio del MRR (crecimiento, cuánto creció) | MRR de cierre del último mes menos MRR de apertura del primero. | closing(to) − opening(from); `pct` = ÷ opening | from → to | `money`, `pct1` | inferido | `mrr.why.hero` |
| `mrr.line_amount` | movimiento de MRR (MRR nuevo, perdido por bajas, expansión, contracción) | Suma de una línea del puente de MRR en el periodo. | Σ `agg_mrr_bridge_month.amount_value` by `line` (lines 1–8, 10, 16) | month → quarter/year; mrr_line; industry via `fact_mrr_movement` Σ `amount_value` | `money` | observado for new/reactivation/churn/expansion/contraction; inferido for pause, resume, inferred_price_step, first_payment_multiple | `mrr.bridge.<line>` |
| `mrr.line_events` | número de movimientos (cuántas bajas, cuántas altas) | Número de movimientos de esa línea. | Σ `agg_mrr_bridge_month.events` | as above | `int` | as above | `mrr.bridge.<line>` |
| `mrr.driver_amount` | cambio por causa (comportamiento, precios, tiempo de cobro) | Cambio del MRR separado por causa. | Σ `amount_value` by `driver` over lines 1–16 | from → to; driver | `money` | behaviour inferido (cash basis); pricing inferido; timing inferido | `mrr.why.driver.<driver>` |
| `mrr.paying_customers` | clientes pagando (base activa, clientes con MRR) | Clientes con MRR mayor que cero al cierre del mes. | `agg_mrr_bridge_month.events` where `line='closing'`; by industry count of `fact_customer_month_mrr` with `mrr_value > 0` | month; industry | `int` | inferido | `mrr.bridge.closing` |
| `mrr.per_paying_customer` | MRR por cliente (ticket promedio de la base, ARPPU) | MRR de cierre dividido por los clientes pagando. | ratio(`mrr.closing`, `mrr.paying_customers`), 2 dp | month; industry | `money` | inferido | `mrr.trend` |
| `mrr.collected` | cobrado (caja del mes, pagos recibidos) | Lo pagado en el mes, tal como llegó. | `line='collected'` | month → year | `money` | observado | `mrr.monthly_table` |
| `mrr.timing_adjustment` | efecto de tiempo de cobro (pagos atrasados o adelantados) | Diferencia entre lo cobrado y el MRR, por pagos atrasados, adelantados o repartidos. | Σ lines 20–24 | month → year; mrr_line | `money` | inferido | `mrr.bridge.timing` |
| `mrr.temporary_dip` | caídas temporales (bajas de pago que vuelven) | Contracciones que vuelven al monto anterior en 1 a 3 meses: la huella que dejaría un descuento. | `fact_mrr_movement` Σ `amount_value`, count where `is_temporary_dip` | year; industry | `money`, `int` | inferido (GLD-MRR-03) | `mrr.bridge.contraction` |
| `mrr.one_off_spike` | picos puntuales (cobros extra que no se repiten) | Expansiones que vuelven al monto anterior en 1 a 3 meses. | `fact_mrr_movement` where `is_one_off_spike` | year; industry | `money`, `int` | inferido | `mrr.bridge.expansion` |
| `mrr.discount_leakage` | fuga por descuentos (ingreso no capturado) | Precio de lista menos lo cobrado por descuentos. | **not_available** (lines 11–15 NULL) | — | — | — | `mrr.leakage` (always routes to OOS-03) |
| `mrr.list_mrr` / `mrr.net_mrr` | MRR de lista / MRR neto | Valor de suscripción a precio de lista / después de descuentos. | **not_available** (NULL until billing) | — | — | — | `mrr.leakage` (OOS-03) |

### 1.6 `kpi_id` → dashboard card (for `highlight_kpi`)

The names are the visible titles in `dashboard/src/components/`. **The dashboard has no `data-kpi-id` attribute today.** The CTO adds `data-kpi-id="<kpi_id>"` to each element below, on top of the existing `data-testid`, and `highlight_kpi` resolves the attribute. A `kpi_id` with `<…>` is parameterized; an unknown id is ignored silently by the page.

| `kpi_id` | Page | Card (visible title, component) | Existing anchor |
|---|---|---|---|
| `dq.scorecard.<dataset_id>` | dq | "Departments" card with the dataset label ("Transactions", "S&M spend", "Industry"): row compliance, status, rows line (`Departments.tsx`) | `data-testid="scorecard"` + `data-dataset` |
| `dq.rule_cell.<rule_id>.<dataset_id>` | dq | "Rules" table cell (`RulesTable.tsx`, `focusRuleCell`) | rule × dataset cell |
| `acq.verdict` | acquisition | "What to move" headline (`LeversSection.tsx`) | `verdict` |
| `acq.plan.won` / `acq.plan.new_mrr` / `acq.plan.payback` | acquisition | Planner outputs "New customers a month", "New MRR a month", "Payback" | `planned-won`, `planned-mrr`, `planned-payback` |
| `acq.lever.ticket` / `acq.lever.mix` / `acq.lever.conversion` / `acq.lever.spend` | acquisition | Planner lever rows | `lever-ticket`, `lever-mix`, `lever-conversion`, `lever-spend` |
| `acq.lever.ranking` | acquisition | "Biggest levers for a 10% move" | `lever-ranking` |
| `acq.lost.new_customers` / `acq.lost.starting_revenue` | acquisition | "Where growth is lost" cards "New customers a month", "Starting revenue per new customer" (`GrowthLostSection.tsx`) | `lost-customers`, `lost-revenue` |
| `acq.lost.ticket_by_cohort` | acquisition | "Starting revenue per new customer, by half-year cohort" | `ticket-trend` |
| `acq.lost.keep_paying` | acquisition | "Do new customers keep paying?" | `retention-trend` |
| `acq.lost.ticket_by_industry` | acquisition | "Starting revenue per new customer, by industry" | `industry-dumbbell` |
| `acq.funnel.stages` / `acq.funnel.won_cost` / `acq.funnel.sensitivity` | acquisition | "Funnel" stages; the Won row's cost; the sensitivity list (`FunnelWorkbench.tsx`) | `funnel-stage`, `stage-cost` on `data-stage="WON"`, `sensitivity` |
| `acq.time.new_customers` | acquisition | "New customers over time" (`TimeSection.tsx`) | the chart section |
| `acq.signals` | acquisition | "Spend and new customers" (`SignalsSection.tsx`) | `signals` |
| `acq.industries` | acquisition | "Industries" (`IndustriesSection.tsx`) | `industries` |
| `acq.monthly_table` | acquisition | "Monthly data" (`MonthlySection.tsx`) | `monthly` |
| `mrr.why.hero` | mrr | "Why MRR changed" hero line (`WhySection.tsx`) | `mrr-hero` |
| `mrr.why.driver.<behaviour\|pricing\|timing>` | mrr | Driver cards "Customer behaviour", "Pricing (inferred)", "Timing of payments" | `driver-<key>` |
| `mrr.bridge.opening` / `mrr.bridge.closing` / `mrr.bridge.<line>` / `mrr.bridge.timing` | mrr | "MRR bridge" rows (`BridgeSection.tsx`) | `bridge-opening`, `bridge-closing`, `bridge-step` + `data-step` |
| `mrr.trend` | mrr | "MRR by month" (`TrendSection.tsx`) | `trend` |
| `mrr.leakage` | mrr | "Revenue not captured (discounts)" (`LeakageSection.tsx`) | `leakage` |
| `mrr.monthly_table` | mrr | "Monthly data" (`DetailsSections.tsx`) | `mrr-monthly-details` |

**Catalog size:** 48 metric entries (DQ 9, Acquisition 25, MRR 14, of which 2 are `not_available` placeholders that route to out of scope), 14 dimensions, 1 parameter (`won_definition`), 32 `kpi_id`s (4 of them parameterized), 11 out-of-scope rules, 16 caveats and 12 briefing candidates.

---

## 2. The query spec

### 2.1 Tool schema (`submit_query_spec`, Kimi K3 tool use, JSON Schema 2020-12)

Kimi must call this tool exactly once per question. Free text outside the tool call is discarded.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "finora/semantic-layer/query-spec/v1",
  "title": "submit_query_spec",
  "type": "object",
  "additionalProperties": false,
  "required": ["catalog_version", "intent"],
  "properties": {
    "catalog_version": { "const": "sl-2026-11-17" },
    "intent": { "enum": ["answer", "out_of_scope"] },
    "domain": { "enum": ["dq", "acquisition", "mrr"] },
    "metrics": {
      "type": "array", "minItems": 1, "maxItems": 3, "uniqueItems": true,
      "items": { "type": "string", "pattern": "^(dq|acq|mrr)\\.[a-z0-9_]+$" }
    },
    "derived": { "type": "array", "maxItems": 1, "items": { "$ref": "#/$defs/derived" } },
    "dimensions": {
      "type": "array", "maxItems": 2, "uniqueItems": true,
      "items": { "enum": ["month", "quarter", "year", "period", "cohort_half", "industry", "spend_category",
                          "spend_group", "funnel_stage", "rule", "dataset", "mrr_line", "driver", "customer_scope"] }
    },
    "filters": { "$ref": "#/$defs/filters" },
    "won_definition": { "enum": ["first_payment", "new_logo"], "default": "first_payment" },
    "sort": {
      "type": "object", "additionalProperties": false, "required": ["by", "dir"],
      "properties": { "by": { "type": "string" }, "dir": { "enum": ["asc", "desc"] } }
    },
    "limit": { "type": "integer", "minimum": 1, "maximum": 50, "default": 12 },
    "chart": {
      "type": "object", "additionalProperties": false, "required": ["type"],
      "properties": { "type": { "enum": ["kpi", "bar", "line", "table"] }, "title_es": { "type": "string", "maxLength": 80 } }
    },
    "out_of_scope": {
      "type": "object", "additionalProperties": false, "required": ["reason_code"],
      "properties": {
        "reason_code": { "enum": ["causal_spend_won", "funnel_stage_observed", "discounts_billing", "currency",
                                  "single_person_pay", "beyond_data_complete_through", "forecast", "customer_level",
                                  "hr_restricted", "dq_record_level", "outside_catalog"] },
        "slots": { "type": "object", "maxProperties": 3,
                   "additionalProperties": { "type": "string", "maxLength": 40 } }
      }
    }
  },
  "allOf": [
    { "if": { "properties": { "intent": { "const": "answer" } } },
      "then": { "required": ["domain", "metrics", "filters", "chart"], "not": { "required": ["out_of_scope"] } } },
    { "if": { "properties": { "intent": { "const": "out_of_scope" } } },
      "then": { "required": ["out_of_scope"] } }
  ],
  "$defs": {
    "month": { "type": "string", "pattern": "^20[0-9]{2}-(0[1-9]|1[0-2])$" },
    "filters": {
      "type": "object", "additionalProperties": false, "required": ["time"],
      "properties": {
        "time": {
          "type": "object", "additionalProperties": false, "maxProperties": 2,
          "properties": {
            "from": { "$ref": "#/$defs/month" }, "to": { "$ref": "#/$defs/month" },
            "year": { "type": "integer", "minimum": 2020, "maximum": 2035 },
            "quarter": { "type": "string", "pattern": "^20[0-9]{2}-Q[1-4]$" },
            "period_code": { "enum": ["pre_2023_06", "from_2023_06", "full"] },
            "relative": { "enum": ["latest_month", "latest_quarter", "latest_year", "full_window", "latest_run"] }
          }
        },
        "industry": { "type": "array", "maxItems": 6, "items": { "enum": ["RESTAURANTS", "MANUFACTURING", "RETAIL",
                      "TECHNOLOGY", "PROFESSIONAL_SERVICES", "HEALTHCARE", "UNKNOWN", "UNMAPPED"] } },
        "spend_category": { "type": "array", "items": { "enum": ["PaidMedia", "PublicidadNoWeb", "Travel",
                            "SoftwareTools", "Team", "PayrollExpenses", "Freelance"] } },
        "spend_group": { "type": "array", "items": { "enum": ["media", "other", "people"] } },
        "funnel_stage": { "type": "array", "items": { "enum": ["NEW", "WORKING", "ENGAGED", "SQL", "DEMO", "PROPOSAL", "WON"] } },
        "scenario_id": { "type": "string", "pattern": "^[a-z0-9_]{1,40}$", "default": "base" },
        "rule_id": { "type": "array", "items": { "type": "string", "pattern": "^[A-Z]{2,3}-[0-9]{2}[a-z]?$" } },
        "dataset_id": { "type": "array", "items": { "enum": ["transactions", "industry", "sm_spend"] } },
        "rule_status": { "type": "array", "items": { "enum": ["pass", "warn", "fail", "na"] } },
        "mrr_line": { "type": "array", "items": { "type": "string", "pattern": "^[a-z_]{3,30}$" } },
        "driver": { "type": "array", "items": { "enum": ["behaviour", "pricing", "timing", "discount"] } },
        "customer_scope": { "enum": ["won", "left_censored", "all"] }
      }
    },
    "derived": {
      "type": "object", "additionalProperties": false, "required": ["op"],
      "properties": {
        "op": { "enum": ["ratio", "share", "growth", "rank", "lever_scenario"] },
        "of": { "type": "string" }, "over": { "type": "string" },
        "from_period": { "type": "string", "maxLength": 12 }, "to_period": { "type": "string", "maxLength": 12 },
        "baseline_period": { "enum": ["pre_2023_06", "from_2023_06"], "default": "from_2023_06" },
        "ticket_pct": { "type": "number", "minimum": -50, "maximum": 100 },
        "spend_pct": { "type": "number", "minimum": -50, "maximum": 100 },
        "mix": { "type": "object", "additionalProperties": false, "required": ["from_industry", "to_industry", "points"],
                 "properties": { "from_industry": { "type": "string" }, "to_industry": { "type": "string" },
                                 "points": { "type": "number", "minimum": 1, "maximum": 50 } } },
        "conversion_scenario_id": { "type": "string", "pattern": "^[a-z0-9_]{1,40}$" }
      }
    }
  }
}
```

**How Kimi fills it** (system prompt rules, Spanish questions):
- **Time.** Resolve Spanish expressions to `filters.time`: "el año pasado" is the calendar year before the year of `data_complete_through`, so 2023; "hoy", "ahora" or "el último mes" is `latest_month`; "desde junio de 2023" or "el periodo actual" is `period_code: from_2023_06`; "antes" is `pre_2023_06`. Never invent a month after `data_complete_through`. Emit it as asked; the compiler routes it to OOS-06.
- **`won_definition`.** `new_logo` only on explicit words such as "nuevos logos", "sin los que ya estaban activos" or "definición canónica".
- **Out of scope.** When the question matches a rule in §3, set `intent: out_of_scope` with its `reason_code`. Kimi never writes `reason_es`: the templates in §3 do. Slots carry only catalog labels (an industry, a month), never numbers.
- **Follow-ups.** For "¿y en Retail?" or "¿y el año anterior?", start from the previous spec and change only what the user changed.

### 2.2 Derived operations (the only ones allowed)

| `op` | Meaning | Allowed on |
|---|---|---|
| `ratio(of, over)` | of ÷ over | Two catalog metrics with the same grain |
| `share(of, over dimension)` | The part of the total for each member | Additive metrics only: counts, flows. Never `mrr.closing` over months |
| `growth(of, from_period, to_period)` | to − from and (to − from) ÷ from; the percentage is spoken in `pct1` | Any metric. Periods are catalog members |
| `rank(of, dir, limit)` | Top or bottom n | A dimension member list, never customers |
| `lever_scenario` | The §16.3 planner arithmetic, computed in code after one SELECT on `agg_acq_lever_period` / `agg_acq_lever_industry` (and `v_funnel_scenario_compare` for a conversion scenario). It applies exactly the formulas and rounding of §16.3 | Acquisition only. Evidence = the weakest lever moved (spend → `no probado` on Won, which stays flat; conversion → `supuesto`; ticket and mix → `observado` with C-MIX) |

### 2.3 Compiler rules

1. **Catalog only.** Every `metric_id`, `dim_id`, filter value and `op` must exist in this catalog version. Anything else is `outside_catalog`, and the spec is not repaired. One retry is allowed with the validator's error list; after that the answer is `error` with "No pude armar esa consulta; ¿puedes decirlo de otra forma?".
2. **Allowed joins only** (star joins on conformed keys; one SELECT):

   | Fact / aggregate | May join |
   |---|---|
   | `agg_acquisition_month` | `dim_month` |
   | `agg_won_month_industry`, `agg_acq_cohort_quality` | `dim_month`, `dim_industry` |
   | `agg_acq_lever_period` | none |
   | `agg_acq_lever_industry`, `agg_acq_value_change`, `agg_industry_profile` | `dim_industry` |
   | `v_sm_spend_shared`; `fact_sm_spend` (partition `hr_sensitive=false` only) | `dim_month`, `dim_spend_category` |
   | `v_acquisition_month_finance` (F only) | `dim_month` |
   | `v_funnel_*`, `v_corr_signal_summary`, `v_acq_cohort_half`, `v_acquisition_month` | `dim_month`, `dim_funnel_stage` (as applicable) |
   | `agg_mrr_bridge_month` | `dim_month`, `dim_movement_type` |
   | `fact_customer_month_mrr`, `fact_mrr_movement` (aggregate only) | `dim_month`, `dim_industry`, `dim_movement_type` |

   **Forbidden:**
   - spend with `dim_industry`, `dim_customer` or any customer fact (CDO-10, §8.12);
   - `dim_customer`, `fact_acquisition` and `fact_customer_month_revenue` as sources (the aggregates cover every catalog metric);
   - joins between two facts, except through the materialized aggregates;
   - `finora_silver.*` and `finora_dq.excluded_rows`.
3. **No customer-level rows.**
   - `customer_id` may not appear in SELECT, GROUP BY, WHERE, ORDER BY or HAVING.
   - A customer-grain fact may be read only inside an aggregate grouped by allowed dimensions.
   - A question about one customer ("el cliente 94", "el que más paga", "quién se fue") is `customer_level` (OOS-07), answered with the aggregate alternative.
   - **Small cells.** A money value from fewer than 5 customers is never put in `summary_es`. It is said as "menos de 5 clientes". The chart rows keep it, with `is_small_cell = true`, because the named roles may read customer-level data in the browser (CDO-11(1)).
4. **Row cap and time cap.**
   - At most **200 result rows** go to `/results` (`LIMIT 201`; if 201 come back, say "muestro los primeros 200").
   - `limit` (default 12, maximum 50) applies to ranked lists.
   - The time range is clipped to `window_start_month` … `data_complete_through`, at most 34 months.
   - `summary_es` cites at most 5 values.
5. **Mandatory filters** (added by code; the spec cannot remove them):
   - the gold snapshot of `gold_run_id` (`FOR VERSION AS OF <snapshot_id>`);
   - `month_key ≤ data_complete_through`;
   - `is_won_reportable` for Won metrics;
   - `scenario_id = 'base'` unless the user names a valid scenario (`v_funnel_scenario_status`);
   - `won_definition` on every lever, funnel and correlation table;
   - `hr_sensitive = false` on `fact_sm_spend` for every role, because Finance's HR values come only from `v_acquisition_month_finance`.
6. **Stocks versus flows.** `mrr.closing`, `mrr.opening`, `mrr.paying_customers` and shares are never summed over time. A quarter or a year takes the last month for stocks, and recomputes from counts for shares.
7. **HR-sensitive values.**
   - **Roles.** `acq.spend_hr_category` and `spend_category` ∈ {Team, PayrollExpenses, Freelance} compile only for `finance`. For other roles they return `hr_restricted` (OOS-09).
   - **Workgroup.** For `finance` they run only in a Finance-only Athena workgroup (decision A3). **That workgroup does not exist today** (the account has `finora-dl` and `primary`), so until the CTO creates it these metrics return `hr_restricted` for every role, with the Finance alternative "ábrelo en la tabla mensual de Adquisición".
   - **Never spoken.** When enabled, the value goes only to the chart rows. `summary_es` says "Te lo muestro en el gráfico; por política no leo en voz alta montos de personal." The result is created under `finance` and served only to `finance` (contract, `/results`).
   - **Briefing.** HR amounts are never in the briefing, the KPI table or Kimi's input.
8. **Mandatory caveats.** The compiler attaches every caveat whose trigger matches the result. Figures inside a caveat (10,1 %, 67.499, the month counts) are templated from gold at each refresh, never literal. The first one is spoken; all of them go in `caveats_es[]`, and the agent offers them ("¿quieres los detalles?").

   | ID | Trigger | `caveat_es` (spoken form) |
   |---|---|---|
   | C-CUR | Any money value (once per session) | "Los montos están en unidades completas; la moneda no está confirmada." |
   | C-MRR-PROXY | Any `mrr.*` | "El MRR se calcula a partir de los pagos, no de la facturación." |
   | C-PROV | A month after `churn_confirmed_through` | "Las bajas de los dos últimos meses son provisionales." |
   | C-FUNNEL | Stage ≠ WON, `acq.funnel_*`, `acq.rate_sensitivity`, conversion lever | "Las etapas antes de 'ganado' son estimaciones con tasas supuestas; no están en los datos." |
   | C-NOT-CAC | `acq.cost_per_won`, or the word "CAC" | "Es gasto de S&M por cliente nuevo, no un CAC: el gasto parece presupuesto y no se asigna por canal." |
   | C-PAYBACK | `acq.payback_months` | "Es un payback simple sobre ingreso, no sobre margen, y supone que el cliente no se va." |
   | C-REGIME | `period` / `period_code` | "El corte de junio de 2023 es una referencia inferida, no la causa del cambio." |
   | C-IMMATURE | `acq.run_rate_per_won` including the last 3 Won months | "Los clientes de los últimos 3 meses aún no tienen ticket medible." |
   | C-MULT | `acq.new_revenue` | "Incluye primeros pagos dobles o triples; son el 10,1 % del ingreso nuevo." |
   | C-RETENTION | `acq.paying_m*` | "Cuenta solo a quien pagó ese mes; es un mínimo, no la tasa de bajas." |
   | C-CORR | `acq.corr_signals` | "Una correlación no prueba causa." |
   | C-PEOPLE | `spend_group = people` | "Es el total de personal; no se desglosa por categoría." |
   | C-LOWN | Any cell with `is_low_n` | "Hay pocos casos (menos de 10); tómalo con cautela." |
   | C-OUTLIER | `acq.avg_monthly_payment` for Restaurantes `all` / `left_censored` | "Dos clientes atípicos suben el promedio de Restaurantes; sin ellos es 67.499." |
   | C-PARTIAL | A partial year or quarter | "2022 tiene 11 meses y 2024 tiene 10." (templated from `months_in_period`) |
   | C-MIX | `lever_scenario` with mix or ticket | "Supone que cada industria mantiene su ticket y que ese volumen se gana al mismo costo." |

9. **Determinism and cache.**
   - The cache key is (`spec_hash`, role, `gold_run_id`), not the raw question, so a follow-up with the same words but a different `previous_result_id` is not served stale.
   - `sql_hash` is the hash of the compiled SQL. Every result logs the spec, the `sql_hash`, the role and the run, never the rows.
10. **Summary.**
    - `summary_es` comes from a template per spec shape (kpi / ranking / comparison / trend), filled with values formatted per §1.1. Kimi may reorder the template's clauses but may not add numbers.
    - It runs through the same number check as the briefing (§4.4).
    - It names the evidence level whenever that level is not `observado`.

---

## 3. Out-of-scope rules

The compiler applies these deterministically, even when Kimi said `answer`: a month after `data_complete_through`, an HR value for a non-Finance role, `customer_id`, a `not_available` metric. Kimi detects the semantic cases (causal claims, forecasts, a person's pay). `reason_es` and `alternative_es` are templates; `{…}` slots take catalog labels, or numbers formatted by code from a real result. The **alternative** is a ready spec that the agent offers ("¿quieres que te lo muestre?").

| # | `reason_code` | Triggers (Spanish patterns) | `reason_es` | `alternative_es` (and its spec) |
|---|---|---|---|---|
| OOS-01 | `causal_spend_won` | "si invertimos/gastamos más… ¿cuántos clientes?", "¿el gasto trae clientes?", "¿qué canal funciona?", "retorno de la pauta", "atribución" | "Con estos datos no se puede medir cuántos clientes trae el gasto: no hay datos por canal ni campaña, y las correlaciones sin tendencia salen al nivel del azar." | "Puedo mostrarte cómo cambiaría el costo por cliente nuevo y el payback si cambia el gasto, con los clientes nuevos fijos, o la prueba de correlaciones: {signals} de {tests} pruebas, frente a {expected} esperadas por azar." (`lever_scenario` with `spend_pct`; or `acq.corr_signals`, method `diff`, company) |
| OOS-02 | `funnel_stage_observed` | "¿en qué etapa perdemos…?", "conversión real de SQL a demo", "¿cuántos leads tuvimos?", "tiempo en cada etapa", "velocidad de respuesta" | "No hay datos de etapas antes del primer pago: solo se observa 'ganado'. Las etapas del embudo son estimaciones con tasas supuestas." | "Puedo mostrarte el embudo estimado con las tasas supuestas, o qué tasa movería más clientes por álgebra, marcado como supuesto." (`acq.funnel_stage_count` or `acq.rate_sensitivity`, with C-FUNNEL). Only when the user explicitly asks for "el embudo estimado" or "con las tasas supuestas" is it answered directly |
| OOS-03 | `discounts_billing` | "descuentos", "promociones", "fuga", "precio de lista", "MRR neto", "cuánto regalamos" | "Los descuentos aún no se pueden medir: faltan los datos de facturación con precio de lista y descuento." | "Puedo darte las caídas temporales de pago que vuelven al monto anterior en 1 a 3 meses, que es la huella que dejaría un descuento, marcado como inferido." (`mrr.temporary_dip`) |
| OOS-04 | `currency` | "¿en qué moneda?", "en dólares", "en pesos", "tipo de cambio", "convertir" | "La moneda no está confirmada por Finanzas; los montos están en unidades completas y no los puedo convertir." | "Puedo darte la misma cifra en unidades completas, o una medida sin moneda como el payback en meses o el cambio en porcentaje." |
| OOS-05 | `single_person_pay` | "¿cuánto gana {persona/cargo}?", "salario de…", "sueldo del equipo de…", "pago de un freelance" | "No tengo datos por persona y no doy montos que puedan revelar el pago de alguien." | For `finance`: "Puedo mostrarte el gasto total de personal de S&M en el gráfico." For others: "Puedo darte el gasto total de S&M o el de medios." (`acq.spend_group` people, or `acq.spend_total`) |
| OOS-06 | `beyond_data_complete_through` | Any month or period after `data_complete_through` ("noviembre de 2024", "este mes", "2025") | "Los datos llegan hasta {data_complete_through_es}; no tengo {mes_pedido} todavía." | "Puedo darte {data_complete_through_es}, el último mes completo, o la tendencia de los últimos 12 meses." (the same spec with `latest_month`) |
| OOS-07 | `customer_level` | "el cliente {N}", "¿quién paga más?", "lista de clientes", "¿qué clientes se fueron?", "nombre del cliente" | "Por privacidad no doy datos de clientes individuales." | "Puedo darte el MRR promedio por cliente o el reparto por industria. El detalle por cliente está en la tabla 'Top movers' de la página de MRR, con tu sesión." (`mrr.per_paying_customer` by industry; `go_to_page("mrr")`) |
| OOS-08 | `dq_record_level` | "muéstrame la fila…", "¿qué registros fallaron?", "el valor exacto del registro" | "No leo registros individuales; contienen datos de origen." | "Te digo cuántos casos tiene la regla y abro la tabla de reglas para que veas los registros." (`dq.rule_failed_count` + `highlight_kpi` on the rule cell) |
| OOS-09 | `hr_restricted` | An HR category for a non-Finance role, or any role while the Finance workgroup is missing | "Ese gasto es información de personal y solo Finanzas puede verlo." | "Puedo darte el gasto total de S&M, el de medios o el total de personal sin desglose." |
| OOS-10 | `forecast` | "¿cuántos tendremos…?", "proyección", "pronóstico", "meta del próximo año" | "No hago proyecciones: solo respondo con datos observados o con escenarios de las palancas." | "Puedo calcular un escenario con las palancas de ticket, mezcla o gasto sobre el periodo actual." (`lever_scenario`) |
| OOS-11 | `outside_catalog` | Leads, CRM, NPS, product usage, churn reasons, margins, LTV, anything not in §1 | "Ese dato no está en el modelo: {falta}." | The closest catalog metric, chosen by Kimi from §1, without numbers |

Every out-of-scope answer is logged as a demand signal (`reason_code`, the normalized question, the role; no rows) and reviewed monthly by the CDO.

---

## 4. The briefing

### 4.1 Flow (once per gold refresh, after `gold.refreshed`)

1. **Build the KPI table (§4.2) by code.** It reads one SELECT per entry on the published gold snapshot and the DQ snapshot of the same silver run. Changes and percentages are computed by code. The table never holds an HR category or a customer-level value.
2. **Ask Kimi K3** (Bedrock, us-east-1) with the KPI table, the definitions of the cited metrics and the rules of §4.3, through a tool-use schema: `submit_briefing { facts: [{ candidate_id, page, kpi_ids, text_es, numbers: [{ kpi_id, value, unit }] }] }` (5–8 facts).
3. **Check every fact (§4.4).** On failure, follow §4.5.
4. **Publish** `briefing.json` (contract shape) next to the snapshots. Each fact gets `evidence`, and the briefing gets `definitions[]` from §1 for the cited metrics. Only after that, flip the pointer.

### 4.2 KPI table (candidates and today's values, gold `r20261117T201211Z`)

`class`: **lever** = a decision input (Observed/Assumption, §16.3); **state** = where we stand; **trust** = data quality; **null** = a limitation or a null result. Values are exact strings from gold. "Display" is the §1.1 format. `template_es` is the deterministic fallback text, and it passes the check by construction.

| `candidate_id` | class | page | `kpi_ids` | Values (exact → display) | Evidence | `template_es` |
|---|---|---|---|---|---|---|
| B01 `acq_ticket_drop` | lever | acquisition | `acq.lost.starting_revenue`, `acq.lost.new_customers` | won/month change +51.9 → "52 %"; run-rate 55767.62 → "55.768", 42550.70 → "42.551"; change −23.7 → "24 %" | observado | "Los clientes nuevos por mes subieron 52 %, pero cada uno empieza pagando 24 % menos: de 55.768 a 42.551 al mes." |
| B02 `acq_ticket_within` | lever | acquisition | `acq.lost.ticket_by_industry` | within share 95.8 → "96 %"; Retail change −32.7 → "33 %"; Healthcare +1.1 → "1 %" | observado | "La caída del ticket es dentro de cada industria, no por mezcla: explica el 96 %. Retail cayó 33 % y solo Salud subió, 1 %." |
| B03 `acq_mix_lever` | lever | acquisition | `acq.lever.mix` | Δmix for 10 points Retail → Technology 2447.28 → "2.447"; points 10 → "10" | observado + supuesto (C-MIX) | "Pasar 10 puntos de clientes nuevos de Retail a Tecnología subiría el ticket en 2.447 al mes, si cada industria mantiene su ticket." |
| B04 `acq_cost_payback` | state | acquisition | `acq.plan.payback`, `acq.funnel.won_cost` | cost per Won 7592244.22 → "7,59 millones", 3047955.01 → "3,05 millones"; payback 136.1 → "136,1", 71.6 → "71,6" | observado / inferido | "El gasto S&M por cliente nuevo bajó de 7,59 millones a 3,05 millones, y el payback simple de 136,1 a 71,6 meses." |
| B05 `acq_retention` | state | acquisition | `acq.lost.keep_paying` | m12 0.8713 → "87,1 %", 0.8997 → "90,0 %" | observado | "Los clientes nuevos siguen pagando igual o más: al mes 12 paga el 90,0 %, frente al 87,1 % antes de junio de 2023." |
| B06 `mrr_level` | state | mrr | `mrr.bridge.closing` | closing 2024-10 96360646.83 → "96,4 millones"; customers 1678 → "1.678" | inferido (C-MRR-PROXY) | "El MRR, calculado sobre pagos, cerró octubre de 2024 en 96,4 millones, con 1.678 clientes pagando." |
| B07 `mrr_growth_drivers` | state | mrr | `mrr.why.hero`, `mrr.why.driver.behaviour`, `mrr.why.driver.timing` | net 2022-02 → 2024-10 61360338.48 → "61,4 millones"; behaviour 63200703.30 → "63,2 millones"; timing −2414732.25 → "2,41 millones" | inferido | "Desde enero de 2022 el MRR creció 61,4 millones: el comportamiento de los clientes suma 63,2 millones y los primeros pagos adelantados restan 2,41 millones." |
| B08 `mrr_last_month` | state | mrr | `mrr.why.hero` | 2024-10 change 3613521.66 → "3,61 millones"; pct 3.9 → "3,9 %" | inferido (C-PROV) | "En octubre de 2024 el MRR subió 3,61 millones, un 3,9 %; el dato es provisional." |
| B09 `dq_status` | trust | dq | `dq.scorecard.transactions`, `dq.scorecard.sm_spend`, `dq.scorecard.industry` | 100.0 → "100 %", 100.0 → "100 %", 99.95 → "99,95 %" | observado | "Los datos de hoy son confiables: Transacciones y Gasto S&M cumplen al 100 % y Industria al 99,95 %, por un registro vacío." |
| B10 `dq_warnings` | trust | dq | `dq.rule_cell.SB-11.transactions`, `dq.rule_cell.SB-10.sm_spend` | warnings 3 → "3"; SB-11 22 → "22"; SB-10 5 → "5" | observado | "Hay 3 avisos que no bloquean: 22 pagos repartidos de forma desigual, 5 meses con gasto de nómina negativo y un registro vacío." |
| B11 `acq_spend_link` | null | acquisition | `acq.signals`, `acq.lever.spend` | diff signals 3 → "3", tests 44 → "44", expected 2.2 → "2,2" | observado / no probado | "Estos datos no muestran un vínculo medible entre gasto y clientes nuevos: 3 de 44 pruebas sin tendencia salen positivas, casi lo que da el azar, 2,2." |
| B12 `mrr_discounts_na` | null | mrr | `mrr.leakage` | none | — | "Los descuentos aún no se pueden medir: faltan los datos de facturación." |

B10 names the negative-payroll months without any amount. Those months are already visible to all three roles on the DQ dashboard (SB-10, `has_negative_spend_cell`).

### 4.3 Selection and ordering (Kimi chooses, code verifies)

1. **5 to 8 facts**, covering all three pages: at least 1 `dq`, 1 `acquisition` and 1 `mrr`.
2. **Decision-first ordering:** every **lever** fact, then **state**, then **trust**, then **null**. Within a class, the fact with the larger absolute change goes first. B01 is mandatory and first while it exists, because it is the page headline (§16.6).
3. **Null results:** at most 1, always last. B11 may only be used together with B01 or B04, never as the only acquisition fact ("no relationship" is not a headline: §16).
4. **Content rules:**
   - at most 35 words and 4 numbers per fact;
   - every number written as digits (no number words, except "un/una" as an article);
   - no customer-level content, no HR category amount, no causal verb linking spend to Won ("gracias a", "por el gasto", "causó");
   - name the evidence when it is not `observado` ("estimado", "supuesto", "provisional").
5. **The agent's opener** says the first 2 or 3 facts. The rest stay available for "¿qué más?".

### 4.4 Number check (exact match after display rounding)

For each fact:
1. **Tokenize.** Find every numeric token in `text_es` with `[−-]?\d{1,3}(?:\.\d{3})*(?:,\d+)?|[−-]?\d+(?:,\d+)?`, with its suffix (" %", " millones", " meses"). Excluded: 4-digit years inside a date expression ("octubre de 2024", "en 2023", "desde junio de 2023"). Any date expression must equal a period field of a cited KPI.
2. **Match each token to the KPI table.** Each token must equal **exactly** the display string (§1.1) of a `numbers[]` entry, and that entry's `value` must equal the KPI table value for its `kpi_id`, as an exact string. The suffix must agree with the `fmt`: "millones" only for `money` ≥ 1.000.000, "%" only for percentage formats.
3. **Match each entry back to the text.** Every `numbers[]` entry must appear in the text, so there are no unused or hidden numbers.
4. **Direction.** For a change KPI, the verb must agree with the sign of the value: subió/creció/aumentó for > 0; bajó/cayó/restó/perdimos for < 0.
5. **Lexical guards.** The fact must contain no number words (dos … novecientos, mil, millón as a count), no HR category name next to a number, no `customer_id`, and no cited `kpi_id` outside the candidate's `kpi_ids`.

### 4.5 When a fact fails

1. **Regenerate once** for all failed facts together, passing the list of failures to Kimi.
2. **Replace.** A fact that still fails is replaced by its candidate's `template_es`, and `briefing_fact_replaced` is logged with `candidate_id`, the failed token and the run. The model's text is never published.
3. **Drop.** A candidate whose KPI value is NULL or missing is dropped and logged (`briefing_fact_dropped`).
4. **Fill.** If fewer than 5 facts remain, fill from the unused templates in §4.3 order.
5. **Degrade.** If the table cannot reach 5, publish `status: "degraded"` with the facts that passed. The agent says "Hoy no tengo el resumen completo; puedo responder tus preguntas."
6. **Never publish a mismatched number.** The run report records counts of generated, regenerated, replaced and dropped facts.

---

## 5. Evaluation set (20 Spanish questions, today's data)

Expected values are for gold `r20261117T201211Z` and DQ run `r20261117T201211Z`, verified with the local golden engines and the live run reports (see the header). Specs are abbreviated: `catalog_version` is omitted, `won_definition` is `first_payment` unless shown, and each spec carries the caveats listed. A spoken answer **passes** when its figures match these display strings exactly, when it carries the listed caveat, and when it states nothing else numeric.

| # | Pregunta (role `revops` unless stated) | Expected spec / out_of_scope | Expected answer (exact → spoken) |
|---|---|---|---|
| 1 | ¿Qué conjunto de datos tiene peor calidad hoy? | `dq`; metrics `[dq.row_compliance_pct, dq.rows_excluded]`; dims `[dataset]`; time `latest_run`; sort asc; limit 1; chart `kpi`; highlight `dq.scorecard.industry` | Industry 99.95 → "Industria, 99,95 %", 1 fila excluida (SQ-02, registro vacío) |
| 2 | ¿Qué reglas de calidad están en advertencia? | `dq`; `[dq.rule_failed_count]`; dims `[rule, dataset]`; filter `rule_status:[warn,fail]`; sort desc; chart `table` | 3 en advertencia, 0 en falla: SB-11 Transacciones 22; SB-10 Gasto S&M 5; SQ-02 Industria 1 |
| 3 | ¿Cuántos clientes nuevos ganamos en 2022? | `acquisition`; `[acq.won_count]`; time `year:2022`; chart `kpi`; C-PARTIAL | 380 → "380" (11 meses) |
| 4 | (follow-up to 3, `previous_result_id` set) ¿Y sin los que probablemente ya estaban activos? | The previous spec with `won_definition: new_logo` | 337 → "337" (43 menos) |
| 5 | ¿Cuánto paga al mes un cliente nuevo hoy comparado con antes? | `[acq.run_rate_per_won]`; derived `growth(from_period pre_2023_06, to_period from_2023_06)`; chart `bar`; C-REGIME, C-IMMATURE | 55767.62 → 42550.70: "de 55.768 a 42.551 al mes, 23,7 % menos" |
| 6 | ¿Qué industria bajó más su ticket? | `[acq.run_rate_per_won]`; dims `[industry]`; derived `growth(pre_2023_06 → from_2023_06)`; `rank asc`, limit 1; chart `bar`; C-REGIME | Retail 43671.05 → 29406.94: "Retail: de 43.671 a 29.407 por cliente nuevo, 32,7 % menos" |
| 7 | ¿Cuál es el payback de un cliente nuevo y cuánto nos cuesta? | `[acq.payback_months, acq.cost_per_won]`; dims `[period]`; chart `bar`; C-PAYBACK, C-NOT-CAC, C-REGIME | Desde junio de 2023: 71.6 → "71,6 meses", 3047955.01 → "3,05 millones"; antes: "136,1 meses", "7,59 millones" |
| 8 | ¿Qué porcentaje de los clientes nuevos sigue pagando al mes 12? | `[acq.paying_m12_share]`; dims `[period]`; chart `bar`; C-RETENTION | "90,0 %" (332 de 369) desde junio de 2023; "87,1 %" (528 de 606) antes |
| 9 | Si pasamos 10 puntos de clientes nuevos de Retail a Tecnología, ¿qué pasa con el MRR nuevo? | `[acq.new_mrr_per_month, acq.run_rate_per_won, acq.payback_months]`; derived `lever_scenario{baseline from_2023_06, mix{RETAIL→TECHNOLOGY, 10}}`; chart `table`; C-MIX | MRR nuevo 2447916.75 → 2588707.33: "de 2,45 millones a 2,59 millones al mes"; ticket "44.998" (+2.447); payback "67,7 meses". Evidence observado + supuesto |
| 10 | (roles `finance` and `revops`) ¿Cuánto gastamos en el equipo de S&M en 2023? | `revops`: always `out_of_scope hr_restricted` (OOS-09). `finance`: `hr_restricted` while the Finance workgroup is missing; once it exists, `[acq.spend_hr_category]`, filter `spend_category:[Team]`, `year:2023`, chart only | No amount in `summary_es` for any role. For `finance`, the eval asserts the chart value = Σ `v_acquisition_month_finance.spend_team_value` for 2023 at test time. The figure is not written here (CDO-11(2)) |
| 11 | ¿Cuál es el MRR a octubre de 2024? | `mrr`; `[mrr.closing, mrr.paying_customers]`; time `2024-10`; chart `kpi`; C-MRR-PROXY, C-PROV | 96360646.83 → "96,4 millones", 1678 → "1.678 clientes" |
| 12 | ¿Cuánto MRR perdimos por bajas en 2024? | `[mrr.line_amount, mrr.line_events]`; filter `mrr_line:[churn]`, `year:2024`; dims `[month]`; chart `bar`; C-MRR-PROXY, C-PROV, C-PARTIAL | −11655036.12 → "perdimos 11,7 millones", 110 bajas. Septiembre y octubre de 2024 provisionales (0 bajas confirmadas) |
| 13 | ¿Qué industria aporta más MRR hoy? | `[mrr.closing, mrr.paying_customers]`; dims `[industry]`; derived `share(of mrr.closing over industry)`; time `latest_month`; sort desc; limit 6; chart `bar`; C-MRR-PROXY, C-PROV | Restaurantes 31203974.13 → "31,2 millones", "32,4 %" del MRR, 459 clientes |
| 14 | ¿Cuál es el cliente que más paga? | `out_of_scope customer_level` (OOS-07) | Alternative, computed: "MRR por cliente 57.426" (2024-10: 96360646.83 ÷ 1678 = 57425.89); highest industry average Tecnología "74.192" |
| 15 | Si invertimos 20 % más en medios pagados, ¿cuántos clientes más ganamos? | `out_of_scope causal_spend_won` (OOS-01) | Alternative slots: "3 de 44 pruebas, frente a 2,2 esperadas" (diff, company, user's Won). No Won figure stated |
| 16 | ¿En qué etapa del embudo perdemos más clientes? | `out_of_scope funnel_stage_observed` (OOS-02) | No stage figure. Alternative offered: the estimated funnel or the sensitivity (supuesto) |
| 17 | ¿Cuánto MRR perdemos por descuentos? | `out_of_scope discounts_billing` (OOS-03) | Alternative: `mrr.temporary_dip`, 31 caídas temporales, −1101960.93 → "1,10 millones" (inferido) |
| 18 | ¿Cuánto es eso en dólares? | `out_of_scope currency` (OOS-04) | No conversion; alternative: the same figure in full units, or payback in months |
| 19 | ¿Cuánto gana el gerente de marketing? | `out_of_scope single_person_pay` (OOS-05), for every role including `finance` | No amount; alternative per role (OOS-05) |
| 20 | ¿Cuántos clientes nuevos tuvimos en noviembre de 2024? | `out_of_scope beyond_data_complete_through` (OOS-06) | "Los datos llegan hasta octubre de 2024"; alternative: octubre de 2024 = "50" clientes nuevos |

**Scoring.** The spec must match on `intent`, `reason_code`, metric set, dimensions, time filter and `won_definition`; sort and chart are advisory. The answer's figures must match the display strings exactly, and the mandatory caveats must be present. Any number not in the expected answer is a failure. The eval runs on every catalog, prompt or Kimi version change, and on every gold model version change. When gold figures change, this table is regenerated from the golden engines, never edited by hand.

---

## 6. What the contract (v1) must change (proposed v1.1, by agreement)

1. **DQ is not in `finora_gold`.** `/api/agent/ask` must also read the DQ snapshot of the same silver run, with `finora_dq.findings` as the Athena fallback, not only "the governed `finora_gold` views and tables".
2. **`ask` response.**
   - Add `pending` to the documented `status` enum.
   - Add `reason_code` to `out_of_scope`.
   - Add to `answered`: `evidence` (observado/inferido/supuesto/no probado), `caveats_es[]`, `kpi_ids[]` (for `highlight_kpi`), `as_of_month`, `catalog_version`, `gold_run_id`.
3. **HR values.**
   - They are never in `summary_es`, for any role; chart only for `finance`.
   - They need a Finance-only Athena workgroup (decision A3), which does not exist, so they are `hr_restricted` until the CTO builds it.
   - The contract's "Athena (workgroup `finora-dl`)" must say so.
4. **Contract example figures are not canonical.** "de 43.695 a 28.733" must read "de 43.671 a 29.407" (gold §16.5, Retail run-rate).
5. **Briefing.** Add `facts[].evidence`, `facts[].candidate_id`, a briefing-level `status` (`ok` | `degraded`) and `caveats[]`. The failure rule becomes "regenerate once, then template, then drop" (§4.5) instead of drop only.
6. **Cache key** becomes (`spec_hash`, role, `gold_run_id`), not the normalized question.
7. **Kimi's input** is stated explicitly: the question, the catalog entries, and the previous spec and `summary_es`. Never rows.
8. **`highlight_kpi` ids** are parameterized (§1.6). The dashboard needs `data-kpi-id` anchors; none exist today.
