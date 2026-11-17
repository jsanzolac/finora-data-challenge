# Round 1: CFO position

**Stance.** The baseline's structure is sound; my objections concern money handling and what gold may claim. (1) All money is exact Decimal, converted once, and reconciled to control totals at every layer. (2) Gold carries CAC and payback only as *indicative*, with scope, basis and currency status attached: S&M is 2.3-5.8x the revenue in Transactions and no owner has confirmed scope. (3) No rule may silently remove revenue or spend; that distorts every board ratio. (4) Every gold number must trace to a staging file and be reproducible.

*All figures below were re-checked by me (`python3 -I` over `data/`, Decimal arithmetic, read-only S3) unless marked "doc only".*

## M1 Inventory

**Agree:** three datasets; staging equals `data/`.
**Change / add:** each staging ETag equals the local MD5 (1,302,387 / 49,402 / 2,063 bytes, SSE AES256). Versioning was never enabled on any of the four buckets, staging has no Object Lock, and bronze/silver/gold are empty. The raw source, the root of the audit trail, can be overwritten. I want versioning on staging and bronze too, not only silver and gold (CTO decides).

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CFO-01 | Bronze | all | Sidecar manifest per load (not a column): staging key, size, ETag/SHA-256, row count, control totals (sum of native amount, sum of native spend) | ETag = MD5; sum amount 221,441.504508; sum spend 77.818 | reject (load fails) | no |

**Verdicts:** no baseline rules.

## M2 Profile

**Agree:** structurally clean. **Change / add:** two doc corrections (rows 2 and 8).

| Figure | Result |
|---|---|
| Revenue 2022 / 2023 / Jan-Oct 2024 | 572,891,144.49 / 781,184,816.16 / 860,339,084.43 (matches) |
| Total revenue | **2,214,415,045.08**; docs say 2,214,415,000 (they scale a rounded native total) |
| S&M 2022 / 2023 / Jan-Oct 2024 | 3,295.6M / 2,510.7M / 1,975.5M; total 7,781.8M (matches) |
| S&M / Transactions revenue | 5.75x / 3.21x / 2.30x; 6.10x / 3.38x / 2.39x without customer 94; monthly 1.61x to 7.62x |
| Budget-like S&M | 34/34 totals within 0.002 of a 0.05 multiple; through May-23, 119/119 category cells within 0.05 pt of a whole-percent share; after Jun-23, 84/119 |
| Negative payroll | 5 months, -13.5M (0.17% of S&M). In 2023-11 and 2024-07, clipping to 0 puts the total 0.016 off the grid: a balancing plug |
| Precision | Native amount has at most 6 decimals, so x10,000 gives at most 2 (59,783 rows integer, 6,024 with two). S&M x1e8 is always an integer. Float and exact arithmetic differ in 2,436 rows |
| Customer 94 | 4.77% of revenue (105,647,524.08) |

Doc only: 0.21 price grid, industry profile. **Verdicts:** none.

## M3 Bronze security checks

**Agree:** the applicable set. **Add:** CFO-01. Bronze must leave `-$0.016`-type cells untouched; escaping would corrupt signed amounts.

| Rule | Verdict | Reason |
|---|---|---|
| BRZ-04 | keep | Flag-only is proportionate; the 5 hits are real negative spend |
| BRZ-06 | keep | Original strings kept, so no float parsing in bronze |

## M4 Silver quality rules

**Agree:** SQ-01, 02, 03, 04, 06, 08, 09.
**Change / add:** SQ-07 replacement: "`amount` parses as an exact decimal (<= 6 decimals): otherwise quarantine the row and block gold; `amount` < 0 is loaded and flagged (a credit note is legitimate)." A quarantined cell leaves a hole in the dense panel and silently understates revenue.

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CFO-02 | Silver | all | Control totals: bronze = silver + quarantine, per file and month, exact Decimal (sum, row count); mismatch blocks gold | Sums in CFO-01 | reject (run) | no |
| CFO-03 | Silver | transactions, sm_spend | Money columns carry `currency_code = 'UNCONFIRMED'`, labelled "currency units"; `$` is not interpreted | Owner definitions | flag | no |

| Rule | Verdict | Reason |
|---|---|---|
| SQ-05 | flag | "Reject duplicates" is ambiguous: quarantine all copies, block gold, never keep-first; 0 duplicates today |
| SQ-07 | flag | Change onFailure as above; min 0, 0 negatives |
| SQ-10 | flag | Native DECIMAL(9,3) fits (max 3.752); add full-value DECIMAL(18,2); a quarantined month must block that month in gold, or spend and CAC are understated |
| SQ-11 | keep | Inferred, flag-only; 5 negatives, all PayrollExpenses |
| SQ-12 | flag | Load orphans with industry `UNASSIGNED` and flag; quarantine would drop revenue (0 orphans today) |
| SQ-13 | keep | Both Jan-22 to Oct-24; CFO-06 limits CAC to overlapping months |

## M5 Silver business rules

**Agree:** SB-03, SB-04 (the pre-existing flag keeps Jan-22's 377 out of CAC), SB-07, SB-09.
**Change / add:**
- **SB-01:** `amount_value = amount x 10000`, exact Decimal; native `DECIMAL(14,6)`, full `DECIMAL(18,2)`, keep both; fail the run if more than 2 decimals result (never round); factor is versioned config from `owner_definitions.md`.
- **SB-02:** same with `DECIMAL(9,3)` x 1e8; monthly total = exact sum of the 7 categories, sign kept, never rescaled to the round total.
- **SB-10:** "Retain the sign as received; no abs, clip or reclassification; flag `is_negative_spend`; nature unconfirmed." "An adjustment" is an interpretation; a budget plug is as likely.
- **SB-05:** 46 customers (13 last paid Aug-24, 33 Sep-24) have 1-2 zero months and are neither active nor churned; add `provisional` (CRO/CDO own the definition).

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CFO-04 | Silver | transactions, sm_spend | Carry `revenue_basis = 'unconfirmed (cash-like)'` and `spend_basis = 'unconfirmed (budget-like)'` on every row | Catch-up 33.1% of gaps; M2 budget evidence | flag | yes |
| CFO-05 | Silver | cross | Scope gate: if annual S&M / Transactions revenue > 1.0, `scope_status = 'UNCONFIRMED'`; cleared only by a recorded owner answer | 5.75x / 3.21x / 2.30x | flag | yes |

| Rule | Verdict | Reason |
|---|---|---|
| SB-01 | flag | Change text; reject at run level is proportionate: a wrong scale is a 10,000x error |
| SB-02 | flag | Change text; x1e8 values are exact integers |
| SB-05 | flag | Provisional gap above |
| SB-06 | flag | Define "usual amount" as the last positive amount before the gap; 155/468 (33.1%) at +-5%, 152 at +-2%, 163 at +-10%; catch-ups are 1.6% of revenue: flag, never restate |
| SB-08 | keep | Without customer 94, 2022 S&M/revenue is 6.10x, not 5.75x; flag-only is right; list is versioned config |
| SB-10 | flag | Change text; 5 months, -13.5M |

## M6 Gold dimensional model

**Agree:** GLD-01 to GLD-04. Mark GLD-04's media / people / other grouping inferred (the dictionary says categories were inferred from names). Spend has no customer or industry key, so gold must not carry CAC by industry or channel.

**CAC readiness (indicative).** Spend Feb-22 to Oct-24 of 7,581.8M over 1,584 new customers gives CAC 4,786,490 currency units (media-only 2,828,346; by year 8.15M, 3.86M, 3.57M). New customers' mean first-3-month revenue is 53,201 (n=1,485). Payback is a **floor**: revenue basis, no gross margin, no cash.

| Share of S&M that belongs to these customers | CAC | Payback, months (GM 100%) |
|---|---|---|
| 100% | 4.79M | 90.0 |
| 50% | 2.39M | 45.0 |
| 25% | 1.20M | 22.5 |
| 10% | 0.48M | 9.0 |

A 12-month payback needs Transactions to be at most 13% of the base. Not supportable: GM-adjusted payback, LTV in currency (censored, no COGS), burn multiple, magic number, recognized-basis NRR. A 0-3 month spend lag moves CAC by up to -5%.

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CFO-06 | Gold | agg_month_kpis | Publish CAC/payback only with numerator, denominator, `scope_status`, `spend_basis`, `currency_code`. Blended only; pre-existing excluded (Jan-22 NULL); trailing 3/6/12-month windows (monthly new customers 17-108); revenue KPIs with and without outliers; `payback_months_revenue_floor` only, no GM column until COGS exists | Table above | flag | yes |
| CFO-07 | Gold | all | Every row carries `_run_id`, source key, source ETag, `rule_set_version`, `as_of_month`; build is deterministic and idempotent; churn flags stored per `as_of_month` | Flags change as months arrive; versioning off | reject (publish blocked) | no |

| Rule | Verdict | Reason |
|---|---|---|
| GLD-05 | flag | Add `currency_code`, basis, `is_outlier`, `is_pre_existing`, lineage (CFO-07); additive amounts only, no ratios |
| GLD-06 | keep | Month x category, native and full spend; add sign and `spend_basis`; total includes negatives |
| GLD-07 | flag | Optional is right; build only per CFO-06; a bare "CAC" is not publishable |

## M7 Verification

I tried to disprove each rule. Survivors need a changed onFailure: SQ-07 and SQ-12 (quarantine removes revenue: flag/load or block gold), SQ-05 (quarantine all copies, block gold). SB-01/SB-02 reject stays, applied per run. Verdicts are in M4-M6.

## M8 Open questions for the data owners

| # | Question | Blocks | Default meanwhile |
|---|---|---|---|
| 1 | Does Transactions cover the whole customer base? What does S&M cover (products, markets, brand)? | CAC, payback, LTV/CAC, S&M % of revenue | Indicative only |
| 2 | Currency of each file; FX if the board reports in another? Judgment, not evidence: Oct-24 revenue per payer of 57,800 reads as peso-class, not USD SMB pricing | Board pack, benchmarks | `UNCONFIRMED` |
| 3 | Revenue invoiced, collected or recognized? Net of tax? Is 0.21 a plan grid, tax or FX factor? | ARR/MRR, NRR, DSO | cash-like |
| 4 | S&M actual or budget? Negative payroll months? Jun-23 -48% break? Booked vs incurred timing? | CAC, variance analysis | budget-like |
| 5 | Do gross margin / COGS, cash, AR and headcount exist? | GM payback, runway, burn multiple | Not computed |
| 6 | Are closed months immutable; any restatement policy? | Reproducibility | Snapshot per run |
| 7 | Customer 94 (4.77%): multi-account or related party? | Concentration risk | With/without |

Others own: churn and retention rules (CRO, CDO), definitions (CDO), versioning and build (CTO), channel split (CMO).
