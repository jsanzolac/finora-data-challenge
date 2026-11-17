"""Least-privilege grants shared by the voice agent's two principals: the API Lambda
finora-dq-agent and the Glue job finora-dl-agent-briefing. Read-only on the agent's
governed gold objects (docs/semantic_layer.md §2.3), an explicit Deny on HR partitions,
Athena in workgroup finora-dl, Kimi K3 on Bedrock (us-east-1 profile + the model ARNs it
routes to; no Marketplace agreement exists for this model)."""

from aws_cdk import aws_iam as iam

from . import names

from agentlib import catalog as SL  # noqa: E402  (voice/ is on sys.path, see app.py)

GOLD_DATA_TABLES = sorted(set(SL.ALLOWED_TABLES) | set(SL.VIEW_BASE_TABLES))


def grant_agent_read(principal: iam.IGrantable, account: str, region: str) -> None:
    add = principal.grant_principal.add_to_principal_policy
    cat = f"arn:aws:glue:{region}:{account}"
    gold = f"arn:aws:s3:::{names.GOLD}"
    prefixes = [f"iceberg/{names.GOLD_DB}/{t}/" for t in GOLD_DATA_TABLES]
    add(iam.PolicyStatement(
        actions=["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults",
                 "athena:StopQueryExecution"],
        resources=[f"arn:aws:athena:{region}:{account}:workgroup/{names.ATHENA_WORKGROUP}"]))
    add(iam.PolicyStatement(  # catalog metadata (views resolve other views); data access is S3, below
        actions=["glue:GetDatabase", "glue:GetTable", "glue:GetTables"],
        resources=[f"{cat}:catalog", f"{cat}:database/{names.GOLD_DB}", f"{cat}:table/{names.GOLD_DB}/*"]))
    add(iam.PolicyStatement(actions=["s3:GetObject"], resources=[f"{gold}/{p}*" for p in prefixes]
                            + [f"{gold}/_runs/run_id=*/gold_report.json", f"{gold}/_runs/run_id=*/mrr_report.json"]))
    add(iam.PolicyStatement(actions=["s3:ListBucket"], resources=[gold],
                            conditions={"StringLike": {"s3:prefix": [f"{p}*" for p in prefixes]}}))
    add(iam.PolicyStatement(actions=["s3:GetBucketLocation"], resources=[gold]))
    add(iam.PolicyStatement(  # CDO-11(2) / semantic layer §2.3 rule 7: HR amounts never reach the agent
        sid="DenyHrSensitiveSpend", effect=iam.Effect.DENY, actions=["s3:GetObject"],
        resources=[f"{gold}/iceberg/{names.GOLD_DB}/fact_sm_spend/data/hr_sensitive=true/*",
                   f"arn:aws:s3:::{names.SILVER}/*"]))
    res = f"arn:aws:s3:::{names.ATHENA_RESULTS}"
    rp = f"{names.ATHENA_WORKGROUP}/"
    add(iam.PolicyStatement(actions=["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload",
                                     "s3:ListMultipartUploadParts"], resources=[f"{res}/{rp}*"]))
    add(iam.PolicyStatement(actions=["s3:ListBucket"], resources=[res], conditions={"StringLike": {"s3:prefix": [f"{rp}*"]}}))
    add(iam.PolicyStatement(actions=["s3:GetBucketLocation"], resources=[res]))
    serving = f"arn:aws:s3:::{names.SERVING}"
    add(iam.PolicyStatement(actions=["s3:GetObject"], resources=[
        f"{serving}/acq/latest.json", f"{serving}/mrr/runs/*/summary.json", f"{serving}/dq/runs/*/summary.json",
        f"{serving}/agent/briefing/*"]))
    grant_bedrock(principal, account)


def grant_bedrock(principal: iam.IGrantable, account: str) -> None:
    principal.grant_principal.add_to_principal_policy(iam.PolicyStatement(
        sid="KimiK3OnBedrock", actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
        resources=[f"arn:aws:bedrock:{names.BEDROCK_REGION}:{account}:inference-profile/{names.BEDROCK_PROFILE}"]
                  + [f"arn:aws:bedrock:{r}::foundation-model/{names.BEDROCK_MODEL}" for r in names.BEDROCK_MODEL_REGIONS]))

