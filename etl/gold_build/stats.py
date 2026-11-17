"""Pearson r in exact arithmetic and the two-sided Student-t critical |r|
(§7.4), without scipy: the regularized incomplete beta function by Lentz's
continued fraction, inverted by bisection. etl/tests checks it against
scipy.stats.t.ppf and the values printed in the spec."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction

_PREC = 50


def _betacf(a: float, b: float, x: float) -> float:
    tiny, eps = 1e-300, 1e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 1000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betai(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_two_sided_p(t: float, df: int) -> float:
    return betai(df / 2.0, 0.5, df / (df + t * t))


def t_critical(alpha: float, df: int) -> float:
    """t with P(|T| >= t) = alpha for df degrees of freedom."""
    lo, hi = 0.0, 1.0
    while t_two_sided_p(hi, df) > alpha:
        hi *= 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_two_sided_p(mid, df) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def r_critical(n: int, alpha: float = 0.05) -> float | None:
    if n < 3:
        return None
    df = n - 2
    t = t_critical(alpha, df)
    return t / math.sqrt(t * t + df)


def _dec(f: Fraction) -> Decimal:
    return Decimal(f.numerator) / Decimal(f.denominator)


def pearson(xs: list, ys: list) -> Decimal | None:
    """Exact sums (Fractions), one square root at 50 digits. None when a
    series is constant. The caller checks n."""
    n = len(xs)
    fx, fy = [Fraction(x) for x in xs], [Fraction(y) for y in ys]
    mx, my = sum(fx) / n, sum(fy) / n
    sxx = sum((x - mx) ** 2 for x in fx)
    syy = sum((y - my) ** 2 for y in fy)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(fx, fy))
    with localcontext() as ctx:
        ctx.prec = _PREC
        return _dec(sxy) / (_dec(sxx) * _dec(syy)).sqrt()


def q(value, places: str) -> Decimal | None:
    if value is None:
        return None
    with localcontext() as ctx:
        ctx.prec = _PREC
        return Decimal(value).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def qfrac(f: Fraction, places: str) -> Decimal:
    """HALF_UP quantize of an exact rational (away from zero on ties)."""
    with localcontext() as ctx:
        ctx.prec = _PREC
        scale = Decimal(places).as_tuple().exponent * -1
        num = f.numerator * 10 ** scale
        den = f.denominator
        qd, r = divmod(abs(num), den)
        if 2 * r >= den:
            qd += 1
        if num < 0:
            qd = -qd
        return Decimal(qd).scaleb(-scale)
