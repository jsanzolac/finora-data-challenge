# ETL review: findings

> Finora's executive review of the data-lake ETL, 2026-11-15. It replaces the `etl-discover` workflow, which was not run, and covers the same agenda (M1–M8 in [`00_baseline.md`](00_baseline.md)).
>
> **Three rounds:**
> - **Round 1 (positions):** all five executives (CRO, CFO, CMO, CDO, CTO).
> - **Round 2 (debate):** all five.
> - **Round 3 (resolution):** the CDO and the CTO only, at the user's request. They built on the compiled draft of this document, not from scratch. The CDO settled the rules in [`round3/cdo_rules.md`](round3/cdo_rules.md), and the CTO designed the ETL that implements them in [`round3/cto_design.md`](round3/cto_design.md).
>
> **Result:**
> - **61 final rules** (51 keep, 10 flag) and 19 dropped or merged.
> - **All 19 open disagreements (D1–D19) decided**, with none left unresolved.
> - **A design that traces all 61 rules**, at about $0.80/month.
> - **9 build-level points (A1–A9)** where the CTO found rules that collide in implementation. They await the CDO's confirmation (§5.4).
>
> **Provenance.** §1.3, §2, §3, §5.1 and §5.3 are copied verbatim from `cdo_rules.md`. §4 summarizes `cto_design.md`. Everything else is the main session's summary.

## 1. Summary of the discussion

### 1.1 Where the executives agreed (rounds 1–2, confirmed in round 3)

- **Layer contracts hold, and bronze can prove them.** Bronze stays CSV and appends `_ingested_at` losslessly. The proof is a byte round-trip: drop the last field and the SHA-256 must equal staging's (CTO-01, which is the same test as the CDO's BRZ-06 text).
- **Money is exact.** DECIMAL everywhere, never floats: floats give a wrong full amount on 2,436 Transactions rows and 32 of 238 S&M cells. Every load reconciles exactly from bronze to silver plus quarantine to gold (CDO-04).
- **No rule silently removes or understates revenue.** A failed lookup maps to an `UNKNOWN` or `UNMAPPED` member and is flagged, never quarantined. In round 3 the CDO went further: a malformed amount, month or ID, a duplicate key or a missing customer-month now rejects the file (D1). So no NULL amount reaches silver, and the previous publish stays live.
- **One control of each kind.** The duplicate reconciliations, manifests, lineage sets and status labels were merged into CDO-04, CTO-02, CTO-06 and CFO-03.
- **The baseline lifecycle rules were wrong.** SB-07 as written gives about 313 "reactivations", against a canonical **64** (60 customers). **211 of 468 gaps (45.1%)** are settled by arrears, prepayment or split, not ⅓.
- **The Feb-2022 cohort is partly left-censored:** 43 `probable_left` customers, so **1,541 new logos** in total (68 in Feb-2022).
- **No attribution.** S&M has no customer, industry or channel key. Spend meets revenue only at the month. There are no lag columns and no causal claims: the whole-window correlation is a trend artifact.
- **No board-ready CAC.** Nothing is named CAC, payback, LTV, MRR or ARR. A labelled `sm_spend_per_new_logo` (4,920,052 for Feb-22 to Oct-24) carries its components and its unconfirmed scope, currency and basis. In full amounts S&M is 5.75× / 3.21× / 2.30× revenue (2022 / 2023 / Jan–Oct 2024), so Transactions may cover only part of the customer base.
- **Outliers are flagged, never removed.** Customers 94 and 322 meet the CRO's median ≥ 25× criterion. All-in figures are primary.
- **PII.** There are no direct identifiers. `Cliente N` is pseudonymised personal data plus confidential financial data, and the payroll categories are HR-sensitive.
- **The infrastructure needs fixing first** (verified read-only, unchanged in round 3):
  - the identity is root access keys, and there are 0 IAM users;
  - there's no CloudTrail;
  - versioning is off on all buckets (staging VersionIds are `null`);
  - there are no bucket policies (TLS isn't enforced).

### 1.2 Disagreements settled during rounds 1–2

| Topic | Positions | Outcome | How it was settled |
|---|---|---|---|
| Reactivation count (SB-07) | Baseline about 313; CRO 65; CDO 64 | **64 (60 customers)** | The CDO showed the CRO's 65th (customer 40) is a split settlement, and the CRO conceded. The CTO reproduced 64. The CFO and CMO withdrew their "keep" on the baseline text |
| Share of settled gaps (SB-06) | Baseline ⅓ | **211 of 468 (155 arrears, 47 prepaid, 9 split)** | Prepayment passed a placebo test (CDO, CRO, CFO). The test order was settled in round 3 (D5) |
| Feb-2022 suspects | CMO 32 of 95; CDO 34 of 108 | The same customers on different bases. The next paid month is canonical | CDO, CTO and CFO; the CMO accepted. The multiples were settled in round 3 (D4) |
| Outlier criterion (SB-08) | CDO ≥ 1.0% share; CRO median ≥ 25× | **The CRO's median criterion** | The CDO withdrew its version, because a share drifts with tenure and window length. CFO, CMO and CTO agreed. The details were settled in round 3 (D17) |
| CAC in gold | CRO: drop it; CFO: indicative plus payback; CMO: `sm_spend_per_new_logo` | **No column named CAC, and no payback** | The CFO withdrew payback and the CRO accepted a labelled view. Its placement was settled in round 3 (D11) |
| Failed lookups (SQ-04, SQ-12) | Baseline quarantine | **UNKNOWN / UNMAPPED member, plus a flag** | All five by round 2 |
| Bronze format and proof | — | CSV with a lossless append; SHA-256 round-trip (CTO-01) | Consensus |
| BRZ-04, SQ-02, SQ-05, SQ-10 onFailure | Mixed | BRZ-04: numeric exemption, quarantine the file. SQ-02: quarantine the record. SQ-05 and SQ-10: reject the file | The CTO and CDO proposed; the others switched |
| Lifecycle model; exact decimals; SQ-11 | CRO-04 vs CDO-07; CTO-04 vs CDO-05 | CDO-07; CDO-05; SQ-11 merged into SB-10 | The proposers withdrew |
| SCD2-ready `dim_customer` (CRO) | — | Not adopted | CTO and CMO: there are no source dates |
| Revenue control total | CRO-02 cited 2,214,415,000 | **2,214,415,045.08** | CDO, CFO and CTO. Totals come from the manifest, never from docs |

### 1.3 Disagreements resolved in round 3 (CDO, verbatim)

The CDO reversed its own round-2 position on D1 (siding with the CTO), D2 and D11 (siding with the CRO, CFO and CMO). It adopted the CTO's bronze texts (D12–D14) and the CFO's flag name (D15). It held its ground on D4 (j ∈ {2, 3}), D6 (normalized retention headline), D7 (tripwire bounds) and D8 (no widening of scale).

| D# | Topic | Decision | Reason (evidence) | Who it sides with |
|---|---|---|---|---|
| D1 | Non-numeric amount (SQ-07, CRO-01) | Reject the file. The same applies to a missing customer-month (SQ-08), an unparseable month (SQ-06), a non-integer ID and a duplicate key (SQ-05). No NULL amount reaches silver, so there is no per-month withholding. CRO-01 merges into SQ-08 | A malformed cell in a full-snapshot money extract means the extract is broken, the same class as SQ-05 and SQ-10, which already reject. The lifecycle model is path-dependent: one NULL month leaves that customer's later churn, settlement and reactivation states unknown, so withholding a single month is not enough. A reject costs a delay, not revenue: the previous publish stays live and the other datasets still advance (CTO-10) | CTO. I reverse my R2 position. The aim of the CDO, CFO and CRO, that nothing is silently removed or understated, still holds |
| D2 | Watermark (CTO-07) | Per-dataset watermarks. Revenue KPIs run to `revenue_complete_through`, spend KPIs to `spend_complete_through`, and combined KPIs to the earlier of the two. A rejected file holds back only its own dataset. Publishing per fact family is a mechanism choice for the CTO within this rule | `agg_month_kpis` reads Transactions only. With a single min(), a late S&M file stops every revenue KPI. Both datasets cover the same window today (2022-01 → 2024-10) | CRO, CFO, CMO. I reverse my R2 "keep" |
| D3 | Small-cell suppression (CDO-11) | Rewritten policy, effective now. Customer-level data is open only to named Finance, RevOps (with the Revenue and CS leaders) and Data roles. Outside them, money in cells under 5 customers is suppressed, with complementary suppression. Counts are not suppressed (they carry `low_n`). The top-1 and top-10 shares are exempt for the board and auditors. No grant outside the named roles until the suppressed shares exist | The risk sits in money spread over few customers, not in counts of pseudonyms. Industry × month revenue cells have ≥ 23 payers, but 1,307 of 3,382 industry × cohort-month × month cells have fewer than 5. Count suppression would hide 64 of 198 new-logo cells (CMO). A lone suppressed cell can be recovered by subtraction (CTO). There are 0 IAM users and no BI tool today | CMO (counts), CFO (concentration), CRO (roles), CTO (IAM now, suppressed views before the first outside grant). I keep the money suppression |
| D4 | Censoring multiples (SB-04) | j ∈ {2, 3}: 43 `probable_left` and 1,541 new logos, 68 of them in Feb-2022. Publish `new_logos_probable_left` beside `new_logos`, and `first_payment_multiple` on `dim_customer`, so the j = 2 count (1,550) stays reproducible | The 3× tail is not chance. Feb-2022 has 6 of 108 against 0.9 expected (background 12 of 1,446 cohorts, Apr-22–Oct-24; Poisson p = 0.0003), and Mar-2022 has 3 of 30 against 0.25 (p = 0.002). The 27 Mar–Jul 2024 logos with a 2× first payment show that such a payment means service began a month earlier. At the window edge that start falls in the censored month, so they support the rule, which only touches cohorts whose implied start is ≤ 2022-01. The extra cost over j = 2 is one column | CDO. CMO and CFO on publishing both counts. Against the CRO (j = 2) |
| D5 | Settlement precedence (SB-06, CDO-07, CRO-03) | The tests run in order, and the first match wins: arrears, then prepay, then split. I withdraw "nearest multiple" | Arrears and prepay never both match (0 of 468). Split matches 178 gaps, 169 of which also match arrears (122) or prepay (47). The union (211) does not depend on order, but `settlement_type`, `is_catch_up` and the normalization do. Result: 155 arrears, 47 prepay, 9 split | CRO, CFO, CTO |
| D6 | Retention basis (CRO-06) | The headline is point-in-time `amount_normalized`. Raw `amount` is published beside it as `_raw` and the 3-month average as `_avg3`; neither is the headline. Never called MRR or ARR while the basis is unconfirmed | Raw NRR drops to 79.8% in Aug-2023, against 88.9% normalized, only because customer 94's 3× catch-up sits in the Aug-2022 base (ex-94: 86.7% vs 86.6%). Normalized minus raw ranges from −0.8 to +9.0 points. Raw also counts settled-gap months as lost revenue, which contradicts the canonical churn. The 3-month average adds 3.3 points at Oct-2024 (96.2% vs 92.9%) through smoothing alone | CDO. CFO on demoting the smoothed series and on the naming ban. Against the CFO (raw headline) and the CRO's round-1 3-month MRR proxy |
| D7 | Tripwire bounds (CDO-08) | [0.5, 20], versioned. While the tripwire fires, every combined KPI for that month, and every window containing it, is NULL | An S&M file off by ×10 or ÷10 trips in 28 or 21 of 34 months with [0.5, 20], and in none with [0.01, 100]. Both bounds catch a ×10,000 slip. Today's 1.61–7.62× leaves a 3.2× margin below and 2.6× above | CDO; CFO (the NULL). Against the CMO |
| D8 | Precision loss (CDO-05) | A value beyond its registered scale or type rejects the file. Nothing is rounded, and the scale is not widened | Every amount has ≤ 6 decimals (≤ 2 after × 10,000), which corroborates the owner factor. A 7th decimal means the format or the factor changed, the same class as SQ-10's 3-decimal rule, and widening the scale would accept that silently. The previous publish stays live, so revenue arrives late but is not frozen | CDO, CFO, CTO. Against the CRO |
| D9 | Manifest checksum mismatch (CTO-02) | If the bytes read differ from the bytes scanned or declared: quarantine for the security role. If the bronze round-trip fails: reject (CTO-01). In both cases nothing loads and the previous snapshot stays current | Bytes that differ from the scanned ones are unscanned, so they must not land in `_rejected/`, which Data can read. A round-trip failure is our own write defect. No staging object stores a checksum today (verified) | CDO. Against the CTO and CFO, although downstream behaviour is identical |
| D10 | Idempotency key (CTO-03) | (dataset, SHA-256 of the bytes), permanently. The VersionId is recorded but is never the key | VersionId is `null` on all 3 objects, and versioning was never enabled (verified 2026-11-15). Keyed on VersionId, a corrected re-upload would become a no-op. Content identity stays correct after versioning is on, and the CTO's execution name already uses `sha256[:16]` | CDO, CRO |
| D11 | Where `sm_spend_per_new_logo` lives (GLD-07) | Its own view, `agg_month_sm_spend_per_new_logo` (CMO-05). It sits outside `agg_month_kpis` and outside standard exports, with components, statuses, and the month plus trailing 3, 6 and 12-month windows. The month-close copy is the retained run (CTO-10) | With per-dataset watermarks (D2), a combined KPI needs its own stop month. One object per confidence level keeps a ratio of unconfirmed scope out of the revenue KPIs. The monthly value varies about 12×, so windows are needed | CRO (location); CFO (windows); CMO (month value, snapshot). I reverse my R2 position |
| D12 | Size and truncation (BRZ-02) | An empty file rejects. Per-dataset ceilings (50 / 5 / 1 MB, versioned) quarantine. There is no size floor. Truncation becomes a silver test: any key of the previous accepted snapshot that is missing from the new one rejects the file (CDO-06) | 100 MB is 77× the largest file. Losing a whole month shrinks Transactions by only 2.9%, so a 50% floor misses it (CRO). The key test catches it exactly and covers the CRO's row-count check | CTO (ceilings), CFO (a missing key rejects), CRO (the floor is dropped) |
| D13 | Object names (BRZ-05) | A registry allowlist. Any other key is quarantined unread. The verbatim key goes into the manifest and is never interpolated into a path | A key with `..` or control bytes must never reach path-building code. The 3 registered keys contain no character outside `[A-Za-z0-9_./-]` except `&` | CTO |
| D14 | Content-Type (BRZ-01) | A mismatch only flags. The byte checks stay in CDO-01 | The uploader sets Content-Type, so it is a claim, not evidence. A CLI upload without it would otherwise reject a valid file | CTO |
| D15 | Name of the negative-spend flag (SB-10) | `is_negative_spend`, nature unconfirmed | A flag must state what is observed. "Adjustment" asserts a meaning no owner has given (Q3). The 0.05-grid evidence points to a budget plug as much as to an adjustment | CFO |
| D16 | Export escaping onFailure (CTO-09) | Escaping is the transform, and escaped cells are counted in the export log. An export that cannot type its columns or apply the escape fails. Typed numbers are never escaped | Escaping a cell is not a failure; being unable to escape is. All five agree on the numeric exemption | CTO (fail closed), CFO (escape rather than reject a cell), CMO (counted) |
| D17 | Outlier details (SB-08) | Recomputed every run. A customer needs at least 3 positive payments. Owner overrides are allowed. A change in the flagged set is logged and alerts Data, with no frozen list. All-in figures are primary, and an ex-outlier figure states how many customers it excludes and the rule version | The set is {94, 322} at all 4 cuts tested (2023-01 → 2024-10), so recomputing does not flap. 5 customers at ≥ 10× have only 1–3 payments. A median needs at least 3 values before a single spike cannot set it, while a minimum of 6 would leave a large new account in the ex-outlier series for 5 months | CDO. CRO on the minimum and overrides (3, not 6); CTO on the alert; CFO on all-in being primary |
| D18 | Churn at the cutoff (SB-05, CDO-07) | `churn_confirmed_through` = `as_of_month` − 2. Churn counts after it are NULL, `grace` and `is_provisional` stay, and retention after it is provisional | Churn events for Jun–Oct 2024 are 15, 18, 14, 0, 0: a churn dated to month m is observable only from m+2. Logo churn reads 7.7% at Oct-2024 against 9.9% at Aug-2024, with 25 base customers in grace | CRO; compatible with my CDO-07 |
| D19 | Snapshot retention | Month-close runs, and runs behind any figure shared outside Finance, RevOps and Data, are kept for the legal audit period, with no expiry until it is set. Other superseded runs may expire after 30 days. Bronze snapshots and manifests live at least as long as the runs that read them | A board figure must be reproducible next year, and a run is under 1 MB | CFO (published runs), CTO (everything else) |

**Unresolved disagreements:** none (`cdo_rules.md`, "Unresolved disagreements"). The 10 flag rules depend on owner answers, not on disagreement between executives. The only new open items are the CTO's build-level points A1–A9 (§5.4).

## 2. Final rules (from `round3/cdo_rules.md`, verbatim)

**61 rules:** bronze 11, silver quality 15, silver business 17, gold 18. **51 keep, 10 flag.**

### 2.0 onFailure and status semantics

| Action | What happens | Where it goes | Downstream |
|---|---|---|---|
| reject (file) | The file is not accepted. A reject record holds the rule id, the reason and the offending line numbers. Data and the dataset owner are alerted | `_rejected/<dataset>/` with its manifest; readable by Data | That dataset stays at its previous accepted snapshot. The other datasets still advance, and the previous published run stays live |
| reject (run / export) | The run, or the export, fails as a whole | The run or export report | Nothing new is published. The previous published run stays live |
| quarantine (row) | The row is held out of silver with its rule id and reason, and it is counted in the reconciliation | Silver `_quarantine/`; readable by Data | The rest of the file continues |
| quarantine (file) | The pipeline does not read the file. It is released only by a recorded override (approver, reason). Quarantined bytes are never edited | Bronze `_quarantine/` with its manifest. Readable only by the security role, plus the CDO for a schema change | That dataset stays at its previous accepted snapshot. The other datasets still advance |
| flag | The data passes unchanged. The hit is recorded in a flag or reason column (silver, gold) or in the manifest (bronze), and it is counted in the run report. "Alerts" means it also notifies the named team. A KPI set to NULL by a rule is a flagged value inside an atomic publish, not a partial publish | In place | Continues |

- **Gold object rules:** onFailure applies when the built object breaks its stated grain, keys or contents.
- **Inferred = true:** the rule asserts a meaning or expectation that no owner has stated, so it comes from the data.
- **Inferred = false:** the rule implements an owner definition (SB-01, SB-02) or is a control. Controls cover security, format, reconciliation, lineage, access and publishing, plus status columns that record that an owner has not answered.
- An inferred rule stays marked until the owner's statement is recorded verbatim in `owner_definitions.md`.

**Status:**
- **keep:** final. Build it as written.
- **flag:** final, and built as written now, but a named owner answer (Q#) is expected to change its text, parameters or onFailure. It is revisited when that answer is recorded.
- An owner answer that only replaces a value in versioned config (factors, mappings, currency, basis or scope statuses) does not by itself make a rule flag.
- **(changed in R3):** the meaning, onFailure or scope differs from the §2 draft. Merging §2's quoted fragments into one text without changing their meaning is not marked.

### 2.1 Bronze

| ID | Dataset | Rule | Evidence | onFailure | Inferred | Status | Proposed by |
|---|---|---|---|---|---|---|---|
| BRZ-01 | all | The object's Content-Type must be `text/csv`; a `charset` parameter is allowed. A different value is recorded in the manifest and flagged; it never decides whether the file is accepted. Whether the bytes are CSV text is decided by the strict byte and field-count check | All 3 staging objects are `text/csv; charset=utf-8` (verified 2026-11-15). The uploader sets Content-Type, so it is a claim, not evidence | flag | false | keep | Baseline; CTO (changed in R3) |
| BRZ-02 | all | A 0-byte file is rejected. A file above its dataset's size ceiling is quarantined unread; the ceilings are versioned parameters: transactions 50 MB, industry 5 MB, sm_spend 1 MB. Size is not used to detect truncation, which is tested in silver against the previous accepted snapshot | The files are 1,302,387, 49,402 and 2,063 bytes. Losing a whole month shrinks Transactions by only 2.9% (1 of 34 months) | reject (empty); quarantine (file, oversize) | false | keep | Baseline; CTO, CFO, CRO (changed in R3) |
| BRZ-03 | all | Every staging object is malware-scanned before it is read. The pipeline proceeds only on `NO_THREATS_FOUND`; any other status quarantines the file. The staging policy denies `GetObject` on `THREATS_FOUND` objects to every role except the security role | Every upload is untrusted. Test with EICAR | quarantine (file) | false | keep | Baseline; CTO |
| BRZ-04 | all | A cell that starts with `=`, `+`, `-`, `@`, TAB or CR is a formula-injection hit, unless the whole cell matches `^-?\$?\d+(\.\d+)?$`. Any hit quarantines the file, because no column holds free text. Hits and exempt cells are counted in the manifest. Bronze never alters a value; escaping happens only at export | 5 cells start with `-` today, all `-$0.0xx` in PayrollExpenses, so there are 0 hits after the exemption | quarantine (file) | false | keep | Baseline; CDO, CTO |
| BRZ-05 | all | Only the object keys registered for a dataset are ingested: `transactions/Transactions.csv`, `industry/Industry.csv` and `s_and_m/S&M_spend.csv`. Any other key is quarantined unread, as is any key that has `..`, `//`, a leading `/`, control characters or non-ASCII characters, or is longer than 1,024 bytes. The `&` in the registered S&M key is allowed. The source key is stored verbatim in the manifest and is never interpolated into a path, query or command | Apart from `&`, the 3 keys use only `[A-Za-z0-9_./-]`. S3 events deliver the S&M key as `S%26M_spend.csv` | quarantine (file) | false | keep | Baseline; CTO (changed in R3) |
| BRZ-06 | all | The bronze object is the staging records plus `_ingested_at` as the last column, with one ISO-8601 UTC value ending in `Z` per load. It keeps the BOM-bearing header, every value as its original string, the row order, the line terminators and the empty record. Test: dropping `_ingested_at` reproduces the staging object exactly | Layer contract | reject | false | keep | Baseline; CDO |
| CDO-01 | all | The bytes are strict UTF-8; a leading BOM is allowed. There is no NUL, TAB or other C0 control byte, except CR and LF as line terminators. Every line has the header's field count | 0 control bytes and 0 TABs; the field counts are constant (3, 2 and 8) | reject | false | keep | CDO; CTO (changed in R3) |
| CDO-02 | all | Schema and PII gate: the header must equal the dataset's columns in a versioned registry (name, order and case). A new, missing, renamed or reordered column quarantines the file until the CDO classifies the change, including whether it carries PII, and the registry version is bumped. The "no PII" verdict covers only the 13 registered columns | All 3 headers match. 0 emails, 0 runs of 7+ digits, no names | quarantine (file, pending CDO classification) | false | keep | CDO |
| CTO-01 | all | Lossless append: with the last field removed from every line, the bronze object equals the staging object byte for byte, with the same SHA-256. It is tested on every run, before anything is published | 0 quotes or embedded commas, CRLF only, and a BOM with no final newline in all 3 files | reject | false | keep | CTO |
| CTO-02 | all | There is one write-once manifest per distinct file content delivered to staging, whether accepted, rejected or quarantined. It is stored at `_manifests/<dataset>/<sha256>.json` and written with `If-None-Match: *`. It holds the verbatim source key, VersionId (null while versioning is off), size, ETag, the SHA-256 of the bytes read, staging LastModified, the malware-scan status, the row count, Decimal control totals computed from the raw strings with a count of unparseable cells, every bronze check's hits, `_ingested_at`, `run_id`, `_rules_version`, and the outcome with its rule id. If the bytes read differ from the bytes that were scanned, or from a checksum S3 holds for the object, the file is quarantined for the security role and not loaded. If the manifest cannot be written, the load is rejected | VersionId is `null`, and no checksum is stored on any staging object (verified 2026-11-15). The ETag equals the MD5 only for single-part SSE-S3 uploads | quarantine (file) on a checksum mismatch; reject if the manifest cannot be written | false | keep | CTO; CFO, CDO (changed in R3) |
| CTO-03 | all | `_ingested_at` takes one value per bronze object: ISO-8601 UTC with `Z`, set at the first successful ingest of a given (dataset, SHA-256 of the staging bytes). Re-delivering bytes already ingested creates no new bronze object and no new `_ingested_at`. If those bytes are not the dataset's current snapshot, the existing snapshot becomes current again and the event is logged. VersionId is recorded but is never the idempotency key | VersionId is `null` on all 3 staging objects, and versioning was never enabled. A VersionId key would turn a corrected re-upload under the same key into a no-op | reject | false | keep | CTO; CDO, CRO (changed in R3) |

Not applicable (baseline, uncontested): macros, zip bombs and PII masking in bronze.

### 2.2 Silver: quality rules

| ID | Dataset | Rule | Evidence | onFailure | Inferred | Status | Proposed by |
|---|---|---|---|---|---|---|---|
| SQ-01 | all | Read as UTF-8, strip the BOM, comma-delimited, header required. CRLF line endings and a missing final newline are tolerated. Numbers are parsed from their strings as exact decimals, never as floats | BOM, comma delimiter and header in all 3 files; none ends with a newline | reject (file) | false | keep | Baseline; CTO |
| SQ-02 | all | A record whose source columns are all empty (ignoring `_ingested_at`) goes to row quarantine with reason `EMPTY_RECORD`. Exactly one is expected, as the last record of industry, and none in the other datasets. Any other count or position is flagged and alerts Data | Industry has 1 trailing `,` record (1,962 = 1,961 + 1). Transactions and S&M have none | quarantine (row); flag (unexpected count or position) | false | keep | Baseline; CDO, CTO (changed in R3) |
| SQ-03 | industry | `ID` is not null, matches `^Cliente [1-9]\d*$`, and yields an integer `customer_id`. A row that fails goes to row quarantine. A duplicate derived `customer_id` rejects the file | 1,961 unique IDs. `^Cliente \d+$` would let `Cliente 094` collide with 94 | quarantine (row); reject (file) on a duplicate | false | keep | Baseline; CDO |
| SQ-04 | industry | `Industria` is normalized to Unicode NFC, then mapped to one of the 6 registered values and its ASCII code (Restaurantes, Producción, Retail, Tecnología, Servicios profesionales, Salud). A value outside the list loads as industry `UNMAPPED`, is flagged and alerts Data. A row is never quarantined for its industry value | 6 values, 0 variants, all NFC. An NFD `Producción` would become an invisible 7th value | flag (and alert) | true | keep | Baseline; CDO, CMO |
| SQ-05 | transactions | `ID` is a positive integer, and (`ID`, `month`) is unique. A non-integer ID or any duplicate key rejects the file; the reject record lists the offending lines | 0 duplicates today. A duplicate double-counts revenue and has no true amount | reject (file) | false | keep | Baseline; CDO, CFO, CTO (changed in R3) |
| SQ-06 | transactions | `month` is a non-padded month/day/year date (Python `%m/%d/%Y`; Spark and Athena `M/d/yyyy`) that falls on the last day of its month. It is converted to a year-month. Any failure rejects the file | 100% are non-padded month-ends. `MM/dd/yyyy` fails in Spark and Athena. Quarantining the row would drop its revenue and break the dense panel | reject (file) | false | keep | Baseline; CDO (changed in R3) |
| SQ-07 | transactions | (a) `amount` must parse as an exact decimal. A value that does not rejects the file, and no NULL or 0 is ever substituted. (b) A negative amount is kept, flagged with `is_negative_amount`, and stays in every sum; it is not a paying month | Min 0, 0 negatives and 0 unparseable values today. The owners do not state that there are no refunds | (a) reject (file); (b) flag | (a) false; (b) true | keep | Baseline; CDO, CFO, CTO (changed in R3) |
| SQ-08 | transactions | The delivery is a dense panel: every customer ID in the file has exactly one row for every month from the file's earliest to its latest month. A missing customer-month rejects the file. An amount is never imputed, as 0 or as anything else, and an unknown month never counts as a zero month in any lifecycle rule | 66,674 = 1,961 × 34. Zero months are explicit (50.6% of rows), so a missing row is an extract defect, not a zero | reject (file) | true | flag (Q8) | Baseline; CDO, CRO (changed in R3) |
| SQ-09 | sm_spend | (a) `Month` matches `YYYY-MM` and is unique; otherwise the file is rejected. (b) A missing month between the earliest and the latest month is flagged; it stays absent and is never zero-filled | 34 unique, contiguous months | (a) reject (file); (b) flag | (a) false; (b) true | keep | Baseline; CDO, CMO |
| SQ-10 | sm_spend | Every spend cell matches `^-?\$\d{1,6}\.\d{3}$`. The `$` is stripped and the sign is kept. Any cell that does not match rejects the file | 238 of 238 cells conform, 5 of them negative. `$d.ddd` would fail at values ≥ 10 | reject (file) | false | keep | Baseline; CDO |
| SQ-12 | cross | A Transactions customer with no Industry row gets industry `UNKNOWN` and is flagged. An Industry customer with no revenue is kept in `dim_customer`. A lookup never quarantines or drops revenue | 100% match in both directions today | flag | false | keep | Baseline; all five |
| SQ-13 | cross | Transactions and S&M are expected to cover the same months. A month present in one dataset and absent from the other is flagged, and every KPI that combines revenue and spend is NULL for that month | Both cover 2022-01 → 2024-10 | flag | true | keep | Baseline; CDO (changed in R3) |
| CDO-04 | all | Exact DECIMAL reconciliation on every run. Per file and per month: rows and Σ native amount in bronze = silver + row quarantine. From silver to gold the same identity holds per month and per month × industry, and Σ by industry = Σ by month. Logo identity in gold: customers with `cohort_censoring` = left, probable_left or none, plus Industry customers with no revenue, add up to the rows of `dim_customer`; and count(`lifecycle_state` = new) = count(`cohort_censoring` = none). Control totals come from the manifest, never from documentation. Any break rejects the run | 66,674 rows, Σ 221,441.504508 (full: 2,214,415,045.08). S&M 238 cells, Σ 77.818. Industry 1,962 = 1,961 + 1. Logos 377 + 43 + 1,541 + 0 = 1,961; count(new) = 1,541 | reject (run) | false | keep | CDO; CFO, CRO, CTO, CMO (changed in R3) |
| CDO-05 | transactions, sm_spend | Money is DECIMAL, never float: `amount` DECIMAL(12,6) → `amount_value` DECIMAL(18,2); spend DECIMAL(12,3) → `spend_value` DECIMAL(18,0). Nothing is ever rounded or truncated. A native value with more decimals than its registered scale (6 for amount, 3 for spend), or a value that overflows its type, rejects the file | All 66,674 amounts have ≤ 6 decimals, so ≤ 2 after × 10,000, and every spend value × 1e8 is an integer. Floats give a wrong full amount on 2,436 rows and on 32 of 238 cells | reject (file) | false | keep | CDO; CTO, CFO (changed in R3) |
| CDO-06 | all | Each delivery is treated as a full snapshot. Silver is rebuilt from the latest accepted snapshot and diffed against the previous accepted snapshot of the same dataset. A key present in the previous snapshot and absent from the new one rejects the file as truncation or removed history; the keys are a Transactions customer-month, an Industry customer or an S&M month. A changed value is kept, flagged and written to the run's restatement log, which alerts Finance when the value falls in a month already published | The files hold the full history. The owners have not said whether deliveries are full or incremental, or whether closed months can change | reject (file) on a removed key; flag on a changed value | true | flag (Q8) | CDO; CTO, CFO, CMO, CRO (changed in R3) |

### 2.3 Silver: business rules

| ID | Dataset | Rule | Evidence | onFailure | Inferred | Status | Proposed by |
|---|---|---|---|---|---|---|---|
| SB-01 | transactions | `amount_value = amount × 10,000`, computed in exact decimal arithmetic | Owner definition (25 → 250,000). Every full amount has cent precision, which corroborates it | reject | false | keep | Baseline (owner) |
| SB-02 | sm_spend | `spend_value = value × 100,000,000`, computed in exact decimal arithmetic, with the sign kept | Owner definition (1.04 → 104,000,000). Every scaled value is an integer | reject | false | keep | Baseline (owner) |
| SB-03 | transactions | A customer is paying in a month when `amount` > 0. A zero or negative month is unpaid | 50.6% of rows are zero; the minimum positive amount is 0.14 | flag | true | keep | Baseline (changed in R3) |
| SB-04 | transactions | `cohort_month` is the customer's first paid month. `first_payment_ratio` = first paid amount ÷ next paid amount, where the next paid month is the second paid month at any distance (NULL when there is a single payment). `first_payment_multiple` j is the integer in {2, 3} with abs(ratio − j) ≤ 0.05 × j, else NULL. `implied_start_month` = `cohort_month` − (j − 1) months. `cohort_censoring` is `left` when `cohort_month` is the snapshot's earliest month (2022-01 today), `probable_left` when `implied_start_month` ≤ that month, and `none` otherwise. The cohort stays the first paid month, and only `none` is a new logo | 377 left, 43 probable_left (40 Feb, 3 Mar), 1,541 none; Feb-2022 has 68 new logos. 3× first payments: Feb-2022 has 6 of 108 against 0.9 expected (Poisson p = 0.0003), and Mar-2022 has 3 of 30 against 0.25 (p = 0.002). With j = 2 only, the counts are 34 and 1,550 | flag | true | flag (Q7) | Baseline; CDO, CMO (changed in R3) |
| SB-05 | transactions | A churn spell is an unsettled run of at least 3 consecutive unpaid months after the first paid month. It is either internal (ended by a payment that does not settle it) or trailing (still open at `as_of_month`). The churn event is dated to the spell's first unpaid month. A trailing run of 1–2 unpaid months at `as_of_month` is `grace`, not churn. A settlement found later (arrears, prepayment or split) restates the spell as a settled gap. `churn_confirmed_through` = `as_of_month` − 2 months, and churn counts for later months are NULL, never 0. The 3-month threshold is a versioned parameter | The return hazard is 43.9% after 1 zero month and 7.7% after 3 (CRO). Churn events for Jun–Oct 2024 are 15, 18, 14, 0, 0, and the last two cannot be observed yet. 46 customers are in grace | flag | true | flag (Q5) | Baseline; CDO, CRO (changed in R3) |
| SB-06 | transactions | A gap is a run of k ≥ 1 unpaid months between paid months p (the last paid month before it) and q (the first paid month after it). x_m is the native amount in month m, and p−1 is the calendar month before p. "a ≈ b" means abs(a − b) ≤ 0.05 × b. The tests run in this order, and the first match settles the gap: (1) arrears: x_q ≈ (k+1)·x_p; (2) prepayment: x_{p−1} > 0, x_p ≈ (k+1)·x_{p−1} and x_q ≈ x_{p−1}; (3) split: x_{p−1} > 0 and x_p + x_q ≈ (k+2)·x_{p−1}. A settled gap gets `settlement_type` (arrears, prepay or split) and `settlement_confidence` (high for arrears and prepay, low for split). Both are set on the gap's unpaid months and on its settling payment months: q for arrears, p for prepayment, and both p and q for split. `is_catch_up` marks q of an arrears gap, and `is_prepaid` marks p of a prepaid gap. Amounts are never restated. The ±5% tolerance is a versioned parameter | 468 gaps: 155 arrears + 47 prepay + 9 split = 211 settled (45.1%), 202 of them high-confidence. Arrears and prepay never both match. Split matches 178 gaps, and 169 of those also match arrears or prepay. ±5% sits on a plateau: 152–163 settled from ±2% to ±10% (CRO) | flag | true | flag (Q5, Q2) | Baseline; CDO, CRO, CFO, CTO (changed in R3) |
| SB-07 | transactions | Reactivation is the first paid month that ends an internal churn spell. That month is `reactivated`, never a new logo, and the customer keeps its cohort. An unsettled internal gap of 1–2 unpaid months is `paused`, and the payment that ends it is not a reactivation | 64 reactivations (60 customers), against 313 under the baseline text; 193 paused gaps | flag | true | keep | Baseline; CDO (changed in R3) |
| SB-08 | transactions | `is_outlier_customer` is true when the customer has at least 3 positive amounts and the median of its positive `amount` is ≥ 25 × the portfolio median positive `amount` (taken over all positive customer-months). Both medians are computed at `as_of_month`, and 25 and 3 are versioned parameters. An owner may add or remove a customer through a recorded owner statement, kept in versioned config and marked `outlier_source` = owner (otherwise rule). Outliers are never removed. Every average is published all-in (the primary figure) and ex-outliers, and an ex-outlier figure states how many customers it excludes and the rule version. A change in the flagged set from the previous published run is written to the restatement log and alerts Data | Flags 94 (60.0×, 31 payments) and 322 (31.7×, 25 payments). The next is 543, at 18.6× with 1 payment, and 5 customers at ≥ 10× have only 1–3 payments. The flagged set is {94, 322} at as_of 2023-01, 2023-10, 2024-04 and 2024-10. The portfolio median is 5.25 | flag | true | keep | Baseline; CRO, CDO, CFO, CTO (changed in R3) |
| SB-09 | industry | Industry is fixed per customer (SCD type 1) and applies to the customer's whole history | The file has no effective dates | flag | true | flag (Q6) | Baseline |
| SB-10 | sm_spend | Spend keeps its sign as received; it is never made absolute, clipped, floored or reclassified. A negative cell gets `is_negative_spend` = true, and its nature is unconfirmed: an adjustment and a budget plug are both possible. A negative in any category other than PayrollExpenses also alerts Finance and Data. Monthly totals are the exact sum of the 7 categories, negatives included | 5 negative PayrollExpenses months, −13,500,000 in total. In 2023-11 and 2024-07, clipping to 0 would push the total off its 0.05 grid (CFO) | flag | true | keep | Baseline; CDO, CFO (changed in R3) |
| CDO-07 | transactions | Exactly one `lifecycle_state` per customer-month: `pre_acquisition` (before the first paid month); `new` (the first paid month of a customer whose `cohort_censoring` is none); `paying` (any other paid month that is not `reactivated`, including the first paid month of a left or probable_left customer); `reactivated`; `settled_gap` (an unpaid month inside a settled gap); `paused` (an unpaid month inside an unsettled internal gap of 1–2 months); `churned` (an unpaid month inside a churn spell); `grace` (an unpaid month in a trailing run of 1–2 unpaid months at `as_of_month`). `is_provisional` is true on every row from the customer's last paid month through `as_of_month`. A row with no state, or with more than one, fails the build | 66,674 rows: paying 31,366; pre_acquisition 29,321; churned 3,811; new 1,541; settled_gap 281; paused 231; reactivated 64; grace 59 (46 customers). 5,399 rows are provisional. The CTO reproduced the model exactly | reject (run) | true | keep | CDO; CRO, CTO (changed in R3) |
| CDO-08 | cross | Unit tripwire: for each month present in both datasets, ratio = S&M full ÷ revenue full. A ratio outside [0.5, 20] (versioned parameters) is flagged with reason `unit_tripwire` and alerts Data and Finance. While it fires, every KPI that combines revenue and spend is NULL for that month and for every trailing window that contains it | The ratio is 1.61–7.62× today. An S&M file off by ×10 or ÷10 trips in 28 or 21 of 34 months with [0.5, 20], and in none with [0.01, 100]. Mixing native values gives about 0.00035× | flag | true | flag (Q1) | CDO; CFO (changed in R3) |
| CFO-03 | transactions, sm_spend | One `dim_source_status` row per money dataset, with: `currency_code` NULL (an ISO 4217 code once an owner states the currency); `currency_status` = 'unconfirmed'; `revenue_basis_status` or `spend_basis_status` = 'unconfirmed'; and `basis_hint` ('cash-like' for revenue, 'budget-like' for spend). Facts carry its key, and every KPI view exposes these columns. The values change only through a recorded owner answer | The owners state neither the currency nor the basis. Settled gaps suggest cash-like revenue; round 0.05 totals suggest budget-like spend | flag | false (statuses); true (`basis_hint`) | keep | CFO; CDO, CMO |
| CFO-05 | cross | `scope_status` = 'unconfirmed' on every KPI that combines revenue and spend, until a recorded owner answer says Transactions covers the customer base that the S&M spend acquires and serves. The S&M ÷ revenue ratio is published as evidence and never sets the status | S&M is 5.75× / 3.21× / 2.30× revenue (2022 / 2023 / Jan–Oct 2024) | flag | false | keep | CFO; CDO (changed in R3) |
| CRO-03 | transactions | `amount_normalized` spreads each settled gap's settling amount evenly over the months it covers: for arrears, x_q over p+1 … q; for prepayment, x_p over p … q−1; for split, x_p + x_q over p … q. Shares are truncated to 6 native decimals, and the remainder goes to the payment month (q for arrears and split, p for prepayment), so Σ `amount_normalized` = Σ `amount` per customer exactly. Every other month equals `amount`, and `amount` itself never changes. The column is analytical only: it is never a revenue total and never drives `is_paying`, new logos or the first paid amount | The Σ identity holds for all 1,961 customers. The 2022 month-on-month stdev is 11.7% normalized vs 15.4% raw (CRO) | flag | true | keep | CRO; CDO, CFO, CMO, CTO (changed in R3) |
| CRO-05 | transactions | Δ = `amount_normalized`(t) − `amount_normalized`(t−1), computed only when `lifecycle_state` is `paying` in both t and t−1. `expansion_amount` = max(Δ, 0) and `contraction_amount` = max(−Δ, 0); otherwise both are 0. `amount_lag12` = `amount_normalized`(t−12). They are labelled a movement proxy, because a change may come from price, tax, FX or a plan change | 91.7% of consecutive paid months are unchanged. Expansion is 2.36% and contraction 2.37% of prior revenue (CRO). The 0.21 price grid is unexplained | flag | true | flag (Q2) | CRO; CDO, CTO, CFO (changed in R3) |
| CRO-07 | transactions | `is_first_month_spike` = `first_payment_ratio` ≥ 1.9, and `first_payment_band` is '<1.9', '1.9–3' or '≥3'; both live on `dim_customer`. They are descriptive: they never remove a logo or change a cohort. A cohort's starting ARPA is the median, over its new logos, of the first paid amount ÷ `first_payment_multiple` when that multiple is 2 or 3, and of the first paid amount otherwise | 116 of 1,470 new logos with a second payment are at ≥ 1.9×, and 64 at ≥ 3×. The median starting ARPA is 42,000 (full amount) | flag | true | keep | CRO; CDO, CMO (changed in R3) |

### 2.4 Gold

| ID | Object / dataset | Rule | Evidence | onFailure | Inferred | Status | Proposed by |
|---|---|---|---|---|---|---|---|
| GLD-01 | `dim_month` (grain: month; key `month_key` = YYYYMM) | A generated calendar that covers every month of the accepted snapshots: month → quarter → year, plus `month_index` and `is_window_start`. It role-plays as the cohort month and the implied start month | 34 contiguous months (2022-01 → 2024-10) | reject (run) | false | keep | Baseline; CTO, CRO (changed in R3) |
| GLD-02 | `dim_industry` (grain: industry; key `industry_key`) | ASCII code, Spanish label as stored and English label. Two extra members: −1 UNKNOWN (no Industry row) and −2 UNMAPPED (a value outside the domain), both shown as "Unknown" in charts. The codes and English labels are inferred conventions | 6 values: RESTAURANTS 529, MANUFACTURING 454, RETAIL 428, TECHNOLOGY 241, PROFESSIONAL_SERVICES 165, HEALTHCARE 144 | reject (run) | true (codes and labels) | keep | Baseline; CDO, CTO, CMO (changed in R3) |
| GLD-03 | `dim_customer` (grain: customer; key `customer_id`; SCD type 1) | `customer_label` (`Cliente N`), `industry_key`, `cohort_month_key`, `cohort_censoring`, `is_new_logo` (`cohort_censoring` = none), `first_payment_ratio`, `first_payment_multiple`, `implied_start_month_key`, `first_payment_band`, `is_first_month_spike`, `first_paid_amount_value`, `last_paid_month_key`, `is_outlier_customer` and `outlier_source`. An Industry customer with no revenue is kept with NULL cohort attributes. There is no unknown customer member, because every fact's customer comes from the same snapshot. Cohort attributes are recomputed on every run | 1,961 rows. A new month can restate cohort attributes | reject (run) | true (cohort attributes) | keep | Baseline; CDO, CRO, CMO, CTO (changed in R3) |
| GLD-04 | `dim_spend_category` (grain: S&M source column; key `category_key`) | One row per registered column: PaidMedia, Travel, PublicidadNoWeb, Freelance, SoftwareTools, Team and PayrollExpenses. Two hierarchies come from a versioned seed: `spend_group` (media = PaidMedia, PublicidadNoWeb; people = Team, PayrollExpenses, Freelance; other = Travel, SoftwareTools) and `channel_class` (digital_paid = PaidMedia; offline = PublicidadNoWeb; non_media = the rest). `is_hr_sensitive` is true for Team, PayrollExpenses and Freelance. A registered column without a seed row loads as −2 UNMAPPED and is flagged. Both hierarchies are inferred | The meanings are inferred from the names. Media is 59.3% of spend, people 30.0% and other 10.7%. The CMO accepts media = PaidMedia + PublicidadNoWeb as a working mapping | flag | true | keep | Baseline; CDO, CMO (changed in R3) |
| GLD-05 | `fct_customer_month_revenue` (grain: customer × month; key (`customer_id`, `month_key`)) | Every row of the dense panel, zero months included, with: `amount` DECIMAL(12,6); `amount_value` DECIMAL(18,2); `amount_normalized` and its full value; `is_paying` and `is_negative_amount`; `lifecycle_state` and `is_provisional`; `settlement_type`, `settlement_confidence`, `is_catch_up` and `is_prepaid`; `expansion_amount`, `contraction_amount` and `amount_lag12`; the keys of `dim_customer`, `dim_month` and `dim_source_status`; and the lineage columns. Measures are additive, and no ratio is stored | 66,674 rows today | reject (run) | true (states and flags) | keep | Baseline; CDO, CRO, CFO (changed in R3) |
| GLD-06 | `fct_sm_spend_month` (grain: month × category; key (`month_key`, `category_key`)) | S&M reshaped to one row per month and category, with signed native spend DECIMAL(12,3), `spend_value` DECIMAL(18,0), `is_negative_spend`, the key of `dim_source_status` and the lineage columns. Its only dimensions are `dim_month` and `dim_spend_category` | 238 rows (34 × 7), 5 of them negative | reject (run) | false | keep | Baseline; CFO, CMO (changed in R3) |
| GLD-07 | `agg_month_kpis` (grain: month; key `month_key`; a view) | Built only from `fct_customer_month_revenue` and its dimensions; it holds no spend measure. Columns: revenue at full amount (all-in and ex-outlier); paying customers; ARPPU (all-in mean, median, ex-outlier and normalized); new logos (`cohort_censoring` = none) and `new_logos_probable_left`; reactivated, paused, grace and churned customers, with churn dated to the spell's first unpaid month; top-1 and top-10 revenue shares; `revenue_basis_status`, `currency_status`, `churn_confirmed_through` and `is_provisional`. It runs to `revenue_complete_through`. Churn counts after `churn_confirmed_through` are NULL, and 2022-01 has NULL new-logo counts | Top-1 share 4.77% (customer 94), top-10 10.83%. Without the NULL, churn events for Sep and Oct 2024 would read 0 | flag (NULL with reason) | true | keep | Baseline; CDO, CRO, CFO, CMO (changed in R3) |
| CMO-05 | `agg_month_sm_spend_per_new_logo` (grain: month; key `month_key`; a view) | Spend meets revenue only through `dim_month`. Columns: S&M at full amount, total and media-only (`spend_group` = media); new logos (`cohort_censoring` = none) and `new_logos_probable_left`; and `sm_spend_per_new_logo` = Σ S&M ÷ Σ new logos, total and media-only, for the month and for trailing 3, 6 and 12-month windows. A value is NULL when its window includes 2022-01, extends past `data_complete_through`, contains a month where the unit tripwire fires or a month missing from either dataset, or has 0 new logos. Every row carries `scope_status`, `spend_basis_status`, `currency_status` and the S&M ÷ revenue ratio. No column is named CAC, and there is no payback or LTV column. The view is not part of any standard export, and any extract of it keeps the status columns | Feb-22–Oct-24: 7,581.8M ÷ 1,541 = 4,920,052 per new logo, against a 42,000 median first payment. The monthly value varies about 12×. Scope is unconfirmed | flag (NULL with reason) | true | flag (Q4, Q1, Q3) | CMO; CFO, CDO, CRO (changed in R3) |
| CRO-06 | `agg_retention_month` (grain: month t × industry × cohort year × `is_outlier_customer`; a view over the revenue fact) | Additive components on point-in-time `amount_normalized`. The base is the customers whose state at t−12 is new, paying, reactivated or settled_gap. Components: base logos and base revenue; those customers' revenue at t; retained revenue Σ min(x_t, x_{t−12}); expansion and contraction; lost revenue (base customers at 0 at t), split into churned (state `churned` at t) and other (paused or grace); retained and churned logos. NRR = revenue at t ÷ base revenue; GRR = retained revenue ÷ base revenue; logo churn = churned logos ÷ base logos. The same components on raw `amount` (`_raw`) and on the 3-month average of `amount_normalized` (`_avg3`) are published as named variants, never as the headline. Months without a 12-month lookback have no value. After `churn_confirmed_through`, logo churn is NULL, and NRR and GRR carry `is_provisional` = true. Nothing here is labelled MRR or ARR while the revenue basis is unconfirmed | Aug-2023 NRR is 79.8% raw vs 88.9% normalized, because customer 94's 3× catch-up sits in the Aug-2022 base (ex-94: 86.7% vs 86.6%). Normalized minus raw ranges from −0.8 to +9.0 points. Oct-2024 NRR / GRR: normalized 92.9% / 85.9%, raw 93.2% / 85.8%, 3-month average 96.2% / 87.3%. Aug-2024, the last final month: 91.4% / 86.5% | flag (NULL with reason) | true | flag (Q2) | CRO; CDO, CFO (changed in R3) |
| CDO-10 | sm_spend | Spend is never allocated below company × month × category. No table or view holds a spend measure together with a customer, industry or cohort key, and `dim_month` and `dim_spend_category` are the only dimensions joined to spend. Spend by `channel_class` is a roll-up of categories, not an attribution of customers to channels. The ban lifts only for an allocation key that the owners approve in writing. A CI test on the table and view definitions enforces it | S&M has no customer, industry or channel key. Within each spend regime, the correlation between spend and new logos is about 0 (CMO) | reject (run) | false | keep | CDO, CMO; CFO (changed in R3) |
| CDO-11 | all | (1) Customer-level data (every silver table, `dim_customer`, `fct_customer_month_revenue` and any view at customer grain) is Confidential-Financial pseudonymised personal data. Only named Finance, RevOps (including the Revenue and Customer Success leaders) and Data roles may read it. (2) Team, PayrollExpenses and Freelance are HR-sensitive: at category grain only Finance may read them. Their `spend_group` total and the other categories may be shared. (3) Any aggregate shared with a role outside (1) suppresses every monetary measure in a cell built from fewer than 5 customers (the value is NULL, with `is_suppressed` = true). Complementary suppression ensures that no suppressed value can be recovered from totals in the same share. Customer and logo counts are not suppressed; they carry `low_n` instead. (4) The top-1 and top-10 revenue shares are exempt from (3) for the board and auditors, and are shown without customer IDs outside (1). (5) No role outside (1) is granted gold access until the suppressed shares exist. The thresholds are versioned parameters | `Cliente N` is a reversible pseudonym, and an SMB may be a sole trader. Industry × month revenue cells have ≥ 23 payers, so none is suppressed. 1,307 of 3,382 industry × cohort-month × month cells have fewer than 5 customers, as do 64 of 198 new-logo industry × month cells | flag (cell suppressed) | false | keep | CDO; CMO, CFO, CRO, CTO (changed in R3) |
| CMO-07 | agg | Every rate or average published at industry or cohort grain carries `low_n` = true when its denominator has fewer than 10 customers or new logos (a versioned parameter). Industry acquisition rates are reported by quarter by default | 141 of 198 industry × month new-logo cells are under 10, against 16 of 72 by quarter | flag | false | keep | CMO; CRO (changed in R3) |
| CMO-08 | `dim_month` | `sm_regime` (`pre_2023_06` / `post`) is a config-driven, inferred annotation of `dim_month` that no calculation uses | S&M fell 47.8% month on month in Jun-2023 (3.451 → 1.800), and Freelance has been 0 since 2023-05. The cause is unknown | flag | true | keep | CMO; CDO |
| CTO-06 | silver, gold | Every silver and gold row carries `_run_id`, `_source_key`, `_source_sha256`, `_ingested_at`, `_rules_version` (a hash of the rules file) and `as_of_month` | Bronze forbids extra columns, so lineage starts in silver. Adding one month restates 45 earlier rows | reject (run) | false | keep | CTO; CFO, CDO |
| CTO-07 | cross | Each money dataset has its own watermark: `revenue_complete_through` is the latest month of the accepted Transactions snapshot, and `spend_complete_through` the latest month of the accepted S&M snapshot. A KPI that uses one dataset runs to that dataset's watermark. A KPI that combines revenue and spend runs to `data_complete_through`, the earlier of the two. A late or rejected dataset is flagged and never holds back a KPI that does not use it. `as_of_month` for the lifecycle rules is `revenue_complete_through` | The same window today, but the files can arrive separately. A single minimum would stop every revenue KPI whenever S&M is late | flag | false | keep | CTO; CRO, CFO, CMO (changed in R3) |
| CTO-08 | all | Unknown members exist only where a lookup can fail. `dim_industry` has −1 UNKNOWN (no Industry row) and −2 UNMAPPED (a value outside the domain), and `dim_spend_category` has −2 UNMAPPED (a column without a mapping row). Facts are never dropped for a missing dimension row, and non-zero revenue or spend on such a member alerts Data. `dim_month` and `dim_customer` have no unknown member: a fact whose month or customer cannot be resolved fails the run | The baseline's orphan quarantine would have dropped revenue. There are 0 orphans today | flag (unknown member); reject (run) for an unresolved month or customer | false | keep | CTO; CDO, CFO (changed in R3) |
| CTO-09 | egress | Exports are produced from gold only. CSV and XLSX exports escape every text-typed cell that starts with `=`, `+`, `-`, `@`, TAB or CR by prefixing `'`, and count the escaped cells in the export log. Typed numeric and date columns are never escaped. An export that cannot type its columns or apply the escape fails | OWASP CSV injection. Escaping a typed number would turn `-0.016` into `'-0.016` | reject (export) | false | keep | CTO; CDO, CFO, CRO, CMO (changed in R3) |
| CTO-10 | silver, gold | Silver and gold are rebuilt in full, into a new `run_id=` prefix, from the latest accepted snapshot of each dataset, meaning one that passed every file-level check in bronze and silver. A run is published atomically, and only after every check passes; if it fails, the previous published run stays live. A file-level reject affects only its own dataset: the run uses that dataset's previous accepted snapshot, and the other datasets advance. Published runs are immutable. A run used for a month-close report, or for any figure shared outside the Finance, RevOps and Data roles, is kept for the audit retention period that legal sets, and never expires until that period is set. Other superseded runs may expire after 30 days. Bronze snapshots and manifests are kept at least as long as any retained run that read them | Lifecycle states change retroactively (one new month restates 45 rows), and the rebuild takes seconds. A board figure must be reproducible | reject (run) | false | keep | CTO; CDO, CFO, CRO, CMO (changed in R3) |

**Totals:**

| Layer | Rules | keep | flag |
|---|---|---|---|
| Bronze | 11 | 11 | 0 |
| Silver quality | 15 | 13 | 2 |
| Silver business | 17 | 11 | 6 |
| Gold | 18 | 16 | 2 |
| **All** | **61** | **51** | **10** |

### 2.5 Canonical metric definitions

| Metric | Canonical definition | Variants published | Owner status |
|---|---|---|---|
| Revenue | Σ `amount` × 10,000 per month, including settling payments. `amount_normalized` is never a revenue total | Ex-outlier | **Owner-backed** for the scale. The currency and the basis (invoiced, collected or recognized) are unconfirmed (Q1, Q2) |
| S&M spend | Σ of the 7 categories × 100,000,000 per month, signed | Media-only, people and other (inferred groups) | **Owner-backed** for the scale. The currency and actual vs budget are unconfirmed (Q1, Q3) |
| Paying | `amount` > 0 in the month. A zero or negative month is unpaid | — | Inferred |
| Active (retention base) | `lifecycle_state` is new, paying, reactivated or settled_gap | — | Inferred |
| Cohort and new logo | The cohort is the first paid month. A new logo is a customer with `cohort_censoring` = none, counted in its cohort month: 1,541 in total, 68 in Feb-2022, and NULL for 2022-01 | `new_logos_probable_left` (43). `first_payment_multiple` makes the j = 2 count (1,550) reproducible | Inferred (Q7) |
| Churned | An unsettled run of at least 3 unpaid months after the first paid month, dated to its first unpaid month. Confirmed through `as_of_month` − 2; later churn counts are NULL. 237 customers have an open trailing churn spell today | — | Inferred (Q5) |
| Grace | A trailing run of 1–2 unpaid months at `as_of_month`: neither active nor churned. 46 customers today | — | Inferred (Q5) |
| Paused | An unsettled internal gap of 1–2 unpaid months. 193 gaps | — | Inferred (Q5) |
| Reactivated | The first paid month that ends an internal churn spell; never a new logo. 64 reactivations (60 customers) | — | Inferred (Q5) |
| Settled gap | A gap settled by arrears, then prepayment, then split, in that order, at ±5%. 211 of 468 gaps (155 / 47 / 9) | `settlement_confidence` | Inferred (Q5, Q2) |
| Outlier | At least 3 positive payments, and a median positive amount ≥ 25 × the portfolio median. Today: customers 94 and 322 | Owner overrides | Inferred (Q9) |
| ARPPU | Σ `amount_value` ÷ paying customers in the month, all-in (the primary figure) | Median; ex-outlier; normalized (Σ `amount_normalized` ÷ customers with `amount_normalized` > 0) | Inferred; the units are owner-backed |
| `sm_spend_per_new_logo` | Σ S&M full ÷ Σ new logos over the month or a trailing 3, 6 or 12-month window. NULL under the CMO-05 conditions, and never called CAC. Feb-22–Oct-24: 4,920,052 | Media-only | Inferred. Scope, currency and spend basis are unconfirmed (Q4, Q1, Q3) |
| NRR(t) | Σ `amount_normalized` at t of the customers active at t−12 ÷ their Σ at t−12. Aug-2024: 91.4% (final); Oct-2024: 92.9% (provisional) | `_raw` (Oct-2024: 93.2%), `_avg3` (96.2%) | Inferred (Q2) |
| GRR(t) | Σ min(x_t, x_{t−12}) over the same base ÷ the base revenue. Aug-2024: 86.5%; Oct-2024: 85.9% (provisional) | `_raw` (85.8%), `_avg3` (87.3%) | Inferred (Q2) |
| Logo churn (12 months) | Customers active at t−12 whose state at t is `churned` ÷ customers active at t−12. NULL after `churn_confirmed_through`. Aug-2024: 9.9% (102 of 1,034) | — | Inferred (Q5) |
| `revenue_complete_through`, `spend_complete_through`, `data_complete_through`, `churn_confirmed_through` | Defined in CTO-07 and SB-05 | — | Controls (not inferred) |

## 3. Dropped rules (from `round3/cdo_rules.md`, verbatim)

| ID | Proposer | Fate | Reason |
|---|---|---|---|
| SQ-11 | Baseline | Dropped, merged into SB-10 | A business expectation, not a quality check: one check, one interpretation |
| CRO-01 | CRO | Merged into SQ-08 (new in R3) | Its principle survives in SQ-08: unknown is never 0 and never a zero month. Unparseable amounts, missing customer-months, bad months and duplicate keys now reject the file (D1), so no NULL amount reaches silver, and its "NULL blocks that month's KPIs" clause has nothing left to act on |
| CRO-02 | CRO | Merged into CDO-04 | A duplicate reconciliation. Its month × industry grain survives. Its control total (2,214,415,000) was wrong |
| CRO-04 | CRO | Dropped, superseded by CDO-07 | Its single `gap` state mixes the 193 pauses with the settled gaps. The CRO withdrew it |
| CFO-01 | CFO | Merged into CTO-02 | A third manifest. Its control totals survive in CTO-02 |
| CFO-02 | CFO | Merged into CDO-04 | The same identity, per file and per month |
| CFO-04 | CFO | Merged into CFO-03 | One status vocabulary; the guess goes into `basis_hint` |
| CFO-06 | CFO | Merged into CMO-05 (R3: previously GLD-07) | Its structure (components, statuses, trailing 3/6/12-month windows) became the columns of the separate view. The payback column was withdrawn |
| CFO-07 | CFO | Merged into CTO-06 | One lineage column set, using SHA-256 rather than the ETag |
| CMO-01 | CMO | Merged into SB-04 | `cohort_censoring` covers it. Comparing with the next calendar month missed 2 Feb-2022 customers |
| CMO-02 | CMO | Withdrawn, merged into CFO-03 | Duplicate currency and basis labels |
| CMO-03 | CMO | Merged into GLD-04 | The mapping is an attribute of `dim_spend_category`, and a new column is caught by CDO-02 |
| CMO-04 | CMO | Merged into CDO-04 | The logo identity became a gold assertion of the single reconciliation |
| CMO-06 | CMO | Merged into CDO-10 | The same ban on allocation; it adds the explicit join list and the CI test |
| CDO-03 | CDO | Merged into CTO-02 | One manifest, keyed on SHA-256 |
| CDO-09 | CDO | Merged into CTO-06 and CTO-10 | `_rules_version` and `as_of_month` on every row; snapshots are immutable `run_id=` prefixes |
| CTO-04 | CTO | Withdrawn, merged into CDO-05 | Identical. Its float evidence becomes a test fixture |
| CTO-05 | CTO | Withdrawn, merged into CDO-06 | Identical |
| CTO-11 | CTO | Withdrawn, merged into CDO-04 | Its gold leg |

**19 rules dropped or merged.** CMO-05 is no longer on this list: it is reinstated as the ID of the separate gold view (D11).

Positions withdrawn inside surviving rules in R3:
- **CDO (mine):**
  - "on a tie, take the nearest multiple" (SB-06);
  - quarantine and withhold the month (SQ-07);
  - the single 100 MB ceiling (BRZ-02) and "flag without blocking" for keys (BRZ-05);
  - Content-Type as a reject (BRZ-01);
  - `is_negative_adjustment` (SB-10);
  - `sm_spend_per_new_logo` inside `agg_month_kpis`;
  - the −1 `dim_customer` member, the TAB allowance (CDO-01) and the quarantine copies for SQ-05;
  - the currency clause in CDO-08, which now lives only in CFO-03.
- **CTO:** the 50% truncation floor, the VersionId key, the single min() watermark, reject on a source-checksum mismatch, and freezing the outlier list.
- **CRO:**
  - j = 2 only;
  - the 6-paid-month minimum, replaced by 3;
  - the 3-month average as the MRR proxy;
  - the `amount_status` NULL path.
- **CFO:** raw NRR and GRR as the headline (raw stays as `_raw`), and reject on any checksum mismatch.
- **CMO:** the tripwire at [0.01, 100], and flag-only for CTO-09.

Carried from §3: the CDO's 1.0% share test, the CFO's `payback_months_revenue_floor`, the CRO's SCD2-ready `dim_customer`, and the CMO's and CFO's "keep" on the baseline SB-07 and SQ-12.

## 4. ETL design (summary of `round3/cto_design.md`)

The design implements exactly the 61 rules. Its traceability table maps every rule ID to a job, table, view or policy and a test: 61 of 61, with no gaps or extras (checked by script). It adds no rules. Where rules collide, it proposes defaults and waits for the CDO (§5.4). No AWS resource was changed, and one read-only check confirmed that nothing has changed since rounds 1–2.

### 4.1 Architecture

1. GuardDuty Malware Protection scans every staging upload. The scan-result event starts one Step Functions ingest per delivery.
2. `bronze_ingest` runs the 11 bronze rules in the CDO's order. It writes the byte-faithful CSV plus a write-once manifest keyed on SHA-256.
3. `silver_validate` gates that dataset's snapshot. An accepted snapshot advances `state.json` (compare-and-swap) and starts one run: `silver_build` → `dl_verify` → `gold_build` → `dl_verify` → `dl_publish`.
4. Each run rebuilds silver and gold in full under an immutable `run_id=` prefix. It publishes by replacing **one pointer object**, which every consumer view reads.
5. **Each dataset advances on its own accepted snapshot and watermark** (D1, D2). A rejected or late file holds back only itself, and the star still switches atomically.

### 4.2 Storage layout and formats

| Area | Location / format |
|---|---|
| Staging | The 3 registered keys, CSV as received |
| Bronze | `al-test-dl-bronze/<dataset_id>/ingest_date=YYYY-MM-DD/<dataset_id>__<ts>__<sha8>.csv`. Byte-faithful CSV plus `_ingested_at`: BOM kept, `,<ts>` before each CRLF, no newline added, the Industry empty record becomes `,,<ts>`. No bronze Glue tables; it is read by key through the manifests only |
| Bronze control | `_manifests/<dataset>/<sha256>.json` (write-once), `_deliveries/` (every delivery, including duplicates), `_events/` (release, retry, restore), `_overrides/`, `_quarantine/`, `_rejected/` |
| Silver | **Parquet with ZSTD (settled)**, one file per table per run, `store/<table>/run_id=<id>/[hr_sensitive=<bool>/]`. Exact `decimal128` money built from `Decimal`, never cast through float. No Iceberg (revisit if Q8 says incremental). Tables: `transactions`, `industry`, `sm_spend` (long format), `customer`, `customer_month`, `gap` (SB-06 audit trail), `month_control`, `source_status`, `restatement_log` |
| Gold | The same Parquet/ZSTD conventions; natural or seed keys; snake_case |
| Control | Silver `_control/state.json` (the only mutable object, CAS), `state_history/`, `config/<rules_version>.yaml`. Gold `_control/published/current.json` (the pointer, CAS), `published_history/`, `retained/` |
| Catalog | `finora_{silver,gold}_store` for the physical run-partitioned tables, and `finora_{silver,gold}` for views filtered to the published run. Four workgroups (`data`, `finance`, `revops`, `pipeline`), each with its own encrypted results and a 1 GB scan cutoff |

### 4.3 Quarantine and rejects

These follow the CDO's onFailure table.

| Kind | Raised by | Where / access | Replay |
|---|---|---|---|
| File quarantine | BRZ-02 (oversize), BRZ-03, BRZ-04, BRZ-05, CDO-02, CTO-02 | `bronze/_quarantine/` (`object.bin` + `reason.json`); security only, the CDO for CDO-02; 365 days | A re-upload, or a security override that re-runs every check except the overridden one |
| File reject | Bronze: BRZ-02 (empty), CDO-01, BRZ-06, CTO-01, CTO-03. Silver: SQ-01, SQ-03 (dup), SQ-05–SQ-08, SQ-09(a), SQ-10, CDO-05, CDO-06 | `_rejected/` records with line numbers (no HR values); Data and security | A corrected re-upload. The dataset keeps its previous snapshot, and the others advance |
| Row quarantine | SQ-02, SQ-03 (regex) | `silver/_quarantine/<table>/run_id=/rows.parquet`; Data | Re-derived every run |
| Run reject | CDO-04, CDO-07, GLD-01–06, CTO-06, CTO-08, CDO-10, CTO-10 | `_runs/run_id=/report.json`; Data | Fix, then rerun. The pointer is unchanged |
| Export reject | CTO-09 | `export_log.json` | Fix, then re-export |

### 4.4 Jobs and orchestration

- **State machines:**
  - `finora-dl-ingest`: one per delivery. Its execution name is the EventBridge event id, which dedupes transport only, so a re-delivery still runs.
  - `finora-dl-run`: a 120 s wait coalesces files that arrive together. It ends as `superseded` if a newer state exists.
  - `finora-dl-retain`: places a legal hold on a run kept for audit.
- **Lambdas** (Python 3.12, all arithmetic in `Decimal`):
  - `bronze_ingest`: stdlib and boto3 only.
  - `silver_validate`, `silver_build`, `gold_build` and `dl_verify`: the AWS SDK for pandas, used for I/O only.
  - `dl_publish`.
  - Schedulers: `freshness_check` and `housekeeping`.
  - `share_build`: deployed disabled.
- **Job order** (the CDO's evaluation order):
  1. **Bronze:** BRZ-05 → BRZ-03 → CTO-02(a) HEAD → BRZ-02 → CTO-02(b) checksum → CDO-01 → CDO-02 → BRZ-04 → BRZ-01 → write → CTO-01 → manifest.
  2. **Silver validate:** SQ-01 → SQ-02 → dataset checks → CDO-05 → SQ-08 → CDO-06, then the snapshot is accepted.
  3. **Silver build:** SB-01/02 → SQ-04/SQ-12 → SB-03 → SB-04 → SB-06 → SB-05/SB-07/CDO-07 → CRO-03 → CRO-05 → SB-08 → CRO-07 → SB-10 → SQ-13/CDO-08/CTO-07 → CFO-03/05.
  4. **Verify, silver leg:** CDO-04.
  5. **Gold build:** dimensions → facts → control tables → `snap_` UNLOAD of the KPI views.
  6. **Verify, gold leg:** CDO-04, CTO-08, the CDO-10 lint.
  7. **Publish:** CTO-10.
- **Idempotency:** by event id, content (dataset, SHA-256: D10), `state.json` seq, write-once `run_id=` prefixes, and newest-wins CAS on the pointer.
- **Watermarks:**
  - `revenue_complete_through` and `spend_complete_through`;
  - `data_complete_through`, the earlier of the two;
  - `churn_confirmed_through` = `as_of_month` − 2.
- **Alerts:** SNS topics for data, finance, security, owners and on-call. Messages carry rule ids and counts, never amounts or customer ids.

### 4.5 Gold dimensional model

| Object | Grain | Key | Rows today | Notes |
|---|---|---|---|---|
| `dim_month` | month | `month_key` YYYYMM | 34 + pre-window months | `quarter_key`, `month_index`, `is_window_start`, `sm_regime` (config only) |
| `dim_industry` | industry | `industry_key` 1–6; −1 UNKNOWN, −2 UNMAPPED | 8 | ES and EN labels, `chart_label` |
| `dim_customer` | customer (SCD1, recomputed every run) | `customer_id` | 1,961 | Cohort, `cohort_censoring`, `first_payment_ratio` and multiple, `implied_start_month_key`, spike flag, first and last paid, outlier |
| `dim_spend_category` | S&M source column | `category_key` 1–7; −2 | 7 | `spend_group`, `channel_class`, `is_hr_sensitive` |
| `dim_source_status` | money dataset | `source_status_key` | 2 | Currency (NULL), currency, basis and scope statuses, `basis_hint` |
| `fct_customer_month_revenue` | customer × month (dense) | (`customer_id`, `month_key`) | 66,674 | Native and full money, `amount_normalized`, lifecycle, settlement, expansion and contraction, `amount_lag12`. Additive only |
| `fct_sm_spend_month` | month × category | (`month_key`, `category_key`) | 238 | Signed spend, `is_negative_spend`; partitioned by `hr_sensitive` |
| `agg_sm_spend_month_group` | month × `spend_group` | | 102 | The people total for non-Finance roles |
| `ctl_run`, `ctl_month` | run; month | | 1 per run; 34 | Watermarks, source SHA-256s, versions; presence, totals, tripwire |
| `agg_month_kpis` (GLD-07) | month (view) | | ≤ revenue watermark | Revenue all-in and ex-outlier, payers, ARPPU (mean, median, normalized), new logos, lifecycle counts, top-1 and top-10 shares, statuses. **No spend measure** |
| `agg_month_sm_spend_per_new_logo` (CMO-05) | month (view) | | | Components, plus 8 ratios (month, t3m, t6m, t12m × total, media), statuses, `null_reasons`. Kept out of standard exports |
| `agg_retention_month` (CRO-06) | t × industry × cohort year × outlier, with roll-ups | | from 2023-01 | NRR, GRR, logo churn on `amount_normalized` (headline), with `_raw` and `_avg3` variants and components |
| `agg_month_industry_cohort`, `agg_cohort_starting_arpa` | month × industry × cohort; cohort | | | Drill-down helpers, with `low_n` |
| `snap_<view>`, `share_<name>` | per run; future | | | Frozen view output for retention; suppressed shares (CDO-11) |

**Drill-down:**
- Total (`agg_month_kpis`) → industry (`agg_month_industry_cohort`, or the fact ⋈ `dim_customer` ⋈ `dim_industry`) → cohort → customer (named roles only) → month (one customer's 34 rows).
- Spend has its own hierarchy (month → `spend_group` → category). It meets revenue only at `month_key`. A sqlglot lint fails the build on any other join (CDO-10).
- Every row carries the CTO-06 lineage. Rows with more than one source point to a snapshot-set id that `ctl_run` resolves.

### 4.6 Security and IAM

- **Service roles,** one per job: uploader, gd-malware, ingest, silver, verify (read-only), gold, publish, housekeeping, freshness, sfn and deploy. **None has `s3:DeleteObject*`**; only lifecycle removes data.
- **Human access through IAM Identity Center permission sets:**
  - `data`: silver and gold, HR denied;
  - `finance`: gold including HR, plus the restatement log;
  - `revops`, including the Revenue and CS leaders: gold, HR denied;
  - `security`: staging, quarantine, overrides;
  - `cdo-review`: CDO-02-tagged quarantine only;
  - `admin`: break-glass, with an alarm.
  - Nobody else gets access until suppressed `share_` objects exist (CDO-11).
- **Bucket policies P1–P12:**
  - TLS 1.2 or later only;
  - deny deletes and policy, lifecycle or versioning changes except for deploy and admin;
  - same-account only;
  - write-once via `If-None-Match`;
  - CAS via `If-Match` on the two control objects;
  - an HR-partition deny for everyone except Finance and the pipeline;
  - a quarantine deny;
  - a deny on `THREATS_FOUND` objects;
  - no forging of scan tags;
  - protection for retention tags and legal holds;
  - a share-zone deny;
  - overrides by security only.
- **Encryption:** SSE-S3 enforced. A customer-managed KMS key is recommended (+$1/month).
- **Audit:**
  - one multi-region CloudTrail trail with S3 data events (read and write) and log validation;
  - alerts on root activity, sign-in without MFA, and policy changes;
  - Access Analyzer, and account-level Block Public Access.
- **Moving off the root keys** (the account owner; this blocks every AWS step):
  1. Create the trail and the root alert.
  2. Set up Organizations plus Identity Center.
  3. Switch `alegra-test` to SSO and confirm the identity is no longer `:root`.
  4. Check that the toldo and radar-emprendedor projects don't use the keys.
  5. Deactivate the keys, wait 7 days, delete them.

### 4.7 Versioning, retention and snapshots (D19)

| Bucket | Versioning | Object Lock | Retention |
|---|---|---|---|
| staging | enable | no | Noncurrent versions expire after 365 days |
| bronze | enable | enable (governance, legal holds only; irreversible, the user decides) | Data, manifests and rejects: no expiry until Q15. Quarantine: 365 days |
| silver, gold | enable | enable (as above) | Each run is tagged `current`, then `superseded`, then `expire` 30 days later. Retained runs are tagged `audit` and get a legal hold. Exports expire after 90 days |
| athena-results (new) | off | no | 7 days |
| audit-trail (new) | enable | optional | 365 days, pending Q15 |

Until Q13 says when a month closes, the first published run for each new revenue watermark is retained automatically, and Finance can retain any other run. Legal holds are used rather than compliance mode, so an erasure (Q16) stays possible.

### 4.8 Cost

About **$0.80/month** at list prices:
- CloudWatch: about $0.60;
- Athena: about $0.08;
- CloudTrail data events: about $0.06;
- S3: about $0.06;
- everything else within free tiers.

Optional: a KMS key adds $1, and GuardDuty threat detection would be priced after its trial. Development and CI cost $0 (the golden run is local).

### 4.9 Build order

Every AWS step needs the user's explicit approval.

| # | Step | Blocked by |
|---|---|---|
| 0 | Put the repo under git with CI; write the config, code, SAM templates and tests; a local golden run reproduces every CDO figure | The user's OK to write files |
| 1 | The account owner moves off the root keys | The owner |
| 2 | Account baseline: Block Public Access, Access Analyzer, SNS, break-glass, alerts | 1 |
| 3 | Storage: versioning, Object Lock, P1–P12, lifecycle, the results bucket, workgroups, Glue, (KMS) | 1; the Object Lock and KMS decisions |
| 4 | Ingest: GuardDuty, EventBridge, `bronze_ingest`; self-tests; **re-upload the 3 files** so they get scanned | 3; A1, A2, A8; the bronze-name decision |
| 5 | Silver | 4; A3, A9 |
| 6 | Gold and the first publish | 5; A4, A5, A7 |
| 7 | Operations: freshness, housekeeping, retain, runbook, `.claude/CLAUDE.md` | 6 |
| 8 | Human access sets | 6; A6 |
| 9 | The export tool (CTO-09) | Before the first export |
| 10 | `share_build` (CDO-11) | The first outside request, plus the CDO's sign-off |
| 11 | Delete `al-test-datalake` | The user's decision |

## 5. Open questions and decisions

### 5.1 For the data owners (from `round3/cdo_rules.md`, verbatim)

| # | Question | Owner | Blocks (rule IDs) |
|---|---|---|---|
| Q1 | Which currency is each file in, and is it the same in both? Which FX applies if the board reports in another currency? | Finance | CDO-08, CFO-03, CMO-05 |
| Q2 | Is revenue invoiced, collected or recognized, and net or gross of tax? What is the 0.21 price grid? Are the first-month spikes setup fees? Are five cells mis-scaled at the source (exactly 1/10 or 1/100 of the previous month: customers 40, 325, 587, 638, 1294)? | Billing + Finance | SB-06, CRO-05, CRO-06 |
| Q3 | Is S&M actual or budget, and booked or incurred? What are the 5 negative PayrollExpenses months? What caused the Jun-2023 break (−47.8%) and the Freelance stop from 2023-05? | Finance | SB-10, CMO-08, CMO-05, CFO-03 |
| Q4 | Does Transactions cover the whole customer base, and the same products, markets and brand as the S&M spend? | Billing + Finance | CFO-05, CMO-05 |
| Q5 | Can an unpaid month be a trial, a pause or part of an annual plan? Please confirm the arrears, prepayment and split patterns | Billing | SB-05, SB-06, SB-07, CDO-07 |
| Q6 | Who assigns industry, and when? Can it change, and with what effective date? Is there a taxonomy, and why is there no "Other"? Do "Servicios profesionales" customers include accountants? | RevOps | SB-09, SQ-04, GLD-02 |
| Q7 | What is the true first-invoice date of each customer? Were IDs assigned from this extract? Were customers who churned before 2022 excluded? Are the Feb-2022 "new" customers really new (a migration)? What explains the 27 double first payments in Mar–Jul 2024 (a promotion or a billing change)? | Billing + RevOps | SB-04, CRO-07, GLD-03 |
| Q8 | Is each delivery a full snapshot or an increment? Will zero months always be present (a dense panel)? Can past months be restated, and are closed months immutable? | Billing + Finance | SQ-08, CDO-06, CTO-10 |
| Q9 | Are customers 94 (4.77% of revenue) and 322 single accounts, or groups or related parties? Did 322 leave after Jan-2024? | Billing + RevOps | SB-08 |
| Q10 | Where are the boundaries between Team, PayrollExpenses, Freelance and Travel, and are they sales or marketing? What sits in PaidMedia and PublicidadNoWeb? Where are accountant-partner commissions and referral fees? Could a payroll category expose one person's pay? | Finance + HR + Marketing | GLD-04, CDO-11 |
| Q11 | Do gross margin or COGS, cash, AR and headcount data exist? | Finance | None in this set (gold publishes no payback or LTV) |
| Q12 | Can we get plan, module, channel and accountant-partner IDs per customer, and an acquisition-source field from the CRM? | RevOps + Marketing | CDO-10 (an approved allocation key), CRO-05 |
| Q13 | What is the delivery cadence and deadline relative to the month-end close? Who uploads, and from which system? When is a month closed, and in which time zone? | Finance + source-system owner | None in this set (design: the uploader role and freshness alerts) |
| Q14 | Will file names, headers, the BOM and CRLF stay stable? Who announces schema changes, and how far ahead? | Source-system owner | CDO-01, CDO-02, CTO-01, BRZ-05 |
| Q15 | How long must these records be kept? Is us-west-2 acceptable for data residency? | Legal + Finance | CTO-10 (retention, Object Lock) |
| Q16 (new) | Can a customer's records be erased on request (a data subject, or the end of a contract)? If so, how does erasure apply to retained bronze snapshots and published runs, given that a removed key otherwise rejects the file? | Legal + DPO | CDO-06, CTO-10, CDO-11 |

**Owner answers that change the design, not only config** (CTO):
- **Q8:** incremental deliveries would mean a merge instead of a snapshot replacement, and possibly Iceberg.
- **Q13:** the uploader principal, the freshness SLA, and month-close retention.
- **Q14:** the registry change process.
- **Q15:** retention dates, expiries, and residency.
- **Q16:** the erasure procedure, which needs a CDO-06 exemption.
- **Q10:** the HR-sensitive set.
- **Q12:** the CDO-10 allow-list.

The other answers (Q1–Q7, Q9) change config only and need a rebuild.

### 5.2 Decisions for Finora (the user and the account owner)

1. **Root keys:** the account owner migrates to Organizations plus Identity Center and deletes the keys. This blocks every AWS step.
2. **Bronze object names:** name bronze objects by dataset id (`sm_spend/…/sm_spend__<ts>__<sha8>.csv`) and keep `s_and_m/S&M_spend.csv` verbatim in the manifest. **The CDO and CTO both recommend this.** The user decides.
3. **Re-upload the 3 staging files** (identical bytes, with SHA-256) so GuardDuty scans them. BRZ-03 blocks the unscanned originals.
4. **Versioning** on staging, bronze, silver and gold, and **Object Lock** (governance mode, irreversible) on bronze, silver and gold. Both are recommended.
5. **A KMS key** (+$1/month, recommended).
6. **The legacy bucket `al-test-datalake`:** delete it, or keep it under P1–P3.
7. **Version control:** the repo isn't a git repository, and the lints need CI.
8. **Approval of each build step**, including step 0 (writing code, config and IaC into the repo).

### 5.3 Proposed corrections to `docs/data_semantics/` (from `round3/cdo_rules.md`, verbatim)

Not applied: the folder is frozen for this review.

| Doc and location | Correction | Raised by |
|---|---|---|
| `transactions_data_dictionary.md` §5.5; `transactions_data_profile.md` §1 (total revenue) | The full revenue total is **2,214,415,045.08**, not 2,214,415,000. The docs rounded before scaling | CDO, CFO |
| `industry_data_dictionary.md`, `sm_spend_data_dictionary.md` (line endings) | **None** of the three files ends with a newline. Only the Transactions docs say so | CDO, CTO |
| `transactions_data_dictionary.md` §4 (paying caveat) and §6 (catch-up row); `transactions_data_profile.md` §5.3 and recommendation 4 | 45.1% of gaps are settled (arrears 155 + prepayment 47 + split 9 = 211 of 468), not ⅓; prepayment was missed. Describe the tests in their precedence order | CDO |
| `sm_spend_data_profile.md` | Add S&M ÷ revenue at full amounts: 5.75× / 3.21× / 2.30× annually (2022 / 2023 / Jan–Oct 2024), 1.61–7.62× monthly. The "2.3–5.8×" figure is annual; it appears in `00_baseline.md`, not in this folder | CDO, CRO, CMO |
| `transactions_data_dictionary.md` §6 (date row) | Add that Spark and Athena need `M/d/yyyy`, because `MM/dd/yyyy` fails | CDO |
| `transactions_data_dictionary.md` §4 (new, churned, reactivation rows) | New customer = `cohort_censoring` none (1,541; Feb-2022 68). Churned: an unsettled run of ≥ 3 unpaid months, dated to its first unpaid month and confirmed through `as_of_month` − 2. Reactivation: 64 (60 customers). Add grace, paused and settled gap, and the ARPPU variants | CDO (new in R3) |
| `transactions_data_dictionary.md` §4.1 | Replace `is_left_censored` with `cohort_censoring`. Base `is_new` on `none`. Redefine `is_catch_up` by the ordered settlement tests. Add `lifecycle_state`, `amount_normalized` and `first_payment_ratio` | CDO (new in R3) |
| `transactions_data_dictionary.md` §5.2 | "If refunds exist in the source, they were netted out or excluded" is not backed by the owners. Write instead: 0 negatives are observed, the owners have not said whether refunds exist, and a negative is kept and flagged | CDO (new in R3) |
| `transactions_data_dictionary.md` code sample; `sm_spend_data_dictionary.md` code sample (`astype(float)`) | Read money as strings and parse it as Decimal, not float. Floats are wrong on 2,436 rows and 32 cells | CDO, CTO (new in R3) |
| `sm_spend_data_dictionary.md` §4 (`cac` example metric) and the CAC mentions in §4 and §5 | Replace with `sm_spend_per_new_logo` on canonical new logos (excluding `probable_left`), with scope, currency and basis statuses. No metric is named CAC | CDO, CMO, CFO (new in R3) |
| `sm_spend_data_dictionary.md` §6 ("Allow negatives in this column only") and the PayrollExpenses description ("reversals or true-ups") | Negatives are kept in every category and flagged as `is_negative_spend`, with an alert outside PayrollExpenses. Their nature is unconfirmed (Q3), and a budget plug is as likely as a reversal | CDO, CFO (new in R3) |
| `sm_spend_data_dictionary.md` §2 ("loaded as DECIMAL(9,3)") | Native DECIMAL(12,3), full amount DECIMAL(18,0) | CDO (new in R3) |
| `sm_spend_data_profile.md` recommendation 2 ("label derived CAC as planned CAC") | No metric is labelled CAC. Use `spend_basis_status` | CDO (new in R3) |
| `industry_data_dictionary.md` §2 (ID regex) and §6 (empty record) | Use the regex `^Cliente [1-9]\d*$`. Route the empty record to quarantine as `EMPTY_RECORD` instead of dropping it. Normalize `Industria` to NFC before the domain check; unknown values map to UNKNOWN or UNMAPPED | CDO (new in R3) |
| `transactions_data_profile.md` §5.4 | Add the canonical split of the 283 customers whose last payment came before Oct-2024: 237 with an open churn spell of ≥ 3 months, and 46 in grace | CDO (new in R3) |

### 5.4 Build-level points for the CDO (from `round3/cto_design.md`)

These are not disagreements over rules. They are places where two rules, as written, collide in implementation, or where the text admits more than one reading. The CTO proposes a default for each and builds it only after the CDO confirms it.

| # | Rules | Issue | CTO's proposed default | Blocks step |
|---|---|---|---|---|
| A1 | CTO-02 × BRZ-02/03/05 | A file quarantined unread has no SHA-256 to key its manifest on | Key it `unread__<etag>__<versionid>`, or by the S3-held SHA-256 | 4 |
| A2 | CTO-02 × release or retry | A write-once manifest can't record a later outcome | The manifest holds the first outcome; later outcomes are write-once `_events/` records | 4 |
| A3 | CTO-03 × CDO-06 | Re-delivering an older snapshot (A, B, A) is rejected as removed history, so a rollback is impossible | Built literally (reject). The CDO decides whether an owner-approved override may pass | 5 |
| A4 | CDO-10 × GLD-06, CFO-03 | The spend fact carries `dim_source_status`, so the literal lint fails | Allow-list `dim_month`, `dim_spend_category`, `dim_source_status` | 6 |
| A5 | GLD-01 × GLD-03 | Implied start months reach 2021-12, before the calendar | Extend `dim_month` backwards with a negative `month_index` | 6 |
| A6 | CDO-11 (2) × quarantine access | The security role can read payroll values in a quarantined S&M file | Security keeps read access, logged by CloudTrail. The CDO decides on a Finance co-reader | 8 |
| A7 | CDO-04 logo identity | A customer whose rows are all ≤ 0 has no censoring class (0 today) | Count `dim_customer` rows with a NULL cohort | 6 |
| A8 | The bronze order | A checksum before BRZ-02 means reading an oversize file that should stay unread | Split CTO-02 into a HEAD identity check and a byte checksum at the first read | 4 |
| A9 | SQ-06, SQ-07(a), SB-04, quotients | Literal readings: padded dates; `Decimal` accepts `1e3` and `NaN`; NULL j; the scale of quotients | A strict non-padded pattern; a strict numeric grammar; NULL; DECIMAL(38,12) HALF_UP, never fed back into money | 5, 6 |

## 6. Round files

| Round | CRO | CFO | CMO | CDO | CTO |
|---|---|---|---|---|---|
| Baseline | [`00_baseline.md`](00_baseline.md) | | | | |
| 1. Positions | [`round1/cro.md`](round1/cro.md) | [`round1/cfo.md`](round1/cfo.md) | [`round1/cmo.md`](round1/cmo.md) | [`round1/cdo.md`](round1/cdo.md) | [`round1/cto.md`](round1/cto.md) |
| 2. Debate | [`round2/cro.md`](round2/cro.md) | [`round2/cfo.md`](round2/cfo.md) | [`round2/cmo.md`](round2/cmo.md) | [`round2/cdo.md`](round2/cdo.md) | [`round2/cto.md`](round2/cto.md) |
| 3. Resolution | — | — | — | [`round3/cdo_rules.md`](round3/cdo_rules.md) | [`round3/cto_design.md`](round3/cto_design.md) |

**Process notes:**
- **Word counts:** every executive overran its length target. Round 1 ran 1,576–3,268 words and round 2 1,856–2,540 (`wc -w`). In round 3 the CDO wrote 11,915 words and the CTO 11,055.
- **Interruptions:** in round 2, four agents hit the account's usage limit. Three had already written complete files. The CDO was resumed and told not to read the other round-2 files.
- **Round 3 ran sequentially:** the CDO took about 24 minutes, then the CTO about 27.
- **What no agent changed:** AWS, `data/` and `docs/data_semantics/`. Each wrote only its own file.
- **An unrelated file,** `docs/aws_architecture/data-lake-voice-dashboard-architecture.html`, appeared during round 1. It was left untouched.
