"""Exact decimal helpers. Money is never a float."""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Context, Decimal, localcontext

Q6 = Decimal("0.000001")
Q3 = Decimal("0.001")
Q2 = Decimal("0.01")
Q0 = Decimal("1")
Q12 = Decimal("0.000000000001")
WIDE = Context(prec=60)


def quotient(a: Decimal, b: Decimal) -> Decimal:
    """A stored quotient: unrounded operands, DECIMAL(38,12) HALF_UP (A9 iv)."""
    with localcontext(WIDE):
        return (a / b).quantize(Q12, rounding=ROUND_HALF_UP)


def trunc6(a: Decimal) -> Decimal:
    with localcontext(WIDE):
        return a.quantize(Q6, rounding=ROUND_DOWN)


def pct(evaluated: int, failed: int) -> tuple[float | None, Decimal | None]:
    """compliance_pct per approved_data_rules.md: HALF_UP to 2 decimals, never
    100.00 with a failure, never 0.00 with a pass. Returns (published, unrounded)."""
    if evaluated == 0:
        return None, None
    with localcontext(WIDE):
        raw = Decimal(evaluated - failed) * 100 / Decimal(evaluated)
        val = raw.quantize(Q2, rounding=ROUND_HALF_UP)
    if failed > 0 and val == Decimal("100.00"):
        val = Decimal("99.99")
    if failed < evaluated and val == Decimal("0.00"):
        val = Decimal("0.01")
    return float(val), raw


def median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2:
        return s[n // 2]
    with localcontext(WIDE):
        return (s[n // 2 - 1] + s[n // 2]) / 2


def month_add(ym: str, delta: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + delta
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def month_range(lo: str, hi: str) -> list[str]:
    out, cur = [], lo
    while cur <= hi:
        out.append(cur)
        cur = month_add(cur, 1)
    return out
