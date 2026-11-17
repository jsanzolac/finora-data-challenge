"""FinoraDlStorage: the four existing lake buckets (imported, RETAIN) plus serving
and athena-results. The legacy bucket is not touched.

al-test-dl-gold was created outside CloudFormation and is imported with its own
context flag (`-c import_gold=true` synthesizes it exactly as it is today:
SSE-S3, all four BPA flags, BucketOwnerEnforced, versioning off, no tags) for an
import-only change set; a normal synth gives it the silver settings."""

from aws_cdk import Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_s3 as s3
from constructs import Construct

from . import names


class DlStorageStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, import_mode: bool = False, **kw) -> None:
        super().__init__(scope, cid, **kw)
        # Lifecycle per layer: noncurrent versions kept long enough to recover a mistake.
        noncurrent = {names.STAGING: 365, names.BRONZE: 365, names.SILVER: 30}
        for logical, name in (("Staging", names.STAGING), ("Bronze", names.BRONZE), ("Silver", names.SILVER)):
            if import_mode:
                # Exactly today's configuration: SSE-S3, all four BPA flags,
                # BucketOwnerEnforced, versioning off. Import-only change set.
                b = s3.Bucket(self, logical, bucket_name=name, encryption=s3.BucketEncryption.S3_MANAGED,
                              bucket_key_enabled=False,
                              block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                              object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
                              removal_policy=RemovalPolicy.RETAIN)
            else:
                b = s3.Bucket(self, logical, bucket_name=name, encryption=s3.BucketEncryption.S3_MANAGED,
                              bucket_key_enabled=False,
                              block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                              object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
                              versioned=True, enforce_ssl=True, removal_policy=RemovalPolicy.RETAIN,
                              lifecycle_rules=[s3.LifecycleRule(
                                  id="noncurrent-and-multipart",
                                  abort_incomplete_multipart_upload_after=Duration.days(7),
                                  noncurrent_version_expiration=Duration.days(noncurrent[name]))])
                if name == names.STAGING:
                    # Native EventBridge notifications (no custom resource).
                    b.node.default_child.add_property_override(
                        "NotificationConfiguration.EventBridgeConfiguration.EventBridgeEnabled", True)
        if import_mode:
            return
        if self.node.try_get_context("import_gold") == "true":
            gold = s3.Bucket(self, "Gold", bucket_name=names.GOLD, encryption=s3.BucketEncryption.S3_MANAGED,
                             bucket_key_enabled=False, block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                             object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
                             removal_policy=RemovalPolicy.RETAIN)
            Tags.of(gold).remove("project")
        else:
            s3.Bucket(self, "Gold", bucket_name=names.GOLD, encryption=s3.BucketEncryption.S3_MANAGED,
                      bucket_key_enabled=False, block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                      object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED, versioned=True, enforce_ssl=True,
                      removal_policy=RemovalPolicy.RETAIN,
                      lifecycle_rules=[s3.LifecycleRule(id="noncurrent-and-multipart",
                                                        abort_incomplete_multipart_upload_after=Duration.days(7),
                                                        noncurrent_version_expiration=Duration.days(30))])
        s3.Bucket(self, "Serving", bucket_name=names.SERVING, encryption=s3.BucketEncryption.S3_MANAGED,
                  block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                  object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED, versioned=True, enforce_ssl=True,
                  removal_policy=RemovalPolicy.RETAIN,
                  lifecycle_rules=[s3.LifecycleRule(id="noncurrent-and-multipart",
                                                    abort_incomplete_multipart_upload_after=Duration.days(7),
                                                    noncurrent_version_expiration=Duration.days(30))])
        s3.Bucket(self, "AthenaResults", bucket_name=names.ATHENA_RESULTS,
                  encryption=s3.BucketEncryption.S3_MANAGED, block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                  object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED, enforce_ssl=True,
                  removal_policy=RemovalPolicy.RETAIN,
                  lifecycle_rules=[s3.LifecycleRule(id="expire-7d", expiration=Duration.days(7),
                                                    abort_incomplete_multipart_upload_after=Duration.days(1))])
