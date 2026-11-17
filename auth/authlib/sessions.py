"""Session tokens, ported from el_toldo app/lib/sessions.py. A random token goes
to the client in an HttpOnly cookie; only its SHA-256 hash is stored."""

from __future__ import annotations

import base64
import hashlib
import os
import time
from typing import Any

SESSION_TTL_S = 12 * 3600  # a financial DQ tool: 12 hours, not el_toldo's 30 days
COOKIE = "dq_session"


def new_token() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def expires_at(now: int | None = None) -> int:
    return (now if now is not None else int(time.time())) + SESSION_TTL_S


def is_live(row: dict[str, Any] | None) -> bool:
    """DynamoDB's TTL sweep can lag by up to 48 hours: always re-check expiry."""
    if not row:
        return False
    return int(row.get("expires_at") or 0) > int(time.time())


def set_cookie(token: str) -> str:
    return f"{COOKIE}={token}; Path=/; Max-Age={SESSION_TTL_S}; HttpOnly; Secure; SameSite=Strict"


def clear_cookie() -> str:
    return f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict"
