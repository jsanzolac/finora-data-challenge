# Round 3: CTO ETL design

**Architecture.** Every upload to staging is scanned by GuardDuty Malware Protection, and the scan-result event starts one Step Functions ingest per delivery. `bronze_ingest` runs the 11 bronze rules in the CDO's order. It writes a byte-faithful CSV with `_ingested_at` appended, plus a write-once manifest keyed on SHA-256. `silver_validate` then gates that dataset's snapshot. An accepted snapshot advances a state object (updated by compare-and-swap) and starts one run: `silver_build` → `dl_verify` → `gold_build` → `dl_verify` → `dl_publish`. The run rebuilds silver and gold in full, as Parquet/ZSTD with exact decimals, under an immutable `run_id=` prefix. It publishes by replacing a single pointer object that every Athena consumer view reads. Each dataset advances on its own accepted snapshot and watermark (D1, D2): a rejected or late file holds back only itself, while the star still switches atomically. KPIs are Athena views, frozen per run as `snap_` tables so that a retained run can be reproduced (D11, D19). Access is through IAM Identity Center permission sets, plus bucket-policy denies on the HR-sensitive and quarantine prefixes (CDO-11).

**Cost:** about **$0.80/month** at list prices, or about $1.80 with the optional KMS key.

**Blockers:**
1. **Root access keys.** Nothing is built until the account owner moves to Identity Center and deletes them.
2. **User decisions:** bronze object names; re-uploading the 3 staging files so GuardDuty scans them; versioning and Object Lock; KMS.
3. **CDO confirmations:** six collisions between rules as written and three literal-reading choices (A1–A9). Each one blocks only its own build step.

## Verified current state

**No change since rounds 1–2.** One read-only check today (2026-11-15, `alegra-test`, us-west-2):
- **Identity:** still `arn:aws:iam::962482423379:root`, with 0 IAM users.
- **Staging:** exactly the 3 objects from rounds 1–2, with the same sizes (1,302,387 / 49,402 / 2,063 B), ETags (`ae01140d…c18718`, `4d04f745…22de51`, `71592d32…aba43b`) and LastModified (2026-11-16 00:31:33–39 UTC). All have VersionId `null`.
- **Other buckets:** bronze, silver, gold and `al-test-datalake` hold 0 object versions. Versioning has never been enabled on any of the 5 buckets, and none has a bucket policy.
- **Account:** no CloudTrail trail, no Glue database, no Lambda function, no state machine and no GuardDuty malware protection plan.

Not re-checked today: encryption, public access block and object ownership. I take the round-1 values.

## Storage layout and formats

### Layout

| Area | Location | Format | Compression | Partitioning | Naming | Writer → readers |
|---|---|---|---|---|---|---|
| Staging | `al-test-dl-staging/{transactions/Transactions.csv, industry/Industry.csv, s_and_m/S&M_spend.csv}` | CSV exactly as received | none | none | the 3 registered keys only (BRZ-05) | uploader → ingest, GuardDuty, security |
| Bronze data | `al-test-dl-bronze/<dataset_id>/ingest_date=YYYY-MM-DD/<dataset_id>__<yyyymmddThhmmssfffZ>__<sha8>.csv` | CSV, byte-faithful plus a last column `_ingested_at` (BRZ-06) | none (CTO-01 compares raw bytes) | `ingest_date`, for browsing only | `dataset_id` ∈ {`transactions`, `industry`, `sm_spend`}; `sha8` = first 8 hex characters of the staging SHA-256. The verbatim source key lives only in the manifest | ingest → silver, verify |
| Manifests | `al-test-dl-bronze/_manifests/<dataset_id>/<sha256>.json` | JSON, write-once (`If-None-Match: *`) | none | none | one per distinct content (CTO-02); see A1 for unread files | ingest → silver, verify, Data, security |
| Delivery log | `al-test-dl-bronze/_deliveries/<dataset_id>/<ts>__<content_id8>.json` | JSON, write-once | none | none | one per delivery event, including duplicates (CTO-03: A, B, A) | ingest → Data, security |
| Content events | `al-test-dl-bronze/_events/<dataset_id>/<sha256>/<ts>__<event>.json` | JSON, write-once | none | none | release, retry and restore events that follow the manifest (A2) | ingest, silver → Data, security |
| File quarantine | `al-test-dl-bronze/_quarantine/<dataset_id or _unregistered>/<ts>__<content_id8>/{object.bin, reason.json}` | the original bytes plus JSON | none | none | object tags `quarantine_rule=<rule id>`, `dataset=<id>` | ingest → security; CDO for `CDO-02` only |
| Rejects | `al-test-dl-bronze/_rejected/<dataset_id>/<sha256>/<ts>__<rule_id>.json` | JSON reject record | none | none | one per rejected attempt | ingest, silver → Data, security |
| Overrides | `al-test-dl-bronze/_overrides/<dataset_id>/<content_id>.json` | JSON, write-once | none | none | release records (approver, reason, overridden rule) | security → ingest |
| Silver store | `al-test-dl-silver/store/<table>/run_id=<run_id>/[hr_sensitive=<bool>/]part-00000.zstd.parquet` | Parquet | ZSTD | `run_id`; also `hr_sensitive` for `sm_spend` and `restatement_log` | one file per table per run | silver → gold, verify, Data (Finance: `restatement_log` only) |
| Row quarantine | `al-test-dl-silver/_quarantine/<table>/run_id=<run_id>/rows.parquet` | Parquet | ZSTD | `run_id` | one per table per run | silver → Data |
| Run report | `al-test-dl-silver/_runs/run_id=<run_id>/report.json` | JSON | none | `run_id` | counts per rule, flags, alerts, verdicts | silver, publish → Data |
| Control state | `al-test-dl-silver/_control/{state.json, state_history/<seq>.json, config/<rules_version>.yaml}` | JSON or YAML | none | none | `state.json` is the only mutable object (CAS with `If-Match`); history and config are write-once | silver, deploy → all pipeline roles |
| Gold store | `al-test-dl-gold/store/<table>/run_id=<run_id>/[hr_sensitive=<bool>/]part-00000.zstd.parquet` | Parquet | ZSTD | `run_id`; also `hr_sensitive` for `fct_sm_spend_month` | one file per table per run, including `snap_<view>` | gold → (1) roles |
| Publish pointer | `al-test-dl-gold/_control/published/current.json` plus `_control/published_history/<run_id>.json` and `_control/retained/<run_id>.json` | JSON | none | none | `current.json` is replaced only by CAS (`If-Match`) | publish → every reader |
| Share zone (future) | `al-test-dl-gold/share/<share_name>/run_id=<run_id>/` | Parquet | ZSTD | `run_id` | suppressed shares (CDO-11 (3)) | `share_build` → outside roles, once approved |
| Exports | `al-test-dl-gold/_exports/<role>/<export_id>/[hr_sensitive=true/]{file.csv or .xlsx, export_log.json}` | CSV or XLSX, plus JSON | none | none | written by the requester's own session (CTO-09) | requester |
| Athena results (new) | `al-test-dl-athena-results/<workgroup>/` | Athena output | none | none | one prefix per workgroup, expiry after 7 days | each workgroup's role only |

**`run_id`:** `r<yyyymmddThhmmssZ>-s<state_seq, 6 digits>`, for example `r20261116T004000Z-s000007`.

**`content_id`:** the SHA-256 when the bytes were read. For a file quarantined unread, it is `unread__<etag>__<versionid or null>` (A1).

### Formats

- **Bronze: CSV, byte-faithful (BRZ-06, CTO-01).**
  - The header becomes `<original header>,_ingested_at`, keeping the BOM.
  - Every record gets `,<ts>` inserted before its CRLF. The final record has no terminator, so `,<ts>` is appended at end of file and no newline is added.
  - Industry's empty record `,` becomes `,,<ts>`.
  - `<ts>` is a single value per object, `YYYY-MM-DDTHH:MM:SS.fffZ` (CTO-03).
  - There are no bronze Glue tables. The pipeline reads bronze by key through the manifests, never through Athena, so bronze can't be queried by accident.
- **Silver: settled as Parquet with ZSTD**, one file per table per run, partitioned by `run_id` (plus `hr_sensitive` where needed), with no Iceberg.
  - Exact money types (CDO-05) are written as Parquet DECIMAL logical types through an explicit pyarrow schema (`decimal128(12,6)`, `decimal128(18,2)`, `decimal128(12,3)`, `decimal128(18,0)`). Values are built from Python `Decimal` and never cast through float.
  - Keys are INT32, flags BOOLEAN, states STRING. `_ingested_at` stays the exact bronze STRING.
  - Why Parquet: it is typed and exact, columnar for Athena, and uses the same toolchain as gold. Each run is immutable (CTO-10).
  - Why not Iceberg: there are no updates or merges, only full rebuilds, and Iceberg has no multi-table transactions anyway. Revisit if Q8 says deliveries are incremental.
- **Gold:** the same Parquet/ZSTD conventions as silver. Natural or seed keys, lower-case snake_case, and no partitions beyond `run_id` and `hr_sensitive`.

### Glue and Athena

- **Databases:**
  - `finora_silver_store` and `finora_gold_store` hold the physical tables, partitioned by `run_id`. The writer registers each run's partitions with `BatchCreatePartition` before publishing.
  - `finora_silver` and `finora_gold` hold views only, each filtered to the published run.
  - Analysts query `finora_silver` and `finora_gold`; `_store` is for the pipeline and for reproducing retained runs.
- **Workgroups:** `finora-dl-data`, `finora-dl-finance`, `finora-dl-revops` and `finora-dl-pipeline`.
  - Each has enforced settings, its own encrypted result prefix and a 1 GB scan cutoff per query.
  - Each role gets one workgroup, so Finance's HR query results can never be read from a shared result prefix.

```sql
-- Store table pattern (identifiers that start with "_" need backticks in DDL and double quotes in DML)
CREATE EXTERNAL TABLE finora_gold_store.fct_customer_month_revenue (
  customer_id INT, month_key INT, source_status_key INT,
  amount DECIMAL(12,6), amount_value DECIMAL(18,2),
  amount_normalized DECIMAL(12,6), amount_normalized_value DECIMAL(18,2),
  -- ... the GLD-05 columns ...
  `_run_id` STRING, `_source_key` STRING, `_source_sha256` STRING,
  `_ingested_at` STRING, `_rules_version` STRING, as_of_month INT)
PARTITIONED BY (run_id STRING)
STORED AS PARQUET LOCATION 's3://al-test-dl-gold/store/fct_customer_month_revenue/';

-- Publish pointer: one JSON object, replaced atomically
CREATE EXTERNAL TABLE finora_gold_store.ctl_published (run_id STRING, state_seq BIGINT, published_at STRING)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://al-test-dl-gold/_control/published/';

-- Consumer view: reads the pointer exactly once. Every other table is tied to the same run_id by join
CREATE VIEW finora_gold.fct_customer_month_revenue AS
SELECT f.* FROM finora_gold_store.fct_customer_month_revenue f
WHERE f.run_id = (SELECT run_id FROM finora_gold_store.ctl_published);
```

- **How views are built:**
  - Each KPI view has a base view `<view>_by_run` in `finora_gold_store`. It computes for every run, partitions all its windows by `run_id`, and joins every table on `run_id`.
  - The consumer view filters the base view once on the pointer, so each query sees exactly one run.
  - To reproduce a retained run, query `<view>_by_run WHERE run_id = '<id>'`, or read its `snap_` table.
- **Residual risk.** An ad hoc query that joins two consumer views reads the pointer twice. If a publish lands in those milliseconds, the query can mix two runs.
  - Every row carries `_run_id`, so a mix is detectable.
  - The runbook says to join on `"_run_id"`.

### Silver tables

| Table | Grain | Key | Rows today | Rules |
|---|---|---|---|---|
| `transactions` | customer × month | (`customer_id`, `month_key`) | 66,674 | SQ-01, SQ-05–SQ-08, CDO-05, SB-01, SB-03 (`amount_raw`, `month_raw`, `_source_line` kept) |
| `industry` | customer | `customer_id` | 1,961 | SQ-03, SQ-04, SB-09 (`id_raw`, `industria_raw`, `industria_nfc`, `industry_key`) |
| `sm_spend` | month × category, long format | (`month_key`, `category_code`) | 238 | SQ-09, SQ-10, CDO-05, SB-02, SB-10. Partitioned by `hr_sensitive` |
| `customer` | customer | `customer_id` | 1,961 | SQ-12, SB-04, SB-08, SB-09, CRO-07 |
| `customer_month` | customer × month | (`customer_id`, `month_key`) | 66,674 | SB-05, SB-06, SB-07, CDO-07, CRO-03, CRO-05 (`is_churn_event`, `churn_spell_type`) |
| `gap` | customer × gap | (`customer_id`, `gap_start_month_key`) | 468 | SB-06 audit trail (p, q, k, the result of each test, the winning test) |
| `month_control` | month | `month_key` | 34 | SQ-09(b), SQ-13, CDO-08, CTO-07 inputs |
| `source_status` | money dataset | `dataset_id` | 2 | CFO-03, CFO-05 (from config) |
| `restatement_log` | changed value or set | (`dataset_id`, `key`, `column`) | 0 (first load) | CDO-06, SB-08. Partitioned by `hr_sensitive` |
| `_quarantine/industry` | source line | (`_source_sha256`, `_source_line`) | 1 (`EMPTY_RECORD`) | SQ-02, SQ-03 |

## Quarantine and rejects

These follow the CDO's onFailure table exactly. Reject means the file is not accepted. Quarantine means the pipeline does not read the file. Flags stay in place.

| Kind | Raised by | Location and contents | Access | Retention | Replay and release |
|---|---|---|---|---|---|
| File quarantine (bronze) | BRZ-02 (oversize), BRZ-03, BRZ-04, BRZ-05, CDO-02, CTO-02 (checksum mismatch) | **`object.bin`:** a server-side copy (CopyObject; the pipeline never parses it) for BRZ-02, BRZ-04, CDO-02 and CTO-02. For BRZ-03 and BRZ-05, the bytes stay in versioned staging, behind the scan-tag deny or the allowlist, and `reason.json` points to their VersionId.<br>**`reason.json`:** rule id, reason code, detected_at, execution id, the verbatim source key (as a JSON string, never used in a path), VersionId, ETag, size, SHA-256 (if read), S3-held checksum, scan status, `_rules_version`.<br>**Manifest:** written as per CTO-02 and A1 | `finora-dl-security` only. `finora-dl-cdo-review` may read objects tagged `quarantine_rule=CDO-02` (see A6 for sm_spend) | 365 days, pending Q15; a legal hold if under investigation | **Fixed file:** the uploader re-uploads; new bytes get a new SHA-256 and follow the normal path.<br>**False positive:** security writes `_overrides/<dataset>/<content_id>.json` (rule overridden, approver, reason, ticket) and starts `finora-dl-ingest` in `release` mode. Every check runs again, and only the overridden rule is skipped, for that content id only. The outcome is recorded as an `_events/` record (A2).<br>**CDO-02:** the CDO classifies the change and the registry version is bumped, with no override needed.<br>Quarantined bytes are never edited |
| File reject (bronze) | BRZ-02 (empty), CDO-01, BRZ-06, CTO-01, CTO-02 (manifest not written), CTO-03 | **Reject record:** rule id, reason, offending line numbers (the first 1,000 plus a count), column names, manifest key. Cell values are included only for non-HR columns, so `_rejected/` never exposes HR-sensitive amounts (CDO-11 (2)) | Data, security | Same as manifests: no expiry until Q15 | **Corrected file:** a re-upload. **Our own defect** (CTO-01, BRZ-06, manifest write): retried through a `retry` event after the fix (A2) |
| File reject (silver, per dataset) | SQ-01, SQ-03 (duplicate), SQ-05, SQ-06, SQ-07(a), SQ-08, SQ-09(a), SQ-10, CDO-05, CDO-06 (removed key) | Same reject record. The bronze object exists but is never accepted | Data, security | Same as manifests | A corrected re-upload. The dataset stays at its previous accepted snapshot, and the others advance |
| Row quarantine (silver) | SQ-02, SQ-03 (regex) | `rows.parquet`: the source columns as STRING, `_rule_id`, `_reason`, `_source_line` and the CTO-06 lineage | Data | Follows its run (see Versioning) | Rows are re-derived on every run. A fix is a corrected file, or a config change the CDO approves |
| Run reject | CDO-04, CDO-07, GLD-01–GLD-06 (grain, keys), CTO-06, CTO-08 (unresolved month or customer), CDO-10, CTO-10 (publish), SB-01/SB-02 (unreachable once CDO-05 passes; asserted) | `_runs/run_id=<id>/report.json` with `status=failed` and the failing rule. The run prefix stays in place for diagnosis | Data | Expires 30 days after the failure | Fix, then a redrive or a new run. The pointer is unchanged, so the previous run stays live |
| Export reject | CTO-09 | `export_log.json` with `status=failed`; no file is delivered | requester | 90 days | Fix the column typing, then re-export |
| Flag | every flag rule | In place: a flag column (silver, gold) or the manifest (bronze), counted in `report.json`. Alerts go to the named team | per layer | per layer | — |

## Jobs and orchestration

### Trigger and state machines

| Component | Definition |
|---|---|
| Trigger | A GuardDuty Malware Protection plan on `al-test-dl-staging` with tagging on. An EventBridge rule on `source=aws.guardduty`, `detail-type="GuardDuty Malware Protection Object Scan Result"` for that bucket starts `finora-dl-ingest`. The execution name is `<dataset or unreg>-<EventBridge event id>`, which dedupes repeated delivery of the same event at the transport level. It does not dedupe by content, because a re-delivery of A must still run (CTO-03) |
| `finora-dl-ingest` (Standard, one per delivery) | `BronzeIngest` → Choice on the outcome:<br>• `accepted` or `restore` → `SilverValidate` → Choice: on accepted, `StartRun` (asynchronous, named `run-s<seq>`); on rejected, `NotifyReject`.<br>• `rejected` → `NotifyReject` (Data and the dataset owner).<br>• `quarantined` → `NotifySecurity` (plus the CDO for CDO-02).<br>• `duplicate_current` → log and Succeed.<br>Retries on Lambda service, throttle and S3 5xx errors: 3 attempts, backoff ×2. Catch `States.ALL` → `NotifyFailure` → Fail |
| `finora-dl-run` (Standard) | `Wait 120 s` (coalesces the 3 files arriving together) → `ReadState`: if `state.seq` > input seq, a newer run owns the work and this one ends as Succeed `superseded`; if the published `state_seq` ≥ `state.seq`, Succeed `already_published` → `SilverBuild` → `VerifySilver` → `GoldBuild` → `VerifyGold` → `Publish` → `NotifyRun` (a digest of flag counts and alerts). Catch → `NotifyRunFailed` (Data and on-call) → Fail. Redrive is allowed |
| `finora-dl-retain` (Standard) | Started by Finance or Data with (`run_id`, reason), or automatically by the export tool when the audience is outside (1). It tags the run `retention=audit`, places a legal hold on the run's objects and on its bronze inputs and manifests, and writes `_control/retained/<run_id>.json` (D19) |
| Schedules (EventBridge Scheduler) | **`freshness_check`, daily:** staging objects whose ETag has no delivery record after 1 hour, and the CTO-07 late-dataset flag. A calendar SLA is added once Q13 is answered.<br>**`housekeeping`, daily:** tags superseded runs older than 30 days `retention=expire`, never retained ones |
| Config and code deploy | The deploy writes `_control/config/<rules_version>.yaml` (write-once), CAS-bumps `state.json` (`seq+1`, reason `deploy`) and starts `finora-dl-run`, so an owner answer means a config change plus a rebuild |

**Lambdas:**
- `bronze_ingest`: Python 3.12, stdlib and boto3 only, 1,024 MB, 120 s.
- `silver_validate`, `silver_build`, `gold_build` and `dl_verify`: Python 3.12 with the AWS SDK for pandas layer, used for pyarrow I/O only. Every calculation is in `Decimal`. 1,024–2,048 MB, 300 s. Reserved concurrency 1 on the builders.
- `dl_publish`, `freshness_check` and `housekeeping`: stdlib and boto3.
- `share_build`: deployed disabled (CDO-11 (3)).
- **Exports** are a CLI library (`finora-dl-export`) run in the requester's own IAM session, so IAM decides what each person can export.

### Job boundaries and evaluation order

| # | Job (role) | Rules, in order | On failure |
|---|---|---|---|
| 1 | `bronze_ingest` (`finora-dl-ingest`) | (1) **BRZ-05:** the event key is matched byte for byte against the registry, in both its literal and `unquote_plus` forms, so `S%26M_spend.csv` matches. Unread. → (2) **BRZ-03:** the event status, cross-checked against the object tag. Unread. → (3) **CTO-02(a):** HeadObject; the ETag and VersionId must equal the scanned ones. Unread. → (4) **BRZ-02:** size from HEAD; 0 B rejects; over the ceiling, quarantine unread. → (5) **CTO-02(b):** GetObject with `IfMatch=<scanned ETag>` (and the VersionId once versioning is on) and `ChecksumMode=ENABLED`. Compute the SHA-256. A 412, or a mismatch with an S3-held checksum, quarantines for security. → (6) **CDO-01** → (7) **CDO-02** → (8) **BRZ-04** → (9) **BRZ-01** (flag) → (10) **write:** BRZ-06 and CTO-03. If a manifest for (dataset, SHA-256) already exists, take the duplicate path: no bronze write, a delivery record, and `restore` when the content is not the current accepted snapshot. Otherwise PUT the bronze object with `If-None-Match`. → (11) **CTO-01:** read the object back, strip the last field and compare SHA-256 with staging. → (12) **CTO-02** manifest (`If-None-Match`) and delivery record. Steps (3) and (5) split the CDO's "CTO-02 checksum" so that BRZ-02 stays "unread" (A8) | reject, quarantine or flag, as per rule |
| 2 | `silver_validate` (`finora-dl-silver`), one dataset | SQ-01 → SQ-02 → {industry: SQ-03 · transactions: SQ-05, SQ-06, SQ-07 · sm_spend: SQ-09, SQ-10} → CDO-05 → SQ-08 (transactions) → CDO-06 (diff against the previous accepted snapshot; skipped and logged `baseline` on the first acceptance). If all pass: CAS `state.json` (accepted pointer, `seq+1`) and write `state_history/<seq>.json`. A snapshot is "accepted" only here | reject (file) → `_rejected/`; that dataset keeps its previous accepted snapshot |
| 3 | `silver_build` (`finora-dl-silver`), the whole run | Reads the 3 accepted snapshots in `state.json` and re-verifies each bronze object's SHA-256 against its manifest, plus CTO-01. Re-applies job 2's rules: a deterministic rebuild, and any difference from acceptance fails the run. Then SB-01/SB-02 → SQ-04 / SQ-12 → SB-03 → SB-04 → SB-06 → SB-05 / SB-07 / CDO-07 → CRO-03 → CRO-05 → SB-08 → CRO-07 → SB-10 → SQ-13 / CDO-08 / CTO-07 → CFO-03 / CFO-05 (config stamping, no dependency). `as_of_month` is the latest month of the accepted Transactions snapshot, read at the start, because SB-05, CDO-07 and SB-08 need it. CTO-07 then publishes it. CTO-06 lineage goes on every row. Writes `store/*/run_id=<id>/`, row quarantine, `restatement_log` and `report.json` | reject (run) |
| 4 | `dl_verify`, silver leg (`finora-dl-verify`, read-only) | CDO-04 silver leg: per file and per month, rows and Σ native amount in bronze (the manifest control totals) = silver + row quarantine. Computed on the Parquet read back from S3 | reject (run) |
| 5 | `gold_build` (`finora-dl-gold`) | GLD-01 (+ CMO-08) → GLD-02 → GLD-04 → `dim_source_status` (CFO-03) → GLD-03 → GLD-05 → GLD-06 → `agg_sm_spend_month_group` → `ctl_month`, `ctl_run` (CTO-07) → CTO-08 unknown members and alerts → CTO-06 lineage → register partitions → Athena `UNLOAD` of every KPI view `_by_run` for this run into `snap_<view>` (GLD-07, CMO-05, CRO-06, the design views, with CMO-07 `low_n`) | reject (run) |
| 6 | `dl_verify`, gold leg (`finora-dl-verify`) | CDO-04 gold leg: per month and per month × industry; Σ by industry = Σ by month; the logo identity; count(`new`) = count(`none`); snap totals = fact totals. Then CTO-08 (no unresolved month or customer), the CDO-10 check on the Glue table and view definitions (the same lint as CI), and the CI lints on banned names | reject (run) |
| 7 | `dl_publish` (`finora-dl-publish`) | CTO-10. Read `current.json` and its ETag. Publish only if `run.state_seq` > `published.state_seq`, by PUT with `If-Match`. Tag the new run `retention=current` and the previous one `retention=superseded`, write `published_history/<run_id>.json`, then alert. Otherwise end as `superseded` | reject (run) |
| 8 | `finora-dl-export` (the requester) | CTO-09 (and CMO-05's export restriction) | reject (export) |
| 9 | `share_build` (disabled) | CDO-11 (3): primary and complementary suppression | reject (run) for that share |

### Idempotency and reruns

| Level | Key | Mechanism |
|---|---|---|
| Event | EventBridge event id | Execution name `<dataset>-<event id>`; Step Functions rejects a duplicate name |
| Content | (dataset, SHA-256), permanently (D10) | The manifest `If-None-Match` plus the bucket policy (write-once). The VersionId is recorded but is never the key. A re-delivery writes no bronze object and no new `_ingested_at` (CTO-03) |
| Snapshot set | `state.json` `seq` (monotonic; one bump per acceptance, restore or deploy) | CAS with `If-Match`. `state_history/<seq>.json` is write-once |
| Run | `run-s<seq>` (forced rerun `run-s<seq>-r<N>`) | Write-once `run_id=` prefixes, through `If-None-Match` and the bucket policy. `UNLOAD` refuses a non-empty prefix |
| Publish | `published.state_seq` | Newest wins: CAS on `current.json`. An older run that finishes late cannot overwrite a newer publish |
| Rerun after a code fix | `_code_version` in `ctl_run` | The deploy bumps `seq` and starts a run. A redrive is used only for transient failures |
| Config change | `_rules_version` | The CI golden run must pass against the current bronze snapshots before the deploy. At run time, a config change that makes an accepted snapshot fail is a run reject: nothing is published, and Data is alerted |

### Per-dataset publishing, late files and watermarks (D1, D2)

**Decision.** Each run publishes the whole star atomically through one pointer. Independence comes from the per-dataset accepted snapshots in `state.json` and from the watermarks in `ctl_run`, not from per-family publishing. That keeps CTO-10's atomicity and satisfies D2. The watermarks are:
- `revenue_complete_through` = max month of the accepted Transactions snapshot;
- `spend_complete_through` = the same for S&M;
- `data_complete_through` = the earlier of the two;
- `churn_confirmed_through` = `as_of_month` − 2.

| Scenario | Result |
|---|---|
| Transactions file rejected (for example SQ-07(a)) | Transactions stays at its previous accepted snapshot, and S&M and Industry advance if they are new. A run publishes with `revenue_complete_through` unchanged. Data and the owner are alerted. No NULL amount reaches silver (D1) |
| S&M is late, and Transactions adds month M+1 | `agg_month_kpis` and `agg_retention_month` show M+1. CMO-05 is NULL for M+1 (beyond `data_complete_through`). SQ-13 flags M+1. `ctl_run.is_late_sm_spend` = true, and `freshness_check` alerts |
| Industry rejected | `dim_customer` uses the previous accepted Industry. New Transactions customers get −1 UNKNOWN (SQ-12, flagged; non-zero revenue alerts Data, CTO-08) |
| A file is quarantined | The same as a reject for that dataset. Security is alerted |
| A, B, A re-delivered | The second A writes no bronze object (CTO-03). A is re-validated, and if it passes, becomes accepted again. If A lacks B's keys, CDO-06 rejects it (A3) |
| A run fails (CDO-04, CDO-07, CTO-08, CDO-10) | Nothing is published, and the previous run stays live (CTO-10) |

### Alerts

SNS topics: `finora-dl-data`, `finora-dl-finance`, `finora-dl-security`, `finora-dl-owners` (addresses pending Q13) and `finora-dl-oncall`.

**Messages carry only rule ids, dataset, run or execution id, and counts.** They never carry amounts or customer ids, because email is outside the access boundary.

| Event | Topics |
|---|---|
| File reject (any layer) | data, owners |
| File quarantine | security; also data for CDO-02 (the CDO) |
| SQ-02 unexpected count or position; SQ-04 UNMAPPED; CTO-08 non-zero revenue or spend on an unknown member; SB-08 flagged-set change; GLD-04 unmapped category | data |
| SB-10 negative outside PayrollExpenses | finance, data |
| CDO-06 changed value in a month already published | finance |
| CDO-08 unit tripwire | data, finance |
| CTO-07 late dataset; staging object not processed | data, owners |
| Run or ingest failure (Step Functions failure alarm) | oncall, data |
| Root-user activity; console sign-in without MFA (an EventBridge rule on CloudTrail) | security |

## Gold dimensional model

Every row of every table and view carries the CTO-06 lineage: `_run_id`, `_source_key`, `_source_sha256`, `_ingested_at`, `_rules_version` and `as_of_month`.
- **Single-source rows** carry their own source.
- **Rows with more than one source** (`dim_month`, `dim_customer`, `ctl_month`, and views that read both datasets) carry `_source_key` = `multi`, `_source_sha256` = the snapshot-set id (the SHA-256 of the sorted source SHA-256s) and the latest input `_ingested_at`. `ctl_run` resolves the set to all three source keys and SHA-256s. This is the CDO's "run manifest" option.

### Objects

| Object | Type | Grain | Primary key | Column groups | Foreign keys | Rows today |
|---|---|---|---|---|---|---|
| `dim_month` | table (GLD-01, CMO-08) | month | `month_key` (YYYYMM) | **Calendar:** `month_start`, `month_end`, `quarter_key` (YYYYQ), `quarter_label`, `year`. **Position:** `month_index` (window start = 0; negative only for the pre-window months needed by `implied_start_month_key`, A5), `is_window_start`. **Annotation:** `sm_regime` (config; no calculation uses it) | — | 34 + pre-window months (at least 2021-12) |
| `dim_industry` | table (GLD-02, from a seed) | industry | `industry_key` (1–6; −1 UNKNOWN; −2 UNMAPPED) | `industry_code` (ASCII), `industry_label_es` (as stored, NFC), `industry_label_en`, `chart_label` ("Unknown" for −1 and −2), `is_unknown_member` | — | 8 |
| `dim_customer` | table (GLD-03, SCD1, recomputed every run) | customer | `customer_id` | **Identity:** `customer_label` (`Cliente N`), `industry_key`. **Cohort:** `cohort_month_key`, `cohort_censoring`, `is_new_logo`, `first_payment_ratio`, `first_payment_multiple`, `implied_start_month_key`, `first_payment_band`, `is_first_month_spike`, `first_paid_amount_value`, `last_paid_month_key`. **Outlier:** `is_outlier_customer`, `outlier_source`. No unknown member. An Industry customer with no revenue has NULL cohort attributes | `industry_key` → `dim_industry`. `cohort_month_key`, `implied_start_month_key` and `last_paid_month_key` → `dim_month` (role-played) | 1,961 |
| `dim_spend_category` | table (GLD-04, from a seed) | S&M source column | `category_key` (1–7; −2 UNMAPPED) | `category_code` (the source column name), `spend_group` (media, people, other), `channel_class` (digital_paid, offline, non_media), `is_hr_sensitive`, `display_order` | — | 7 (+ −2) |
| `dim_source_status` | table (CFO-03, from config) | money dataset | `source_status_key` (1 transactions, 2 sm_spend) | `dataset_id`, `currency_code` (NULL), `currency_status`, `revenue_basis_status` or `spend_basis_status`, `basis_hint`, `status_ref` (the owner statement or config version) | — | 2 |
| `fct_customer_month_revenue` | table (GLD-05), dense panel | customer × month | (`customer_id`, `month_key`) | **Money:** `amount` DECIMAL(12,6), `amount_value` DECIMAL(18,2), `amount_normalized`, `amount_normalized_value`. **Flags:** `is_paying`, `is_negative_amount`. **Lifecycle:** `lifecycle_state`, `is_provisional`, `is_churn_event`, `churn_spell_type`. **Settlement:** `settlement_type`, `settlement_confidence`, `is_catch_up`, `is_prepaid`. **Movement (native plus `_value`):** `expansion_amount`, `contraction_amount`, `amount_lag12`. All measures are additive; no ratio is stored | `customer_id` → `dim_customer`; `month_key` → `dim_month`; `source_status_key` → `dim_source_status` | 66,674 |
| `fct_sm_spend_month` | table (GLD-06), partitioned by `hr_sensitive` | month × category | (`month_key`, `category_key`) | `spend` DECIMAL(12,3) (signed, native), `spend_value` DECIMAL(18,0), `is_negative_spend` | `month_key` → `dim_month`; `category_key` → `dim_spend_category`; `source_status_key` → `dim_source_status` (A4) | 238 (102 of them HR-sensitive) |
| `agg_sm_spend_month_group` | table (materialized so that non-Finance roles can read the people total; CDO-11 (2)) | month × `spend_group` | (`month_key`, `spend_group`) | `spend`, `spend_value`, `has_negative_spend` | `month_key` → `dim_month` | 102 |
| `ctl_run` | table | run | `run_id` | **Run:** `state_seq`. **Watermarks:** `as_of_month`, `revenue_complete_through`, `spend_complete_through`, `data_complete_through`, `churn_confirmed_through`. **Per dataset:** `source_key`, `sha256`, `bronze_key`, `_ingested_at`, `is_late`, `latest_delivery_outcome`. **Versions:** `_rules_version`, `_view_version`, `_code_version`. **Status:** `scope_status`, `outlier_set` (ids) and `outlier_rule_version` | — | 1 per run |
| `ctl_month` | table | month | `month_key` | **Presence:** `in_transactions`, `in_sm_spend`, `is_missing_in_other` (SQ-13), `is_sm_month_gap` (SQ-09(b)). **Totals:** `revenue_value_total`, `sm_spend_value_total`. **Tripwire:** `sm_to_revenue_ratio`, `unit_tripwire` (CDO-08), `combined_null_reasons` | `month_key` → `dim_month` | 34 |
| `agg_month_kpis` | view (GLD-07) | month | `month_key` | see below | via the fact | ≤ `revenue_complete_through` |
| `agg_month_sm_spend_per_new_logo` | view (CMO-05) | month | `month_key` | see below | month only | ≤ last month |
| `agg_retention_month` | view (CRO-06) | t × industry × cohort year × `is_outlier_customer`, plus roll-ups | (`month_key`, `grain_level`, `industry_key`, `cohort_year`, `is_outlier_customer`) | see below | via the fact | from 2023-01 |
| `agg_month_industry_cohort` | view (drill-down helper; no new rule) | month × industry × cohort month | (`month_key`, `industry_key`, `cohort_month_key`) | **Additive:** `revenue_value`, `revenue_normalized_value`, `paying_customers`, `new_logos`, `reactivated_customers`, `paused_customers`, `grace_customers`, `churned_customers` (NULL after `churn_confirmed_through`; new logos NULL at the window start). **Average:** `arppu_mean`, with `low_n` (CMO-07) | via the fact | — |
| `agg_cohort_starting_arpa` | view (CRO-07) | cohort month (× industry, with GROUPING SETS) | (`cohort_month_key`, `industry_key` or ALL) | `new_logos`, `first_month_spikes`, `starting_arpa_median` (the first paid amount ÷ `first_payment_multiple` when it is 2 or 3, otherwise the first paid amount; exact median), `low_n` | `dim_customer` | — |
| `snap_<view>` | table per run | as its view | as its view | the frozen output of each view above for that run (D11, D19) | — | — |
| `share_<name>` | table (future, CDO-11 (3)) | per share | per share | money suppressed (`is_suppressed`), counts with `low_n` | — | 0 |

### Join paths and drill-down (total → industry → cohort → customer → month)

| Level | Query | Objects | Control |
|---|---|---|---|
| Total | Σ per month | `agg_month_kpis` (all-in, ex-outlier) | runs to `revenue_complete_through` |
| Industry | group by `industry_key` | `agg_month_industry_cohort` summed over cohorts, or `fct` ⋈ `dim_customer` ⋈ `dim_industry` | Σ industry = total (CDO-04 gold leg) |
| Cohort | group by `industry_key`, `cohort_month_key` (or `cohort_year` in retention) | `agg_month_industry_cohort`, `agg_retention_month`, `agg_cohort_starting_arpa` | `low_n` (CMO-07). Industry acquisition defaults to `quarter_key` |
| Customer | filter by industry and cohort; list `customer_id` | `fct` ⋈ `dim_customer` | (1) roles only (CDO-11 (1)) |
| Month | one customer's 34 rows | `fct_customer_month_revenue` | `lifecycle_state`, settlement, `amount_normalized` |

**Spend has its own hierarchy:** month → `spend_group` → category. Category grain is Finance-only for Team, PayrollExpenses and Freelance.
- **Spend meets revenue only at `month_key` through `dim_month`:** in `ctl_month` and in CMO-05, where the new-logo counts are first aggregated to month from `dim_customer`.
- **No object holds a spend measure together with `customer_id`, `industry_key` or `cohort_month_key`** (CDO-10).
- **The CI lint** (sqlglot over the view DDL and the Glue schemas) fails the build on any other join.

### KPI view columns

| View | Columns |
|---|---|
| `agg_month_kpis` (GLD-07) | **Revenue:** `revenue_value` (Σ `amount_value`), `revenue_value_ex_outlier`, `outlier_customers_excluded`, `outlier_rule_version`.<br>**Payers:** `paying_customers`, `paying_customers_ex_outlier`.<br>**ARPPU:** `arppu_mean` (primary), `arppu_median`, `arppu_mean_ex_outlier`, `arppu_normalized` (Σ `amount_normalized` ÷ customers with `amount_normalized` > 0).<br>**Logos:** `new_logos` (`cohort_censoring` = none, counted in the cohort month), `new_logos_probable_left`, both NULL at `is_window_start`.<br>**Lifecycle counts:** `reactivated_customers`, `paused_customers`, `grace_customers`, `churned_customers` (churn events dated to the spell's first unpaid month; NULL after `churn_confirmed_through`).<br>**Concentration:** `top1_revenue_share`, `top10_revenue_share` (no ids).<br>**Status:** `revenue_basis_status`, `currency_status`, `currency_code`, `revenue_complete_through`, `churn_confirmed_through`, `is_provisional` (month > `churn_confirmed_through`), `null_reasons`.<br>**No spend measure** |
| `agg_month_sm_spend_per_new_logo` (CMO-05) | **Components:** `sm_spend_value_total` and `sm_spend_value_media` (from `agg_sm_spend_month_group`), `new_logos`, `new_logos_probable_left`, and their `_t3m`, `_t6m` and `_t12m` window sums.<br>**Ratios:** `sm_spend_per_new_logo_{m, t3m, t6m, t12m}_{total, media}` (8 columns).<br>**Evidence and status:** `sm_to_revenue_ratio`, `unit_tripwire`, `scope_status`, `spend_basis_status`, `currency_status`, `data_complete_through`, `null_reasons_{m, t3m, t6m, t12m}`.<br>**When a ratio is NULL:** windows are `ROWS BETWEEN n−1 PRECEDING` over the dense `dim_month` rows with `month_index` ≥ 0, so a missing month sits inside its window. A ratio is NULL when its window has fewer than n rows, includes `is_window_start`, passes `data_complete_through`, contains a `unit_tripwire` or `is_missing_in_other` month, or has Σ new logos = 0.<br>**No CAC, payback or LTV column.** The view is excluded from the standard exports, and the export tool refuses an extract that drops a status column |
| `agg_retention_month` (CRO-06) | **Base:** customers whose state at t−12 is new, paying, reactivated or settled_gap.<br>**Components, for each basis** (`amount_normalized` = headline, `_raw`, `_avg3` = the 3-month mean of `amount_normalized`): `base_logos`, `base_revenue`, `revenue_t`, `retained_revenue` (Σ min), `expansion_revenue`, `contraction_revenue`, `lost_revenue_churned`, `lost_revenue_other` (paused or grace), `retained_logos`, `churned_logos`.<br>**Ratios:** `nrr`, `grr` (and their `_raw` and `_avg3` variants) and `logo_churn`, each computed from unrounded sums.<br>**Flags:** `is_provisional` (t > `churn_confirmed_through`), `low_n` (`base_logos` < 10), `null_reasons`.<br>**Roll-ups:** GROUPING SETS with `grain_level` ∈ {total, industry, cohort_year, industry_cohort_outlier}, plus `is_outlier_customer` at each level.<br>**When a value is NULL:** with no 12-month lookback (t < 2023-01; `_avg3` before 2023-03); `logo_churn` after `churn_confirmed_through`.<br>Nothing is named MRR or ARR |

**Conventions:**
- **Medians are exact.** They are computed with `row_number()` and `count()` per group, averaging the middle pair after a cast to a wider scale. `approx_percentile` is never used.
- **Quotients** are computed from unrounded component sums (A9).
- **Every NULL set by a rule** carries its reason in `null_reasons`.

## Security and IAM

### Service roles

No role is granted `s3:DeleteObject*`. Only S3 lifecycle removes data.

| Role | Used by | Allow | Never |
|---|---|---|---|
| `finora-dl-uploader` | the source-system uploader (Q13) | `s3:PutObject` on the 3 registered staging keys only, single-part, with `--checksum-algorithm SHA256` | Get, Tagging, Delete, any other key |
| `finora-dl-gd-malware` | GuardDuty Malware Protection | AWS's documented plan policy, scoped to staging: GetObject and GetObjectVersion, Get and PutObjectTagging, plus its managed EventBridge rule | — |
| `finora-dl-ingest` | `bronze_ingest` | **Staging:** GetObject, GetObjectVersion, GetObjectTagging. **Bronze:** PutObject on `<dataset>/*`, `_manifests/*`, `_deliveries/*`, `_events/*`, `_quarantine/*`, `_rejected/*`; GetObject on `<dataset>/*` (the CTO-01 read-back), `_manifests/*`, `_overrides/*`; PutObjectTagging on `_quarantine/*`. **Silver:** GetObject on `_control/*` | silver or gold writes |
| `finora-dl-silver` | `silver_validate`, `silver_build` | **Bronze:** GetObject on `<dataset>/*`, `_manifests/*`, `_events/*`; PutObject on `_rejected/*`, `_events/*`. **Silver:** PutObject on `store/*`, `_quarantine/*`, `_runs/*`, `_control/state_history/*`; Get and Put on `_control/state.json`. **Gold:** GetObject on `_control/published/*`. **Glue:** Get and BatchCreatePartition on `finora_silver_store` | bronze `_quarantine/*` (explicit deny) |
| `finora-dl-verify` | `dl_verify` | Read-only: bronze `_manifests/*`; silver `store/*`, `_quarantine/*`; gold `store/*`; Glue Get on all 4 databases | any Put |
| `finora-dl-gold` | `gold_build` | Silver GetObject on `store/*`. Gold PutObject on `store/*`. Glue Get and BatchCreatePartition on `finora_gold_store`. Athena in `finora-dl-pipeline` (UNLOAD, via `aws:CalledVia`) | bronze; `_control/published/*` |
| `finora-dl-publish` | `dl_publish` | Gold Get and Put on `_control/published/current.json` (with `If-Match`); Put on `_control/published_history/*`; PutObjectTagging on `store/*` with `s3:RequestObjectTag/retention` ∈ {current, superseded} (silver and gold) | `audit`/`expire` tags |
| `finora-dl-housekeeping` | `housekeeping`, `finora-dl-retain` | PutObjectTagging with `retention` ∈ {expire, audit}. PutObjectLegalHold only with `s3:object-lock-legal-hold` = ON (bronze, silver, gold). Put on gold `_control/retained/*` | legal hold OFF |
| `finora-dl-freshness` | `freshness_check` | Staging ListBucket and GetObjectTagging (no GetObject). Bronze ListBucket on `_deliveries/`. Silver Get on `_control/state.json`. SNS Publish | data reads |
| `finora-dl-sfn` | Step Functions | `lambda:InvokeFunction` on the dl functions; `sns:Publish` on the dl topics; `states:StartExecution` on `finora-dl-run` | — |
| `finora-dl-deploy` | CloudFormation (SAM), through Identity Center with MFA | CloudFormation and the stack's resource types; `iam:PassRole` only for `finora-dl-*` | S3 data access |

### Human permission sets (IAM Identity Center)

CDO-11 (1) and (5): only these sets can read silver or gold.

| Set | Who | Access |
|---|---|---|
| `finora-dl-data` | named Data team | Workgroup `finora-dl-data`. Silver `store/*`, `_quarantine/*`, `_runs/*`. Gold `store/*` (`hr_sensitive=true` denied). Bronze `_rejected/*`, `_manifests/*`. May start `finora-dl-retain` |
| `finora-dl-finance` | named Finance | Workgroup `finora-dl-finance`. Gold `store/*`, including HR. Silver `store/restatement_log/*`, including HR. May start `finora-dl-retain` |
| `finora-dl-revops` | RevOps, including the Revenue and CS leaders | Workgroup `finora-dl-revops`. Gold `store/*` (HR denied). No silver |
| `finora-dl-security` | security on-call | Staging (including `THREATS_FOUND`), bronze `_quarantine/*`, `_manifests/*`, `_rejected/*`. Put on `_overrides/*` (`If-None-Match`). May start a release ingest. CloudTrail read |
| `finora-dl-cdo-review` | the CDO | Bronze `_quarantine/*` only where `s3:ExistingObjectTag/quarantine_rule` = `CDO-02` |
| `finora-dl-admin` | break-glass (2 named people) | Admin with MFA. Every use alarms |
| (none) | everyone else | No silver or gold access until the `share_` objects exist (CDO-11 (5)) |

### Bucket policies

| # | Buckets | Statement | Implements |
|---|---|---|---|
| P1 | all `al-test-dl-*`, results, trail | Deny `s3:*` when `aws:SecureTransport` = false, or when `s3:TlsVersion` < 1.2 | TLS |
| P2 | same | Deny `s3:DeleteObject*`, `PutBucketPolicy`, `PutLifecycleConfiguration` and `PutBucketVersioning`, except for `finora-dl-deploy` (configuration only) and `finora-dl-admin` | no deletes |
| P3 | same | Deny `s3:*` when `aws:PrincipalAccount` ≠ 962482423379 | no cross-account access |
| P4 | bronze, silver, gold | Deny PutObject on data, manifest, store, history and override prefixes when the `s3:if-none-match` condition key is absent. Exception: `finora-dl-gold` with `aws:CalledVia` = athena on `store/snap_*`, because `UNLOAD` already refuses a non-empty prefix | write-once (CTO-02, CTO-10) |
| P5 | silver, gold | Deny PutObject on `_control/state.json` and `_control/published/current.json` when the `s3:if-match` condition key is absent | CAS |
| P6 | silver, gold | Deny GetObject on `*/hr_sensitive=true/*` unless the principal is `finora-dl-finance`, silver, verify, gold or admin | CDO-11 (2) |
| P7 | bronze | Deny GetObject on `_quarantine/*` unless the principal is `finora-dl-security`, or `finora-dl-cdo-review` with the tag `CDO-02` | quarantine access |
| P8 | staging | Deny GetObject when `s3:ExistingObjectTag/GuardDutyMalwareScanStatus` = `THREATS_FOUND`, unless the principal is security or gd-malware | BRZ-03 |
| P9 | staging | Deny `PutObjectTagging`, and PutObject carrying `s3:RequestObjectTagKeys`, unless the principal is gd-malware | scan-tag forgery |
| P10 | bronze, silver, gold | Deny PutObjectTagging when `s3:ExistingObjectTag/retention` = `audit`, and deny PutObjectLegalHold with OFF, unless the principal is admin | D19 |
| P11 | gold | Deny `share/*` to everyone except `share_build`, until a share is approved | CDO-11 (5) |
| P12 | bronze | Deny PutObject on `_overrides/*` unless the principal is `finora-dl-security` | release control |

### Encryption, logging and audit

- **At rest:**
  - SSE-S3 (AES-256) stays the default. SSE-C is already blocked, and P1 plus a deny on any other `x-amz-server-side-encryption` value enforce it.
  - **Recommended option** (user decision, +$1/month): one customer-managed KMS key, `alias/finora-dl`, with S3 Bucket Keys on bronze, silver and gold. The key policy adds a second gate, so an over-broad S3 grant still cannot decrypt, and every decrypt is logged.
  - Athena results use SSE-S3 (or the same key).
- **In transit:** P1.
- **Secrets:** there are none. Lambdas use their role credentials, and no environment variable holds a secret.
- **Logs:**
  - Logs carry no amounts, customer ids or cell values: only counts, line numbers and rule ids.
  - CloudWatch log groups keep 90 days.
  - SNS follows the same rule.
- **CloudTrail:**
  - One multi-region trail with management events (read and write) and S3 data events (read and write) for staging, bronze, silver, gold and results. All reads are logged, for CDO-11 audits and SOC 2.
  - Log-file validation is on.
  - The trail bucket `al-test-dl-audit-trail` has versioning, P1–P3, and 365-day retention pending Q15.
- **Detection:**
  - An EventBridge rule on CloudTrail alerts `finora-dl-security` on root activity, console sign-in without MFA, IAM policy changes and changes to the dl bucket policies.
  - IAM Access Analyzer (external access, free).
  - Account-level S3 Block Public Access.
  - **Optional:** GuardDuty threat detection. Price it after the 30-day trial, because the account also carries the toldo and radar-emprendedor projects.

### Access model by layer

| Area | Pipeline roles | Security | CDO | Data | Finance | RevOps | Others |
|---|---|---|---|---|---|---|---|
| Staging | ingest (read), uploader (put) | read, including threats | — | — | — | — | — |
| Bronze data | ingest (write), silver and verify (read) | — | — | — | — | — | — |
| Bronze `_manifests/`, `_rejected/` | write and read | read | — | read | — | — | — |
| Bronze `_quarantine/` | ingest (write) | read | CDO-02-tagged objects only | — | — | — | — |
| Silver `store/` (customer-level) | silver (write), gold and verify (read) | — | — | read | `restatement_log` only | — | — |
| Silver and gold `hr_sensitive=true` | silver, gold, verify | — | — | **deny** | read | **deny** | — |
| Silver `_quarantine/` (rows) | silver | — | — | read | — | — | — |
| Gold `store/` | gold (write) | — | — | read | read | read | **none until shares exist** |
| Gold `share/` | `share_build` | — | — | — | — | — | the approved outside role, later |

### Moving off the root keys (the account owner; this blocks build step 2 onward)

1. Create the CloudTrail trail and the root-activity alert first, so the next steps are recorded.
2. Create AWS Organizations, with this account as the management account (free), and enable an organization instance of IAM Identity Center. An account instance can't grant AWS account access. Then create `finora-dl-admin` (MFA) and `finora-dl-deploy`.
3. Switch the `alegra-test` profile to `aws configure sso` and confirm that `aws sts get-caller-identity` no longer shows `:root`. Then update `.claude/CLAUDE.md`, with approval.
4. Check that the toldo and radar-emprendedor projects don't use the root keys: the credential report's `access_key_last_used_service`, and one week of CloudTrail history.
5. Deactivate the keys, wait 7 days with the alert armed, then delete them. Keep root MFA; root is for the break-glass procedure only.

## Versioning, retention and snapshots

How D19 is applied:
- **Retained runs:** a month-close run, or one behind a figure shared outside (1), is kept with no expiry until legal sets the audit period.
- **Other runs:** a superseded run expires 30 days after supersession.
- **Bronze:** bronze snapshots and manifests live at least as long as the retained runs that read them.

| Bucket | Versioning | Object Lock | Lifecycle | D19 mechanics |
|---|---|---|---|---|
| `al-test-dl-staging` | **Enable** | no | Noncurrent versions expire after 365 days; incomplete multipart uploads abort after 7 days | Not a run input after bronze. Staging stays the landing zone, read-only for the pipeline |
| `al-test-dl-bronze` | **Enable** | **Enable** (governance, no default retention; user decision, irreversible) | Data, `_manifests/`, `_deliveries/`, `_events/` and `_rejected/`: no expiry until Q15. `_quarantine/`: 365 days. Multipart uploads abort after 7 days | `finora-dl-retain` places a legal hold on the bronze objects and manifests listed in a retained run's `ctl_run` |
| `al-test-dl-silver` | **Enable** | **Enable** (as above) | Objects tagged `retention=expire` expire after 1 day; noncurrent versions are purged after 1 day; `_control/` never expires. Multipart uploads abort after 7 days | **Each run's objects carry `retention`:** written as `current`; on publish, the previous run becomes `superseded`; 30 days later, `housekeeping` sets `expire`. **Retained:** `audit` plus a legal hold (P10 blocks re-tagging). **Failed runs:** `expire` 30 days after the failure |
| `al-test-dl-gold` | **Enable** | **Enable** (as above) | As silver. `_control/` never expires; `_exports/` expire after 90 days | As silver. The `snap_` tables make the retained run the month-close copy of CMO-05 and the other views (D11) |
| `al-test-dl-athena-results` (new) | off | no | 7 days | — |
| `al-test-dl-audit-trail` (new) | **Enable** | optional | 365 days, pending Q15 | — |
| `al-test-datalake` (legacy) | unchanged | no | — | Deletion is the user's decision. Until then, P1–P3 and no grants |

**Default retention for month-close runs, until Q13 says when a month closes:** the first published run with each new `revenue_complete_through` is retained automatically, and Finance can retain any other run through `finora-dl-retain`. **The legal hold is deliberately not compliance-mode retention:** if Q16 allows erasure, the admin can lift a hold after recording a decision, whereas compliance mode could never be lifted.

## Cost

| Item | Assumption (list prices, us-west-2) | $/month |
|---|---|---|
| S3 storage | about 0.3 GB across the layers, including 30 days of runs, retained runs and versions, at $0.023/GB | 0.01 |
| S3 requests | about 5,000 PUT, COPY or LIST plus about 50,000 GET (including Athena) | 0.05 |
| Athena | about 1,500 queries at the 10 MB minimum (about 15 GB) at $5/TB, plus 5 `UNLOAD`s per run | 0.08 |
| Lambda | about 20 runs × about 30 GB-s, plus ingests; free tier (400,000 GB-s) | 0.00 |
| Step Functions Standard | about 1,500 transitions; free tier (4,000) | 0.00 |
| GuardDuty Malware Protection (S3) | about 30 objects and under 0.1 GB; free tier, about $0.02 after it | 0.00 |
| EventBridge (AWS events), Scheduler, SNS email | free tiers | 0.00 |
| Glue Data Catalog | under 1 million objects and requests; free | 0.00 |
| CloudTrail | first trail's management events free; about 50,000 S3 data events at $0.10 per 100,000; logs under 0.1 GB | 0.06 |
| CloudWatch | Logs ingest under 0.2 GB at $0.50/GB; 5 alarms at $0.10 | 0.60 |
| Identity Center, Organizations, Access Analyzer (external) | free | 0.00 |
| **Total** | | **about $0.80** |
| Optional: KMS key, with bucket keys | $1 per key-month, plus requests | +1.00 |
| Optional: GuardDuty threat detection | volume-based; 30-day trial first | to be priced |

**Development and CI:** $0. The golden run executes locally over `data/`, with no AWS calls.

## Build order

**Every AWS step needs the user's explicit approval for that step, and evidence after it:** settings, the policy simulator, or checksums.

| # | Step | AWS change | Blocked by |
|---|---|---|---|
| 0 | Put the repo under git with CI. Write the config `dl_rules.yaml` (registry, factors, ceilings, seeds, parameters, statuses), the code, the SAM templates and the tests. The golden run reproduces every CDO figure locally | no; repo files only, with the user's OK | user OK to write files; A1–A9 only for the defaults they touch |
| 1 | The account owner moves off the root keys (§ Security) | yes (owner) | owner availability |
| 2 | Account baseline: account-level Block Public Access, Access Analyzer, SNS topics, the break-glass role, alerts | yes | 1 |
| 3 | Storage: versioning on 4 buckets, Object Lock, policies P1–P12, lifecycle, the results bucket, 4 workgroups, Glue databases, (KMS) | yes | 1; Object Lock and KMS decisions |
| 4 | Ingest: GuardDuty plan, EventBridge rule, `finora-dl-ingest`, `bronze_ingest`. Self-tests in staging: EICAR, an unregistered key, an oversize file, a 0-byte file (to confirm GuardDuty's status for empty objects). Then **re-upload the 3 files** (identical bytes, with SHA-256) so they get scanned, because GuardDuty scans only new objects. Evidence: CTO-01 matches the 3 staging SHA-256 values | yes, plus data uploads | 3; A1, A2, A8; the bronze-name decision |
| 5 | Silver: `silver_validate`, `silver_build`, `state.json`, the 3 acceptances | yes | 4; A3, A9 |
| 6 | Gold and publish: `gold_build`, `dl_verify`, `dl_publish`, Glue tables and views, snaps, the CDO-04 legs, the CDO-10 lint. First publish | yes | 5; A4, A5, A7 |
| 7 | Operations: `freshness_check`, `housekeeping`, `finora-dl-retain`, runbook, `.claude/CLAUDE.md` | yes | 6 |
| 8 | Human access: the Data, Finance, RevOps, security and CDO-review sets for named people; policy-simulator tests | yes | 6; A6 |
| 9 | The export tool (CTO-09) | no AWS resource | before the first export |
| 10 | `share_build` and the share zone (CDO-11 (3)) | yes | the first request for an outside grant, plus the CDO's sign-off on each share |
| 11 | Delete `al-test-datalake` | yes | user decision |

## Rule traceability

Every rule ID in `cdo_rules.md` appears exactly once below: 61 rules (bronze 11, silver quality 15, silver business 17, gold 18).
- "Golden" means the run over today's 3 files must reproduce the CDO's figure exactly, in `Decimal`.
- "Fixture" means a crafted failing input in the unit tests.

| Rule ID | Layer | Implemented in (job / table / view / policy) | Test |
|---|---|---|---|
| BRZ-01 | Bronze | `bronze_ingest` step 9; manifest `content_type`, `content_type_flag` | Fixture: Content-Type `application/octet-stream` → accepted and flagged. Golden: 3 × `text/csv; charset=utf-8`, 0 flags |
| BRZ-02 | Bronze | `bronze_ingest` step 4 (HEAD size); ceilings in config (50 / 5 / 1 MB) | Fixture: 0 B → reject. Ceiling + 1 B → quarantine, and the mock asserts no GetObject. Build step 4 self-test |
| BRZ-03 | Bronze | GuardDuty plan + EventBridge; `bronze_ingest` step 2; staging policies P8 and P9 | EICAR → `THREATS_FOUND` → quarantine, with the ingest role's GetObject denied. `UNSUPPORTED` / `FAILED` / `ACCESS_DENIED` → quarantine. A forged tag is denied (P9) |
| BRZ-04 | Bronze | `bronze_ingest` step 8; manifest hit and exempt counts | Fixture: `=HYPERLINK(...)`, `@x`, a TAB-led cell → quarantine. Golden: 5 exempt (`-$0.0xx`), 0 hits |
| BRZ-05 | Bronze | `bronze_ingest` step 1; registry allowlist; `_quarantine/_unregistered/` | Fixture keys: `..`, `//`, a leading `/`, a control byte, non-ASCII, 1,025 B, an unregistered key → quarantine. The `S%26M_spend.csv` event form matches. Grep test: the key is never used in path building |
| BRZ-06 | Bronze | `bronze_ingest` step 10 (writer) | Golden: the BOM, CRLF and record order are kept; Industry's `,` → `,,<ts>`; one `_ingested_at` value per object, ending in `Z` |
| CDO-01 | Bronze | `bronze_ingest` step 6 | Fixture: invalid UTF-8, a NUL, a TAB, a ragged line → reject. Golden: field counts 3 / 2 / 8 |
| CDO-02 | Bronze | `bronze_ingest` step 7; versioned registry; `quarantine_rule=CDO-02` tag; `finora-dl-cdo-review` | Fixture: a reordered, renamed, extra or missing column → quarantine; a registry bump then passes it |
| CTO-01 | Bronze | `bronze_ingest` step 11 (read-back); re-checked in `silver_build` | Golden: the stripped bronze SHA-256 equals the 3 staging SHA-256 values. Fixture: a writer that drops the BOM → reject |
| CTO-02 | Bronze | `bronze_ingest` steps 3, 5, 12; `_manifests/` (P4); A1 and A2 | Schema test of every manifest field. A second PUT → 412. The ETag changed after the scan → quarantine. The manifest PUT fails → reject. Control totals = 221,441.504508 / 77.818 / 1,962 rows |
| CTO-03 | Bronze | `bronze_ingest` step 10; `_deliveries/`; `state.json` restore | Fixture A, B, A: no new bronze object and the same `_ingested_at`; A is re-validated. A corrected re-upload under the same key → a new SHA-256 and a new object |
| SQ-01 | Silver | `silver_validate`, `silver_build` reader (`utf-8-sig`, CRLF, `Decimal` from strings) | Golden: no float anywhere (a type assertion on the Arrow schema). Fixture: no header → reject. A missing final newline is tolerated |
| SQ-02 | Silver | reader → `_quarantine/industry/` `EMPTY_RECORD` | Golden: 1,962 = 1,961 + 1. Fixture: an empty record mid-file, or in Transactions → quarantine + flag + data alert |
| SQ-03 | Silver | `silver_validate` (industry) | Fixture: `Cliente 094`, `Cliente 0` → row quarantine. Duplicate `Cliente 5` → reject. Golden: 1,961 unique |
| SQ-04 | Silver | `silver_build`: NFC normalization + seed map → `industry_key` | Fixture: NFD `Producción` → mapped. `Agro` → −2 UNMAPPED, flag and alert, row kept. Golden: 6 values |
| SQ-05 | Silver | `silver_validate` (transactions) | Fixture: a duplicate (ID, month) → reject, listing both lines. `12a` → reject. Golden: 0 duplicates |
| SQ-06 | Silver | `silver_validate`: a strict non-padded pattern, `strptime('%m/%d/%Y')`, and a last-day-of-month check (A9) | Fixture: `1/30/2022` → reject; `01/31/2022` → reject (A9). Golden: 34 month-ends |
| SQ-07 | Silver | `silver_validate` (a): strict decimal grammar (A9); `silver_build` (b): `is_negative_amount` | Fixture: `abc`, `1e3`, `NaN`, an empty value → reject with no substitution. `-1.5` → kept, flagged, not paying, in every sum |
| SQ-08 | Silver | `silver_validate`, after CDO-05 | Fixture: delete one customer-month → reject. Golden: 66,674 = 1,961 × 34 |
| SQ-09 | Silver | `silver_validate` (a); `month_control.is_sm_month_gap` (b) | Fixture: a duplicate `2023-05` or `2023-5` → reject. Drop `2023-05` → flagged, absent, not zero-filled |
| SQ-10 | Silver | `silver_validate` (sm_spend) | Fixture: `$12.5`, `12.500`, `$1234567.000` → reject. Golden: 238 cells, 5 negative |
| SQ-12 | Silver | `silver_build` lookups → −1 UNKNOWN; `silver.customer` union | Fixture: a Transactions customer missing from Industry → −1, flagged, revenue kept. An Industry customer with no revenue → kept with NULL cohort |
| SQ-13 | Silver | `month_control.is_missing_in_other` → CMO-05 NULL | Fixture: S&M without 2024-10 → flag, and CMO-05 NULL for 2024-10 and its windows |
| CDO-04 | Silver | `dl_verify`, both legs | Golden: 66,674 rows, Σ 221,441.504508 (full: 2,214,415,045.08); 238 cells, Σ 77.818; 1,962 = 1,961 + 1; logos 377 + 43 + 1,541 + 0 = 1,961; count(new) = 1,541. Fixture: one tampered silver row → run reject |
| CDO-05 | Silver | `silver_validate` scale and overflow checks; explicit decimal Arrow schema | Fixture: a 7-decimal amount → reject; 4-decimal spend → reject; an overflow of DECIMAL(18,2) → reject. Golden: the 2,436 float-trap rows and the 32 float-trap cells are exact |
| CDO-06 | Silver | `silver_validate` diff against the previous accepted snapshot; `restatement_log`; finance alert | Fixture: drop one customer-month, Industry customer or S&M month → reject. Change an amount in a published month → flag + finance alert. First acceptance → `baseline` |
| SB-01 | Silver | `silver_build`: `amount_value = amount × 10000` from config, in exact `Decimal` | Golden: 25 → 250,000 and Σ 2,214,415,045.08. An overflow is asserted unreachable after CDO-05 (run reject) |
| SB-02 | Silver | `silver_build`: `spend_value = value × 100000000`, sign kept | Golden: 1.04 → 104,000,000; every value is an integer; the negatives total −13,500,000 |
| SB-03 | Silver | `transactions.is_paying` (`amount` > 0) | Fixture: 0 and −x → unpaid; 0.14 → paying. Golden: 50.6% zero rows |
| SB-04 | Silver | `silver.customer`: cohort, ratio, j ∈ {2, 3} at ±5% × j, implied start, censoring | Golden: 377 left / 43 probable_left / 1,541 none; Feb-2022 has 68. With config j = {2}: 34 / 1,550 |
| SB-05 | Silver | `customer_month`: churn spells (internal or trailing), grace, `is_churn_event`; `churn_confirmed_through` | Golden: churn events Jun–Oct 2024 = 15, 18, 14, NULL, NULL; 46 grace customers; 237 open trailing spells; `churn_confirmed_through` = 2024-08 |
| SB-06 | Silver | `silver.gap`: arrears, then prepay, then split, first match wins; flags on unpaid and settling months | Golden: 468 gaps; 155 / 47 / 9; 202 high-confidence. Fixture: a gap matching both arrears and split → arrears. Amounts are unchanged (a checksum) |
| SB-07 | Silver | `customer_month`: `reactivated`, `paused` | Golden: 64 reactivations (60 customers), 193 paused gaps. Fixture: a reactivated customer keeps its cohort and is not a new logo |
| SB-08 | Silver | `silver.customer.is_outlier_customer`, `outlier_source`; owner overrides in config; `restatement_log` + data alert | Golden: {94, 322}, with portfolio median 5.25. Fixture: 543 (1 payment) is excluded; an owner override is applied; a set change → alert |
| SB-09 | Silver | `silver.customer.industry_key`, applied to the whole history (SCD1) | Fixture: an industry change in a new snapshot → the whole history restated, plus a CDO-06 flag |
| SB-10 | Silver | `silver.sm_spend`: sign kept, `is_negative_spend`; an alert outside PayrollExpenses; monthly total = Σ 7 categories | Golden: 5 negatives, −13,500,000. Fixture: a negative Travel cell → finance and data alert. No `abs`, clip or floor (grep test) |
| CDO-07 | Silver | `customer_month.lifecycle_state`, `is_provisional` | Golden: paying 31,366; pre_acquisition 29,321; churned 3,811; new 1,541; settled_gap 281; paused 231; reactivated 64; grace 59; 5,399 provisional. Exactly one state per row, else run reject |
| CDO-08 | Silver | `month_control.sm_to_revenue_ratio`, `unit_tripwire`, bounds [0.5, 20] from config | Golden: 1.61–7.62×, 0 trips. Fixture: S&M ×10 → 28 of 34 months trip; ÷10 → 21; the CMO-05 windows containing them are NULL |
| CFO-03 | Silver | `silver.source_status` → `dim_source_status`; `source_status_key` on both facts | Test: 2 rows, `currency_code` NULL, statuses `unconfirmed`, `basis_hint` set. Lint: every KPI view exposes the status columns |
| CFO-05 | Silver | `scope_status` from config → `ctl_run` → CMO-05 | Lint: no expression derives `scope_status` from the ratio; the ratio is published beside it |
| CRO-03 | Silver | `customer_month.amount_normalized` (truncated shares, remainder to the payment month) | Golden: Σ normalized = Σ amount for each of the 1,961 customers. Lint: no revenue total and no `is_paying` reads `amount_normalized` |
| CRO-05 | Silver | `customer_month`: `expansion_amount`, `contraction_amount`, `amount_lag12` | Golden: expansion 2.36% and contraction 2.37% of prior revenue. Fixture: paused → paying gives Δ = 0 |
| CRO-07 | Silver | `silver.customer`: `first_payment_band`, `is_first_month_spike` → `dim_customer`; `agg_cohort_starting_arpa` | Golden: 116 of 1,470 at ≥ 1.9×, 64 at ≥ 3×; median starting ARPA 42,000 |
| GLD-01 | Gold | `dim_month`, generated from config and the accepted snapshots | Golden: 34 contiguous months, 2022-01 `is_window_start`, plus pre-window rows for `implied_start_month_key` (A5). PK unique, else run reject |
| GLD-02 | Gold | `dim_industry` from the seed | Golden: 8 rows; RESTAURANTS 529, MANUFACTURING 454, RETAIL 428, TECHNOLOGY 241, PROFESSIONAL_SERVICES 165, HEALTHCARE 144 |
| GLD-03 | Gold | `dim_customer` | Golden: 1,961 rows, no −1 member, PK unique; Industry-only customers have NULL cohort attributes |
| GLD-04 | Gold | `dim_spend_category` from the seed | Golden: 7 rows; media 59.3%, people 30.0%, other 10.7%. Fixture: a registered column without a seed row → −2 and a flag |
| GLD-05 | Gold | `fct_customer_month_revenue` | Golden: 66,674 rows, unique PK, 0 ratio columns (lint), Σ equal to silver |
| GLD-06 | Gold | `fct_sm_spend_month` (`hr_sensitive` partition) | Golden: 238 rows, 5 negative, PK unique. Lint: only `dim_month` and `dim_spend_category` (plus A4) |
| GLD-07 | Gold | view `agg_month_kpis` + `snap_agg_month_kpis` | Golden: top-1 4.77%, top-10 10.83%; Sep and Oct 2024 churn NULL (not 0); 2022-01 new logos NULL; the last row is `revenue_complete_through`; no spend column (lint) |
| CMO-05 | Gold | view `agg_month_sm_spend_per_new_logo` + snap; excluded from the standard export config | Golden: Feb-22–Oct-24 components 7,581.8M ÷ 1,541 = 4,920,052. Fixture: each NULL condition. Lint: no `cac`, `payback` or `ltv`. The export tool refuses an extract without the status columns |
| CRO-06 | Gold | view `agg_retention_month` + snap | Golden: Aug-2024 NRR / GRR 91.4% / 86.5%, logo churn 9.9% (102 / 1,034); Oct-2024 92.9% / 85.9% (provisional), `_raw` 93.2% / 85.8%, `_avg3` 96.2% / 87.3%; Aug-2023 `_raw` 79.8% vs 88.9% |
| CDO-10 | Gold | CI lint (sqlglot over the view DDL and the table schemas) + `dl_verify` on the Glue catalog | Fixture: a view joining spend to `dim_customer`, or a table with `spend_value` and `industry_key` → CI fails and the run rejects |
| CDO-11 | Gold | Permission sets; P6, P7, P11; the per-role workgroups; `agg_sm_spend_month_group`; `share_build` (gated) | Policy simulator: Data and RevOps denied `hr_sensitive=true`; RevOps denied silver; any other principal denied gold. `share_build`: no group with exactly one suppressed cell, and counts never suppressed |
| CMO-07 | Gold | `low_n` in `agg_retention_month`, `agg_month_industry_cohort`, `agg_cohort_starting_arpa` and the shares; the quarter-grain standard export | Golden: 141 of 198 industry × month new-logo cells `low_n`, 16 of 72 by quarter |
| CMO-08 | Gold | `dim_month.sm_regime` from config (boundary 2023-06) | Lint: no view or job uses `sm_regime` in an expression |
| CTO-06 | Gold | the lineage columns on every silver and gold row; `ctl_run` for multi-source rows | Schema test: the 6 columns are present and non-null in every table and view; `_source_sha256` resolves through `ctl_run` |
| CTO-07 | Gold | `ctl_run` watermarks and `is_late_*`; view row limits | Fixture: S&M late → revenue KPIs advance, CMO-05 NULL beyond `data_complete_through`, a late flag and an alert |
| CTO-08 | Gold | the −1 and −2 members in the dims; `gold_build` alerts; `dl_verify` | Fixture: an orphan customer → −1 and a data alert; a fact month missing from `dim_month` → run reject |
| CTO-09 | Gold | `finora-dl-export` library and CLI | Fixture: text `=cmd` → `'=cmd`, counted; typed `-0.016` is not escaped; an untyped column → the export fails; a non-gold source → refused |
| CTO-10 | Gold | `run_id=` prefixes (P4); `dl_publish` CAS (P5); retention tags (P10); `housekeeping`; `finora-dl-retain` | Fixture: `dl_verify` fails → pointer unchanged. An older run finishing late → not published. A superseded run is tagged `expire` at 30 days; a retained run never is |

## Open questions

### A. For the CDO: rules that can't be built exactly as written

Each row has a proposed default. I build it only after the CDO confirms it or replaces it.

| # | Rule IDs | What blocks it | Proposed default (pending the CDO) | Blocks step |
|---|---|---|---|---|
| A1 | CTO-02 × BRZ-02, BRZ-03, BRZ-05 | A file quarantined *unread* (oversize, failed scan or bad key) has no "SHA-256 of the bytes read", so `_manifests/<dataset>/<sha256>.json` can't be keyed. For `THREATS_FOUND`, P8 denies the read anyway | Key it as `_manifests/<dataset or _unregistered>/unread__<etag>__<versionid>.json`, or by the S3-held SHA-256 when the uploader sent one. If the file is later released, it gets its normal SHA-256 manifest | 4 |
| A2 | CTO-02 (write-once, "the outcome with its rule id") × file-quarantine release, and retry after our own defect | The manifest can't be rewritten, so a release, or a retry after a CTO-01, BRZ-06 or manifest-write failure, can't change its outcome | The manifest records the *first* outcome. Later outcomes are write-once `_events/<dataset>/<sha256>/…` records (release, retry, restore), and the current outcome is the latest event. Retrying after our own defect needs a recorded event, like a release | 4 |
| A3 | CTO-03 × CDO-06 | A, B, A: CTO-03 says A "becomes current again", but if A lacks keys that B has (for example B added a month), CDO-06 rejects A as removed history. An owner-approved rollback is impossible | Built literally: A is re-validated and rejected. The CDO should decide whether an owner-approved rollback may pass CDO-06 through a recorded override | 5 |
| A4 | CDO-10 × GLD-06 and CFO-03 | GLD-06 and CFO-03 put the `dim_source_status` key on the spend fact, and CMO-05 must show its statuses. CDO-10 lists `dim_month` and `dim_spend_category` as the *only* dimensions joined to spend, so the literal lint fails GLD-06 | Lint allow-list = {`dim_month`, `dim_spend_category`, `dim_source_status`}. The last is one row per dataset with no customer, industry or cohort key, so it can't allocate spend | 6 |
| A5 | GLD-01 × GLD-03 | GLD-01 covers "every month of the accepted snapshots", but `implied_start_month_key` (role-played on `dim_month`) reaches 2021-12 for the 6 Feb-2022 3× logos, and possibly 2021-11 for 2022-01 cohorts | Extend `dim_month` back to the earliest implied start, with negative `month_index`. Every view's window logic uses `month_index` ≥ 0 | 6 |
| A6 | CDO-11 (2) × the quarantine access in the onFailure table | A quarantined sm_spend file holds Team, PayrollExpenses and Freelance at category grain. The onFailure table makes it readable by the security role (and by the CDO for CDO-02), while CDO-11 (2) says only Finance | Security keeps read access, needed for forensics, and every read is logged by CloudTrail data events. The CDO decides whether a Finance co-reader or a Finance-only view is required for sm_spend | 8 |
| A7 | CDO-04 (logo identity) | "Industry customers with no revenue" doesn't cover a Transactions customer whose rows are all ≤ 0: it has no `cohort_censoring`, so the identity would fail. There are 0 such customers today | Implement the term as "`dim_customer` rows with `cohort_month_key` NULL" (any source) | 6 |
| A8 | Bronze evaluation order | The CDO places "CTO-02 checksum" before BRZ-02, but checking bytes means reading them, and BRZ-02 says oversize is quarantined *unread* | Split CTO-02 into (a) a HEAD identity check before BRZ-02 and (b) a byte checksum at the first read, before CDO-01 | 4 |
| A9 | SQ-06, SQ-07(a), SB-04, plus every quotient | Literal readings: (i) SQ-06 cites `%m/%d/%Y`, which also accepts padded dates. (ii) Python `Decimal` accepts `1e3`, `NaN` and `Infinity`. (iii) SB-04's `implied_start_month` when j is NULL. (iv) CDO-05 forbids rounding, but means, `÷ j`, `_avg3` and ratios need a scale | (i) A strict non-padded pattern: `01/31/2022` rejects. (ii) Strict grammar `^-?\d+(\.\d+)?$`. (iii) NULL. (iv) Quotients are computed from unrounded sums and published as DECIMAL(38,12), HALF_UP, and are never fed back into money columns | 5, 6 |

### B. Decisions for the user and the account owner

1. **Root keys.** The account owner runs the migration in § Security: Organizations plus Identity Center, then deletes the keys. This blocks every AWS step.
2. **Bronze names.** Name bronze objects by dataset id (`sm_spend/…/sm_spend__<ts>__<sha8>.csv`), with the verbatim `s_and_m/S&M_spend.csv` kept in the manifest. The CDO recommends this, and I agree. If you keep `S&M`, BRZ-05 still bans interpolating the key, and every tool needs `%26` handling.
3. **Re-uploading the 3 staging files** (identical bytes, with SHA-256), so GuardDuty scans them. BRZ-03 blocks the unscanned originals. This is a data upload.
4. **Versioning** on staging, bronze, silver and gold (recommended), and **Object Lock** on bronze, silver and gold (recommended; irreversible; governance mode with legal holds only).
5. **KMS key** for bronze, silver and gold: +$1/month, recommended.
6. **Legacy bucket** `al-test-datalake`: delete it, or keep it under P1–P3.
7. **Version control.** The repo is not a git repository, and the CDO-10, CTO-09 and naming lints need CI.
8. **Approval of each build step**, and of writing the code, config and IaC into the repo (step 0).

### C. Owner answers that change the design (not only config)

| Q | Design impact |
|---|---|
| Q8 (full snapshot or increment) | **If deliveries are incremental:** CDO-06 and CTO-10 change from snapshot replacement to merge, and Iceberg becomes worth its cost. **If they are full:** this design stands |
| Q13 (cadence, uploader, month close, time zone) | The uploader role's principal, the freshness SLA in `freshness_check`, and automatic retention of month-close runs (replacing the default "first run per new watermark") |
| Q14 (stability of names, headers, BOM, CRLF) | The registry update process and notice period; CTO-01 depends on the BOM and CRLF staying stable |
| Q15 (retention period, residency) | **Retention period:** switch the legal holds to governance retention dates, and set the expiries for quarantine, CloudTrail and `_rejected/`. **Residency:** confirms us-west-2 for every bucket and for the trail |
| Q16 (erasure) | Erasure of retained runs and bronze snapshots: lift the legal hold, then delete as admin, then rebuild. It also needs a CDO-06 exemption for the erased keys (see A3) |
| Q10 (HR boundaries) | The `is_hr_sensitive` set, and with it the P6 partitions and `agg_sm_spend_month_group` |
| Q12 (an allocation key) | The CDO-10 lint allow-list, plus the first spend-to-customer object |
| Q1–Q7, Q9 | Config only (factors, statuses, parameters, seeds, overrides), followed by a rebuild |
