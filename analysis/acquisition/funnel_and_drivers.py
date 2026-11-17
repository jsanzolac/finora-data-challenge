#!/usr/bin/env python3
"""Acquisition funnel built backwards from Won, and signals between new customers,
industry and S&M spend.

Run:  infra/.venv/bin/python analysis/acquisition/funnel_and_drivers.py
Out:  analysis/acquisition/output/report.md plus one CSV per table.

Source: the silver layer, built locally from data/*.csv with the same engine the
Glue silver job runs (etl/silver_build/engine.py), so the figures match the live
silver tables. data/ is only read.
"""

# =====================================================================================
# 1. CONVERSION RATES: edit this table. Each rate is the share of a stage that reaches
#    the next stage. The funnel is estimated backwards from Won: stage = next / rate.
# =====================================================================================
RATES = [
    # (stage,    next stage, rate)
    ("New",      "Working",  "0.80"),
    ("Working",  "Engaged",  "0.40"),
    ("Engaged",  "SQL",      "0.50"),
    ("SQL",      "Demo",     "0.70"),
    ("Demo",     "Proposal", "0.60"),
    ("Proposal", "Won",      "0.40"),
]
LAGS = [0, 1, 2, 3]          # spend this many months before the Won month
EXAMPLE_MONTH = "2024-10"     # month whose arithmetic is shown step by step

# Owner definitions: revenue amount x 10,000; S&M spend x 100,000,000 (currency not stated).
REVENUE_SCALE = 10_000
SPEND_SCALE = 100_000_000
# =====================================================================================

import csv
import hashlib
import io
import math
import sys
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from statistics import correlation

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "output"
sys.path.insert(0, str(ROOT / "etl"))

from common import config                                    # noqa: E402
from common.records import make_bronze, strip_bronze         # noqa: E402
from silver_build.engine import DatasetInput, build          # noqa: E402

FILES = {"transactions": ("transactions/Transactions.csv", "Transactions.csv"),
         "industry": ("industry/Industry.csv", "Industry.csv"),
         "sm_spend": ("s_and_m/S&M_spend.csv", "S&M_spend.csv")}
SPEND_COLS = ["PaidMedia", "Travel", "PublicidadNoWeb", "Freelance", "SoftwareTools", "Team", "PayrollExpenses"]
INDUSTRY_LABEL = {"RESTAURANTS": "Restaurants", "MANUFACTURING": "Manufacturing", "RETAIL": "Retail",
                  "TECHNOLOGY": "Technology", "PROFESSIONAL_SERVICES": "Professional services",
                  "HEALTHCARE": "Healthcare"}
STAGES = [r[0] for r in RATES] + [RATES[-1][1]]               # New ... Won


# ---------------------------------------------------------------------------- data
def load_silver():
    ts = "2026-11-17T00:00:00Z"
    inputs = {}
    for ds, (key, name) in FILES.items():
        raw = (ROOT / "data" / name).read_bytes()
        staging, _ = strip_bronze(make_bronze(raw, ts))
        inputs[ds] = DatasetInput(staging=staging, source_key=key,
                                  sha256=hashlib.sha256(raw).hexdigest(), ingested_at=ts)
    res = build(inputs, config.load(), "analysis", None)
    return res["silver"], res["W"]


def raw_first_paid_months():
    """Independent cross-check straight from the CSV: first month with amount > 0."""
    first = {}
    text = (ROOT / "data" / "Transactions.csv").read_text(encoding="utf-8-sig")
    for row in csv.DictReader(io.StringIO(text)):
        if not row["ID"] or Decimal(row["amount"]) <= 0:
            continue
        m, _, y = row["month"].split("/")
        ym = f"{int(y):04d}-{int(m):02d}"
        cid = int(row["ID"])
        if cid not in first or ym < first[cid]:
            first[cid] = ym
    return first


# ---------------------------------------------------------------------------- helpers
def q(x, places="0.1"):
    return Decimal(x).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def money(x):
    return f"{q(x, '1'):,}"


def millions(x):
    return f"{q(Decimal(x) / Decimal(1_000_000), '0.1'):,}"


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def write_csv(name, header, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def shift(month, k):
    y, m = map(int, month.split("-"))
    m -= k
    while m < 1:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def crit_r(n):
    """Rough two-sided 5% threshold for a Pearson r with n points (t ~ 2)."""
    return 2 / math.sqrt(n - 2 + 4)


def lagged_corr(won, spend, months, lag):
    pairs = [(won[m], spend[shift(m, lag)]) for m in months if shift(m, lag) in spend]
    xs, ys = [float(a) for a, _ in pairs], [float(b) for _, b in pairs]
    if len(pairs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None, len(pairs)
    return correlation(xs, ys), len(pairs)


# ---------------------------------------------------------------------------- funnel
def funnel(won, spend_total):
    """Counts per stage from Won backwards, and cost per unit = spend / count."""
    counts = {"Won": Decimal(won)}
    for stage, nxt, rate in reversed(RATES):
        counts[stage] = counts[nxt] / Decimal(rate)
    rows = []
    for st in STAGES:
        c = counts[st]
        cpu = spend_total / c if c else None
        rows.append((st, c, cpu, "Real" if st == "Won" else "Estimated"))
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    silver, W = load_silver()
    first_month, last_month = W[0], W[-1]
    customers = silver["customer"]
    cm = silver["customer_month"]

    # Won = first payment > 0 in the month, excluding customers whose first payment is in the first data month.
    won_customers = [c for c in customers if c["cohort_month"] and c["cohort_month"] != first_month]
    months = [m for m in W if m != first_month]
    industries = sorted({c["industry_code"] for c in customers}, key=lambda k: -sum(
        1 for c in won_customers if c["industry_code"] == k))

    # Cross-check against the raw file.
    raw_first = raw_first_paid_months()
    silver_first = {c["customer_id"]: c["cohort_month"] for c in customers if c["cohort_month"]}
    assert raw_first == silver_first, "first-payment months differ between raw CSV and silver"

    won = {m: 0 for m in months}
    won_ind = {k: {m: 0 for m in months} for k in industries}
    new_rev = {m: Decimal(0) for m in months}
    won_probable_left = {m: 0 for m in months}
    for c in won_customers:
        m = c["cohort_month"]
        won[m] += 1
        won_ind[c["industry_code"]][m] += 1
        new_rev[m] += c["first_paid_amount"] * REVENUE_SCALE
        if c["cohort_censoring"] == "probable_left":
            won_probable_left[m] += 1

    spend = {col: {} for col in SPEND_COLS}
    for r in silver["sm_spend"]:
        spend[r["category"]][r["month"]] = r["spend"] * SPEND_SCALE
    spend_total = {m: sum(spend[col][m] for col in SPEND_COLS) for m in W}
    spend_all = {**spend, "Total spend": spend_total}

    rep = ["# Acquisition funnel and new-customer signals", "",
           f"Source: silver layer built from `data/` with the Glue ETL engine; months {first_month} to {last_month}. "
           f"Won excludes the {sum(1 for c in customers if c['cohort_month'] == first_month)} customers whose first "
           f"payment is in {first_month}. Money in full units (revenue x {REVENUE_SCALE:,}, spend x {SPEND_SCALE:,}); "
           "currency not stated.", ""]

    # ---- rates table
    rep += ["## Conversion rates (edit `RATES` at the top of the script)", "",
            md_table(["From stage", "To stage", "Conversion rate"], [(a, b, r) for a, b, r in RATES]),
            "", f"Overall New → Won: {q(math.prod(Decimal(r) for _, _, r in RATES) * 100, '0.001')}%", ""]

    # ---- 1. full period
    tot_won = sum(won.values())
    tot_spend = sum(spend_total[m] for m in months)
    hdr = ["Stage", "Count", "Cost per unit", "Real or estimated"]
    full = funnel(tot_won, tot_spend)
    full_rows = [(s, f"{q(c):,}", money(cpu), kind) for s, c, cpu, kind in full]
    rep += ["## 1. Funnel built backwards from Won", "",
            f"### Full period ({months[0]} to {months[-1]}, {len(months)} months)", "",
            f"Won {tot_won:,} (real); total S&M spend {money(tot_spend)} (real).", "",
            md_table(hdr, full_rows), ""]
    write_csv("funnel_full_period.csv", hdr, [(s, f"{c:.6f}", f"{cpu:.2f}", k) for s, c, cpu, k in full])

    # ---- worked example
    m = EXAMPLE_MONTH
    lines = [f"### Arithmetic for {m}", "",
             f"1. **Won** = customers whose first payment above 0 is in {m} = **{won[m]}** (real).",
             f"2. **Total S&M spend** {m} = " + " + ".join(f"{col} {money(spend[col][m])}" for col in SPEND_COLS)
             + f" = **{money(spend_total[m])}** (real)."]
    val, step = Decimal(won[m]), 3
    for stage, nxt, rate in reversed(RATES):
        new = val / Decimal(rate)
        lines.append(f"{step}. **{stage}** = {nxt} ÷ {rate} = {q(val, '0.001')} ÷ {rate} = **{q(new, '0.001')}** (estimated).")
        val, step = new, step + 1
    lines.append(f"{step}. **Cost per unit** = total spend ÷ count at the stage, e.g. cost per Won = "
                 f"{money(spend_total[m])} ÷ {won[m]} = **{money(spend_total[m] / won[m])}**; cost per New = "
                 f"{money(spend_total[m])} ÷ {q(val, '0.001')} = **{money(spend_total[m] / val)}**.")
    rep += lines + [""]

    # ---- per month
    rep += ["### One table per month", ""]
    pm_csv = []
    for mm in months:
        rows = funnel(won[mm], spend_total[mm])
        rep += [f"#### {mm}  (Won {won[mm]}, spend {money(spend_total[mm])})", "",
                md_table(hdr, [(s, f"{q(c):,}", money(cpu) if cpu is not None else "n/a (Won = 0)", k)
                               for s, c, cpu, k in rows]), ""]
        pm_csv += [(mm, s, f"{c:.6f}", f"{cpu:.2f}" if cpu is not None else "", k) for s, c, cpu, k in rows]
    write_csv("funnel_by_month.csv", ["month"] + hdr, pm_csv)

    # ---- 2. monthly table
    ind_hdr = [f"Won {INDUSTRY_LABEL.get(k, k)}" for k in industries]
    mhdr = ["Month", "Won"] + ind_hdr + ["New revenue"] + SPEND_COLS + ["Total spend"]
    mrows, mcsv = [], []
    for mm in months:
        mrows.append([mm, won[mm]] + [won_ind[k][mm] for k in industries] + [money(new_rev[mm])]
                     + [millions(spend[c][mm]) for c in SPEND_COLS] + [millions(spend_total[mm])])
        mcsv.append([mm, won[mm]] + [won_ind[k][mm] for k in industries] + [f"{new_rev[mm]:.2f}"]
                    + [f"{spend[c][mm]:.0f}" for c in SPEND_COLS] + [f"{spend_total[mm]:.0f}"])
    mrows.append(["**Total**", tot_won] + [sum(won_ind[k].values()) for k in industries]
                 + [money(sum(new_rev.values()))] + [millions(sum(spend[c][x] for x in months)) for c in SPEND_COLS]
                 + [millions(tot_spend)])
    write_csv("monthly_won_revenue_spend.csv", mhdr, mcsv)
    rep += ["## 2. New customers vs. industry, customer payments and S&M spend", "",
            "### Monthly table (spend columns in millions; new revenue in full units)", "",
            md_table(mhdr, mrows), ""]

    # ---- correlations: spend x lag
    def corr_table(series, title, fname):
        hdr_c = ["Spend column"] + [f"{l} months earlier" for l in LAGS]
        rows, rcsv, ns = [], [], {}
        for col, sp in spend_all.items():
            cells = []
            for l in LAGS:
                r, n = lagged_corr(series, sp, months, l)
                ns[l] = n
                cells.append(r)
            rows.append([col] + [("n/a" if r is None else f"{r:+.2f}") for r in cells])
            rcsv.append([col] + [("" if r is None else f"{r:.4f}") for r in cells])
        rows.append(["*Months behind each r*"] + [str(ns[l]) for l in LAGS])
        rows.append(["*|r| needed for a 5% signal*"] + [f"{crit_r(ns[l]):.2f}" for l in LAGS])
        write_csv(fname, hdr_c, rcsv + [["months_n"] + [ns[l] for l in LAGS]])
        return [title, "", md_table(hdr_c, rows), ""]

    rep += ["### Correlation of Won with spend 0 to 3 months earlier (Pearson r)", ""]
    rep += corr_table(won, "#### All industries", "corr_won_vs_spend.csv")
    for k in industries:
        rep += corr_table(won_ind[k], f"#### {INDUSTRY_LABEL.get(k, k)}: that industry's Won vs. spend",
                          f"corr_won_{k.lower()}_vs_spend.csv")

    # sensitivity: without the 43 probable existing customers
    won_strict = {mm: won[mm] - won_probable_left[mm] for mm in months}
    sens = []
    for l in LAGS:
        r_all, n = lagged_corr(won, spend_total, months, l)
        r_strict, _ = lagged_corr(won_strict, spend_total, months, l)
        sens.append((l, f"{r_all:+.2f}", f"{r_strict:+.2f}", n))
    rep += ["#### Sensitivity: total spend vs. Won without the 43 customers silver tags as probably already customers", "",
            md_table(["Months earlier", "r (your Won definition)", "r (without the 43)", "Months"], sens), ""]

    # trend check: month-over-month changes (removes the shared trend / the mid-2023 spend cut)
    def diffs(series, ms):
        return {b: series[b] - series[a] for a, b in zip(ms, ms[1:])}
    dwon = diffs(won, months)
    dmonths = list(dwon)
    trend_rows = []
    for col in ["PaidMedia", "Total spend"]:
        dsp = diffs(spend_all[col], W)
        cells, ns = [], []
        for l in LAGS:
            r, n = lagged_corr(dwon, dsp, dmonths, l)
            cells.append("n/a" if r is None else f"{r:+.2f}")
            ns.append(n)
        trend_rows.append([col] + cells)
    trend_rows.append(["*Months behind each r*"] + [str(n) for n in ns])
    rep += ["#### Trend check: month-over-month change in Won vs. change in spend", "",
            md_table(["Spend column"] + [f"{l} months earlier" for l in LAGS], trend_rows), ""]
    cut = "2023-06"
    before, after = [x for x in months if x < cut], [x for x in months if x >= cut]
    avg = lambda d, ms: sum(Decimal(d[x]) for x in ms) / len(ms)
    cpw = lambda ms: sum(spend_total[x] for x in ms) / sum(won[x] for x in ms)
    rep += [md_table(["Period", "Months", "Won", "Won per month", "Total spend per month", "Cost per Won"],
                     [(f"{p[0]} to {p[-1]}", len(p), sum(won[x] for x in p), q(avg(won, p)),
                       money(avg(spend_total, p)), money(cpw(p))) for p in (before, after)]), ""]

    # ---- per industry profile
    paid_by_cust = defaultdict(list)
    for r in cm:
        if r["is_paying"] and r["amount"] is not None and r["amount"] > 0:
            paid_by_cust[r["customer_id"]].append(r["amount"] * REVENUE_SCALE)
    prof_hdr = ["Industry", "Customers", "of which Won (new)", "Average monthly payment",
                "Average monthly payment without outlier customers", "Average months paying"]
    prof, pcsv = [], []
    for k in industries:
        cs = [c for c in customers if c["industry_code"] == k]
        pays = [a for c in cs for a in paid_by_cust[c["customer_id"]]]
        pays_no = [a for c in cs if not c["is_outlier_customer"] for a in paid_by_cust[c["customer_id"]]]
        avg_pay, avg_no = sum(pays) / len(pays), sum(pays_no) / len(pays_no)
        avg_months = Decimal(sum(len(paid_by_cust[c["customer_id"]]) for c in cs)) / len(cs)
        n_won = sum(1 for c in won_customers if c["industry_code"] == k)
        prof.append([INDUSTRY_LABEL.get(k, k), len(cs), n_won, money(avg_pay), money(avg_no), f"{q(avg_months)}"])
        pcsv.append([k, len(cs), n_won, f"{avg_pay:.2f}", f"{avg_no:.2f}", f"{avg_months:.2f}"])
    write_csv("industry_profile.csv", prof_hdr, pcsv)
    rep += ["### Industry profile (all customers)", "",
            "Average monthly payment = mean of every paid customer-month (amount > 0). Average months paying = paid "
            f"months per customer up to {last_month} (recent customers have had less time, so this is a lower bound).",
            "", md_table(prof_hdr, prof), ""]

    (OUT / "report.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
    print("\n".join(rep))


if __name__ == "__main__":
    main()
