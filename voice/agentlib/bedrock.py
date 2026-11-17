"""Kimi K3 on Amazon Bedrock (us-east-1), through the Converse API with a forced
tool: the model's answer is always the tool's JSON input, never free text.

Model facts checked on 2026-11-17 (one probe call): inference profile
`us.moonshotai.kimi-k3` (routes to us-east-1, us-east-2, us-west-2), no Marketplace
agreement, `toolChoice: {tool: ...}` honoured, a `reasoningContent` block comes
before the `toolUse` block, and `temperature` is refused ("This model doesn't
support the temperature field"), so no sampling parameter is ever sent.

Nothing here logs a prompt or an answer: only sizes, latency and token counts.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import boto3
from botocore.config import Config

DEFAULT_MODEL = "us.moonshotai.kimi-k3"
DEFAULT_REGION = "us-east-1"

_clients: dict[tuple[str, float], Any] = {}


class ModelError(Exception):
    """The model did not return a usable tool call (or Bedrock failed)."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(kind)
        self.kind, self.detail = kind, detail[:300]


def model_id() -> str:
    return os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL)


def client(read_timeout: float = 20.0):
    region = os.environ.get("BEDROCK_REGION", DEFAULT_REGION)
    key = (region, read_timeout)
    if key not in _clients:
        _clients[key] = boto3.client(
            "bedrock-runtime", region_name=region,
            config=Config(connect_timeout=3, read_timeout=read_timeout,
                          retries={"max_attempts": 2, "mode": "standard"}))
    return _clients[key]


def tool_spec(name: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {"toolSpec": {"name": name, "description": description, "inputSchema": {"json": schema}}}


def call_tool(system: str, user_text: str, tool: dict[str, Any], *, max_tokens: int = 2000,
              timeout_s: float = 20.0, log_event: str = "bedrock.call") -> dict[str, Any]:
    """One Converse call that must end in `tool`. Returns the tool input (a dict)."""
    name = tool["toolSpec"]["name"]
    started = time.monotonic()
    try:
        resp = _converse(
            client(timeout_s), timeout_s,
            modelId=model_id(),
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user_text}]}],
            toolConfig={"tools": [tool], "toolChoice": {"tool": {"name": name}}},
            inferenceConfig={"maxTokens": max_tokens})
    except Exception as err:  # noqa: BLE001 -- Bedrock/botocore errors all become ModelError
        _log(log_event, ok=False, kind=type(err).__name__, ms=_ms(started))
        raise ModelError("bedrock_error", type(err).__name__) from None
    usage = resp.get("usage") or {}
    blocks = ((resp.get("output") or {}).get("message") or {}).get("content") or []
    for b in blocks:
        tu = b.get("toolUse") if isinstance(b, dict) else None
        if tu and tu.get("name") == name:
            data = tu.get("input")
            if isinstance(data, str):  # some providers return the JSON as a string
                try:
                    data = json.loads(data)
                except ValueError:
                    data = None
            if isinstance(data, dict):
                _log(log_event, ok=True, ms=_ms(started), stop=resp.get("stopReason"),
                     tokens_in=usage.get("inputTokens"), tokens_out=usage.get("outputTokens"))
                return data
    _log(log_event, ok=False, kind="no_tool_use", ms=_ms(started), stop=resp.get("stopReason"))
    raise ModelError("no_tool_use", str(resp.get("stopReason")))


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _log(event: str, **kw: Any) -> None:
    print(json.dumps({"event": event, "model": model_id(), **kw}))


def _converse(c, timeout_s: float, **kw: Any) -> dict:
    """client.converse, or the same REST call signed with SigV4 when the runtime's
    botocore predates Converse (an old Glue/Lambda bundle)."""
    if hasattr(c, "converse"):
        return c.converse(**kw)
    import urllib.parse
    import urllib.request

    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    region = c.meta.region_name
    url = (f"https://bedrock-runtime.{region}.amazonaws.com/model/"
           f"{urllib.parse.quote(kw.pop('modelId'), safe='')}/converse")
    body = json.dumps(kw).encode()
    req = AWSRequest(method="POST", url=url, data=body, headers={"Content-Type": "application/json"})
    SigV4Auth(boto3.Session().get_credentials().get_frozen_credentials(), "bedrock", region).add_auth(req)
    r = urllib.request.Request(url, data=body, headers=dict(req.headers.items()), method="POST")
    with urllib.request.urlopen(r, timeout=timeout_s) as resp:
        return json.loads(resp.read())
