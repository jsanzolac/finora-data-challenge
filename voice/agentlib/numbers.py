"""Numbers in Spanish text, and the check that every one of them came from data.

Used by the briefing (every number of `text_es` must be one of the fact's `numbers`,
and every `numbers` entry must be the KPI table's value, within rounding) and by the
ask summary (every number must be a value of the result rows, within rounding).

Spanish notation, as the prompts require: "." groups thousands, "," is the decimal
mark ("42.550,70", "52 %", "2,1 millones"). Not counted as figures: a bare year
(2023), a year-month (2024-10), a half-year (2023-H1) and the window phrases of the
definitions ("meses 2 a 4", "mes 6", "mes 12").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

_MULT = {"mil": Decimal(1000), "millón": Decimal(10) ** 6, "millon": Decimal(10) ** 6,
         "millones": Decimal(10) ** 6, "mil millones": Decimal(10) ** 9}
_EXEMPT = [
    re.compile(r"\b[A-Z]{2,3}-\d{2}[a-z]?\b"),                  # a rule id: SB-11, SQ-02
    re.compile(r"\bretenci[oó]n a (?:6|12) meses\b", re.I),      # catalog metric names
    re.compile(r"\ben 1 a 3 meses\b|\búltimos 12 meses\b", re.I),  # fixed wording of the §3 templates
    re.compile(r"\b\d{4}-Q[1-4]\b"),                           # 2022-Q1
    re.compile(r"\b\d{4}-(?:0[1-9]|1[0-2])\b"),                 # 2024-10
    re.compile(r"\b\d{4}-H[12]\b", re.I),                        # 2023-H1
    re.compile(r"\bH[12]\b"),                                    # H1
    re.compile(r"\bmes(?:es)?\s+\d{1,2}(?:\s*(?:a|y|-|–|al)\s*\d{1,2})?\b", re.I),  # meses 2 a 4
    re.compile(r"(?<![\d.,])(?:19|20)\d{2}(?!\d|[.,]\d|\s*%)"),  # a bare year
]
_NUM = re.compile(
    r"(?<![\w.,])(?P<sign>[-−–]\s?)?(?P<num>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)"
    r"(?P<mult>\s+mil\s+millones|\s+millones|\s+millón|\s+millon|\s+mil)?"
    r"(?P<pct>\s?%|\s+por\s+ciento)?", re.I)

UP = re.compile(r"\b(sub[ií]\w*|aument\w*|crec\w*|super\w*|mejor\w*|ganó|gan[oó])\b", re.I)
DOWN = re.compile(r"\b(baj\w*|cay\w*|ca[ií]d\w*|disminu\w*|redu\w*|perd\w*|empeor\w*|menos)\b", re.I)


@dataclass(frozen=True)
class Spoken:
    value: Decimal        # absolute value after the multiplier
    tolerance: Decimal    # half a unit of the last spoken digit (times the multiplier)
    is_pct: bool
    text: str
    start: int


def _blank(text: str) -> str:
    out = text
    for rx in _EXEMPT:
        out = rx.sub(lambda m: " " * len(m.group(0)), out)
    return out


def extract(text: str) -> list[Spoken]:
    """Every figure in a Spanish sentence (sign dropped: direction is in the words)."""
    found: list[Spoken] = []
    for m in _NUM.finditer(_blank(text or "")):
        raw = m.group("num")
        intpart, _, dec = raw.partition(",")
        try:
            val = Decimal(intpart.replace(".", "") + ("." + dec if dec else ""))
        except InvalidOperation:
            continue
        mult = _MULT.get(" ".join((m.group("mult") or "").split()).lower(), Decimal(1))
        tol = Decimal(5) * Decimal(10) ** (-(len(dec) + 1)) * mult
        found.append(Spoken(val * mult, tol, bool(m.group("pct")), m.group(0).strip(), m.start()))
    return found


def to_decimal(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        return None


def decimals_of(v: str) -> int:
    s = str(v).strip()
    return len(s.split(".", 1)[1]) if "." in s else 0


def is_rounding_of(given: Any, exact: Any) -> bool:
    """`given` is `exact` rounded to the digits `given` shows (or more precise)."""
    g, e = to_decimal(given), to_decimal(exact)
    if g is None or e is None:
        return False
    tol = Decimal(5) * Decimal(10) ** (-(decimals_of(str(given)) + 1))
    return abs(g - e) <= tol + Decimal("1e-9")


def display_candidates(value: Decimal, unit: str, is_pct: bool) -> list[Decimal]:
    """The ways a stored value can be spoken. A share (0.9290) is spoken as a
    percentage (92,9 %); a pct or pct_change value (52.1) is already in points."""
    v = abs(value)
    if is_pct:
        if unit == "share":
            return [v * 100]
        if unit in ("pct", "pct_change", "pp"):
            return [v]
        return []
    if unit == "share":
        return [v, v * 100]
    return [v]


def spoken_matches(sp: Spoken, values: Iterable[tuple[Decimal, str]]) -> bool:
    for val, unit in values:
        for cand in display_candidates(val, unit, sp.is_pct):
            if abs(sp.value - cand) <= sp.tolerance + Decimal("1e-9"):
                return True
    return False


def unmatched(text: str, values: Iterable[tuple[Decimal, str]]) -> list[str]:
    """The figures of `text` that match none of `values` ((value, unit) pairs)."""
    vals = [(v, u) for v, u in values if v is not None]
    return [sp.text for sp in extract(text) if not spoken_matches(sp, vals)]


def direction_conflict(text: str, sp_values: list[tuple[Decimal, str]]) -> bool:
    """A fact with one signed change must not use the opposite verb: a negative
    change said with "subió", or a positive one with "bajó"."""
    signed = [v for v, u in sp_values if u == "pct_change" and v != 0]
    if len(signed) != 1:
        return False
    up, down = bool(UP.search(text)), bool(DOWN.search(text))
    return (signed[0] < 0 and up and not down) or (signed[0] > 0 and down and not up)
