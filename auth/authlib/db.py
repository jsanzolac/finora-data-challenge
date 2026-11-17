"""DynamoDB access for users, sessions and rate limits (port of the el_toldo
functions). Table names come from the environment."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

_res = None


def _t(name: str):
    global _res
    if _res is None:
        _res = boto3.resource("dynamodb")
    return _res.Table(os.environ[{"users": "USERS_TABLE", "sessions": "SESSIONS_TABLE",
                                  "rate_limits": "RATE_LIMITS_TABLE",
                                  "agent_tokens": "AGENT_TOKENS_TABLE"}[name]])


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_user(email: str) -> dict[str, Any] | None:
    return _t("users").get_item(Key={"email": email}).get("Item") if email else None


def put_user(email: str, password_hash: str, role: str, must_change_password: bool = True) -> None:
    _t("users").put_item(Item={"email": email, "password_hash": password_hash, "role": role,
                               "must_change_password": must_change_password,
                               "created_at": now_iso(), "updated_at": now_iso()})


def set_password(email: str, password_hash: str) -> None:
    _t("users").update_item(
        Key={"email": email},
        UpdateExpression="SET password_hash = :h, must_change_password = :f, updated_at = :u",
        ExpressionAttributeValues={":h": password_hash, ":f": False, ":u": now_iso()})


def put_session(token_hash: str, email: str, expires_at: int) -> None:
    _t("sessions").put_item(Item={"token_hash": token_hash, "email": email, "expires_at": expires_at,
                                  "created_at": now_iso()})


def get_session(token_hash: str) -> dict[str, Any] | None:
    return _t("sessions").get_item(Key={"token_hash": token_hash}).get("Item")


def delete_session(token_hash: str) -> None:
    _t("sessions").delete_item(Key={"token_hash": token_hash})


def delete_other_sessions(email: str, keep_hash: str) -> int:
    """After a password change every other session of the user is revoked."""
    got = _t("sessions").query(IndexName="by_email", KeyConditionExpression=Key("email").eq(email))
    n = 0
    for item in got.get("Items", []):
        if item["token_hash"] != keep_hash:
            delete_session(item["token_hash"])
            n += 1
    return n


def hit_bucket(pk: str, limit: int, ttl_epoch: int) -> bool:
    """True once `pk` has been hit more than `limit` times (el_toldo hit_bucket)."""
    got = _t("rate_limits").update_item(
        Key={"pk": pk}, UpdateExpression="ADD hits :one SET #ttl = :ttl",
        ExpressionAttributeNames={"#ttl": "ttl"},
        ExpressionAttributeValues={":one": 1, ":ttl": ttl_epoch}, ReturnValues="UPDATED_NEW")["Attributes"]
    return int(got.get("hits") or 0) > limit


def window_key(seconds: int) -> str:
    return str(int(time.time()) // seconds)


# ---- Voice agent tokens (contracts/agent_api_contract.md v1): a table of their own,
# so an agent token can never be accepted as a dq_session cookie and vice versa.

def put_agent_token(token_hash: str, email: str, role: str, session_hash: str, expires_at: int) -> None:
    _t("agent_tokens").put_item(Item={"token_hash": token_hash, "email": email, "role": role,
                                      "scope": "agent:read", "session_hash": session_hash,
                                      "expires_at": expires_at, "created_at": now_iso()})


def get_agent_token(token_hash: str) -> dict[str, Any] | None:
    return _t("agent_tokens").get_item(Key={"token_hash": token_hash}).get("Item")
