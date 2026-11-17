# Owner definitions

> Definitions provided by the data owners (received 2026-11-15). They are **authoritative** and override any assumption in the data dictionaries and profiles in this folder.
> The `etl-discover` workflow (`.claude/workflows/etl-discover.js`) reads this file: rules it backs are marked `inferred: false`.

## Original text (Spanish, verbatim)

**Transactions.csv**
Histórico mensual de ingresos por cliente. Multiplica los valores por 10.000 para obtener el monto.
Ej.: 25 = 250.000

**S&M_spend.csv**
Gasto mensual de Sales & Marketing, expresado en cientos de millones.
Ej.: 1.04 = 104.000.000

**Industry.csv**
Industria de cada cliente.

## English translation and how to apply it

| File | Definition | Conversion to the full amount | Owner's example |
|---|---|---|---|
| `Transactions.csv` | Monthly revenue history per customer | `amount × 10,000` | 25 → 250,000 |
| `S&M_spend.csv` | Monthly Sales & Marketing spend, expressed in hundreds of millions | `value × 100,000,000` | 1.04 → 104,000,000 |
| `Industry.csv` | Industry of each customer | None | — |

**Number format.** In the owners' examples, `.` groups thousands in the results (`250.000` = 250,000; `104.000.000` = 104,000,000). The files use `.` as the **decimal point** (`6.3`, `$1.040`). Parse the files with `.` as the decimal separator, then apply the conversion.

**Not stated by the owners** (still open):
- The currency. `$` in `S&M_spend.csv` could be USD or a peso currency.
- Whether revenue is invoiced, collected or recognized, and whether it includes taxes.
- Whether S&M spend is actual or budgeted.
