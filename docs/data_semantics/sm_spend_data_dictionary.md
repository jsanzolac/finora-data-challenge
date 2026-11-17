# Data Dictionary: `S&M_spend.csv`

> Monthly Sales & Marketing (S&M) spend, broken down by expense category.
> Companion profile: [sm_spend_data_profile.md](sm_spend_data_profile.md)

## 1. Dataset overview

| Property | Value |
|---|---|
| File | `data/S&M_spend.csv` (the `&` in the name must be quoted or escaped in shells and URLs) |
| Business entity | Sales & Marketing expense |
| Grain | One row per calendar month (company-wide, with no customer, channel or country split) |
| Primary key | `Month` |
| Data rows | 34 |
| Columns | 8 (1 period column + 7 spend categories) |
| Time coverage | 2022-01 → 2024-10, contiguous with no missing months. 2024 is partial (10 months) |
| File size | 2,063 bytes |
| Encoding | UTF-8 **with BOM** (`EF BB BF`) |
| Delimiter / quoting | Comma / no quoted fields |
| Line endings | CRLF (`\r\n`) |
| Language | Mixed English/Spanish column names (`PublicidadNoWeb`) |
| File last modified | 2025-02-09 |
| Currency / unit | **Hundreds of millions** ([owner definition](owner_definitions.md)): multiply by 100,000,000, so `$1.040` = 104,000,000. The currency is not stated. See §4.1 |

## 2. Columns

All seven spend columns use the same physical format: a currency string `$d.ddd`, negatives written `-$d.ddd` (sign before the symbol), and exactly 3 decimals. They should be loaded as `DECIMAL(9,3)`.

| # | Column | Business name | Logical type | Nullable | Observed range | Example | Description |
|---|---|---|---|---|---|---|---|
| 1 | `Month` | Spend month | Period (year-month) | No | `2022-01` – `2024-10` | `2023-05` | Calendar month in which the spend was booked. Format `YYYY-MM`. |
| 2 | `PaidMedia` | Paid (digital) media | Currency amount, ≥ 0 | No | 0.400 – 1.505 | `$1.040` | Paid online advertising, such as search, social and display ads. The largest category (44.4% of total spend). |
| 3 | `Travel` | Travel | Currency amount, ≥ 0 | No | 0.066 – 0.263 | `$0.120` | Travel expenses of the S&M team (trips, events, client visits). |
| 4 | `PublicidadNoWeb` | Non-web (offline) advertising | Currency amount, ≥ 0 | No | 0.156 – 0.630 | `$0.340` | Advertising outside digital channels, such as print, radio, TV, outdoor and sponsorships. Spanish: *publicidad no web*. |
| 5 | `Freelance` | Freelance / contractors | Currency amount, ≥ 0 | No | 0.000 – 0.338 | `$0.100` | Fees paid to external freelancers and contractors. **Zero from Jul-2023 onward** (also zero in May-2023). |
| 6 | `SoftwareTools` | S&M software and tools | Currency amount, ≥ 0 | No | 0.033 – 0.195 | `$0.080` | Subscriptions for marketing and sales tooling (CRM, automation, analytics). |
| 7 | `Team` | S&M team cost | Currency amount, ≥ 0 | No | 0.240 – 0.453 | `$0.240` | Cost of the in-house S&M team, mainly base compensation. It becomes a near-fixed amount from Jun-2023. |
| 8 | `PayrollExpenses` | Payroll-related expenses | Currency amount, **can be negative** | No | −0.053 – 0.863 | `-$0.016` | Payroll items beyond base team cost, such as commissions, bonuses, payroll taxes and benefits, plus accrual adjustments. Negative in 5 months, which points to reversals or true-ups. |

The meaning of each category was inferred from the column name and observed behavior; the source does not document it. See §6.

## 3. Derived fields (semantic layer)

| Derived field | Definition | Notes |
|---|---|---|
| `<column>_amount` | Each spend value × 100,000,000 | Full amount per the owner definition (§4.1). For example, `PaidMedia` 1.040 → 104,000,000 |
| `total_sm_spend` | `PaidMedia + Travel + PublicidadNoWeb + Freelance + SoftwareTools + Team + PayrollExpenses` | The file has no total column. Totals land on round budget figures in 0.05 steps (2.000, 2.300, 3.500, …) within ±0.002 rounding |
| `media_spend` | `PaidMedia + PublicidadNoWeb` | Working media, 59.3% of the period total |
| `people_spend` | `Team + PayrollExpenses + Freelance` | People cost, 30.0% of the period total |
| `other_spend` | `Travel + SoftwareTools` | Non-media opex, 10.7% of the period total |
| `month_start` / `month_end` | First or last calendar day of `Month` | Use `month_end` to join to `Transactions.month` |
| `cac` (example metric) | `(total_sm_spend × 100,000,000) / new_customers` in the same month | `new_customers` comes from Transactions (first month with `amount > 0`). Exclude Jan-2022, whose "new" count includes 377 customers who were already paying. Compare with revenue only after converting it too (`amount × 10,000`) |

## 4. Business rules and semantics

### 4.1 Units and number format

- **Unit ([owner definition](owner_definitions.md)):** values are in **hundreds of millions**. Multiply by 100,000,000 to get the full amount: `$1.040` = 1.04 × 100,000,000 = 104,000,000. A typical month (total ≈ 2.0) is about 200,000,000.
- `.` is a **decimal point**, not a thousands separator. The owner's example confirms it: 1.04 = 104.000.000, where the result uses `.` to group thousands.
- `$` marks currency, but the owners did not say which one. It could be USD or a peso currency (COP, MXN), both of which use `$`.
- `Transactions.csv` uses a different scale (× 10,000). Convert both files to full amounts before computing CAC or S&M as a share of revenue.

### 4.2 Observed allocation pattern

- The monthly total is a round number (2.0, 2.3, 2.7, 3.5, …). Each category behaves like a **percentage of that total**: for example, Jan-2022 is 52 / 6 / 17 / 5 / 4 / 12 / 4 %, and Team was about 12% every month until May-2023. This points to budget-allocated or modelled figures rather than raw ledger extracts.
- From Jun-2023, `Team` turns into a nearly fixed amount (0.412 → 0.453) and `Freelance` drops to zero. This is consistent with freelancers being replaced by in-house staff.
- `PayrollExpenses` behaves like a **balancing item**. Its share swings from −3.5% to +24.7% of the total, and it is the only column that goes negative. Do not treat a negative value as a data error. It is valid, but it should be explained by the owner.

### 4.3 Relationships

| Relationship | Cardinality | Join rule | Coverage |
|---|---|---|---|
| `S&M_spend.Month` → `Transactions.month` | 1 : 1,961 (one S&M row per customer-month) | Join on year-month: `to_period("M")` on both sides | Same 34-month window exactly |
| `S&M_spend` → `Industry` | None | No industry split in spend | Not applicable |

Spend cannot be attributed to customers or industries. It only supports **company-level, month-level** metrics such as CAC, the S&M-to-revenue ratio and the spend mix.

## 5. Known issues and handling rules

| Issue | Impact | Handling rule |
|---|---|---|
| Values stored as currency strings | They load as text, so arithmetic fails | Strip `$` and keep the sign: `"-$0.016"` → `-0.016` |
| Values are scaled (hundreds of millions) and the currency is not stated | Scale errors in CAC or ratios when mixed with Transactions (scaled × 10,000) | Convert to full amounts (× 100,000,000) in silver, and label the currency as unconfirmed |
| UTF-8 BOM | Header read as `﻿Month` | Read with `encoding="utf-8-sig"` |
| `&` in the file name | Shell and URL breakage | Quote the path, or rename to `sm_spend.csv` in pipelines |
| Negative `PayrollExpenses` | Breaks "spend ≥ 0" assertions | Allow negatives in this column only |
| Partial 2024 (Jan–Oct) | Year totals are not comparable | Compare monthly averages or matching month ranges |

```python
import pandas as pd

sm = pd.read_csv("data/S&M_spend.csv", encoding="utf-8-sig", dtype=str)
spend_cols = [c for c in sm.columns if c != "Month"]
sm[spend_cols] = sm[spend_cols].apply(lambda s: s.str.replace("$", "", regex=False).astype(float))
sm["Month"] = pd.PeriodIndex(sm["Month"], freq="M")
sm["total_sm_spend"] = sm[spend_cols].sum(axis=1)
sm["total_sm_spend_amount"] = sm["total_sm_spend"] * 100_000_000  # owner definition: hundreds of millions
```

## 6. Open questions for the data owner

1. ~~What is the unit?~~ Answered: hundreds of millions (see [owner_definitions.md](owner_definitions.md)). Still open: which currency?
2. Are these actuals from the ledger, or budget/allocated figures? The round totals and percentage splits suggest the latter.
3. What exactly goes into `PaidMedia` and `PublicidadNoWeb`? Which channels are included?
4. What is the boundary between `Team` and `PayrollExpenses`? What caused the negative months (2023-11, 2023-12, 2024-02, 2024-03, 2024-07)?
5. Was the Freelance-to-Team shift in mid-2023 a deliberate change in operating model?
6. Does this spend cover acquiring the same customers that appear in `Transactions.csv` (same market or country)?
