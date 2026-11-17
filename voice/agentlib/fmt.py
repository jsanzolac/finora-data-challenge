"""Display formats of docs/semantic_layer.md §1.1 (catalog sl-2026-11-17).

HALF_UP from the exact decimal string; "." groups thousands and "," is the decimal
mark. `display(value, fmt)` is what is spoken and written in text_es / summary_es;
`chart_label(value, fmt)` uses "M" instead of "millones". `core(display)` is what the
number check compares: the digits as written plus the suffix kind (%, millones).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

MILLION = Decimal(1_000_000)
MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
             "octubre", "noviembre", "diciembre"]


def dec(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        return None


def q(v: Decimal, places: int) -> Decimal:
    return v.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def group(v: Decimal, places: int) -> str:
    """|v| with "." thousands and "," decimals (the sign is never written: verbs carry it)."""
    s = f"{abs(q(v, places)):.{places}f}"
    whole, _, frac = s.partition(".")
    out = ""
    while len(whole) > 3:
        out = "." + whole[-3:] + out
        whole = whole[:-3]
    out = whole + out
    return out + ("," + frac if frac else "")


def display(value: Any, fmt: str, *, chart: bool = False, signed: bool = False) -> str:
    v = dec(value)
    if v is None:
        return "sin dato"
    sign = "−" if signed and v < 0 else ""
    if fmt == "int":
        return sign + group(v, 0)
    if fmt == "dec1":
        return sign + group(v, 1)
    if fmt == "money":
        a = abs(v)
        if a < MILLION:
            return sign + group(v, 0)
        places = 2 if a < 10 * MILLION else 1
        return sign + group(v / MILLION, places) + (" M" if chart else " millones")
    if fmt == "pct0":
        return sign + group(v, 0) + " %"
    if fmt == "pct1":
        return sign + group(v, 1) + " %"
    if fmt == "pct_dq":
        s = group(v, 2)
        if "," in s:
            s = s.rstrip("0").rstrip(",")
        return sign + s + " %"
    if fmt == "share_pct1":
        return sign + group(v * 100, 1) + " %"
    if fmt == "months1":
        return sign + group(v, 1) + " meses"
    if fmt == "r4":
        return ("−" if v < 0 else "") + group(v, 4)
    return sign + group(v, 2)


def core(text: str) -> tuple[str, str]:
    """('3,05', 'millones') from '3,05 millones'; ('52', '%') from '52 %' or '52%'."""
    t = " ".join(str(text).replace("−", "").replace("-", "").split()).lower()
    if t.endswith("%"):
        return t[:-1].strip(), "%"
    if t.endswith(" por ciento"):
        return t[: -len(" por ciento")].strip(), "%"
    for suffix in ("mil millones", "millones", "millón", "millon", " m"):
        if t.endswith(suffix):
            return t[: -len(suffix)].strip(), "millones"
    if t.endswith(" meses"):
        return t[: -len(" meses")].strip(), ""
    return t, ""


def month_es(month: str, with_year: bool = True) -> str:
    """'2024-10' -> 'octubre de 2024'."""
    try:
        y, m = month.split("-")
        name = MONTHS_ES[int(m) - 1]
    except (ValueError, IndexError):
        return month
    return f"{name} de {y}" if with_year else name


def period_es(code: str) -> str:
    return {"pre_2023_06": "antes de junio de 2023", "from_2023_06": "desde junio de 2023",
            "full": "en toda la ventana"}.get(code, code)


def cohort_es(code: str) -> str:
    try:
        y, h = code.split("-")
        return f"el {'primer' if h == 'H1' else 'segundo'} semestre de {y}"
    except ValueError:
        return code


def quarter_es(code: str) -> str:
    try:
        y, qq = code.split("-Q")
        return f"el trimestre {qq} de {y}"
    except ValueError:
        return code
