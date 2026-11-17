# Data Profile: `Industry.csv`

> Profiled on 2026-11-15 with Python 3.13 / pandas 3.0.0 against `data/Industry.csv` (49,402 bytes, modified 2025-02-09).
> Companion dictionary: [industry_data_dictionary.md](industry_data_dictionary.md)

## 1. Summary

| Metric | Value |
|---|---|
| Physical records (excluding header) | 1,962 |
| Valid data rows | **1,961** |
| Empty records | 1 (trailing `,`) |
| Columns | 2 |
| Completeness (valid rows) | 100% (0 nulls, 0 empty strings) |
| Duplicate rows / duplicate keys | 0 / 0 |
| Distinct customers | 1,961 |
| Distinct industries | 6 |
| Most frequent industry | `Restaurantes` (26.98%) |
| Join coverage with `Transactions.csv` | 100% / 100% |

**Overall assessment:** the table is clean and ready to use once you drop the trailing empty record and read the file with `utf-8-sig`.

## 2. File-level checks

| Check | Result | Status |
|---|---|---|
| Encoding | UTF-8 with BOM | ⚠️ Needs `utf-8-sig` |
| Line endings | CRLF | ℹ️ Informational |
| Header present | Yes: `ID,Industria` | ✅ |
| Consistent field count | Yes, 2 fields per line | ✅ |
| Quoted fields / embedded commas | None | ✅ |
| Trailing empty record | 1 (`,` on the last line) | ⚠️ Drop it |
| Sort order | Ascending by the numeric part of `ID` | ✅ |

## 3. Column profiles

### 3.1 `ID`

| Metric | Value |
|---|---|
| Inferred type | string (pattern `Cliente <int>`) |
| Nulls | 0 |
| Distinct | 1,961 (100% unique) |
| Pattern conformance `^Cliente \d+$` | 100% |
| Numeric suffix range | 1 – 1,961 |
| Missing numbers in range | None (contiguous) |
| Length (chars) | min 9 (`Cliente 1`), max 12 (`Cliente 1961`) |
| Leading/trailing whitespace | 0 |

### 3.2 `Industria`

| Metric | Value |
|---|---|
| Inferred type | string, categorical |
| Nulls / empty | 0 / 0 |
| Distinct | 6 |
| Length (chars) | min 5 (`Salud`), max 23 (`Servicios profesionales`) |
| Values with non-ASCII characters | `Producción`, `Tecnología` |
| Leading/trailing whitespace | 0 |
| Case or spelling variants | None |

**Frequency distribution** (one bar block = 1% of customers)

```
Restaurantes             529  26.98%  ███████████████████████████
Producción               454  23.15%  ███████████████████████
Retail                   428  21.83%  ██████████████████████
Tecnología               241  12.29%  ████████████
Servicios profesionales  165   8.41%  ████████
Salud                    144   7.34%  ███████
                       -----
                       1,961
```

The top three industries (Restaurantes, Producción, Retail) hold **71.96%** of customers.

## 4. Data quality checks

| # | Rule | Records failing | Status |
|---|---|---|---|
| Q1 | `ID` is not null | 0 | ✅ |
| Q2 | `ID` is unique | 0 | ✅ |
| Q3 | `ID` matches `^Cliente \d+$` | 0 | ✅ |
| Q4 | `Industria` is not null | 0 | ✅ |
| Q5 | `Industria` is in the 6-value domain | 0 | ✅ |
| Q6 | No fully empty records | 1 | ⚠️ |
| Q7 | Every `ID` exists in `Transactions.csv` | 0 | ✅ |
| Q8 | Every `Transactions.ID` exists here | 0 | ✅ |

## 5. Cross-file profile (joined to `Transactions.csv`)

### 5.1 Industry mix by acquisition cohort

The cohort is the customer's first month with `amount > 0`. "Pre-2022" means the customer was already paying in Jan-2022, so their true start date is unknown.

| Cohort | Customers | Restaurantes | Producción | Retail | Tecnología | Serv. prof. | Salud |
|---|---|---|---|---|---|---|---|
| Pre-2022 | 377 | 28.9% | 24.1% | 15.4% | 16.4% | 6.1% | 9.0% |
| 2022 (Feb–Dec) | 380 | 27.1% | 25.0% | 17.9% | 14.2% | 8.7% | 7.1% |
| 2023 | 650 | 25.2% | 23.8% | **26.0%** | 9.8% | 9.4% | 5.7% |
| 2024 (Jan–Oct) | 554 | 27.6% | 20.4% | 24.0% | 11.0% | 8.7% | 8.3% |

Retail's share of new customers rose from about 15% in the pre-2022 base to about 25% in the 2023–2024 cohorts, while Tecnología's fell from about 16% to about 10%.

### 5.2 Revenue and retention by industry (Jan-2022 – Oct-2024)

| Industry | Customers | % customers | Total revenue | % revenue | % revenue excl. customer 94 | Avg revenue / customer | Mean amount / paid month | Median amount / paid month | Median paid months | Paying in Oct-2024 |
|---|---|---|---|---|---|---|---|---|---|---|
| Restaurantes | 529 | 26.98% | 75,819.16 | 34.24% | 30.94% | 143.33 | 8.32 | 5.65 | 15 | 86.8% |
| Producción | 454 | 23.15% | 50,033.07 | 22.59% | 23.73% | 110.20 | 6.37 | 5.04 | 15 | 85.7% |
| Tecnología | 241 | 12.29% | 34,911.64 | 15.77% | 16.56% | 144.86 | 7.89 | 6.30 | 17 | 85.5% |
| Retail | 428 | 21.83% | 27,394.30 | 12.37% | 12.99% | 64.01 | 4.23 | 3.15 | 13 | 84.1% |
| Salud | 144 | 7.34% | 18,721.42 | 8.45% | 8.88% | 130.01 | 7.59 | 6.72 | 15 | 86.1% |
| Servicios profesionales | 165 | 8.41% | 14,561.91 | 6.58% | 6.91% | 88.25 | 5.51 | 3.57 | 14 | 84.8% |
| **Total** | **1,961** | 100% | **221,441.50** | 100% | 100% | 112.92 | 6.72 | 5.25 | 15 | 85.6% |

Notes:
- Customer 94 (`Restaurantes`) alone generates 10,564.75, or 4.77% of all revenue. That one customer lifts Restaurantes from about 31% to 34% of revenue.
- Retail is 21.8% of customers but only 12.4% of revenue. It has the lowest ticket (median 3.15 per paid month) and the shortest median paid tenure (13 months). Combined with its growing share of new customers (§5.1), this pulls average revenue per paying customer down.
- Retention, measured as the share of customers still paying in Oct-2024, is very similar across industries (84–87%).

## 6. Findings and recommendations

1. **Drop the trailing empty record** before any row count. Otherwise you get 1,962 customers, one of them with a null industry.
2. **Normalize the join key** (`Cliente N` → `N`). Without it, a join to Transactions returns no matches.
3. **Treat industry as a slowly changing dimension (SCD Type 1)** until history is available. Avoid conclusions that depend on the industry at a past point in time.
4. **Report industry results with and without customer 94** to avoid an outlier-driven reading of Restaurantes.
5. **Store an ASCII industry code** next to the Spanish label so tools that can't handle accents don't break.
