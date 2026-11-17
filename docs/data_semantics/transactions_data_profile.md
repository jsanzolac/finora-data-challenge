# Data Profile: `Transactions.csv`

> Profiled on 2026-11-15 with Python 3.13 / pandas 3.0.0 against `data/Transactions.csv` (1,302,387 bytes, modified 2025-02-09).
> Companion dictionary: [transactions_data_dictionary.md](transactions_data_dictionary.md)
> Amounts are in the file's native unit. Multiply by 10,000 for full amounts ([owner definition](owner_definitions.md)). The currency is not stated.

## 1. Summary

| Metric | Value |
|---|---|
| Rows | **66,674** |
| Columns | 3 (`ID`, `month`, `amount`) |
| Customers | 1,961 (IDs 1–1,961, contiguous) |
| Months | 34 (2022-01 → 2024-10, contiguous) |
| Panel density | 100%: every customer has all 34 months |
| Completeness | 100% (0 nulls, 0 empty strings) |
| Duplicate keys (`ID`,`month`) / duplicate rows | 0 / 0 |
| Rows with `amount = 0` | 33,703 (50.55%) |
| Rows with `amount > 0` | 32,971 (49.45%) |
| Negative amounts | 0 |
| Total revenue | **221,441.50** (= 2,214,415,000) |
| Revenue, first → last month | 3,500.03 (Jan-22) → 9,700.74 (Oct-24), CMGR **+3.14%** |
| Paying customers, first → last month | 377 → 1,678, CMGR **+4.63%** |
| Paying customers in Oct-2024 | 1,678 of 1,961 (85.6%) |

**Overall assessment:** the data is structurally perfect, with a complete, unique and dense panel. The main risks are in interpretation: zero-filled rows, catch-up payments, censoring at both ends of the window, a heavy outlier customer, and a scaled amount (× 10,000) with an unstated currency.

## 2. File-level checks

| Check | Result | Status |
|---|---|---|
| Encoding | UTF-8 with BOM | ⚠️ Needs `utf-8-sig` |
| Line endings | CRLF; no newline at EOF | ℹ️ Informational |
| Header | `ID,month,amount` | ✅ |
| Consistent field count | 3 per line | ✅ |
| Sort order | `ID` ↑, then `month` ↑ | ✅ |
| Date format | `M/D/YYYY`, no zero padding (US) | ⚠️ Parse explicitly |
| Numeric format | Plain decimals, `.` separator, no thousands separator | ✅ |

## 3. Column profiles

### 3.1 `ID`

| Metric | Value |
|---|---|
| Type | integer |
| Distinct | 1,961 |
| Range | 1 – 1,961, no gaps |
| Rows per ID | Exactly 34 for every ID |
| Relationship to acquisition | IDs are ordered by first paid month with **zero violations** (Spearman ρ = 0.996). IDs 1–377 were already paying in Jan-2022, IDs 378–500 were acquired in Feb–Mar 2022, and IDs 1501–1961 from Mar-2024 onward |
| Join to `Industry` | 100% match after mapping `N` ↔ `"Cliente N"` |

### 3.2 `month`

| Metric | Value |
|---|---|
| Type | string `M/D/YYYY` → date |
| Distinct | 34 |
| Min / max | 2022-01-31 / 2024-10-31 |
| All values are month-end | Yes (100%, including `2/29/2024`) |
| Rows per month | Exactly 1,961 |
| Alignment with `S&M_spend.Month` | Identical 34-month range |

### 3.3 `amount`

| Statistic | All rows | Positive rows only |
|---|---|---|
| Count | 66,674 | 32,971 |
| Mean | 3.321 | **6.716** |
| Std | 9.927 | 13.284 |
| Min | 0.000 | 0.140 |
| P1 | 0.000 | 0.630 |
| P5 | 0.000 | 0.840 |
| P10 | 0.000 | 1.512 |
| P25 | 0.000 | 3.150 |
| Median | 0.000 | **5.250** |
| P75 | 5.145 | 8.045 |
| P90 | 8.731 | 11.072 |
| P95 | 11.072 | 14.700 |
| P99 | 21.000 | 32.583 |
| Max | 847.966 | 847.966 |
| Distinct values | 1,627 | 1,626 |

**Distribution of positive amounts**

```
(0, 1]      1,780   5.4%  █████
(1, 2]      2,939   8.9%  █████████
(2, 4]      7,113  21.6%  ██████████████████████
(4, 6]      7,007  21.3%  █████████████████████
(6, 8]      5,883  17.8%  ██████████████████
(8, 10]     3,423  10.4%  ██████████
(10, 15]    3,238   9.8%  ██████████
(15, 20]      844   2.6%  ███
(20, 50]      632   1.9%  ██
(50, 100]      41   0.1%
(100, 1000]    71   0.2%
```

The distribution is right-skewed. The IQR upper fence is 15.39, and 1,520 positive rows (4.6%) sit above it. 112 rows above 50 come from 41 customers and account for 8.97% of revenue.

**Precision and price points**

| Decimals in raw value | Rows |
|---|---|
| 0 (includes all 33,703 zeros) | 33,721 |
| 1 | 8,545 |
| 2 | 13,952 |
| 3 | 2,890 |
| 4 | 675 |
| 5 | 867 |
| 6 | 6,024 |

- **All 22,515 positive amounts with two or fewer decimals are exact multiples of 0.21.** That is 68.3% of positive rows. The most common values are 4.20 = 20×0.21 (2,417 rows), 6.30 = 30×0.21 (2,224), 3.15 = 15×0.21 (1,592), 0.63 = 3×0.21 (1,331), 5.25 = 25×0.21 (1,273), 8.40 = 40×0.21 (1,238), 2.10 = 10×0.21 (1,135) and 7.35 = 35×0.21 (1,100).
- The share of amounts off this grid rises steadily, from 24.4% of paying rows in Jan-2022 to 46.2% in Oct-2024. This points to more prorated, discounted or FX-converted billing over time.
- 980 customers only ever pay on-grid amounts, 331 only pay off-grid amounts, and 650 do both.

## 4. Monthly time series

| Month | Paying customers | New customers | Last paid this month | Revenue | MoM | ARPPU (mean) | Median paid amount |
|---|---|---|---|---|---|---|---|
| 2022-01 | 377 | 377¹ | 5 | 3,500.03 | — | 9.28 | 7.23 |
| 2022-02 | 457 | 108 | 2 | 4,381.85 | +25.2% | 9.59 | 7.35 |
| 2022-03 | 467 | 30 | 1 | 3,954.52 | −9.8% | 8.47 | 6.62 |
| 2022-04 | 499 | 19 | 6 | 4,879.49 | +23.4% | 9.78 | 6.30 |
| 2022-05 | 532 | 38 | 8 | 4,929.92 | +1.0% | 9.27 | 6.30 |
| 2022-06 | 520 | 33 | 2 | 3,954.52 | −19.8% | 7.60 | 6.30 |
| 2022-07 | 586 | 32 | 6 | 4,937.84 | +24.9% | 8.43 | 6.30 |
| 2022-08 | 609 | 26 | 2 | 5,509.10 | +11.6% | 9.05 | 6.30 |
| 2022-09 | 629 | 17 | 3 | 5,046.38 | −8.4% | 8.02 | 6.30 |
| 2022-10 | 654 | 32 | 4 | 4,926.84 | −2.4% | 7.53 | 6.30 |
| 2022-11 | 669 | 19 | 3 | 5,027.42 | +2.0% | 7.51 | 6.30 |
| 2022-12 | 697 | 26 | 14 | 6,241.20 | +24.1% | 8.95 | 6.30 |
| 2023-01 | 733 | 60 | 3 | 5,636.31 | −9.7% | 7.69 | 6.09 |
| 2023-02 | 763 | 30 | 4 | 5,551.89 | −1.5% | 7.28 | 5.97 |
| 2023-03 | 792 | 38 | 12 | 5,669.09 | +2.1% | 7.16 | 5.67 |
| 2023-04 | 822 | 51 | 9 | 6,008.28 | +6.0% | 7.31 | 5.67 |
| 2023-05 | 861 | 47 | 5 | 6,202.21 | +3.2% | 7.20 | 5.55 |
| 2023-06 | 899 | 46 | 4 | 6,201.36 | −0.0% | 6.90 | 5.54 |
| 2023-07 | 959 | 65 | 8 | 6,447.62 | +4.0% | 6.72 | 5.25 |
| 2023-08 | 1,021 | 66 | 8 | 6,812.01 | +5.7% | 6.67 | 5.25 |
| 2023-09 | 1,078 | 56 | 12 | 6,924.94 | +1.7% | 6.42 | 4.83 |
| 2023-10 | 1,133 | 64 | 11 | 7,185.50 | +3.8% | 6.34 | 4.83 |
| 2023-11 | 1,203 | 72 | 6 | 7,687.48 | +7.0% | 6.39 | 4.72 |
| 2023-12 | 1,241 | 55 | 12 | 7,791.80 | +1.4% | 6.28 | 4.62 |
| 2024-01 | 1,283 | 57 | 13 | 7,650.60 | −1.8% | 5.96 | 4.48 |
| 2024-02 | 1,292 | 32 | 11 | 7,563.31 | −1.1% | 5.85 | 4.43 |
| 2024-03 | 1,320 | 43 | 6 | 7,803.88 | +3.2% | 5.91 | 4.44 |
| 2024-04 | 1,397 | 69 | 13 | 8,412.07 | +7.8% | 6.02 | 4.62 |
| 2024-05 | 1,457 | 66 | 14 | 8,565.17 | +1.8% | 5.88 | 4.43 |
| 2024-06 | 1,530 | 84 | 16 | 9,009.50 | +5.2% | 5.89 | 4.41 |
| 2024-07 | 1,566 | 48 | 14 | 8,943.39 | −0.7% | 5.71 | 4.37 |
| 2024-08 | 1,602 | 56 | 13 | 9,118.88 | +2.0% | 5.69 | 4.34 |
| 2024-09 | 1,645 | 49 | 33 | 9,266.37 | +1.6% | 5.63 | 4.20 |
| 2024-10 | 1,678 | 50 | 1,678² | 9,700.74 | +4.7% | 5.78 | 4.20 |

¹ Left-censored: these customers were already paying when the window opens, so they are not acquisitions.
² Right-censored: these customers are still active at the end of the window, so they have not churned.

**Yearly revenue:** 2022 = 57,289.11 · 2023 = 78,118.48 (+36.4% YoY) · 2024 Jan–Oct = 86,033.91 (+37.3% against Jan–Oct 2023, which was 62,639.21).

Observations:
- Revenue in 2022 is **volatile** (±20–25% month over month) while the paying-customer count rises smoothly. This fits billing-timing effects such as catch-up payments (§5.3), not real swings in demand.
- Mar-2022 and Jun-2022 have the same revenue to the cent (3,954.52). This was checked and is a coincidence, not a duplicated column: the two months' vectors differ for 229 customers.
- **ARPPU falls steadily**, from 9.28 to 5.78 (8.59 to 5.59 without customer 94). The median paid amount falls from 7.23 to 4.20. The cause is the customer mix: newer cohorts pay less (§5.4).
- The 33 customers whose last payment was in Sep-2024 are probably **not churned yet**. Most gaps last 1–2 months (§5.3).

## 5. Customer-level profile

### 5.1 Acquisition cohorts

| Cohort | Customers | ID range | Paying in Oct-2024 | Oct-2024 mean amount | Oct-2024 median amount | Median first payment |
|---|---|---|---|---|---|---|
| Pre-2022 (left-censored) | 377 | 1–377 | 298 (79.0%) | 9.74 | 6.86 | n/a |
| 2022 (Feb–Dec) | 380 | 378–757 | 286 (75.3%) | 6.67 | 5.88 | 6.30 |
| 2023 | 650 | 758–1,407 | 570 (87.7%) | 4.63 | 3.62 | 3.68 |
| 2024 (Jan–Oct) | 554 | 1,408–1,961 | 524 (94.6%) | 4.30 | 3.69 | 4.20 |

New customers per month average 48.0 from Feb-2022 to Oct-2024 (1,584 over 33 months). The series rises from about 20–40 per month in mid-2022 to 50–85 per month from mid-2023, apart from the Feb-2022 spike of 108.

### 5.2 Tenure and lifetime revenue

**Paid months per customer** (mean 16.8, median 15, min 1, max 34)

```
1          76   3.9%  ████
2–3       133   6.8%  ███████
4–6       222  11.3%  ███████████
7–12      395  20.1%  ████████████████████
13–18     367  18.7%  ███████████████████
19–24     204  10.4%  ██████████
25–30     179   9.1%  █████████
31–33     200  10.2%  ██████████
34 (all)  185   9.4%  █████████
```

**Lifetime revenue per customer in the window** (mean 112.92, median 56.70, P90 264.60, P99 678.18, max 10,564.75)

```
≤ 10          225  11.5%  ███████████
10–25         327  16.7%  █████████████████
25–50         361  18.4%  ██████████████████
50–100        372  19.0%  ███████████████████
100–200       357  18.2%  ██████████████████
200–500       281  14.3%  ██████████████
500–1,000      31   1.6%  ██
> 1,000         7   0.4%
```

### 5.3 Gaps, reactivations and catch-up payments

| Metric | Value |
|---|---|
| Customers with one continuous paying spell | 1,621 (82.7%) |
| Customers with 2+ spells (at least one internal gap) | 340 (17.3%) |
| Spells per customer | 1: 1,621 · 2: 255 · 3: 60 · 4: 14 · 5: 7 · 6: 2 · 7: 1 · 8: 1 |
| Internal gaps (zeros between two positive months) | 468 |
| Gap length | 1 month: 330 (70.5%) · 2: 62 · 3: 24 · 4: 18 · 5–30: 34 |
| Gaps of ≤ 2 months | 392 (83.8%) |
| Payment after the gap ≈ (gap+1) × payment before (±5%) | **155 (33.1%) are catch-up payments** |
| Payment after the gap ≈ payment before (±5%) | 122 (26.1%) resume at the same price |
| Consecutive paid months with an unchanged amount | 91.7% (up 4.2%, down 4.1%) |
| Distinct positive amounts per customer | median 2, max 31 |

Example: customer 94 paid about 230–310 per month in 2022. It has zeros in Mar-2022, Jun-2022 and Jul-2022, followed by 547.11 in Apr-2022 (about 2× its usual amount) and 847.97 in Aug-2022 (about 3×). The zeros are late payments, not churn.

### 5.4 Churn snapshot (naive: last paid month before Oct-2024)

| Metric | Value |
|---|---|
| Customers whose last payment was before Oct-2024 | 283 (14.4%) |
| …of which the last payment was in Sep-2024 (likely still active) | 33 |
| Customers active in Oct-2024 | 1,678 (85.6%) |
| One-month customers (paid exactly once) | 76 |

### 5.5 Revenue concentration

| Slice | Share of total revenue |
|---|---|
| Customer 94 (Restaurantes) | **4.77%** (10,564.75) |
| Top 2 customers (94, 322) | 6.63% |
| Top 1% of customers (19) | 13.8% |
| Top 10% of customers (196) | 43.2% |

Top 10 customers by lifetime revenue: 94 (10,564.75), 322 (4,127.11), 75 (1,659.08), 108 (1,484.81), 168 (1,176.08), 28 (1,143.45), 39 (1,112.99), 413 (985.04), 34 (873.60), 18 (863.16).

### 5.6 By industry (joined with `Industry.csv`, positive rows only)

| Industry | Paid rows | Mean | Std | Min | P25 | Median | P75 | Max |
|---|---|---|---|---|---|---|---|---|
| Restaurantes | 9,112 | 8.32 | 22.94 | 0.14 | 3.78 | 5.65 | 8.40 | 847.97 |
| Producción | 7,855 | 6.37 | 6.60 | 0.29 | 3.15 | 5.04 | 7.88 | 115.05 |
| Retail | 6,472 | 4.23 | 4.58 | 0.36 | 1.89 | 3.15 | 5.67 | 183.53 |
| Tecnología | 4,423 | 7.89 | 8.06 | 0.39 | 4.20 | 6.30 | 9.45 | 214.20 |
| Servicios profesionales | 2,641 | 5.51 | 6.38 | 0.24 | 1.89 | 3.57 | 7.35 | 121.56 |
| Salud | 2,468 | 7.59 | 5.44 | 0.63 | 4.20 | 6.72 | 8.89 | 104.58 |

For revenue share, retention and cohort mix by industry, see the [industry profile](industry_data_profile.md#5-cross-file-profile-joined-to-transactionscsv).

## 6. Data quality checks

| # | Rule | Records failing | Status |
|---|---|---|---|
| Q1 | `ID`, `month`, `amount` not null | 0 | ✅ |
| Q2 | (`ID`, `month`) unique | 0 | ✅ |
| Q3 | Panel is complete (1,961 × 34) | 0 missing cells | ✅ |
| Q4 | `month` parses with `%m/%d/%Y` and is a month-end | 0 | ✅ |
| Q5 | `amount` is numeric and ≥ 0 | 0 | ✅ |
| Q6 | Every `ID` exists in `Industry.csv` | 0 | ✅ |
| Q7 | Every customer has at least one positive month | 0 (all 1,961 do) | ✅ |
| Q8 | Positive `amount` ≤ IQR upper fence (15.39) | 1,520 rows (4.6%); max 847.97 (customer 94) | ⚠️ Valid but long-tailed |
| Q9 | Revenue unit and currency documented | Unit: yes (owner: × 10,000). Currency: not stated | ⚠️ |

## 7. Findings and recommendations

1. **Treat the file as a monthly revenue fact, not a transaction log.** Compute activity from `amount > 0`, never from row counts.
2. **Compute ticket metrics on positive rows only.** The all-rows mean (3.32) is half the true average paid amount (6.72).
3. **Don't count Jan-2022 as acquisitions.** Flag the 377 pre-existing customers (IDs 1–377) as left-censored in cohort, LTV and CAC analysis.
4. **Use a grace window for churn.** About one in three gaps ends in a catch-up payment, and 84% of gaps last ≤ 2 months. Defining churn as 3+ consecutive zero months removes most false churn and false reactivations.
5. **Isolate customer 94** (and check customer 322) in averages and industry comparisons. Publish metrics with and without them.
6. **Read the falling ARPPU correctly.** It comes from newer, lower-priced cohorts, not from existing customers paying less: 91.7% of consecutive amounts are unchanged.
7. **Convert to full amounts first** (revenue × 10,000; S&M spend × 100,000,000). Then confirm the currency, and that the data covers the same scope as `S&M_spend.csv`, before computing CAC, payback or LTV/CAC.
