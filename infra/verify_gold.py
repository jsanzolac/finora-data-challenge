#!/usr/bin/env python3
"""Post-run verification of the gold build on Athena (workgroup finora-dl).

    figures     Read-only: §12 figures from finora_gold, the reconciliation to silver at the
                silver run's snapshots (counts and mismatch counts only; no HR value is printed),
                the funnel views and the correlations.
    rate-edit   Appends ONE clearly labelled test scenario through Athena (append-only, as a
                user would) and shows that v_funnel_month / v_funnel_period change on the next
                query. Non-base scenarios persist by design (spec §6.1-6.2: append-only, no
                retire mechanism), so it stays, labelled as a deploy check.

Usage: AWS_PROFILE=alegra-test infra/.venv/bin/python infra/verify_gold.py figures <gold_run_id> [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gold_athena_ddl import LOG, check_account, out, run  # noqa: E402
from stacks import names  # noqa: E402

DB = names.GOLD_DB
FAILS: list[str] = []


def expect(label: str, got, want) -> None:
    ok = got == want
    out(f"  [{'ok' if ok else 'FAIL'}] {label}: {got}" + ("" if ok else f" (expected {want})"))
    if not ok:
        FAILS.append(label)


def one(sql: str) -> dict:
    rows, st = run(sql, DB)
    return rows[0] if rows else {}


def figures(run_id: str) -> None:
    rep = json.loads(boto3.client("s3", region_name=names.REGION).get_object(
        Bucket=names.GOLD, Key=f"_runs/run_id={run_id}/gold_report.json")["Body"].read())
    silver_run, snaps = rep["silver_run_id"], rep["silver_snapshots"]
    out(f"gold run {run_id} ({rep['status']}), silver run {silver_run}, silver snapshots {snaps}")
    out("== row counts (finora_gold, main)")
    want = {"dim_month": 34, "dim_industry": 8, "dim_customer": 1961, "dim_spend_category": 8, "dim_funnel_stage": 7,
            "fact_acquisition": 1584, "fact_customer_month_revenue": 66674, "fact_sm_spend": 238,
            "agg_acquisition_month": 34, "agg_won_month_industry": 198, "agg_industry_profile": 18,
            "agg_won_spend_lag_corr": 1848, "gold_build_status": 1}
    for t, n in want.items():
        expect(t, int(one(f"SELECT count(*) AS n FROM {DB}.{t}")["n"]), n)
    expect("fact_sm_spend by hr_sensitive", one(f"""SELECT count_if(hr_sensitive) AS hr, count_if(NOT hr_sensitive) AS shared
        FROM {DB}.fact_sm_spend"""), {"hr": "102", "shared": "136"})
    expect("every row carries this run", one(f"""SELECT count(*) AS n FROM {DB}.fact_customer_month_revenue
        WHERE _run_id <> '{run_id}' OR _silver_run_id <> '{silver_run}'""")["n"], "0")
    out("== §12.2 / §12.3 headline figures")
    r = one(f"""SELECT sum(won_count) AS won, sum(won_new_logo_count) AS new_logo, sum(new_revenue_value) AS new_rev,
        sum(new_revenue_multiple_value) AS multiple, sum(new_revenue_new_logo_value) AS rev_nl,
        sum(new_revenue_run_rate_value) AS run_rate, sum(spend_total_value) AS spend
        FROM {DB}.agg_acquisition_month WHERE is_won_reportable""")
    expect("Won (user) / new logos", (r["won"], r["new_logo"]), ("1584", "1541"))
    expect("new revenue / of which multiples / new logos / run-rate",
           (r["new_rev"], r["multiple"], r["rev_nl"], r["run_rate"]),
           ("105482511.96", "10663744.35", "99728662.11", "99662644.41"))
    expect("spend, 33 Won months", r["spend"], "7581800000")
    expect("window start spend (Won NULL)", one(f"""SELECT a.won_count AS won, a.spend_total_value AS spend
        FROM {DB}.agg_acquisition_month a JOIN {DB}.dim_month d ON d.month_key = a.month_key WHERE d.is_window_start"""),
           {"won": None, "spend": "200000000"})
    expect("fact_customer_month_revenue Σ amount_value / paid rows",
           one(f"SELECT sum(amount_value) AS v, count_if(amount > 0) AS paid FROM {DB}.fact_customer_month_revenue"),
           {"v": "2214415045.08", "paid": "32971"})
    out("== reconciliation to silver at its run snapshots (FOR VERSION AS OF)")
    s = {t: int(v) for t, v in snaps.items()}
    expect("GC-01 Won = silver customers with cohort, not left", one(f"""SELECT
        (SELECT count(*) FROM finora_silver.customer FOR VERSION AS OF {s['customer']}
          WHERE cohort_month IS NOT NULL AND cohort_censoring <> 'left') AS silver,
        (SELECT count(*) FROM {DB}.fact_acquisition) AS gold"""), {"silver": "1584", "gold": "1584"})
    expect("GC-04 new revenue = silver first payments x 10,000", one(f"""SELECT
        (SELECT CAST(sum(first_paid_amount * 10000) AS DECIMAL(18,2)) FROM finora_silver.customer
          FOR VERSION AS OF {s['customer']} WHERE cohort_month IS NOT NULL AND cohort_censoring <> 'left') AS silver,
        (SELECT sum(first_paid_amount_value) FROM {DB}.fact_acquisition) AS gold"""),
           {"silver": "105482511.96", "gold": "105482511.96"})
    expect("GC-05 spend cells differing from silver (count only)", one(f"""SELECT count(*) AS n FROM (
        SELECT CAST(replace(s.month, '-', '') AS integer) AS month_key, s.category, s.spend_value
        FROM finora_silver.sm_spend FOR VERSION AS OF {s['sm_spend']} s) x
        JOIN {DB}.dim_spend_category c ON c.category_code = x.category
        FULL OUTER JOIN {DB}.fact_sm_spend f ON f.month_key = x.month_key AND f.category_key = c.category_key
        WHERE x.spend_value IS DISTINCT FROM f.spend_value""")["n"], "0")
    expect("GC-05 monthly totals = silver month_control.sm_value_total (mismatching months)", one(f"""SELECT count(*) AS n
        FROM finora_silver.month_control FOR VERSION AS OF {s['month_control']} m
        JOIN {DB}.agg_acquisition_month a ON a.month_key = CAST(replace(m.month, '-', '') AS integer)
        WHERE a.spend_total_value IS DISTINCT FROM m.sm_value_total""")["n"], "0")
    expect("GC-06 revenue fact rows and Σ amount_value = silver", one(f"""SELECT
        (SELECT count(*) FROM finora_silver.customer_month FOR VERSION AS OF {s['customer_month']}) AS silver_rows,
        (SELECT count(*) FROM {DB}.fact_customer_month_revenue) AS gold_rows,
        (SELECT sum(amount_value) FROM finora_silver.transactions FOR VERSION AS OF {s['transactions']}) AS silver_v,
        (SELECT sum(amount_value) FROM {DB}.fact_customer_month_revenue) AS gold_v"""),
           {"silver_rows": "66674", "gold_rows": "66674", "silver_v": "2214415045.08", "gold_v": "2214415045.08"})
    expect("GC-02 new logos = silver customer.is_new_logo = month_control.new_logos", one(f"""SELECT
        (SELECT count_if(is_new_logo) FROM finora_silver.customer FOR VERSION AS OF {s['customer']}) AS c,
        (SELECT sum(new_logos) FROM finora_silver.month_control FOR VERSION AS OF {s['month_control']}) AS m,
        (SELECT sum(won_new_logo_count) FROM {DB}.agg_acquisition_month) AS g"""), {"c": "1541", "m": "1541", "g": "1541"})
    out("== §12.5 funnel (v_funnel_period / v_funnel_month, base)")
    rows, _ = run(f"""SELECT stage_code, CAST(stage_count AS VARCHAR) AS n, CAST(cost_per_unit_value AS VARCHAR) AS c
        FROM {DB}.v_funnel_period WHERE scenario_id = 'base' AND won_definition = 'first_payment'
        AND period_type = 'full' ORDER BY stage_key""", DB)
    expect("full period, user Won", [(r["stage_code"], r["n"], r["c"]) for r in rows], [
        ("NEW", "58928.571429", "128660.85"), ("WORKING", "47142.857143", "160826.06"),
        ("ENGAGED", "18857.142857", "402065.15"), ("SQL", "9428.571429", "804130.30"),
        ("DEMO", "6600.000000", "1148757.58"), ("PROPOSAL", "3960.000000", "1914595.96"),
        ("WON", "1584.000000", "4786489.90")])
    expect("full period, new logo: New / Won cost", one(f"""SELECT
        max(CASE WHEN stage_code = 'NEW' THEN CAST(stage_count AS VARCHAR) END) AS new_n,
        max(CASE WHEN stage_code = 'WON' THEN CAST(cost_per_unit_value AS VARCHAR) END) AS won_c
        FROM {DB}.v_funnel_period WHERE scenario_id = 'base' AND won_definition = 'new_logo' AND period_type = 'full'"""),
           {"new_n": "57328.869048", "won_c": "4920051.91"})
    expect("2024-10: New / Won", one(f"""SELECT
        max(CASE WHEN stage_code = 'NEW' THEN CAST(stage_count AS VARCHAR) || ' / ' || CAST(cost_per_unit_value AS VARCHAR) END) AS new,
        max(CASE WHEN stage_code = 'WON' THEN CAST(stage_count AS VARCHAR) || ' / ' || CAST(cost_per_unit_value AS VARCHAR) END) AS won
        FROM {DB}.v_funnel_month WHERE scenario_id = 'base' AND won_definition = 'first_payment' AND month = '2024-10'"""),
           {"new": "1860.119048 / 107520.00", "won": "50.000000 / 4000000.00"})
    rows, _ = run(f"""SELECT period_id, CAST(won_count AS VARCHAR) AS won, CAST(cost_per_unit_value AS VARCHAR) AS c
        FROM {DB}.v_funnel_period WHERE scenario_id = 'base' AND won_definition = 'first_payment' AND stage_code = 'WON'
        AND period_type IN ('sm_regime', 'year') ORDER BY period_id""", DB)
    expect("regimes and years: Won / cost per Won", {r["period_id"]: (r["won"], r["c"]) for r in rows}, {
        "2022": ("380", "8146315.79"), "2023": ("650", "3862615.38"), "2024": ("554", "3565884.48"),
        "from_2023_06": ("978", "3047955.01"), "pre_2023_06": ("606", "7592244.22")})
    expect("v_funnel_scenario_status: base valid", one(f"""SELECT status, failed_checks FROM {DB}.v_funnel_scenario_status
        WHERE scenario_id = 'base'"""), {"status": "valid", "failed_checks": ""})
    out("== correlations (§12.8, §7.5)")
    rows, _ = run(f"""SELECT method, lag_months, CAST(r AS VARCHAR) AS r, n_pairs, is_signal_5pct FROM {DB}.agg_won_spend_lag_corr
        WHERE won_definition = 'first_payment' AND scope_code = 'ALL' AND spend_series = 'TOTAL'
        ORDER BY method, lag_months""", DB)
    expect("TOTAL, company, user Won (method, lag, r, n)", [(r["method"], r["lag_months"], r["r"], r["n_pairs"]) for r in rows], [
        ("diff", "0", "0.1412", "32"), ("diff", "1", "-0.1790", "32"), ("diff", "2", "-0.0895", "31"),
        ("diff", "3", "0.1377", "30"), ("level", "0", "-0.4795", "33"), ("level", "1", "-0.4964", "33"),
        ("level", "2", "-0.4190", "32"), ("level", "3", "-0.2609", "31"), ("within_regime", "0", "-0.1586", "33"),
        ("within_regime", "1", "-0.2523", "33"), ("within_regime", "2", "0.0363", "32"),
        ("within_regime", "3", "0.2266", "31")])
    rows, _ = run(f"""SELECT method, won_definition, scope_type, tests, signals, CAST(expected_by_chance AS VARCHAR) AS e
        FROM {DB}.v_corr_signal_summary ORDER BY won_definition, method, scope_type""", DB)
    expect("v_corr_signal_summary (signals)", {(r["won_definition"], r["method"], r["scope_type"]): r["signals"] for r in rows}, {
        ("first_payment", "diff", "company"): "3", ("first_payment", "diff", "industry"): "11",
        ("first_payment", "level", "company"): "30", ("first_payment", "level", "industry"): "110",
        ("first_payment", "within_regime", "company"): "3", ("first_payment", "within_regime", "industry"): "17",
        ("new_logo", "diff", "company"): "3", ("new_logo", "diff", "industry"): "13",
        ("new_logo", "level", "company"): "32", ("new_logo", "level", "industry"): "123",
        ("new_logo", "within_regime", "company"): "3", ("new_logo", "within_regime", "industry"): "14"})
    expect("v_acquisition_month rows / v_sm_spend_shared rows", one(f"""SELECT
        (SELECT count(*) FROM {DB}.v_acquisition_month) AS m, (SELECT count(*) FROM {DB}.v_sm_spend_shared) AS s"""),
           {"m": "33", "s": "136"})
    expect("gold_build_status", one(f"""SELECT _run_id, _silver_run_id, data_complete_through, base_rates_match_seed,
        controls_passed FROM {DB}.gold_build_status"""), {"_run_id": run_id, "_silver_run_id": silver_run,
                                                          "data_complete_through": "2024-10",
                                                          "base_rates_match_seed": "true", "controls_passed": "true"})


SCENARIO = "cto_deploy_check_20261117"


def rate_edit() -> None:
    q = (f"SELECT stage_code, CAST(stage_count AS VARCHAR) AS n FROM {DB}.v_funnel_period WHERE scenario_id = '{SCENARIO}' "
         "AND won_definition = 'first_payment' AND period_type = 'full' AND stage_code IN ('NEW', 'WON') ORDER BY stage_key")
    before, _ = run(q, DB)
    expect(f"{SCENARIO} absent from v_funnel_period before the insert", before, [])
    sql = f"""INSERT INTO {DB}.funnel_conversion_rate
SELECT '{SCENARIO}', 'CTO deploy check: SQL to Demo at 80% (test, not a business assumption)', from_stage_code,
       to_stage_code, CASE WHEN from_stage_code = 'SQL' THEN CAST('0.8000' AS DECIMAL(5,4)) ELSE rate END,
       CAST(current_timestamp AT TIME ZONE 'UTC' AS timestamp(6)), 'cto-deploy-check',
       'Deploy verification of the rate-edit flow, 2026-11-17; test scenario, not a business assumption'
FROM {DB}.v_funnel_rate_current WHERE scenario_id = 'base'"""
    out(sql)
    run(sql, DB)
    after, _ = run(q, DB)
    expect(f"{SCENARIO} in v_funnel_period on the next query (New, Won)", [(r["stage_code"], r["n"]) for r in after],
           [("NEW", "51562.500000"), ("WON", "1584.000000")])
    m = one(f"""SELECT count(*) AS n FROM {DB}.v_funnel_month WHERE scenario_id = '{SCENARIO}'""")
    expect(f"{SCENARIO} rows in v_funnel_month (2 definitions x 33 months x 7 stages)", m["n"], "462")
    c = one(f"""SELECT CAST(won_implied_same_new AS VARCHAR) AS w, CAST(cost_per_won_implied_value AS VARCHAR) AS c
        FROM {DB}.v_funnel_scenario_compare WHERE scenario_id = '{SCENARIO}' AND won_definition = 'first_payment'
        AND period_type = 'full'""")
    expect("§12.6 via the views", c, {"w": "1810.285714", "c": "4188178.66"})
    expect("status", one(f"SELECT status FROM {DB}.v_funnel_scenario_status WHERE scenario_id = '{SCENARIO}'"),
           {"status": "valid"})
    expect("base unchanged", one(f"""SELECT CAST(stage_count AS VARCHAR) AS n FROM {DB}.v_funnel_period
        WHERE scenario_id = 'base' AND won_definition = 'first_payment' AND period_type = 'full' AND stage_code = 'NEW'"""),
           {"n": "58928.571429"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["figures", "rate-edit"])
    ap.add_argument("run_id", nargs="?")
    ap.add_argument("--out")
    a = ap.parse_args()
    check_account()
    out(f"# verify_gold.py {a.command} {a.run_id or ''}")
    figures(a.run_id) if a.command == "figures" else rate_edit()
    out(f"{len(FAILS)} failures" + (f": {FAILS}" if FAILS else ""))
    if a.out:
        with open(a.out, "a", encoding="utf-8") as f:
            f.write("\n".join(LOG) + "\n\n")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
