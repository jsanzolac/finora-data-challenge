"""HTTP plumbing for API Gateway HTTP API (payload 2.0), served same-origin
through CloudFront /api/*. No CORS headers: nothing cross-origin is allowed."""

from __future__ import annotations

import json
from typing import Any, Callable

from . import db, sessions

Event = dict[str, Any]
Result = dict[str, Any]

MESSAGES = {
    "unauthenticated": "Log in to continue.",
    "invalid_credentials": "Email or password is incorrect.",
    "password_change_required": "Change your password to continue.",
    "forbidden": "Your role cannot access this resource.",
    "not_found": "Not found.",
    "rate_limited": "Too many attempts. Try again later.",
    "weak_password": "The new password must have at least 12 characters and differ from the current one.",
    "invalid_current_password": "The current password is incorrect.",
    "bad_request": "The request is not valid.",
    "internal": "Something went wrong.",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str | None = None):
        super().__init__(code)
        self.status, self.code, self.message = status, code, message or MESSAGES.get(code, code)


def json_response(status: int, body: Any, cookies: list[str] | None = None) -> Result:
    out: Result = {"statusCode": status,
                   "headers": {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"},
                   "body": json.dumps(body, ensure_ascii=False, default=str)}
    if cookies:
        out["cookies"] = cookies
    return out


def error_response(err: ApiError) -> Result:
    return json_response(err.status, {"error": {"code": err.code, "message": err.message}})


def session_token(event: Event) -> str:
    raw = list(event.get("cookies") or [])
    header = (event.get("headers") or {}).get("cookie")
    if header:
        raw += header.split(";")
    for c in raw:
        name, _, value = c.strip().partition("=")
        if name == sessions.COOKIE and value:
            return value
    return ""


def require_user(event: Event, allow_must_change: bool = False) -> dict[str, Any]:
    """The one sanctioned way to get the caller: cookie -> hashed token ->
    sessions table (expiry re-checked) -> users table."""
    token = session_token(event)
    if not token:
        raise ApiError(401, "unauthenticated")
    row = db.get_session(sessions.hash_token(token))
    if not sessions.is_live(row):
        raise ApiError(401, "unauthenticated")
    user = db.get_user(row["email"])
    if not user:
        raise ApiError(401, "unauthenticated")
    if user.get("must_change_password") and not allow_must_change:
        raise ApiError(403, "password_change_required")
    return user


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {"email": user["email"], "role": user["role"],
            "must_change_password": bool(user.get("must_change_password"))}


def parse_body(event: Event) -> dict[str, Any]:
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        import base64
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def route_key(event: Event) -> str:
    key = event.get("routeKey")
    if isinstance(key, str) and key and key != "$default":
        return key
    ctx = event.get("requestContext", {}).get("http", {})
    return f"{ctx.get('method', 'GET')} {ctx.get('path', '/')}"


def dispatch(routes: dict[str, Callable[[Event], Result]], event: Event) -> Result:
    try:
        handler = routes.get(route_key(event))
        if handler is None:
            raise ApiError(404, "not_found")
        return handler(event)
    except ApiError as err:
        return error_response(err)
    except Exception as err:  # noqa: BLE001 -- the boundary
        print(json.dumps({"event": "unhandled_error", "kind": type(err).__name__}))
        return error_response(ApiError(500, "internal"))
