"""ElevenLabs, as far as the API Lambda needs it: one signed WebSocket URL per voice
session (the agent has authentication enabled, so only this backend can start one).

The API key is the el_toldo key, SSM SecureString /toldo/prod/elevenlabs/api_key in
us-east-1 (same account, alias/aws/ssm). It is read at run time, kept in memory for
five minutes (so a rotation is picked up), and never logged, returned or copied.
Standard library + boto3 only.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import boto3

API = "https://api.elevenlabs.io"
KEY_CACHE_S = 300

_key: tuple[str, float] | None = None
_ssm = None


class VoiceUnavailable(Exception):
    def __init__(self, kind: str, status: int = 0):
        super().__init__(kind)
        self.kind, self.status = kind, status


def _ssm_client():
    global _ssm
    if _ssm is None:
        _ssm = boto3.client("ssm", region_name=os.environ.get("ELEVENLABS_KEY_REGION", "us-east-1"))
    return _ssm


def api_key() -> str:
    global _key
    if _key and time.monotonic() - _key[1] < KEY_CACHE_S:
        return _key[0]
    name = os.environ.get("ELEVENLABS_KEY_PARAM", "/toldo/prod/elevenlabs/api_key")
    try:
        value = _ssm_client().get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
    except Exception as err:  # noqa: BLE001
        raise VoiceUnavailable(f"ssm_{type(err).__name__}") from None
    if not value:
        raise VoiceUnavailable("ssm_empty")
    _key = (value, time.monotonic())
    return value


def signed_url(agent_id: str, timeout: float = 6.0) -> str:
    if not agent_id:
        raise VoiceUnavailable("agent_not_configured")
    url = API + "/v1/convai/conversation/get-signed-url?" + urllib.parse.urlencode({"agent_id": agent_id})
    req = urllib.request.Request(url, headers={"xi-api-key": api_key()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            got = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        raise VoiceUnavailable("elevenlabs_http", err.code) from None
    except (urllib.error.URLError, TimeoutError, ValueError) as err:
        raise VoiceUnavailable(f"elevenlabs_{type(err).__name__}") from None
    signed = got.get("signed_url") or ""
    if not signed.startswith("wss://"):
        raise VoiceUnavailable("elevenlabs_bad_response")
    return signed


# ---- Credit floor (the ElevenLabs credits are shared with el_toldo's production agents):
# no Finora voice session starts when the account's remaining credits are under the floor.
CREDITS_CACHE_S = 60
_credits: tuple[int, float] | None = None


def remaining_credits(timeout: float = 4.0) -> int:
    """character_limit - character_count of the subscription, cached a minute."""
    global _credits
    if _credits and time.monotonic() - _credits[1] < CREDITS_CACHE_S:
        return _credits[0]
    req = urllib.request.Request(API + "/v1/user/subscription", headers={"xi-api-key": api_key()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            got = json.loads(resp.read() or b"{}")
        left = int(got["character_limit"]) - int(got["character_count"])
    except urllib.error.HTTPError as err:
        raise VoiceUnavailable("subscription_http", err.code) from None
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError) as err:
        raise VoiceUnavailable(f"subscription_{type(err).__name__}") from None
    _credits = (left, time.monotonic())
    return left


def credit_floor() -> int:
    try:
        return int(os.environ.get("VOICE_CREDIT_FLOOR", "6000"))
    except ValueError:
        return 6000


def check_budget() -> int:
    """Fails closed: no reading, no session (el_toldo must never be starved)."""
    left = remaining_credits()
    if left < credit_floor():
        raise VoiceUnavailable("budget")
    return left
