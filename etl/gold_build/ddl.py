"""Athena DDL for the gold layer: the user-owned rates table, its one-time seed
and the views of §7 (docs/gold_acquisition_model.md). Applied by the deploy
step infra/gold_athena_ddl.py; the gold job never runs it (§6.5).

One SQL text per view, rendered for two dialects: `athena` (Trino, engine v3:
the product) and `spark` (local tests only). Objects are referenced as
@@name@@ and resolved by the caller: finora_gold.<name> on Athena, temp views
or fixture CTEs in tests.

Exact arithmetic. Rates are DECIMAL(5,4), so every rate is an integer i / 10^4
and a product of k rates is P / 10^(4k) with P an integer of at most 30 digits.
Every published quotient is computed as one integer division of integers
(DECIMAL(38,0), which Trino rounds HALF_UP), then scaled. No intermediate value
is rounded and no division can overflow for any rate in (0, 1].
"""

from __future__ import annotations

import re
from decimal import Decimal

from gold_build import engine, schemas

RATE = schemas.RATE_TABLE


def _ten(k: int) -> str:
    return f"CAST('{10 ** k}' AS DECIMAL({k + 1},0))"


def exact(num: str, den: str, scale: int, qdigits: int = 38) -> str:
    """HALF_UP(num / den) at `scale` decimals; num and den are integer-valued."""
    n = f"CAST(({num}) AS DECIMAL(38,0)) * {_ten(scale)}"
    q = f"CAST(CAST({n} AS DECIMAL(38,0)) / CAST(({den}) AS DECIMAL(38,0)) AS DECIMAL({qdigits},0))"
    unit = f"CAST('{Decimal(1).scaleb(-scale):f}' AS DECIMAL({scale + 1},{scale}))"
    return f"CAST({q} * {unit} AS DECIMAL(38,{scale}))"


def _dialect(sql: str, dialect: str) -> str:
    if dialect == "athena":
        now = "(CAST(current_timestamp AT TIME ZONE 'UTC' AS timestamp(6)) + INTERVAL '{m}' MINUTE)"
        sql = sql.replace("@@STR@@", "VARCHAR")
    else:
        now = "(CAST(current_timestamp() AS TIMESTAMP_NTZ) + INTERVAL '{m}' MINUTE)"
        sql = sql.replace("@@STR@@", "STRING")
    return re.sub(r"@@NOW_PLUS_([0-9]+)@@", lambda m: now.format(m=m.group(1)), sql)


def resolve(sql: str, ref) -> str:
    return re.sub(r"@@([a-z_]+)@@", lambda m: ref(m.group(1)), sql)


# --------------------------------------------------------------------------- #
# Rates                                                                       #
# --------------------------------------------------------------------------- #

def rate_ints(cfg: dict, alias: str = "c") -> str:
    """Pivot of the six current rates of a scenario as integers i1..i6 (rate x 10^4)."""
    return ",\n  ".join(
        f"MAX(CASE WHEN {alias}.from_stage_code = '{f}' THEN CAST({alias}.rate * 10000 AS DECIMAL(5,0)) END) AS i{n}"
        for n, (f, _) in enumerate(cfg["transitions"], start=1))


def stage_product(cfg: dict) -> tuple[str, str]:
    """(P, 10^(4k)) as CASE expressions over k = downstream transitions of a stage."""
    n = len(cfg["transitions"])
    p_cases = ["WHEN 0 THEN CAST('1' AS DECIMAL(30,0))"]
    s_cases = ["WHEN 0 THEN CAST('1' AS DECIMAL(25,0))"]
    for k in range(1, n + 1):
        prod = " * ".join(f"r.i{j}" for j in range(n - k + 1, n + 1))
        p_cases.append(f"WHEN {k} THEN CAST({prod} AS DECIMAL(30,0))")
        s_cases.append(f"WHEN {k} THEN CAST('{10 ** (4 * k)}' AS DECIMAL(25,0))")
    return (f"(CASE st.k {' '.join(p_cases)} END)", f"(CASE st.k {' '.join(s_cases)} END)")


def p6(alias: str, n: int = 6) -> str:
    return f"CAST({' * '.join(f'{alias}.i{j}' for j in range(1, n + 1))} AS DECIMAL(30,0))"


def v_funnel_rate_current(cfg: dict) -> str:
    return f"""SELECT scenario_id, scenario_label, from_stage_code, to_stage_code, rate, changed_at, changed_by, change_reason
FROM (
  SELECT x.scenario_id, x.scenario_label, x.from_stage_code, x.to_stage_code, x.rate, x.changed_at, x.changed_by,
         x.change_reason,
         row_number() OVER (PARTITION BY x.scenario_id, x.from_stage_code
                            ORDER BY x.changed_at DESC NULLS LAST, x.to_stage_code DESC NULLS LAST, x.rate DESC NULLS LAST,
                                     x.changed_by DESC NULLS LAST, x.change_reason DESC NULLS LAST,
                                     x.scenario_label DESC NULLS LAST) AS rn
  FROM @@{RATE}@@ x
) ranked
WHERE rn = 1"""


def v_funnel_scenario_status(cfg: dict) -> str:
    pat = cfg["base_seed"]["scenario_id_pattern"]
    tol = cfg["params"]["future_tolerance_minutes"]
    now = f"@@NOW_PLUS_{tol}@@"
    return f"""WITH pairs AS (
  SELECT stage_code AS from_code, next_stage_code AS to_code FROM @@dim_funnel_stage@@ WHERE next_stage_code IS NOT NULL
),
dup AS (
  SELECT scenario_id, from_stage_code, changed_at, COUNT(*) AS n FROM @@{RATE}@@ GROUP BY scenario_id, from_stage_code, changed_at
),
cur AS (SELECT * FROM @@v_funnel_rate_current@@),
checks AS (
  SELECT c.scenario_id,
    COUNT(*) AS n_current,
    SUM(CASE WHEN p.from_code IS NULL THEN 1 ELSE 0 END) AS n_bad_pair,
    SUM(CASE WHEN c.rate IS NULL OR c.rate <= 0 OR c.rate > 1 THEN 1 ELSE 0 END) AS n_bad_rate,
    COUNT(DISTINCT CASE WHEN f.from_code IS NOT NULL THEN c.from_stage_code END) AS n_valid_from,
    SUM(CASE WHEN d.n > 1 THEN 1 ELSE 0 END) AS n_dup,
    SUM(CASE WHEN c.changed_by IS NULL OR trim(c.changed_by) = '' OR c.change_reason IS NULL OR trim(c.change_reason) = ''
              OR c.changed_at IS NULL OR c.changed_at > {now} THEN 1 ELSE 0 END) AS n_bad_meta
  FROM cur c
  LEFT JOIN pairs p ON c.from_stage_code = p.from_code AND c.to_stage_code = p.to_code
  LEFT JOIN (SELECT DISTINCT from_code FROM pairs) f ON c.from_stage_code = f.from_code
  LEFT JOIN dup d ON d.scenario_id IS NOT DISTINCT FROM c.scenario_id AND d.from_stage_code IS NOT DISTINCT FROM c.from_stage_code
                 AND d.changed_at IS NOT DISTINCT FROM c.changed_at
  GROUP BY c.scenario_id
),
latest AS (
  SELECT scenario_id, scenario_label, changed_at, changed_by, change_reason,
         row_number() OVER (PARTITION BY scenario_id ORDER BY changed_at DESC NULLS LAST, from_stage_code DESC NULLS LAST) AS rn
  FROM cur
),
flags AS (
  SELECT k.*,
    (k.scenario_id IS NOT NULL AND regexp_like(k.scenario_id, '{pat}') AND NOT regexp_like(k.scenario_id, '[^a-z0-9_]')) AS ok01,
    (k.n_bad_pair = 0) AS ok02,
    (k.n_bad_rate = 0) AS ok03,
    (k.n_current = {len(cfg['transitions'])} AND k.n_valid_from = {len(cfg['transitions'])}) AS ok04,
    (k.n_dup = 0) AS ok05,
    (k.n_bad_meta = 0) AS ok06
  FROM checks k
)
SELECT f.scenario_id, l.scenario_label,
  CASE WHEN f.ok01 AND f.ok02 AND f.ok03 AND f.ok04 AND f.ok05 AND f.ok06 THEN 'valid' ELSE 'invalid' END AS status,
  concat_ws(',', CASE WHEN NOT f.ok01 THEN 'GR-01' END, CASE WHEN NOT f.ok02 THEN 'GR-02' END,
                 CASE WHEN NOT f.ok03 THEN 'GR-03' END, CASE WHEN NOT f.ok04 THEN 'GR-04' END,
                 CASE WHEN NOT f.ok05 THEN 'GR-05' END, CASE WHEN NOT f.ok06 THEN 'GR-06' END) AS failed_checks,
  f.n_current AS current_transitions,
  l.changed_at AS latest_changed_at, l.changed_by AS latest_changed_by, l.change_reason AS latest_change_reason
FROM flags f
JOIN latest l ON l.scenario_id IS NOT DISTINCT FROM f.scenario_id AND l.rn = 1"""


def _valid_rates(cfg: dict) -> str:
    return f"""SELECT c.scenario_id, MAX(s.scenario_label) AS scenario_label,
  {rate_ints(cfg)}
FROM @@v_funnel_rate_current@@ c
JOIN @@v_funnel_scenario_status@@ s ON s.scenario_id = c.scenario_id AND s.status = 'valid'
GROUP BY c.scenario_id"""


def _stages(cfg: dict) -> str:
    n = len(cfg["transitions"])
    return (f"SELECT stage_key, stage_code, stage_label, is_observed, {n + 1} - stage_key AS k "
            f"FROM @@dim_funnel_stage@@")


def _definitions(cfg: dict) -> str:
    return " UNION ALL ".join(f"SELECT '{d}' AS won_definition" for d in cfg["won_definitions"])


REASON_RANK = {r: i for i, r in enumerate(("won_zero", "spend_missing", "beyond_data_complete_through",
                                            "unit_tripwire", "won_incomplete"), start=1)}


def _months(cfg: dict) -> str:
    """Reportable months x won definition, with the month-level cost reason rank."""
    return f"""SELECT a.month_key, d.month, d.year, d.year_quarter, d.sm_regime, w.won_definition,
  CASE WHEN w.won_definition = 'first_payment' THEN a.won_count ELSE a.won_new_logo_count END AS won,
  a.spend_total_value AS spend, a.won_is_complete, a.is_unit_tripwire, a.currency_status, a.spend_basis_status,
  a.scope_status, g.data_complete_through,
  CASE WHEN COALESCE(CASE WHEN w.won_definition = 'first_payment' THEN a.won_count ELSE a.won_new_logo_count END, 0) = 0 THEN 1
       WHEN a.spend_total_value IS NULL THEN 2
       WHEN g.data_complete_through IS NULL OR d.month > g.data_complete_through THEN 3
       WHEN COALESCE(a.is_unit_tripwire, FALSE) THEN 4
       WHEN a.won_is_complete = FALSE THEN 5 END AS reason_rank
FROM @@agg_acquisition_month@@ a
JOIN @@dim_month@@ d ON d.month_key = a.month_key
CROSS JOIN @@gold_build_status@@ g
CROSS JOIN ({_definitions(cfg)}) w
WHERE a.is_won_reportable"""


def _reason(expr: str) -> str:
    return "CASE " + " ".join(f"WHEN {expr} = {i} THEN '{r}'" for r, i in REASON_RANK.items()) + " END"


def _stage_cols(cfg: dict) -> str:
    P, S = stage_product(cfg)
    return f"""st.stage_key, st.stage_code, st.stage_label,
  CASE WHEN st.is_observed THEN 'Real' ELSE 'Estimated' END AS real_or_estimated,
  {exact(P, S, 12, 13)} AS downstream_rate_product,
  {exact(f'CAST(b.won AS DECIMAL(38,0)) * {S}', P, 6)} AS stage_count,
  CASE WHEN b.reason_rank IS NULL THEN {exact(f'CAST(b.spend AS DECIMAL(38,0)) * {P}', f'CAST(b.won AS DECIMAL(38,0)) * {S}', 2)} END
    AS cost_per_unit_value,
  {_reason('b.reason_rank')} AS cost_null_reason"""


def v_funnel_month(cfg: dict) -> str:
    return f"""WITH r AS ({_valid_rates(cfg)}),
st AS ({_stages(cfg)}),
b AS ({_months(cfg)})
SELECT r.scenario_id, r.scenario_label, b.won_definition, b.month_key, b.month, b.sm_regime,
  {_stage_cols(cfg)},
  b.won AS won_count, b.spend AS spend_total_value, (b.won < {cfg['params']['low_n']}) AS is_low_n,
  b.currency_status, b.spend_basis_status, b.scope_status
FROM r CROSS JOIN st CROSS JOIN b"""


def _periods(cfg: dict) -> str:
    """Reportable months up to data_complete_through, aggregated per period and definition."""
    m = "SELECT * FROM months WHERE data_complete_through IS NOT NULL AND month <= data_complete_through"
    return f"""months AS ({_months(cfg)}),
member AS (
  SELECT 'full' AS period_type, 'full' AS period_id, x.* FROM ({m}) x
  UNION ALL SELECT 'year', CAST(x.year AS @@STR@@), x.* FROM ({m}) x
  UNION ALL SELECT 'quarter', x.year_quarter, x.* FROM ({m}) x
  UNION ALL SELECT 'sm_regime', x.sm_regime, x.* FROM ({m}) x
),
b AS (
  SELECT period_type, period_id, won_definition, COUNT(*) AS months_in_period, MIN(month) AS first_month,
    MAX(month) AS last_month, SUM(won) AS won,
    CASE WHEN COUNT(spend) = COUNT(*) THEN SUM(spend) END AS spend,
    CASE WHEN SUM(won) = 0 THEN 1 ELSE MIN(reason_rank) END AS reason_rank,
    CASE WHEN period_type = 'year' THEN COUNT(*) < 12 WHEN period_type = 'quarter' THEN COUNT(*) < 3 END
      AS is_partial_period,
    MAX(currency_status) AS currency_status, MAX(spend_basis_status) AS spend_basis_status,
    MAX(scope_status) AS scope_status
  FROM member GROUP BY period_type, period_id, won_definition
)"""


def v_funnel_period(cfg: dict) -> str:
    return f"""WITH r AS ({_valid_rates(cfg)}),
st AS ({_stages(cfg)}),
{_periods(cfg)}
SELECT r.scenario_id, r.scenario_label, b.won_definition, b.period_type, b.period_id, b.is_partial_period,
  b.months_in_period, b.first_month, b.last_month,
  {_stage_cols(cfg)},
  b.won AS won_count, b.spend AS spend_total_value,
  {exact('b.won', 'b.months_in_period', 6)} AS won_per_month,
  CASE WHEN b.spend IS NOT NULL THEN {exact('b.spend', 'b.months_in_period', 2)} END AS spend_per_month_value,
  (b.won < {cfg['params']['low_n']}) AS is_low_n, b.currency_status, b.spend_basis_status, b.scope_status
FROM r CROSS JOIN st CROSS JOIN b"""


def v_funnel_scenario_compare(cfg: dict) -> str:
    one = _ten(4 * len(cfg["transitions"]))
    ps, pb = p6("r"), p6("rb")
    won = "CAST(b.won AS DECIMAL(38,0))"
    return f"""WITH r AS ({_valid_rates(cfg)}),
{_periods(cfg)}
SELECT r.scenario_id, r.scenario_label, b.won_definition, b.period_type, b.period_id, b.is_partial_period,
  b.months_in_period, b.won AS won_count, b.spend AS spend_total_value,
  {exact(ps, one, 12, 13)} AS overall_rate,
  {exact(pb, one, 12, 13)} AS overall_rate_base,
  {exact(f'{won} * {one}', pb, 6)} AS new_estimated_base,
  {exact(f'{won} * {ps}', pb, 6)} AS won_implied_same_new,
  {exact(f'{won} * ({ps} - {pb})', pb, 6)} AS won_implied_delta,
  {exact(f'({ps} - {pb}) * 100', pb, 6)} AS won_implied_delta_pct,
  {exact(f'{won} * {one}', ps, 6)} AS new_required_same_won,
  {exact(f'{won} * {one}', ps, 6)} - {exact(f'{won} * {one}', pb, 6)} AS new_required_delta,
  {exact(f'({pb} - {ps}) * 100', ps, 6)} AS new_required_delta_pct,
  CASE WHEN b.reason_rank IS NULL THEN {exact(f'CAST(b.spend AS DECIMAL(38,0)) * {pb}', f'{won} * {ps}', 2)} END
    AS cost_per_won_implied_value,
  {_reason('b.reason_rank')} AS cost_null_reason,
  '{_basis()}' AS basis,
  b.currency_status, b.spend_basis_status, b.scope_status
FROM r CROSS JOIN (SELECT * FROM r WHERE scenario_id = 'base') rb CROSS JOIN b"""


def _basis() -> str:
    from gold_build.funnel import BASIS
    return BASIS


def v_funnel_rate_sensitivity(cfg: dict) -> str:
    point = int(Decimal(cfg["params"]["rate_point"]) * 10000)
    return f"""WITH {_periods(cfg)},
full_won AS (SELECT won_definition, won FROM b WHERE period_type = 'full'),
cur AS (
  SELECT c.scenario_id, s.scenario_label, c.from_stage_code, c.to_stage_code, c.rate,
         CAST(c.rate * 10000 AS DECIMAL(5,0)) AS i
  FROM @@v_funnel_rate_current@@ c
  JOIN @@v_funnel_scenario_status@@ s ON s.scenario_id = c.scenario_id AND s.status = 'valid'
)
SELECT c.scenario_id, c.scenario_label, w.won_definition, st.stage_key AS from_stage_key, c.from_stage_code,
  c.to_stage_code, c.rate, w.won AS won_count_full_period,
  CASE WHEN c.i + {point} <= 10000 THEN {exact(f'{point * 100}', 'c.i', 6)} END AS won_pct_change_per_point,
  CASE WHEN c.i + {point} <= 10000 THEN {exact(f'CAST(w.won AS DECIMAL(38,0)) * {point}', 'c.i', 6)} END
    AS won_change_per_point_full_period,
  CASE WHEN c.i + {point} <= 10000 THEN {exact(f'-{point * 100}', f'c.i + {point}', 6)} END
    AS new_required_pct_change_per_point,
  '{_basis()}' AS basis
FROM cur c
JOIN @@dim_funnel_stage@@ st ON st.stage_code = c.from_stage_code
CROSS JOIN full_won w"""


def v_acquisition_month(cfg: dict, finance: bool = False) -> str:
    reg = [i for i in cfg["industries"] if not i["is_unknown_member"]]
    unk = [str(i["industry_key"]) for i in cfg["industries"] if i["is_unknown_member"]]
    piv = ",\n  ".join(
        f"COALESCE(SUM(CASE WHEN wi.industry_key = {i['industry_key']} THEN wi.won_count END), 0) "
        f"AS won_{i['industry_code'].lower()}" for i in reg)
    piv += (f",\n  COALESCE(SUM(CASE WHEN wi.industry_key IN ({', '.join(unk)}) THEN wi.won_count END), 0) "
            "AS won_unknown_industry")
    shared = [engine.spend_col(c["category_code"]) for c in cfg["spend_categories"]
              if c["category_key"] > 0 and not c["is_hr_sensitive"]]
    hr = [c for c in cfg["spend_categories"] if c["category_key"] > 0 and c["is_hr_sensitive"]]
    hr_cols = ""
    hr_join = ""
    if finance:
        hr_cols = ",\n  " + ",\n  ".join(f"h.{engine.spend_col(c['category_code'])}" for c in hr)
        hr_piv = ",\n    ".join(f"MAX(CASE WHEN category_key = {c['category_key']} THEN spend_value END) "
                                f"AS {engine.spend_col(c['category_code'])}" for c in hr)
        hr_join = (f"\nLEFT JOIN (\n  SELECT month_key,\n    {hr_piv}\n  FROM @@fact_sm_spend@@ WHERE hr_sensitive = TRUE "
                   "GROUP BY month_key\n) h ON h.month_key = a.month_key")
    return f"""WITH wi AS (SELECT month_key, industry_key, won_count FROM @@agg_won_month_industry@@),
ind AS (
  SELECT wi.month_key,
  {piv}
  FROM wi GROUP BY wi.month_key
)
SELECT a.month_key, d.month, a.won_count, a.won_new_logo_count,
  {', '.join(f'ind.won_{i["industry_code"].lower()}' for i in reg)}, ind.won_unknown_industry,
  a.new_revenue_value,
  {', '.join(f'a.{c}' for c in shared)}, a.spend_people_value, a.spend_total_value{hr_cols},
  a.currency_status, a.revenue_basis_status, a.spend_basis_status, a.scope_status
FROM @@agg_acquisition_month@@ a
JOIN @@dim_month@@ d ON d.month_key = a.month_key
LEFT JOIN ind ON ind.month_key = a.month_key{hr_join}
WHERE a.is_won_reportable"""


def v_corr_signal_summary(cfg: dict) -> str:
    return """SELECT method, won_definition, CASE WHEN scope_code = 'ALL' THEN 'company' ELSE 'industry' END AS scope_type,
  COUNT(*) AS tests, COUNT(r) AS tests_with_r,
  SUM(CASE WHEN is_signal_5pct THEN 1 ELSE 0 END) AS signals,
  CAST(COUNT(r) AS DECIMAL(10,0)) * CAST('0.05' AS DECIMAL(3,2)) AS expected_by_chance
FROM @@agg_won_spend_lag_corr@@
GROUP BY method, won_definition, CASE WHEN scope_code = 'ALL' THEN 'company' ELSE 'industry' END"""


def v_sm_spend_shared(cfg: dict) -> str:
    cols = [c for c, _ in schemas.COLUMNS["fact_sm_spend"] if c != "hr_sensitive"]
    return f"SELECT {', '.join(cols)} FROM @@fact_sm_spend@@ WHERE hr_sensitive = FALSE"


def v_acq_cohort_half(cfg: dict) -> str:
    """§16.4(f): agg_acq_cohort_quality rolled up to won_definition x cohort_half."""
    counts = ("won_count", "run_rate_customers", "run_rate_no_paid_customers", "run_rate_immature_customers",
              "paying_m6_eligible", "paying_m6_count", "paying_m12_eligible", "paying_m12_count", "outlier_customers")
    sums = ",\n  ".join(f"SUM({c}) AS {c}" for c in counts)
    rr_num = "SUM(run_rate_m2_4_sum_value) * CAST('1000000' AS DECIMAL(7,0))"
    rr_den = "SUM(run_rate_customers) * CAST('1000000' AS DECIMAL(7,0))"
    return f"""SELECT won_definition, cohort_half,
  {sums},
  CASE WHEN SUM(run_rate_customers) > 0 THEN {exact(rr_num, rr_den, 2)} END AS run_rate_mrr_per_won_value,
  CASE WHEN SUM(paying_m6_eligible) > 0 THEN {exact('SUM(paying_m6_count)', 'SUM(paying_m6_eligible)', 4)} END
    AS paying_m6_share,
  CASE WHEN SUM(paying_m12_eligible) > 0 THEN {exact('SUM(paying_m12_count)', 'SUM(paying_m12_eligible)', 4)} END
    AS paying_m12_share,
  (SUM(paying_m6_eligible) = SUM(won_count)) AS is_complete_m6,
  (SUM(paying_m12_eligible) = SUM(won_count)) AS is_complete_m12,
  (SUM(run_rate_immature_customers) = 0) AS is_complete_run_rate
FROM @@agg_acq_cohort_quality@@
GROUP BY won_definition, cohort_half"""


VIEWS = [  # dependency order
    ("v_funnel_rate_current", v_funnel_rate_current),
    ("v_funnel_scenario_status", v_funnel_scenario_status),
    ("v_funnel_month", v_funnel_month),
    ("v_funnel_period", v_funnel_period),
    ("v_funnel_scenario_compare", v_funnel_scenario_compare),
    ("v_funnel_rate_sensitivity", v_funnel_rate_sensitivity),
    ("v_acquisition_month", v_acquisition_month),
    ("v_acquisition_month_finance", lambda cfg: v_acquisition_month(cfg, finance=True)),
    ("v_corr_signal_summary", v_corr_signal_summary),
    ("v_sm_spend_shared", v_sm_spend_shared),
    ("v_acq_cohort_half", v_acq_cohort_half),
]


def views(cfg: dict, dialect: str = "athena") -> list[tuple[str, str]]:
    return [(name, _dialect(fn(cfg), dialect)) for name, fn in VIEWS]


def create_view_statements(cfg: dict, db: str = schemas.DB) -> list[tuple[str, str]]:
    return [(name, f"CREATE OR REPLACE VIEW {db}.{name} AS\n" + resolve(sql, lambda n: f"{db}.{n}"))
            for name, sql in views(cfg, "athena")]


# --------------------------------------------------------------------------- #
# The rates table (one-time, idempotent deploy step, §6.5)                    #
# --------------------------------------------------------------------------- #

def athena_type(t: str) -> str:
    return {"string": "string", "timestamp": "timestamp"}.get(t, t)


def rate_table_ddl(bucket: str, db: str = schemas.DB) -> str:
    cols = ",\n  ".join(f"{n} {athena_type(t)}" for n, t in schemas.RATE_COLUMNS)
    # Athena VACUUM would expire snapshots; these properties make it keep every
    # one (§6.4: the rate table's snapshots are never expired).
    return (f"CREATE TABLE IF NOT EXISTS {db}.{RATE} (\n  {cols}\n)\n"
            f"LOCATION 's3://{bucket}/iceberg/{db}/{RATE}/'\n"
            "TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet', 'write_compression'='zstd',\n"
            "  'vacuum_min_snapshots_to_keep'='2147483647', 'vacuum_max_snapshot_age_seconds'='3153600000')")


def sql_string(s: str) -> str:
    """A Trino string literal. Callers validate first; control characters are refused here too."""
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in s):
        raise ValueError("control characters are not allowed in a SQL literal")
    return "'" + s.replace("'", "''") + "'"


def rate_literal(rate: str) -> str:
    if not re.fullmatch(r"(0|1)\.[0-9]{4}", rate):
        raise ValueError("a rate literal must have the form d.dddd")
    return f"CAST('{rate}' AS DECIMAL(5,4))"


def insert_rows_sql(rows: list[dict], db: str = schemas.DB) -> str:
    """INSERT ... VALUES with changed_at = the statement's current_timestamp (UTC)."""
    vals = ",\n".join(
        f"({sql_string(r['scenario_id'])}, {sql_string(r['scenario_label'])}, {sql_string(r['from_stage_code'])}, "
        f"{sql_string(r['to_stage_code'])}, {rate_literal(r['rate'])}, "
        "CAST(current_timestamp AT TIME ZONE 'UTC' AS timestamp(6)), "
        f"{sql_string(r['changed_by'])}, {sql_string(r['change_reason'])})" for r in rows)
    cols = ", ".join(n for n, _ in schemas.RATE_COLUMNS)
    return f"INSERT INTO {db}.{RATE} ({cols})\nVALUES\n{vals}"


def seed_rows(cfg: dict) -> list[dict]:
    s = cfg["base_seed"]
    return [{"scenario_id": s["scenario_id"], "scenario_label": s["scenario_label"],
             "from_stage_code": r["from_stage_code"], "to_stage_code": r["to_stage_code"], "rate": r["rate"],
             "changed_by": s["changed_by"], "change_reason": s["change_reason"]} for r in s["rates"]]


# --------------------------------------------------------------------------- #
# Fixture queries (tests and the pre-deploy Athena check)                     #
# --------------------------------------------------------------------------- #

def _lit(v, t: str, dialect: str) -> str:
    if v is None:
        return f"CAST(NULL AS {_cast_type(t, dialect)})"
    if t == "string":
        return f"CAST({sql_string(str(v))} AS {_cast_type(t, dialect)})"
    if t == "boolean":
        return "TRUE" if v else "FALSE"
    if t == "timestamp":
        return f"CAST('{v.strftime('%Y-%m-%d %H:%M:%S.%f')}' AS {_cast_type(t, dialect)})"
    if t == "date":
        return f"DATE '{v.isoformat()}'"
    return f"CAST('{v}' AS {_cast_type(t, dialect)})"


def _cast_type(t: str, dialect: str) -> str:
    if t == "string":
        return "VARCHAR" if dialect == "athena" else "STRING"
    if t == "timestamp":
        return "timestamp(6)" if dialect == "athena" else "TIMESTAMP_NTZ"
    if t == "int":
        return "INTEGER"
    return t.upper()


def values_cte(rows: list[dict], cols: list[tuple[str, str]], dialect: str) -> str:
    body = ",\n    ".join("(" + ", ".join(_lit(r.get(c), t, dialect) for c, t in cols) + ")" for r in rows)
    return f"SELECT * FROM (VALUES\n    {body}\n) AS t({', '.join(c for c, _ in cols)})"


def dependencies(cfg: dict, target: str, dialect: str = "athena") -> list[str]:
    """Every object the target reads, transitively, in dependency order (target last)."""
    sql = dict(views(cfg, dialect))
    out: list[str] = []

    def visit(name: str) -> None:
        if name in out:
            return
        for dep in re.findall(r"@@([a-z_]+)@@", sql.get(name, "")):
            visit(dep)
        out.append(name)

    visit(target)
    return out


def fixture_query(cfg: dict, target: str, tables: dict[str, tuple[list[dict], list[tuple[str, str]]]],
                  dialect: str, select: str = "SELECT * FROM {target}") -> str:
    """One query: the fixture tables and the views the target needs, as CTEs."""
    sql = dict(views(cfg, dialect))
    ctes = []
    for name in dependencies(cfg, target, dialect):
        if name in sql:
            ctes.append((name, sql[name]))
        else:
            rows, cols = tables[name]
            ctes.append((name, values_cte(rows, cols, dialect)))
    body = ",\n".join(f"{name} AS (\n{resolve(q, lambda n: n)}\n)" for name, q in ctes)
    return f"WITH {body}\n{select.format(target=target)}"
