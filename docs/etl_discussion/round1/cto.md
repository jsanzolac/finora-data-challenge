# Round 1: CTO position

The baseline can be built on serverless AWS for about $1/month, and I re-verified every data figure used below. My changes make the contracts provable and safe to run:
1. Bronze stays CSV and is a lossless append, proven by a byte round-trip to the staging SHA-256.
2. From silver onward: exact decimals, full rebuilds, atomic publishes and reconciliation.
3. Before any data moves past staging, fix the account: it has root keys, no CloudTrail, no TLS-only policy and no versioning.

## M1 Inventory

Verified read-only on 2026-11-15, identity `arn:aws:iam::962482423379:root`, region us-west-2:

| Key | Bytes | ETag (= MD5) | LastModified (UTC) | Content-Type | Same as `data/` |
|---|---|---|---|---|---|
| `transactions/Transactions.csv` | 1,302,387 | `ae01140d…c18718` | 2026-11-16 00:31:33 | `text/csv; charset=utf-8` | yes (MD5, SHA-256, `cmp`) |
| `industry/Industry.csv` | 49,402 | `4d04f745…22de51` | 2026-11-16 00:31:37 | same | yes |
| `s_and_m/S&M_spend.csv` | 2,063 | `71592d32…aba43b` | 2026-11-16 00:31:39 | same | yes |

The bucket settings match the docs on all 5 `al-test-*` buckets: us-west-2, versioning never enabled, SSE-S3 with SSE-C blocked, all four public-access-block flags on, BucketOwnerEnforced. Bronze, silver, gold and legacy hold 0 objects and 0 versions.

**Not in the docs** (omissions, not contradictions):
- **Buckets:** no bucket policy (so TLS is not enforced), lifecycle, logging or notifications.
- **Account:** no S3 Block Public Access at account level, no CloudTrail trail, no GuardDuty, 0 IAM users. The root keys are present (MFA on).
- **Shared account:** it also holds the `toldo-*` and `radar-emprendedor-*` buckets, so the root keys put more than the data lake at risk.
- **Athena:** the `primary` workgroup has no result location and no encryption.
- **Files:** none of the 3 ends with a CRLF; the docs say so only for Transactions.
- **Upload checks:** the staging objects carry no user metadata, so the MD5 check made at upload left no trace on them.

**Agree:** 3 files = 3 datasets, one prefix each.

**Change / add:**

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CTO-02 | Bronze | all | Write one JSON manifest per file, holding the key, VersionId, size, ETag, SHA-256, CRC64NVME, scan status, `_ingested_at` and each rule's outcome. Uploaders send `x-amz-checksum-sha256` so S3 validates the PUT | The objects record only the ETag and CRC. I verified the SHA-256 by downloading them | quarantine on mismatch | no |

**Verdicts:** M1 has no baseline rules.

## M2 Profile

**Agree.** I re-verified the figures with `python3 -I` and `Decimal`:
- **All files:** BOM, CRLF only, 0 quotes, 0 NUL or control bytes, constant field counts. The only non-ASCII characters are `ó` and `í`. No PII.
- **Transactions:** 66,674 rows = 1,961 IDs × 34 month-ends. 0 duplicate keys, 0 negatives, maximum 847.966434, sum 221,441.504508. The Jan-2022 payers are exactly IDs 1–377, and customer 94 has 4.77% of revenue. There are 468 gaps across 340 customers, 83.8% of them ≤ 2 months, with 155 catch-ups.
- **Industry:** 1,961 rows plus the `,` record. IDs match Transactions both ways.
- **S&M:** 238 of 238 cells match `^-?\$\d+\.\d{3}$`. The only negatives are 5 in PayrollExpenses and the only zeros are 17 in Freelance. Same window as Transactions; total 77.818.

**Change / add:**

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CTO-04 | Silver | all | Parse numbers as exact decimals (Python `Decimal` or Arrow `decimal128`), never as floats: `amount` DECIMAL(12,6), `amount_value` DECIMAL(18,2), spend DECIMAL(9,3), `spend_value` DECIMAL(18,0) | Floats give a wrong full amount on 2,436 Transactions rows (`11.072376 × 10,000 = 110723.76000000001`) and on 32 of 238 S&M cells (`0.276 × 1e8 = 27600000.000000004`) | reject | no |

**Verdicts:** M2 has no baseline rules.

## M3 Bronze security checks

**Agree:** these are the right six checks, and macros, zip bombs and PII don't apply. Every check except the malware scan runs as stdlib Python in the bronze Lambda and costs about $0.

**Malware scan (BRZ-03):** use GuardDuty Malware Protection for S3 on staging. It runs without a GuardDuty detector, tags each object with `GuardDutyMalwareScanStatus` and emits an EventBridge event. It costs $0.09/GB plus about $0.215 per 1,000 objects, with a free tier of 1 GB and 1,000 objects a month (checked today), so $0 for us. I rejected ClamAV on Lambda: it brings an image, signature updates, cold starts and patching, for no gain on text.

**`_ingested_at` with no other change (BRZ-06):**
- **Keep CSV.** Parquet is itself a change: it types or nulls values, drops the BOM and CRLF, and loses the round-trip proof.
- **Append** `,<ts>` before each line terminator, and `,_ingested_at` to the header. The BOM and CRLF stay, no final newline is added, and Industry's `,` becomes `,,<ts>`. This is unambiguous because no field is quoted or contains a comma.
- **Name:** renaming to `sm_spend` changes the key, not the data. Keep the original key in the metadata and manifest. The user decides.
- **Event keys:** S3 delivers `S%26M_spend.csv`, so decode with `unquote_plus`.
- **Layout:** `<dataset>/ingest_date=YYYY-MM-DD/<dataset>__<ts>__<sha8>.csv`, with Athena partition projection. Every column is STRING, and `_ingested_at` needs backticks in DDL (an Athena rule).

**Change / add.** Replacement text:
- **BRZ-01:** "Strict UTF-8 (a BOM is allowed); no NUL or control bytes except CR and LF; the header equals the registry header; constant field count. A Content-Type mismatch only flags." On failure: quarantine.
- **BRZ-02:** "0 bytes: reject. Above the dataset's ceiling (Transactions 50 MB, Industry 5 MB, sm_spend 1 MB): quarantine. Below 50% of the previous snapshot: quarantine (truncation)."
- **BRZ-03:** "Proceed only on `NO_THREATS_FOUND`. Any other status goes to quarantine. The staging policy denies `GetObject` on `THREATS_FOUND` to every role except the security role."
- **BRZ-04:** "Signed numbers (`^-\$?\d+(\.\d+)?$`) pass. Any other cell starting with `=`, `+`, `-`, `@`, TAB or CR quarantines the file (there are no free-text columns)."
- **BRZ-05:** "The key must be on the registry allowlist. Non-ASCII, control characters, `..`, `//`, a leading `/` or more than 1,024 bytes: quarantine. `&` is allowed only in `s_and_m/S&M_spend.csv`, where it is flagged."

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CTO-01 | Bronze | all | Lossless append. With the last field removed from every line, the bronze object must equal the staging object byte for byte (same SHA-256). Test it on every run, before publishing | 0 quotes or embedded commas; CRLF only; BOM and no final newline in 3 of 3 | reject | no |
| CTO-03 | Bronze | all | `_ingested_at` takes one value per file, ISO-8601 UTC with `Z`, set at the first successful ingest of a staging VersionId. Re-processing that VersionId does nothing | Reruns must not create duplicate snapshots | reject | no |

**Verdicts:**

| Rule | Verdict | Reason |
|---|---|---|
| BRZ-01 | flag | The uploader sets Content-Type, so it can't decide a reject. Add the header check |
| BRZ-02 | flag | 100 MB is 77× the largest file and catches nothing. Use per-dataset ceilings and a truncation floor |
| BRZ-03 | keep | A cheap managed control. It adds little signal on CSV, but auditors expect it |
| BRZ-04 | flag | Only 5 cells match, all of them signed numbers in PayrollExpenses (verified): flagging them is noise |
| BRZ-05 | flag | `&` is the only character outside `[A-Za-z0-9_./-]` (verified). Turn the check into an allowlist |
| BRZ-06 | flag | The contract is right. It needs CTO-01 and CTO-03 to be testable, and a decision on the rename |

## M4 Silver quality rules

**Agree:** SQ-03, SQ-04 and SQ-07 to SQ-11 as written. The CDO owns their meaning, and all of them pass today.

**Change / add:**
- **SQ-01:** add "CRLF and a missing final newline are tolerated. Numbers are parsed as in CTO-04."
- **SQ-02:** replace with "A record is empty when all of its source columns are empty, ignoring `_ingested_at`. Drop it and count it. More than one, or not the last record: quarantine the file." This applies to all datasets.
- **SQ-05:** quarantine every copy of a duplicate.
- **SQ-12:** map orphan Transactions rows to the Unknown member (CTO-08) and flag them.
- **SQ-13:** becomes the gold watermark (CTO-07).

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CTO-05 | Silver | all | Treat each delivery as a full snapshot. Rebuild from the latest accepted bronze snapshot, compare it with the previous one, and flag changed values in months already published | The files hold the full history. The owners haven't said how deliveries work | flag | yes |
| CTO-06 | Silver, Gold | all | Every table carries `_run_id`, `_source_key`, `_source_sha256`, `_ingested_at` and `_rules_version` | Audit lineage. Bronze forbids extra columns, so lineage starts in silver | reject | no |

**Verdicts:**

| Rule | Verdict | Reason |
|---|---|---|
| SQ-01 | keep | BOM, comma delimiter and header verified in 3 of 3 files |
| SQ-02 | flag | After bronze the record reads `,,<ts>`, so a "fully empty" test misses it |
| SQ-05 | flag | 0 duplicates today, but the rule doesn't say which copy survives |
| SQ-06 | keep | 34 non-padded month-ends. Parse with `%m/%d/%Y` (Python) or `%c/%e/%Y` (Athena) |
| SQ-10 | keep | 238 of 238 cells conform. The full amount needs DECIMAL(18,0) |
| SQ-12 | flag | 100% match today, but quarantining orphans would silently remove revenue |
| SQ-13 | flag | Same window today. It becomes the watermark |

## M5 Silver business rules

**Agree:** SB-01 and SB-02 are owner definitions. SB-03 to SB-10 are correctly marked inferred, and the CDO owns them.

**Change / add:**
- **SB-04, SB-05, SB-07:** the flags change retroactively as months arrive, so do a full rebuild on every run (CTO-10) with `as_of_month` = the watermark.
- **SB-06:** I reproduced the 155 catch-ups only with "the first payment after a k-month gap is within ±5% of (k+1) × the last payment before the gap". The CDO must fix this definition.

**Verdicts:**

| Rule | Verdict | Reason |
|---|---|---|
| SB-01 | keep | Owner definition. Exact in DECIMAL |
| SB-02 | keep | Owner definition. × 1e8 always gives integers |
| SB-05 | flag | Needs an explicit `as_of`. Churn at the end of the window is provisional |
| SB-06 | flag | The 155 of 468 is reproducible only with an exact definition |
| SB-08 | flag | "Outlier" has no threshold, so the rule isn't deterministic. It needs a list or a percentile |

## M6 Gold dimensional model

**Agree:** a star built from GLD-01 to GLD-06, with a dense revenue fact that keeps the zero months.

**Change / add:**
- **Keys:** natural keys (`customer_id`; `month_key` = YYYYMM; the industry and category codes). With SCD1 there is no surrogate-key service.
- **Storage:** Parquet with ZSTD, one file per table per run, no partitions (under 1 MB). No Iceberg: a full rebuild plus a swap of the table location gives the same isolation. Revisit it if loads become incremental.
- **GLD-07** becomes an Athena view.
- **Names:** lower-case snake_case.

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CTO-07 | Gold | cross | `data_complete_through` = the earliest of the datasets' latest months. KPI views stop there. A late dataset flags and never blocks the others | Same window today, but the files can arrive separately | flag | no |
| CTO-08 | Gold | all | Every dimension has an Unknown member (−1). Facts are never dropped for a missing dimension row | The SQ-12 quarantine would drop revenue | flag | no |
| CTO-09 | Gold | egress | CSV and XLSX exports escape text cells that start with `=`, `+`, `-`, `@`, TAB or CR by prefixing `'`. Bronze is never exported | OWASP CSV injection. Bronze keeps the raw strings | reject (the export fails) | no |
| CTO-10 | Silver, Gold | all | Rebuild in full into `run_id=`. Swap the Glue table locations only after every check passes. If a run fails, the previous one stays live | SB-04/05/07 change retroactively, and the rebuild takes seconds | reject | no |

**Verdicts:**

| Rule | Verdict | Reason |
|---|---|---|
| GLD-01 | keep | 34 months. Generate the calendar, don't derive it from the data |
| GLD-02 | flag | 6 values. Add the Unknown member. The English labels are inferred |
| GLD-03 | keep | 1,961 rows. The cohort is recomputed on every run |
| GLD-04 | flag | The media / people / other grouping is inferred. The CMO and CFO should confirm it |
| GLD-05 | keep | 66,674 rows including the zero months. The flags carry `_rules_version` |
| GLD-06 | keep | 238 rows (34 × 7). `spend_value` is an integer |
| GLD-07 | flag | Make it a view. CAC is blocked on open question 4 (coverage) |

## M7 Verification

Each rule ID gets a unit test with a failing fixture (a float, a `=HYPERLINK` cell, a truncated file, a duplicate key) and a golden run over today's files.

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CTO-11 | Gold | cross | Reconcile before publishing. Row counts (66,674, 1,961 and 238) and native totals (221,441.504508 and 77.818) must match across bronze, silver and gold, after the rows that were dropped or quarantined | Totals verified today with `Decimal` | reject (the previous publish stays live) | no |

**Feasibility of every baseline rule:**

| Rule | Feasible? | How | Note |
|---|---|---|---|
| BRZ-01, BRZ-02, BRZ-04, BRZ-05 | yes | stdlib in the bronze Lambda, a dataset registry and head-object | see the replacement texts |
| BRZ-03 | yes-with-cost | GuardDuty Malware Protection for S3 | $0 today; needs a service role and an EventBridge rule |
| BRZ-06 | yes | stdlib byte append | tested with CTO-01 |
| SQ-01 to SQ-04 | yes | pyarrow with `utf-8-sig`, regex, a lookup table | SQ-02 ignores `_ingested_at` |
| SQ-05 to SQ-08 | yes | group-by, `strptime`, Decimal, ID × month count | SQ-05 must say which copy survives |
| SQ-09 to SQ-11 | yes | regex, Decimal, a calendar | |
| SQ-12, SQ-13 | yes | anti-join, min/max month | onFailure changes; watermark |
| SB-01, SB-02 | yes | Decimal | |
| SB-03, SB-04, SB-05, SB-07 | yes | pandas window functions and run-lengths | need `as_of`; SB-07 depends on SB-06 |
| SB-06 | not as written | window functions | the tolerance base is ambiguous |
| SB-08 | not as written | — | no threshold is defined |
| SB-09, SB-10 | yes | join, sign test | |
| GLD-01 to GLD-06 | yes | Parquet, Glue catalog, Athena | |
| GLD-07 | yes | Athena view | CAC is blocked by question 4 |

## M8 Open questions for the data owners

1. Is each delivery a full restatement or an increment? Can past months be restated?
2. What is the delivery cadence and deadline relative to the month-end close? Who uploads, and from which system? The answer defines the uploader role.
3. Will the file names, headers, BOM and CRLF stay stable? Who announces schema changes?
4. How long must these records be kept, and is us-west-2 acceptable for residency? The answer decides Object Lock.
5. When is a month closed, and in which time zone?
6. For the account owner: remove the root keys. The account is shared, so check first that no other project depends on them.

## Implementation sketch

| Component | Service and detail |
|---|---|
| Scan and trigger | A GuardDuty malware protection plan on staging. An EventBridge rule on the scan-result event starts Step Functions |
| Orchestrator | Step Functions Standard. The execution name `<dataset>-<sha256[:16]>` makes a duplicate delivery a no-op. Retries with backoff; a Catch sends the file to quarantine and alerts through SNS. A late file gets its own run. A forced rerun uses `-rerun-N` |
| `bronze_ingest` | Lambda, Python 3.12, stdlib and boto3 only |
| `silver_build`, `gold_build` | Lambda with the AWS SDK for pandas layer. Reserved concurrency 1 serializes the runs |
| Catalog and query | Glue databases per layer. Athena workgroup `finora-dl`: enforced settings, encrypted results in a new results bucket with 7-day expiry, a 1 GB scan cutoff |
| Infrastructure as code | AWS SAM / CloudFormation |

**Quarantine:**
- **File level:** `bronze/_quarantine/<dataset>/<ts>__<sha8>/` holds a copy of the staging bytes plus `reason.json` (rule_id, reason, VersionId, SHA-256, scan status, run_id). Files that fail the malware scan are never copied.
- **Row level:** `silver/_quarantine/<table>/run_id=<id>/rows.parquet` holds the source columns as STRING plus `_rule_id`, `_reason`, `_source_line` and the lineage columns.
- **Access and retention:** only `finora-dl-security` can read either location, and objects expire after 365 days.
- **Replay:** re-upload the fixed file (a new VersionId). For a false positive, the security role starts a release that records the override and the approver. Quarantined objects are never edited.

**IAM roles** (none can delete):

| Role | Allowed |
|---|---|
| `finora-dl-uploader` | Put on `staging/<dataset>/*`, with a checksum |
| `finora-dl-bronze` | Get and GetTagging on staging. Put on `bronze/<dataset>`, `_quarantine` and `_manifests` |
| `finora-dl-silver`, `finora-dl-gold` | Read the layer below (`_quarantine` denied), write their own layer and its Glue database |
| `finora-dl-sfn` | Invoke the 3 functions; publish to SNS |
| `finora-dl-analyst` | The `finora-dl` workgroup; read gold |
| `finora-dl-deploy` | CloudFormation, through IAM Identity Center with MFA |

**Moving off the root keys** (the account owner does this):
1. Create a multi-region CloudTrail trail.
2. Turn on Identity Center and switch `alegra-test` to SSO.
3. Confirm that `sts get-caller-identity` no longer shows `:root`.
4. Check that the toldo and radar-emprendedor projects don't use the keys.
5. Deactivate the keys, wait a week, then delete them.
6. Alarm on any use of the root user.

**Versioning.**
- **Staging and bronze:** on, with noncurrent versions expiring after 365 days. These two matter more than silver and gold, which can be rebuilt from them. Bronze is a candidate for Object Lock (governance mode) once the CFO and legal set a retention period.
- **Silver and gold:** on, with noncurrent versions expiring after 30 days.
- **Every bucket:** deny requests without TLS, deny `DeleteObject*` except to the deploy role, and abort incomplete multipart uploads after 7 days.

**Monthly cost** (list prices; only GuardDuty re-checked today):

| Item | Cost |
|---|---|
| S3 | ~$0.05 |
| GuardDuty, Lambda, Step Functions, Glue catalog | $0 (free tiers) |
| Athena, at the 10 MB minimum per query | ~$0.05 |
| CloudTrail | ~$0 |
| CloudWatch and SNS | ~$0.50 |
| **Total** | **~$1/month** |

A customer-managed KMS key would add about $1/month.

**Build order** (each AWS step needs the user's approval):
1. The account owner removes the root keys. This blocks every step below.
2. Infrastructure as code: bucket hardening, the Athena results bucket, Glue and the workgroup.
3. GuardDuty, EventBridge and Step Functions.
4. `bronze_ingest`, with the CTO-01 golden test against the 3 SHA-256 values.
5. `silver_build`, after the CDO's round-3 rules.
6. `gold_build` and CTO-11.
7. Alerts, a runbook and `.claude/CLAUDE.md`.
