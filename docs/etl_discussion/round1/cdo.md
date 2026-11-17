# Round 1: CDO position

The baseline's structure is sound. Its lifecycle rules are not canonical yet: catch-up, churn and reactivation contradict each other and miss prepayments, so the baseline reports 313 "reactivations" where the canonical count is 64.
Bronze must prove it is byte-faithful (a round-trip test). Its flags go into a manifest, never into a second column.
In silver, a failed lookup must never quarantine revenue, every number is DECIMAL, and snapshot-fitted quality rules are marked inferred.
Gold keeps the dense customer × month grain, with one lifecycle state per row plus `rule_version` and `as_of_month`. CAC stays provisional.

*Evidence: I re-ran every figure with `python3 -I` over `data/` (2026-11-15). Read-only S3 checks show the staging ETags equal the MD5s of `data/`, so the local copies are identical.*

## M1 Inventory

**Agree:** there are 3 objects, each its own dataset: Transactions (1,302,387 B), Industry (49,402 B) and S&M (2,063 B). All are `text/csv; charset=utf-8` with SSE AES256. Bronze, silver and gold are empty.

**Change / add:**
- Register the dataset ids `transactions`, `industry` and `sm_spend`, each with a frozen column contract (CDO-02).
- **Versioning has never been enabled on any of the 4 buckets.** A re-upload overwrites staging, so bronze must be the audit trail (CDO-03).
- Keep three dates apart: the data cutoff (2024-10), the file mtime (2025-02-09) and the landing time (2026-11-16 00:31 UTC). `as_of_month` comes from the data.

## M2 Profile

**Agree:** 0 nulls, 0 duplicate keys, a dense 1,961 × 34 panel, a BOM in every file, Industry's trailing `,` record, 377 left-censored customers, customer 94 at 4.77% of revenue, and all 22,515 positive amounts with ≤ 2 decimals on the 0.21 grid.

**Change / add** (gaps in the profile; the doc corrections are proposals only, since `docs/data_semantics/` is frozen):

| Item | Verified finding |
|---|---|
| Whitespace and case | 0 padded cells out of 204,218 (the profile only checked Industry). Header case differs between files (`month` / `Month`) |
| Unicode | Accents are NFC (ó ×454, í ×241). An NFD `Producción` would become an invisible 7th value, so normalize before the domain check |
| Precision | Up to 6 decimals. After × 10,000, **every row has ≤ 2 decimals** (cents), which corroborates the owner factor. **Doc error:** the full revenue total is 2,214,415,045.08, not 2,214,415,000; the doc rounded before scaling |
| Dates | 100% non-padded `M/D/YYYY` and month-end. Spark and Athena need `M/d/yyyy`, because `MM/dd/yyyy` fails |
| Format | Header order is exact. `$` is ASCII U+0024 in all 238 cells, with the sign before the symbol in 5. The `&` in the key must be `%26` in URLs. **None** of the three files ends with a newline (the docs say this only for Transactions) |
| Catch-up | The profile missed **prepayment** ((k+1)× paid *before* the gap): 47 gaps. With 9 split payments, **211 of 468 gaps (45.1%) are settled**, not ⅓. Ties: 0 today, but the ±5% bands overlap for k ≥ 10 (12 gaps) |
| Left-censoring | **34 of the 108 "new" customers in Feb-2022** have a first payment ≈ 2× their next one, against 0–2 in later cohorts. 12 Jan-2022 payers caught up a gap from before the window |
| S&M ÷ revenue | The baseline's "2.3–5.8×" is annual. Monthly it runs from 1.61× to 7.62× |
| PII | 0 emails, 0 runs of 7+ digits, no names. **No direct identifiers, but not anonymous:** `Cliente N` is a pseudonym Finora can reverse, and an SMB may be a sole proprietor. Treat it as pseudonymised personal data plus confidential financial data. Team and PayrollExpenses are HR-sensitive |

## M3 Bronze security checks

**Agree:** the check set and the not-applicable list. Masking in bronze would change values, so it is correctly excluded.

**Change / add:**

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CDO-01 | bronze | all | Strict UTF-8 (a leading BOM is allowed); no NUL or C0 bytes except CR, LF and TAB; every line has the header's field count | 0 control bytes; field counts constant (3, 2, 8) | reject | false |
| CDO-02 | bronze | all | Schema and PII gate: the header must equal the registered columns (name, order, case). The "no PII" verdict only covers these 13 columns | All headers match | quarantine (file, pending CDO classification) | false |
| CDO-03 | bronze | all | Load manifest: verbatim source key, size, sha256, ETag, staging LastModified, row count, BRZ-04/05 hits. Bronze is write-once per load; a checksum mismatch fails the load | Versioning is off; ETag = MD5 verified | reject | false |
| BRZ-04 (replace) | bronze | all | Same prefixes, **except** cells that fully match `^-?\$?\d+(\.\d+)?$`. Hits go to the manifest; neutralize at export only | 5 hits today, all `-$0.0xx`, so 0 after the exemption | flag | false |
| BRZ-06 (replace) | bronze | all | Staging records plus `_ingested_at` (one ISO-8601 UTC `Z` value per load) as the last column. The BOM-bearing header, the values, the row order and the empty record are kept. **Test:** dropping `_ingested_at` reproduces staging exactly | Layer contract | reject | false |

**Renaming `S&M_spend.csv` → `sm_spend.csv`** does not break the contract, which governs columns and values. The verbatim key must be recorded in CDO-03. A `_source_file` column would be a second new column, and so a violation.

**Verdicts:**

| Rule | Verdict | Reason |
|---|---|---|
| BRZ-01 | keep | Testable. Content-Type is correct on all 3 objects today |
| BRZ-02 | keep | Deterministic. The 100 MB ceiling is a policy parameter |
| BRZ-03 | keep | Test it with EICAR. Quarantining the whole file is right |
| BRZ-04 | flag | Without the numeric exemption it flags every legitimate negative. It must not become a column |
| BRZ-05 | keep | It flags without blocking. The key goes into the manifest |
| BRZ-06 | flag | "Original string" is ambiguous about the BOM and the empty record. It needs the round-trip test |

## M4 Silver quality rules

**Agree:** stripping the BOM, typing and deriving keys belong in silver.

**Change / add:**

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CDO-04 | silver | all | Exact DECIMAL reconciliation per load: rows(bronze) = silver + quarantine, and the same for Σ native amount. The identity also holds from silver to gold | 66,674 rows, Σ 221,441.504508; S&M Σ 77.818; Industry 1,962 = 1,961 + 1 | reject | false |
| CDO-05 | silver | transactions, sm_spend | DECIMAL only: `amount` (12,6) → value (18,2); spend (12,3) → value (18,0). Any precision loss fails | ≤ 2 decimals after scaling on all rows | reject | false |
| CDO-06 | silver | all | Each delivery is a full snapshot: rebuild from the latest bronze load, and diff against the previous load (restated or removed cells) | The owners have not said full or incremental | flag | true |

**Replacement texts:**
- **SQ-02:** route empty records to quarantine (`EMPTY_RECORD`). Exactly 1 is expected, at the end of the file.
- **SQ-03:** use `^Cliente [1-9]\d*$`. A duplicate *derived* `customer_id` rejects the file.
- **SQ-04:** normalize to NFC, then map. An unmapped value gets `UNMAPPED`, is flagged and raises an alert. inferred = true.
- **SQ-05:** any duplicate key rejects the file.
- **SQ-07:** (a) a value that is not numeric is quarantined (false); (b) a negative is kept and flagged (true).
- **SQ-08:** a missing cell is flagged and never imputed as 0 (true).
- **SQ-09:** (a) format and uniqueness, otherwise reject the file (false); (b) gaps are flagged (true).
- **SQ-10:** use `^-?\$\d{1,6}\.\d{3}$`, otherwise reject the file.
- **SQ-12:** a Transactions customer with no Industry row gets `UNKNOWN` and is flagged. An Industry customer with no revenue is kept. A lookup never quarantines revenue.
- **SQ-13:** inferred = true. CAC for a month that does not match is null.

**Verdicts:**

| Rule | Verdict | Reason |
|---|---|---|
| SQ-01 | keep | Structural, testable, in the right layer |
| SQ-02 | flag | It drops records but is labelled "flag". By the M7 semantics a drop is quarantine |
| SQ-03 | flag | `\d+` lets `Cliente 094` collide with 94 |
| SQ-04 | flag | The 6-value domain is observed, not stated by the owners. Quarantining orphans revenue. NFC is missing |
| SQ-05 | flag | "Reject duplicates" is ambiguous, and a duplicate key double-counts revenue |
| SQ-06 | keep | 0 failures. Only the `M/d/yyyy` portability note applies |
| SQ-07 | flag | It mixes a structural check with a snapshot expectation (no refunds is not stated by the owners) |
| SQ-08 | flag | Density is a snapshot fact, so inferred = true |
| SQ-09 | flag | It mixes a structural part with an inferred part |
| SQ-10 | flag | `$d.ddd` fails at ≥ 10. A quarantined row deletes a whole month |
| SQ-11 | drop | A business expectation; merged into SB-10 |
| SQ-12 | flag | Quarantining orphans silently removes revenue |
| SQ-13 | flag | A cross-file expectation, so inferred = true |

## M5 Silver business rules

**Agree:** SB-01 and SB-02 are the only rules the owners back. Cent precision after scaling corroborates SB-01.

**Change / add:**

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CDO-07 | silver | transactions | Exactly one `lifecycle_state` per customer-month: `pre_acquisition`, `new`, `paying`, `reactivated`, `settled_gap`, `paused` (an unsettled gap of 1–2 months), `grace` (fewer than 3 trailing zero months at the cutoff), `churned` | 29,321 pre-acquisition rows; 193 pauses; 64 reactivations (60 customers); 237 customers with ≥ 3 trailing zero months, 46 in grace | reject (build) | true |
| CDO-08 | silver | cross | Unit tripwire: a monthly ratio of S&M full ÷ revenue full outside [0.5, 20] is flagged. Currency = NULL, `currency_status = unconfirmed` | 1.61–7.62× today. Mixing native values gives about 0.00035× | flag | true |

**Replacement texts:**
- **SB-04:** `cohort_censoring` = `left` (cohort 2022-01), or `probable_left` (cohort ≤ 2022-03 and a first payment ≈ j × the next, j = 2…n+1, ±5%), or otherwise `none`. Only `none` counts as new and enters CAC.
- **SB-05:** churn is an unsettled zero spell of at least 3 months (internal or trailing), **dated to its first zero month**. 1–2 trailing months = `grace`. A later settlement restates the churn.
- **SB-06:** a gap of k months between p and q is settled by arrears (x_q ≈ (k+1)·x_p), by prepayment (x_p ≈ (k+1)·x_{p−1} and x_q ≈ x_{p−1}) or by a split (x_p + x_q ≈ (k+2)·x_{p−1}). The tolerance is ±5%; on a tie, take the nearest multiple.
- **SB-07:** reactivation is the first paid month after churn. A 1–2 month gap is `paused`.
- **SB-08:** `is_outlier_customer` = a share of window revenue of at least 1.0% (a parameter; 94 and 322 today). Never remove an outlier; publish averages with and without outliers.
- **SB-10:** any negative spend is kept with `is_negative_adjustment`. A negative outside PayrollExpenses also raises an alert. This absorbs SQ-11.

**Canonical metrics** (owner status: only units and scaling are backed by the owners; everything else is inferred):

| Metric | Definition |
|---|---|
| Full amounts | Revenue × 10,000; spend × 100,000,000. The currency is unconfirmed. **Owner** |
| Paying | amount > 0 |
| New / cohort | First paid month with `cohort_censoring = none` (Feb-2022: 74, not 108) |
| Churned, reactivated, settled | SB-05, SB-07, SB-06 |
| ARPPU | revenue ÷ paying customers. It includes catch-ups, and is also published as a median and excluding outliers |
| CAC | S&M full ÷ new customers in the same month. Blended and **provisional** (blocked by Q1, Q3, Q4) |

**Verdicts:**

| Rule | Verdict | Reason |
|---|---|---|
| SB-01 | keep | Owner-backed and verified |
| SB-02 | keep | Owner-backed. Scaling gives whole numbers |
| SB-03 | keep | Deterministic and correctly inferred. Paying ≠ active (see CDO-07) |
| SB-04 | flag | ID order has 0 violations against the first paid month, so IDs probably come from this extract and cannot prove a customer is new. 34 Feb-2022 customers look left-censored |
| SB-05 | flag | It has no churn date and no state for internal spells or for the last 2 months (46 customers) |
| SB-06 | flag | It misses 47 prepaid and 9 split gaps, and has no tie-break |
| SB-07 | flag | It gives 313 against a canonical 64. It contradicts the grace window |
| SB-08 | flag | "E.g. customer 94" is not testable |
| SB-09 | keep | Correctly inferred; Q6 is pending |
| SB-10 | flag | Merge SQ-11 into it, and cover every category |

## M6 Gold dimensional model

**Agree:** the grain is customer × month, the dimensions are conformed, and aggregates come only from the facts.

**Change / add:**

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CDO-09 | gold | all | Every derived column carries `rule_version` and `as_of_month`. Published KPIs are snapshotted | Settlement and grace states change as new months arrive | reject (publish) | false |
| CDO-10 | gold | sm_spend | No S&M below company × month (no industry or cohort CAC) without an allocation key approved by the owners | S&M has no customer key | reject (build) | false |
| CDO-11 | gold | all | Customer-level facts are Confidential-Financial. Any share outside Finance, RevOps or Data suppresses cells with fewer than 5 customers | Pseudonymised SMB data. Customer 94 can be re-identified internally | flag (cell suppressed) | false |

**Replacement texts:**
- **GLD-02:** add the `UNKNOWN` and `UNMAPPED` members. The code and English label are inferred conventions.
- **GLD-03:** add `cohort_censoring`, `is_outlier_customer` and the unknown member −1.
- **GLD-04:** the grouping is marked as inferred.
- **GLD-05:** add DECIMAL native and full amounts, `lifecycle_state`, `is_catch_up`, `is_prepaid`, `rule_version` and `as_of_month`. All 66,674 rows are kept.
- **GLD-07:** CAC is null for 2022-01 and labelled "provisional", with a trailing-3-month variant. Churn for the last 2 months is provisional.

**Access:**
- staging and bronze: the pipeline and platform admins;
- silver: the Data team;
- customer-level gold: named Finance, RevOps and Data roles;
- payroll categories: Finance;
- all reads are logged.

**Verdicts:**

| Rule | Verdict | Reason |
|---|---|---|
| GLD-01 | keep | 34 contiguous months; conformed |
| GLD-02 | flag | Needs the unknown and unmapped members; its labels are inferred |
| GLD-03 | flag | Cohort attributes can be restated; needs censoring |
| GLD-04 | flag | The media / people / other grouping has no owner backing |
| GLD-05 | flag | The booleans lack grace, pause and settled states, so the counts cannot reconcile |
| GLD-06 | keep | Signed amounts at the right grain |
| GLD-07 | flag | CAC needs the provisional label and the censoring handling |

## M7 Verification

**onFailure semantics:**

| Action | What happens | Downstream |
|---|---|---|
| reject | The whole file or load goes to `_rejected/` with the rule id and an alert | Stops; the last good version stays current |
| quarantine | The row (or, for a security hit, the file) goes to `_quarantine/` with the rule id and is counted in CDO-04 | The rest continues |
| flag | The data passes unchanged; the hit is recorded in a reason column (silver and gold) or in the manifest (bronze) | Continues |

**Inferred:** it describes meaning. Controls (security, reconciliation, lineage, access) are inferred = false.

**Counts (36 baseline rules):** keep 12, flag 23, drop 1.

| Layer | keep | flag | drop |
|---|---|---|---|
| Bronze | 4 | 2 | 0 |
| Silver quality | 2 | 10 | 1 |
| Silver business | 4 | 6 | 0 |
| Gold | 2 | 5 | 0 |

New rules: CDO-01 to CDO-11.

**Most at risk:**
1. SB-06 and SB-07: reactivations are overstated about 5×.
2. SB-04: acquisitions are inflated.
3. SQ-12 and SQ-04: they can silently delete revenue.
4. BRZ-06: it cannot be proved without the round-trip test.
5. GLD-07: CAC is published before its scope is known.

## M8 Open questions for the data owners

| # | Ask | Owner | Blocks |
|---|---|---|---|
| Q1 | The currency of each file. Is it the same in both? | Finance | CDO-08, GLD-07 |
| Q2 | Is revenue invoiced, collected or recognized? Net or gross of tax? What is the 0.21 grid? | Billing | SB-06 |
| Q3 | Is S&M actual or budget? What are the 5 negative PayrollExpenses months and the Jun-2023 break? | Finance | SB-10, GLD-07 |
| Q4 | Does Transactions cover the whole base and the same market as S&M? | Billing + Finance | GLD-07 |
| Q5 | Can a zero month be a trial, a pause or an annual plan? Confirm the arrears and prepay patterns | Billing | SB-05 to SB-07 |
| Q6 | Who assigns industry? Can it change? Is there a taxonomy? Why is there no "Other"? | RevOps | SB-09, SQ-04 |
| Q7 | The true first-invoice date per customer. Were IDs assigned from this extract? Were customers who churned before 2022 excluded? | Billing | SB-04 |
| Q8 | Full snapshot or incremental? Can past months be restated? | All | CDO-06, CDO-09 |
| Q9 | Is customer 94 (and 322) one account or a group? | Billing | SB-08 |
| Q10 | Where are the boundaries between Team, PayrollExpenses and Freelance? Could payroll expose an individual's pay? | Finance + HR | GLD-04, CDO-11 |
