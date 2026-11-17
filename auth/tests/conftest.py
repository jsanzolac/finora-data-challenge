import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "auth"))
sys.path.insert(0, str(ROOT / "dq_api"))

os.environ.update({"AWS_DEFAULT_REGION": "us-west-2", "AWS_ACCESS_KEY_ID": "testing",
                   "AWS_SECRET_ACCESS_KEY": "testing", "AWS_SESSION_TOKEN": "testing",
                   "USERS_TABLE": "users", "SESSIONS_TABLE": "sessions", "RATE_LIMITS_TABLE": "rate_limits",
                   "SERVING_BUCKET": "serving"})
os.environ.pop("AWS_PROFILE", None)


@pytest.fixture(autouse=True)
def aws():
    with mock_aws():
        ddb = boto3.client("dynamodb")
        ddb.create_table(TableName="users", BillingMode="PAY_PER_REQUEST",
                         KeySchema=[{"AttributeName": "email", "KeyType": "HASH"}],
                         AttributeDefinitions=[{"AttributeName": "email", "AttributeType": "S"}])
        ddb.create_table(TableName="sessions", BillingMode="PAY_PER_REQUEST",
                         KeySchema=[{"AttributeName": "token_hash", "KeyType": "HASH"}],
                         AttributeDefinitions=[{"AttributeName": "token_hash", "AttributeType": "S"},
                                               {"AttributeName": "email", "AttributeType": "S"}],
                         GlobalSecondaryIndexes=[{"IndexName": "by_email",
                                                  "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                                                  "Projection": {"ProjectionType": "KEYS_ONLY"}}])
        ddb.create_table(TableName="rate_limits", BillingMode="PAY_PER_REQUEST",
                         KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
                         AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}])
        boto3.client("s3").create_bucket(Bucket="serving",
                                          CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
        import authlib.db as db
        db._res = None
        import handler as dq_handler  # noqa: F401  (dq_api)
        dq_handler._s3 = None
        dq_handler._cache.clear()
        yield
