"""Small S3 helpers. Keys from staging are data: they are passed to the SDK as
parameters only, never interpolated into a path, query or command."""

from __future__ import annotations

import gzip
import json
import time
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

_s3 = None
_s3_once = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _native_if_none_match() -> bool:
    return "IfNoneMatch" in s3().meta.service_model.operation_model("PutObject").input_shape.members


def _s3_write_once():
    """A client whose PutObject always sends `If-None-Match: *`. Older botocore
    builds (some Glue runtimes) predate the IfNoneMatch parameter; S3 honours
    the header either way and answers 412 PreconditionFailed when the key exists."""
    global _s3_once
    if _s3_once is None:
        _s3_once = boto3.client("s3")

        def _add(request, **_):
            request.headers["If-None-Match"] = "*"

        _s3_once.meta.events.register("before-sign.s3.PutObject", _add)
    return _s3_once


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id() -> str:
    return "r" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def get_bytes(bucket: str, key: str, version_id: str | None = None) -> bytes | None:
    kw: dict[str, Any] = {"Bucket": bucket, "Key": key}
    if version_id:
        kw["VersionId"] = version_id
    try:
        return s3().get_object(**kw)["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404", "NoSuchVersion"):
            return None
        raise


def get_json(bucket: str, key: str) -> Any:
    raw = get_bytes(bucket, key)
    if raw is None:
        return None
    if key.endswith(".gz"):
        raw = gzip.decompress(raw)
    return json.loads(raw)


def put_bytes(bucket: str, key: str, body: bytes, content_type: str, once: bool = False) -> bool:
    """Write an object. With once=True the write is If-None-Match: * and returns
    False when the object already exists."""
    kw: dict[str, Any] = {"Bucket": bucket, "Key": key, "Body": body, "ContentType": content_type}
    client = s3()
    if once:
        if _native_if_none_match():
            kw["IfNoneMatch"] = "*"
        else:
            client = _s3_write_once()
    try:
        client.put_object(**kw)
        return True
    except ClientError as e:
        if once and e.response["Error"]["Code"] in ("PreconditionFailed", "412", "ConditionalRequestConflict"):
            return False
        raise


def put_json(bucket: str, key: str, obj: Any, once: bool = False, cache: str | None = None) -> bool:
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    if key.endswith(".gz"):
        return put_bytes(bucket, key, gzip.compress(body), "application/gzip", once)
    return put_bytes(bucket, key, body, "application/json", once)


def log(event: str, **fields: Any) -> None:
    """Structured log line. Callers pass ids, counts and codes only, never cell values."""
    print(json.dumps({"event": event, "ts": time.time(), **fields}, default=str))
