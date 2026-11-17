"""Ported from el_toldo backend/tests/test_auth.py (login, logout, session,
password change), adapted to the HttpOnly dq_session cookie."""

import time

import pytest

from authlib import db, passwords, sessions
from helpers import body_of, ev, load_auth, token_of

auth = load_auth()
EMAIL, PW = "ana@finora.example", "Temporary-Pass-2026"


def make_user(role="data", must_change=False, email=EMAIL, pw=PW):
    db.put_user(email, passwords.hash_password(pw), role, must_change)


def login(email=EMAIL, password=PW, ip="203.0.113.9"):
    return auth.handler(ev("POST /api/auth/login", {"email": email, "password": password}, ip=ip), None)


# --- passwords (el_toldo) ----------------------------------------------------
def test_password_round_trip():
    stored = passwords.hash_password("Amaranto2026")
    assert stored.startswith("scrypt:32768:8:1:")
    assert passwords.verify_password("Amaranto2026", stored)
    assert not passwords.verify_password("amaranto2026", stored)


def test_hashes_are_salted_so_equal_passwords_differ():
    assert passwords.hash_password("x" * 12) != passwords.hash_password("x" * 12)


def test_a_malformed_hash_never_verifies():
    for bad in ("", "scrypt", "bcrypt:1:2:3:a:b", "scrypt:0:8:1::", "scrypt:a:b:c:d:e"):
        assert not passwords.verify_password("anything", bad)


def test_the_password_is_never_stored_in_the_clear():
    make_user()
    assert PW not in str(db.get_user(EMAIL))


# --- login --------------------------------------------------------------------
def test_login_sets_a_secure_httponly_strict_cookie():
    make_user()
    r = login()
    assert r["statusCode"] == 200
    assert body_of(r) == {"user": {"email": EMAIL, "role": "data", "must_change_password": False}}
    cookie = r["cookies"][0]
    for attr in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/"):
        assert attr in cookie
    assert "token" not in r["body"]  # the token travels only in the cookie


def test_addresses_are_case_and_space_insensitive():
    make_user()
    assert login(email="  ANA@Finora.Example ")["statusCode"] == 200


def test_wrong_password_and_unknown_address_are_indistinguishable():
    make_user()
    a, b = login(password="wrong-password-123"), login(email="nobody@finora.example")
    assert a["statusCode"] == b["statusCode"] == 401
    assert body_of(a) == body_of(b) == {"error": {"code": "invalid_credentials",
                                                  "message": "Email or password is incorrect."}}


def test_login_against_an_unknown_address_still_does_the_work(monkeypatch):
    calls = []
    monkeypatch.setattr(passwords, "burn_verify", lambda pw: calls.append(pw))
    login(email="nobody@finora.example")
    assert calls == [PW]


def test_login_is_rate_limited_per_email():
    make_user()
    codes = [login(password="wrong-password-123", ip=f"203.0.113.{i}")["statusCode"] for i in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
    assert body_of(login(ip="203.0.113.99"))["error"]["code"] == "rate_limited"


# --- sessions -------------------------------------------------------------------
def test_no_cookie_is_unauthenticated():
    r = auth.handler(ev("GET /api/auth/session"), None)
    assert r["statusCode"] == 401 and body_of(r)["error"]["code"] == "unauthenticated"


def test_a_forged_token_is_rejected():
    r = auth.handler(ev("GET /api/auth/session", cookie="forged"), None)
    assert r["statusCode"] == 401


def test_only_the_hash_of_the_token_is_stored():
    make_user()
    token = token_of(login())
    assert db.get_session(token) is None
    assert db.get_session(sessions.hash_token(token))["email"] == EMAIL


def test_an_expired_session_stops_working_before_the_ttl_sweep():
    make_user()
    token = token_of(login())
    db.put_session(sessions.hash_token(token), EMAIL, int(time.time()) - 1)
    assert auth.handler(ev("GET /api/auth/session", cookie=token), None)["statusCode"] == 401


def test_session_returns_the_user():
    make_user(role="finance", must_change=True)
    token = token_of(login())
    r = auth.handler(ev("GET /api/auth/session", cookie=token), None)
    assert body_of(r)["user"] == {"email": EMAIL, "role": "finance", "must_change_password": True}


def test_logout_kills_that_session_only_and_clears_the_cookie():
    make_user()
    t1, t2 = token_of(login()), token_of(login())
    r = auth.handler(ev("POST /api/auth/logout", cookie=t1), None)
    assert r["statusCode"] == 200 and "Max-Age=0" in r["cookies"][0]
    assert auth.handler(ev("GET /api/auth/session", cookie=t1), None)["statusCode"] == 401
    assert auth.handler(ev("GET /api/auth/session", cookie=t2), None)["statusCode"] == 200


# --- password change --------------------------------------------------------------
def change(token, current, new):
    return auth.handler(ev("POST /api/auth/password", {"current": current, "new": new}, cookie=token), None)


def test_changing_the_password_requires_the_current_one():
    make_user(must_change=True)
    token = token_of(login())
    r = change(token, "not-the-password", "A-new-long-password")
    assert r["statusCode"] == 400 and body_of(r)["error"]["code"] == "invalid_current_password"


def test_a_weak_or_unchanged_new_password_is_refused():
    make_user(must_change=True)
    token = token_of(login())
    assert body_of(change(token, PW, "short"))["error"]["code"] == "weak_password"
    assert body_of(change(token, PW, PW))["error"]["code"] == "weak_password"


def test_password_change_clears_the_flag_and_revokes_other_sessions():
    make_user(must_change=True)
    t1, t2 = token_of(login()), token_of(login())
    r = change(t1, PW, "A-new-long-password")
    assert r["statusCode"] == 200 and body_of(r)["user"]["must_change_password"] is False
    assert not db.get_user(EMAIL)["must_change_password"]
    assert auth.handler(ev("GET /api/auth/session", cookie=t1), None)["statusCode"] == 200
    assert auth.handler(ev("GET /api/auth/session", cookie=t2), None)["statusCode"] == 401
    assert login(password="A-new-long-password")["statusCode"] == 200
    assert login()["statusCode"] == 401


def test_unknown_route_is_404():
    assert auth.handler(ev("POST /api/auth/register", {}), None)["statusCode"] == 404
