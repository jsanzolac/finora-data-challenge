"""FinoraDqAuth: users, sessions (TTL) and rate_limits tables, and the auth Lambda."""

from pathlib import Path

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from . import names


class DqAuthStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, asset_dir: Path, **kw) -> None:
        super().__init__(scope, cid, **kw)
        self.users = ddb.Table(self, "Users", table_name=names.USERS_TABLE,
                               partition_key=ddb.Attribute(name="email", type=ddb.AttributeType.STRING),
                               billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
                               point_in_time_recovery_specification=ddb.PointInTimeRecoverySpecification(
                                   point_in_time_recovery_enabled=True),
                               removal_policy=RemovalPolicy.RETAIN)
        self.sessions = ddb.Table(self, "Sessions", table_name=names.SESSIONS_TABLE,
                                  partition_key=ddb.Attribute(name="token_hash", type=ddb.AttributeType.STRING),
                                  billing_mode=ddb.BillingMode.PAY_PER_REQUEST, time_to_live_attribute="expires_at",
                                  removal_policy=RemovalPolicy.RETAIN)
        self.sessions.add_global_secondary_index(
            index_name="by_email", partition_key=ddb.Attribute(name="email", type=ddb.AttributeType.STRING),
            projection_type=ddb.ProjectionType.KEYS_ONLY)
        self.rate_limits = ddb.Table(self, "RateLimits", table_name=names.RATE_LIMITS_TABLE,
                                     partition_key=ddb.Attribute(name="pk", type=ddb.AttributeType.STRING),
                                     billing_mode=ddb.BillingMode.PAY_PER_REQUEST, time_to_live_attribute="ttl",
                                     removal_policy=RemovalPolicy.RETAIN)
        # Voice agent tokens (contracts/agent_api_contract.md v1.1): SHA-256 hashes only, 45-minute TTL.
        # A table of their own, so an agent token can never be accepted as a dq_session cookie.
        self.agent_tokens = ddb.Table(self, "AgentTokens", table_name=names.AGENT_TOKENS_TABLE,
                                      partition_key=ddb.Attribute(name="token_hash", type=ddb.AttributeType.STRING),
                                      billing_mode=ddb.BillingMode.PAY_PER_REQUEST, time_to_live_attribute="expires_at",
                                      removal_policy=RemovalPolicy.RETAIN)
        lg = logs.LogGroup(self, "AuthLogs", log_group_name="/aws/lambda/finora-dq-auth",
                           retention=logs.RetentionDays.ONE_MONTH, removal_policy=RemovalPolicy.RETAIN)
        self.fn = lambda_.Function(self, "Auth", function_name="finora-dq-auth",
                                   runtime=lambda_.Runtime.PYTHON_3_13, architecture=lambda_.Architecture.ARM_64,
                                   handler="auth_handler.handler", code=lambda_.Code.from_asset(str(asset_dir)),
                                   memory_size=1024, timeout=Duration.seconds(10), log_group=lg,
                                   environment={"USERS_TABLE": names.USERS_TABLE,
                                                "SESSIONS_TABLE": names.SESSIONS_TABLE,
                                                "RATE_LIMITS_TABLE": names.RATE_LIMITS_TABLE})
        self.users.grant_read_write_data(self.fn)
        self.sessions.grant_read_write_data(self.fn)
        self.rate_limits.grant_read_write_data(self.fn)
