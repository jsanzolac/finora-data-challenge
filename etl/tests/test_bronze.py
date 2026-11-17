"""Bronze: byte-faithful plus `_ingested_at` (BRZ-06) and the CTO-01 round trip."""

import hashlib

import pytest

from common.records import make_bronze, round_trip_ok, split_records, strip_bronze
from golden_helpers import FILES, ROOT
from test_golden import SHA

TS = "2026-11-16T04:10:00Z"


@pytest.mark.parametrize("ds", list(FILES))
def test_round_trip_on_todays_files(ds):
    raw = (ROOT / "data" / FILES[ds][1]).read_bytes()
    bronze = make_bronze(raw, TS)
    back, removed = strip_bronze(bronze)
    assert hashlib.sha256(back).hexdigest() == SHA[ds] and len(back) == len(raw)
    assert round_trip_ok(raw, bronze, TS)
    assert removed[0] == b"_ingested_at" and set(removed[1:]) == {TS.encode()}
    assert bronze.startswith(b"\xef\xbb\xbf") and not bronze.endswith(b"\n")
    assert bronze.count(b"\r\n") == raw.count(b"\r\n")
    assert len(bronze) == len(raw) + len(b",_ingested_at") + (len(removed) - 1) * (len(TS) + 1)


def test_industry_empty_record_gets_the_suffix_too():
    raw = (ROOT / "data" / "Industry.csv").read_bytes()
    assert make_bronze(raw, TS).endswith(b"\r\n,," + TS.encode())


@pytest.mark.parametrize("raw", [b"", b"h", b"h\n", b"h\r\n\r\n", b"h\na\n\nb", b"h\r\nx\r", b"\n\n",
                                 b"h\r\na,b\r\n", b"h\xff\r\n\xfe,\x00"])
def test_round_trip_on_edge_bytes(raw):
    bronze = make_bronze(raw, TS)
    assert round_trip_ok(raw, bronze, TS)
    assert (bronze == b"") == (raw == b"")


def test_cr_before_lf_is_the_terminator():
    assert split_records(b"a\r\nb\nc\r") == [(b"a", b"\r\n"), (b"b", b"\n"), (b"c\r", b"")]


def test_a_tampered_bronze_object_fails_the_self_test():
    raw = b"h\r\na,1\r\nb,2"
    bronze = make_bronze(raw, TS).replace(b"b,2", b"b,3")
    assert not round_trip_ok(raw, bronze, TS)
