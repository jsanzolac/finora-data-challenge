# Data Dictionary: `Transactions.csv`

> Monthly revenue per customer, stored as a dense customer × month panel.
> Companion profile: [transactions_data_profile.md](transactions_data_profile.md)

## 1. Dataset overview

| Property | Value |
|---|---|
| File | `data/Transactions.csv` |
| Business entity | Customer revenue (billing / payment) per month |
| Grain | One row per **customer × calendar month** |
| Primary key | (`ID`, `month`) |
| Data rows | 66,674 = 1,961 customers × 34 months (fully dense, zero-filled) |
| Columns | 3 |
| Time coverage | 2022-01-31 → 2024-10-31 (34 month-ends, contiguous) |
| File size | 1,302,387 bytes |
| Encoding | UTF-8 **with BOM** (`EF BB BF`) |
| Delimiter / quoting | Comma / no quoted fields |
| Line endings | CRLF (`\r\n`); no newline after the last record |
| Sort order | `ID` ascending, then `month` ascending |
| File last modified | 2025-02-09 |
| Currency / unit | Scaled × 10,000 ([owner definition](owner_definitions.md)): `25` = 250,000. The currency is not stated |

Despite the file name, rows are **not individual transactions**. Each row is the monthly total for one customer, and months without revenue appear explicitly as `0`.

## 2. Columns

| # | Column | Business name | Physical type | Logical type | Nullable | Format / domain | Example | Description |
|---|---|---|---|---|---|---|---|---|
| 1 | `ID` | Customer ID | integer | Identifier, FK → `Industry` | No | 1 – 1,961, contiguous; each ID appears exactly 34 times | `94` | Customer identifier. It equals the numeric suffix of `Industry.ID` (`"Cliente 94"`). IDs are **assigned in order of first paying month** (monotonic, Spearman ρ = 0.996). |
| 2 | `month` | Revenue month | string | Date (month-end) → year-month period | No | `M/D/YYYY` with no zero padding; always the **last calendar day** of the month; 34 distinct values | `2/29/2024` | The calendar month the amount belongs to. The day part carries no information beyond "end of month". |
| 3 | `amount` | Monthly revenue | decimal (string in file) | Currency amount, ≥ 0 | No | 0 – 847.966434; up to 6 decimals; no negatives | `6.3` | Revenue recorded for the customer in the month, **scaled: multiply by 10,000** for the full amount (owner definition; `6.3` = 63,000). `0` means no revenue was recorded that month (see the semantics in §4). |

## 3. Keys and relationships

| Relationship | Cardinality | Join rule | Coverage |
|---|---|---|---|
| `Transactions.ID` → `Industry.ID` | N : 1 | `Transactions.ID = int(Industry.ID.removeprefix("Cliente "))` | 100%: all 1,961 IDs match, with no orphans |
| `Transactions.month` → `S&M_spend.Month` | N : 1 | `to_period("M")` on both sides (`1/31/2022` ↔ `2022-01`) | 100%: identical 34-month window |

## 4. Semantic definitions (metrics layer)

These are the recommended canonical definitions for metrics built on this table. Each definition carries a caveat. The profile backs every number below.

| Concept | Definition | Caveat |
|---|---|---|
| **Paying (active) customer in month *m*** | `amount > 0` in *m* | About ⅓ of zero months inside a paying history are later "caught up" (next payment ≈ (gap+1) × usual amount), so a zero does not always mean the customer was inactive |
| **Cohort / first paid month** | `min(month)` where `amount > 0` | **Left-censored:** the 377 customers paying in Jan-2022 (IDs 1–377) started earlier, on an unknown date. Label them `pre-2022` |
| **New customer in month *m*** | Cohort month = *m* | Do not count Jan-2022 as acquisitions |
| **Last paid month** | `max(month)` where `amount > 0` | **Right-censored:** 1,678 customers were still paying in Oct-2024 |
| **Churned customer** | Last paid month < 2024-10 and no later revenue | 83.8% of observed gaps last 1–2 months. Recommend a **3-month grace window**: call a customer churned after ≥ 3 consecutive zero months, or flag a customer as provisional churn when their last payment was less than 3 months before the window end |
| **Reactivation** | `amount > 0` after ≥ 1 zero month that followed a positive month | 340 customers (17.3%) have at least one gap. Separate catch-up payments from real win-backs |
| **Monthly revenue** | `SUM(amount)` per month | Includes catch-up amounts. It is cash or billing based, not smoothed MRR |
| **ARPPU** (average revenue per paying user) | Monthly revenue ÷ paying customers | One customer (ID 94) contributes about 4.8% of all revenue. Also report a median or an excluding-outlier version |
| **Customer lifetime revenue** | `SUM(amount)` per customer over the window | Truncated by the window on both ends |
| **Paid tenure** | Count of months with `amount > 0` | Not the same as the calendar span when gaps exist |

### 4.1 Suggested derived columns

| Derived column | Type | Definition |
|---|---|---|
| `customer_id` | INTEGER | `ID` |
| `month` | DATE / period | `to_datetime(month, "%m/%d/%Y").to_period("M")` |
| `amount_value` | DECIMAL | `amount × 10,000`, the full amount per the owner definition |
| `is_paying` | BOOLEAN | `amount > 0` |
| `cohort_month` | period | First month with `is_paying` per customer |
| `is_left_censored` | BOOLEAN | `cohort_month == 2022-01` |
| `months_since_cohort` | INTEGER | `month − cohort_month` (in months) |
| `is_new` | BOOLEAN | `month == cohort_month AND NOT is_left_censored` |
| `is_catch_up` | BOOLEAN | `is_paying` after a zero streak of length *k*, and `amount ≈ (k+1) × prior amount` (±5%) |
| `industry_code` | VARCHAR | From `Industry` (see the [industry dictionary](industry_data_dictionary.md)) |

## 5. Business rules and value semantics

1. **Dense panel.** Every customer has a row for every month in the window, including months before acquisition and after churn. Row counts therefore never measure activity; use `is_paying`.
2. **Non-negative.** There are no refunds, credit notes or negative adjustments. If refunds exist in the source, they were netted out or excluded.
3. **Price grid.** Every positive amount with two or fewer decimals (68.3% of positive rows) is an exact multiple of **0.21**: 4.20, 6.30, 3.15, 0.63, 5.25, 8.40, and so on. These look like list prices for plans. The remaining amounts have up to 6 decimals, which suggests prorations, discounts, FX conversion or usage-based charges. Their share grows over time, from 24% of paying rows in Jan-2022 to 46% in Oct-2024.
4. **Amounts are sticky.** In 91.7% of consecutive paid months the amount does not change. Changes are rare and balanced (4.2% up, 4.1% down).
5. **Unit and currency.** Per the owner, multiply `amount` by 10,000 to get the full amount. The median paid month (5.25) is therefore 52,500, and total revenue in the window (221,441.50) is 2,214,415,000. The currency is not stated. `S&M_spend.csv` uses a different scale (hundreds of millions), so convert both before combining them.

## 6. Known issues and handling rules

| Issue | Impact | Handling rule |
|---|---|---|
| File name says "Transactions", but rows are monthly aggregates | Misread as event-level data | Name it `fct_customer_monthly_revenue` in the semantic layer |
| Non-padded US date format `M/D/YYYY` | Locale-dependent parsers may swap day and month | Parse explicitly with `format="%m/%d/%Y"` |
| UTF-8 BOM | Header read as `﻿ID` | Read with `encoding="utf-8-sig"` |
| Integer `ID` vs `"Cliente N"` in Industry | Join fails without normalization | Normalize to an integer `customer_id` |
| Zero = "no revenue", not "unknown" | Averaging all rows understates ticket size (3.32 vs 6.72) | Compute ticket metrics on `amount > 0` only |
| Catch-up payments | Spiky revenue and false churn or reactivations | Use the grace window in §4 and the `is_catch_up` flag |
| Extreme outlier (ID 94, up to 847.97 per month) | Skews means and industry comparisons | Report medians and excluding-outlier views next to totals |
| Censoring at both ends | Biased tenure and lifetime value | Flag `is_left_censored`, and treat active customers in Oct-2024 as ongoing |

```python
import pandas as pd

tx = pd.read_csv("data/Transactions.csv", encoding="utf-8-sig")
tx["month"] = pd.to_datetime(tx["month"], format="%m/%d/%Y").dt.to_period("M")
tx = tx.rename(columns={"ID": "customer_id"})
tx["is_paying"] = tx["amount"] > 0
tx["cohort_month"] = tx["month"].where(tx["is_paying"]).groupby(tx["customer_id"]).transform("min")
tx["is_left_censored"] = tx["cohort_month"] == pd.Period("2022-01", "M")
```

## 7. Open questions for the data owner

1. Is `amount` invoiced, collected (cash) or recognized revenue? The catch-up pattern suggests collected cash.
2. ~~What is the unit?~~ Answered: × 10,000 (see [owner_definitions.md](owner_definitions.md)). Still open: which currency?
3. Is revenue net or gross of taxes and discounts? The 0.21 grid may include a tax or FX factor.
4. Are these all customers or a sample? Were churned-before-2022 customers excluded?
5. Do zero months always mean no service? Or could the customer be on a free or trial plan, or an annual plan billed in a different month?
6. What explains customer 94's scale (about 300 per month, roughly 50 times the median)? Is it a multi-account or enterprise customer?
