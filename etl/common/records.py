"""Byte-level record handling shared by bronze and silver (BRZ-06, CTO-01).

A file is split on LF. A CR immediately before the LF belongs to the
terminator. A final terminator starts no record. Nothing is decoded here.
"""

from __future__ import annotations

import hashlib

HEADER_SUFFIX = b",_ingested_at"


def split_records(data: bytes) -> list[tuple[bytes, bytes]]:
    """Return [(record_bytes, terminator_bytes)]."""
    out: list[tuple[bytes, bytes]] = []
    start, n = 0, len(data)
    while start < n:
        i = data.find(b"\n", start)
        if i == -1:
            out.append((data[start:], b""))
            break
        cut = i - 1 if i > start and data[i - 1:i] == b"\r" else i
        out.append((data[start:cut], data[cut:i + 1]))
        start = i + 1
    return out


def make_bronze(staging: bytes, ingested_at: str) -> bytes:
    """Append `,_ingested_at` to record 1 and `,<ts>` to every other record,
    before its terminator. Every other byte is kept. 0 bytes in, 0 bytes out."""
    suffix = b"," + ingested_at.encode("ascii")
    parts: list[bytes] = []
    for idx, (rec, term) in enumerate(split_records(staging)):
        parts.append(rec + (HEADER_SUFFIX if idx == 0 else suffix) + term)
    return b"".join(parts)


def strip_bronze(bronze: bytes) -> tuple[bytes, list[bytes]]:
    """Remove the last field of every bronze record. Returns (staging bytes,
    removed suffix values)."""
    parts: list[bytes] = []
    removed: list[bytes] = []
    for rec, term in split_records(bronze):
        pos = rec.rfind(b",")
        if pos < 0:
            raise ValueError("bronze record without the appended field")
        parts.append(rec[:pos] + term)
        removed.append(rec[pos + 1:])
    return b"".join(parts), removed


def round_trip_ok(staging: bytes, bronze: bytes, ingested_at: str) -> bool:
    """CTO-01 self-test: stripping reproduces the staging bytes exactly, and the
    appended values are the header name then one timestamp."""
    back, removed = strip_bronze(bronze) if bronze else (b"", [])
    if len(back) != len(staging) or hashlib.sha256(back).digest() != hashlib.sha256(staging).digest():
        return False
    if removed and removed[0] != b"_ingested_at":
        return False
    return all(v == ingested_at.encode("ascii") for v in removed[1:])


def data_records(staging: bytes) -> tuple[bytes | None, list[bytes]]:
    """(header bytes or None, data record bytes in order)."""
    recs = [r for r, _ in split_records(staging)]
    if not recs:
        return None, []
    return recs[0], recs[1:]
