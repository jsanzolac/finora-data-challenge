# Data Profile: `S&M_spend.csv`

> Profiled on 2026-11-15 with Python 3.13 / pandas 3.0.0 against `data/S&M_spend.csv` (2,063 bytes, modified 2025-02-09).
> Companion dictionary: [sm_spend_data_dictionary.md](sm_spend_data_dictionary.md)
> All amounts are in the file's native unit: **hundreds of millions** per the [owner definition](owner_definitions.md) (multiply by 100,000,000; 1.04 = 104,000,000). The currency is not stated.

## 1. Summary

| Metric | Value |
|---|---|
| Rows | 34 months (2022-01 → 2024-10) |
| Columns | 8 (`Month` + 7 spend categories) |
| Completeness | 100% (0 nulls, 0 empty strings) |
| Duplicate months | 0 |
| Missing months in range | 0 |
| Format conformance (`-?\$\d+\.\d{3}`) | 100% of 238 spend cells |
| Zero values | 17 (all in `Freelance`) |
| Negative values | 5 (all in `PayrollExpenses`) |
| Total S&M spend, full period | **77.818** (= 7,781,800,000) |
| Average monthly spend | 2.289 (≈ 228.9 million; median 2.226) |
| Peak month | 2022-10: 3.752 |
| Lowest month | 2023-08: 1.100 |

**Overall assessment:** the data is structurally clean and complete. Two points matter for interpretation: (1) values are scaled (hundreds of millions) and the currency is not stated, and (2) the figures look budget-allocated (round totals split by percentages) rather than raw actuals.

## 2. File-level checks

| Check | Result | Status |
|---|---|---|
| Encoding | UTF-8 with BOM | ⚠️ Needs `utf-8-sig` |
| Line endings | CRLF | ℹ️ Informational |
| Header | `Month,PaidMedia,Travel,PublicidadNoWeb,Freelance,SoftwareTools,Team,PayrollExpenses` | ✅ |
| Consistent field count | 8 per line | ✅ |
| Numeric columns stored as text | Yes (`$` prefix) | ⚠️ Must be parsed |
| Negative format | `-$0.016` (sign before symbol) | ℹ️ Parser must keep the sign |
| Sort order | Ascending by `Month` | ✅ |

## 3. Column profiles

### 3.1 `Month`

| Metric | Value |
|---|---|
| Type | string `YYYY-MM` → year-month period |
| Distinct | 34 (100% unique) |
| Min / max | 2022-01 / 2024-10 |
| Gaps | None |
| Months per year | 2022: 12 · 2023: 12 · 2024: 10 (partial) |

### 3.2 Spend columns: descriptive statistics

| Column | Mean | Median | Std | CV | Min (month) | Max (month) | Zeros | Neg. | Distinct | Period total | Share of total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `PaidMedia` | 1.016 | 1.038 | 0.305 | 0.30 | 0.400 (2023-08) | 1.505 (2022-09) | 0 | 0 | 32 | 34.530 | **44.37%** |
| `Team` | 0.387 | 0.416 | 0.067 | 0.17 | 0.240 (2022-01) | 0.453 (2024-10) | 0 | 0 | 26 | 13.170 | 16.92% |
| `PublicidadNoWeb` | 0.343 | 0.328 | 0.113 | 0.33 | 0.156 (2023-11) | 0.630 (2022-09) | 0 | 0 | 34 | 11.651 | 14.97% |
| `PayrollExpenses` | 0.208 | 0.180 | 0.206 | 0.99 | −0.053 (2023-12) | 0.863 (2023-05) | 0 | **5** | 32 | 7.084 | 9.10% |
| `Travel` | 0.147 | 0.134 | 0.051 | 0.35 | 0.066 (2023-08) | 0.263 (2022-10) | 0 | 0 | 26 | 4.986 | 6.41% |
| `SoftwareTools` | 0.098 | 0.090 | 0.039 | 0.40 | 0.033 (2023-08) | 0.195 (2023-01) | 0 | 0 | 28 | 3.326 | 4.27% |
| `Freelance` | 0.090 | 0.036 | 0.104 | 1.16 | 0.000 (2023-05) | 0.338 (2022-10) | **17** | 0 | 15 | 3.071 | 3.95% |
| **Total (derived)** | **2.289** | 2.226 | 0.700 | 0.31 | 1.100 (2023-08) | 3.752 (2022-10) | 0 | 0 | 27 | **77.818** | 100% |

Correlation of each category with the monthly total: Travel 0.97, PaidMedia 0.94, PublicidadNoWeb 0.88, PayrollExpenses 0.81, Freelance 0.77, SoftwareTools 0.73, **Team −0.19**. Team is the only category that does not scale with the budget.

### 3.3 Monthly series

| Month | PaidMedia | Travel | PublicidadNoWeb | Freelance | SoftwareTools | Team | PayrollExp. | **Total** |
|---|---|---|---|---|---|---|---|---|
| 2022-01 | 1.040 | 0.120 | 0.340 | 0.100 | 0.080 | 0.240 | 0.080 | **2.000** |
| 2022-02 | 1.081 | 0.161 | 0.391 | 0.115 | 0.092 | 0.276 | 0.184 | **2.300** |
| 2022-03 | 1.081 | 0.161 | 0.276 | 0.115 | 0.138 | 0.276 | 0.253 | **2.300** |
| 2022-04 | 1.222 | 0.141 | 0.400 | 0.141 | 0.118 | 0.282 | 0.047 | **2.351** |
| 2022-05 | 1.350 | 0.189 | 0.324 | 0.189 | 0.081 | 0.324 | 0.243 | **2.700** |
| 2022-06 | 1.058 | 0.141 | 0.376 | 0.141 | 0.141 | 0.282 | 0.212 | **2.351** |
| 2022-07 | 0.880 | 0.132 | 0.308 | 0.198 | 0.132 | 0.264 | 0.286 | **2.200** |
| 2022-08 | 1.300 | 0.195 | 0.553 | 0.228 | 0.098 | 0.390 | 0.487 | **3.251** |
| 2022-09 | 1.505 | 0.245 | 0.630 | 0.280 | 0.140 | 0.420 | 0.280 | **3.500** |
| 2022-10 | 1.463 | 0.263 | 0.450 | 0.338 | 0.188 | 0.450 | 0.600 | **3.752** |
| 2022-11 | 1.500 | 0.210 | 0.420 | 0.270 | 0.090 | 0.360 | 0.150 | **3.000** |
| 2022-12 | 1.300 | 0.195 | 0.520 | 0.228 | 0.098 | 0.390 | 0.520 | **3.251** |
| 2023-01 | 1.365 | 0.228 | 0.585 | 0.163 | 0.195 | 0.390 | 0.325 | **3.251** |
| 2023-02 | 1.050 | 0.150 | 0.425 | 0.200 | 0.100 | 0.300 | 0.275 | **2.500** |
| 2023-03 | 1.305 | 0.174 | 0.377 | 0.116 | 0.087 | 0.348 | 0.493 | **2.900** |
| 2023-04 | 1.387 | 0.177 | 0.354 | 0.177 | 0.148 | 0.354 | 0.354 | **2.951** |
| 2023-05 | 1.380 | 0.242 | 0.414 | 0.000 | 0.138 | 0.414 | 0.863 | **3.451** |
| 2023-06 | 0.828 | 0.126 | 0.252 | 0.072 | 0.072 | 0.412 | 0.038 | **1.800** |
| 2023-07 | 0.683 | 0.123 | 0.280 | 0.000 | 0.070 | 0.415 | 0.180 | **1.751** |
| 2023-08 | 0.400 | 0.066 | 0.176 | 0.000 | 0.033 | 0.416 | 0.009 | **1.100** |
| 2023-09 | 0.513 | 0.075 | 0.163 | 0.000 | 0.038 | 0.419 | 0.044 | **1.252** |
| 2023-10 | 0.554 | 0.081 | 0.216 | 0.000 | 0.054 | 0.423 | 0.023 | **1.351** |
| 2023-11 | 0.598 | 0.078 | 0.156 | 0.000 | 0.052 | 0.432 | −0.016 | **1.300** |
| 2023-12 | 0.675 | 0.090 | 0.255 | 0.000 | 0.090 | 0.443 | −0.053 | **1.500** |
| 2024-01 | 0.703 | 0.130 | 0.333 | 0.000 | 0.074 | 0.442 | 0.169 | **1.851** |
| 2024-02 | 1.020 | 0.120 | 0.300 | 0.000 | 0.120 | 0.443 | −0.003 | **2.000** |
| 2024-03 | 0.875 | 0.105 | 0.298 | 0.000 | 0.088 | 0.432 | −0.047 | **1.751** |
| 2024-04 | 1.035 | 0.135 | 0.293 | 0.000 | 0.068 | 0.442 | 0.278 | **2.251** |
| 2024-05 | 1.105 | 0.141 | 0.353 | 0.000 | 0.141 | 0.445 | 0.166 | **2.351** |
| 2024-06 | 0.980 | 0.120 | 0.360 | 0.000 | 0.060 | 0.447 | 0.033 | **2.000** |
| 2024-07 | 0.900 | 0.108 | 0.288 | 0.000 | 0.072 | 0.448 | −0.016 | **1.800** |
| 2024-08 | 0.874 | 0.114 | 0.266 | 0.000 | 0.057 | 0.449 | 0.140 | **1.900** |
| 2024-09 | 0.740 | 0.130 | 0.259 | 0.000 | 0.093 | 0.449 | 0.180 | **1.851** |
| 2024-10 | 0.780 | 0.120 | 0.260 | 0.000 | 0.080 | 0.453 | 0.307 | **2.000** |

### 3.4 Yearly view (monthly averages; 2024 = Jan–Oct)

| Year | PaidMedia | Travel | PublicidadNoWeb | Freelance | SoftwareTools | Team | PayrollExp. | **Avg monthly total** | Year total |
|---|---|---|---|---|---|---|---|---|---|
| 2022 | 1.232 | 0.179 | 0.416 | 0.195 | 0.116 | 0.330 | 0.278 | **2.746** | 32.956 (12 mo) |
| 2023 | 0.895 | 0.134 | 0.304 | 0.061 | 0.090 | 0.397 | 0.211 | **2.092** | 25.107 (12 mo) |
| 2024 | 0.901 | 0.122 | 0.301 | 0.000 | 0.085 | 0.445 | 0.121 | **1.975** | 19.755 (10 mo) |

Average monthly spend fell **−23.8%** from 2022 to 2023 and another **−5.6%** in 2024 YTD. Team is the only category that grew (+35% from 2022 to 2024).

## 4. Data quality checks

| # | Rule | Records failing | Status |
|---|---|---|---|
| Q1 | `Month` is not null, unique and `YYYY-MM` | 0 | ✅ |
| Q2 | No missing months between min and max | 0 | ✅ |
| Q3 | Spend cells match `-?\$\d+\.\d{3}` | 0 | ✅ |
| Q4 | Spend cells are not null | 0 | ✅ |
| Q5 | Spend ≥ 0 (all columns except `PayrollExpenses`) | 0 | ✅ |
| Q6 | `PayrollExpenses` ≥ 0 | 5 (2023-11, 2023-12, 2024-02, 2024-03, 2024-07) | ⚠️ Valid but needs an explanation |
| Q7 | `Freelance` > 0 | 17 (2023-05, 2023-07 → 2024-10) | ℹ️ Structural, not an error |
| Q8 | Month range matches `Transactions.csv` | 0 (both 2022-01 → 2024-10) | ✅ |
| Q9 | Currency and unit documented | Unit: yes (owner: hundreds of millions). Currency: not stated | ⚠️ Currency to confirm |

## 5. Patterns and anomalies

1. **Round-number totals with percentage splits.** Monthly totals fall on 0.05 steps (2.000, 2.300, 2.351≈2.35, 3.251≈3.25, …). Through May-2023, categories map to whole percentages of the total. For example, 2022-01 splits as PaidMedia 52%, PublicidadNoWeb 17%, Team 12%, Travel 6%, Freelance 5%, SoftwareTools 4% and PayrollExpenses 4%, and Team sits at about 12% in every month through May-2023. Treat the data as **planned or allocated spend** until the owner confirms otherwise.
2. **Structural break in Jun-2023:**
   - Total spend dropped from 3.451 (May-2023) to 1.800 (Jun-2023), −48% in one month, and reached its low in Aug-2023 (1.100).
   - `Team` stopped scaling with the budget and became an almost fixed, slowly rising amount (0.412 → 0.453). Its share rose from about 12% to 19–38%.
   - `Freelance` disappeared (last non-zero value 0.072 in Jun-2023).
3. **`PayrollExpenses` acts as the plug.** Its share of total ranges from −3.5% to +24.7%, with a CV of 0.99, and its only spike (0.863 in May-2023, 25% of the total) comes right before the break. That could be severance or a bonus payout, which should be confirmed.
4. **Recovery in 2024.** Spend returned to about 1.8–2.35 per month, still below 2022 levels. Paid media is back to 0.74–1.1.
5. **Stable mix of non-people spend.** Travel stays at about 6% of the total in every month, and SoftwareTools at 3–6%.

## 6. Recommendations

1. Convert to **full amounts** (× 100,000,000) before using this file next to `Transactions.csv`, which uses a different scale (× 10,000). Mixing native values would distort CAC by four orders of magnitude. The currency still needs confirming.
2. Confirm whether the data is **actual or budget**. If it is budget, label derived CAC as "planned CAC".
3. Model `PayrollExpenses` as a signed amount and document what the negative months mean.
4. When comparing periods, use **monthly averages or like-for-like months**, because 2024 has only 10 months.
5. Keep the Jun-2023 break in mind: any spend-to-acquisition model fitted across it should include a regime indicator.
