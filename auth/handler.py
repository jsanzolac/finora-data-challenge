"""Auth Lambda: login, logout, session and password change (port of el_toldo
app/handlers/auth.py; register, guest, Google, forgot/reset and delete_account
are not ported). Accounts are created only by scripts/create_user.py."""

from __future__ import annotations

import json
import re
import time

from authlib import db, passwords, sessions
from authlib.http import ApiError, dispatch, json_response, parse_body, public_user, require_user

MIN_PASSWORD = 12
LOGIN_PER_EMAIL = 10      # per 15 minutes
LOGIN_PER_IP = 50         # per 15 minutes
WINDOW = 15 * 60
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value) -> str:
    return value.strip().lower()[:160] if isinstance(value, str) else ""


def _client_ip(event) -> str:
    xff = (event.get("headers") or {}).get("x-forwarded-for", "")
    return (xff.split(",")[0].strip() if xff else "") or \
        event.get("requestContext", {}).get("http", {}).get("sourceIp", "unknown")


def _log(event: str, **kw) -> None:
    print(json.dumps({"event": event, **kw}))  # never an email, password or token


def login(event):
    body = parse_body(event)
    email = _normalize_email(body.get("email"))
    password = body.get("password") if isinstance(body.get("password"), str) else ""
    ttl = int(time.time()) + 2 * WINDOW
    w = db.window_key(WINDOW)
    if db.hit_bucket(f"login-ip#{_client_ip(event)}#{w}", LOGIN_PER_IP, ttl) or \
            (email and db.hit_bucket(f"login-email#{email}#{w}", LOGIN_PER_EMAIL, ttl)):
        _log("auth.rate_limited")
        raise ApiError(429, "rate_limited")
    user = db.get_user(email) if EMAIL.match(email or "") else None
    if not user:
        passwords.burn_verify(password)  # same work: "no account" and "wrong password" look alike
        raise ApiError(401, "invalid_credentials")
    if not passwords.verify_password(password, user.get("password_hash") or ""):
        raise ApiError(401, "invalid_credentials")
    token = sessions.new_token()
    db.put_session(sessions.hash_token(token), user["email"], sessions.expires_at())
    _log("auth.signed_in", role=user["role"])
    return json_response(200, {"user": public_user(user)}, cookies=[sessions.set_cookie(token)])


def logout(event):
    from authlib.http import session_token
    token = session_token(event)
    if token:
        db.delete_session(sessions.hash_token(token))
    return json_response(200, {"ok": True}, cookies=[sessions.clear_cookie()])


def session(event):
    user = require_user(event, allow_must_change=True)
    return json_response(200, {"user": public_user(user)})


def change_password(event):
    from authlib.http import session_token
    user = require_user(event, allow_must_change=True)
    body = parse_body(event)
    current = body.get("current") if isinstance(body.get("current"), str) else ""
    new = body.get("new") if isinstance(body.get("new"), str) else ""
    ttl = int(time.time()) + 2 * WINDOW
    if db.hit_bucket(f"password#{user['email']}#{db.window_key(WINDOW)}", LOGIN_PER_EMAIL, ttl):
        raise ApiError(429, "rate_limited")
    if not passwords.verify_password(current, user.get("password_hash") or ""):
        raise ApiError(400, "invalid_current_password")
    if len(new) < MIN_PASSWORD or new == current:
        raise ApiError(400, "weak_password")
    db.set_password(user["email"], passwords.hash_password(new))
    keep = sessions.hash_token(session_token(event))
    revoked = db.delete_other_sessions(user["email"], keep)
    _log("auth.password_changed", revoked_sessions=revoked)
    return json_response(200, {"user": {**public_user(user), "must_change_password": False}})


ROUTES = {
    "POST /api/auth/login": login,
    "POST /api/auth/logout": logout,
    "GET /api/auth/session": session,
    "POST /api/auth/password": change_password,
}


def handler(event, context):
    return dispatch(ROUTES, event)
