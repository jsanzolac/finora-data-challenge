# Approved data rules (phase 1: staging → silver)

Approved by the CDO on 2026-11-16 and amended on 2026-11-17 (SB-11; see § Changelog). This file is the single rule set the ETL implements in phase 1. It is self-contained: every rule is written in full, and it supersedes `docs/etl_discussion/round3/cdo_rules.md` wherever they differ.

## Summary

**Policy (user decision, 2026-11-16, authoritative):**
1. No file is ever rejected or quarantined. Every delivered file is loaded.
2. Quality rules act on rows. A row that fails is kept out of silver and stored with every rule it failed, so data quality (DQ) can be measured per dataset.
3. File checks are off: no malware scan, size, object-name, Content-Type or header/schema gate.
4. The three departments on the DQ dashboard are the datasets: `transactions` "Transactions", `industry` "Industry", `sm_spend` "S&M spend".
5. Scope: staging → bronze → silver, plus the DQ store behind the dashboard. Gold is out of scope.

**Counts.** All 61 rule IDs of `cdo_rules.md` are accounted for: 40 active, 21 deferred. SB-11, added on 2026-11-17, is new, so 41 IDs are active.

| Layer | Active IDs | keep | flag | Catalog entries | exclude | flag | finding | run control |
|---|---|---|---|---|---|---|---|---|
| Bronze | 4 | 4 | 0 | 4 | 0 | 0 | 0 | 4 |
| Silver quality | 19 | 15 | 4 | 22 | 10 | 3 | 5 | 4 |
| Silver business | 18 | 11 | 7 | 18 | 0 | 6 | 4 | 8 |
| **Active** | **41** | **30** | **11** | **44** | **10** | **9** | **9** | **16** |
| Deferred | 21 | | | | | | | |

Three IDs have two parts with different actions, so they have two catalog entries each: `SQ-07a`/`SQ-07b`, `SQ-09a`/`SQ-09b`, `CDO-06a`/`CDO-06b`. The catalog id is the API `rule_id`.

**What changed from `cdo_rules.md`:**
- Every "reject (file)" and "quarantine (file)" is gone. Each became a row-level **exclude**, a **finding** where no row exists, or a **run control** on our own pipeline.
- CDO-01 moved from bronze to silver and now acts on one line at a time. Its field-count clause is carried by SQ-01.
- BRZ-01–BRZ-05 and CDO-02 are deferred (file checks off). All gold rules are deferred.
- Holes are new: an excluded or missing customer-month is `unknown`, never a zero month (§ Holes).
- SQ-08, SQ-09(b), SQ-12, SQ-13 and CDO-06(a) are findings. SQ-04 and SQ-07(b) stay flags.
- CDO-04 is now the identity rows(bronze) = rows(silver) + rows(excluded).
- A new lifecycle state, `unknown`, and a new censoring value, `unknown`, exist only for holes. Today's files produce neither.

**Risks the policy accepts (CDO note, not rules):**
- A truncated or garbled file is loaded. Silver then holds only what passes, and the dashboard shows the failures and findings. Consumers of silver must read the DQ status of the run they use.
- The header is not validated and columns are assigned by position. A file with reordered columns shows up as mass row failures, not as a schema alert. The manifest records the header as received.
- With no schema or PII gate, unexpected content in a malformed line is stored as received in the DQ store. Access to it is limited (§ Access).

## Policy and semantics

### Actions

| Action | Kind | What happens to the item | Silver | DQ store | Run |
|---|---|---|---|---|---|
| **exclude** | row | The source row fails a quality rule | Kept out of every silver table | One record per row with its raw values and **every** rule it failed | Continues |
| **flag** | row | The source row is valid but notable | Stays in silver with the rule's flag column set | One record per row × rule | Continues |
| **finding** | finding | No row exists to act on: a missing customer-month, a month gap, a window mismatch, a removed key, or a fact about a customer or gap | Nothing is removed. Affected derived values are marked as stated in the rule | One record per item, with its key | Continues |
| **run control** | control | A pipeline-integrity assertion fails | Nothing new is published | The run report only | The run fails. The previous publish stays live. No file is rejected, and the same bytes are retried after the fix |

- **No rule rejects, quarantines, skips or holds back a file.**
- **A run control must be unreachable by file content.** It may fire only on a defect of our own code or infrastructure. If any input file can trigger one, that is a bug in this document: tell the CDO.
- A row with at least one exclude-failure is **excluded**; any other data row is **included**. Flags and business rules are evaluated on included rows only.
- **Inferred = true:** the rule asserts a meaning or expectation no owner has stated. It stays marked until the owner's statement is recorded verbatim in `owner_definitions.md`.
- **Status:** `keep` = final. `flag` = final and built as written, but the named owner answer (Q#) is expected to change its text, parameters or action.

### What a row is

| Dataset | Row | `rows_read` today | Key | Why |
|---|---|---|---|---|
| `transactions` | One source line after the header = one customer × month | 66,674 | (`ID`, `month`) | Source grain |
| `industry` | One source line after the header = one customer | 1,962 | `ID` | Source grain. The trailing `,` line is a row |
| `sm_spend` | **One source line after the header = one month** (not a month × category cell) | 34 | `Month` | See below |

**S&M decision: the row is the month line.** Silver stores S&M long (7 rows per included line), but the unit that is read, excluded, flagged, counted and reconciled is the line:
1. A month with 6 of its 7 categories would give a total that looks valid and is wrong. If any cell fails, the whole month is kept out, and the month is visibly absent instead of silently understated.
2. `source_line`, `rows_read` (34) and `failed_columns` in the dashboard contract are line-based. `failed_columns` names the cell.
3. The reconciliation stays exact: 34 lines = included + excluded, and silver long rows = 7 × included lines.

### Parsing, evaluation order and what is stored

- **Records.** A file is split on LF. A CR immediately before the LF belongs to the terminator. A final terminator starts no record. Record 1 is the header: it is consumed and never validated. `source_line` is the 1-based record number (the header is 1).
- **Columns by position** (the registry): `transactions`: `ID`, `month`, `amount`. `industry`: `ID`, `Industria`. `sm_spend`: `Month`, `PaidMedia`, `Travel`, `PublicidadNoWeb`, `Freelance`, `SoftwareTools`, `Team`, `PayrollExpenses`.
- **Order per data row:**

  | Stage | Rules | Behaviour |
  |---|---|---|
  | A. Structure | CDO-01 → SQ-02 → SQ-01 | Short-circuit: a row that fails one is excluded with that single rule and is evaluated by no later rule |
  | B. Cells and keys | SQ-03, SQ-05, SQ-06, SQ-07a, SQ-09a, SQ-10, CDO-05 | No short-circuit: every rule is evaluated on every row that passed stage A, and the row is stored with every rule it failed. CDO-05 needs a parsed number, so it is evaluated only on rows that pass SQ-07a (or SQ-10) |
  | C. Row flags | SQ-04, SQ-07b, CDO-06b | Included rows only |
  | D. Findings | SQ-08, SQ-09b, SQ-12, SQ-13, CDO-06a | After all rows are classified |
  | E. Business | SB-01/02 → SB-03 → SB-04 → SB-06 → SB-05 / SB-07 / CDO-07 → SB-11 → CRO-03 → CRO-05 → SB-08 → CRO-07 → SB-09 → SB-10 → CDO-08 → CFO-03 / CFO-05 | Included rows only, with the hole semantics below |
  | F. Controls | CDO-04, CTO-06, CDO-11, then publish (CTO-10) | Any failure fails the run |

- **DQ record of a row:** `source_line`, `key` (the raw key columns), `values` (every source column as the raw string, never re-formatted), and per failed rule: `rule_id`, `failed_columns`, `reason` as `CODE: text`.
- **Stage-A failures have no trusted columns.** Decode the line with U+FFFD for invalid bytes, split on `,`, and assign fields to the registered columns by position. Missing fields are `""`. Surplus fields are appended to the last column, joined by `,`. `failed_columns` = all source columns.
- **Finding record:** `source_line` null, `key` normalized (`ID` as the integer string, `month` as `YYYY-MM`), `values` `{}`.
- A stored value longer than 1,000 characters is cut and suffixed `…[truncated]`.
- A `reason` never contains a cell value of an HR-sensitive column (§ Access).

### Grammars

Every pattern is a **full match** on the raw field, with ASCII digits only and no trimming.

```
G-ID            ^[1-9][0-9]*$
G-INDUSTRY-ID   ^Cliente [1-9][0-9]*$
G-TX-MONTH      ^(1[0-2]|[1-9])/(3[01]|[12][0-9]|[1-9])/([0-9]{4})$   and a real calendar date, and the last day of its month
G-AMOUNT        ^-?[0-9]+(\.[0-9]+)?$
G-SM-MONTH      ^[0-9]{4}-(0[1-9]|1[0-2])$
G-SPEND         ^-?\$[0-9]{1,6}\.[0-9]{3}$
```

### Holes: excluded or missing customer-months

**Definitions (Transactions).**
- **U** = the distinct `customer_id` of every data row whose `ID` matches G-ID, included or excluded.
- **W** = every calendar month from the earliest to the latest month among included rows. `as_of_month` = the last month of W. `churn_confirmed_through` = `as_of_month` − 2 months.
- **Panel** = U × W. A cell with an included row is **known**: paid when `amount` > 0, unpaid otherwise. A cell with no included row is a **hole**. `hole_reason` = `excluded` when at least one excluded row carries that parsed key, else `missing`.
- **Stretch** = a maximal run of consecutive panel months of one customer that are not known-paid (known-unpaid months and holes). It is leading (before the first known-paid month), internal (between known-paid months p and q) or trailing (after the last). A stretch is **clean** with no hole and **broken** with at least one.
- Silver `transactions` holds included rows only, so no NULL amount is ever in it. The derived lifecycle panel (`customer_month`) has exactly one row per panel cell, holes included.

| # | Rule |
|---|---|
| H1 | A hole is never paid, never unpaid and never zero. No amount is imputed. Its panel row has `is_hole` = true, `hole_reason`, and NULL in `amount`, `amount_value`, `is_paying`, `amount_normalized`, `expansion_amount`, `contraction_amount` |
| H2 | Clean stretches are classified by SB-04–SB-07 exactly as written. A gap, a churn spell, a pause and a grace run are clean stretches by definition |
| H3 | Every month of a broken stretch, known-unpaid months and holes alike, has `lifecycle_state` = `unknown`. No settlement test, churn event, pause, grace or pre-acquisition state is derived from it |
| H4 | The known-paid month that ends a broken stretch is `paying`. It is never `reactivated` and never `new` |
| H5 | `cohort_month` is the first known-paid month. `cohort_censoring` = `unknown` when the leading stretch is broken, or the stretch right after the first known-paid month is broken; `left` (cohort at the first month of W) takes precedence. `first_payment_hole_affected` = true when the stretch right after the first known-paid month is broken; then `first_payment_ratio`, `first_payment_multiple`, `implied_start_month`, `first_payment_band` and `is_first_month_spike` are NULL. An `unknown` customer is not a new logo |
| H6 | In SB-06, if month p−1 is a hole, tests 2 and 3 do not match and the gap has `settlement_hole_affected` = true. Test 1 is unaffected |
| H7 | `is_hole_affected` (panel row) = true on every month of a broken stretch, on the known-paid month that ends one, and on every month from p to q of a gap with `settlement_hole_affected` |
| H8 | Customer: `has_excluded_months` = the customer has at least one hole (either reason), and `hole_months` = how many. Medians and the outlier test (SB-08) use known-paid amounts only |
| H9 | CRO-05: `expansion_amount` and `contraction_amount` are NULL when month t−1 is a hole. `amount_lag12` is NULL when month t−12 is a hole or before W |
| H10 | Month: `revenue_total` is the sum of included rows. `hole_count` > 0 sets `revenue_is_complete` = false for that month |
| H11 | `is_provisional` keeps its meaning (CDO-07) and is not used for holes |

**Other datasets.**
- **S&M:** a month with no included line is absent from silver and never zero-filled. Its total, its S&M ÷ revenue ratio and its tripwire are NULL (`in_sm_spend` = false in `month_control`).
- **Industry:** a customer with no included Industry row has `industry_code` = `UNKNOWN` (SQ-12). Its revenue is never dropped.

### Exclude or flag: the four judgment calls

| Rule | Decision | Why |
|---|---|---|
| SQ-02 empty record | **exclude**, counts toward compliance | It has no key and no value, so nothing could be kept in silver. It is a defect of the extract that the owner can fix |
| SQ-04 `UNMAPPED` industry | **flag**, does not count | The list of 6 values is inferred; no owner has given a taxonomy (Q6). An unlisted value may be a real new industry. Excluding the row would also erase the difference between "unlisted value" and "no row". A recorded taxonomy would let the CDO change this to exclude |
| SQ-12 `UNKNOWN` industry | **not exclude: a finding** charged to `industry`, does not count | No Transactions row is at fault and none is touched. What is missing is an Industry row, so there is no row to flag. The owners have not said when a new customer gets its row (Q6) |
| SQ-07(b) negative amount | **flag**, does not count | The owners do not state that there are no refunds or credit notes. A negative number is well-formed, and excluding it would overstate revenue |

## Bronze

Table names in this file follow the CTO design. Column names, values and reason codes are binding.

| ID | Dataset(s) | Title (≤ 40 chars) | Rule | Evidence | Action | Kind | Inferred | Counts toward compliance | Status | Change vs cdo_rules |
|---|---|---|---|---|---|---|---|---|---|---|
| BRZ-06 | all | Bronze adds only _ingested_at | The bronze object is the staging object with `,_ingested_at` appended to record 1 (whatever it contains) and `,<timestamp>` appended to every other record, before that record's terminator. The BOM, every byte of every record, the record order, the terminators and the missing final newline are preserved. Blank and malformed records get the suffix too. A 0-byte staging object gives a 0-byte bronze object. Nothing is decoded, validated, altered or dropped in bronze | Layer contract. All 3 files have a BOM, CRLF and no final newline | run control | control | false | no | keep | changed by user policy (it must now accept any bytes) |
| CTO-01 | all | Bronze round-trip self-test | Pipeline self-test, not a file check: removing the last field (the final `,` and what follows it) from every bronze record reproduces the staging bytes exactly, with the same length and SHA-256. It runs on every load, before anything is published. A mismatch is a defect of our writer: the run fails, the file is not rejected, and the same bytes are retried after the fix | 0 quotes or embedded commas, CRLF only, BOM, no final newline | run control | control | false | no | keep | changed by user policy (reject → self-test) |
| CTO-02 | all | Lineage manifest per file | One write-once manifest per (dataset, SHA-256 of the staging bytes), at `_manifests/<dataset>/<sha256>.json`, written with `If-None-Match: *`. Fields: the verbatim source key, VersionId (null while versioning is off), size, ETag, SHA-256, staging LastModified, record count and data-row count, the header as received and `header_matches_registry` (information only, never a gate), `_ingested_at`, the `run_id` of the first ingest, `_rules_version`, and Decimal control totals computed from the raw strings with a count of cells that did not parse. It holds no scan status, no checksum comparison and no check hits. The source key is data: it is never interpolated into a path, query or command. If the manifest cannot be written, the run fails | VersionId is `null` on all 3 objects; no checksum is stored on them (verified 2026-11-15) | run control | control | false | no | keep | changed by user policy (scan and checksum-gate fields removed) |
| CTO-03 | all | One timestamp per file, idempotent | `_ingested_at` has one value per bronze object: UTC, `YYYY-MM-DDTHH:MM:SSZ`, set at the first ingest of a given (dataset, SHA-256 of the staging bytes). Re-delivering bytes already ingested creates no new bronze object and no new timestamp. If those bytes are not the dataset's current snapshot, that snapshot becomes current again and the event is logged. VersionId is recorded and is never the idempotency key | A VersionId key would turn a corrected re-upload under the same key into a no-op | run control | control | false | no | keep | kept |

## Silver: quality rules

| ID | Dataset(s) | Title (≤ 40 chars) | Rule | Evidence | Action | Kind | Inferred | Counts toward compliance | Status | Change vs cdo_rules |
|---|---|---|---|---|---|---|---|---|---|---|
| CDO-01 | all | Line is valid UTF-8, no control chars | The bytes of each data record decode as strict UTF-8 (the BOM is stripped from record 1 only) and contain no C0 control character U+0000–U+001F. The line terminator is not part of the record. A failing row is excluded with `UNDECODABLE_LINE` or `CONTROL_CHAR` and is evaluated by no other rule | 0 undecodable lines, 0 control bytes and 0 TABs in the 3 files | exclude | row | false | yes | keep | changed by user policy (was a bronze file reject; its field-count clause moved to SQ-01) |
| SQ-01 | all | Line has the registered field count | Parse contract: UTF-8, BOM stripped, record 1 consumed as the header, fields split on every `,` with no quote handling and no trimming, columns assigned by position, numbers parsed from their strings as exact decimals and never as floats. CRLF or LF endings and a missing final newline are accepted. A data record that does not split into exactly 3 (`transactions`), 2 (`industry`) or 8 (`sm_spend`) fields is excluded with `FIELD_COUNT` and is evaluated by no other rule | Field counts are constant (3, 2, 8). 0 quotes and 0 embedded commas | exclude | row | false | yes | keep | changed by user policy |
| SQ-02 | all | Empty records | A data record whose fields are all zero-length (a blank line, `,`, `,,` and so on) is excluded with `EMPTY_RECORD` and is evaluated by no other rule. It is tested before SQ-01. Every empty record is a failure: none is "expected" | Industry line 1,963 is `,` (1,962 = 1,961 + 1). The other two files have none | exclude | row | false | yes | keep | changed by CDO (the "exactly one is expected" clause is dropped; the row count replaces the alert) |
| SQ-03 | industry | Customer ID valid and unique | (a) `ID` matches G-INDUSTRY-ID and yields the integer `customer_id`; otherwise the row is excluded with `BAD_CUSTOMER_ID`. (b) The derived `customer_id` is unique among rows that pass (a); otherwise every copy is excluded with `DUPLICATE_CUSTOMER_ID`, identical copies included. The pipeline never picks a winner | 1,961 unique IDs. A looser pattern would let `Cliente 094` collide with 94 | exclude | row | false | yes | keep | changed by user policy (duplicate: file reject → all copies excluded) |
| SQ-04 | industry | Industry outside the registered list | On included rows, `Industria` is normalized to Unicode NFC and mapped to one of the 6 registered values and its code: Restaurantes `RESTAURANTS`, Producción `MANUFACTURING`, Retail `RETAIL`, Tecnología `TECHNOLOGY`, Servicios profesionales `PROFESSIONAL_SERVICES`, Salud `HEALTHCARE`. Any other value, an empty one included, keeps its row in silver with `industry_code` = `UNMAPPED`, `is_industry_unmapped` = true and the raw value kept; reason `UNMAPPED_INDUSTRY`. The codes are an inferred convention | 6 values, 0 variants, all NFC (529, 454, 428, 241, 165, 144 customers). An NFD `Producción` would become an invisible 7th value | flag | row | true | no | flag (Q6) | changed by CDO (flag confirmed; status keep → flag because the Q6 taxonomy decides whether this becomes exclude) |
| SQ-05 | transactions | Customer-month key valid and unique | (a) `ID` matches G-ID and yields `customer_id`; otherwise the row is excluded with `BAD_ID`. (b) (`customer_id`, month) is unique among rows whose `ID` and `month` both parse, whatever their amount; otherwise every copy is excluded with `DUPLICATE_KEY` | 0 bad IDs and 0 duplicates. A duplicate double-counts revenue and has no true amount | exclude | row | false | yes | keep | changed by user policy |
| SQ-06 | transactions | Month is a month-end date | `month` matches G-TX-MONTH (non-padded month/day/year), is a real calendar date and is the last day of its month. It is converted to `YYYY-MM`. A padded date (`01/31/2022`), another format or a day that is not month-end is excluded with `BAD_MONTH`. Validate with the pattern before any date parser, because `%m/%d/%Y` and `M/d/yyyy` parsers accept padding | 66,674 of 66,674 are non-padded month-ends | exclude | row | false | yes | keep | changed by user policy; strict pattern set by CDO (A9) |
| SQ-07 | transactions | (a) Amount is a plain decimal number · (b) Negative amount | (a) `amount` matches G-AMOUNT; otherwise the row is excluded with `BAD_AMOUNT`. `1e3`, `NaN`, `Infinity`, `+5`, `.5`, `5.`, `1,5`, an empty value and any space all fail. No NULL or 0 is ever substituted. (b) On included rows, an amount below 0 keeps its row in silver with `is_negative_amount` = true; it stays in every sum and is not a paying month; reason `NEGATIVE_AMOUNT` | Minimum 0, 0 negatives and 0 unparseable values. The owners do not state that there are no refunds | (a) exclude; (b) flag | (a) row; (b) row | (a) false; (b) true | (a) yes; (b) no | keep | (a) changed by user policy; (b) kept |
| SQ-08 | transactions | Missing customer-months | The delivery is expected to be a dense panel. A finding `MISSING_CUSTOMER_MONTH` is recorded for each panel cell (U × W) that no source row carries. A cell whose rows were excluded is also a hole, but it is counted under the rule that excluded it, not here. Nothing is imputed, and both kinds of hole follow H1–H11 | 66,674 = 1,961 × 34. Zero months are explicit (33,703 rows, 50.55%), so a missing row is an extract defect, not a zero | finding | finding | true | yes | flag (Q8) | changed by user policy (file reject → finding) |
| SQ-09 | sm_spend | (a) Month valid and unique · (b) Missing months in the series | (a) `Month` matches G-SM-MONTH; otherwise the line is excluded with `BAD_MONTH`. A `Month` repeated among lines that pass the pattern excludes every copy with `DUPLICATE_MONTH`. (b) A finding `MONTH_GAP` is recorded for each calendar month between the earliest and the latest included month that no source line carries. The month stays absent and is never zero-filled | 34 unique, contiguous months (2022-01 → 2024-10) | (a) exclude; (b) finding | (a) row; (b) finding | (a) false; (b) true | (a) yes; (b) yes | keep | (a) changed by user policy; (b) changed by user policy (flag → finding) |
| SQ-10 | sm_spend | Spend cells match the $0.000 format | Each of the 7 spend cells matches G-SPEND. The `$` is stripped and the sign is kept. If any cell fails, the whole month line is excluded with `BAD_SPEND_CELL`, and `failed_columns` lists the failing cells | 238 of 238 cells conform, 5 of them negative | exclude | row | false | yes | keep | changed by user policy (cell failure → the line is excluded) |
| SQ-12 | industry | Customers with no Industry row | A finding `NO_INDUSTRY_ROW` is recorded, against `industry`, for each `customer_id` in included Transactions rows that has no included Industry row. In silver that customer has `industry_code` = `UNKNOWN` and `is_industry_unknown` = true. No Transactions row is excluded, flagged or changed. An Industry customer with no Transactions row is kept and is not a finding | 100% match in both directions today (1,961 and 1,961) | finding | finding | true | no | flag (Q6) | changed by CDO (flag on revenue rows → finding charged to Industry; marked inferred; status keep → flag) |
| SQ-13 | transactions, sm_spend | Month covered by only one dataset | The two money datasets are expected to cover the same months. A finding `MONTH_NOT_IN_DATASET` is recorded for each month that has at least one included row in one of them and none in the other, against the dataset that lacks it. In `month_control` that month's S&M ÷ revenue ratio and tripwire are NULL | Both cover 2022-01 → 2024-10 | finding | finding | true | no | keep | changed by user policy (flag → finding) |
| CDO-04 | all | Bronze rows = silver + excluded | Exact, per dataset, on every run. (1) Data rows in bronze = included rows + excluded rows; each data row is in exactly one of the two; each excluded row has at least one failed exclude rule; each flagged row is included. (2) Silver `transactions` rows = included rows; silver `industry` rows = included rows; silver `sm_spend` rows = 7 × included lines. (3) In exact Decimal: Σ `amount` in silver = Σ of the included rows' source strings, recomputed independently from bronze; the same for Σ spend; Σ `amount_value` = Σ `amount` × 10,000; Σ `spend_value` = Σ spend × 100,000,000. (4) Lifecycle panel rows = U × W cells = included Transactions rows + holes. Control totals come from bronze and the manifest, never from documentation. Any break fails the run | 66,674 = 66,674 + 0; 1,962 = 1,961 + 1; 34 = 34 + 0, and 238 = 7 × 34. Σ `amount` 221,441.504508 (full 2,214,415,045.08); Σ spend 77.818 (full 7,781,800,000) | run control | control | false | no | keep | changed by user policy (quarantine → excluded; gold leg deferred) |
| CDO-05 | transactions, sm_spend | Value fits its registered precision | Money is DECIMAL, never float: `amount` DECIMAL(12,6) → `amount_value` DECIMAL(18,2); spend DECIMAL(12,3) → `spend_value` DECIMAL(18,0). Nothing is rounded, truncated or widened. A Transactions row whose `amount`, after dropping trailing fractional zeros and leading integer zeros, needs more than 6 decimal places or more than 6 integer digits is excluded with `PRECISION`. For `sm_spend`, G-SPEND already limits a cell to 6 integer digits and 3 decimals, so the rule is evaluated there and cannot fail while that pattern stands | Every amount has ≤ 6 decimals, so ≤ 2 after × 10,000. Floats give a wrong full amount on 2,436 rows and on 32 of 238 cells | exclude | row | false | yes | keep | changed by user policy |
| CDO-06 | all | (a) Keys removed since the previous run · (b) Values restated since previous run | Each delivery is treated as a full snapshot, and silver is rebuilt from it. It is compared with the previous succeeded run of the same dataset. Keys: a Transactions (`customer_id`, month), an Industry `customer_id`, an S&M month. A key is delivered when any source row carries it, included or excluded. (a) A finding `REMOVED_KEY` is recorded for each key delivered in the previous run and not delivered now. (b) An included row whose key was included in the previous run with a different typed value (the amount; the NFC `Industria`; any spend cell) stays in silver with `is_restated` = true, reason `RESTATED_VALUE`, and its old and new values go to the restatement log. On a dataset's first run both parts have evaluated = 0 and status `na` | The files hold the full history. The owners have not said whether deliveries are full or incremental, or whether closed months can change | (a) finding; (b) flag | (a) finding; (b) row | true | (a) yes; (b) no | flag (Q8) | changed by user policy (file reject → finding) |
| CTO-06 | all | Lineage on every row | Every silver row and every DQ-store record carries `_run_id`, `_source_key`, `_source_sha256`, `_ingested_at`, `_rules_version` (a hash of the rules config, which includes the catalog in this file) and `as_of_month`. Row-grain tables and DQ row records also carry `_source_line`. A row built from two sources (silver `customer`) traces to both through the run manifest. A row without lineage fails the run. The gold part of this rule is deferred | Bronze forbids extra columns, so lineage starts in silver | run control | control | false | no | keep | kept (silver part only) |
| CTO-10 | all | Full rebuild, atomic publish | Every run rebuilds silver and the DQ store in full, under a new run id, from the current bronze snapshot of each dataset. No file-level acceptance exists: every delivered file is loaded. The run is published atomically, only after every run control passes, and its pointer (`dq/latest.json` for the DQ store) is written last. A failed run publishes nothing and the previous publish stays live. Published runs are immutable. The summaries of at least the 24 most recent succeeded runs are retained for the trend. The gold part and the month-close retention of this rule are deferred | Lifecycle states change retroactively (one new month restates 45 earlier rows), and a rebuild takes seconds | run control | control | false | no | keep | changed by user policy ("accepted snapshot" and per-dataset hold-back removed) |
| CDO-11 | all | Access and HR-sensitive masking | (1) Customer-level data (silver and the DQ store) is Confidential-Financial pseudonymised data, readable only by the `finance`, `revops` and `data` roles. (2) `Team`, `PayrollExpenses` and `Freelance` are HR-sensitive: only `finance` reads their values; every other role receives `__restricted__`. The full policy is § Access and is part of this rule. The run asserts that HR-sensitive values appear in no log line, run report or `reason` string, and that silver `sm_spend` rows of those categories sit only in the `hr_sensitive` partition. Parts (3)–(5) of the original rule (suppression in shared aggregates) are deferred with gold | `Cliente N` is a reversible pseudonym, and an SMB may be a sole trader. A payroll category can expose one person's pay (Q10) | run control | control | false | no | keep | kept (parts 1–2; gold parts deferred) |

## Silver: business rules

Business rules run on included rows only and follow H1–H11. They never exclude a row and never count toward compliance. A `flag` or `finding` here marks a row or item that needs attention or whose result is undetermined because of a hole.

| ID | Dataset(s) | Title (≤ 40 chars) | Rule | Evidence | Action | Kind | Inferred | Counts toward compliance | Status | Change vs cdo_rules |
|---|---|---|---|---|---|---|---|---|---|---|
| SB-01 | transactions | Revenue × 10,000 (owner definition) | `amount_value` = `amount` × 10,000 for every included row, in exact decimal arithmetic. The run asserts that `amount_value` ÷ 10,000 = `amount` exactly on every row | Owner definition (25 → 250,000). Every full amount has cent precision | run control | control | false | no | keep | kept |
| SB-02 | sm_spend | S&M × 100,000,000 (owner definition) | `spend_value` = spend × 100,000,000 for every included cell, in exact decimal arithmetic, with the sign kept. The run asserts that every `spend_value` is an integer and that `spend_value` ÷ 100,000,000 = spend exactly | Owner definition (1.04 → 104,000,000) | run control | control | false | no | keep | kept |
| SB-03 | transactions | Paying means amount above zero | `is_paying` = (`amount` > 0) on every included row. A zero or negative month is unpaid. A hole has `is_paying` NULL (H1). The run asserts the identity on every included row | 33,703 of 66,674 rows are zero. The minimum positive amount is 0.140007 | run control | control | true | no | keep | kept (hole clause added) |
| SB-04 | transactions | Cohort and left-censoring | `cohort_month` is the customer's first known-paid month. `first_payment_ratio` = first paid amount ÷ next paid amount, where the next is the second known-paid month at any distance (NULL with a single payment). `first_payment_multiple` j is the integer in {2, 3} with abs(first − j × next) ≤ 0.05 × j × next, else NULL. `implied_start_month` = `cohort_month` − (j − 1) months, NULL when j is NULL. `cohort_censoring` is, in this order: `left` when `cohort_month` is the first month of W; `unknown` under H5; `probable_left` when `implied_start_month` ≤ the first month of W; `none` otherwise. Only `none` is a new logo. A finding `COHORT_UNKNOWN` is recorded for each customer with `unknown` | 377 left, 43 probable_left (40 Feb-2022, 3 Mar-2022), 1,541 none; Feb-2022 has 68 new logos. 3× first payments in Feb-2022: 6 of 108 against 0.9 expected (Poisson p = 0.0003) | finding | finding | true | no | flag (Q7) | changed by user policy (`unknown` added for holes) |
| SB-05 | transactions | Churn after 3 unpaid months | A churn spell is an unsettled clean stretch of at least 3 unpaid months after the first known-paid month: internal (ended by a payment that does not settle it) or trailing (still open at `as_of_month`). Its months are `churned`, and `is_churn_event` marks its first unpaid month. A clean trailing stretch of 1–2 unpaid months is `grace`. A settlement found later restates the spell as a settled gap. Churn counts for months after `churn_confirmed_through` are NULL, never 0. The threshold 3 is a versioned parameter. An included row inside a broken stretch has state `unknown` (H3) and is flagged `STATE_UNKNOWN` | The return hazard is 43.9% after 1 zero month and 7.7% after 3. 237 customers have an open churn spell and 46 are in grace. Churn events for Jun–Oct 2024 are 15, 18, 14, 0, 0: the last two cannot be observed yet | flag | row | true | no | flag (Q5) | changed by user policy (`unknown` added for holes) |
| SB-06 | transactions | Settled gaps: arrears, prepay, split | A gap is a clean internal stretch of k ≥ 1 unpaid months between known-paid months p and q. x_m is the native amount of month m, and p−1 is the calendar month before p. "a ≈ b" means abs(a − b) ≤ 0.05 × b. The tests run in this order and the first match settles the gap: (1) arrears: x_q ≈ (k+1) × x_p; (2) prepay: x_{p−1} > 0, x_p ≈ (k+1) × x_{p−1} and x_q ≈ x_{p−1}; (3) split: x_{p−1} > 0 and x_p + x_q ≈ (k+2) × x_{p−1}. When p−1 is before W, tests 2 and 3 do not match. A settled gap gets `settlement_type` (`arrears`, `prepay`, `split`) and `settlement_confidence` (`high` for arrears and prepay, `low` for split) on its unpaid months and on its settling months: q for arrears, p for prepay, p and q for split. Its unpaid months have state `settled_gap`. `is_catch_up` marks q of an arrears gap and `is_prepaid` marks p of a prepaid gap. Amounts are never restated. The tolerance 0.05 is a versioned parameter. A finding `SETTLEMENT_HOLE` is recorded for each gap with `settlement_hole_affected` (H6) | 468 gaps: 155 arrears + 47 prepay + 9 split = 211 settled (45.1%). Arrears and prepay never both match. ±5% sits on a plateau | finding | finding | true | no | flag (Q5, Q2) | changed by user policy (hole clause added) |
| SB-07 | transactions | Reactivation versus pause | The first known-paid month that ends an internal churn spell is `reactivated`: never a new logo, and the customer keeps its cohort. An unsettled clean internal stretch of 1–2 unpaid months is `paused`, and the payment that ends it is `paying`, not a reactivation. A known-paid month that ends a broken internal stretch is `paying` (H4) and is flagged `REACTIVATION_UNKNOWN` | 64 reactivations (60 customers); 193 paused gaps (231 months) | flag | row | true | no | keep | changed by user policy (hole clause added) |
| SB-08 | transactions | Outlier customers | `is_outlier_customer` is true when the customer has at least 3 known-paid amounts and the median of them is ≥ 25 × the portfolio median, taken over all known-paid customer-months up to `as_of_month`. A median of an even count is the mean of the two middle values. 25 and 3 are versioned parameters. An owner may add or remove a customer through a recorded statement in versioned config (`outlier_source` = `owner`, otherwise `rule`). Outliers are never removed from silver. A change in the flagged set from the previous published run is written to the restatement log. A finding `OUTLIER_INCOMPLETE_HISTORY` is recorded for each customer with `has_excluded_months` (H8). Publishing averages all-in and ex-outlier is deferred with gold | Flags 94 (60.0×, 31 payments) and 322 (31.7×, 25 payments). The portfolio median is 5.25. The next customer is at 18.6× with 1 payment | finding | finding | true | no | keep | changed by user policy (hole clause added) |
| SB-09 | industry | Industry fixed per customer | A customer has one industry (SCD type 1), applied to its whole history: silver `customer` holds exactly one `industry_code` per `customer_id`. The run asserts it | The file has no effective dates | run control | control | true | no | flag (Q6) | kept |
| SB-10 | sm_spend | Negative spend | Spend keeps its sign as received. It is never made absolute, clipped, floored or reclassified. A negative cell has `is_negative_spend` = true, and its line is flagged with `NEGATIVE_SPEND` and the negative columns in `failed_columns` (`NEGATIVE_SPEND_OTHER_CATEGORY` when any of them is not `PayrollExpenses`, which also alerts Finance and Data). Its nature is unconfirmed: an adjustment and a budget plug are both possible. The monthly total in `month_control` is the exact sum of the 7 categories, negatives included | 5 negative `PayrollExpenses` months, −13,500,000 in total. Clipping to 0 would push two monthly totals off their 0.05 grid | flag | row | true | no | keep | kept |
| SB-11 | transactions | Uneven split of a two-month total | Two consecutive months m and m+1 of one customer are an uneven split when, with x the native `amount` and b = x_{m−1}: (1) months m−1, m, m+1 and m+2 are all known-paid (`amount` > 0), so the four-month window holds no hole and no unpaid month; (2) none of the four months has a `settlement_type`, whether from SB-06 or from an uneven split already tagged; (3) x_{m+2} = b; (4) x_m ≠ b; (5) x_m + x_{m+1} = 2 × b. Every test is an exact Decimal equality with no tolerance. This is not a versioned parameter: `amount_normalized` = b below is exact only because the sum is exact. Windows are tested from the earliest m upward, and a tagged month is never re-tagged. Both months get `settlement_type` = `uneven_split`, `settlement_confidence` = `high`, `amount_normalized` = b (which equals (x_m + x_{m+1}) ÷ 2 exactly) and the new column `uneven_split_start_month` = m as `YYYY-MM` (NULL on every other panel row). `is_catch_up` and `is_prepaid` stay false, and `lifecycle_state` stays `paying`. Both included rows are flagged with `failed_columns` [`amount`] and reason `UNEVEN_SPLIT: <m> and <m+1> sum to twice the amount of <m−1> and <m+2>`. Nothing else changes: `amount`, `amount_value`, `is_paying`, revenue totals, medians, first paid amounts, lifecycle states and the `gap` table. A pair is decided only once month m+2 is delivered, so a later delivery can tag it retroactively (CTO-10). Runs of 3 or more months and pairs whose two baselines differ are not covered (deferred, Q17) | 11 pairs in 10 customers (12, 34, 78, 93, 191, 336 twice, 370, 437, 576, 651), 22 rows; every window month is `paying` with no settlement. Customer 12: 7.154784 + 6.285216 = 2 × 6.72. The same 11 match at any tolerance up to ±1%; ±2% adds a two-month dip (customer 40). A one-sided baseline matches 20 (m−1) or 173 (m+2) pairs, mostly price changes (141 are a price step billed one month late). Removes 82.483002 from both Σ `expansion_amount` and Σ `contraction_amount`; the net is unchanged. Evidence: `docs/etl_discussion/round3/cdo_uneven_split.md` | flag | row | true | no | flag (Q17) | new (2026-11-17, user-requested after the customer 12 review) |
| CDO-07 | transactions | One lifecycle state per customer-month | Every panel cell (U × W) has exactly one `lifecycle_state`: `pre_acquisition` (a month of a clean leading stretch); `new` (the first known-paid month of a customer whose `cohort_censoring` is `none`); `paying` (any other known-paid month that is not `reactivated`); `reactivated`; `settled_gap`; `paused`; `churned`; `grace`; `unknown` (H3). `is_provisional` is true on every row from the customer's last known-paid month through `as_of_month`. A cell with no state or more than one fails the run | 66,674 cells: paying 31,366; pre_acquisition 29,321; churned 3,811; new 1,541; settled_gap 281; paused 231; reactivated 64; grace 59; unknown 0. 5,399 rows are provisional | run control | control | true | no | keep | changed by user policy (`unknown` state added) |
| CDO-08 | sm_spend | Unit tripwire: S&M ÷ revenue | For each month with included rows in both money datasets, compare Σ `spend_value` (S) with Σ `amount_value` (R). The tripwire fires when R ≤ 0, S < 0.5 × R or S > 20 × R. The S&M line of that month is flagged with `UNIT_TRIPWIRE`, `month_control.is_unit_tripwire` = true, and Data and Finance are alerted. The fault may be in either dataset. The bounds [0.5, 20] are versioned parameters. `sm_to_revenue_ratio` = S ÷ R is stored as evidence | The ratio is 1.61–7.62 today. An S&M file off by ×10 or ÷10 trips in 28 or 21 of 34 months. Mixing native values gives about 0.00035 | flag | row | true | no | flag (Q1) | kept (the combined-KPI NULL clause is deferred with gold) |
| CFO-03 | transactions, sm_spend | Currency and basis are unconfirmed | Silver `source_status` has exactly one row per money dataset, from versioned config: `currency_code` NULL, `currency_status` = `unconfirmed`, `revenue_basis_status` or `spend_basis_status` = `unconfirmed`, and `basis_hint` (`cash-like` for revenue, `budget-like` for spend). The values change only through a recorded owner answer. The run asserts the two rows exist with the configured values | The owners state neither the currency nor the basis. Settled gaps suggest cash-like revenue; round 0.05 totals suggest budget-like spend | run control | control | false (statuses); true (`basis_hint`) | no | keep | kept (the KPI-view clause is deferred with gold) |
| CFO-05 | transactions, sm_spend | Scope of S&M vs revenue unconfirmed | `scope_status` = `unconfirmed` on every `month_control` row, from versioned config, until a recorded owner answer says Transactions covers the customer base that the S&M spend acquires and serves. `sm_to_revenue_ratio` is evidence and never sets the status. The run asserts the column holds the configured value | S&M is 5.75× / 3.21× / 2.30× revenue (2022 / 2023 / Jan–Oct 2024) | run control | control | false | no | keep | kept |
| CRO-03 | transactions | Normalized amount for settled gaps | `amount_normalized` spreads the settling amount of each settled gap evenly over the months it covers: for arrears, x_q over p+1 … q; for prepay, x_p over p … q−1; for split, x_p + x_q over p … q. Each share is truncated (not rounded) to 6 decimals, and the remainder goes to the payment month: q for arrears and split, p for prepay. Each month of an uneven split (SB-11) equals its baseline b. Every other known month equals `amount`; a hole is NULL. `amount` never changes. The column is analytical only: it is never a revenue total and never drives `is_paying`, new logos or the first paid amount. The run asserts Σ `amount_normalized` = Σ `amount` per customer exactly | The identity holds for all 1,961 customers | run control | control | true | no | keep | kept (uneven-split sentence added 2026-11-17) |
| CRO-05 | transactions | Expansion and contraction proxy | Δ = `amount_normalized`(t) − `amount_normalized`(t−1), computed only when `lifecycle_state` is `paying` in both t and t−1. `expansion_amount` = max(Δ, 0) and `contraction_amount` = max(−Δ, 0); otherwise both are 0. `amount_lag12` = `amount_normalized`(t−12), NULL before W. They are a movement proxy: a change may come from price, tax, FX or a plan change. An included row whose values are NULL under H9 is flagged `MOVEMENT_UNKNOWN` | 91.7% of consecutive paid months are unchanged. The 0.21 price grid is unexplained | flag | row | true | no | flag (Q2) | changed by user policy (hole clause added) |
| CRO-07 | transactions | First-month spike | On silver `customer`: `is_first_month_spike` = first paid amount ≥ 1.9 × next paid amount, and `first_payment_band` is `<1.9`, `1.9–3` (from 1.9, below 3) or `≥3`; both are NULL when `first_payment_ratio` is NULL. They are descriptive and never remove a logo or change a cohort. Silver keeps `first_paid_amount` and `first_payment_multiple` so a cohort's starting ARPA can be computed later (deferred with gold). A finding `FIRST_PAYMENT_UNKNOWN` is recorded for each customer with `first_payment_hole_affected` (H5) | 116 new logos are at ≥ 1.9× and 64 at ≥ 3× | finding | finding | true | no | keep | changed by user policy (hole clause added) |

## Deferred rules

Not built in phase 1. Each returns only by a recorded decision.

| ID | Layer in cdo_rules | Subject | Reason |
|---|---|---|---|
| BRZ-01 | Bronze | Content-Type must be `text/csv` | file checks off by user decision 2026-11-16 |
| BRZ-02 | Bronze | Empty file and size ceilings | file checks off by user decision 2026-11-16 |
| BRZ-03 | Bronze | Malware scan before read | file checks off by user decision 2026-11-16 |
| BRZ-04 | Bronze | Formula-injection scan that quarantines the file | file checks off by user decision 2026-11-16 |
| BRZ-05 | Bronze | Object-key allowlist | file checks off by user decision 2026-11-16. Its code-safety clause (the key is never interpolated) lives on in CTO-02 |
| CDO-02 | Bronze | Header/schema and PII gate | file checks off by user decision 2026-11-16. The header is recorded in the manifest, without a gate |
| GLD-01 | Gold | `dim_month` | gold out of scope in phase 1 |
| GLD-02 | Gold | `dim_industry` | gold out of scope in phase 1. The six codes plus `UNMAPPED` and `UNKNOWN` are used in silver through SQ-04 and SQ-12 |
| GLD-03 | Gold | `dim_customer` | gold out of scope in phase 1 |
| GLD-04 | Gold | `dim_spend_category` and its hierarchies | gold out of scope in phase 1. Only the HR-sensitive set is used now (CDO-11) |
| GLD-05 | Gold | `fct_customer_month_revenue` | gold out of scope in phase 1 |
| GLD-06 | Gold | `fct_sm_spend_month` | gold out of scope in phase 1 |
| GLD-07 | Gold | `agg_month_kpis` | gold out of scope in phase 1 |
| CMO-05 | Gold | `agg_month_sm_spend_per_new_logo` | gold out of scope in phase 1 |
| CRO-06 | Gold | `agg_retention_month` (NRR, GRR, logo churn) | gold out of scope in phase 1 |
| CDO-10 | Gold | No spend allocation below company × month × category | gold out of scope in phase 1. Silver builds no table that joins spend to a customer, industry or cohort key |
| CMO-07 | Gold | `low_n` on rates and averages | gold out of scope in phase 1 |
| CMO-08 | Gold | `sm_regime` annotation | gold out of scope in phase 1 |
| CTO-07 | Gold | Per-dataset watermarks for KPIs | gold out of scope in phase 1. `as_of_month` is defined in § Holes |
| CTO-08 | Gold | Unknown members in dimensions | gold out of scope in phase 1. "Never drop a fact for a failed lookup" is carried by SQ-04 and SQ-12 |
| CTO-09 | Gold | Export escaping | gold out of scope in phase 1. No export exists; the dashboard shows raw strings as text only |

Also deferred, inside IDs that stay active: the gold parts of CDO-11 (suppression in shared aggregates, parts 3–5), CTO-06 (lineage on gold rows), CTO-10 (gold rebuild and month-close retention) and CDO-04 (the silver → gold and logo identities).

## DQ metric definitions

The ETL computes every number below and writes it to the DQ store. The dashboard computes nothing.

**Per catalog rule × dataset**
- `evaluated` and `failed`: as defined per rule in the table below.
- `compliance_pct` = (evaluated − failed) ÷ evaluated × 100, rounded HALF_UP to 2 decimals. If failed > 0 and the rounded value is 100.00, publish 99.99. If failed < evaluated and the rounded value is 0.00, publish 0.01. If evaluated = 0, `compliance_pct` is null.
- `status`:

  | Status | Condition |
  |---|---|
  | `na` | The dataset is not in `applies_to`, or evaluated = 0 |
  | `pass` | failed = 0 |
  | `warn` | failed > 0 and (the rule does not count toward compliance, or the unrounded compliance is ≥ 99%) |
  | `fail` | failed > 0, the rule counts toward compliance, and the unrounded compliance is < 99% |

  The thresholds (100 and 99) are versioned parameters. A rule that does not count toward compliance never reaches `fail`.

**Which rules count toward compliance.** Those whose failure means delivered data is unusable or absent: every `exclude` rule, plus the findings SQ-08, SQ-09b and CDO-06a. Flags, the other findings, all business rules and all run controls do not count.

**Per dataset (department)**
- `rows_read` = data rows (the header is not a row). `rows_excluded` = rows with at least one exclude-failure.
- `row_compliance_pct` = (`rows_read` − `rows_excluded`) ÷ `rows_read` × 100, with the same rounding and the same 99.99 rule. Null when `rows_read` = 0. Findings and flags never change it.
- `rows_flagged` = distinct included rows with at least one hit in a `kind: row`, `action: flag` rule, quality or business.
- `rules_evaluated` = catalog rules of kind `row` or `finding` that count toward compliance, include the dataset in `applies_to` and have evaluated > 0. `rules_failing` = those with failed > 0.
- `rank` (1 = most compliant, no ties): sort by (1) unrounded `row_compliance_pct`, descending, null last; (2) `rules_failing`, ascending; (3) `rows_flagged` ÷ `rows_read`, ascending; (4) the fixed order `transactions`, `industry`, `sm_spend`.
- `trend`: the `row_compliance_pct` of each dataset per succeeded run.

**Run controls** are not rules of the dashboard. They are written to the run report with evaluated = 1 and failed = 0 or 1 per applicable dataset, and they are never written to `summary.json`: a published summary means every control passed.

**`evaluated` and `failed` per rule**

| Catalog id | Dataset | `evaluated` | `failed` |
|---|---|---|---|
| CDO-01 | each | data rows | rows that do not decode or hold a control character |
| SQ-02 | each | data rows that pass CDO-01 | empty records |
| SQ-01 | each | data rows that pass CDO-01 and SQ-02 | rows with the wrong field count |
| SQ-03 | industry | rows that pass stage A | rows with a bad ID or a duplicated `customer_id` |
| SQ-04 | industry | included rows | rows with `is_industry_unmapped` |
| SQ-05 | transactions | rows that pass stage A | rows with a bad ID or a duplicated key |
| SQ-06 | transactions | rows that pass stage A | rows with a bad month |
| SQ-07a | transactions | rows that pass stage A | rows with a bad amount |
| SQ-07b | transactions | included rows | rows with `is_negative_amount` |
| SQ-08 | transactions | panel cells (U × W) | holes with `hole_reason` = `missing` |
| SQ-09a | sm_spend | lines that pass stage A | lines with a bad or duplicated month |
| SQ-09b | sm_spend | calendar months from the earliest to the latest included month | months that no source line carries |
| SQ-10 | sm_spend | lines that pass stage A | lines with at least one bad spend cell |
| SQ-12 | industry | distinct `customer_id` in included Transactions rows | those with no included Industry row |
| SQ-13 | transactions, sm_spend | months with included rows in either money dataset | months this dataset lacks |
| CDO-05 | transactions | rows that pass stage A and SQ-07a | rows beyond DECIMAL(12,6) |
| CDO-05 | sm_spend | lines that pass stage A and SQ-10 | 0 by construction |
| CDO-06a | each | keys delivered in the previous succeeded run | keys not delivered now |
| CDO-06b | each | included rows whose key was included in the previous succeeded run | rows with `is_restated` |
| SB-04 | transactions | customers with at least one known-paid month | customers with `cohort_censoring` = `unknown` |
| SB-05 | transactions | included rows | included rows with `lifecycle_state` = `unknown` |
| SB-06 | transactions | gaps | gaps with `settlement_hole_affected` |
| SB-07 | transactions | known-paid months that end an internal stretch, clean or broken | those that end a broken stretch |
| SB-08 | transactions | customers with at least one known-paid month | customers with `has_excluded_months` |
| SB-10 | sm_spend | included lines | lines with at least one negative cell |
| SB-11 | transactions | included rows | included rows with `settlement_type` = `uneven_split` |
| CDO-08 | sm_spend | included lines whose month has included Transactions rows | lines whose month trips the tripwire |
| CRO-05 | transactions | included rows | included rows with a NULL under H9 |
| CRO-07 | transactions | customers with at least one known-paid month | customers with `first_payment_hole_affected` |

## Access

| Role | Summaries and rule results, all 3 datasets | Records of `transactions` and `industry` (customer-level) | `sm_spend` records: `Month`, `PaidMedia`, `Travel`, `PublicidadNoWeb`, `SoftwareTools` | `sm_spend` records: `Team`, `PayrollExpenses`, `Freelance` |
|---|---|---|---|---|
| `finance` | yes | yes | yes | yes |
| `data` | yes | yes | yes | "Restricted" |
| `revops` | yes | yes | yes | "Restricted" |

- **`revops` and `data` can see customer-level non-compliant records**, as `finance` can. All three are the named roles of CDO-11 (1). The records hold a pseudonym (`Cliente N`), a month and an amount or industry, and are Confidential-Financial. No other role exists, and none is granted until the CDO approves it.
- **HR-sensitive values are Finance-only, with no exception for `data`.** The API returns `"__restricted__"` for the three columns in `values`, and the UI shows "Restricted". Column names, `failed_columns`, counts and reason codes are visible to every role.
- **An `sm_spend` record that failed CDO-01 or SQ-01** has no trusted column positions, so every value in it is restricted for `data` and `revops`.
- **Search (`q`) runs on the masked record.** It must never match against a restricted value, or a role could recover it by probing.
- **`reason` strings, logs and run reports never contain an HR-sensitive value.** The restatement log and silver `sm_spend` keep those categories in an `hr_sensitive` partition that only Finance and the pipeline role read.
- **The unmasked serving store and bronze** are read only by the pipeline and API service roles. A person in `data` who must debug an HR-sensitive cell does it with a Finance reader.
- **PII:** the 13 registered columns hold no direct personal data (0 emails, 0 runs of 7+ digits, no names). With the schema gate off, a malformed line may carry anything, and the DQ store keeps it as received. That is why record access is limited to these roles and stored values are capped at 1,000 characters.

## Resolutions of the CTO's A-items

| Item | Resolution |
|---|---|
| A1 | Moot. No file is quarantined unread now that file checks are off, so every manifest is keyed by its SHA-256 |
| A2 | Moot. There is no quarantine release. The manifest records the first ingest only; run outcomes live in run reports, and a retry after our own defect is a new run over the same bytes |
| A3 | Moot. CDO-06 no longer rejects. For A, B, A, A becomes current again (CTO-03) and the keys B had are recorded as `REMOVED_KEY` findings |
| A4 | Gold. Deferred |
| A5 | Gold. Deferred. In silver, `implied_start_month` may fall before W and is stored as a plain `YYYY-MM` |
| A6 | Gold-era wording, deferred. Its live part is settled in § Access: HR-sensitive values are Finance-only, also in the DQ store |
| A7 | Gold. Deferred |
| A8 | Moot. Bronze has no check order: read, append, self-test, manifest |
| A9 (i) | Confirmed. SQ-06 uses the strict non-padded pattern G-TX-MONTH. `01/31/2022` fails, and the row is excluded, not the file |
| A9 (ii) | Confirmed. SQ-07a uses G-AMOUNT. `1e3`, `NaN`, `Infinity`, a leading `+`, `.5` and `5.` fail. Never pass a raw string to `Decimal()` before the pattern matches |
| A9 (iii) | Confirmed. `implied_start_month` is NULL when j is NULL |
| A9 (iv) | Confirmed with one addition. Money columns are never rounded. A stored quotient (`first_payment_ratio`, `sm_to_revenue_ratio`, a median of an even count, `compliance_pct` before its 2-decimal rounding) is computed from unrounded Decimal operands, stored as DECIMAL(38,12) HALF_UP, and never fed back into a money column or a test. **Every test is done without division:** tolerances as abs(a − b) ≤ 0.05 × b, the multiple as abs(first − j × next) ≤ 0.05 × j × next, the spike as first ≥ 1.9 × next, the outlier as median ≥ 25 × portfolio median, the tripwire as 0.5 × R ≤ S ≤ 20 × R. The CRO-03 share is the one truncation: 6 decimals, rounded down, with the remainder kept on the payment month |

## Expected results on today's files

Golden result for `data/*.csv`, as a first run (no previous run), re-checked on 2026-11-16 with `python3 -I` and `Decimal` under the rules above. The SB-11 figures were added and every figure was re-checked on 2026-11-17, by running SB-11 inside the engine's lifecycle hook: all run controls pass, and SB-11 changes only the figures named below.

| File | SHA-256 |
|---|---|
| `Transactions.csv` | `2dcbe59e9ac497c441f3c019963b11e9848ce4916e5773d257a36f83d953ae95` |
| `Industry.csv` | `b4330fc6d7df60429849b3b176746f5389c65931f281308eb8224c8efd440ff5` |
| `S&M_spend.csv` | `41fbb6499f2b0ad4565ccc0e96ec490c72599e15fd46d64086fd98e3443c4c13` |

**Departments**

| Dataset | `rows_read` | `rows_excluded` | `rows_flagged` | `row_compliance_pct` | `rules_evaluated` | `rules_failing` | `rank` |
|---|---|---|---|---|---|---|---|
| `transactions` | 66,674 | 0 | 22 | 100.00 | 8 | 0 | 1 |
| `sm_spend` | 34 | 0 | 5 | 100.00 | 7 | 0 | 2 |
| `industry` | 1,962 | 1 | 0 | 99.95 | 4 | 1 | 3 |

**Rules** (evaluated / failed / `compliance_pct` / status; "na" = 0 / 0 / null / `na`)

| Catalog id | `transactions` | `industry` | `sm_spend` |
|---|---|---|---|
| CDO-01 | 66,674 / 0 / 100.00 / pass | 1,962 / 0 / 100.00 / pass | 34 / 0 / 100.00 / pass |
| SQ-02 | 66,674 / 0 / 100.00 / pass | 1,962 / 1 / 99.95 / warn | 34 / 0 / 100.00 / pass |
| SQ-01 | 66,674 / 0 / 100.00 / pass | 1,961 / 0 / 100.00 / pass | 34 / 0 / 100.00 / pass |
| SQ-03 | na | 1,961 / 0 / 100.00 / pass | na |
| SQ-04 | na | 1,961 / 0 / 100.00 / pass | na |
| SQ-05 | 66,674 / 0 / 100.00 / pass | na | na |
| SQ-06 | 66,674 / 0 / 100.00 / pass | na | na |
| SQ-07a | 66,674 / 0 / 100.00 / pass | na | na |
| SQ-07b | 66,674 / 0 / 100.00 / pass | na | na |
| SQ-08 | 66,674 / 0 / 100.00 / pass | na | na |
| SQ-09a | na | na | 34 / 0 / 100.00 / pass |
| SQ-09b | na | na | 34 / 0 / 100.00 / pass |
| SQ-10 | na | na | 34 / 0 / 100.00 / pass |
| SQ-12 | na | 1,961 / 0 / 100.00 / pass | na |
| SQ-13 | 34 / 0 / 100.00 / pass | na | 34 / 0 / 100.00 / pass |
| CDO-05 | 66,674 / 0 / 100.00 / pass | na | 34 / 0 / 100.00 / pass |
| CDO-06a | na (first run) | na (first run) | na (first run) |
| CDO-06b | na (first run) | na (first run) | na (first run) |
| SB-04 | 1,961 / 0 / 100.00 / pass | na | na |
| SB-05 | 66,674 / 0 / 100.00 / pass | na | na |
| SB-06 | 468 / 0 / 100.00 / pass | na | na |
| SB-07 | 468 / 0 / 100.00 / pass | na | na |
| SB-08 | 1,961 / 0 / 100.00 / pass | na | na |
| SB-10 | na | na | 34 / 5 / 85.29 / warn |
| SB-11 | 66,674 / 22 / 99.97 / warn | na | na |
| CDO-08 | na | na | 34 / 0 / 100.00 / pass |
| CRO-05 | 66,674 / 0 / 100.00 / pass | na | na |
| CRO-07 | 1,961 / 0 / 100.00 / pass | na | na |

All 16 run controls: evaluated 1, failed 0 for each applicable dataset.

**Records**
- **Excluded (1):** `industry`, `source_line` 1963, `key` `{"ID": ""}`, `values` `{"ID": "", "Industria": ""}`, `failed_columns` `["ID", "Industria"]`, rule SQ-02, reason `EMPTY_RECORD: every source column is empty`, no other failed rule.
- **Flagged (27):**
  - `sm_spend` (5): rule SB-10, `failed_columns` `["PayrollExpenses"]`, reason code `NEGATIVE_SPEND`, months 2023-11, 2023-12, 2024-02, 2024-03 and 2024-07 (`source_line` 24, 25, 27, 28 and 32). Their values are HR-sensitive and are not reproduced here; the five sum to −13,500,000 at full amount.
  - `transactions` (22): rule SB-11, `failed_columns` `["amount"]`, reason code `UNEVEN_SPLIT`, 11 pairs, listed as customer: months (`source_line`): 12: 2022-11, 2022-12 (386, 387); 34: 2022-05, 2022-06 (1128, 1129); 78: 2022-05, 2022-06 (2624, 2625); 93: 2023-07, 2023-08 (3148, 3149); 191: 2022-05, 2022-06 (6466, 6467); 336: 2022-06, 2022-07 (11397, 11398) and 2023-02, 2023-03 (11405, 11406); 370: 2022-02, 2022-03 (12549, 12550); 437: 2024-01, 2024-02 (14850, 14851); 576: 2024-03, 2024-04 (19578, 19579); 651: 2023-02, 2023-03 (22115, 22116). Both rows of a pair carry the same reason, for example `UNEVEN_SPLIT: 2022-11 and 2022-12 sum to twice the amount of 2022-10 and 2023-01`.
- **Findings:** none.

**Business figures** (unchanged by the new policy, because today's files have no excluded Transactions or S&M row and no hole)

| Figure | Value |
|---|---|
| Transactions: rows in silver; U; W; `as_of_month`; `churn_confirmed_through` | 66,674; 1,961 customers; 34 months (2022-01 → 2024-10); 2024-10; 2024-08 |
| Σ `amount`; Σ `amount_value` | 221,441.504508; 2,214,415,045.08 |
| Zero rows; paid rows; negative rows; holes | 33,703; 32,971; 0; 0 |
| Industry: rows read; in silver; excluded | 1,962; 1,961; 1 (the empty record) |
| Industry mix in silver | RESTAURANTS 529; MANUFACTURING 454; RETAIL 428; TECHNOLOGY 241; PROFESSIONAL_SERVICES 165; HEALTHCARE 144; UNMAPPED 0; UNKNOWN 0 |
| S&M: lines; silver long rows; Σ spend; Σ `spend_value` | 34; 238; 77.818; 7,781,800,000 |
| S&M negative cells | 5, all `PayrollExpenses` |
| `cohort_censoring` | left 377; probable_left 43 (40 Feb-2022, 3 Mar-2022); none 1,541; unknown 0 |
| New logos | 1,541 (68 in Feb-2022) |
| `lifecycle_state` | paying 31,366; pre_acquisition 29,321; churned 3,811; new 1,541; settled_gap 281; paused 231; reactivated 64; grace 59; unknown 0 |
| Gaps; settled | 468; 211 = arrears 155 + prepay 47 + split 9 |
| Paused gaps; reactivations | 193; 64 (60 customers) |
| Open churn spells; customers in grace; provisional rows | 237; 46; 5,399 |
| Portfolio median; outliers | 5.25; {94 at 60.0×, 322 at 31.7×} |
| First-month spikes among new logos | 116 at ≥ 1.9×; 64 at ≥ 3× |
| S&M ÷ revenue by month; tripwire | 1.61 to 7.62; fires in 0 of 34 months |
| Σ `amount_normalized` = Σ `amount` per customer | holds for 1,961 of 1,961 |
| Uneven splits (SB-11) | 11 pairs, 10 customers, 22 rows with `settlement_type` = `uneven_split` and `settlement_confidence` = `high`; the first month is above b in 7 pairs and below it in 4. `lifecycle_state`, gap and settlement counts above are unchanged |
| CRO-05: Σ `expansion_amount`; Σ `contraction_amount`; rows above 0 | 3,499.903452; 4,656.537782; 1,212 and 954. Without SB-11 they were 3,582.386454; 4,739.020784; 1,230 and 969. Both sums fall by 82.483002 (824,830.02 at full amount), and the net, −1,156.634330, is unchanged |
| `amount_lag12` | 18 rows read b instead of the raw amount: months t whose t−12 is a pair month, for the 9 pairs that start no later than 2023-09 |

**Hole fixtures.** Today's files exercise no hole. The ETL tests must add synthetic cases for at least: a bad amount inside a gap, a duplicated key, a missing line, a hole before the first paid month, a hole in month p−1, a hole in the last month, and an S&M line with one bad cell.

## Asks for the data owners

| Ask | Owner | Changes |
|---|---|---|
| Fix the extract so `Industry.csv` does not end with an empty `,` record | RevOps / source-system owner | SQ-02 on `industry` returns to 100% |
| Q6: the industry taxonomy, who assigns it and when a new customer gets its row | RevOps | SQ-04 (flag or exclude), SQ-12 (counts or not), SB-09 |
| Q8: full snapshot or increment; are zero months always present; can closed months change | Billing + Finance | SQ-08, CDO-06 |
| Q2: can revenue be negative (refunds, credit notes); invoiced, collected or recognized | Billing + Finance | SQ-07b, SB-06, CRO-05 |
| Q3: what the 5 negative `PayrollExpenses` months are; actual or budget | Finance | SB-10, CFO-03 |
| Q1, Q4: currency of each file; does Transactions cover the base the S&M spend serves | Finance | CDO-08, CFO-03, CFO-05 |
| Q5, Q7, Q9: unpaid-month patterns; true first-invoice dates; whether 94 and 322 are single accounts | Billing + RevOps | SB-04–SB-08 |
| Q17: are the 11 uneven two-month splits one usual two-month charge split in two (proration, a billing-date change or something else), and what are the 6 longer runs | Billing | SB-11 (its status, and whether it extends to runs of 3+ months), CRO-05 |

## Notes for the builder

- **Contract v1 fit.** The API `rule_id` is the catalog id (`SQ-07a`, not `SQ-07`). Run controls are not in `summary.json`. `rows_read` excludes the header. The numbers in the contract's examples are illustrative; the golden values are the ones above (for example `rules_evaluated` is 4 for `industry`).
- **`description`** in the API is the Rule cell of the tables above. For a two-part ID, use that part's sentence.
- **Corrections to earlier documents** (not applied there; this file is authoritative): zero rows are 33,703 of 66,674 = 50.55% (`cdo_rules.md` says 50.6%); "a zero or missing month" must never be read as unpaid: only a known zero is unpaid. The corrections listed in `cdo_rules.md` for `docs/data_semantics/` remain open.

## Changelog

| Date | Change | Requested by |
|---|---|---|
| 2026-11-16 | First approval | CDO |
| 2026-11-17 | New rule SB-11 "uneven split", added after the review of customer 12, whose Nov and Dec 2022 add up to twice its usual 6.72. Matching edits: one sentence in CRO-03; SB-11 placed in stage E; the counts; SB-11 added to the DQ metric table; expected results updated (transactions `rows_flagged` 0 → 22, the SB-11 rule result and records, the CRO-05 movement totals); ask Q17 added. No other rule changed. Evidence and notes for the CTO: `docs/etl_discussion/round3/cdo_uneven_split.md` | User |

## Machine-readable catalog

```yaml
rule_catalog:
  # ---------- bronze
  - id: BRZ-06
    title: "Bronze adds only _ingested_at"
    layer: bronze
    kind: control
    action: run_control
    applies_to: [transactions, industry, sm_spend]
    inferred: false
    counts_toward_compliance: false
    params: {column: _ingested_at, record_separator: LF}
  - id: CTO-01
    title: "Bronze round-trip self-test"
    layer: bronze
    kind: control
    action: run_control
    applies_to: [transactions, industry, sm_spend]
    inferred: false
    counts_toward_compliance: false
  - id: CTO-02
    title: "Lineage manifest per file"
    layer: bronze
    kind: control
    action: run_control
    applies_to: [transactions, industry, sm_spend]
    inferred: false
    counts_toward_compliance: false
    params: {manifest_key: "_manifests/<dataset>/<sha256>.json"}
  - id: CTO-03
    title: "One timestamp per file, idempotent"
    layer: bronze
    kind: control
    action: run_control
    applies_to: [transactions, industry, sm_spend]
    inferred: false
    counts_toward_compliance: false
    params: {idempotency_key: [dataset, sha256], timestamp_format: "YYYY-MM-DDTHH:MM:SSZ"}
  # ---------- silver quality
  - id: CDO-01
    title: "Line is valid UTF-8, no control chars"
    layer: silver_quality
    kind: row
    action: exclude
    applies_to: [transactions, industry, sm_spend]
    inferred: false
    counts_toward_compliance: true
    params: {short_circuit: true, reason_codes: [UNDECODABLE_LINE, CONTROL_CHAR]}
  - id: SQ-02
    title: "Empty records"
    layer: silver_quality
    kind: row
    action: exclude
    applies_to: [transactions, industry, sm_spend]
    inferred: false
    counts_toward_compliance: true
    params: {short_circuit: true, reason_codes: [EMPTY_RECORD]}
  - id: SQ-01
    title: "Line has the registered field count"
    layer: silver_quality
    kind: row
    action: exclude
    applies_to: [transactions, industry, sm_spend]
    inferred: false
    counts_toward_compliance: true
    params:
      short_circuit: true
      delimiter: ","
      field_count: {transactions: 3, industry: 2, sm_spend: 8}
      columns:
        transactions: [ID, month, amount]
        industry: [ID, Industria]
        sm_spend: [Month, PaidMedia, Travel, PublicidadNoWeb, Freelance, SoftwareTools, Team, PayrollExpenses]
      reason_codes: [FIELD_COUNT]
  - id: SQ-03
    title: "Customer ID valid and unique"
    layer: silver_quality
    kind: row
    action: exclude
    applies_to: [industry]
    inferred: false
    counts_toward_compliance: true
    params: {id_pattern: '^Cliente [1-9][0-9]*$', reason_codes: [BAD_CUSTOMER_ID, DUPLICATE_CUSTOMER_ID]}
  - id: SQ-04
    title: "Industry outside the registered list"
    layer: silver_quality
    kind: row
    action: flag
    applies_to: [industry]
    inferred: true
    counts_toward_compliance: false
    params:
      normalization: NFC
      domain:
        "Restaurantes": RESTAURANTS
        "Producción": MANUFACTURING
        "Retail": RETAIL
        "Tecnología": TECHNOLOGY
        "Servicios profesionales": PROFESSIONAL_SERVICES
        "Salud": HEALTHCARE
      unmapped_code: UNMAPPED
      reason_codes: [UNMAPPED_INDUSTRY]
  - id: SQ-05
    title: "Customer-month key valid and unique"
    layer: silver_quality
    kind: row
    action: exclude
    applies_to: [transactions]
    inferred: false
    counts_toward_compliance: true
    params: {id_pattern: '^[1-9][0-9]*$', reason_codes: [BAD_ID, DUPLICATE_KEY]}
  - id: SQ-06
    title: "Month is a month-end date"
    layer: silver_quality
    kind: row
    action: exclude
    applies_to: [transactions]
    inferred: false
    counts_toward_compliance: true
    params: {month_pattern: '^(1[0-2]|[1-9])/(3[01]|[12][0-9]|[1-9])/([0-9]{4})$', must_be_month_end: true, reason_codes: [BAD_MONTH]}
  - id: SQ-07a
    title: "Amount is a plain decimal number"
    layer: silver_quality
    kind: row
    action: exclude
    applies_to: [transactions]
    inferred: false
    counts_toward_compliance: true
    params: {amount_pattern: '^-?[0-9]+(\.[0-9]+)?$', reason_codes: [BAD_AMOUNT]}
  - id: SQ-07b
    title: "Negative amount"
    layer: silver_quality
    kind: row
    action: flag
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: false
    params: {flag_column: is_negative_amount, reason_codes: [NEGATIVE_AMOUNT]}
  - id: SQ-08
    title: "Missing customer-months"
    layer: silver_quality
    kind: finding
    action: finding
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: true
    params: {reason_codes: [MISSING_CUSTOMER_MONTH]}
  - id: SQ-09a
    title: "Month valid and unique"
    layer: silver_quality
    kind: row
    action: exclude
    applies_to: [sm_spend]
    inferred: false
    counts_toward_compliance: true
    params: {month_pattern: '^[0-9]{4}-(0[1-9]|1[0-2])$', reason_codes: [BAD_MONTH, DUPLICATE_MONTH]}
  - id: SQ-09b
    title: "Missing months in the series"
    layer: silver_quality
    kind: finding
    action: finding
    applies_to: [sm_spend]
    inferred: true
    counts_toward_compliance: true
    params: {reason_codes: [MONTH_GAP]}
  - id: SQ-10
    title: "Spend cells match the $0.000 format"
    layer: silver_quality
    kind: row
    action: exclude
    applies_to: [sm_spend]
    inferred: false
    counts_toward_compliance: true
    params: {cell_pattern: '^-?\$[0-9]{1,6}\.[0-9]{3}$', spend_columns: [PaidMedia, Travel, PublicidadNoWeb, Freelance, SoftwareTools, Team, PayrollExpenses], reason_codes: [BAD_SPEND_CELL]}
  - id: SQ-12
    title: "Customers with no Industry row"
    layer: silver_quality
    kind: finding
    action: finding
    applies_to: [industry]
    inferred: true
    counts_toward_compliance: false
    params: {unknown_code: UNKNOWN, reason_codes: [NO_INDUSTRY_ROW]}
  - id: SQ-13
    title: "Month covered by only one dataset"
    layer: silver_quality
    kind: finding
    action: finding
    applies_to: [transactions, sm_spend]
    inferred: true
    counts_toward_compliance: false
    params: {reason_codes: [MONTH_NOT_IN_DATASET]}
  - id: CDO-05
    title: "Value fits its registered precision"
    layer: silver_quality
    kind: row
    action: exclude
    applies_to: [transactions, sm_spend]
    inferred: false
    counts_toward_compliance: true
    params:
      amount: {precision: 12, scale: 6, value_precision: 18, value_scale: 2}
      spend: {precision: 12, scale: 3, value_precision: 18, value_scale: 0}
      reason_codes: [PRECISION]
  - id: CDO-06a
    title: "Keys removed since the previous run"
    layer: silver_quality
    kind: finding
    action: finding
    applies_to: [transactions, industry, sm_spend]
    inferred: true
    counts_toward_compliance: true
    params: {compare_to: previous_succeeded_run, reason_codes: [REMOVED_KEY]}
  - id: CDO-06b
    title: "Values restated since previous run"
    layer: silver_quality
    kind: row
    action: flag
    applies_to: [transactions, industry, sm_spend]
    inferred: true
    counts_toward_compliance: false
    params: {compare_to: previous_succeeded_run, flag_column: is_restated, reason_codes: [RESTATED_VALUE]}
  - id: CDO-04
    title: "Bronze rows = silver + excluded"
    layer: silver_quality
    kind: control
    action: run_control
    applies_to: [transactions, industry, sm_spend]
    inferred: false
    counts_toward_compliance: false
    params: {sm_spend_long_rows_per_line: 7}
  - id: CTO-06
    title: "Lineage on every row"
    layer: silver_quality
    kind: control
    action: run_control
    applies_to: [transactions, industry, sm_spend]
    inferred: false
    counts_toward_compliance: false
    params: {columns: [_run_id, _source_key, _source_sha256, _ingested_at, _rules_version, as_of_month, _source_line]}
  - id: CTO-10
    title: "Full rebuild, atomic publish"
    layer: silver_quality
    kind: control
    action: run_control
    applies_to: [transactions, industry, sm_spend]
    inferred: false
    counts_toward_compliance: false
    params: {min_summaries_retained: 24}
  - id: CDO-11
    title: "Access and HR-sensitive masking"
    layer: silver_quality
    kind: control
    action: run_control
    applies_to: [transactions, industry, sm_spend]
    inferred: false
    counts_toward_compliance: false
    params:
      roles: [data, finance, revops]
      hr_sensitive_columns: [Team, PayrollExpenses, Freelance]
      hr_sensitive_roles: [finance]
      restricted_value: "__restricted__"
      max_stored_value_chars: 1000
  # ---------- silver business
  - id: SB-01
    title: "Revenue × 10,000 (owner definition)"
    layer: silver_business
    kind: control
    action: run_control
    applies_to: [transactions]
    inferred: false
    counts_toward_compliance: false
    params: {factor: 10000}
  - id: SB-02
    title: "S&M × 100,000,000 (owner definition)"
    layer: silver_business
    kind: control
    action: run_control
    applies_to: [sm_spend]
    inferred: false
    counts_toward_compliance: false
    params: {factor: 100000000}
  - id: SB-03
    title: "Paying means amount above zero"
    layer: silver_business
    kind: control
    action: run_control
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: false
  - id: SB-04
    title: "Cohort and left-censoring"
    layer: silver_business
    kind: finding
    action: finding
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: false
    params: {censoring_multiples: [2, 3], tolerance: 0.05, reason_codes: [COHORT_UNKNOWN]}
  - id: SB-05
    title: "Churn after 3 unpaid months"
    layer: silver_business
    kind: row
    action: flag
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: false
    params: {churn_months: 3, grace_max_months: 2, churn_confirmed_lag_months: 2, reason_codes: [STATE_UNKNOWN]}
  - id: SB-06
    title: "Settled gaps: arrears, prepay, split"
    layer: silver_business
    kind: finding
    action: finding
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: false
    params: {settlement_tolerance: 0.05, test_order: [arrears, prepay, split], reason_codes: [SETTLEMENT_HOLE]}
  - id: SB-07
    title: "Reactivation versus pause"
    layer: silver_business
    kind: row
    action: flag
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: false
    params: {pause_max_months: 2, reason_codes: [REACTIVATION_UNKNOWN]}
  - id: SB-08
    title: "Outlier customers"
    layer: silver_business
    kind: finding
    action: finding
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: false
    params: {outlier_ratio: 25, min_payments: 3, owner_overrides: [], reason_codes: [OUTLIER_INCOMPLETE_HISTORY]}
  - id: SB-09
    title: "Industry fixed per customer"
    layer: silver_business
    kind: control
    action: run_control
    applies_to: [industry]
    inferred: true
    counts_toward_compliance: false
  - id: SB-10
    title: "Negative spend"
    layer: silver_business
    kind: row
    action: flag
    applies_to: [sm_spend]
    inferred: true
    counts_toward_compliance: false
    params: {flag_column: is_negative_spend, expected_negative_columns: [PayrollExpenses], reason_codes: [NEGATIVE_SPEND, NEGATIVE_SPEND_OTHER_CATEGORY]}
  - id: SB-11
    title: "Uneven split of a two-month total"
    layer: silver_business
    kind: row
    action: flag
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: false
    params: {window_months: 4, pair_months: 2, sum_test: exact, settlement_type: uneven_split, settlement_confidence: high, pair_column: uneven_split_start_month, reason_codes: [UNEVEN_SPLIT]}
  - id: CDO-07
    title: "One lifecycle state per customer-month"
    layer: silver_business
    kind: control
    action: run_control
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: false
    params: {states: [pre_acquisition, new, paying, reactivated, settled_gap, paused, churned, grace, unknown]}
  - id: CDO-08
    title: "Unit tripwire: S&M ÷ revenue"
    layer: silver_business
    kind: row
    action: flag
    applies_to: [sm_spend]
    inferred: true
    counts_toward_compliance: false
    params: {tripwire_bounds: [0.5, 20], reason_codes: [UNIT_TRIPWIRE]}
  - id: CFO-03
    title: "Currency and basis are unconfirmed"
    layer: silver_business
    kind: control
    action: run_control
    applies_to: [transactions, sm_spend]
    inferred: false
    counts_toward_compliance: false
    params:
      currency_code: null
      currency_status: unconfirmed
      basis_status: unconfirmed
      basis_hint: {transactions: cash-like, sm_spend: budget-like}
  - id: CFO-05
    title: "Scope of S&M vs revenue unconfirmed"
    layer: silver_business
    kind: control
    action: run_control
    applies_to: [transactions, sm_spend]
    inferred: false
    counts_toward_compliance: false
    params: {scope_status: unconfirmed}
  - id: CRO-03
    title: "Normalized amount for settled gaps"
    layer: silver_business
    kind: control
    action: run_control
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: false
    params: {share_scale: 6, share_rounding: down}
  - id: CRO-05
    title: "Expansion and contraction proxy"
    layer: silver_business
    kind: row
    action: flag
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: false
    params: {lag_months: 12, reason_codes: [MOVEMENT_UNKNOWN]}
  - id: CRO-07
    title: "First-month spike"
    layer: silver_business
    kind: finding
    action: finding
    applies_to: [transactions]
    inferred: true
    counts_toward_compliance: false
    params: {spike_ratio: 1.9, band_edges: [1.9, 3], reason_codes: [FIRST_PAYMENT_UNKNOWN]}
```
