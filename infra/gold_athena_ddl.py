#!/usr/bin/env python3
"""Gold deploy step (Athena, workgroup finora-dl), docs/gold_acquisition_model.md §6.5 and §14.1.

    precheck    Read-only. Runs every view's Athena (Trino) SQL over inline VALUES fixtures
                built from today's files (no table is read or created) and compares each
                result with the exact Python reference and §12. No HR value is sent: the
                fact_sm_spend fixture carries placeholder amounts.
    rate-table  One-time, idempotent: CREATE TABLE IF NOT EXISTS finora_gold.funnel_conversion_rate,
                then the base seed only if no row with scenario_id = 'base' exists.
    views       CREATE OR REPLACE VIEW for the §7 views (needs the gold tables: run after
                the first gold build). Idempotent.
    sql         Print the DDL.

Usage: AWS_PROFILE=alegra-test infra/.venv/bin/python infra/gold_athena_ddl.py <command> [--out FILE]
The account is checked first (962482423379); credentials are never printed.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "etl"))
sys.path.insert(0, str(ROOT / "etl" / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gold_build import ddl, engine, funnel, gconfig, schemas  # noqa: E402
from stacks import names  # noqa: E402

ACCOUNT = "962482423379"
LOG: list[str] = []


def out(line: str = "") -> None:
    print(line)
    LOG.append(line)


def athena():
    return boto3.client("athena", region_name=names.REGION)


def run(sql: str, database: str | None = None, timeout: int = 120) -> tuple[list[dict], dict]:
    kw = {"QueryString": sql, "WorkGroup": names.ATHENA_WORKGROUP}
    if database:
        kw["QueryExecutionContext"] = {"Database": database}
    a = athena()
    qid = a.start_query_execution(**kw)["QueryExecutionId"]
    t0 = time.time()
    while True:
        q = a.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = q["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        if time.time() - t0 > timeout:
            raise TimeoutError(qid)
        time.sleep(0.5)
    if state != "SUCCEEDED":
        raise RuntimeError(f"{qid} {state}: {q['Status'].get('StateChangeReason', '')[:800]}")
    rows, token = [], None
    while True:
        kw = {"QueryExecutionId": qid, "MaxResults": 1000}
        if token:
            kw["NextToken"] = token
        r = a.get_query_results(**kw)
        rows += [[c.get("VarCharValue") for c in x["Data"]] for x in r["ResultSet"]["Rows"]]
        token = r.get("NextToken")
        if not token:
            break
    stats = q.get("Statistics", {})
    if not rows or sql.lstrip().upper().startswith(("INSERT", "CREATE")):
        return [], stats
    return [dict(zip(rows[0], x)) for x in rows[1:]], stats


def check_account() -> None:
    acct = boto3.client("sts", region_name=names.REGION).get_caller_identity()["Account"]
    if acct != ACCOUNT:
        sys.exit(f"wrong account {acct}")


# --------------------------------------------------------------------------- #
# precheck                                                                    #
# --------------------------------------------------------------------------- #

def _d(v):
    return None if v is None else Decimal(v)


def precheck() -> int:
    from gold_helpers import golden_gold, scenario, seed
    from test_gold import gr_cases

    G = gconfig.load()
    g = golden_gold()
    T = g["tables"]
    now = datetime.utcnow()
    rates = seed() + scenario("sql_demo_080", "SQL to Demo at 80%", {"SQL": "0.8000"})
    rates += scenario("tiny_rates", "extreme but valid", {f: "0.0001" for f, _ in G["transitions"]})
    for check, rs in gr_cases().items():
        sid = rs[0]["scenario_id"] if check == "GR-01" else f"case_{check[-2:]}"
        rates += [dict(r, scenario_id=sid) for r in rs]
    rates += scenario("later", "future", ts=now + timedelta(hours=1))
    rate_cols = [(n, t) for n, t in schemas.RATE_COLUMNS]
    fake_sm = [{"month_key": 202410, "category_key": k, "spend": Decimal("1.000"), "spend_value": Decimal(k * 1000),
                "is_negative_spend": False, "is_restated": False, "is_unit_tripwire": False, "hr_sensitive": hr,
                **{c: "x" for c, _ in schemas.ROW_LINEAGE if c != "_source_line"}, "_source_line": k,
                **{c: T["fact_sm_spend"][0][c] for c, _ in schemas.LINEAGE}}
               for k, hr in ((1, False), (2, False), (3, False), (4, True), (5, False), (6, True), (7, True))]
    corr_subset = [r for r in T["agg_won_spend_lag_corr"] if r["spend_series"] in ("TOTAL", "Team")
                   and r["scope_code"] in ("ALL", "HEALTHCARE")]
    wmi_cols = [("month_key", "int"), ("industry_key", "int"), ("won_count", "int")]
    corr_cols = [(c, t) for c, t in schemas.COLUMNS["agg_won_spend_lag_corr"] if not c.startswith("_")
                 and c != "as_of_month"]
    tables = {
        "funnel_conversion_rate": (rates, rate_cols),
        "dim_funnel_stage": (T["dim_funnel_stage"], schemas.TABLES["dim_funnel_stage"]),
        "agg_acquisition_month": (T["agg_acquisition_month"], schemas.TABLES["agg_acquisition_month"]),
        "dim_month": (T["dim_month"], schemas.TABLES["dim_month"]),
        "gold_build_status": (T["gold_build_status"], schemas.TABLES["gold_build_status"]),
        "agg_won_month_industry": (T["agg_won_month_industry"], wmi_cols),
        "fact_sm_spend": (fake_sm, schemas.COLUMNS["fact_sm_spend"]),
        "agg_won_spend_lag_corr": (corr_subset, corr_cols),
    }
    dm = {r["month_key"]: r for r in T["dim_month"]}
    months = [dict(r, month=dm[r["month_key"]]["month"], year_quarter=dm[r["month_key"]]["year_quarter"],
                   sm_regime=dm[r["month_key"]]["sm_regime"]) for r in T["agg_acquisition_month"] if r["is_won_reportable"]]
    status = funnel.scenario_status(rates, G, now)
    valid = {k: v["rates"] for k, v in status.items() if v["status"] == "valid"}
    fails = 0
    total_bytes = 0

    def q(target, select="SELECT * FROM {target}"):
        nonlocal total_bytes
        sql = ddl.fixture_query(G, target, tables, "athena", select)
        rows, st = run(sql)
        total_bytes += st.get("DataScannedInBytes", 0)
        out(f"  {target}: {len(rows)} rows, query {len(sql):,} chars, {st.get('EngineExecutionTimeInMillis')} ms, "
            f"scanned {st.get('DataScannedInBytes', 0)} B")
        return rows

    def expect(name, ok, detail=""):
        nonlocal fails
        out(f"  [{'ok' if ok else 'FAIL'}] {name}{'' if ok else ': ' + detail}")
        fails += 0 if ok else 1

    out("== status / current")
    st = {r["scenario_id"]: r for r in q("v_funnel_scenario_status")}
    want = {k: (v["status"], ",".join(v["failed_checks"])) for k, v in status.items()}
    got = {k: (r["status"], r["failed_checks"]) for k, r in st.items()}
    expect("v_funnel_scenario_status = reference (GR-01..06, future changed_at, extreme rates)", got == want,
           f"{got} != {want}")
    out("== v_funnel_month")
    fm = q("v_funnel_month")
    n = bad = 0
    gm = {(r["scenario_id"], r["won_definition"], r["month"], r["stage_code"]): r for r in fm}
    for sid, rt in valid.items():
        for d in G["won_definitions"]:
            for m, srows in funnel.funnel_month(months, rt, d, "2024-10", G).items():
                for r in srows:
                    v = gm.get((sid, d, m, r["stage_code"]))
                    n += 1
                    if v is None or (_d(v["stage_count"]), _d(v["cost_per_unit_value"]), v["cost_null_reason"],
                                     _d(v["downstream_rate_product"])) != (r["stage_count"], r["cost_per_unit_value"],
                                                                           r["cost_null_reason"],
                                                                           r["downstream_rate_product"]):
                        bad += 1
    expect(f"v_funnel_month: {n} rows = exact reference (incl. tiny_rates, no overflow)", bad == 0 and n == len(fm),
           f"{bad} mismatches, {n} vs {len(fm)}")
    out("== v_funnel_period")
    fp = q("v_funnel_period")
    gp = {(r["scenario_id"], r["won_definition"], r["period_type"], r["period_id"], r["stage_code"]): r for r in fp}
    n = bad = 0
    for sid, rt in valid.items():
        for d in G["won_definitions"]:
            for (pt, pid), (extra, srows) in funnel.funnel_period(months, rt, d, "2024-10", G).items():
                for r in srows:
                    v = gp.get((sid, d, pt, pid, r["stage_code"]))
                    n += 1
                    if v is None or (_d(v["stage_count"]), _d(v["cost_per_unit_value"]), _d(v["won_per_month"]),
                                     _d(v["spend_per_month_value"])) != (
                            r["stage_count"], r["cost_per_unit_value"], extra["won_per_month"],
                            extra["spend_per_month_value"]):
                        bad += 1
    expect(f"v_funnel_period: {n} rows = exact reference", bad == 0 and n == len(fp), f"{bad} mismatches")
    full = {r["stage_code"]: (r["stage_count"], r["cost_per_unit_value"]) for k, r in gp.items()
            if k[:4] == ("base", "first_payment", "full", "full")}
    expect("§12.5 base, full period: New 58928.571429 / 128660.85, Won 1584 / 4786489.90",
           full.get("NEW") == ("58928.571429", "128660.85") and full.get("WON") == ("1584.000000", "4786489.90"),
           str(full))
    out("== v_funnel_scenario_compare")
    c = {(r["scenario_id"], r["won_definition"], r["period_type"], r["period_id"]): r
         for r in q("v_funnel_scenario_compare")}
    x = c[("sql_demo_080", "first_payment", "full", "full")]
    expect("§12.6 sql_demo_080: 1810.285714 / +226.285714 / +14.285714 / 51562.5 / -7366.071429 / 4188178.66",
           (x["won_implied_same_new"], x["won_implied_delta"], x["won_implied_delta_pct"], x["new_required_same_won"],
            x["new_required_delta"], x["cost_per_won_implied_value"]) ==
           ("1810.285714", "226.285714", "14.285714", "51562.500000", "-7366.071429", "4188178.66"), str(x))
    bad = 0
    for (sid, d, pt, pid), r in c.items():
        ms = funnel.periods(months, "2024-10")[(pt, pid)]
        won = sum(funnel.won_of(m, d) for m in ms)
        ref = funnel.compare(won, sum(m["spend_total_value"] for m in ms), valid[sid], valid["base"])
        for k in ("won_implied_same_new", "won_implied_delta", "won_implied_delta_pct", "new_required_same_won",
                  "new_required_delta", "new_required_delta_pct", "cost_per_won_implied_value"):
            bad += _d(r[k]) != ref[k]
    expect(f"v_funnel_scenario_compare: {len(c)} rows x 7 columns = exact reference", bad == 0, f"{bad} mismatches")
    out("== v_funnel_rate_sensitivity")
    sens = {(r["scenario_id"], r["won_definition"], r["from_stage_code"]): r for r in q("v_funnel_rate_sensitivity")}
    bad = 0
    for (sid, d, f), r in sens.items():
        won = sum(funnel.won_of(m, d) for m in months)
        ref = funnel.sensitivity(won, valid[sid][f])
        bad += any(_d(r[k]) != ref[k] for k in ref)
    expect(f"v_funnel_rate_sensitivity: {len(sens)} rows = exact reference", bad == 0, f"{bad} mismatches")
    out("== v_acquisition_month / _finance / v_sm_spend_shared / v_corr_signal_summary")
    am = q("v_acquisition_month")
    expect("v_acquisition_month: 33 rows, Won 1584, spend 7581800000",
           len(am) == 33 and sum(int(r["won_count"]) for r in am) == 1584
           and sum(Decimal(r["spend_total_value"]) for r in am) == Decimal("7581800000"))
    fin = {r["month"]: r for r in q("v_acquisition_month_finance")}
    expect("v_acquisition_month_finance pivots the HR partition (placeholder values)",
           (fin["2024-10"]["spend_freelance_value"], fin["2024-10"]["spend_team_value"],
            fin["2024-10"]["spend_payroll_expenses_value"]) == ("4000", "6000", "7000"), str(fin["2024-10"]))
    sh = q("v_sm_spend_shared")
    expect("v_sm_spend_shared keeps only hr_sensitive = false", sorted(int(r["category_key"]) for r in sh) == [1, 2, 3, 5])
    ss = {(r["method"], r["won_definition"], r["scope_type"]): r for r in q("v_corr_signal_summary")}
    want = {}
    for r in corr_subset:
        k = (r["method"], r["won_definition"], "company" if r["scope_code"] == "ALL" else "industry")
        w = want.setdefault(k, [0, 0, 0])
        w[0] += 1
        w[1] += r["r"] is not None
        w[2] += bool(r["is_signal_5pct"])
    expect("v_corr_signal_summary = reference on a 48-row subset",
           {k: [int(v["tests"]), int(v["tests_with_r"]), int(v["signals"])] for k, v in ss.items()} == want
           and all(Decimal(v["expected_by_chance"]) == Decimal("0.05") * int(v["tests_with_r"]) for v in ss.values()))
    out("== API INSERT expression")
    r, _ = run("SELECT CAST(current_timestamp AT TIME ZONE 'UTC' AS timestamp(6)) AS t, "
               "CAST('0.8000' AS DECIMAL(5,4)) AS r, 'O''Brien' AS s")
    expect("timestamp(6) in UTC, DECIMAL(5,4), quote escaping", r[0]["r"] == "0.8000" and r[0]["s"] == "O'Brien"
           and abs((datetime.fromisoformat(r[0]["t"][:19]) - datetime.utcnow()).total_seconds()) < 120, str(r))
    out(f"precheck: {fails} failures; data scanned {total_bytes} B")
    return fails


# --------------------------------------------------------------------------- #
# rate-table, views                                                           #
# --------------------------------------------------------------------------- #

def rate_table() -> None:
    G = gconfig.load()
    db = names.GOLD_DB
    out(ddl.rate_table_ddl(names.GOLD, db))
    run(ddl.rate_table_ddl(names.GOLD, db), db)
    rows, _ = run(f"SELECT count(*) AS n FROM {db}.{schemas.RATE_TABLE} WHERE scenario_id = 'base'", db)
    n = int(rows[0]["n"])
    if n == 0:
        sql = ddl.insert_rows_sql(ddl.seed_rows(G), db)
        out(sql)
        run(sql, db)
        out("seeded base (6 rows)")
    else:
        out(f"base already present ({n} rows): not re-seeded")
    rows, _ = run(f"SELECT scenario_id, from_stage_code, to_stage_code, CAST(rate AS VARCHAR) AS rate, "
                  f"CAST(changed_at AS VARCHAR) AS changed_at, changed_by, change_reason "
                  f"FROM {db}.{schemas.RATE_TABLE} ORDER BY scenario_id, changed_at, from_stage_code", db)
    for r in rows:
        out("  " + " | ".join(str(v) for v in r.values()))


def create_views(only: list[str] | None = None) -> None:
    G = gconfig.load()
    db = names.GOLD_DB
    for name, sql in ddl.create_view_statements(G, db):
        if only and name not in only:
            continue
        run(sql, db)
        rows, st = run(f"SELECT count(*) AS n FROM {db}.{name}", db)
        out(f"view {db}.{name}: {rows[0]['n']} rows (scanned {st.get('DataScannedInBytes', 0)} B)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["precheck", "rate-table", "views", "sql"])
    ap.add_argument("--out")
    ap.add_argument("--only", action="append", help="views: create only these views")
    a = ap.parse_args()
    if a.command == "sql":
        G = gconfig.load()
        print(ddl.rate_table_ddl(names.GOLD) + ";\n")
        for _, sql in ddl.create_view_statements(G):
            print(sql + ";\n")
        return
    check_account()
    out(f"# gold_athena_ddl.py {a.command} at {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')} "
        f"(workgroup {names.ATHENA_WORKGROUP}, account {ACCOUNT})")
    rc = 0
    if a.command == "precheck":
        rc = 1 if precheck() else 0
    elif a.command == "rate-table":
        rate_table()
    else:
        create_views(a.only)
    if a.out:
        with open(a.out, "a", encoding="utf-8") as f:
            f.write("\n".join(LOG) + "\n\n")
    sys.exit(rc)


if __name__ == "__main__":
    main()
