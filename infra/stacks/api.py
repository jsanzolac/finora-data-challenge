"""FinoraDqApi: HTTP API with /api/auth/*, /api/dq/* and /api/acq/*, and the dq_api Lambda.

The dq_api Lambda has its own code asset (DQ routes + acquisition routes, entry
api_handler.handler); the auth Lambda keeps the shared asset unchanged.
/api/acq/scenarios reads and appends the user-owned rates table through Athena
(workgroup finora-dl): the role can read only the two gold objects those views
read, write only the rates table's prefix, and read no hr_sensitive=true data."""

from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigw
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_apigatewayv2_integrations as integ
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

from . import names


class DqApiStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, asset_dir: Path, dq_asset_dir: Path, auth,
                 agent_asset_dir: Path | None = None, voice: dict | None = None, **kw) -> None:
        super().__init__(scope, cid, **kw)
        serving = s3.Bucket.from_bucket_name(self, "Serving", names.SERVING)
        lg = logs.LogGroup(self, "DqApiLogs", log_group_name="/aws/lambda/finora-dq-api",
                           retention=logs.RetentionDays.ONE_MONTH, removal_policy=RemovalPolicy.RETAIN)
        # 28 s: Athena reads for /api/acq/scenarios, under API Gateway's 30 s integration limit.
        fn = lambda_.Function(self, "DqApi", function_name="finora-dq-api", runtime=lambda_.Runtime.PYTHON_3_13,
                              architecture=lambda_.Architecture.ARM_64, handler="api_handler.handler",
                              code=lambda_.Code.from_asset(str(dq_asset_dir)), memory_size=1024,
                              timeout=Duration.seconds(28), log_group=lg,
                              environment={"SERVING_BUCKET": names.SERVING, "USERS_TABLE": names.USERS_TABLE,
                                           "SESSIONS_TABLE": names.SESSIONS_TABLE,
                                           "RATE_LIMITS_TABLE": names.RATE_LIMITS_TABLE,
                                           "GOLD_DATABASE": names.GOLD_DB,
                                           "ATHENA_WORKGROUP": names.ATHENA_WORKGROUP})
        serving.grant_read(fn, "dq/*")
        serving.grant_read(fn, "acq/*")
        acct, region = self.account, self.region
        cat = f"arn:aws:glue:{region}:{acct}"
        rate_prefix = f"iceberg/{names.GOLD_DB}/funnel_conversion_rate/"
        stage_prefix = f"iceberg/{names.GOLD_DB}/dim_funnel_stage/"
        results_prefix = f"{names.ATHENA_WORKGROUP}/"
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults"],
            resources=[f"arn:aws:athena:{region}:{acct}:workgroup/{names.ATHENA_WORKGROUP}"]))
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["glue:GetDatabase", "glue:GetTable", "glue:GetTables"],
            resources=[f"{cat}:catalog", f"{cat}:database/{names.GOLD_DB}", f"{cat}:table/{names.GOLD_DB}/*"]))
        fn.add_to_role_policy(iam.PolicyStatement(  # Athena's Iceberg INSERT commits the new metadata here
            actions=["glue:UpdateTable"], resources=[f"{cat}:table/{names.GOLD_DB}/funnel_conversion_rate"]))
        gold_arn = f"arn:aws:s3:::{names.GOLD}"
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"],
            resources=[f"{gold_arn}/{rate_prefix}*"]))
        fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[f"{gold_arn}/{stage_prefix}*"]))
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket"], resources=[gold_arn],
            conditions={"StringLike": {"s3:prefix": [f"{rate_prefix}*", f"{stage_prefix}*"]}}))
        fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetBucketLocation"], resources=[gold_arn]))
        res_arn = f"arn:aws:s3:::{names.ATHENA_RESULTS}"
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"],
            resources=[f"{res_arn}/{results_prefix}*"]))
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket"], resources=[res_arn], conditions={"StringLike": {"s3:prefix": [f"{results_prefix}*"]}}))
        fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetBucketLocation"], resources=[res_arn]))
        # /api/mrr/*: the gold MRR job's serving snapshot, read only
        fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject"],
                                                  resources=[f"arn:aws:s3:::{names.SERVING}/mrr/*"]))
        auth.users.grant_read_data(fn)
        auth.sessions.grant_read_data(fn)
        self.http_api = apigw.HttpApi(self, "HttpApi", api_name="finora-dq-api", create_default_stage=True)
        stage = self.http_api.default_stage.node.default_child
        stage.default_route_settings = apigw.CfnStage.RouteSettingsProperty(
            throttling_burst_limit=50, throttling_rate_limit=25)
        auth_int = integ.HttpLambdaIntegration("AuthInt", auth.fn)
        dq_int = integ.HttpLambdaIntegration("DqInt", fn)
        for method, path in ((apigw.HttpMethod.POST, "/api/auth/login"), (apigw.HttpMethod.POST, "/api/auth/logout"),
                             (apigw.HttpMethod.GET, "/api/auth/session"), (apigw.HttpMethod.POST, "/api/auth/password")):
            self.http_api.add_routes(path=path, methods=[method], integration=auth_int)
        for path in ("/api/dq/runs", "/api/dq/summary", "/api/dq/rules/{rule_id}/datasets/{dataset_id}/records"):
            self.http_api.add_routes(path=path, methods=[apigw.HttpMethod.GET], integration=dq_int)
        for method, path in ((apigw.HttpMethod.GET, "/api/acq/summary"), (apigw.HttpMethod.GET, "/api/acq/scenarios"),
                             (apigw.HttpMethod.POST, "/api/acq/scenarios"),
                             (apigw.HttpMethod.GET, "/api/mrr/summary"), (apigw.HttpMethod.GET, "/api/mrr/movements")):
            self.http_api.add_routes(path=path, methods=[method], integration=dq_int)
        if agent_asset_dir is not None:
            self._voice_agent(agent_asset_dir, auth, voice or {})
        self.api_domain = f"{self.http_api.api_id}.execute-api.{self.region}.amazonaws.com"
        CfnOutput(self, "ApiEndpoint", value=self.http_api.api_endpoint)

    def _voice_agent(self, asset_dir: Path, auth, voice: dict) -> None:
        """finora-dq-agent (contracts/agent_api_contract.md v1.1): its own Lambda and role, so
        only it can read the ElevenLabs key, call Bedrock and read the agent's gold objects."""
        from . import agent_iam
        acct, region = self.account, self.region
        results = ddb.Table(self, "AgentResults", table_name=names.AGENT_RESULTS_TABLE,
                            partition_key=ddb.Attribute(name="pk", type=ddb.AttributeType.STRING),
                            billing_mode=ddb.BillingMode.PAY_PER_REQUEST, time_to_live_attribute="expires_at",
                            removal_policy=RemovalPolicy.RETAIN)
        lg = logs.LogGroup(self, "AgentLogs", log_group_name="/aws/lambda/finora-dq-agent",
                           retention=logs.RetentionDays.ONE_MONTH, removal_policy=RemovalPolicy.RETAIN)
        fn = lambda_.Function(
            self, "Agent", function_name="finora-dq-agent", runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64, handler="agent_api.handler",
            code=lambda_.Code.from_asset(str(asset_dir)), memory_size=1024, timeout=Duration.seconds(28),
            log_group=lg, description="Voice agent API: session, briefing, ask, results (FinoraDqApi)",
            environment={"SERVING_BUCKET": names.SERVING, "GOLD_BUCKET": names.GOLD,
                         "USERS_TABLE": names.USERS_TABLE, "SESSIONS_TABLE": names.SESSIONS_TABLE,
                         "RATE_LIMITS_TABLE": names.RATE_LIMITS_TABLE, "AGENT_TOKENS_TABLE": names.AGENT_TOKENS_TABLE,
                         "AGENT_RESULTS_TABLE": names.AGENT_RESULTS_TABLE, "ATHENA_WORKGROUP": names.ATHENA_WORKGROUP,
                         "BEDROCK_REGION": names.BEDROCK_REGION, "BEDROCK_MODEL_ID": names.BEDROCK_PROFILE,
                         "ELEVENLABS_KEY_PARAM": names.ELEVENLABS_KEY_PARAM,
                         "ELEVENLABS_KEY_REGION": names.ELEVENLABS_KEY_REGION,
                         "ELEVENLABS_AGENT_ID": voice.get("agent_id", ""),
                         "VOICE_CREDIT_FLOOR": str(voice.get("credit_floor", 6000)),
                         "VOICE_SESSIONS_PER_DAY": str(voice.get("sessions_per_day", 5))})
        auth.users.grant_read_data(fn)
        auth.sessions.grant_read_data(fn)
        auth.rate_limits.grant_read_write_data(fn)
        auth.agent_tokens.grant_read_write_data(fn)
        results.grant_read_write_data(fn)
        agent_iam.grant_agent_read(fn, acct, region)
        # The el_toldo ElevenLabs key: this one parameter, read-only, cross-region; decrypt only via SSM.
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{names.ELEVENLABS_KEY_REGION}:{acct}:parameter{names.ELEVENLABS_KEY_PARAM}"]))
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["kms:Decrypt"], resources=[f"arn:aws:kms:{names.ELEVENLABS_KEY_REGION}:{acct}:key/*"],
            conditions={"StringEquals": {"kms:ViaService": f"ssm.{names.ELEVENLABS_KEY_REGION}.amazonaws.com"},
                        "ForAnyValue:StringEquals": {"kms:ResourceAliases": "alias/aws/ssm"}}))
        agent_int = integ.HttpLambdaIntegration("AgentInt", fn)
        for method, path in ((apigw.HttpMethod.POST, "/api/agent-session"), (apigw.HttpMethod.GET, "/api/agent/briefing"),
                             (apigw.HttpMethod.POST, "/api/agent/ask"),
                             (apigw.HttpMethod.GET, "/api/agent/results/{result_id}")):
            self.http_api.add_routes(path=path, methods=[method], integration=agent_int)
        CfnOutput(self, "AgentFunction", value=fn.function_name)
