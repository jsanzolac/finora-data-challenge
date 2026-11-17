# Round 2: CTO debate

At 1.3 MB, almost everything the other four propose is cheap to build. The real cost is ambiguity, not compute. I rebuilt the CDO's lifecycle model in /tmp and it reproduces exactly (64 reactivations, 74 Feb-2022 new logos), but it is deterministic only once two clauses are written down.
Five of us proposed overlapping manifests, lineage columns, reconciliations, status labels and first-payment flags. I merge each family into one rule so that each is built once.
I push back on three things: onFailure modes that are rejects in disguise, partial per-month publishing, and a share-based outlier test. I would also defer cell suppression until someone outside Finance reads the data. None of this moves the run cost off about $1/month.

*Evidence: `python3 -I` with `Decimal` over `data/` (scripts in /tmp/cto_r2), plus read-only S3 checks today. The identity is still `:root`. Staging holds 3 objects, and bronze, silver and gold hold 0. Versioning and Object Lock are off on all four buckets.*

## Verdicts on the other executives' new rules

| Rule | Proposer | Verdict (keep/flag/drop) | Reason |
|---|---|---|---|
| CRO-01 | CRO | flag | Right principle, and cheap: generate customers × calendar and left-join, so a missing cell is NULL with `amount_status='missing'`. A duplicate key rejects the file instead (see SQ-05 below) |
| CRO-02 | CRO | flag | Merge into the single reconciliation (CDO-04). Its control total is wrong (2,214,415,000 vs 2,214,415,045.08), so totals must come from the manifest |
| CRO-03 | CRO | flag | Feasible, but 3 of 155 catch-ups don't split into whole cents. Put the residual in the payment month so Σ normalized = Σ amount, and spread by the CDO-07 settlement type |
| CRO-04 | CRO | drop | Superseded by CDO-07, which has the same states and more. `is_provisional` is derived from it (`grace`, or `amount_status` ≠ ok) |
| CRO-05 | CRO | flag | "Consecutive paid months" can mean calendar-adjacent or across a pause. Define it as t and t−1 both `paying`. Additive fact columns, so fine |
| CRO-06 | CRO | flag | Build it as an Athena view over the fact. The CDO confirms the definition. With a 12-month lookback it exists only for 2023-01 → 2024-10 (22 months) |
| CRO-07 | CRO | flag | A third first-payment test (≥ 3× the later median flags 80 customers). Compute it once beside CMO-01 and SB-04 (see the CMO reply) |
| CFO-01 | CFO | keep | Merge it with CDO-03 and CTO-02 into one manifest. Control totals are computed from the raw strings, and unparseable cells are counted, never failing bronze |
| CFO-02 | CFO | keep | Merge into the CDO-04 reconciliation, per file and per month |
| CFO-03 | CFO | flag | Merge CFO-03, CFO-04 and CMO-02 into one versioned `dataset_status` config (currency, basis, scope) stamped on the facts. An owner answer then means a config change plus a rebuild |
| CFO-04 | CFO | flag | Same merge as CFO-03 |
| CFO-05 | CFO | flag | The computed gate is always true (5.75 / 3.21 / 2.30), so it is a constant posing as a check. Make `scope_status` config. CDO-08 is the only computed ratio check |
| CFO-06 | CFO | flag | Store the numerator and denominator per month, never the ratio. Trailing 3/6/12 windows are view window functions. Use CMO-05's name |
| CFO-07 | CFO | keep | Merge with CTO-06 and CDO-09. Use SHA-256, not the ETag |
| CMO-01 | CMO | flag | 32 of 95 and 34 of 108 are the same customers over two denominators. Use the next *paid* month, and merge with SB-04 and CRO-07 |
| CMO-02 | CMO | flag | Merged into `dataset_status` (CFO-03) |
| CMO-03 | CMO | keep | A seed table for `dim_spend_category`. Drop its "new column fails" clause, because CDO-02 already quarantines at bronze |
| CMO-04 | CMO | flag | Cheap assertion, but the identity becomes left + probable_left + none = 377 + 38 + 1,546 = 1,961 |
| CMO-05 | CMO | keep | The honest name wins over "CAC". NULL for Jan-2022. One view, with the CFO-06 components |
| CMO-06 | CMO | keep | Merge with CDO-10. Enforce it in CI by linting the view DDL for spend-to-customer, industry or channel joins |
| CMO-07 | CMO | flag | It depends on the query grain, so compute it in the aggregate view. 140 of 198 industry × month cells are under 10; by quarter, 16 of 72 |
| CMO-08 | CMO | flag | A cheap seed attribute, but it bakes an interpretation into a conformed dimension. Mark it inferred and keep it in config pending Q3 (−47.8% May→Jun 2023 verified) |
| CDO-01 | CDO | keep | Same as my BRZ-01 text. Accept reject. Drop the TAB allowance (0 TABs, no free text) |
| CDO-02 | CDO | keep | The registry is a versioned JSON in the repo. A header mismatch quarantines the file |
| CDO-03 | CDO | keep | The base text for the single manifest. Write-once comes from S3 conditional writes plus no `DeleteObject`, with no Object Lock needed |
| CDO-04 | CDO | keep | The base text for the single reconciliation (absorbs CFO-02, CRO-02, CTO-11). Per file and month, plus per industry in gold |
| CDO-05 | CDO | keep | Identical to CTO-04. Adopt its precisions |
| CDO-06 | CDO | keep | Identical to CTO-05, which I withdraw |
| CDO-07 | CDO | flag | Reproduced exactly and exhaustive, but 169 of 468 gaps match two settlement tests. Needs a precedence clause and a censored-first-month clause |
| CDO-08 | CDO | keep | One line of SQL. Today's range is 1.61–7.62. It catches a missing ×10,000 (≈ 0.00035×) |
| CDO-09 | CDO | keep | Per row and per run, not per column. Snapshots are justified: one new month restates 45 earlier rows |
| CDO-10 | CDO | keep | Merged with CMO-06 |
| CDO-11 | CDO | flag | 63 of 198 cells would be suppressed, it needs complementary suppression, and no outside consumer exists. Use IAM now; build `share_` views on the first request |

## Replies

**To the CDO.**
- **CDO-07 is implementable.** It is a 60-line state machine. Two runs give identical output, and every one of the 66,674 rows gets exactly one state: 64 reactivations (60 customers), 29,321 pre-acquisition rows and 46 grace customers.
  - **Precedence.** The split test contains the arrears test whenever x_p ≈ x_{p−1}: 122 gaps match both, and 47 match both prepay and split. The 211 settled gaps don't depend on order, but `is_catch_up`, `is_prepaid` and CRO-03's spreading do. Add "precedence: arrears > prepay > split".
  - **Censored first month.** The first paid month of a `left` or `probable_left` customer must be `paying`, not `new`. Otherwise count(`new`) is 1,584 while the CAC denominator is 1,546.
  - **Your 64 vs the CRO's 65:** the gap is customer 40 (k = 3), settled only by a split.
- **CDO-09.** Adding Oct-2024 restates 45 earlier rows across 27 customers: 28 grace → churned, 9 grace → paused, 5 grace → settled_gap and 3 churned → settled_gap. Each published run is an immutable `run_id=` prefix, not an `as_of` dimension inside one table.
- **CDO-11.** With a published monthly total, any single suppressed industry cell can be recovered by subtraction. There are 0 IAM users and no BI tool today.
- **Your bronze verdicts.**
  - **BRZ-02, "keep at 100 MB":** that is 77× the largest file, so it catches nothing. The realistic failure is truncation.
  - **BRZ-05, "flags without blocking":** a key with `..` or control bytes must not reach code that builds paths from it.

**To the CFO.**
- **onFailure.** "Quarantine and block gold" (SQ-05, SQ-07) is a reject with extra steps. A run publishes atomically or not at all (CTO-10). A parse failure or duplicate key rejects the file, the previous publish stays live, and the copy goes to `_rejected/` for diagnosis. For SQ-10, "block that month in gold" means two versions of the truth in one star, and I won't build partial publishes. Negative amounts: load and flag, as you, the CRO and the CDO all say.
- **CFO-07.** The ETag equals the MD5 only for single-part SSE-S3 uploads. A multipart upload or a move to SSE-KMS silently breaks that, so use SHA-256.
- **CFO-01.** Bronze keeps strings. A control total it cannot parse is a silver problem, not a bronze reject.

**To the CRO.**
- **Control totals.** CRO-02's figure would have rejected a correct load. Totals come from the manifest, never from docs.
- **SQ-08, "a hole is quarantine":** there is no row to quarantine. Generate the NULL cell and flag it (CRO-01). The CDO decides whether holes reject.
- **Outliers.** Your median-ratio test should beat the CDO's 1.0% share. Share depends on the window: over the first 12 months the third-largest customer sits at 1.02%. Customer 322's share has decayed from 3.48% to 1.86% since it stopped paying, so it would eventually flip out and restate every ex-outlier KPI. The ratios (94 at 60.0×, 322 at 31.7×, the next at 18.6×) stay put after churn. Freeze the list per `_rules_version` and alert on change, rather than flipping it automatically.
- **SCD2-ready `dim_customer`:** drop it. With no effective dates the columns would be constants. Bronze snapshots keep the history, and CDO-06's diff tells us when an industry first changes. Build SCD2 then.
- **Dropping CAC:** I disagree. An unpublished metric gets rebuilt in a spreadsheet without labels. Publish CMO-05's name with the CFO's components.

**To the CMO.**
- **Feb-2022.** Your 32 of 95 used the next calendar month. All 108 have a next paid month, and 34 of them paid about 2× it.
- **One first-payment attribute.** The 2× first payment also appears in Mar–Jun 2024 (5, 8, 5 and 7 customers), and that can't be left-censoring. Compute `first_payment_multiple` (j, ±5%, against the next paid amount) and `first_payment_spike` (CRO-07) once on `dim_customer`. The CDO's `cohort_censoring` uses the multiple only for cohorts ≤ 2022-03, and `acquisition_confidence` is derived from the two. That gives three flags from one computation and one new-logo count.

## Where I changed my mind

- **CTO-02 (amended), new text:** "One write-once manifest per accepted or rejected file, `_manifests/<dataset>/<sha256>.json`. It holds the verbatim source key, VersionId (null while versioning is off), size, ETag, SHA-256, staging LastModified, scan status, row count, Decimal control totals from the raw strings with an unparseable-cell count, BRZ-01 to BRZ-05 hits, `_ingested_at`, `run_id` and `_rules_version`. It is written with `If-None-Match: *`. A checksum mismatch rejects." It absorbs CFO-01 and CDO-03.
- **CTO-04: withdrawn** in favour of CDO-05, with `amount` DECIMAL(12,6) → DECIMAL(18,2) and spend DECIMAL(12,3) → DECIMAL(18,0).
- **CTO-05: withdrawn** in favour of CDO-06.
- **CTO-06 (amended):** every silver and gold row carries `_run_id`, `_source_key`, `_source_sha256`, `_ingested_at`, `_rules_version` (a hash of the rules file) and `as_of_month`. It absorbs CFO-07 and CDO-09.
- **CTO-08 (amended):** each dimension gets two members: −1 `UNKNOWN` (no Industry row) and −2 `UNMAPPED` (an unrecognised value).
- **CTO-11: withdrawn** into CDO-04, with the CMO-04 identity added as a gold assertion.
- **SQ-02:** I now quarantine the empty record, as the CDO proposes, so that 1,962 = 1,961 + 1 reconciles.
- **SQ-05:** a duplicate key now rejects the file, as the CDO proposes. In a dense panel it means a broken extract, and a partial publish at month-end close is worse than a late one.
- **Bronze onFailure:** reject (`_rejected/`, readable by Data) is for malformed files. Quarantine (`_quarantine/`, readable only by the security role) is for BRZ-03, BRZ-04 and BRZ-05 hits.
- **I hold** CTO-01, CTO-03, CTO-07, CTO-09 and CTO-10, the versioning plan (now backed by the CFO), and the root-key removal as the blocker for any AWS step.
