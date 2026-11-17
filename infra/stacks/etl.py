"""FinoraDlEtl: the data lake ETL on AWS Glue, as in the reference architecture
(docs/aws_architecture/data-lake-voice-dashboard-architecture.html, 03-04).

  EventBridge (staging Object Created) -> Step Functions finora-dl-ingest
    -> Glue finora-dl-bronze-ingest  (Glue 5.0, driver-side Python)
    -> Glue finora-dl-silver-build   (Glue 5.0 Spark, Iceberg, Glue Data Quality; MaxConcurrentRuns=1)
    -> Glue finora-dl-dq-publish     (Glue 5.0, driver-side Python; serving JSON, latest.json last)
    -> Glue finora-dl-gold-build     (Glue 5.0 Spark, Iceberg; write-audit-publish; acq/latest.json last)
    -> EventBridge gold.refreshed
    -> Glue finora-dl-gold-mrr       (Glue 5.0 Spark, Iceberg; MRR model; mrr/latest.json last)

The gold step runs only after the DQ publish succeeded, and its failure goes to
its own Fail state (never RecordFailedRun): dq/* is never touched by a gold
failure, the execution ends FAILED and finora-dl-ingest-failed alerts on SNS.

All data movement and transformation in the lake runs on Glue. Lambdas remain
only for the API and auth (FinoraDqAuth, FinoraDqApi). Also here: the Glue DQ
rulesets finora-dl-<dataset>, the Glue databases finora_silver and finora_dq
(Iceberg tables, created by the silver job), the SNS alert topic and the Athena
workgroup.
"""

from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_athena as athena
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_glue as glue
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3_assets as assets
from aws_cdk import aws_sns as sns
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

from . import names

from common import config, dqdl  # noqa: E402  (etl/ is on sys.path, see app.py)
from gold_mrr import schemas as mrr_schemas  # noqa: E402

GLUE_VERSION = "5.0"
JOB_LOG_GROUP = "/aws-glue/jobs/finora-dl"
ICEBERG_WAREHOUSE = f"s3://{names.SILVER}/iceberg/"
JOBS = {  # name -> (script, timeout minutes, max concurrent runs)
    "bronze": ("finora-dl-bronze-ingest", "bronze_ingest_job.py", 10, 3),
    "silver": ("finora-dl-silver-build", "silver_build_job.py", 30, 1),
    "publish": ("finora-dl-dq-publish", "dq_publish_job.py", 10, 1),
    "gold": ("finora-dl-gold-build", "gold_build_job.py", 15, 1),
    "mrr": ("finora-dl-gold-mrr", "gold_mrr_job.py", 15, 1),
    "briefing": ("finora-dl-agent-briefing", "agent_briefing_job.py", 10, 1),
}
GOLD_WAREHOUSE = f"s3://{names.GOLD}/iceberg/"
RATE_TABLE = "funnel_conversion_rate"
GOLD_TABLES = ["dim_month", "dim_industry", "dim_customer", "dim_spend_category", "dim_funnel_stage",
               "fact_acquisition", "fact_customer_month_revenue", "fact_sm_spend", "agg_acquisition_month",
               "agg_won_month_industry", "agg_industry_profile", "agg_won_spend_lag_corr", "gold_build_status"]


class DlEtlStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, etl_dir: Path, glue_lib_dir: Path, gold_lib_dir: Path,
                 mrr_lib_dir: Path, briefing_lib_dir: Path, **kw) -> None:
        super().__init__(scope, cid, **kw)
        acct, region = self.account, self.region
        cfg = config.load()

        def bucket_arn(b: str, path: str = "") -> str:
            return f"arn:aws:s3:::{b}{path}"

        # ---- Logs: one group for the Glue jobs' continuous logs, plus Glue's
        # default groups, all with a retention (Glue would create them without one).
        for lid, name in (("GlueJobLogs", JOB_LOG_GROUP), ("GlueOutputLogs", "/aws-glue/jobs/output"),
                          ("GlueErrorLogs", "/aws-glue/jobs/error")):
            logs.LogGroup(self, lid, log_group_name=name, retention=logs.RetentionDays.ONE_MONTH,
                          removal_policy=RemovalPolicy.RETAIN)

        # ---- Code as CDK assets: the shared library zip (--extra-py-files) and one script per job
        lib = assets.Asset(self, "GlueLib", path=str(glue_lib_dir))
        # The gold job has its own library zip (common + gold_build + the gold config),
        # so adding it changes nothing in the bronze, silver and publish jobs.
        gold_lib = assets.Asset(self, "GlueGoldLib", path=str(gold_lib_dir))
        # The gold MRR job has its own zip too (common + gold_mrr + its config): adding it
        # changes nothing in the other four jobs, including the acquisition gold job.
        mrr_lib = assets.Asset(self, "GlueGoldMrrLib", path=str(mrr_lib_dir))
        # The voice briefing job has its own zip too (agentlib + sqlglot + the catalog): adding it
        # changes nothing in the other five jobs.
        briefing_lib = assets.Asset(self, "GlueBriefingLib", path=str(briefing_lib_dir))
        libs = {k: (gold_lib if k == "gold" else mrr_lib if k == "mrr" else briefing_lib if k == "briefing" else lib)
                for k in JOBS}
        scripts = {k: assets.Asset(self, f"{k.title()}Script", path=str(etl_dir / "glue_jobs" / s))
                   for k, (_, s, _, _) in JOBS.items()}

        # ---- Least-privilege roles, one per job
        def role(key: str, desc: str) -> iam.Role:
            r = iam.Role(self, f"{key.title()}Role", role_name=f"finora-dl-glue-{key}",
                         assumed_by=iam.ServicePrincipal("glue.amazonaws.com"), description=desc)
            libs[key].grant_read(r)
            scripts[key].grant_read(r)
            r.add_to_policy(iam.PolicyStatement(
                actions=["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"],
                resources=[f"arn:aws:logs:{region}:{acct}:log-group:{g}:*"
                           for g in (JOB_LOG_GROUP, "/aws-glue/jobs/output", "/aws-glue/jobs/error")]))
            return r

        def s3(r: iam.Role, actions: list[str], resources: list[str]) -> None:
            r.add_to_policy(iam.PolicyStatement(actions=actions, resources=resources))

        staging_prefixes = [cfg["datasets"][ds]["staging_prefix"] for ds in cfg["dataset_order"]]
        bronze_role = role("bronze", "finora-dl-bronze-ingest: read staging, write bronze")
        s3(bronze_role, ["s3:GetObject", "s3:GetObjectVersion"],
           [bucket_arn(names.STAGING, f"/{p}*") for p in staging_prefixes])
        s3(bronze_role, ["s3:ListBucket"], [bucket_arn(names.STAGING), bucket_arn(names.BRONZE)])
        s3(bronze_role, ["s3:GetObject", "s3:PutObject"], [bucket_arn(names.BRONZE, "/*")])

        silver_role = role("silver", "finora-dl-silver-build: read bronze, write silver Iceberg + DQ, Glue DQ")
        s3(silver_role, ["s3:GetObject"], [bucket_arn(names.BRONZE, "/*")])
        s3(silver_role, ["s3:ListBucket"], [bucket_arn(names.BRONZE), bucket_arn(names.SILVER), bucket_arn(names.SERVING)])
        s3(silver_role, ["s3:GetObject", "s3:PutObject"],
           [bucket_arn(names.SILVER, p) for p in ("/iceberg/*", "/_runs/*", "/_glue_tmp/*")])
        s3(silver_role, ["s3:GetObject"], [bucket_arn(names.SERVING, "/dq/latest.json")])
        cat = f"arn:aws:glue:{region}:{acct}"
        silver_role.add_to_policy(iam.PolicyStatement(
            actions=["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:CreateTable", "glue:UpdateTable"],
            resources=[f"{cat}:catalog", f"{cat}:database/finora_silver", f"{cat}:database/finora_dq",
                       f"{cat}:table/finora_silver/*", f"{cat}:table/finora_dq/*"]))
        silver_role.add_to_policy(iam.PolicyStatement(
            actions=["glue:GetDataQualityRuleset"],
            resources=[f"{cat}:dataQualityRuleset/{dqdl.ruleset_name(ds)}" for ds in cfg["dataset_order"]]))
        # PublishDataQuality has no resource-level permissions.
        silver_role.add_to_policy(iam.PolicyStatement(actions=["glue:PublishDataQuality"], resources=["*"]))

        publish_role = role("publish", "finora-dl-dq-publish: read run bundles, write the DQ serving store")
        s3(publish_role, ["s3:GetObject"], [bucket_arn(names.SILVER, "/_runs/*"), bucket_arn(names.BRONZE, "/_runs/*")])
        s3(publish_role, ["s3:ListBucket"], [bucket_arn(names.SILVER), bucket_arn(names.BRONZE), bucket_arn(names.SERVING)])
        s3(publish_role, ["s3:GetObject", "s3:PutObject"], [bucket_arn(names.SERVING, "/dq/*")])
        topic = sns.Topic(self, "Alerts", topic_name=names.ALERT_TOPIC, enforce_ssl=True)

        # Gold: read silver (all partitions), write the job-owned gold tables, the run
        # report and the acquisition serving snapshot. Never the user-owned rates table.
        gold_role = role("gold", "finora-dl-gold-build: read silver, write gold Iceberg + acq serving; "
                                 "never the rates table")
        s3(gold_role, ["s3:GetObject"], [bucket_arn(names.SILVER, "/iceberg/finora_silver/*")])
        s3(gold_role, ["s3:ListBucket"], [bucket_arn(names.SILVER), bucket_arn(names.GOLD)])
        s3(gold_role, ["s3:GetObject", "s3:PutObject"],
           [bucket_arn(names.GOLD, p) for p in (f"/iceberg/{names.GOLD_DB}/*", "/_runs/*", "/_glue_tmp/*")])
        s3(gold_role, ["s3:GetObject"], [bucket_arn(names.SERVING, "/dq/runs.json")])
        s3(gold_role, ["s3:PutObject"], [bucket_arn(names.SERVING, "/acq/*")])
        gold_role.add_to_policy(iam.PolicyStatement(
            actions=["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:CreateTable", "glue:UpdateTable"],
            resources=[f"{cat}:catalog", f"{cat}:database/{names.GOLD_DB}", f"{cat}:table/{names.GOLD_DB}/*"]))
        gold_role.add_to_policy(iam.PolicyStatement(
            actions=["glue:GetDatabase", "glue:GetTable", "glue:GetTables"],
            resources=[f"{cat}:database/finora_silver", f"{cat}:table/finora_silver/*"]))
        topic.grant_publish(gold_role)
        # §6.5: IAM, not only code, keeps the rebuild off the user-owned rates table. The
        # table is created and seeded by the deploy step (infra/gold_athena_ddl.py), never
        # by this role, so the deny applies from the first run.
        gold_role.add_to_policy(iam.PolicyStatement(
            sid="DenyRateTableDataAndMetadataWrites", effect=iam.Effect.DENY,
            actions=["s3:PutObject", "s3:DeleteObject", "s3:DeleteObjectVersion"],
            resources=[bucket_arn(names.GOLD, f"/iceberg/{names.GOLD_DB}/{RATE_TABLE}/*")]))
        gold_role.add_to_policy(iam.PolicyStatement(
            sid="DenyRateTableCatalogWrites", effect=iam.Effect.DENY,
            actions=["glue:CreateTable", "glue:UpdateTable", "glue:DeleteTable"],
            resources=[f"{cat}:table/{names.GOLD_DB}/{RATE_TABLE}"]))
        # Gold MRR: read the four silver tables it uses, write only its own gold tables,
        # its run report and the mrr/* serving snapshot. No write on any acquisition
        # table, the rates table, dq/* or acq/*: nothing outside these prefixes is allowed.
        mrr_role = role("mrr", "finora-dl-gold-mrr: read silver, write the gold MRR Iceberg tables + mrr serving")
        s3(mrr_role, ["s3:GetObject"],
           [bucket_arn(names.SILVER, f"/iceberg/finora_silver/{t}/*") for t in mrr_schemas.SILVER_INPUTS])
        s3(mrr_role, ["s3:ListBucket"], [bucket_arn(names.SILVER), bucket_arn(names.GOLD)])
        s3(mrr_role, ["s3:GetObject", "s3:PutObject"],
           [bucket_arn(names.GOLD, f"/iceberg/{names.GOLD_DB}/{t}/*") for t in mrr_schemas.TABLE_NAMES]
           + [bucket_arn(names.GOLD, "/_glue_tmp/mrr/*")])
        s3(mrr_role, ["s3:PutObject"], [bucket_arn(names.GOLD, "/_runs/run_id=*/mrr_report.json")])
        s3(mrr_role, ["s3:GetObject"], [bucket_arn(names.SERVING, "/dq/runs.json")])
        s3(mrr_role, ["s3:PutObject"], [bucket_arn(names.SERVING, "/mrr/*")])
        mrr_role.add_to_policy(iam.PolicyStatement(
            actions=["glue:GetDatabase", "glue:GetTable", "glue:GetTables"],
            resources=[f"{cat}:catalog", f"{cat}:database/{names.GOLD_DB}", f"{cat}:table/{names.GOLD_DB}/*",
                       f"{cat}:database/finora_silver"]
                      + [f"{cat}:table/finora_silver/{t}" for t in mrr_schemas.SILVER_INPUTS]))
        mrr_role.add_to_policy(iam.PolicyStatement(
            actions=["glue:CreateTable", "glue:UpdateTable"],
            resources=[f"{cat}:catalog", f"{cat}:database/{names.GOLD_DB}"]
                      + [f"{cat}:table/{names.GOLD_DB}/{t}" for t in mrr_schemas.TABLE_NAMES]))
        # Agent briefing: read the agent's governed gold objects (Athena, finora-dl), the run reports
        # and the serving snapshots; call Kimi K3 (Bedrock us-east-1); write only agent/briefing/*.
        briefing_role = role("briefing", "finora-dl-agent-briefing: read governed gold + serving, Kimi K3, "
                                         "write agent/briefing/* only")
        from . import agent_iam
        agent_iam.grant_agent_read(briefing_role, acct, region)
        s3(briefing_role, ["s3:PutObject"], [bucket_arn(names.SERVING, "/agent/briefing/*")])
        roles = {"bronze": bronze_role, "silver": silver_role, "publish": publish_role, "gold": gold_role,
                 "mrr": mrr_role, "briefing": briefing_role}

        # ---- Glue Data Quality rulesets (generated from the approved rules config)
        rulesets = []
        for ds in cfg["dataset_order"]:
            rulesets.append(glue.CfnDataQualityRuleset(
                self, f"Ruleset{ds.title().replace('_', '')}", name=dqdl.ruleset_name(ds),
                ruleset=dqdl.ruleset(cfg, ds),
                description=f"Finora DL row-level quality rules for {ds} (approved_data_rules.md ids in labels)"))

        # ---- Glue jobs
        buckets = {"--STAGING_BUCKET": names.STAGING, "--BRONZE_BUCKET": names.BRONZE,
                   "--SILVER_BUCKET": names.SILVER, "--SERVING_BUCKET": names.SERVING}
        jobs = {}
        for key, (name, _, timeout, conc) in JOBS.items():
            args = {
                "--job-language": "python",
                "--job-bookmark-option": "job-bookmark-disable",
                "--enable-continuous-cloudwatch-log": "true",
                "--continuous-log-logGroup": JOB_LOG_GROUP,
                "--enable-metrics": "false",
                "--enable-spark-ui": "false",
                "--enable-glue-datacatalog": "false",
                "--extra-py-files": libs[key].s3_object_url,
                **buckets,
            }
            if key == "silver":
                args.update({"--datalake-formats": "iceberg", "--iceberg_warehouse": ICEBERG_WAREHOUSE,
                             "--TempDir": f"s3://{names.SILVER}/_glue_tmp/"})
            if key == "publish":
                args["--mode"] = "published"
            if key == "gold":
                args = {k: v for k, v in args.items() if k not in buckets}
                args.update({"--datalake-formats": "iceberg", "--iceberg_warehouse": GOLD_WAREHOUSE,
                             "--TempDir": f"s3://{names.GOLD}/_glue_tmp/", "--GOLD_BUCKET": names.GOLD,
                             "--SERVING_BUCKET": names.SERVING, "--ALERT_TOPIC_ARN": topic.topic_arn})
            if key == "mrr":
                args = {k: v for k, v in args.items() if k not in buckets}
                args.update({"--datalake-formats": "iceberg", "--iceberg_warehouse": GOLD_WAREHOUSE,
                             "--TempDir": f"s3://{names.GOLD}/_glue_tmp/mrr/", "--GOLD_BUCKET": names.GOLD,
                             "--SERVING_BUCKET": names.SERVING})
            if key == "briefing":
                args = {k: v for k, v in args.items() if k not in buckets}
                args.update({"--GOLD_BUCKET": names.GOLD, "--SERVING_BUCKET": names.SERVING,
                             "--ATHENA_WORKGROUP": names.ATHENA_WORKGROUP, "--BEDROCK_MODEL_ID": names.BEDROCK_PROFILE,
                             "--BEDROCK_REGION": names.BEDROCK_REGION})
            jobs[key] = glue.CfnJob(
                self, f"{key.title()}Job", name=name, role=roles[key].role_arn, glue_version=GLUE_VERSION,
                command=glue.CfnJob.JobCommandProperty(name="glueetl", python_version="3",
                                                       script_location=scripts[key].s3_object_url),
                worker_type="G.1X", number_of_workers=2, timeout=timeout, max_retries=0,
                execution_property=glue.CfnJob.ExecutionPropertyProperty(max_concurrent_runs=conc),
                default_arguments=args,
                description=f"Finora DL {key} (FinoraDlEtl)")
            jobs[key].node.add_dependency(roles[key])
        for r in rulesets:
            jobs["silver"].node.add_dependency(r)

        # ---- Step Functions: run_id from the execution start time, then the four jobs
        parts = sfn.Pass(self, "SplitStartTime", parameters={
            "parts": sfn.JsonPath.string_split(sfn.JsonPath.string_at("$$.Execution.StartTime"), "-:T.Z"),
            "event": sfn.JsonPath.object_at("$")})
        p = [sfn.JsonPath.array_get_item(sfn.JsonPath.list_at("$.parts"), i) for i in range(6)]
        ids = sfn.Pass(self, "RunIds", parameters={
            "run_id": sfn.JsonPath.format("r{}{}{}T{}{}{}Z", *p),
            "started_at": sfn.JsonPath.format("{}-{}-{}T{}:{}:{}Z", *p),
            "event": sfn.JsonPath.object_at("$.event")})

        def run_job(state_id: str, key: str, extra: dict, result_path: str | None) -> tasks.GlueStartJobRun:
            t = tasks.GlueStartJobRun(
                self, state_id, glue_job_name=JOBS[key][0], integration_pattern=sfn.IntegrationPattern.RUN_JOB,
                arguments=sfn.TaskInput.from_object({"--run_id": sfn.JsonPath.string_at("$.run_id"),
                                                     "--started_at": sfn.JsonPath.string_at("$.started_at"), **extra}),
                result_selector={"JobRunId": sfn.JsonPath.string_at("$.Id"),
                                 "JobRunState": sfn.JsonPath.string_at("$.JobRunState"),
                                 "ExecutionTime": sfn.JsonPath.number_at("$.ExecutionTime")},
                result_path=result_path or sfn.JsonPath.DISCARD)
            # Serialized runs: StartJobRun is refused while a run is in progress.
            t.add_retry(errors=["Glue.ConcurrentRunsExceededException"], interval=Duration.seconds(60),
                        max_attempts=20, backoff_rate=1.5, max_delay=Duration.minutes(5),
                        jitter_strategy=sfn.JitterType.FULL)
            t.add_retry(errors=["Glue.AWSGlueException", "Glue.InternalServiceException",
                                "Glue.OperationTimeoutException", "Glue.ThrottlingException"],
                        interval=Duration.seconds(10), max_attempts=3, backoff_rate=2)
            return t

        bronze = run_job("BronzeIngest", "bronze",
                         {"--event": sfn.JsonPath.json_to_string(sfn.JsonPath.object_at("$.event"))}, "$.bronze")
        silver = run_job("SilverBuild", "silver", {}, "$.silver")
        publish = run_job("DqPublish", "publish", {"--mode": "published"}, "$.publish")
        record = run_job("RecordFailedRun", "publish", {"--mode": "failed"}, None)
        fail = sfn.Fail(self, "RunFailed", cause="A run control or pipeline step failed; the previous publish stays live")
        record.add_catch(fail, result_path="$.record_error")
        record.next(fail)
        for t in (silver, publish):
            t.add_catch(record, result_path="$.error")
        bronze.add_catch(fail, result_path="$.error")
        # Gold runs after the DQ publish; its failure never reaches RecordFailedRun (dq/*).
        gold = run_job("GoldBuild", "gold", {}, "$.gold")
        gold_fail = sfn.Fail(self, "GoldFailed", cause="The gold build failed after the DQ publish succeeded; "
                                                        "the previous gold build and acq/latest.json stay live")
        gold.add_catch(gold_fail, result_path="$.gold_error")
        refreshed = tasks.EventBridgePutEvents(
            self, "GoldRefreshed", result_path=sfn.JsonPath.DISCARD,
            entries=[tasks.EventBridgePutEventsEntry(
                source="finora.dl", detail_type="gold.refreshed",
                detail=sfn.TaskInput.from_object({
                    "refresh_version": sfn.JsonPath.string_at("$.run_id"),
                    "run_id": sfn.JsonPath.string_at("$.run_id"),
                    "database": names.GOLD_DB,
                    "tables": GOLD_TABLES,
                    "report": sfn.JsonPath.format(f"s3://{names.GOLD}/_runs/run_id={{}}/gold_report.json",
                                                  sfn.JsonPath.string_at("$.run_id")),
                    "serving_summary": sfn.JsonPath.format(f"s3://{names.SERVING}/acq/runs/{{}}/summary.json",
                                                           sfn.JsonPath.string_at("$.run_id"))}))])
        refreshed.add_retry(errors=["States.ALL"], interval=Duration.seconds(5), max_attempts=3, backoff_rate=2)
        # Gold MRR runs after the acquisition publish and its event; its failure goes to its
        # own Fail state: dq/*, acq/* and the acquisition tables are already published.
        mrr = run_job("GoldMrrBuild", "mrr", {}, "$.gold_mrr")
        mrr_fail = sfn.Fail(self, "GoldMrrFailed", cause="The gold MRR build failed after the DQ and acquisition "
                                                          "publishes succeeded; the previous mrr/latest.json stays live")
        mrr.add_catch(mrr_fail, result_path="$.gold_mrr_error")
        # The voice briefing runs last; its failure goes to its own Fail state: dq/*, acq/* and mrr/*
        # are already published and the job can write only agent/briefing/* (IAM).
        briefing = run_job("AgentBriefing", "briefing", {}, "$.agent_briefing")
        briefing_fail = sfn.Fail(self, "BriefingFailed", cause="The voice briefing failed after every publish "
                                                                "succeeded; the previous agent/briefing/latest.json stays live")
        briefing.add_catch(briefing_fail, result_path="$.agent_briefing_error")
        sm_logs = logs.LogGroup(self, "SfnLogs", log_group_name="/aws/vendedlogs/states/finora-dl-ingest",
                                retention=logs.RetentionDays.ONE_MONTH, removal_policy=RemovalPolicy.RETAIN)
        machine = sfn.StateMachine(
            self, "Ingest", state_machine_name="finora-dl-ingest",
            definition_body=sfn.DefinitionBody.from_chainable(
                parts.next(ids).next(bronze).next(silver).next(publish).next(gold).next(refreshed).next(mrr)
                .next(briefing).next(sfn.Succeed(self, "Published"))),
            timeout=Duration.hours(3),
            logs=sfn.LogOptions(destination=sm_logs, level=sfn.LogLevel.ERROR, include_execution_data=False))
        for j in jobs.values():
            machine.node.add_dependency(j)

        events.Rule(self, "StagingObjectCreated", rule_name="finora-dl-staging-object-created",
                    event_pattern=events.EventPattern(
                        source=["aws.s3"], detail_type=["Object Created"],
                        detail={"bucket": {"name": [names.STAGING]},
                                "object": {"key": [{"prefix": p} for p in staging_prefixes]}}),
                    targets=[targets.SfnStateMachine(machine)])
        events.Rule(self, "IngestFailed", rule_name="finora-dl-ingest-failed",
                    event_pattern=events.EventPattern(
                        source=["aws.states"], detail_type=["Step Functions Execution Status Change"],
                        detail={"status": ["FAILED", "TIMED_OUT", "ABORTED"],
                                "stateMachineArn": [machine.state_machine_arn]}),
                    targets=[targets.SnsTopic(topic)])

        # ---- Glue Data Catalog (Iceberg tables are created by the silver job) + Athena
        for db_name, desc in (("finora_silver", "Silver Iceberg tables; one snapshot per run, tagged <run_id>"),
                              ("finora_dq", "DQ store Iceberg tables: findings and excluded_rows (quarantine)")):
            glue.CfnDatabase(self, db_name, catalog_id=acct,
                             database_input=glue.CfnDatabase.DatabaseInputProperty(
                                 name=db_name, description=desc, location_uri=f"{ICEBERG_WAREHOUSE}{db_name}/"))
        glue.CfnDatabase(self, names.GOLD_DB, catalog_id=acct, database_input=glue.CfnDatabase.DatabaseInputProperty(
            name=names.GOLD_DB, location_uri=f"{GOLD_WAREHOUSE}{names.GOLD_DB}/",
            description="Gold acquisition model (docs/gold_acquisition_model.md): Iceberg tables written by "
                        "finora-dl-gold-build, the user-owned funnel_conversion_rate and the Athena views"))

        athena.CfnWorkGroup(self, "WorkGroup", name="finora-dl", state="ENABLED",
                            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                                enforce_work_group_configuration=True,
                                bytes_scanned_cutoff_per_query=1024 ** 3,
                                publish_cloud_watch_metrics_enabled=True,
                                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                                    output_location=f"s3://{names.ATHENA_RESULTS}/finora-dl/",
                                    encryption_configuration=athena.CfnWorkGroup.EncryptionConfigurationProperty(
                                        encryption_option="SSE_S3"))))
        CfnOutput(self, "AlertTopicArn", value=topic.topic_arn)
        CfnOutput(self, "StateMachineArn", value=machine.state_machine_arn)
        CfnOutput(self, "GlueJobs", value=",".join(n for n, _, _, _ in JOBS.values()))
