# Data Dictionary: `Industry.csv`

> Lookup table that assigns each customer to one industry vertical.
> Companion profile: [industry_data_profile.md](industry_data_profile.md)

## 1. Dataset overview

| Property | Value |
|---|---|
| File | `data/Industry.csv` |
| Business entity | Customer (client account) |
| Grain | One row per customer |
| Primary key | `ID` |
| Data rows | 1,961 (plus 1 header row and 1 empty trailing record `,`) |
| Columns | 2 |
| Time coverage | None. This is a static attribute table with no effective dates |
| File size | 49,402 bytes |
| Encoding | UTF-8 **with BOM** (`EF BB BF`) |
| Delimiter / quoting | Comma / no quoted fields |
| Line endings | CRLF (`\r\n`) |
| Language | Spanish (column name and category values) |
| File last modified | 2025-02-09 |
| Owner definition | "Industria de cada cliente" (the industry of each customer). See [owner_definitions.md](owner_definitions.md) |
| Source system | Not documented (see open questions) |

## 2. Columns

| # | Column | Business name | Physical type | Logical type | Nullable | Format / domain | Example | Description |
|---|---|---|---|---|---|---|---|---|
| 1 | `ID` | Customer ID | string | Identifier (natural key) | No | Regex `^Cliente \d+$`; `Cliente 1` to `Cliente 1961`, contiguous, no gaps | `Cliente 13` | Unique customer identifier. The numeric suffix equals `Transactions.ID`. |
| 2 | `Industria` | Industry | string | Categorical (nominal), 6 values | No | See domain below | `Retail` | The industry vertical of the customer's business. |

### 2.1 Domain of `Industria`

| Value (as stored) | English label | Suggested code | Customers | Share | Meaning (assumed) |
|---|---|---|---|---|---|
| `Restaurantes` | Restaurants | `RESTAURANTS` | 529 | 26.98% | Food service businesses: restaurants, cafés, bars |
| `Producción` | Manufacturing / Production | `MANUFACTURING` | 454 | 23.15% | Businesses that produce or manufacture goods |
| `Retail` | Retail | `RETAIL` | 428 | 21.83% | Stores selling goods to final consumers |
| `Tecnología` | Technology | `TECHNOLOGY` | 241 | 12.29% | Software, IT and technology companies |
| `Servicios profesionales` | Professional services | `PROFESSIONAL_SERVICES` | 165 | 8.41% | Consulting, legal, accounting, agencies and similar |
| `Salud` | Healthcare | `HEALTHCARE` | 144 | 7.34% | Clinics, medical practices, pharmacies and similar |

The values are case-sensitive and carry accents (`Producción`, `Tecnología`). Compare them exactly, or normalize them to the suggested codes before use.

## 3. Keys and relationships

```
Industry (1) ──── (34) Transactions        S&M_spend: no customer key
  ID = "Cliente N"     ID = N                (joins to Transactions only
                                              at month level)
```

| Relationship | Cardinality | Join rule | Coverage |
|---|---|---|---|
| `Industry.ID` → `Transactions.ID` | 1 : 34 (one row per month) | `int(Industry.ID.removeprefix("Cliente "))` = `Transactions.ID` | 100% in both directions: all 1,961 IDs match, with no orphans |
| `Industry` → `S&M_spend` | None | No customer dimension in S&M spend | Not applicable |

The two files store the key differently: `Industry.ID` is a string (`"Cliente 94"`) and `Transactions.ID` is an integer (`94`). Normalize the key before joining.

## 4. Business rules and semantics

1. **One industry per customer.** There are no duplicates and no multi-industry assignments.
2. **The classification is static.** There are no effective dates, so a reclassification cannot be tracked. Treat the value as the customer's current (latest) industry and apply it to the full history.
3. **ID order follows acquisition order** (derived from Transactions). IDs are assigned in order of the customer's first paying month: IDs 1–377 were already paying in Jan-2022, and later IDs were acquired after that. This lets `ID` serve as a rough acquisition-sequence proxy, but use the computed cohort month for analysis.
4. **Industry mix shifts over time.** Later cohorts have more `Retail` customers and fewer `Tecnología` customers (see profile §5).

## 5. Known issues and handling rules

| Issue | Impact | Handling rule |
|---|---|---|
| Empty trailing record (`,` on line 1963) | Parsers read it as a row with two null values | Drop rows where `ID` is empty |
| UTF-8 BOM | The header is read as `﻿ID` unless the BOM is stripped | Read with `encoding="utf-8-sig"` |
| Non-ASCII category values | Accents can be mangled by Latin-1/ASCII tools (`ProducciÃ³n`) | Always read as UTF-8; prefer the ASCII codes downstream |
| Key format differs from Transactions | A naive join returns zero matches | Extract the integer suffix as `customer_id` |
| Spanish column name | Inconsistent naming against English columns elsewhere | Rename to `industry` in the semantic layer |

## 6. Recommended semantic-layer mapping

| Source column | Target name | Target type | Transformation |
|---|---|---|---|
| `ID` | `customer_id` | `INTEGER` (PK) | `CAST(REPLACE(ID, 'Cliente ', '') AS INTEGER)` |
| `ID` | `customer_label` | `VARCHAR(12)` | Keep as is |
| `Industria` | `industry_es` | `VARCHAR(23)` | Keep as is |
| `Industria` | `industry_code` | `VARCHAR(21)` | Map using the table in §2.1 |

```python
import pandas as pd

industry = (
    pd.read_csv("data/Industry.csv", encoding="utf-8-sig", dtype=str)
      .dropna(how="all")
      .assign(customer_id=lambda d: d["ID"].str.removeprefix("Cliente ").astype(int))
      .rename(columns={"Industria": "industry_es"})
)
```

## 7. Open questions for the data owner

1. Who assigns the industry: the customer at signup, sales, or an enrichment process? Can it change?
2. Is there a taxonomy behind the six values (for example a CIIU/ISIC mapping), or are they free buckets?
3. Why are there no "Other" or "Unknown" values? Were unclassified customers removed from the extract?
4. Are these 1,961 customers the full customer base or a sample?
