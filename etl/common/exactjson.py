"""JSON that round-trips Decimal exactly (value and exponent), for moving
engine results between the Spark driver and executors. Money is never a float."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

_TAG = "$dec"


def _enc(o: Any) -> Any:
    if isinstance(o, Decimal):
        return {_TAG: str(o)}
    if isinstance(o, dict):
        return {k: _enc(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_enc(v) for v in o]
    return o


def _hook(d: dict) -> Any:
    return Decimal(d[_TAG]) if len(d) == 1 and _TAG in d else d


def dumps(o: Any) -> str:
    return json.dumps(_enc(o), ensure_ascii=False, separators=(",", ":"))


def loads(s: str) -> Any:
    return json.loads(s, object_hook=_hook)
