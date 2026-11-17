"""Voice agent tokens (contracts/agent_api_contract.md v1, "Secrets and identities").

A dedicated, read-only bearer token per voice session: 45 minutes, issued only to a
logged-in user whose password is not pending a change, stored SHA-256-hashed with a
TTL in its own table (never the sessions table, so it can never work as a dq_session
cookie). It carries the user's role and is accepted only by the two agent webhook
routes, /api/agent/briefing and /api/agent/ask.

Validation re-checks everything at every call: expiry (DynamoDB's TTL sweep lags),
the scope, the user (still there, password not pending, role unchanged since issue)
and the browser session it was issued from (a logout or a password change that
revokes that session also kills the agent token).
"""

from __future__ import annotations

import base64
import os
import re
import time
from typing import Any

from . import db, sessions
from .http import ApiError

AGENT_TOKEN_TTL_S = 45 * 60
SCOPE = "agent:read"
PREFIX = "fat_"  # Finora agent token: tells a leaked value apart from a session cookie at a glance
_FORMAT = re.compile(r"fat_[A-Za-z0-9_-]{43}")
RELOAD_ES = "Por favor recarga la página para continuar."


def new_token() -> str:
    return PREFIX + base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def issue(user: dict[str, Any], session_token: str, now: int | None = None) -> tuple[str, int]:
    """(token, expires_at epoch). The caller has already run require_user (cookie,
    live session, password not pending)."""
    if user.get("must_change_password"):
        raise ApiError(403, "password_change_required")
    now = now if now is not None else int(time.time())
    token = new_token()
    expires = now + AGENT_TOKEN_TTL_S
    db.put_agent_token(sessions.hash_token(token), user["email"], user["role"],
                       sessions.hash_token(session_token), expires)
    return token, expires


def bearer(event: dict[str, Any]) -> str:
    """The token from `Authorization: Bearer <token>`. A bare token in the header is
    accepted too (same secret, no weaker): it covers a webhook client that sends the
    variable's value without the scheme."""
    headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
    raw = str(headers.get("authorization") or "").strip()
    if raw[:7].lower() == "bearer ":
        raw = raw[7:].strip()
    return raw if _FORMAT.fullmatch(raw) else ""


def unauthenticated() -> ApiError:
    return ApiError(401, "unauthenticated", RELOAD_ES)


def require_agent(event: dict[str, Any]) -> dict[str, Any]:
    """The caller of an agent webhook route: {email, role, token_hash}. 401 (with the
    sentence the agent says) for anything not live; 403 for a role outside the three."""
    token = bearer(event)
    if not token:
        raise unauthenticated()
    th = sessions.hash_token(token)
    row = db.get_agent_token(th)
    if not row or int(row.get("expires_at") or 0) <= int(time.time()) or row.get("scope") != SCOPE:
        raise unauthenticated()
    session_hash = str(row.get("session_hash") or "")
    if not session_hash or not sessions.is_live(db.get_session(session_hash)):
        raise unauthenticated()  # the browser session was logged out or revoked
    user = db.get_user(str(row.get("email") or ""))
    if not user or user.get("role") != row.get("role"):
        raise unauthenticated()  # deleted, or the role changed since issue: start a new session
    if user.get("must_change_password"):
        raise ApiError(403, "password_change_required")
    return {"email": user["email"], "role": user["role"], "token_hash": th}
