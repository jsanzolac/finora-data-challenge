# Gold model: acquisition funnel and new-customer signals

> **Status.** The CDO approved this spec on 2026-11-17 for the CTO to build on Glue Spark, Iceberg and Athena (`docs/aws_architecture/`). It is self-contained. Every open question in §15 has a default, so the build does not wait for answers. When the user approves this spec, record it in the changelog of `docs/approved_data_rules.md`. That entry moves GLD-01–GLD-06, CDO-10, CMO-07, CMO-08 and the gold parts of CDO-04, CDO-11, CTO-06, CTO-07, CTO-08 and CTO-10 out of "Deferred", as amended here. GLD-07, CMO-05, CRO-06 and CTO-09 stay deferred.
>
> **Sources.** Silver tables `finora_silver.*` (schemas: `etl/common/schemas.py`); owner definitions `docs/data_semantics/owner_definitions.md`; approved silver rules `docs/approved_data_rules.md`; the main-session analysis `analysis/acquisition/funnel_and_drivers.py` and `analysis/acquisition/output/`. The CDO re-verified every figure in §12 on 2026-11-17, using the silver engine (`etl/tests/golden_helpers.py` `run()`) on `data/*.csv` and an independent recomputation.

## 1. Verdict on the business question

The CRO asked where we are losing growth, and why: is it demand, lead quality, response speed, the stages after SQL, or the different paths (product-led, near-direct-to-SQL, slow)?

**What the data can answer (facts, today's files):**
- **Won is real.** 1,584 customers made their first payment between 2022-02 and 2024-10. Won per month was 34.5 in 2022 (Feb–Dec), 54.2 in 2023 and 55.4 in 2024 (Jan–Oct). New customers have been flat at about 55 a month since 2023.
- **S&M spend per Won:** 8,146,316 (2022), 3,862,615 (2023), 3,565,884 (2024). Spend is in full units; the currency is unconfirmed.
- **Won splits by industry, and each customer's first payment** are known, along with how long industries keep paying.

**What the data cannot answer:**
- **Where growth is lost.** None of the three files holds a lead, a stage, a source or a timestamp before the first payment. Every count above Won is Won ÷ an assumed rate, so every month has the same funnel shape by construction. The estimated stages restate Won and the rates; they add no information. None of the four hypotheses raised in the meeting can be tested with these files. §13 lists the data that would be needed.
- **A spend → Won response.** The month-level correlations between spend and Won are negative for almost every category (total spend −0.48 / −0.50 / −0.42 / −0.26 at 0–3 months). They come from the June-2023 break: spend per month fell from 287.6M to 175.3M while Won rose from 37.9 to 57.5. Once the trend or the regime is removed, "signals" appear at the rate chance alone produces: 3 of 44 tests, against 2.2 expected. No statement of the form "spend X more, get Y more Won" is supported (§7.5).

## 2. Scope, conventions and where things live

| Item | Value |
|---|---|
| Glue database | `finora_gold` (new) |
| Warehouse | `s3://al-test-dl-gold/iceberg/finora_gold/<table>/` (the bucket is empty today; verified 2026-11-17) |
| Run reports | `s3://al-test-dl-gold/_runs/run_id=<id>/gold_report.json` |
| Format | Iceberg v2, Parquet, zstd, exact DECIMAL for money; one snapshot per table per run, tagged `<run_id>` (as in silver) |
| Input | Every silver table read at `VERSION AS OF '<silver_run_id>'`, the latest silver run marked `succeeded` in `s3://al-test-dl-serving/dq/runs.json` (today `r20261117T150932Z`). Never the untagged current state: tag `r20261117T040928Z` is a failed partial write |
| Query engine | Athena engine v3, workgroup `finora-dl` (1 GB scan cap); Finance's HR queries run in a separate workgroup (§9) |
| Window W | The months of silver `month_control`: 2022-01 → 2024-10 today. Window start = first month of W |
| Watermarks (CTO-07) | `revenue_complete_through` = silver `as_of_month`; `spend_complete_through` = last month with an included S&M line; `data_complete_through` = the earlier of the two. All are 2024-10 today |

**Units.** Owner definitions: revenue `amount` × 10,000 and S&M spend × 100,000,000. The currency is not stated. Column-name convention:
- A column ending in `_value` is a full amount.
- A column without the suffix is native, as in the file.
- Money is never FLOAT.
- Native revenue is DECIMAL(12,6); full revenue is DECIMAL(18,2). Native spend is DECIMAL(12,3); full spend is DECIMAL(18,0).
- Averages and costs are stored as DECIMAL(18,2), rounded HALF_UP from unrounded operands.
- Estimated stage counts are DECIMAL(38,6), rounded HALF_UP.
- Correlation coefficients are dimensionless. They are computed in double precision and stored as DECIMAL(5,4), HALF_UP.

**Statuses carried on every row that shows money** (CFO-03, CFO-05): `currency_status` = `unconfirmed`, `revenue_basis_status` = `unconfirmed` (hint cash-like), `spend_basis_status` = `unconfirmed` (hint budget-like), `scope_status` = `unconfirmed`. No column or label calls a cost per Won "CAC".

**Gold lineage (CTO-06, gold part).** Every row of every materialized gold table carries:

| Column | Type | Meaning |
|---|---|---|
| `_run_id` | STRING | Gold build run id (`rYYYYMMDDTHHMMSSZ`) |
| `_silver_run_id` | STRING | Silver run tag that was read |
| `_rules_version` | STRING | Silver `_rules_version` of the rows read |
| `_gold_model_version` | STRING | SHA-256 of the gold config (§14.2) |
| `_transactions_sha256`, `_industry_sha256`, `_sm_spend_sha256` | STRING | Silver `_source_sha256` of each input dataset; NULL when the table does not use that dataset |
| `as_of_month` | STRING | `revenue_complete_through` |
| `_built_at` | TIMESTAMP | UTC |

Row-grain facts also carry silver's `_source_key`, `_ingested_at` and `_source_line`, which trace each row to the delivered file and line.

## 3. Canonical definitions used by this model

| Term | Definition | Backed by |
|---|---|---|
| **Won** (default, `won_definition` = `first_payment`) | A customer whose first known-paid month (`amount` > 0) is month *m*, excluding customers whose first payment is in the window start month (`cohort_censoring` = `left`). In silver terms: `cohort_month IS NOT NULL AND cohort_censoring <> 'left'`, counted in `cohort_month` | User definition 2026-11-17; silver SB-03, SB-04. Excluding the window start is the user's rule, and matches the left-censoring in the dictionary |
| **Won, canonical new logo** (`won_definition` = `new_logo`) | Won with `cohort_censoring` = `none` (silver `is_new_logo`). It drops the 43 `probable_left` customers, whose first payment is a 2× or 3× multiple implying a start on or before the window start | Silver SB-04 (inferred) |
| **New revenue** | Σ of the Won customers' first payments at full value (`first_paid_amount` × 10,000), as paid, catch-ups and multiples included | User definition; owner unit |
| **New revenue, run-rate variant** | The same sum, except that a first payment flagged as a 2× or 3× multiple is replaced by that customer's next paid amount | Inferred (SB-04 / CRO-07) |
| **Spend** | Signed S&M spend per month and category at full value, kept as received (negatives included, SB-10). **Total spend** = the exact sum of the 7 categories | Owner unit; SB-02, SB-10 |
| **Spend groups** | media = PaidMedia + PublicidadNoWeb; people = Team + PayrollExpenses + Freelance; other = Travel + SoftwareTools | GLD-04 (inferred) |
| **Estimated stage count** | count(stage) = Won ÷ Π(rates from that stage down to Won). Only Won is observed | User definition (backwards funnel) |
| **Cost per unit at a stage** | total spend of the period ÷ count(stage), computed as total spend × Π(rates from that stage to Won) ÷ Won. Cost per Won = total spend ÷ Won. "Real" only at Won | User definition |
| **Period spend** | The spend of the same months as the Won counted. The window start month's spend (200,000,000 today) is not in any funnel period, because its Won is excluded | CDO decision (§8.3) |
| **Low n** (CMO-07) | A rate or average whose denominator has fewer than 10 customers or Won | CMO-07 |
| **Small cell** (CDO-11(3)) | A money cell built from 1–4 customers. It is suppressed in any share outside the named roles | CDO-11 |
| **Signal** | \|r\| at or above the two-sided 5% critical value for its number of pairs (§7.4). A signal is evidence to look at, not proof | CDO decision |

## 4. The model at a glance

```
                      dim_month ─────────────┬──────────────┬───────────────┐
                         │                   │              │               │
 dim_industry ── fact_acquisition      fact_customer_     fact_sm_spend ── dim_spend_category
      │          (1 row per Won)       month_revenue      (month × category,
      └──────── dim_customer ───────── (customer × month)  hr_sensitive partition)
                                                              │
 dim_funnel_stage    funnel_conversion_rate (user-owned)      │   spend meets customers ONLY through dim_month
        │                    │                                │
        └── v_funnel_* views ┴── agg_acquisition_month ◄──────┘
                                agg_won_month_industry, agg_industry_profile, agg_won_spend_lag_corr
```

| Object | Kind | Grain | Rows today | Built by | Access (§9) |
|---|---|---|---|---|---|
| `dim_month` | dimension | month | 34 | gold job | F, R, D |
| `dim_industry` | dimension | industry | 8 | gold job (seed) | F, R, D |
| `dim_customer` | dimension | customer | 1,961 | gold job | F, R, D (customer-level) |
| `dim_spend_category` | dimension | S&M category | 8 | gold job (seed) | F, R, D |
| `dim_funnel_stage` | dimension | funnel stage | 7 | gold job (seed) | F, R, D |
| `fact_acquisition` | fact | Won customer | 1,584 | gold job | F, R, D (customer-level) |
| `fact_customer_month_revenue` | fact | customer × month | 66,674 | gold job | F, R, D (customer-level) |
| `fact_sm_spend` | fact | month × category | 238 | gold job | shared partition F, R, D; HR partition F only |
| `funnel_conversion_rate` | config | scenario × transition × version | 6 (seed) | **users** (never the job) | read F, R, D; insert F, R |
| `agg_acquisition_month` | aggregate table | month | 34 | gold job | F, R, D |
| `agg_won_month_industry` | aggregate table | month × industry | 198 | gold job | F, R, D |
| `agg_industry_profile` | aggregate table | industry × customer scope | 18 | gold job | F, R, D |
| `agg_won_spend_lag_corr` | aggregate table | definition × scope × series × lag × method | 1,848 | gold job | F, R, D |
| `gold_build_status` | control | gold run | 1 | gold job | F, R, D |
| `v_funnel_rate_current`, `v_funnel_scenario_status` | views | scenario × transition / scenario | live | DDL | F, R, D |
| `v_funnel_month`, `v_funnel_period` | views | scenario × definition × month (or period) × stage | live | DDL | F, R, D |
| `v_funnel_scenario_compare`, `v_funnel_rate_sensitivity` | views | scenario × definition × period / scenario × transition | live | DDL | F, R, D |
| `v_acquisition_month` | view | month | 33 | DDL | F, R, D |
| `v_acquisition_month_finance` | view | month | 33 | DDL | **F only** |
| `v_corr_signal_summary` | view | method × definition × scope type | 12 | DDL | F, R, D |
| `v_sm_spend_shared` | view | month × non-HR category | 136 | DDL | F, R, D |

F = `finance`, R = `revops`, D = `data`: the named roles of CDO-11(1).

**Changes from the suggested starting point, and why:**
1. **The funnel outputs are views, not tables.** A rate edit then takes effect at the next query, with no rebuild or redeploy. Everything that does not depend on rates is materialized and tested on every run.
2. **`agg_acquisition_month` is materialized.** Total spend includes the HR-sensitive categories, which roles other than Finance cannot read at query time. The pipeline role computes the total once.
3. **Correlations are materialized.** They do not depend on rates, and a fixed table can be tested against expected values.
4. **`won_definition` is a column of every funnel and correlation output.** The user's Won is the default, and the canonical new-logo count is one filter away.
5. **`dim_customer` has no `customer_label` (`Cliente N`).** It is derivable from `customer_id`, and minimization says not to copy it.
6. **New: `gold_build_status`.** It holds the watermarks and statuses that every consumer needs.

## 5. Tables

Types are Spark/Glue types. "Source" names the silver table and column. Every table also has the gold lineage block (§2).

### 5.1 `dim_month` (GLD-01)

Grain: one row per month of W. PK `month_key`. Source: silver `month_control`, plus config.

| Column | Type | Definition |
|---|---|---|
| `month_key` | INT | YYYYMM |
| `month` | STRING | `YYYY-MM` |
| `month_start_date`, `month_end_date` | DATE | First and last calendar day |
| `year`, `quarter` | INT | Calendar year; quarter 1–4 |
| `year_quarter` | STRING | `YYYY-Qn` |
| `month_index` | INT | 0 at the window start |
| `is_window_start` | BOOLEAN | Month = first month of W |
| `is_won_reportable` | BOOLEAN | NOT `is_window_start` AND month ≤ `revenue_complete_through` |
| `sm_regime` | STRING | `pre_2023_06` / `from_2023_06`. Boundary from config. **Inferred** (CMO-08); the cause of the break is unknown |
| `in_transactions`, `in_sm_spend` | BOOLEAN | From `month_control` |
| `revenue_is_complete` | BOOLEAN | From `month_control` (no hole in the month) |
| `is_unit_tripwire` | BOOLEAN | From `month_control` (CDO-08) |

`implied_start_month` can fall before W (18 customers have 2021-12). It stays a plain string in `fact_acquisition` and is not a key (A5), so `dim_month` needs no months outside W. A fact month that cannot be resolved fails the run (CTO-08).

### 5.2 `dim_industry` (GLD-02)

Grain: one row per industry, plus two unknown members. PK `industry_key`. Source: config seed, checked against silver `industry.industry_code`. Keys are fixed and never renumbered.

| `industry_key` | `industry_code` | `industry_label_es` (as stored) | `industry_label_en` | `chart_label` | `is_unknown_member` |
|---|---|---|---|---|---|
| 1 | RESTAURANTS | Restaurantes | Restaurants | Restaurants | false |
| 2 | MANUFACTURING | Producción | Manufacturing | Manufacturing | false |
| 3 | RETAIL | Retail | Retail | Retail | false |
| 4 | TECHNOLOGY | Tecnología | Technology | Technology | false |
| 5 | PROFESSIONAL_SERVICES | Servicios profesionales | Professional services | Professional services | false |
| 6 | HEALTHCARE | Salud | Healthcare | Healthcare | false |
| −1 | UNKNOWN | NULL | Unknown | Unknown | true |
| −2 | UNMAPPED | NULL | Unmapped | Unknown | true |

`sort_order` = the key order (1–6, then −1, −2). The codes and English labels are inferred conventions (SQ-04). Revenue or Won on −1 or −2 alerts Data (CTO-08).

### 5.3 `dim_customer` (GLD-03, slimmed)

Grain: one row per customer in silver `customer`. PK `customer_id`. SCD type 1, recomputed every run. **Customer-level, Confidential-Financial (CDO-11(1)).**

| Column | Type | Source / definition |
|---|---|---|
| `customer_id` | INT | `customer.customer_id` (a reversible pseudonym) |
| `industry_key` | SMALLINT | `customer.industry_code` → `dim_industry` |
| `cohort_month_key` | INT | `customer.cohort_month`; NULL if the customer never paid |
| `cohort_censoring` | STRING | `left`, `probable_left`, `none`, `unknown` or NULL |
| `is_won` | BOOLEAN | `cohort_month IS NOT NULL AND cohort_censoring <> 'left'` |
| `is_new_logo` | BOOLEAN | `customer.is_new_logo` |
| `paid_months` | INT | `customer.paid_months` |
| `last_paid_month_key` | INT | `customer.last_paid_month` |
| `is_outlier_customer`, `outlier_source` | BOOLEAN, STRING | SB-08 |
| `has_excluded_months` | BOOLEAN | H8 |
| `in_transactions` | BOOLEAN | `customer.in_transactions` |

### 5.4 `dim_spend_category` (GLD-04)

Grain: one row per S&M source column, plus −2 UNMAPPED. PK `category_key`. Source: config seed. The hierarchies are **inferred** from the column names.

| `category_key` | `category_code` | `category_label_en` | `spend_group` | `channel_class` | `is_hr_sensitive` |
|---|---|---|---|---|---|
| 1 | PaidMedia | Paid digital media | media | digital_paid | false |
| 2 | Travel | Travel | other | non_media | false |
| 3 | PublicidadNoWeb | Offline advertising | media | offline | false |
| 4 | Freelance | Freelance and contractors | people | non_media | **true** |
| 5 | SoftwareTools | S&M software and tools | other | non_media | false |
| 6 | Team | S&M team | people | non_media | **true** |
| 7 | PayrollExpenses | Payroll-related expenses | people | non_media | **true** |
| −2 | UNMAPPED | Unmapped | NULL | NULL | true (fail closed) |

### 5.5 `dim_funnel_stage` (new)

Grain: one row per stage. PK `stage_key`. Source: config seed.

| `stage_key` | `stage_code` | `stage_label` | `next_stage_code` | `is_observed` | `basis` |
|---|---|---|---|---|---|
| 1 | NEW | New | WORKING | false | estimated: Won ÷ assumed rates |
| 2 | WORKING | Working | ENGAGED | false | same |
| 3 | ENGAGED | Engaged | SQL | false | same |
| 4 | SQL | SQL | DEMO | false | same |
| 5 | DEMO | Demo | PROPOSAL | false | same |
| 6 | PROPOSAL | Proposal | WON | false | same |
| 7 | WON | Won | NULL | true | observed: silver `customer` first payment |

### 5.6 `fact_acquisition` (new)

Grain: **one row per Won customer** (user definition). PK `customer_id`. Source: silver `customer`, joined to silver `transactions` at (`customer_id`, `cohort_month`) for the line lineage. **Customer-level.** Rows: 1,584 today.

| Column | Type | Source / definition |
|---|---|---|
| `customer_id` | INT | FK `dim_customer` |
| `won_month_key` | INT | `cohort_month` → `dim_month` |
| `industry_key` | SMALLINT | FK `dim_industry` (conformed, the same as in `dim_customer`) |
| `won_count` | INT | Always 1 (additive measure) |
| `first_paid_amount` | DECIMAL(12,6) | `customer.first_paid_amount` (native) |
| `first_paid_amount_value` | DECIMAL(18,2) | × 10,000 |
| `run_rate_amount_value` | DECIMAL(18,2) | `next_paid_amount` × 10,000 when `first_payment_multiple` is not NULL, else `first_paid_amount_value`. **Inferred** |
| `first_payment_multiple` | INT | 2, 3 or NULL (SB-04) |
| `is_first_payment_multiple` | BOOLEAN | `first_payment_multiple` IS NOT NULL |
| `first_payment_ratio` | DECIMAL(38,12) | SB-04 |
| `first_payment_band`, `is_first_month_spike` | STRING, BOOLEAN | CRO-07 |
| `implied_start_month` | STRING | `YYYY-MM`; may precede W; not a key |
| `cohort_censoring` | STRING | `none`, `probable_left` or `unknown` (`left` never appears here) |
| `is_new_logo` | BOOLEAN | `cohort_censoring` = `none` |
| `is_probable_left` | BOOLEAN | `cohort_censoring` = `probable_left` |
| `is_cohort_unknown` | BOOLEAN | `cohort_censoring` = `unknown` (H5: a hole hides the start) |
| `first_payment_hole_affected` | BOOLEAN | H5 |
| `is_outlier_customer` | BOOLEAN | SB-08 |
| `_source_key`, `_ingested_at`, `_source_line` | | Silver `transactions` row of the first payment |

### 5.7 `fact_customer_month_revenue` (GLD-05)

Grain: customer × month over the dense panel, with zero months and holes (H1). PK (`customer_id`, `month_key`). Source: silver `customer_month`, with `is_negative_amount` and `_source_line` from silver `transactions` (NULL for a hole). **Customer-level.** Rows: 66,674 today. No partition: the table is about 2 MB, and 34 month partitions would only make small files. Partition by `month_key` once it passes 1 GB.

| Column | Type | Definition |
|---|---|---|
| `customer_id`, `month_key`, `industry_key`, `cohort_month_key` | INT, INT, SMALLINT, INT | Keys |
| `months_since_cohort` | INT | Month − cohort month; NULL before the cohort or with no cohort |
| `amount`, `amount_value` | DECIMAL(12,6), DECIMAL(18,2) | NULL for a hole |
| `amount_normalized`, `amount_normalized_value` | DECIMAL(18,6), DECIMAL(18,2) | CRO-03; analytical only |
| `is_paying`, `is_negative_amount`, `is_first_paid_month` | BOOLEAN | `is_first_paid_month` = month is the cohort month |
| `is_hole`, `hole_reason` | BOOLEAN, STRING | H1 |
| `lifecycle_state`, `is_provisional` | STRING, BOOLEAN | CDO-07 |
| `settlement_type`, `settlement_confidence`, `uneven_split_start_month`, `is_catch_up`, `is_prepaid` | | SB-06, SB-11 |
| `expansion_amount`, `contraction_amount`, `amount_lag12` | DECIMAL(18,6) | CRO-05 (native) |

### 5.8 `fact_sm_spend` (GLD-06)

Grain: month × category. PK (`month_key`, `category_key`). Source: silver `sm_spend`. Rows: 238 today (34 × 7). **Partitioned by `hr_sensitive`**: the 102 rows of Team, PayrollExpenses and Freelance sit in `hr_sensitive=true` and the other 136 in `false`. Only `dim_month` and `dim_spend_category` join to it (CDO-10).

| Column | Type | Definition |
|---|---|---|
| `month_key`, `category_key` | INT, SMALLINT | Keys |
| `spend` | DECIMAL(12,3) | Native, signed |
| `spend_value` | DECIMAL(18,0) | × 100,000,000, signed |
| `is_negative_spend`, `is_restated`, `is_unit_tripwire` | BOOLEAN | SB-10, CDO-06b, CDO-08 |
| `hr_sensitive` | BOOLEAN | Partition: `dim_spend_category.is_hr_sensitive` |
| `_source_key`, `_ingested_at`, `_source_line` | | Silver lineage |

Table property: `write.metadata.metrics.column.spend` = `none` and `write.metadata.metrics.column.spend_value` = `none`. Iceberg manifests are readable by every role that can query the table. With default metrics they would hold the min and max of the HR values (§9.4).

### 5.9 `agg_acquisition_month` (new; materialized)

Grain: one row per month of W. PK `month_key`. Built only from `fact_acquisition`, `fact_sm_spend`, `dim_month` and `gold_build_status`. Rows: 34. The window-start row exists because its spend feeds the lagged correlations; its Won columns are NULL.

| Column | Type | Definition |
|---|---|---|
| `month_key`, `is_won_reportable` | INT, BOOLEAN | |
| `won_count` | INT | Σ `fact_acquisition.won_count` in the month; NULL when not `is_won_reportable` |
| `won_new_logo_count`, `won_probable_left_count`, `won_cohort_unknown_count`, `won_first_payment_multiple_count` | INT | The same, filtered |
| `won_is_complete` | BOOLEAN | `revenue_is_complete` AND no Won customer of the month has `cohort_censoring` = `unknown` |
| `new_revenue_value` | DECIMAL(18,2) | Σ `first_paid_amount_value` |
| `new_revenue_new_logo_value` | DECIMAL(18,2) | The same, for `is_new_logo` |
| `new_revenue_multiple_value` | DECIMAL(18,2) | The part of `new_revenue_value` from first payments that are multiples |
| `new_revenue_run_rate_value` | DECIMAL(18,2) | Σ `run_rate_amount_value` (**inferred**) |
| `spend_paid_media_value`, `spend_travel_value`, `spend_publicidad_no_web_value`, `spend_software_tools_value` | DECIMAL(18,0) | The non-HR categories |
| `spend_media_value`, `spend_other_value`, `spend_people_value` | DECIMAL(18,0) | Group totals (`spend_people_value` is a sum of the HR categories; see §9 decision A1) |
| `spend_total_value` | DECIMAL(18,0) | Σ of the 7 categories, negatives included. NULL when `in_sm_spend` is false or the month is after `spend_complete_through` |
| `has_negative_spend_cell` | BOOLEAN | SB-10 (already visible to all three roles on the DQ dashboard) |
| `in_sm_spend`, `is_unit_tripwire` | BOOLEAN | |
| `currency_status`, `revenue_basis_status`, `spend_basis_status`, `scope_status` | STRING | §2 |

### 5.10 `agg_won_month_industry` (new; materialized)

Grain: Won-reportable month × industry. Dense: zero rows exist for the 6 registered industries, and an unknown member appears only when it has at least one Won. PK (`month_key`, `industry_key`). Rows: 198. It holds **no spend measure** (CDO-10).

| Column | Type | Definition |
|---|---|---|
| `month_key`, `industry_key` | INT, SMALLINT | |
| `won_count`, `won_new_logo_count` | INT | 0 is a real zero: no customer of that industry first paid that month |
| `new_revenue_value`, `new_revenue_new_logo_value` | DECIMAL(18,2) | |
| `is_low_n` | BOOLEAN | `won_count` < 10 (CMO-07) |
| `is_small_cell` | BOOLEAN | 0 < `won_count` < 5. The money in this cell must be suppressed, with complementary suppression, in any share outside F, R and D (CDO-11(3)) |

### 5.11 `agg_industry_profile` (new; materialized)

Grain: industry × `customer_scope`, where the scope is `all`, `won` (acquired in 2022-02 → 2024-10) or `left_censored` (already paying at the window start). PK (`industry_key`, `customer_scope`). Rows: 18. Built from `fact_customer_month_revenue` and `dim_customer`.

| Column | Type | Definition |
|---|---|---|
| `customers` | INT | Customers in scope with at least one known-paid month |
| `paid_customer_months` | INT | Known-paid customer-months (`amount` > 0) up to `as_of_month` |
| `avg_monthly_payment_value` | DECIMAL(18,2) | Σ `amount_value` over the paid customer-months ÷ `paid_customer_months`. Catch-ups are included as paid (user definition) |
| `avg_monthly_payment_ex_outlier_value` | DECIMAL(18,2) | The same, without `is_outlier_customer` customers |
| `median_monthly_payment_value` | DECIMAL(18,2) | Median of the same months. An even count takes the mean of the two middle values (the silver convention) |
| `outlier_customers` | INT | Count of outliers in the cell |
| `avg_months_paying` | DECIMAL(9,4) | Mean `paid_months`. **Right-censored: a lower bound on lifetime**, and a left-censored customer's months start at the window start |
| `avg_months_observable` | DECIMAL(9,4) | Mean of the months from the cohort month (or the window start) to `as_of_month`, inclusive |
| `share_of_observable_months_paid` | DECIMAL(9,4) | Σ `paid_months` ÷ Σ observable months. This one is comparable across cohorts of different ages |
| `is_low_n` | BOOLEAN | `customers` < 10 |

### 5.12 `agg_won_spend_lag_corr` (new; materialized)

Grain: `won_definition` × `scope_code` × `spend_series` × `lag_months` × `method`. PK is all five. Rows: 2 × 7 × 11 × 4 × 3 = 1,848. §7 has the full method.

| Column | Type | Definition |
|---|---|---|
| `won_definition` | STRING | `first_payment` (default), `new_logo` |
| `scope_code`, `industry_key` | STRING, SMALLINT | `ALL` with `industry_key` NULL, or an industry code with its key: that industry's Won against **company-level** spend |
| `spend_series` | STRING | One of the 7 category codes, `GROUP_MEDIA`, `GROUP_PEOPLE`, `GROUP_OTHER` or `TOTAL` |
| `category_key` | SMALLINT | For a category series; NULL otherwise |
| `lag_months` | INT | 0, 1, 2 or 3: spend this many months **before** the Won month |
| `method` | STRING | `level`, `diff` (month-over-month changes) or `within_regime` (deviations from each `sm_regime` mean; **inferred** regime) |
| `r` | DECIMAL(5,4) | Pearson r; NULL with `null_reason` |
| `n_pairs` | INT | Month pairs used |
| `r_critical_5pct` | DECIMAL(5,4) | Two-sided 5% critical \|r\| for `n_pairs` |
| `is_signal_5pct` | BOOLEAN | \|r\| ≥ `r_critical_5pct`, compared unrounded |
| `won_mean_per_month` | DECIMAL(9,4) | Mean Won of the scope over the paired months |
| `is_low_volume` | BOOLEAN | `won_mean_per_month` < 10 (Technology, Professional services and Healthcare today) |
| `first_won_month_key`, `last_won_month_key` | INT | Range of the paired Won months |
| `null_reason` | STRING | `too_few_pairs` (n < 3) or `constant_series` |

### 5.13 `gold_build_status` (new; control)

One row per gold build (full rebuild): `_run_id`, `_silver_run_id`, `window_start_month`, `revenue_complete_through`, `spend_complete_through`, `data_complete_through`, `currency_code` (NULL), `currency_status`, `revenue_basis_status`, `spend_basis_status`, `scope_status`, `base_rates_match_seed` (BOOLEAN), `rate_table_snapshot_id` (BIGINT, the snapshot of `funnel_conversion_rate` read for the history check), `rate_table_rows_sha256`, `controls_passed` (always true in a published row), and `_built_at`.

## 6. Editable conversion rates

### 6.1 The table: `funnel_conversion_rate` (user-owned, append-only)

| Column | Type | Rule |
|---|---|---|
| `scenario_id` | STRING | `^[a-z][a-z0-9_]{0,39}$`. `base` is the seeded scenario |
| `scenario_label` | STRING | Free text, at most 200 characters, no customer or personal data |
| `from_stage_code`, `to_stage_code` | STRING | A consecutive pair of `dim_funnel_stage` (NEW→WORKING … PROPOSAL→WON) |
| `rate` | DECIMAL(5,4) | 0 < rate ≤ 1. The share of `from_stage` that reaches `to_stage` |
| `changed_at` | TIMESTAMP | UTC, set to `current_timestamp` by the INSERT |
| `changed_by` | STRING | The editor's SSO user name (an employee work identity: personal data, readable only by the named roles). Never an email or customer data |
| `change_reason` | STRING | Required, at most 500 characters |

**One table holds every rate.** A change is a new row and never an UPDATE or DELETE. The **current** rate of a transition is its row with the latest `changed_at`, so the table is its own audit log.

**Seed (the `base` scenario = the user's rates, 2026-11-17).** The deploy inserts it **once**, and only if no row with `scenario_id = 'base'` exists. `changed_by` = `seed`, and `change_reason` = `User definition 2026-11-17, docs/gold_acquisition_model.md`.

| from → to | NEW→WORKING | WORKING→ENGAGED | ENGAGED→SQL | SQL→DEMO | DEMO→PROPOSAL | PROPOSAL→WON | Overall New→Won |
|---|---|---|---|---|---|---|---|
| `base` | 0.8000 | 0.4000 | 0.5000 | 0.7000 | 0.6000 | 0.4000 | 0.026880 (2.688%) |

The base scenario can be edited like any other, through new rows with a reason, because it is an assumption and not data. The gold job compares it with the seed and reports `base_rates_match_seed`, so a reader always knows whether "base" still means the user's 2026-11-17 rates.

### 6.2 How a user changes rates (Athena, workgroup `finora-dl`, roles `finance` or `revops`)

Illustrative SQL. The CTO confirms the exact Athena v3 syntax when building.

```sql
-- New scenario: copy base and change SQL→Demo to 0.80
INSERT INTO finora_gold.funnel_conversion_rate
SELECT 'sql_demo_080', 'SQL to Demo at 80%', from_stage_code, to_stage_code,
       CASE WHEN from_stage_code = 'SQL' THEN DECIMAL '0.8000' ELSE rate END,
       CAST(current_timestamp AS timestamp(6)), '<your-sso-user>', 'What if demos are booked faster'
FROM finora_gold.v_funnel_rate_current WHERE scenario_id = 'base';

-- Change one rate of an existing scenario: insert one row with a later changed_at
INSERT INTO finora_gold.funnel_conversion_rate VALUES
('sql_demo_080', 'SQL to Demo at 80%', 'DEMO', 'PROPOSAL', DECIMAL '0.6500',
 CAST(current_timestamp AS timestamp(6)), '<your-sso-user>', 'Q4 pipeline review assumption');
```

### 6.3 Validation (live, in `v_funnel_scenario_status`)

`v_funnel_rate_current` keeps the latest row per (`scenario_id`, `from_stage_code`). `v_funnel_scenario_status` returns one row per scenario with `status` (`valid` / `invalid`) and the IDs of the failing checks:

| Check | Rule |
|---|---|
| GR-01 | `scenario_id` matches the pattern |
| GR-02 | Every current row is a consecutive stage pair |
| GR-03 | 0 < `rate` ≤ 1 |
| GR-04 | Exactly 6 current transitions, one per `from_stage_code` |
| GR-05 | No two rows share (`scenario_id`, `from_stage_code`, `changed_at`), so "latest" is never ambiguous |
| GR-06 | `changed_by` and `change_reason` are non-empty; `changed_at` is not NULL and not more than 5 minutes in the future |

**An invalid scenario produces no funnel rows.** It appears only in the status view, with its reasons. A user fixes it by inserting corrected rows.

### 6.4 Audit

| Question | Answered by |
|---|---|
| What changed, when, and why | The table itself (append-only rows) |
| Was history rewritten? | Iceberg snapshots of the table are **never expired**. Each gold run stores the snapshot id and a row hash in `gold_build_status`. The next run time-travels to that snapshot and checks that every old row still exists. If any is missing, it raises finding `RATE_HISTORY_REWRITTEN` in the gold run report and an alert on SNS `finora-dl-alerts` |
| Who really ran the change | CloudTrail `StartQueryExecution` (the principal and the query). **Today the account has no CloudTrail trail** (verified 2026-11-17: `describe-trails` is empty), so only the 90-day Event history exists. A trail with at least one year of retention is an ask to the CTO, and it needs the user's approval because it is an AWS change |

### 6.5 The full rebuild never touches user rates

1. The gold job's output list does not include `funnel_conversion_rate`. The job only reads it, for the history check.
2. IAM enforces this, not just code. The gold job role has an **explicit Deny** on `s3:PutObject` and `s3:DeleteObject` under `iceberg/finora_gold/funnel_conversion_rate/`, and on `glue:UpdateTable` and `glue:DeleteTable` for that table.
3. The table is created and seeded by a one-time, idempotent deploy step: `CREATE ... IF NOT EXISTS`, plus the seed only when `base` is absent. Redeploying never re-seeds or truncates it.
4. The views are DDL, deployed with the code. Rebuilding the job-owned tables does not change them.

## 7. Views and methods

### 7.1 The funnel (`v_funnel_month`, `v_funnel_period`)

For each valid scenario × `won_definition` × month (or period) × stage:

| Column | Definition |
|---|---|
| `stage_count` | WON: the observed Won (an integer). Any other stage: Won ÷ Π(current rates from that stage to Won), DECIMAL(38,6) HALF_UP |
| `cost_per_unit_value` | `spend_total_value` × Π(rates from that stage to Won) ÷ Won, DECIMAL(38,2) HALF_UP. This form never divides by a rounded count. At WON it equals spend ÷ Won |
| `real_or_estimated` | `Real` for WON; `Estimated` for every other stage |
| `downstream_rate_product` | Π, DECIMAL(38,12) |
| `won_count`, `spend_total_value` | The two real inputs |
| `is_low_n` | Won < 10 |
| `cost_null_reason` | `cost_per_unit_value` is NULL with: `won_zero` (Won = 0, so no stage count can be estimated); `spend_missing` (no S&M line); `beyond_data_complete_through`; `unit_tripwire` (CDO-08); `won_incomplete` (`won_is_complete` = false). The stage counts are still shown |
| Statuses | `currency_status`, `spend_basis_status`, `scope_status` |

`v_funnel_period` aggregates the reportable months up to `data_complete_through` by `period_type`:
- `full`: every reportable month.
- `year` and `quarter`: these carry `is_partial_period`. 2022 has 11 months, 2024 has 10, and 2022-Q1 has 2.
- `sm_regime`: **inferred**. This is the trend check by regime.

The view adds `months_in_period`, `first_month`, `last_month`, `won_per_month` (DECIMAL(18,6)) and `spend_per_month_value` (DECIMAL(18,2)), both HALF_UP. Won and spend are summed over the same months. A period that contains a month with a `cost_null_reason` has a NULL period cost, with that reason.

**Read this before using it.** Because the rates are constant over time, `stage_count` for every stage is proportional to Won in every month and period. The funnel's shape never changes, and month-to-month differences at any stage are just Won's differences scaled.

### 7.2 "If we move this variable": `v_funnel_scenario_compare` and `v_funnel_rate_sensitivity`

What can be stated honestly is **arithmetic under the rate assumptions**. Every row of both views carries `basis` = `assumption: stage volumes and rates are not observed`.

`v_funnel_scenario_compare` (scenario vs `base`, per `won_definition` and period):

| Column | Definition | Reads as |
|---|---|---|
| `overall_rate`, `overall_rate_base` | Π of the scenario's and of base's six rates | |
| `new_estimated_base` | Won ÷ `overall_rate_base` | The New volume that base implies |
| `won_implied_same_new` | Won × `overall_rate` ÷ `overall_rate_base` | "With the same New, these rates imply this many Won" |
| `won_implied_delta`, `won_implied_delta_pct` | Against the actual Won | |
| `new_required_same_won` | Won ÷ `overall_rate` | "To get the same Won with these rates, we need this much New" |
| `new_required_delta`, `new_required_delta_pct` | Against `new_estimated_base` | |
| `cost_per_won_implied_value` | Period spend ÷ `won_implied_same_new` | Assumes the rate change costs nothing extra |

`v_funnel_rate_sensitivity` has one row per scenario × transition. One "rate point" is +0.01 on that transition's rate, with the other five unchanged:

| Column | Definition | Unit |
|---|---|---|
| `rate` | The current rate | |
| `won_pct_change_per_point` | 1 ÷ `rate`: the Won gained per rate point, New held fixed | percent |
| `won_change_per_point_full_period` | Won(full period) × 0.01 ÷ `rate` | Won |
| `new_required_pct_change_per_point` | −1 ÷ (`rate` + 0.01): the change in New needed for the same Won | percent |

All of them are NULL when `rate` + 0.01 > 1. The transition with the lowest rate gives the most Won per point, as a matter of algebra, not evidence.

**What these views do not mean.** They do not say a rate can be moved, what it would cost, or that rates are independent of volume (more New usually lowers early-stage rates). They do not say anything about spend. Today's data supports no spend → Won relationship (§7.5).

### 7.3 Monthly table (`v_acquisition_month`, `v_acquisition_month_finance`)

`v_acquisition_month` is the user's monthly table, one row per Won-reportable month. Its columns are:
- month and `won_count`;
- `won_new_logo_count`;
- `won_restaurants`, `won_manufacturing`, `won_retail`, `won_technology`, `won_professional_services`, `won_healthcare` and `won_unknown_industry`, pivoted from `agg_won_month_industry` and generated from the `dim_industry` seed at deploy;
- `new_revenue_value`;
- the four non-HR spend columns, `spend_people_value` and `spend_total_value`;
- the statuses.

`v_acquisition_month_finance` adds `spend_freelance_value`, `spend_team_value` and `spend_payroll_expenses_value` from the HR partition of `fact_sm_spend`. Any other role that queries it fails on S3 access, by design.

### 7.4 Correlations (`agg_won_spend_lag_corr`, `v_corr_signal_summary`)

- **Pairing.** For a Won month *m* and lag *L*, pair Won(*m*) with spend(*m* − *L*). *m* ranges over the Won-reportable months up to `data_complete_through`. The spend month may be the window start, so its spend is used at *L* ≥ 1. A pair is dropped when spend(*m* − *L*) is missing or before W, or when either month has `is_unit_tripwire` or `won_is_complete` = false. **n = the pairs kept.** Today: level and within_regime have 33, 33, 32, 31 for *L* = 0–3; diff has 32, 32, 31, 30.
- **Industry scope.** That industry's Won(*m*), including its zero months, against **company** spend. Spend is never split by industry (CDO-10).
- **Methods.**
  - `level`: Pearson r of the two series.
  - `diff` (the user's trend check): ΔWon(*m*) = Won(*m*) − Won(*m*−1) needs both months reportable, so it starts at the second reportable month; Δspend(*m*−*L*) needs both spend months. Then Pearson r.
  - `within_regime`: on the kept pairs, subtract from each side its mean within the `sm_regime` of the Won month *m*, then Pearson r.
- **Threshold.** `r_critical_5pct` = t ÷ √(t² + n − 2), where t is Student's t at 0.975 with n − 2 degrees of freedom: 0.3440 (n 33), 0.3494 (32), 0.3550 (31), 0.3610 (30), 0.3673 (29). Use `scipy.stats.t.ppf`, or a versioned lookup table that reproduces these values to 4 decimals.
- **Why a signal is not proof.**
  - Each method × definition family has 308 tests (44 company-level, 264 industry), so about 15 cross 5% by chance alone.
  - The monthly series share a trend and a structural break, and the industry series are small counts (Healthcare 3.3 Won a month).
  - Correlation is not causation, and spend is budget-like (round totals, CFO-03).
- **`v_corr_signal_summary`.** Per method × `won_definition` × scope type (company / industry): tests, tests with r, signals, and `expected_by_chance` = 0.05 × tests with r. This is the first thing to read.

### 7.5 What today's correlations say (CDO reading, recorded for the users)

| Family (user's Won) | Tests | Signals | Expected by chance |
|---|---|---|---|
| level, company | 44 | 30 | 2.2 |
| level, industries | 264 | 110 | 13.2 |
| diff, company | 44 | 3 | 2.2 |
| diff, industries | 264 | 11 | 13.2 |
| within_regime, company | 44 | 3 | 2.2 |
| within_regime, industries | 264 | 17 | 13.2 |

The level signals are almost all negative. They disappear once the trend (diff) or the regime (within_regime) is removed: what remains is about the number chance produces, with no consistent sign across adjacent lags (SoftwareTools diff −0.38 at lag 2, then +0.42 at lag 3).

Team's positive level r (+0.53 and +0.60 at lags 2–3) becomes −0.17 / −0.31 / +0.03 / +0.23 within regime. It reflects Team becoming a near-fixed, higher amount from June 2023, when Won was also higher.

**Reading for users:** these files show no usable spend → Won relationship, in either direction.

## 8. Edge cases and decisions

| # | Case | Decision | Why |
|---|---|---|---|
| 8.1 | 43 `probable_left` customers (40 in 2022-02, 3 in 2022-03) | Kept in Won (the user's definition), flagged `is_probable_left`. `won_definition = 'new_logo'` excludes them (1,541) | The user owns the business definition. The canonical new-logo count must stay one filter away, because 2022-02 Won is 108 against 68 new logos |
| 8.2 | First payments that are multiples or catch-ups | `new_revenue_value` stays as paid. The multiple part is published separately (`new_revenue_multiple_value`), along with a **run-rate** variant (**inferred**) | Cash-like basis (CFO-03): the payment happened. A 2× or 3× first payment overstates starting monthly revenue. 102 Won customers carry 10.1% of new revenue |
| 8.3 | Window-start spend | Used as a lagged predictor; never in a funnel period cost | Its Won is excluded, so including it would charge 200,000,000 to no customers |
| 8.4 | Negative PayrollExpenses (5 months, −13,500,000 in total) | Kept as received (SB-10), inside every total. `has_negative_spend_cell` is carried | Clipping would move two monthly totals off their 0.05 budget grid. The nature of the negatives is unconfirmed (Q3) |
| 8.5 | Industry months with Won = 0 (7 of 198 cells) | Real zeros: kept in the dense table and in the industry correlations | An industry with no first payment that month is an observation, not missing data |
| 8.6 | Low-volume industries | `is_low_n` on cells, `is_low_volume` on correlations. No funnel or cost by industry | 140 of 198 industry-months have fewer than 10 Won |
| 8.7 | Cost per Won by industry, channel or cohort | **Not built** | CDO-10: spend has no allocation key |
| 8.8 | Holes in future deliveries | Won stays at the first **known**-paid month and is flagged (`is_cohort_unknown`, `won_is_complete`). Costs and correlations exclude incomplete months | H5: a hole can hide an earlier first payment. Today there are 0 holes |
| 8.9 | History extended backwards in a future file | The excluded month is the **window start**, whatever it is, not a hard-coded 2022-01 | Left-censoring is a property of the window, not of the calendar |
| 8.10 | Outliers 94 and 322 | They affect only `agg_industry_profile` (Restaurants, scopes `all` and `left_censored`). Both were already paying in 2022-01, so neither is Won | Restaurants' average monthly payment is 83,208.03 all-in and 67,499.22 ex-outlier |
| 8.11 | `sm_regime` in calculations | Allowed only in diagnostics labelled inferred (`period_type = 'sm_regime'`, `method = 'within_regime'`), never in a headline KPI or a target. **Amends CMO-08**, which said no calculation uses it | The trend check needs it, and the cause of the June-2023 break is unknown |
| 8.12 | **CDO-10 clarified** | No table or view holds a **monetary measure derived from spend** at a grain that includes a customer, industry or cohort key. A dimensionless statistic pairing a segment's counts with company-level spend (r) is allowed: it allocates nothing. The CI test checks column lineage declared in the gold config, not column names | The user asked for per-industry correlations, and r is not an allocation |

## 9. Access (CDO-11, gold part)

### 9.1 Matrix

| Object | `finance` | `revops` | `data` | Basis |
|---|---|---|---|---|
| `dim_month`, `dim_industry`, `dim_spend_category`, `dim_funnel_stage`, `gold_build_status` | read | read | read | No sensitive values |
| `dim_customer`, `fact_acquisition`, `fact_customer_month_revenue` | read | read | read | CDO-11(1): Confidential-Financial pseudonymised data, named roles only |
| `fact_sm_spend` partition `hr_sensitive=false`, `v_sm_spend_shared` | read | read | read | |
| `fact_sm_spend` partition `hr_sensitive=true`, `v_acquisition_month_finance` | read | — | — | CDO-11(2): HR categories are Finance-only, with no exception for `data` |
| `agg_acquisition_month`, `v_acquisition_month`, all `v_funnel_*` | read | read | read | Decision A1 |
| `agg_won_month_industry`, `agg_industry_profile` | read | read | read | Small cells are flagged for any future outside share |
| `agg_won_spend_lag_corr`, `v_corr_signal_summary` | read | read | read | Decision A2 |
| `funnel_conversion_rate` | read + insert | read + insert | read | The rates are business assumptions owned by RevOps and Finance |
| Gold job role | read silver (all partitions); write job-owned gold tables; **Deny** on the rate table | | | §6.5 |
| Any other role (marketing, board, BI) | none | | | CDO-11(5): no grant until suppressed shares exist |

### 9.2 Decisions

- **A1. Total spend, the people group and cost per stage are shared with `finance`, `revops` and `data`.** Total spend already sits unpartitioned in silver `month_control.sm_value_total`, which these three roles read today (`etl/common/schemas.py`: only `sm_spend` and `restatement_log` are HR-partitioned). Restricting it in gold alone would protect nothing. It reveals the people-group total (total − the non-HR categories), which the round-3 CDO-11(2) allows: "their spend_group total ... may be shared". **Residual risk:** if the S&M people cost covers only a few people, a group total comes close to individual pay. That depends on the currency (Q1) and the headcount (Q10). **Contingency:** if Finance and HR answer that it does, total spend and everything derived from it move to Finance-only in silver `month_control` and in gold together, and media + other becomes the shared cost basis.
- **A2. Correlation rows are shared, including those of HR categories.** r is dimensionless and invariant to scale and shift, so it discloses no amount.
- **A3. HR queries run in a Finance-only Athena workgroup** (for example `finora-dl-finance`), with its own results prefix that no other role can read. Athena writes query results to S3, so in the shared `finora-dl` workgroup a Finance query's HR values would land where others can read them.
- **A4. Preconditions before any human role is granted.**
  1. A deny on the `hr_sensitive=true` prefixes for non-Finance principals. `infra/stacks/` has none today (checked 2026-11-17).
  2. Column metrics set to `none` on the money columns of HR-partitioned tables (§5.8).
  3. The Finance workgroup.
- **Ask to the CTO.** Silver `sm_spend` and `restatement_log` were created with default Iceberg metrics. Their manifests may hold the bounds of HR values; check and fix this together with gold.
- **A5. PII minimization.**
  - Gold holds no raw source strings, no `Cliente N` label and no free text from source files.
  - `changed_by` in the rate table is an employee work identity, readable only by the named roles.
  - Aggregates hold no `customer_id`.
- **Ad-hoc files follow the same rule.** `analysis/acquisition/output/report.md` and `monthly_won_revenue_spend.csv` print Team, PayrollExpenses and Freelance per month. Under CDO-11(2) they must be restricted to Finance or regenerated without those columns.

## 10. Gold quality controls and reconciliation to silver

The gold job builds every table on an Iceberg branch, runs the run controls there, and only then fast-forwards `main` for every table (write-audit-publish). A failed control publishes nothing. The previous gold build stays live, and silver is untouched (CTO-10, gold part). Today's expected values are in §12.

| ID | Run control (fails the gold run) |
|---|---|
| GC-01 | **Won.** rows(`fact_acquisition`) = count of silver `customer` with `cohort_month` NOT NULL and `cohort_censoring` ≠ `left` = Σ `agg_acquisition_month.won_count` = Σ `agg_won_month_industry.won_count`, in total and per month |
| GC-02 | **New logos.** Σ `won_new_logo_count` = count of silver `customer.is_new_logo` = Σ silver `month_control.new_logos` = count of silver `customer_month` with `lifecycle_state` = `new` |
| GC-03 | **Partition of payers.** Won + `left` = customers with a known-paid month |
| GC-04 | **New revenue.** Σ `new_revenue_value` = Σ silver `first_paid_amount` × 10,000 over Won, exact, in total and per month. Each `first_paid_amount_value` = `fact_customer_month_revenue.amount_value` at (customer, Won month) |
| GC-05 | **Spend.** rows(`fact_sm_spend`) = rows(silver `sm_spend`); `spend_value` equal per (month, category); Σ per month = silver `month_control.sm_value_total` = `agg_acquisition_month.spend_total_value`; media + other + people = total |
| GC-06 | **Revenue fact.** rows = silver `customer_month` rows; Σ `amount_value` = Σ silver `transactions.amount_value`; Σ `amount_normalized` = Σ `amount` per customer |
| GC-07 | **Dimensions.** Every FK resolves. Rows of `dim_customer` = silver `customer`; `dim_month` = W. A fact month or customer that cannot be resolved fails; unknown industry or category members only alert (CTO-08) |
| GC-08 | **HR isolation.** HR categories sit only in `hr_sensitive=true`. No HR value appears in a log line or the run report. The metrics properties of §5.8 are present |
| GC-09 | **CDO-10.** CI test over the table and view definitions using the declared column lineage (§8.12) |
| GC-10 | **Lineage.** Every lineage column is non-NULL on every row (`_source_line` is NULL only for holes) |
| GC-11 | **Correlations.** An independent recomputation (Python `statistics.correlation`) matches every stored r to within 0.00005, and every `n_pairs` exactly |
| GC-12 | **Funnel arithmetic** (CI, on the views with a fixture rate table). For every row, count(stage) × rate(stage→next) = count(next) before rounding; base reproduces §12.5 exactly; the `sql_demo_080` fixture reproduces §12.6 |

Findings go to the gold run report and do not fail the run: invalid scenarios (GR-01–GR-06), `RATE_HISTORY_REWRITTEN`, `BASE_DIFFERS_FROM_SEED`, and revenue or Won on an unknown member.

## 11. Proposed next view (not in this build): cohort quality

The only lens these files give on "Sales says quality fell" is what Won customers do **after** paying. A proposed `agg_cohort_quality` (Won month or quarter × industry) would hold:
- Won and new logos;
- the median first payment and the median run-rate amount;
- the share still paying at +3, +6 and +12 months, NULL until the cohort is old enough (right-censoring);
- `share_of_observable_months_paid`.

It needs no new source and no spend. It is built only if the user asks (§15).

## 12. Expected results on today's files

Verified on 2026-11-17 by running the silver engine (`etl/tests/golden_helpers.py` `run()`) on `data/*.csv` and recomputing independently. The files' SHA-256 values equal the golden values in `docs/approved_data_rules.md`. The latest succeeded live silver run (`r20261117T150932Z`) should give the same; the CTO confirms on it.

### 12.1 Row counts

| Object | Rows | Notes |
|---|---|---|
| `dim_month` | 34 | 2022-01 → 2024-10; `pre_2023_06` 17 months (incl. 2022-01), `from_2023_06` 17 |
| `dim_industry` | 8 | 6 + UNKNOWN + UNMAPPED |
| `dim_customer` | 1,961 | `left` 377, `probable_left` 43, `none` 1,541, `unknown` 0, never paid 0 |
| `dim_spend_category` | 8 | 7 + UNMAPPED |
| `dim_funnel_stage` | 7 | |
| `fact_acquisition` | 1,584 | |
| `fact_customer_month_revenue` | 66,674 | Paid rows 32,971; Σ `amount_value` 2,214,415,045.08; holes 0 |
| `fact_sm_spend` | 238 | `hr_sensitive=true` 102, `false` 136; Σ `spend_value` 7,781,800,000 |
| `funnel_conversion_rate` | 6 | The seed |
| `agg_acquisition_month` | 34 | 33 with Won |
| `agg_won_month_industry` | 198 | 33 × 6 |
| `agg_industry_profile` | 18 | |
| `agg_won_spend_lag_corr` | 1,848 | No NULL r today |

### 12.2 Won and new revenue

| Figure | Value |
|---|---|
| Won (user definition), 2022-02 → 2024-10 | **1,584** (377 excluded as first paid in 2022-01) |
| of which `probable_left` / `none` / `unknown` | 43 (40 in 2022-02, 3 in 2022-03) / 1,541 / 0 |
| Won with a first-payment multiple | 102 (81 at 2×, 21 at 3×). Among new logos: 59 (47 and 12) |
| New revenue (as paid) | **105,482,511.96** |
| of which from multiples | 10,663,744.35 |
| New revenue, new logos only | 99,728,662.11 |
| New revenue, run-rate variant (inferred) | 99,662,644.41 |
| New revenue per Won / per new logo | 66,592.49 / 64,716.85 |
| Won by year (months; Won per month) | 2022: 380 (11; 34.55) · 2023: 650 (12; 54.17) · 2024: 554 (10; 55.40) |

| Industry | Won | New logos | Multiples | New revenue | Zero-Won months |
|---|---|---|---|---|---|
| Restaurants | 420 | 407 | 28 | 34,958,519.61 | 0 |
| Manufacturing | 363 | 352 | 27 | 23,458,917.93 | 0 |
| Retail | 370 | 364 | 25 | 16,712,170.02 | 0 |
| Technology | 179 | 175 | 5 | 16,795,207.80 | 0 |
| Professional services | 142 | 135 | 10 | 6,702,344.67 | 4 (2022-04, 2022-06, 2022-10, 2024-01) |
| Healthcare | 110 | 108 | 7 | 6,855,351.93 | 3 (2022-09, 2022-12, 2023-09) |
| **Total** | **1,584** | **1,541** | **102** | **105,482,511.96** | 7 |

Industry × month cells: 7 with 0 Won, 56 with 1–4 (`is_small_cell`), and 140 of 198 with fewer than 10 (`is_low_n`).

### 12.3 Spend (full units)

| Figure | Value |
|---|---|
| All 34 months / the 33 Won months / window start (2022-01) | 7,781,800,000 / **7,581,800,000** / 200,000,000 |
| 33 months by non-HR category | PaidMedia 3,349,000,000 · Travel 486,600,000 · PublicidadNoWeb 1,131,100,000 · SoftwareTools 324,600,000 |
| 33 months by group | media 4,480,100,000 · other 811,200,000 · people 2,290,500,000 |
| HR categories | Not reproduced here (CDO-11). The test asserts parity with silver per (month, category) |
| Negative cells | 5, all PayrollExpenses (2023-11, 2023-12, 2024-02, 2024-03, 2024-07), summing to −13,500,000 |
| By regime (months; spend) | `pre_2023_06` Won months 2022-02 → 2023-05 (16; 4,600,900,000) · `from_2023_06` (17; 2,980,900,000) |
| By year (spend; spend per Won) | 2022: 3,095,600,000; 8,146,315.79 · 2023: 2,510,700,000; 3,862,615.38 · 2024: 1,975,500,000; 3,565,884.48 |

### 12.4 Monthly table (`agg_acquisition_month` and `agg_won_month_industry`)

| Month | Won | New logos | Probable left | Multiples | New revenue | Total spend | Rest. | Manuf. | Retail | Tech. | Prof. | Health. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022-02 | 108 | 68 | 40 | 40 | 11,147,080.56 | 230,000,000 | 25 | 25 | 19 | 17 | 16 | 6 |
| 2022-03 | 30 | 27 | 3 | 4 | 2,780,438.64 | 230,000,000 | 11 | 7 | 4 | 4 | 1 | 3 |
| 2022-04 | 19 | 19 | 0 | 1 | 3,975,300.00 | 235,100,000 | 6 | 5 | 4 | 2 | 0 | 2 |
| 2022-05 | 38 | 38 | 0 | 2 | 5,894,203.14 | 270,000,000 | 11 | 9 | 8 | 5 | 3 | 2 |
| 2022-06 | 33 | 33 | 0 | 1 | 2,673,999.93 | 235,100,000 | 7 | 11 | 6 | 6 | 0 | 3 |
| 2022-07 | 32 | 32 | 0 | 1 | 5,484,038.07 | 220,000,000 | 8 | 8 | 7 | 3 | 4 | 2 |
| 2022-08 | 26 | 26 | 0 | 1 | 2,553,621.00 | 325,100,000 | 7 | 7 | 4 | 3 | 3 | 2 |
| 2022-09 | 17 | 17 | 0 | 0 | 1,347,150.00 | 350,000,000 | 4 | 4 | 5 | 2 | 2 | 0 |
| 2022-10 | 32 | 32 | 0 | 0 | 2,252,250.00 | 375,200,000 | 9 | 8 | 5 | 5 | 0 | 5 |
| 2022-11 | 19 | 19 | 0 | 0 | 1,474,725.00 | 300,000,000 | 5 | 5 | 2 | 2 | 3 | 2 |
| 2022-12 | 26 | 26 | 0 | 0 | 6,569,241.00 | 325,100,000 | 10 | 6 | 4 | 5 | 1 | 0 |
| 2023-01 | 60 | 60 | 0 | 0 | 3,693,081.00 | 325,100,000 | 15 | 16 | 15 | 8 | 4 | 2 |
| 2023-02 | 30 | 30 | 0 | 1 | 1,641,990.00 | 250,000,000 | 7 | 6 | 7 | 3 | 4 | 3 |
| 2023-03 | 38 | 38 | 0 | 2 | 1,683,150.00 | 290,000,000 | 7 | 13 | 9 | 5 | 2 | 2 |
| 2023-04 | 51 | 51 | 0 | 1 | 2,886,870.00 | 295,100,000 | 22 | 2 | 13 | 4 | 7 | 3 |
| 2023-05 | 47 | 47 | 0 | 2 | 1,996,049.58 | 345,100,000 | 10 | 6 | 19 | 7 | 3 | 2 |
| 2023-06 | 46 | 46 | 0 | 2 | 2,178,540.00 | 180,000,000 | 7 | 12 | 14 | 5 | 2 | 6 |
| 2023-07 | 65 | 65 | 0 | 0 | 2,532,600.00 | 175,100,000 | 18 | 14 | 18 | 6 | 5 | 4 |
| 2023-08 | 66 | 66 | 0 | 1 | 2,993,130.00 | 110,000,000 | 9 | 22 | 17 | 8 | 6 | 4 |
| 2023-09 | 56 | 56 | 0 | 5 | 2,253,550.32 | 125,200,000 | 19 | 13 | 11 | 4 | 9 | 0 |
| 2023-10 | 64 | 64 | 0 | 1 | 2,961,945.00 | 135,100,000 | 16 | 15 | 19 | 3 | 8 | 3 |
| 2023-11 | 72 | 72 | 0 | 2 | 3,278,191.35 | 130,000,000 | 17 | 21 | 15 | 6 | 8 | 5 |
| 2023-12 | 55 | 55 | 0 | 1 | 3,064,950.00 | 150,000,000 | 17 | 15 | 12 | 5 | 3 | 3 |
| 2024-01 | 57 | 57 | 0 | 0 | 2,313,787.98 | 185,100,000 | 24 | 10 | 13 | 6 | 0 | 4 |
| 2024-02 | 32 | 32 | 0 | 1 | 1,287,465.90 | 200,000,000 | 8 | 9 | 5 | 3 | 1 | 6 |
| 2024-03 | 43 | 43 | 0 | 7 | 2,707,393.29 | 175,100,000 | 7 | 12 | 11 | 4 | 2 | 7 |
| 2024-04 | 69 | 69 | 0 | 9 | 4,189,594.29 | 225,100,000 | 20 | 13 | 17 | 6 | 8 | 5 |
| 2024-05 | 66 | 66 | 0 | 6 | 3,984,671.67 | 235,100,000 | 20 | 14 | 14 | 7 | 8 | 3 |
| 2024-06 | 84 | 84 | 0 | 8 | 4,629,579.78 | 200,000,000 | 24 | 15 | 21 | 10 | 8 | 6 |
| 2024-07 | 48 | 48 | 0 | 2 | 2,378,775.21 | 180,000,000 | 13 | 14 | 5 | 7 | 6 | 3 |
| 2024-08 | 56 | 56 | 0 | 0 | 2,090,916.66 | 190,000,000 | 7 | 10 | 23 | 7 | 5 | 4 |
| 2024-09 | 49 | 49 | 0 | 1 | 2,382,899.19 | 185,100,000 | 12 | 7 | 17 | 5 | 5 | 3 |
| 2024-10 | 50 | 50 | 0 | 0 | 2,201,333.40 | 200,000,000 | 18 | 9 | 7 | 6 | 5 | 5 |
| **Total** | **1,584** | **1,541** | **43** | **102** | **105,482,511.96** | **7,581,800,000** | **420** | **363** | **370** | **179** | **142** | **110** |

Window-start row (2022-01): Won columns NULL; `spend_total_value` 200,000,000.

### 12.5 Funnel, `base` scenario (counts 6 dp, costs 2 dp, HALF_UP)

| Stage | Π to Won | Full period, user Won: count / cost per unit | Full period, new logo: count / cost per unit | 2024-10: count / cost per unit |
|---|---|---|---|---|
| New | 0.02688 | 58,928.571429 / 128,660.85 | 57,328.869048 / 132,251.00 | 1,860.119048 / 107,520.00 |
| Working | 0.0336 | 47,142.857143 / 160,826.06 | 45,863.095238 / 165,313.74 | 1,488.095238 / 134,400.00 |
| Engaged | 0.084 | 18,857.142857 / 402,065.15 | 18,345.238095 / 413,284.36 | 595.238095 / 336,000.00 |
| SQL | 0.168 | 9,428.571429 / 804,130.30 | 9,172.619048 / 826,568.72 | 297.619048 / 672,000.00 |
| Demo | 0.24 | 6,600.000000 / 1,148,757.58 | 6,420.833333 / 1,180,812.46 | 208.333333 / 960,000.00 |
| Proposal | 0.40 | 3,960.000000 / 1,914,595.96 | 3,852.500000 / 1,968,020.77 | 125.000000 / 1,600,000.00 |
| Won (Real) | 1 | 1,584 / **4,786,489.90** | 1,541 / 4,920,051.91 | 50 / 4,000,000.00 |

The inputs are Won 1,584 or 1,541 with spend 7,581,800,000 (33 months), and Won 50 with spend 200,000,000 for 2024-10. Cost per Won for the new-logo definition equals the deferred CMO-05 `sm_spend_per_new_logo` for the same months.

Other months:
- 2022-09 (lowest Won, 17; spend 350,000,000): New 632.440476 / 553,411.76, Won 20,588,235.29.
- 2022-02 (Won 108; spend 230,000,000): New 4,017.857143 / 57,244.44, Won 2,129,629.63.

| `v_funnel_period`, stage WON | Months | Won | Won per month | Spend | Spend per month | Cost per Won |
|---|---|---|---|---|---|---|
| `sm_regime` = `pre_2023_06` | 16 | 606 | 37.875 | 4,600,900,000 | 287,556,250.00 | 7,592,244.22 |
| `sm_regime` = `from_2023_06` | 17 | 978 | 57.529412 | 2,980,900,000 | 175,347,058.82 | 3,047,955.01 |
| `year` 2022 (partial, 11) | 11 | 380 | 34.545455 | 3,095,600,000 | 281,418,181.82 | 8,146,315.79 |
| `year` 2023 | 12 | 650 | 54.166667 | 2,510,700,000 | 209,225,000.00 | 3,862,615.38 |
| `year` 2024 (partial, 10) | 10 | 554 | 55.400000 | 1,975,500,000 | 197,550,000.00 | 3,565,884.48 |

Quarters (Won; spend; cost per Won):

| Year | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|
| 2022 | 138; 460,000,000; 3,333,333.33 (2 months) | 90; 740,200,000; 8,224,444.44 | 75; 895,100,000; 11,934,666.67 | 77; 1,000,300,000; 12,990,909.09 |
| 2023 | 128; 865,100,000; 6,758,593.75 | 144; 820,200,000; 5,695,833.33 | 187; 410,300,000; 2,194,117.65 | 191; 415,100,000; 2,173,298.43 |
| 2024 | 132; 560,200,000; 4,243,939.39 | 219; 660,200,000; 3,014,611.87 | 153; 555,100,000; 3,628,104.58 | 50; 200,000,000; 4,000,000.00 (1 month) |

### 12.6 Scenario fixture and sensitivity (tests only; not seeded)

Fixture `sql_demo_080` = base with SQL→DEMO at 0.80; full period, user Won.

| Column | Value |
|---|---|
| `overall_rate` / `overall_rate_base` | 0.03072 / 0.02688 |
| `new_estimated_base` | 58,928.571429 |
| `won_implied_same_new` (delta, %) | 1,810.285714 (+226.285714, +14.285714%) |
| `new_required_same_won` (delta) | 51,562.500000 (−7,366.071429) |
| `cost_per_won_implied_value` | 4,188,178.66 (base 4,786,489.90) |

`v_funnel_rate_sensitivity`, base, full period, user Won (+1 rate point, New held fixed):

| Transition | Rate | Won % per point | Extra Won per point |
|---|---|---|---|
| NEW→WORKING | 0.80 | 1.250000 | 19.800000 |
| WORKING→ENGAGED | 0.40 | 2.500000 | 39.600000 |
| ENGAGED→SQL | 0.50 | 2.000000 | 31.680000 |
| SQL→DEMO | 0.70 | 1.428571 | 22.628571 |
| DEMO→PROPOSAL | 0.60 | 1.666667 | 26.400000 |
| PROPOSAL→WON | 0.40 | 2.500000 | 39.600000 |

### 12.7 Industry profile (`agg_industry_profile`)

| Industry | Scope | Customers | Paid months | Avg monthly payment | Ex-outlier | Median | Avg months paying | Avg months observable | Share paid |
|---|---|---|---|---|---|---|---|---|---|
| Restaurants | all | 529 | 9,112 | 83,208.03 | 67,499.22 | 56,516.25 | 17.2250 | 19.2420 | 0.8952 |
| Restaurants | won | 420 | 5,819 | 61,846.98 | 61,846.98 | 50,421.00 | 13.8548 | 15.4119 | 0.8990 |
| Restaurants | left_censored | 109 | 3,293 | 120,954.76 | 77,659.99 | 63,000.00 | 30.2110 | 34.0000 | 0.8886 |
| Manufacturing | all | 454 | 7,855 | 63,695.82 | 63,695.82 | 50,400.00 | 17.3018 | 19.6784 | 0.8792 |
| Manufacturing | won | 363 | 5,205 | 51,948.78 | 51,948.78 | 42,000.00 | 14.3388 | 16.0882 | 0.8913 |
| Manufacturing | left_censored | 91 | 2,650 | 86,768.79 | 86,768.79 | 67,410.00 | 29.1209 | 34.0000 | 0.8565 |
| Retail | all | 428 | 6,472 | 42,327.41 | 42,327.41 | 31,500.00 | 15.1215 | 17.3014 | 0.8740 |
| Retail | won | 370 | 4,894 | 38,077.60 | 38,077.60 | 25,200.00 | 13.2270 | 14.6838 | 0.9008 |
| Retail | left_censored | 58 | 1,578 | 55,507.74 | 55,507.74 | 42,000.00 | 27.2069 | 34.0000 | 0.8002 |
| Technology | all | 241 | 4,423 | 78,932.04 | 78,932.04 | 63,000.00 | 18.3527 | 21.0373 | 0.8724 |
| Technology | won | 179 | 2,551 | 68,094.48 | 68,094.48 | 52,500.00 | 14.2514 | 16.5475 | 0.8612 |
| Technology | left_censored | 62 | 1,872 | 93,700.55 | 93,700.55 | 83,275.50 | 30.1935 | 34.0000 | 0.8880 |
| Professional services | all | 165 | 2,641 | 55,137.87 | 55,137.87 | 35,700.00 | 16.0061 | 17.9212 | 0.8931 |
| Professional services | won | 142 | 1,962 | 43,490.25 | 43,490.25 | 31,500.00 | 13.8169 | 15.3169 | 0.9021 |
| Professional services | left_censored | 23 | 679 | 88,794.18 | 88,794.18 | 63,000.00 | 29.5217 | 34.0000 | 0.8683 |
| Healthcare | all | 144 | 2,468 | 75,856.65 | 75,856.65 | 67,200.00 | 17.1389 | 19.5000 | 0.8789 |
| Healthcare | won | 110 | 1,523 | 63,247.72 | 63,247.72 | 63,000.00 | 13.8455 | 15.0182 | 0.9219 |
| Healthcare | left_censored | 34 | 945 | 96,177.71 | 96,177.71 | 84,000.00 | 27.7941 | 34.0000 | 0.8175 |

Outliers: 2 (customers 94 and 322, both Restaurants and `left_censored`). Paid months sum to 32,971.

**Caveat for readers.** In every industry, Won customers pay less per month than customers who were already paying in 2022-01. That is not evidence that quality fell: the older group survived longer and had more time to expand. §11 is the like-for-like view.

### 12.8 Correlations, company scope, user's Won (r to 4 dp; `*` = signal at 5%)

n: level and within_regime 33 / 33 / 32 / 31; diff 32 / 32 / 31 / 30. Critical \|r\|: 0.3440 / 0.3440 / 0.3494 / 0.3550 (level, within); 0.3494 / 0.3494 / 0.3550 / 0.3610 (diff).

| Series | level L0 | L1 | L2 | L3 | diff L0 | L1 | L2 | L3 | within L0 | L1 | L2 | L3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PaidMedia | −0.4805* | −0.4312* | −0.3859* | −0.3406 | +0.0120 | −0.0941 | +0.1472 | −0.1291 | −0.1664 | −0.1323 | +0.1103 | +0.1001 |
| Travel | −0.4305* | −0.5374* | −0.4053* | −0.2187 | +0.2138 | −0.3229 | −0.0513 | +0.2078 | −0.0849 | −0.3347 | +0.0328 | +0.2945 |
| PublicidadNoWeb | −0.4109* | −0.4362* | −0.5165* | −0.3266 | +0.1748 | −0.0259 | −0.2808 | +0.0251 | −0.0985 | −0.1716 | −0.1084 | +0.2005 |
| Freelance | −0.5965* | −0.5674* | −0.6236* | −0.5068* | −0.0771 | −0.0353 | −0.1525 | +0.1572 | −0.3841* | −0.3202 | −0.0712 | +0.1820 |
| SoftwareTools | −0.3865* | −0.4538* | −0.4820* | −0.0980 | −0.0252 | −0.0589 | −0.3765* | +0.4157* | −0.1066 | −0.2519 | −0.2336 | +0.3833* |
| Team | +0.2654 | +0.1976 | +0.5281* | +0.5996* | +0.2085 | −0.1489 | −0.1568 | +0.1475 | −0.1688 | −0.3078 | +0.0305 | +0.2309 |
| PayrollExpenses | −0.2890 | −0.3760* | −0.2438 | −0.0769 | +0.1489 | −0.1640 | −0.0493 | +0.1889 | +0.0447 | −0.2008 | +0.0678 | +0.2135 |
| GROUP_MEDIA | −0.4783* | −0.4484* | −0.4372* | −0.3496 | +0.0719 | −0.0822 | +0.0125 | −0.0907 | −0.1594 | −0.1540 | +0.0551 | +0.1337 |
| GROUP_PEOPLE | −0.4067* | −0.4678* | −0.3024 | −0.1084 | +0.1598 | −0.1875 | −0.1004 | +0.2354 | −0.1122 | −0.2897 | +0.0436 | +0.2609 |
| GROUP_OTHER | −0.4416* | −0.5378* | −0.4712* | −0.1787 | +0.0988 | −0.2138 | −0.2716 | +0.3822* | −0.1107 | −0.3323 | −0.0991 | +0.3699* |
| TOTAL | −0.4795* | −0.4964* | −0.4190* | −0.2609 | +0.1412 | −0.1790 | −0.0895 | +0.1377 | −0.1586 | −0.2523 | +0.0363 | +0.2266 |

TOTAL, level, new-logo definition: −0.5508 / −0.5401 / −0.4143 / −0.2609.

TOTAL, level, user's Won by industry (L0 / L1 / L2 / L3):

| Industry | L0 | L1 | L2 | L3 |
|---|---|---|---|---|
| Restaurants | −0.3217 | −0.4725 | −0.3806 | −0.3315 |
| Manufacturing | −0.5585 | −0.4918 | −0.3776 | −0.1885 |
| Retail | −0.4035 | −0.3815 | −0.2885 | −0.1090 |
| Technology | −0.1316 | −0.1637 | −0.0610 | +0.0326 |
| Professional services | −0.3537 | −0.3906 | −0.3208 | −0.1178 |
| Healthcare | −0.3892 | −0.2027 | −0.2826 | −0.4068 |

`v_corr_signal_summary`: the user's Won is in §7.5. For the new-logo definition, the signals are: level 32 of 44 (company) and 123 of 264 (industries); diff 3 and 13; within_regime 3 and 14.

**Correction to the main-session summary.** "Month-over-month changes show no relation (|r| ≤ 0.18)" holds for PaidMedia and total spend. Across all 11 series, 3 of 44 company-level diff tests cross 5% (maximum |r| 0.4157, SoftwareTools at lag 3), which is about what chance gives (2.2).

## 13. Not supported by current data

| Question from the meeting | Why these files cannot answer it | Data needed | Owner |
|---|---|---|---|
| Where in the funnel we lose growth; whether the problem is after SQL | No stage exists before the first payment. Estimated stages are Won ÷ assumptions, with the same shape every month | CRM stage events: one row per lead or opportunity × stage entry, with timestamps, outcome and lost reason | RevOps / Sales Ops |
| "Marketing brings more demand" (more New) | New is not in any file; the model's New is derived from Won | Lead creation events with source and campaign | Marketing + RevOps |
| "Sales says quality fell" | No pre-sale attributes and no lost leads. Only post-Won behaviour exists (§11) | Lead firmographics and ICP fit at creation; the reasons leads are lost | RevOps + Marketing |
| "We respond slowly" | No timestamps | First-response time per inbound lead | Sales Ops |
| Product-led payers vs near-direct-to-SQL vs weeks in a stage | No sign-up, trial or path data; no time in stage | Product sign-up, activation and self-serve checkout events, keyed to the customer; CRM stage timestamps | Product / Engineering + RevOps |
| Which channel or spend drives Won | Spend is company × month × category with no channel, campaign or customer key (CDO-10); correlations are confounded (§7.5) | Spend by channel and campaign (monthly or weekly), plus lead source per customer as an approved allocation key | Marketing + Finance |
| Time from close to first payment; whether "first payment" is the true start | First-invoice and contract dates are unknown (Q7) | Contract or first-invoice date per customer | Billing |
| Comparing costs across markets and currencies | Currency, basis and scope are unconfirmed (Q1, Q3, Q4) | Owner statements | Finance |

To join any of these to the current model, every new source needs the key that maps its customer to `customer_id`, from RevOps (Q12).

## 14. Build notes for the CTO

### 14.1 Orchestration and publish

- **Job.** A new Glue 5.0 Spark job (suggested name `finora-dl-gold-build`, with `--datalake-formats iceberg`).
- **Trigger.** It runs in `finora-dl-ingest` after the silver job, and only when silver succeeded. It reads silver by the run tag.
- **Publish.** Write-audit-publish (§10). On success it emits the architecture's `gold.refreshed` event.
- **Views.** Deployed as Athena DDL with the code. The rate table is created and seeded by the idempotent step in §6.5.
- **No AWS change without the user's approval of that specific change.**

### 14.2 Gold config

Generate `etl/config/gold_acquisition.yaml` from this document, in the same way as `dl_rules.yaml`. Its SHA-256 is `_gold_model_version`. It holds:
- the stage, industry and category seeds (§5);
- the base-rate seed (§6.1);
- the parameters: lags `[0,1,2,3]`, α 0.05 two-sided, `low_n` 10, small cell 5, `low_volume` 10, regime boundary `2023-06`, rate point 0.01;
- the rounding rules (§2);
- the column lineage for the CDO-10 test.

### 14.3 Tests

- §12 is the golden result on `data/*.csv`.
- Synthetic cases must cover:
  - a hole in a Won month and in a first-payment month;
  - a missing S&M month (`spend_missing`);
  - a tripwire month;
  - a month with Won = 0;
  - an invalid scenario for each GR check;
  - a history rewrite.

## 15. Open questions

**For the user** (defaults apply until answered):
1. **Total spend and cost per stage for `revops` and `data`.** Default: yes, as silver already allows (A1). Alternative: Finance-only until Finance answers the Q10 extension.
2. **Who edits rates.** Default: `finance` and `revops`, with `data` read-only. Should `data` also edit?
3. **Marketing access.** The CMO's team has no role today. Default: no gold access. Granting it requires the CDO-11(3)–(5) suppressed shares first; say if they need it now.
4. **The cohort-quality view (§11).** It is the only test of "quality fell" that these files support. Build it next?

**Asks for the data owners** (named):

| Ask | Owner | Unblocks |
|---|---|---|
| CRM stage events with timestamps, outcome and lost reason, plus the customer ↔ CRM key | RevOps / Sales Ops | Real stage counts, conversion, time in stage, the "after SQL" question |
| Lead source and campaign per lead and per customer; spend by channel and campaign | Marketing (+ Finance for spend) | Channel attribution; an approved CDO-10 allocation key |
| Product sign-up, activation and self-serve checkout events | Product / Engineering | Product-led vs sales-led paths |
| First-response timestamps for inbound leads | Sales Ops | The response-speed hypothesis |
| Q10 extension: could the people-group total (Team + PayrollExpenses + Freelance) reveal one person's pay? How many people does it cover? | Finance + HR | Decision A1 and its contingency |
| Q1, Q3, Q4: currency; actual or budget; whether Transactions covers the base the S&M spend acquires | Finance | Every money status in this model |
| Q7: the true first-invoice or contract date | Billing | The meaning of "Won" and its lag to the close |

## 16. Decision levers (addendum, CDO, 2026-11-17)

The user rejected the §7.5 reading as a page headline: "The funnel page does not allow to take any decisions. One cannot simply say there's no relationships, I need a way to provide an insight on what variable I could move." This section defines the lever planner of `contracts/acq_api_contract.md` v1.2 (`levers` block). **It wins over the contract's working definitions on any conflict.** §7.5 stays as the evidence behind the signals; §16.6 replaces its "Reading for users" on the page. Everything here is computed from silver `customer`, `customer_month` and `month_control` (and gold's own `fact_acquisition`, `agg_acquisition_month`); no new source.

**Amendments to earlier sections, made here:**
- **§8.11.** `sm_regime` may also be used as a **baseline preset** of the planner (labelled inferred). It still never defines a target; targets are the user's inputs.
- **§11 / §15 Q4.** The cohort-quality view is built now, as `agg_acq_cohort_quality` (§16.4), because the user asked for decision levers.
- **§2 rounding, one exception.** `new_mrr_per_month_value` and `payback_months` are computed from the **published, rounded** operands (§16.2), so the UI reproduces them exactly with the contract's exact-decimal arithmetic.

### 16.1 What changed against the coordinator's working draft (contract v1.2)

| # | Item | Draft | §16 (canonical) | Why | Effect today (user's Won) |
|---|---|---|---|---|---|
| 1 | Amount used for the run-rate | Raw `amount` of the paid months 2–4 | `amount_normalized` (CRO-03, which includes SB-06 settlements and SB-11 uneven splits) of the months 2–4 where it is > 0 | A catch-up month in the window counted at its 2×/3× value while the gap months it settles were dropped: that inflates the ticket. Normalized, each settled month carries its share and an uneven split carries its baseline b | Before Jun 2023: 56,382.85 → **55,767.62** |
| 2 | Censoring | Partial windows allowed (months beyond the data simply dropped) | **Mature cohorts only:** the Won month + 3 ≤ `data_complete_through` | Cohorts with 1 or 2 observed months are compared with cohorts with 3. Today the 155 Won of 2024-08 → 2024-10 have no run-rate yet | From Jun 2023: 42,625.13 → **42,550.70** (809 customers) |
| 3 | Shift-share weights | Shares of **Won** | Shares of **run-rate customers** | With Won shares the parts do not add up to the change of the two published means: the draft's −849 + −12,969 = −13,818, while 42,625 − 56,383 = −13,758 | Mix **−558.82**, within **−12,658.10**, total **−13,216.92** (exact) |
| 4 | Money rounding | `cost_per_won_value` "7592244.00", `spend_per_month_value` whole units | 2 dp HALF_UP on both | 175,347,058.82 a month is not a whole number | 7,592,244.22 and 175,347,058.82 |
| 5 | Confirmed unchanged | | Window months 2–4, first payment excluded, customers with no qualifying month left out of the mean (and counted), `new_mrr_per_month` = Won/month × run-rate, payback = cost per Won ÷ run-rate, `paying_m6/m12` = strict `is_paying` among observable customers, half-year cohorts | | Retention figures of the draft reproduce exactly |
| 6 | Added | | `won_definition` on every lever table; completeness counts (`run_rate_no_paid_customers`, `run_rate_immature_customers`, `paying_m6_eligible`, …); per-industry shift-share terms | Same conventions as the rest of the model (§4 change 4) | |

**A finding the draft did not show, which the page must not contradict.** The ticket step **precedes** the spend break. By half-year cohort: 2022-H2 61,597.90 → 2023-H1 45,109.09 → 2023-H2 39,934.42; the Jan–May 2023 cohorts alone, all before the break, are already at **45,096.88** (223 customers). Monthly values are noisy (2022-09 38,109; 2022-11 75,020; 2022-12 60,340; 2023-01 45,532), so the step is dated to the half-year, not to a month. The regime split is therefore a convenient baseline, not the boundary of the change. No label may say or imply that the spend regime lowered the ticket (or that it raised Won).

### 16.2 Definitions

Let *c* be a Won customer's Won month (`cohort_month`), with *c* as "month 1".

**Per customer (on `fact_acquisition`, §16.4):**
- **Run-rate window:** months *c*+1, *c*+2, *c*+3 (the user's "months 2–4"). The first payment is never in it: it may be a multiple (SB-04) or a catch-up.
- **Qualifying month:** `amount_normalized` > 0. That is a paid month, or a zero month settled later by a catch-up, prepay or split (SB-06, CRO-03); an SB-11 uneven-split month counts at its baseline b. A paused, grace or churned month does not qualify.
- **`run_rate_status`:** `immature` when *c* + 3 > `data_complete_through`; else `no_paid_month` when no month qualifies (an early leaver); else `ok`.
- **`run_rate_m2_4_value`** (status `ok` only) = Σ `amount_normalized` × 10,000 over the qualifying months ÷ their number, HALF_UP to 6 dp. NULL otherwise. **Inferred** (it relies on SB-06/CRO-03 settlements). It is not `run_rate_amount_value` (§5.6), which substitutes a multiple first payment in new revenue.
- **Outliers.** SB-08 outlier customers are kept: they are real customers. 94 and 322 were paying at the window start (`left`), so they are never Won and enter no lever. Today 0 Won customers are outliers; every lever aggregate carries `outlier_customers`, and the page shows a note when it is > 0.
- **`paying_m6` / `paying_m12`:** `is_paying` (the dictionary's canonical "paying", `amount` > 0) in month *c*+5 / *c*+11. NULL when that month is after `data_complete_through` (not observable). This is strict cash: a gap that a later catch-up settles counts as not paying, so it is a lower bound of retention (the paid-or-settled variant is at most 1.4 points higher today: 2023-H2 at month 6, 95.2 vs 96.6). It is a retention marker, not churn: churn needs the 3-month grace window.

**Per period (`agg_acq_lever_period`):**
- **Periods** are the inferred `sm_regime` of `dim_month`: `pre_2023_06` = 2022-02 → 2023-05 (16 Won months), `from_2023_06` = 2023-06 → `data_complete_through` (17 today). Labelled inferred.
- **`won_per_month`** = Won ÷ Won-reportable months of the period up to `data_complete_through`; DECIMAL(18,6) HALF_UP.
- **`run_rate_mrr_per_won_value`** = mean of `run_rate_m2_4_value` over the period's `ok` customers (customer-weighted), HALF_UP 2 dp. It is "per Won customer with an observable run-rate"; the label on the page is "Starting monthly revenue per new customer (months 2–4)". `run_rate_customers` + `run_rate_no_paid_customers` + `run_rate_immature_customers` = `won_count`. `run_rate_last_cohort_month_key` = the last Won month that is mature (2024-07 today).
- **`new_mrr_per_month_value`** = `won_per_month` (6 dp) × `run_rate_mrr_per_won_value` (2 dp), HALF_UP 2 dp. It applies the mature customers' ticket to every Won of the period, including the early leavers (2.6% and 1.7% of mature Won today), so it is an upper bound by that share. It is "new MRR at run-rate", not booked revenue.
- **`spend_per_month_value`** = period spend (§3: the spend of the Won months only) ÷ months, 2 dp. **`cost_per_won_value`** = period spend ÷ Won, 2 dp. Both NULL when Won = 0 or any month of the period has a non-null `cost_null_reason` (§7.1). Never called "CAC".
- **`payback_months`** = `cost_per_won_value` ÷ `run_rate_mrr_per_won_value`, HALF_UP 1 dp; NULL when either is NULL. Page label: **"Simple cash-revenue payback: months of starting revenue needed to cover S&M spend per new customer. Revenue, not margin; undiscounted; assumes no churn; currency not stated."** It is not a margin payback and not LTV/CAC (the CFO owns those).
- **`paying_m6_share` / `paying_m12_share`** = Σ `paying_m6` true ÷ Σ eligible (non-NULL) customers, DECIMAL(9,4); `paying_m6_eligible`, `paying_m6_count` published; NULL when eligible = 0.

**Per industry (`agg_acq_lever_industry`)**: the same Won, run-rate and retention measures by `industry_key` within a period, plus `won_share` (of the period's Won) and `run_rate_share` (of its run-rate customers). **No spend, cost or payback by industry** (CDO-10, §8.12).

**Value change (shift-share), `agg_acq_value_change`.** From period 0 to period 1, with *s* = `run_rate_share` and *v* = `run_rate_mrr_per_won_value` (unrounded) of each industry *i*:
- total = v̄₁ − v̄₀ (the two period means); mix = Σᵢ (s₁ᵢ − s₀ᵢ) × v₀ᵢ; within-industry = Σᵢ s₁ᵢ × (v₁ᵢ − v₀ᵢ). Mix + within = total exactly.
- The split is order-dependent. The reverse order (mix at new values, within at old shares) is published as `mix_reverse_order_value`; today it is −428.14, so "about 96% within industries" holds either way.
- An industry with run-rate customers in only one of the two periods makes the split NULL (`null_reason` = `industry_not_in_both_periods`). Today all 6 are in both. UNKNOWN and UNMAPPED are members like any other.

**Half-year cohorts.** `cohort_half` = `YYYY-H1` (Won month Jan–Jun) or `YYYY-H2` (Jul–Dec). 2022-H1 is Feb–Jun 2022 (the window start is excluded) and holds the 43 `probable_left` customers under the user's Won; `won_definition = 'new_logo'` removes them. A cohort is `is_complete_m6` (`_m12`, `_run_rate`) when every member is observable for that measure; a partial cohort shows its eligible count.

### 16.3 The four planner levers

The planner starts from one period's baseline (default `from_2023_06`, the most recent; user's Won). With **f** = overall(s) ÷ overall(base) (conversion), **Δmix** (industry mix), **t** (ticket change) and **g** (spend change), computed in this order with exact decimals, HALF_UP at each step:

- Won′ = `won_per_month` × f (6 dp)
- run-rate′ = (`run_rate_mrr_per_won_value` + Δmix) × (1 + t) (2 dp)
- new MRR′ = Won′ × run-rate′ (2 dp)
- cost per Won′ = `cost_per_won_value` × (1 + g) ÷ f (2 dp)
- payback′ = cost per Won′ ÷ run-rate′ (1 dp)

With f = 1 and Δmix = t = g = 0 this reproduces the gold baseline exactly. An output's evidence label is the weakest label among the levers moved (Untested < Assumption < Observed).

| Lever | What the user moves | Arithmetic | Evidence label | How to read (one line on the page) |
|---|---|---|---|---|
| 1. Conversion rates | The six stage rates (a scenario) | f = overall(s) ÷ overall(base); Won′ and cost per Won′ | **Assumption** | "If the stage rates were these, new customers would change by this much. No stage before Won is observed in the data." |
| 2. Ticket size | t, a % on the starting monthly revenue per new customer | run-rate′ = run-rate × (1 + t) | **Observed baseline; the target is your choice** | "New customers start at 42,551 a month today. Reference: +29.7% would bring each industry back to its Feb-2022–May-2023 level at today's mix." |
| 3. Industry mix | p points of new customers moved from industry A to B | Δmix = p/100 × (v_B − v_A), at the period's observed `run_rate_mrr_per_won_value` | **Observed values, assuming they hold** | "Moving 10 points of new customers from Retail to Technology adds 2,447 a month per new customer, if each industry's ticket holds and the volume can be won at today's cost." |
| 4. Spend | g, a % on S&M spend per month | cost per Won′ and payback′ only; **Won held flat** | **Untested on Won** | "Changes what each new customer costs and the payback. Whether spend changes the number of new customers is not measurable in these files: test it before relying on it." |

**Lever 3 rules.** The UI moves shares between two industries only, keeps every share in [0, 1], and blocks a move into or out of a cell with `is_low_n` (fewer than 10 run-rate customers in the period; none today). The run-rate reference for the "observed" label is the selected period's own per-industry value.

**Lever 4: recommended test design (owners: CMO executes, CFO sets the spend at risk, CDO registers the metrics).**
1. **Why a company-level test is not enough.** Won per month has a standard deviation of 12.5 in `from_2023_06` (mean 57.5). A company-level switchback (alternating high and low media months) over 12 months detects only a change of about 20 Won a month (35%), at 5% two-sided and 80% power; over 24 months, about 14 (25%).
2. **Prerequisite.** Lead source and campaign per customer, and spend by channel and campaign, keyed to `customer_id` (§13; Marketing + RevOps, Q12). Without it there is no unit to randomize.
3. **Design.** A holdout on PaidMedia, the largest media line: randomize a targetable unit (region, audience or channel) into hold and increase cells for 8–12 weeks, with a pre-registered primary metric (Won, `new_logo` definition, per cell), secondary metrics (`run_rate_m2_4_value`, `paying_m6`), lags 0–3 months as in §7.4, and a decision rule set before the start: incremental Won ÷ incremental spend compared with today's cost per Won.
4. Until a test reads out, lever 4 stays **Untested** and the page never shows a Won change from spend.

### 16.4 Gold tables for the levers

Every table carries the gold lineage block (§2) and, where money appears, the four statuses. Access is as `agg_acquisition_month` (F, R, D; decision A1); none of these holds an HR category. Customer-level columns are F, R, D as `fact_acquisition`.

**(a) New columns on `fact_acquisition`** (customer grain):

| Column | Type | Definition |
|---|---|---|
| `cohort_half` | STRING | `YYYY-H1` / `YYYY-H2` of `won_month_key` |
| `run_rate_status` | STRING | `ok`, `no_paid_month`, `immature` |
| `run_rate_m2_4_months` | INT | Qualifying months in the window, 0–3; NULL when `immature` |
| `run_rate_m2_4_value` | DECIMAL(18,6) | §16.2; NULL unless `ok`. **Inferred** |
| `paying_m6`, `paying_m12` | BOOLEAN | §16.2; NULL when not observable |

**(b) `agg_acq_cohort_quality`** (materialized). Grain: `won_definition` × `won_month_key` × `industry_key`, dense on the registered industries (an unknown member only when it has Won). PK all three. Rows today: 2 × 33 × 6 = **396**. All measures are additive, so any rollup (half-year, period, company) is exact.

| Column | Type | Definition |
|---|---|---|
| `won_definition`, `won_month_key`, `industry_key`, `cohort_half` | STRING, INT, SMALLINT, STRING | Keys (`cohort_half` derived) |
| `won_count` | INT | Won in the cell |
| `run_rate_customers`, `run_rate_no_paid_customers`, `run_rate_immature_customers` | INT | By `run_rate_status`; they sum to `won_count` |
| `run_rate_m2_4_sum_value` | DECIMAL(38,6) | Σ `run_rate_m2_4_value` of the `ok` customers |
| `paying_m6_eligible`, `paying_m6_count`, `paying_m12_eligible`, `paying_m12_count` | INT | |
| `outlier_customers` | INT | |
| `is_low_n`, `is_small_cell` | BOOLEAN | `won_count` < 10; 0 < `won_count` < 5 (CDO-11(3)) |

**(c) `agg_acq_lever_period`** (materialized). Grain: `won_definition` × `period_code`. Rows today: **4**. Columns: `period_code`, `period_label`, `is_inferred` (true), `first_month_key`, `last_month_key`, `months` INT, `won_count` INT, `won_per_month` DECIMAL(18,6), `run_rate_customers`, `run_rate_no_paid_customers`, `run_rate_immature_customers` INT, `run_rate_last_cohort_month_key` INT, `run_rate_mrr_per_won_value` DECIMAL(18,2), `new_mrr_per_month_value` DECIMAL(18,2), `spend_total_value` DECIMAL(18,0), `spend_per_month_value` DECIMAL(18,2), `cost_per_won_value` DECIMAL(18,2), `payback_months` DECIMAL(9,1), `cost_null_reason` STRING, `paying_m6_eligible`, `paying_m6_count` INT, `paying_m6_share` DECIMAL(9,4), the same three for m12, `outlier_customers` INT. Spend enters only at period grain, with no customer, industry or cohort key (CDO-10 holds).

**(d) `agg_acq_lever_industry`** (materialized). Grain: `won_definition` × `period_code` × `industry_key`. Rows today: **24**. Columns: `won_count`, `won_share` DECIMAL(9,4), `run_rate_customers`, `run_rate_no_paid_customers`, `run_rate_immature_customers`, `run_rate_share` DECIMAL(9,4), `run_rate_mrr_per_won_value` DECIMAL(18,2), the m6/m12 eligible, count and share columns, `outlier_customers`, `is_low_n` (`run_rate_customers` < 10), `is_small_cell`. **No spend-derived column.**

**(e) `agg_acq_value_change`** (materialized). Grain: `won_definition` × `from_period_code` × `to_period_code` × `industry_key`. Rows today: 2 × 1 × 6 = **12**. Columns: `share_from`, `share_to` DECIMAL(9,4) (run-rate shares), `value_from`, `value_to` DECIMAL(18,2), `mix_term_value`, `within_term_value`, `mix_reverse_term_value`, `within_reverse_term_value` DECIMAL(18,6) (each term from unrounded operands), `null_reason`. Totals = Σ terms, HALF_UP 2 dp.

**(f) View `v_acq_cohort_half`**: `agg_acq_cohort_quality` rolled up to `won_definition` × `cohort_half` (company level): Σ counts; run-rate = Σ sum ÷ Σ customers (2 dp); shares from counts; `is_complete_m6` = (`paying_m6_eligible` = `won_count`), likewise m12 and run-rate.

**Mapping to the contract's `levers` block** (user's Won, `won_definition = 'first_payment'`; a contract bump to v1.3 is needed for the added fields, by agreement):

| Contract | Gold | Notes |
|---|---|---|
| `definitions_version` | `"cdo-s16-2026-11-17"` | Replaces `draft-2026-11-17` |
| `periods[]` | `agg_acq_lever_period` | Add `run_rate_no_paid_customers`, `run_rate_immature_customers`, `run_rate_last_cohort_month` (`YYYY-MM`), `paying_m6_eligible`, `paying_m12_eligible`, `cost_null_reason`, `inferred: true`. `paying_m*_pct` = share × 100, 1 dp HALF_UP from the counts. Money strings 2 dp; `payback_months` 1 dp |
| `industries[]` | `agg_acq_lever_industry` | `share_pct` = `won_share` × 100 (1 dp). Add `run_rate_customers`, `run_rate_share_pct`, `paying_m6_pct` |
| `value_change` | Σ over `agg_acq_value_change` | Add `mix_reverse_order_value` and `by_industry[]` (`industry_code`, `mix_value`, `within_industry_value`) |
| `cohorts[]` | `v_acq_cohort_half` | `run_rate_mrr_per_won_value`, `is_complete_m6`, `is_complete_m12`, add `is_complete_run_rate`, `paying_m6_eligible`, `paying_m12_eligible` |

**New run controls** (fail the gold run, added to §10):
- **GC-13.** Σ `agg_acq_cohort_quality.won_count` = GC-01 per month and industry; the three run-rate counts sum to `won_count` on every row; each period row equals the rollup of the cohort table; `run_rate_m2_4_sum_value` = Σ `fact_acquisition.run_rate_m2_4_value`.
- **GC-14.** Σ mix + Σ within = v̄₁ − v̄₀ within 0.00001; `new_mrr_per_month_value` and `payback_months` reproduce from the published operands exactly; count ≤ eligible ≤ Won for m6 and m12.
- **GC-09 extended.** `agg_acq_lever_industry`, `agg_acq_cohort_quality` and `agg_acq_value_change` have no column with spend lineage.

### 16.5 Expected figures on today's files

Verified on 2026-11-17 with the silver engine (`etl/tests/golden_helpers.py` `run()`, run tag `r20261117T150932Z`) on `data/*.csv`, by an independent Python Decimal recomputation of §16.2. `data_complete_through` = 2024-10.

**Periods (`agg_acq_lever_period`)**

| Measure | `first_payment`, pre_2023_06 | `first_payment`, from_2023_06 | `new_logo`, pre_2023_06 | `new_logo`, from_2023_06 |
|---|---|---|---|---|
| Months / Won | 16 / 606 | 17 / 978 | 16 / 563 | 17 / 978 |
| `won_per_month` | 37.875000 | 57.529412 | 35.187500 | 57.529412 |
| Run-rate customers / no paid / immature | 590 / 16 / 0 | 809 / 14 / 155 | 547 / 16 / 0 | 809 / 14 / 155 |
| `run_rate_last_cohort_month` | 2023-05 | 2024-07 | 2023-05 | 2024-07 |
| `run_rate_mrr_per_won_value` | **55,767.62** | **42,550.70** | 55,401.22 | 42,550.70 |
| `new_mrr_per_month_value` | **2,112,198.61** | **2,447,916.75** | 1,949,430.43 | 2,447,916.75 |
| `spend_total_value` / `spend_per_month_value` | 4,600,900,000 / 287,556,250.00 | 2,980,900,000 / 175,347,058.82 | same | same |
| `cost_per_won_value` | **7,592,244.22** | **3,047,955.01** | 8,172,113.68 | 3,047,955.01 |
| `payback_months` | **136.1** | **71.6** | 147.5 | 71.6 |
| m6: count / eligible / share | 563 / 606 / 0.9290 | 656 / 691 / 0.9493 | 523 / 563 / 0.9290 | 656 / 691 / 0.9493 |
| m12: count / eligible / share | 528 / 606 / 0.8713 | 332 / 369 / 0.8997 | 489 / 563 / 0.8686 | 332 / 369 / 0.8997 |
| `outlier_customers` | 0 | 0 | 0 | 0 |

Changes, user's Won, pre → from Jun 2023: Won per month +51.9%; spend per month −39.0%; run-rate −13,216.92 (−23.7%); new MRR per month +335,718.14 (+15.9%); cost per Won −59.9%; payback 136.1 → 71.6.

**Industries (`agg_acq_lever_industry`, user's Won)**

| Industry | Pre: Won / won share / run-rate customers / run-rate share / run-rate | From Jun 2023: Won / won share / run-rate customers / run-rate share / run-rate | Change | m12 pre / from (count/eligible) |
|---|---|---|---|---|
| Restaurants | 164 / 0.2706 / 156 / 0.2644 / 63,081.55 | 256 / 0.2618 / 214 / 0.2645 / 47,442.30 | −24.8% | 143/164 · 72/86 |
| Manufacturing | 138 / 0.2277 / 136 / 0.2305 / 53,180.27 | 225 / 0.2301 / 195 / 0.2410 / 42,684.42 | −19.7% | 124/138 · 86/97 |
| Retail | 131 / 0.2162 / 130 / 0.2203 / 43,671.05 | 239 / 0.2444 / 191 / 0.2361 / 29,406.94 | −32.7% | 112/131 · 85/94 |
| Technology | 81 / 0.1337 / 76 / 0.1288 / 68,409.85 | 98 / 0.1002 / 80 / 0.0989 / 53,879.73 | −21.2% | 66/81 · 31/32 |
| Professional services | 53 / 0.0875 / 53 / 0.0898 / 49,363.76 | 89 / 0.0910 / 71 / 0.0878 / 35,283.63 | −28.5% | 48/53 · 36/38 |
| Healthcare | 39 / 0.0644 / 39 / 0.0661 / 59,922.86 | 71 / 0.0726 / 58 / 0.0717 / 60,606.24 | +1.1% | 35/39 · 22/22 |

m6 (count/eligible), pre · from: Restaurants 148/164 · 170/182; Manufacturing 129/138 · 160/170; Retail 127/131 · 161/166; Technology 72/81 · 59/63; Professional services 49/53 · 57/60; Healthcare 38/39 · 49/50. No cell is `is_low_n`.

**Value change (user's Won):** total **−13,216.92**; mix **−558.82**; within-industry **−12,658.10** (95.8%); reverse order: mix −428.14, within −12,788.78. Each industry at its pre-period run-rate and today's run-rate shares gives 55,208.80, which is the +29.7% ticket reference. `new_logo`: total −12,850.52, mix −618.47, within −12,232.04.

**Half-year cohorts (`v_acq_cohort_half`, user's Won)**

| Cohort | Won | Run-rate customers (no paid / immature) | Run-rate | m6 count / eligible / % | m12 count / eligible / % |
|---|---|---|---|---|---|
| 2022-H1 | 228 | 223 (5 / 0) | 62,673.51 | 214 / 228 / 93.9 | 200 / 228 / 87.7 |
| 2022-H2 | 152 | 144 (8 / 0) | 61,597.90 | 138 / 152 / 90.8 | 128 / 152 / 84.2 |
| 2023-H1 | 272 | 269 (3 / 0) | 45,109.09 | 256 / 272 / 94.1 | 238 / 272 / 87.5 |
| 2023-H2 | 378 | 374 (4 / 0) | 39,934.42 | 360 / 378 / 95.2 | 294 / 323 / 91.0 (partial) |
| 2024-H1 | 351 | 342 (9 / 0) | 44,945.08 | 251 / 267 / 94.0 (partial) | — (0 eligible) |
| 2024-H2 | 203 | 47 (1 / 155) | 43,384.87 (partial: Jul only) | — | — |

`new_logo` differs only in 2022-H1: Won 185, run-rate 63,209.80, m6 174/185 (94.1), m12 161/185 (87.0).

**Planner fixtures** (baseline `from_2023_06`, user's Won; for the UI and API tests):

| Move | Won′ | Run-rate′ | New MRR′ | Cost per Won′ | Payback′ |
|---|---|---|---|---|---|
| None | 57.529412 | 42,550.70 | 2,447,916.75 | 3,047,955.01 | 71.6 |
| Ticket +10% | 57.529412 | 46,805.77 | 2,692,708.43 | 3,047,955.01 | 65.1 |
| Mix: 10 points Retail → Technology | 57.529412 | 44,997.98 (Δmix 2,447.28) | 2,588,707.33 | 3,047,955.01 | 67.7 |
| Spend −20% | 57.529412 | 42,550.70 | 2,447,916.75 | 2,438,364.01 | 57.3 |
| Conversion f = 1.05 | 60.405883 | 42,550.70 | 2,570,312.61 | 2,902,814.30 | 68.2 |

### 16.6 Replacement headline for the signals section

**Headline (decision-oriented, no causal claim):**
> **Spend per month fell 39% from June 2023 while new customers per month rose 52%: these files show no measurable link from spend to new customers. New MRR per month rose only 16%, because each new customer starts 24% smaller (55,768 → 42,551 a month), in every industry except Healthcare, and new customers keep paying as long as before. Plan with ticket size and industry mix (observed); treat conversion rates as assumptions; test spend before relying on it.**

Sub-line, always shown: "Starting revenue per new customer was already lower in the Jan–May 2023 cohorts (45,097 against 61,598 in Jul–Dec 2022), before the spend change, so its timing does not tie it to spend. Correlation tests: §7.5."

**Rule for the "no measurable link" clause** (the v1.1 rule that awaited CDO approval): the UI shows it when, in `signal_summary` for the user's Won at company scope, both `diff` and `within_regime` have `signals` ≤ 2 × `expected_by_chance` (today 3 and 3 against 2.2). Otherwise it shows: "Some de-trended tests show a link between spend and new customers; review them with the data team before using it." The `level` family is never used for the headline, because it carries the June-2023 break. The figures in the headline are templated from `levers.periods` (pre_2023_06 → from_2023_06, rounded to whole percent and whole units), and the "except Healthcare" clause lists every industry whose run-rate did not fall by at least 5%.

**Changelog.** 2026-11-17 (CDO): §16 Decision levers appended. It defines the lever planner and supersedes contract v1.2's working definitions on the run-rate amount (`amount_normalized`), run-rate censoring (mature cohorts only), shift-share weights (run-rate customers) and cost rounding. It also adds `agg_acq_cohort_quality`, `agg_acq_lever_period`, `agg_acq_lever_industry` and `agg_acq_value_change`, and amends §8.11 and §11.
