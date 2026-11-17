# Deploy evidence: Finora DQ data lake (us-west-2, account 962482423379), 2026-11-17 UTC

## Tests before deploy
- etl: 53 passed (golden run = every figure of approved_data_rules.md § Expected results; 26 dirty/hole fixtures; bronze round-trip; moto end-to-end)
- auth: 19 passed (ported el_toldo tests + cookie, rate limit, session revocation)
- dq_api: 13 passed (401 on every /api/dq/* route, 403 password_change_required, finance vs data/revops masking, q never matches restricted values, paging)
- cdk synth: 5 stacks OK; cdk diff saved to infra/deploy_diff.txt (no destroy/replace)

## Changes made
1. cdk bootstrap aws://962482423379/us-west-2 (CDKToolkit).
2. FinoraDlStorage: IMPORT change set (Import x3 only: al-test-dl-staging/-bronze/-silver, DeletionPolicy Retain) -> IMPORT_COMPLETE. `cdk import` itself was refused by CloudFormation (an import may not add RoleArn/Tags); the same template and mapping were imported with `aws cloudformation create-change-set --change-set-type IMPORT`. Then a normal deploy: versioning, TLS-only policies, lifecycle, staging EventBridge; new buckets al-test-dl-serving and al-test-dl-athena-results.
3. FinoraDlEtl, FinoraDqAuth, FinoraDqApi, FinoraDqWeb deployed (FinoraDlEtl redeployed once: Parquet codec fix).
4. finora-dl-ingest started twice by hand with the 3 staging keys: first-load-all-three FAILED (pyarrow in the managed layer has no ZSTD; recorded as failed in runs.json, nothing published); first-load-all-three-retry SUCCEEDED, run r20261117T020252Z.

## Stack outputs
```
ApiEndpoint = https://dx2tg0v3a8.execute-api.us-west-2.amazonaws.com
AlertTopicArn = arn:aws:sns:us-west-2:962482423379:finora-dl-alerts
StateMachineArn = arn:aws:states:us-west-2:962482423379:stateMachine:finora-dl-ingest
Url = https://d1smzfxmkay9lx.cloudfront.net
SiteBucket = finoradqweb-sitee53d7754-avnigxub3kvj
WebSource = out
```

## Buckets after deploy
```
al-test-dl-staging versioning=Enabled eventbridge={"EventBridgeConfiguration":{}} lifecycle=noncurrent-and-multipart
al-test-dl-bronze versioning=Enabled eventbridge= lifecycle=noncurrent-and-multipart
al-test-dl-silver versioning=Enabled eventbridge= lifecycle=noncurrent-and-multipart
al-test-dl-serving versioning=Enabled eventbridge= lifecycle=noncurrent-and-multipart
al-test-dl-athena-results versioning=None eventbridge= lifecycle=expire-7d
```

## Staging untouched (keys, sizes, ETags as before; VersionId null = pre-versioning objects)
```
industry/Industry.csv	49402	"4d04f745051f8a06aaff813ac422de51"	null
s_and_m/S&M_spend.csv	2063	"71592d3292d540824085aa2a2aaba43b"	null
transactions/Transactions.csv	1302387	"ae01140d09abe202c873dcd6edc18718"	null
```

## Pipeline
```
first-load-all-three-retry	SUCCEEDED	2026-11-16T21:02:50.908000-05:00
first-load-all-three	FAILED	2026-11-16T20:59:20.798000-05:00
dq/latest.json: {"run_id":"r20261117T020252Z","published_at":"2026-11-17T02:03:04Z"}
```
Bronze round-trip from S3 (strip last field) reproduces staging SHA-256 2dcbe59e…, b4330fc6…, 41fbb649…; suffixes = {_ingested_at, one timestamp}. Second run: all 3 files `duplicate`, no new bronze object (CTO-03).

## Athena (workgroup finora-dl) vs golden run
```
SELECT count(*), sum(amount), sum(amount_value) FROM finora_silver.transactions WHERE run_id='r20261117T020252Z'
66674	221441.504508	2214415045.08
SELECT count(*) FROM finora_silver.industry WHERE run_id='r20261117T020252Z'
1961
SELECT count(*), sum(spend), sum(spend_value) FROM finora_silver.sm_spend WHERE run_id='r20261117T020252Z'
238	77.818	7781800000
SELECT hr_sensitive, count(*) FROM finora_silver.sm_spend WHERE run_id='r20261117T020252Z' GROUP BY hr_sensitive ORDER BY 1
false	136	true	102
SELECT count(*), sum(CASE WHEN is_new_logo THEN 1 ELSE 0 END), sum(CASE WHEN cohort_censoring='probable_left' THEN 1 ELSE 0 END) FROM finora_silver.customer WHERE run_id='r20261117T020252Z'
1961	1541	43
SELECT lifecycle_state, count(*) FROM finora_silver.customer_month WHERE run_id='r20261117T020252Z' GROUP BY 1 ORDER BY 2 DESC
paying	31366	pre_acquisition	29321	churned	3811	new	1541	settled_gap	281	paused	231	reactivated	64	grace	59
SELECT settlement_type, count(*) FROM finora_silver.gap WHERE run_id='r20261117T020252Z' AND settlement_type IS NOT NULL GROUP BY 1 ORDER BY 2 DESC
arrears	155	prepay	47	split	9
SELECT array_join(array_agg(customer_id ORDER BY customer_id), ',') FROM finora_silver.customer WHERE run_id='r20261117T020252Z' AND is_outlier_customer
94,322
SELECT rule_id, dataset_id, action, count(*) FROM finora_dq.findings WHERE run_id='r20261117T020252Z' AND hr_sensitive='false' GROUP BY 1,2,3 ORDER BY 1
SB-10	sm_spend	flagged	5	SQ-02	industry	excluded	1
SELECT dataset, count(*), max(source_line) FROM finora_dq.excluded WHERE run_id='r20261117T020252Z' AND hr_sensitive='false' GROUP BY 1
industry	1	1963
```

## HTTP (CloudFront https://d1smzfxmkay9lx.cloudfront.net)
```
GET / -> 200 text/html
GET /login -> 200 text/html
GET /change-password -> 200 text/html
GET /index.txt -> 200 text/plain
GET /does-not-exist -> 404 text/html
GET /api/dq/summary (no cookie) -> {"error": {"code": "unauthenticated", "message": "Log in to continue."}} 401
x-frame-options: DENY
content-security-policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'
x-content-type-options: nosniff
strict-transport-security: max-age=31536000; includeSubDomains
```


---

# Re-platform onto AWS Glue (reference architecture), 2026-11-17 UTC

**Principle:** all data movement and transformation in the lake runs on Glue. Lambdas remain only for the API and auth (`finora-dq-api`, `finora-dq-auth`), as in the reference (Analytics API = API Gateway + Lambda). `FinoraDqApi`, `FinoraDqAuth`, `FinoraDqWeb` and `FinoraDlStorage`: no differences (`infra/deploy_diff_glue.txt`).

## Architecture now
| Stage | Runs on |
|---|---|
| Trigger | EventBridge `finora-dl-staging-object-created` (staging Object Created) -> Step Functions `finora-dl-ingest` (`glue:startJobRun.sync`; run_id from the execution start time) |
| Bronze | Glue 5.0 job `finora-dl-bronze-ingest` (driver-side Python, G.1X x2, 10 min, MaxConcurrentRuns 3): byte-faithful CSV + `_ingested_at`, write-once manifest on (dataset, SHA-256) |
| Silver + DQ | Glue 5.0 Spark job `finora-dl-silver-build` (`--datalake-formats iceberg`, G.1X x2, 30 min, **MaxConcurrentRuns 1**; Step Functions retries `Glue.ConcurrentRunsExceededException` with backoff and jitter; the S3 lock is gone): Glue Data Quality (EvaluateDataQuality, row-level outcomes) with rulesets `finora-dl-transactions`, `finora-dl-industry`, `finora-dl-sm_spend`; lifecycle per customer on executors (`applyInPandas`, Python Decimal); findings, business rules and run controls in the exact-Decimal engine; 11 Iceberg tables in `finora_silver` / `finora_dq` (quarantine `finora_dq.excluded_rows`), one overwrite snapshot per table per run, tagged `<run_id>` |
| Serving refresh | Glue 5.0 job `finora-dl-dq-publish` (driver-side Python, G.1X x2, 10 min, MaxConcurrentRuns 1): same serving JSON as before, `latest.json` last; `--mode failed` records failed runs |

Rules in Glue DQ vs Spark/Python: 18 DQDL rules covering 9 catalog rules (SQ-03, SQ-04, SQ-05, SQ-06, SQ-07a, SQ-07b, SQ-09a, SQ-10, CDO-05 on transactions), named by label `rule_id`/`check` and visible in the job run's Data quality tab. Spark/Python: 18 dashboard rules (stage A CDO-01, SQ-02, SQ-01; findings SQ-08, SQ-09b, SQ-12, SQ-13; CDO-06a/b; SB-04 to SB-08, SB-10, CDO-08, CRO-05, CRO-07; CDO-05 on sm_spend) plus the 16 run controls. The engine's reference predicates shadow every Glue DQ outcome; any disagreement fails the run (none: 406,233 row checks consulted, 0 mismatches).

## Tests before deploy
- `etl` on PySpark 3.5.4 (Glue 5.0's Spark) + Iceberg 1.7.1, Python 3.11: **85 passed** (golden run and all 24 dirty/hole fixtures identical on the Glue path vs the reference engine; DQDL generation and regex equivalence; Iceberg snapshot/tag/time travel/partition/quarantine; moto end-to-end in reference and Glue modes; write-once header fallback).
- `etl` on Python 3.13 without Spark: 58 passed, 3 skipped (Spark-only). `auth` 19 passed, `dq_api` 13 passed.
- Not run locally: Glue Data Quality itself (Glue runtime only; `etl/tests/dqdl_local.py` is a Spark stand-in, the real service was verified on AWS). Shuffle-based aggregates over Iceberg crash this Mac's JVMs (HotSpot SIGSEGV, JDK 11 and 17 on macOS 26), so local Iceberg checks use metadata tables and plain scans; aggregates were verified with Athena.

## Changes made
1. `cdk diff --all` saved to `infra/deploy_diff_glue.txt` (FinoraDlEtl only; no replacements).
2. Deploy 1 of FinoraDlEtl: added 3 Glue jobs, 3 roles (`finora-dl-glue-{bronze,silver,publish}`), 3 DQ rulesets, Glue log groups; state machine updated in place; Glue databases updated (Iceberg location); **removed** Lambdas `finora-dl-bronze_ingest`, `finora-dl-silver_build`, `finora-dl-dq_publish` (+ roles) and the 11 Parquet Glue table definitions (metadata only). Lambda log groups orphaned (retained).
3. Run `glue-first-load-all-three` (r20261117T040928Z) **FAILED** in silver: Iceberg deletes the empty data file an empty Spark task writes, and the role has no `s3:DeleteObject` (kept that way on purpose). Recorded as failed in runs.json; `latest.json` untouched. 8 tables had committed and carry tag `r20261117T040928Z`.
4. Fix (no empty write tasks: one task per table, an empty RDD for empty tables; failed writes now leave a failed run report). Deploy 2 (library asset only; diff appended to `deploy_diff_glue.txt`).
5. Run `glue-first-load-all-three-retry` **SUCCEEDED** 04:19:00 -> 04:25:01 UTC, run **r20261117T041900Z**, published `2026-11-17T04:24:18Z`. Bronze: all 3 files `duplicate` (no new bronze object, CTO-03).

## Golden parity (`infra/parity_diff_glue.txt`, `scripts/compare_dq_runs.py`)
- Record pages: 39 of 39 identical to the Lambda run r20261117T020252Z (run_id and timestamps normalized).
- summary.json: identical except the blocks that depend on run history: CDO-06a/CDO-06b were `na` on the Lambda run (first run) and are now evaluated against it (transactions 66,674 / industry 1,961 / sm_spend 34 evaluated, 0 failed, pass), which adds 1 to each dataset's `rules_evaluated` (9 / 5 / 8), and `trend` has 2 entries. With those reported separately (`--history-aware`): **DIFF: empty**.
- Offline first-run parity (Glue code path on local PySpark, no previous run) vs the Lambda run: **DIFF: empty** on all 40 files.
- DQ result: transactions 100.00, sm_spend 100.00 (5 SB-10 flags), industry 99.95 (1 SQ-02 exclusion, line 1963), as in approved_data_rules.md.

## Iceberg (report `_runs/run_id=r20261117T041900Z/report.json`) and Athena (`infra/athena_evidence_glue.txt`)
Snapshot per table, tag r20261117T041900Z: transactions 7813859245337130562 (66,674), industry 1546021125826945277 (1,961), sm_spend 832567271261532486 (238), customer 1307680357252673399 (1,961), customer_month 6861095787448877427 (66,674), gap 2280563831638346538 (468), month_control 5472663242314575855 (34), source_status 1495208935671227723 (2), restatement_log 7070171005224328754 (0), findings 971760108734010254 (11), excluded_rows 1958866677157842609 (1).
Athena workgroup finora-dl reproduces every golden figure: Σ amount 221441.504508, Σ amount_value 2214415045.08, sm_spend 238 / 77.818 / 7781800000 (136 + 102 by hr_sensitive), customers 1961 / new logos 1541 / probable_left 43, lifecycle states as golden, settlements 155/47/9, outliers 94,322, excluded industry line 1963 (SQ-02); `FOR VERSION AS OF 7813859245337130562` returns the run.

## Untouched
Staging (keys, sizes, ETags as before), gold, legacy, us-east-1. Lambda-era Parquet (`store/` 11 objects, `dq/` 8) and `_control/silver_build.lock` left in S3, no longer catalogued.

## Cost
Per run 584 DPU-seconds (bronze 103, silver 340, publish 141) x USD 0.44/DPU-hour = **about USD 0.07** (Glue DQ in ETL is billed as job time; Step Functions, S3, Athena under USD 0.001). About USD 2/month at one run a day, USD 4 at 60 runs. The Lambda pipeline cost under USD 0.01 per run and took 10 s; the Glue run takes about 6 min.

## Deviations from the reference, and why
- Bronze stays byte-faithful CSV + `_ingested_at` (not Parquet): the bronze contract in `.claude/CLAUDE.md` ("exactly ONE new column, no other changes") overrides the reference.
- Bronze and publish are Glue Spark jobs with driver-side Python, not Python shell: AWS is steering away from Python shell (migration guide), its runtime is Python 3.9 (end of life) with boto3 1.21; one Glue 5.0 runtime for all three jobs. Cost difference about USD 0.03 per run.
- Stage A (CDO-01 bytes are UTF-8 without control characters, SQ-02, SQ-01) stays in the byte-level parser: it decides what a row and its cells are, before any DataFrame exists.
- Cross-row business logic runs on the driver in exact Decimal with lifecycle() on executors: about 70k rows; reusing the tested engine guarantees the golden figures.
- Iceberg has no multi-table transaction: a run that fails mid-write can leave some tables at the new snapshot (seen in step 3). Serving is unaffected (latest.json is written last); `_run_id` and the tags show which run each table holds. Follow-up: tag only after all 11 commits succeed.
- `cloudwatch:PutMetricData` is not granted (Glue logs a non-fatal error each run); job metrics would be billed as custom metrics.


---

# SB-11 deploy (uneven split of a two-month total), 2026-11-17 UTC

**Approval:** user, "ok deploy the rule" (scope: deploy FinoraDlEtl, one rebuild, read-only verification). Rule: `docs/approved_data_rules.md` SB-11 (CDO evidence `docs/etl_discussion/round3/cdo_uneven_split.md` §11). Pre-deploy project snapshot: `/Users/juananzola/alegra_snapshots/alegra_pre_sb11_deploy_20261117T150536Z.tgz`.

## Tests before deploy (run by the main session after the Rule-cell markup fix, rules_version `sha256:a6dce7113e3fd468`)
`etl` with PySpark 3.5.4 + Iceberg 1.7.1: 121 passed. `etl` without Spark: 92 passed, 3 skipped. `dq_api` 13, `auth` 19 passed.

## Changes made
1. `cdk diff --all --no-change-set` (read-only) saved to `infra/deploy_diff_sb11_final.txt` (supersedes `deploy_diff_sb11.txt`, whose rules_version and zip hash predate the markup fix). Only FinoraDlEtl differs: 3 Glue jobs (`--extra-py-files` -> `d42b6c3d...f1c6.zip`, 53,703 B) and 3 DQ rulesets, all in place. Each live ruleset differs from the new one in exactly one line, the `# rules_version` comment (`a0060ddfcacd93e7` -> `a6dce7113e3fd468`). No IAM, Step Functions, EventBridge, SNS, Athena, Glue database or bucket change; no replacement or destroy. The other 4 stacks: no differences.
2. `cdk deploy FinoraDlEtl --exclusively` (dependency stacks not deployed) 15:08:28 -> 15:09:04 UTC, UPDATE_COMPLETE, 6 resources UPDATE_COMPLETE in place (`infra/deploy_log_sb11.txt`). Verified live: all 3 jobs on the new zip, MaxConcurrentRuns 3/1/1, retries 0, G.1X x2; all 3 rulesets carry `a6dce7113e3fd468`.
3. One execution `sb11-rebuild-1` (3 staging keys) **SUCCEEDED** 15:09:32 -> 15:15:41 UTC, run **r20261117T150932Z**, published 15:15:15Z. Glue job runs (attempt 0 each): bronze `jr_929df26f...` 51 s (all 3 files `duplicate`: only `_deliveries/` and `_runs/` written), silver `jr_c77ee844...` 151 s, publish `jr_88379661...` 41 s.

## Results
- `dq/latest.json` -> r20261117T150932Z; `runs.json` marks it `succeeded` (r20261117T041900Z stays `succeeded`).
- Run report `_runs/run_id=r20261117T150932Z/report.json`: rules_version `sha256:a6dce7113e3fd468`; `customer_month.columns_added` = `["uneven_split_start_month"]` (Iceberg ADD COLUMN, metadata only; placed after `settlement_confidence` in the Glue catalog), `[]` on the other 10 tables; 19 run controls, 0 failed; Glue DQ shadow 0 mismatches; figures `uneven_split_pairs` 11, `uneven_split_customers` 10. Snapshots (tag r20261117T150932Z): transactions 2573843347159346284 (66,674), industry 7838209493197630333 (1,961), sm_spend 3356459405715221528 (238), customer 6328355583053186166 (1,961), customer_month 642067429204887907 (66,674), gap 6950291511617394988 (468), month_control 8518835669733755993 (34), source_status 5254717572819767018 (2), restatement_log 8794075694935605083 (0), findings 2766108985900296686 (33 = 11 + 22 SB-11), excluded_rows 414822036591355964 (1).
- Parity vs r20261117T041900Z (`infra/parity_diff_sb11_final.txt`, `--history-aware`): only the SB-11 rule block (transactions 66,674 evaluated / 22 failed / 99.97 / warn), `transactions.rows_flagged` 0 -> 22, and the new `records/SB-11/transactions/page-1.json` (22 records, 11 pairs, customers 12, 34, 78, 93, 191, 336 x2, 370, 437, 576, 651; reason `UNEVEN_SPLIT: ...`, `failed_columns` [amount]). 39 of 39 common record pages identical. History blocks: CDO-06a/b pass on both runs, trend 2 -> 3 entries. No literal `**` in summary.json.
- Athena (`infra/athena_evidence_sb11.txt`): uneven_split / high: 22 rows, 10 customers, 11 pairs; Σ expansion 3,499.903452, Σ contraction 4,656.537782 (1,212 / 954 months), each 82.483002 below the pre-SB-11 snapshot read by time travel (3,582.386454 / 4,739.020784), net -1,156.634330 unchanged; Σ amount 221,441.504508 over 66,674 rows (= Σ amount_normalized); lifecycle states, gap settlements 155/47/9, customers 1,961 / 1,541 / 43, outliers 94,322, sm_spend 238 / 77.818, quarantine (industry line 1963, SQ-02) unchanged; findings add `SB-11 transactions flagged 22`. `FOR VERSION AS OF 2573843347159346284` returns the run.

## Untouched
Staging (sizes and ETags `ae01140d...`, `4d04f745...`, `71592d32...` as before, 3 object versions); FinoraDlStorage, FinoraDqAuth, FinoraDqApi, FinoraDqWeb (LastUpdatedTime before this deploy); IAM; gold, legacy, us-east-1. HTTP after the run: site `/` 200; `/api/dq/summary?run=latest` without a session 401 `unauthenticated`.

## Cost
486 DPU-seconds (bronze 102, silver 302, publish 82) x USD 0.44/DPU-hour = **about USD 0.06**; Athena verification scans under USD 0.001.

## Rollback (not needed, not executed)
Data rollback needs no rebuild: the previous run stays readable by tag `r20261117T041900Z` / snapshot ids, and `dq/runs/r20261117T041900Z/` is intact. Code rollback: the safest path is to keep the current schema (the nullable column stays, NULL) and disable only the `_uneven_splits` step in the engine, then `cdk deploy FinoraDlEtl` and one rebuild. Redeploying the previous library zip (`3c5c3523...zip`) as-is is untested: it has no schema evolution and would write `customer_month` by name without the new column (`writeTo().overwrite()`), so test that locally against a table that has the column first. Dropping the column would need explicit approval.

## Observations
- Bronze and publish (driver-side Python) log `GlueBootstrap: Bootstrapping failed / Connection refused` from the second worker's executor once the driver has finished; also present on the previous run, and harmless. Silver logs only the known `cloudwatch:PutMetricData` denial (7 times).


---

# Gold build (acquisition model) + acquisition API, 2026-11-17 UTC

**Scope (coordinator brief, user request "Build the gold tables" + "continue and start with the dashboard too"):** spec `docs/gold_acquisition_model.md` (CDO, 2026-11-17); API contract `contracts/acq_api_contract.md` v1.1 (not edited). Defaults for spec §15: revops and data see total spend and cost per stage; finance and revops may edit rates, data is read-only; no CMO access; no cohort-quality view.

## Architecture added
| Piece | What |
|---|---|
| Glue job `finora-dl-gold-build` | Glue 5.0 Spark, Iceberg, G.1X x2, 15 min, no retries, MaxConcurrentRuns 1, own library zip (`common` + `gold_build` + `gold_acquisition.json`; the other three jobs keep zip `d42b6c3d...`). Reads every silver table at the tag of the latest `succeeded` run in `dq/runs.json`; exact-Decimal engine on the driver; writes 13 job-owned tables with write-audit-publish (branch `audit_<run_id>` -> row-digest audit + metrics-property check -> `fast_forward` main -> tag `<run_id>` -> drop branch; `gold_build_status` last); report `s3://al-test-dl-gold/_runs/run_id=<id>/gold_report.json`; then `acq/runs/<id>/summary.json` and `acq/latest.json` last; SNS alert on RATE_HISTORY_REWRITTEN / unknown members |
| Role `finora-dl-glue-gold` | read `al-test-dl-silver/iceberg/finora_silver/*` (all partitions) and `serving/dq/runs.json`; read/write `al-test-dl-gold/{iceberg/finora_gold,_runs,_glue_tmp}/*`; PutObject `serving/acq/*` only; Glue create/update on `finora_gold`, read on `finora_silver`; sns:Publish on `finora-dl-alerts`; **explicit Deny** s3:PutObject/DeleteObject/DeleteObjectVersion on `iceberg/finora_gold/funnel_conversion_rate/*` and glue:CreateTable/UpdateTable/DeleteTable on that table; no s3:DeleteObject anywhere |
| State machine `finora-dl-ingest` | bronze -> silver -> dq-publish -> **GoldBuild** -> **GoldRefreshed** (EventBridge PutEvents, source `finora.dl`, detail-type `gold.refreshed`) -> Published. GoldBuild's Catch goes to `GoldFailed` (Fail), never to `RecordFailedRun`: a gold failure cannot touch `dq/*` or `acq/latest.json`; the execution ends FAILED and `finora-dl-ingest-failed` alerts on SNS. Tested in `infra/tests/test_gold_infra.py` and `etl/tests/test_gold_spark.py` |
| Glue database `finora_gold` | location `s3://al-test-dl-gold/iceberg/finora_gold/` |
| Rates table (deploy step) | `infra/gold_athena_ddl.py rate-table`: Athena `CREATE TABLE IF NOT EXISTS finora_gold.funnel_conversion_rate` (Iceberg; `vacuum_min_snapshots_to_keep`/`vacuum_max_snapshot_age_seconds` set so Athena VACUUM cannot expire history), base seed only when absent |
| Views (deploy step) | `infra/gold_athena_ddl.py views`: 10 views (`v_funnel_rate_current`, `v_funnel_scenario_status`, `v_funnel_month`, `v_funnel_period`, `v_funnel_scenario_compare`, `v_funnel_rate_sensitivity`, `v_acquisition_month`, `v_acquisition_month_finance`, `v_corr_signal_summary`, `v_sm_spend_shared`), SQL in `etl/gold_build/ddl.py`; all published quotients are one HALF_UP integer division of exact integers (rates as i/10^4), so no rounding of intermediates and no overflow for any rate in (0, 1] |
| Bucket `al-test-dl-gold` | imported into FinoraDlStorage (import-only change set `import-gold-bucket`, 1 change: Import, Retain), then versioning, lifecycle `noncurrent-and-multipart` (30 / 7 days, as silver), TLS-only policy, tag |
| API (FinoraDqApi) | `GET /api/acq/summary`, `GET /api/acq/scenarios`, `POST /api/acq/scenarios` on the existing HTTP API; `finora-dq-api` now has its own asset (`build/api_dq`: authlib + unchanged `handler.py` + `acq.py` + entry `api_handler.handler`), timeout 28 s; IAM: Athena on workgroup `finora-dl`; Glue read on `finora_gold`, UpdateTable on the rate table only; S3 read/write on the rate table prefix, read on `dim_funnel_stage/*`, read `serving/acq/*`, results prefix `al-test-dl-athena-results/finora-dl/*`. No HR prefix, no other gold table, no silver. The auth Lambda keeps its asset (FinoraDqAuth: no differences) |

## Tests before deploy
- `etl` with PySpark 3.5.4 + Iceberg 1.7.1 (Python 3.11): **157 passed, 1 skipped** (the scipy cross-check; scipy is not in that env). New: `test_gold.py` 25 (§12.1-12.8 golden, §14.3 synthetic cases, GR-01..06, history rewrite, base vs seed, CDO-10 lineage, HR isolation, lineage block, payload), `test_gold_views.py` 7 (the view SQL on Spark: §12.5/§12.6 exactly, GC-12 over all 2,352 funnel rows, rate-edit flow, one invalid scenario per GR -> no funnel rows, synthetic cost reasons), `test_gold_spark.py` 5 (end to end on local Iceberg + moto: WAP publish and tags, rebuilds never alter user rate rows (snapshot list and row hash unchanged), history rewrite alerted, failed control / failed audit / missing silver tag publish nothing and leave `acq/latest.json` and `dq/*` untouched). Local only: Iceberg's vectorized reader is switched off in these tests (it crashes this Mac's JVM; Glue keeps the default).
- `etl` without Spark (Python 3.13): 117 passed, 5 skipped. `dq_api`: 31 passed (13 existing + 18 new `/api/acq/*`). `auth`: 19 passed. `infra/tests`: 5 passed.
- Athena pre-check of the Trino rendering (`infra/gold_athena_ddl.py precheck`, inline VALUES, 0 bytes scanned, `infra/athena_precheck_gold.txt`): 12 of 12 checks equal the exact reference, including an extreme-rate scenario (all 0.0001) without overflow.

## Changes made
1. `cdk diff --all --no-change-set` -> `infra/deploy_diff_gold.txt` (see its RESULT line). FinoraDqWeb differed only because the parallel frontend work rebuilt `dashboard/out/` (new `/acquisition` page); pinned to the deployed content it shows 0 differences; not deployed.
2. FinoraDlStorage import-only change set (`infra/import_gold/`): IMPORT_COMPLETE 18:53:45Z; post-import diff appended; `cdk deploy FinoraDlStorage --exclusively` (49.9 s). Verified: versioning Enabled, lifecycle 30/7, policy Deny when `aws:SecureTransport` false, SSE-S3, 4 BPA flags.
3. `cdk deploy FinoraDlEtl --exclusively` (111 s). Verified: gold job settings; bronze/silver/publish still on zip `d42b6c3d...`, LastModifiedOn unchanged; state machine DqPublish -> GoldBuild -> GoldRefreshed -> Published, GoldBuild catch -> GoldFailed.
4. `cdk deploy FinoraDqApi --exclusively` (63 s). Verified: handler `api_handler.handler`, timeout 28, 10 routes; `finora-dq-auth` unchanged (LastModified 01:55:53Z); FinoraDqAuth/FinoraDqWeb LastUpdatedTime before this deploy.
5. `gold_athena_ddl.py rate-table` 19:00:48Z: table created, base seeded (6 rows, snapshot 987657331643210322).
6. One execution `gold-first-build` (3 staging keys) **SUCCEEDED** 19:01:13 -> 19:12:00 UTC, run **r20261117T190113Z**, attempt 0 everywhere: bronze `jr_311c75e1...` 45 s (all 3 files duplicate), silver `jr_f3eaa55c...` 145 s, publish `jr_8eacef72...` 50 s (DQ published 19:07:04Z), gold `jr_12203f5e...` 180 s (acq published 19:11:03Z), GoldRefreshed emitted.
7. `gold_athena_ddl.py views` 19:12:15Z: 10 views created and queried.

## Results (`infra/athena_evidence_gold.txt`, 0 failures)
- Gold report: status succeeded, silver run r20261117T190113Z, controls GC-01..GC-11 all passed, 0 findings, all 13 audits digest-match, `fact_sm_spend` metrics properties present; snapshots (tag r20261117T190113Z): dim_month 8932245907416688578, dim_industry 7363688664918632786, dim_customer 3639165850164629899, dim_spend_category 2750737621030468361, dim_funnel_stage 5781435868418547031, fact_acquisition 4516568561778079082, fact_customer_month_revenue 336948086566298291, fact_sm_spend 4418607155948918041, agg_acquisition_month 7257351783932284405, agg_won_month_industry 280117297066557524, agg_industry_profile 44244885381285079, agg_won_spend_lag_corr 2832639110179097369, gold_build_status 2471003113368778351.
- Athena: row counts as §12.1 (fact_sm_spend 102 HR / 136 shared); Won 1,584, new logos 1,541; new revenue 105,482,511.96 (multiples 10,663,744.35, new logos 99,728,662.11, run-rate 99,662,644.41); spend 7,581,800,000 over the 33 Won months (window start 200,000,000, Won NULL); base funnel full period New 58,928.571429 / 128,660.85 ... Won 1,584 / 4,786,489.90; new-logo New 57,328.869048, cost per Won 4,920,051.91; 2024-10 New 1,860.119048 / 107,520.00, Won 50 / 4,000,000.00; regimes and years as §12.5; TOTAL company correlations as §12.8; `v_corr_signal_summary` = §7.5 (30/110, 3/11, 3/17; new logo 32/123, 3/13, 3/14).
- Reconciliation to silver at the run's snapshots (`FOR VERSION AS OF`): Won 1,584 = 1,584; new revenue equal; 0 spend cells and 0 monthly totals differ; 66,674 rows and Σ amount_value 2,214,415,045.08 equal; new logos 1,541 three ways.
- HR manifests: both `fact_sm_spend` data files carry no spend/spend_value bounds (other columns do).
- Rate edit through Athena: test scenario `cto_deploy_check_20261117` (label "CTO deploy check ... test, not a business assumption", changed_by `cto-deploy-check`) appended as a user would; on the next query `v_funnel_period` New = 51,562.500000, `v_funnel_month` 462 rows, compare 1,810.285714 / 4,188,178.66 (§12.6); base unchanged. Left in place: the spec is append-only with no retire mechanism, and non-base scenarios persist by design. Rate table snapshots: the seed and this append only; the gold job wrote none.
- Serving: `dq/latest.json` -> r20261117T190113Z (runs.json `succeeded`); `acq/latest.json` -> r20261117T190113Z (68 B); `acq/runs/r20261117T190113Z/summary.json` 457,944 B (correlations 424,390 B, months 22,839 B, profile 7,072 B).
- DQ parity vs r20261117T150932Z (`--history-aware`, `infra/parity_diff_gold.txt`): 41 files, **DIFF: empty**; history blocks: CDO-06a/b pass on both, trend 3 -> 4.
- Untouched: staging (keys, sizes, ETags `4d04f745...`, `71592d32...`, `ae01140d...`; 3 versions); FinoraDqAuth, FinoraDqWeb; silver tables and jobs; us-east-1, legacy. HTTP: site `/` 200; `/api/dq/summary`, `/api/acq/summary`, `/api/acq/scenarios` (GET) and `POST /api/acq/scenarios` without a session: 401 `unauthenticated`.

## Cost
Per run 842 DPU-seconds (bronze 90, silver 290, publish 101, gold 361) x USD 0.44/DPU-hour = **about USD 0.10** (gold about USD 0.044); wall time about 11 min. Athena: pre-check 0 B, verification a few hundred KB (under USD 0.001); each `/api/acq/scenarios` query is billed at Athena's 10 MB minimum (about USD 0.00005). Storage: a few MB.

## Rollback (not needed, not executed)
Data: the previous state of every gold table is empty (first build); later builds stay readable by tag. Code: revert `infra/stacks/etl.py` (remove GoldBuild/GoldRefreshed) and redeploy FinoraDlEtl; the DQ path never depended on gold. API: redeploy FinoraDqApi with the previous handler. The rates table is user-owned and is never dropped by a rollback (deleting it needs explicit approval).


---

# Gold MRR deploy (finora-dl-gold-mrr), 2026-11-17 UTC

**Scope (coordinator brief):** FinoraDlEtl only: the MRR gold logic as a new Glue job + the IAM it needs, the new `finora_gold` Iceberg tables, the state-machine step, the `mrr/*` serving snapshot; one pipeline execution. Spec: `docs/mrr_discounts_model.md` §6 (CDO, proposed; spec SHA-256 pinned in `etl/config/gold_mrr.json`). Snapshot: `contracts/mrr_api_contract.md` v1.

## Design
- **Separate job, not a stage of `finora-dl-gold-build`:** the acquisition job's script, library zip (`66e628da...zip`), role and outputs are unchanged; the MRR job has its own zip (`common` + `gold_mrr`), its own role `finora-dl-glue-mrr` (read 4 silver tables; write only its 4 tables, `_runs/run_id=*/mrr_report.json`, `_glue_tmp/mrr/*` and `mrr/*`; no delete) and its own Fail state.
- **Orchestration:** DqPublish → GoldBuild → GoldRefreshed → **GoldMrrBuild** → Published; catch → `GoldMrrFailed`. An MRR failure cannot reach `RecordFailedRun` (`dq/*`) and runs after `acq/*` is published. If GoldBuild fails, MRR does not run (accepted for a minimal state-machine edit).
- **Tables (`finora_gold`, WAP, tag `<run_id>`):** `fact_customer_month_mrr`, `fact_mrr_movement`, `agg_mrr_bridge_month` (marker, published last), `dim_movement_type` (the line domain §6.2 references).

## Tests before deploy
`etl` per file (PySpark 3.5.4 + Iceberg 1.7.1): 208 passed, 1 skipped (new: `test_gold_mrr.py` 27 golden + edge cases, `test_gold_mrr_spark.py` 4 WAP/serving/failure). `infra` 6 passed (state-machine test extended; new MRR role-scope test). `dq_api` 31, `auth` 19.

## Changes made
1. Baseline `cdk diff FinoraDlEtl --exclusively` (19:18 UTC): no differences. Gate diff `infra/deploy_diff_gold_mrr.txt`: FinoraDlEtl additive only (MrrRole + policy, MrrJob, state machine in place, Ingest role +StartJobRun on the new job); FinoraDlStorage/FinoraDqAuth/FinoraDqApi none; FinoraDqWeb drift from the local `dashboard/out` build (not part of this change, not deployed).
2. Deploy 1 `cdk deploy FinoraDlEtl --exclusively` 19:36:19 → 19:38:16 UTC, UPDATE_COMPLETE (`infra/deploy_log_gold_mrr.txt`). Deploy 2 (MRR zip only: `months[].timing_lines` key for the frontend) 19:39:09 → 19:39:49 UTC (`infra/deploy_log_gold_mrr_2.txt`; diff appended).
3. One execution `gold-mrr-first-build` **SUCCEEDED** 19:40:44 → 19:52:44 UTC, run **r20261117T194044Z**. Glue runs: bronze 40 s / 81 DPU-s (3 duplicates), silver 141 s / 283, publish 75 s / 151, gold 159 s / 319, **gold-mrr 145 s / 291**.

## Results (run report `s3://al-test-dl-gold/_runs/run_id=r20261117T194044Z/mrr_report.json`)
- 11 run controls, 0 failed (GC-MRR-0..5, continuity, contract period, domain, lineage); contract checks on the serialized snapshot: passed.
- Snapshots (tag r20261117T194044Z): dim_movement_type 4257230467772049119 (24), fact_customer_month_mrr 8428047127975232331 (66,674), fact_mrr_movement 4758573355703885865 (4,589), agg_mrr_bridge_month 4993782003310372836 (792); all audits digest-match.
- Figures equal CDO §6.6 exactly: opening 3,500.030835 (377) → closing 9,636.064683 (1,678); behaviour +6,320.070330, pricing (inferred) +57.436743, timing −241.473225; 140 price-step windows; 581 inferred rows; spikes 222 / dips 31; 2024-10 9,274.712517 → 9,636.064683, collected 9,700.744683.
- Athena (workgroup finora-dl, ~70 KB scanned): same rows and figures; Σ collected = Σ mrr_proxy = 221,441.504508, Σ timing 0; 0 bridge mismatches; `FOR VERSION AS OF 4993782003310372836` returns the run.
- Serving: `mrr/runs/r20261117T194044Z/movements/page-1..23.json`, `summary.json`, then `mrr/latest.json` (19:52:09Z, last).

## Untouched / parity
- DQ parity vs r20261117T190113Z (`scripts/compare_dq_runs.py --history-aware`): DIFF empty on 41 files; trend 4 → 5.
- Acquisition vs r20261117T190113Z: `acq/runs/<id>/summary.json` identical (ids/timestamps normalized); `gold_report.json` differs only in `rate_table` (6 → 12 rows: the user-owned rates table was appended at 19:16:51 UTC by the acquisition deploy check, before this deploy; base still matches the seed, no findings).
- Staging sizes and ETags as before. FinoraDlStorage/FinoraDqAuth not deployed by this change; FinoraDqApi (19:51 UTC) and FinoraDqWeb (19:53 UTC) were deployed by another agent during this run, not by this change.

## Cost
gold-mrr 291 DPU-s × USD 0.44/DPU-h ≈ **USD 0.036 per run**; whole pipeline 1,125 DPU-s ≈ USD 0.14. Athena checks under USD 0.001.

## Rollback (not executed)
Data: previous runs stay readable by tag; `mrr/latest.json` can be pointed back. Code: remove the `mrr` entry from `JOBS` and the GoldMrrBuild step, `cdk deploy FinoraDlEtl --exclusively` (the 4 Iceberg tables remain; dropping them needs explicit approval).


---

# Decision levers (§16) in the acquisition gold job, 2026-11-17 UTC

**Approval:** user, "ship levers" (relayed by the coordinator). Spec: `docs/gold_acquisition_model.md` §16 (CDO); snapshot: `contracts/acq_api_contract.md` v1.3 (`levers` mirrors the §16 tables; shift-share terms at 6 dp, every other `*_value` at 2 dp; `won_definition` = `first_payment` / `new_logo`).

- **Code:** `etl/gold_build/levers.py` (new); `engine.py`, `schemas.py`, `summary.py`, `ddl.py` (view `v_acq_cohort_half`); config regenerated (`etl/config/build_gold_yaml.py`: lever params and GC-09 lineage for the 4 new tables and the view). Tests: `etl/tests/test_gold_levers.py` (10, §16.5 as the oracle: periods, industries, value change, cohorts, the 5 planner fixtures, GC-13/GC-14), plus a Spark view test and a schema-evolution test. etl with Spark: 199 passed, 1 skipped; without Spark: 152 passed, 7 skipped; infra: 6 passed.
- **Diff** (`infra/deploy_diff_levers.txt`): FinoraDlEtl, 1 change in place: `finora-dl-gold-build` `--extra-py-files` zip `66e628da...` -> `b17ee40e...`. No IAM change. Deploy `--exclusively` (37 s). `finora-dl-gold-mrr` (zip `446c829e...`) and silver (zip `d42b6c3d...`) unchanged.
- **Run** `gold-levers-build`, run **r20261117T201211Z**: SUCCEEDED 20:12:11 -> 20:24:42 UTC, attempt 0 everywhere (bronze 50 s, silver 123 s, publish 51 s, gold 183 s / 367 DPU-s, gold MRR 137 s). Gold report: GC-01..GC-11, GC-13, GC-14 passed, 0 findings; `fact_acquisition` gained the 6 lever columns by Iceberg schema evolution; new tables: agg_acq_cohort_quality 396, agg_acq_lever_period 4, agg_acq_lever_industry 24, agg_acq_value_change 12 rows. View `v_acq_cohort_half` created (`gold_athena_ddl.py views --only v_acq_cohort_half`), 12 rows.
- **Published figures** (user's Won, pre_2023_06 -> from_2023_06): Won/month 37.875000 -> 57.529412; run-rate 55,767.62 -> 42,550.70; new MRR/month 2,112,198.61 -> 2,447,916.75; cost per Won 7,592,244.22 -> 3,047,955.01; payback 136.1 -> 71.6; shift-share mix -558.82 + within -12,658.10 = -13,216.92; cohorts m6 93.9 / 90.8 / 94.1 / 95.2 / 94.0, m12 87.7 / 84.2 / 87.5 / 91.0. All equal §16.5.
- **Parity** (`infra/parity_levers.txt`): acq summary = r20261117T190113Z except run fields and `levers`; MRR summary = r20261117T194044Z except run fields, and all 23 movement pages equal except run_id; DQ vs r20261117T194044Z `--history-aware`: DIFF empty (trend 5 -> 6). Pointers `acq/`, `mrr/`, `dq/latest.json` -> r20261117T201211Z. Staging unchanged.
- **Cost:** about USD 0.13 per run (1,090 DPU-s across the five jobs).

## Voice agent (2026-11-17): ElevenLabs + Kimi K3 (contract v1.1, semantic layer sl-2026-11-17)

- **Diff gate** (`infra/deploy_diff_voice.txt`, `cdk diff --no-change-set --exclusively --output cdk.out.voice`): only voice resources (FinoraDqAuth: table `finora-dq-agent-tokens`; FinoraDqApi: Lambda `finora-dq-agent`, role, log group, table `finora-dq-agent-results`, 4 routes; FinoraDlEtl: Glue job `finora-dl-agent-briefing`, role `finora-dl-glue-briefing`, state-machine step `AgentBriefing` + `BriefingFailed`), plus a code refresh of `finora-dq-auth` / `finora-dq-api` (their zips carry the extended `authlib`; no behaviour change). No replacement, no destroy, FinoraDqWeb untouched. Deploy logs: `deploy_log_voice.txt`, `deploy_log_voice_2.txt` (agent Lambda code only: a header-presence log line).
- **ElevenLabs** (`scripts/push_voice_agent.py --apply`): agent `agent_7401m7nnq0dcew2tqtsk7e158k62` (es, signed URLs required, retention 0, transcripts and audio deleted, voice not recorded, 300 s max, concurrency 2, daily 5), 5 tools (2 webhooks to `https://d1smzfxmkay9lx.cloudfront.net`, 3 client). Key: el_toldo's, read-only from SSM us-east-1; tier `payg`, 10,000 credits/month (2,446 used at check), shared with el_toldo's production agents -> credit floor 6,000 in `/api/agent-session`.
- **Kimi K3** (`us.moonshotai.kimi-k3`, Bedrock us-east-1): no Marketplace agreement; forced tool use works; `temperature` is refused. Nested arrays in tool input degenerate, so the spec tool takes flat `derived_*` fields that code maps back to the §2.1 spec.
- **First briefing**: Glue run `jr_661a88d4…` on gold `r20261117T201211Z`, SUCCEEDED in 98 s (197 DPU-s); `agent/briefing/r20261117T201211Z.json` status ok, 7 Kimi facts, all passed the §4.4 check (0 regenerated / replaced / dropped).
- **Checks**: CloudFront forwards `Authorization` to `/api/agent/*` (log `agent.unauthenticated has_authorization=true`); every route returns its contract 401 without a valid token.
- **Eval** (`scripts/voice_eval.py --lambda`): 22/22 (20 questions; #10 and #19 as finance and revops), 1.9–10.9 s each; `evidence/voice_eval/`.
- **Tests**: dq_api 49 (10 new), auth 19, infra 6 (state-machine test extended), voice 15 (new), etl 152 passed + 7 skipped without Spark.
