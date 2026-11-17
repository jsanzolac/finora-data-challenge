# ETL review: baseline proposal and agenda

> Starting point for Finora's executive review of the data-lake ETL (CRO, CFO, CMO, CDO, CTO). It stands in for the `etl-discover` workflow (`.claude/workflows/etl-discover.js`), which could not run in this session, and covers the same ground.
> The proposal comes from profiling the three files plus the owner definitions. It has **not been verified yet**: challenging it is the point of the review.

## How the review works

| Round | Who | Output |
|---|---|---|
| 1. Positions | All five executives, independently | `round1/<role>.md` |
| 2. Debate | All five, after reading every round-1 position; each acts as a skeptic of the others' rules | `round2/<role>.md` |
| 3. Resolution | The CDO settles the rules, then the CTO settles the ETL design | `round3/cdo_rules.md`, `round3/cto_design.md` |
| Final | The main session | `ETL_FINDINGS.md` |

## Agenda (the matters the workflow was meant to cover)

| # | Matter |
|---|---|
| M1 | Inventory: the files in staging and how they group into datasets |
| M2 | Profile: data-quality findings (types, nulls, keys, duplicates, formats, encoding, anomalies, PII) |
| M3 | Bronze security checks: only the ones that apply, each with a reason |
| M4 | Silver quality rules |
| M5 | Silver business rules, and which ones are inferred (not stated by the owners) |
| M6 | Gold dimensional model: facts and dimensions that support drill-down, not only precomputed metrics |
| M7 | Verification: try to disprove each rule and give a verdict of keep, flag or drop |
| M8 | Open questions for the data owners |

## Layer contracts (fixed by the user)

- **Bronze:** the security checks plus exactly ONE new column, `_ingested_at` (UTC). No other changes.
- **Silver:** quality and business rules. Inferred business rules are marked as inferred.
- **Gold:** a dimensional model (facts and dimensions) that supports drill-down, not only precomputed metrics.
- Each rule has an id, layer, dataset, rule, evidence, onFailure (reject / quarantine / flag), and inferred (true / false).

## Inputs

- **Staging (read-only):** `s3://al-test-dl-staging/` holds `transactions/Transactions.csv`, `industry/Industry.csv` and `s_and_m/S&M_spend.csv`. The same files are in `data/`.
- **Owner definitions (authoritative):** `docs/data_semantics/owner_definitions.md`. Revenue `amount` × 10,000; S&M spend × 100,000,000; the currency is not stated.
- **Dictionaries and profiles:** `docs/data_semantics/`.

## Key findings behind the proposal

- The files are structurally clean: no nulls, no duplicate keys, consistent formats. The quirks are a UTF-8 BOM in all three files, an empty last record in `Industry.csv`, and a key that differs between files (`"Cliente 94"` vs `94`).
- Values are scaled, by a different factor per file. Combine them only after converting.
- `Transactions.csv` is a dense customer × month table (1,961 × 34, zero-filled), not a transaction log.
- Zeros are ambiguous: about ⅓ of gaps end in a catch-up payment.
- The window is censored at both ends: 377 customers were already paying in Jan-2022, and 1,678 are still paying in Oct-2024.
- Customer 94 accounts for 4.8% of all revenue.
- S&M looks budget-allocated: round totals split by percentages, PayrollExpenses negative in 5 months, and a structural break in Jun-2023.
- In full amounts, S&M is 2.3–5.8× the revenue in Transactions, so Transactions may be only part of the customer base.

## Baseline rules

### Bronze

| ID | Dataset | Rule | Evidence | On failure | Inferred |
|---|---|---|---|---|---|
| BRZ-01 | all | Content is CSV text that matches the `.csv` extension and Content-Type | All three files are UTF-8 CSV text | reject | no |
| BRZ-02 | all | Size check: reject empty files; quarantine files above an agreed ceiling (proposed 100 MB) | Today the files are 2 KB–1.3 MB | reject / quarantine | no |
| BRZ-03 | all | Malware scan before loading | Every upload is untrusted | quarantine | no |
| BRZ-04 | all | Detect CSV formula injection: cells starting with `=`, `+`, `-`, `@`, tab or CR | Only 5 cells match today, the legitimate negative PayrollExpenses values (`-$0.016`) | flag | no |
| BRZ-05 | all | Detect unsafe object names (traversal, control characters, shell/URL metacharacters, non-ASCII) | `S&M_spend.csv` contains `&` | flag | no |
| BRZ-06 | all | Add exactly one column, `_ingested_at` (UTC load timestamp); keep every value as the original string; no other change | Layer contract | reject (load fails) | no |

Not applicable: macros (plain CSV), zip bombs (not compressed), PII masking (no names, emails or tax IDs; customers are pseudonymous `Cliente N`; re-check if new columns arrive).

### Silver: quality rules

| ID | Dataset | Rule | Evidence | On failure | Inferred |
|---|---|---|---|---|---|
| SQ-01 | all | Read as UTF-8, strip the BOM, comma-delimited, header required | All files have a BOM, commas, a header | reject file | no |
| SQ-02 | industry | Drop fully empty records | 1 trailing `,` record | flag | no |
| SQ-03 | industry | `ID` not null, unique, matches `^Cliente \d+$`; derive integer `customer_id` | 1,961 unique, 100% pattern | quarantine row | no |
| SQ-04 | industry | `Industria` is one of the 6 known values; map it to an ASCII code | 6 values, 0 variants | quarantine row | no |
| SQ-05 | transactions | `ID` is an integer; (`ID`, `month`) is unique | 0 duplicates | reject duplicates | no |
| SQ-06 | transactions | `month` parses as `%m/%d/%Y` and is a month-end; convert to year-month | 100% month-end | quarantine row | no |
| SQ-07 | transactions | `amount` is numeric and ≥ 0 | min 0, 0 negatives | quarantine row | no |
| SQ-08 | transactions | Dense panel: every customer has every month | 1,961 × 34 = 66,674 | flag | no |
| SQ-09 | sm_spend | `Month` is `YYYY-MM`, unique, with no gaps | 34 contiguous months | reject dup / flag gap | no |
| SQ-10 | sm_spend | Spend cells match `$d.ddd` or `-$d.ddd`; strip `$`, keep the sign, store as DECIMAL(9,3) | 238/238 conform | quarantine row | no |
| SQ-11 | sm_spend | Spend ≥ 0 in every category except PayrollExpenses | Negatives only in PayrollExpenses | flag | inferred |
| SQ-12 | cross | Every Transactions customer exists in Industry, and the reverse | 100% match both ways | quarantine orphans | no |
| SQ-13 | cross | Transactions and S&M cover the same months | Both Jan-2022 → Oct-2024 | flag | no |

### Silver: business rules

| ID | Dataset | Rule | Evidence | On failure | Inferred |
|---|---|---|---|---|---|
| SB-01 | transactions | `amount_value = amount × 10,000` | Owner definition | reject | no |
| SB-02 | sm_spend | `spend_value = value × 100,000,000` | Owner definition | reject | no |
| SB-03 | transactions | A customer is paying in a month when `amount > 0` | 50.6% of rows are zero | flag | yes |
| SB-04 | transactions | Cohort = first paid month; the Jan-2022 cohort is marked pre-existing (never counted as new) | IDs 1–377 paid in Jan-2022; IDs follow acquisition order | flag | yes |
| SB-05 | transactions | Churned = 3+ consecutive zero months after the last payment; customers paying in Oct-2024 are ongoing | 83.8% of gaps last ≤ 2 months | flag | yes |
| SB-06 | transactions | Catch-up payment: after k zero months, a payment ≈ (k+1) × the usual amount (±5%) | 155 of 468 gaps (33.1%) | flag | yes |
| SB-07 | transactions | Reactivation: a payment after a gap that is not a catch-up | 340 customers have gaps | flag | yes |
| SB-08 | transactions | Flag outliers (e.g. customer 94) instead of removing them; report with and without them | Customer 94 = 4.77% of revenue | flag | yes |
| SB-09 | industry | Industry is fixed per customer (SCD type 1) and applies to the whole history | No effective dates | flag | yes |
| SB-10 | sm_spend | Negative PayrollExpenses is valid (an adjustment) but flagged | 5 negative months | flag | yes |

### Gold: dimensional model

| ID | Object | Grain | Contents |
|---|---|---|---|
| GLD-01 | `dim_month` | month | month → quarter → year |
| GLD-02 | `dim_industry` | industry | code, Spanish label, English label |
| GLD-03 | `dim_customer` | customer | `customer_id`, label, industry key, cohort month, pre-existing flag |
| GLD-04 | `dim_spend_category` | category | 7 categories grouped into media / people / other |
| GLD-05 | `fct_customer_month_revenue` | customer × month | native and full amounts; flags for paying, new, churn month, reactivation, catch-up, outlier |
| GLD-06 | `fct_sm_spend_month` | month × category | S&M reshaped to one row per month and category; native and full spend |
| GLD-07 | `agg_month_kpis` (optional) | month | revenue, paying, new and churned customers, ARPPU, S&M, CAC; built only from the facts |

### Infrastructure notes

- Rejected and quarantined rows go to a quarantine prefix in each layer, with the reason recorded.
- At 1.3 MB, Python jobs (Lambda or Glue Python shell) with Athena on top are enough.
- Enable versioning on silver and gold before loading data.
- Open decision: does renaming `S&M_spend.csv` to `sm_spend.csv` in bronze break the "no other changes" contract?

### Open questions for the data owners

1. Which currency are the amounts in?
2. Is revenue invoiced, collected or recognized? The catch-up payments suggest collected.
3. Is S&M actual spend or budget? What do the negative PayrollExpenses months mean?
4. Does `Transactions.csv` cover the whole customer base? This blocks any CAC or efficiency analysis.
5. Can a zero month mean a trial, a pause or an annual plan billed in another month?
6. Who assigns industries, and can a customer's industry change?
