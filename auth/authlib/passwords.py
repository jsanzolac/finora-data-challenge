"""Password hashing: a direct port of el_toldo app/lib/passwords.py (scrypt,
standard library only). Format: scrypt:N:r:p:{salt_b64}:{hash_b64}."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

N = 32768
R = 8
P = 1
KEYLEN = 64
MAXMEM = 64 * 1024 * 1024  # scrypt at N=32768, r=8 needs ~33.5 MB


def _derive(password: str, salt: bytes, keylen: int, n: int = N, r: int = R, p: int = P) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=keylen, maxmem=MAXMEM)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = _derive(password, salt, KEYLEN)
    return f"scrypt:{N}:{R}:{P}:{base64.b64encode(salt).decode()}:{base64.b64encode(derived).decode()}"


def verify_password(password: str, stored: str) -> bool:
    parts = (stored or "").split(":")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt = base64.b64decode(parts[4])
        expected = base64.b64decode(parts[5])
    except (ValueError, TypeError):
        return False
    if not (n and r and p and salt and expected):
        return False
    actual = _derive(password, salt, len(expected), n, r, p)
    return hmac.compare_digest(actual, expected)  # constant time


_dummy: str | None = None


def burn_verify(password: str) -> None:
    """Comparable work for an unknown email, so timing is not an enumeration oracle."""
    global _dummy
    if _dummy is None:
        _dummy = hash_password("finora-dummy-password-for-timing")
    verify_password(password, _dummy)
