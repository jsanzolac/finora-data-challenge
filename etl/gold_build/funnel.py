"""Reference implementation of the rate-table logic and the funnel arithmetic
(docs/gold_acquisition_model.md §6.3, §7.1, §7.2), in exact rationals.

The Athena views (gold_build/ddl.py) are the product; this module is their
oracle in the tests, and the gold job uses it for the run findings (invalid
scenarios, BASE_DIFFERS_FROM_SEED, RATE_HISTORY_REWRITTEN) and the rate hash.

GR-05 and GR-06 are evaluated on each transition's current row (the latest),
so a user can always fix an invalid scenario by inserting corrected rows
(§6.3); GR-05 then means "the latest row of a transition is unique".
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction

from gold_build.stats import qfrac

CHECKS = ("GR-01", "GR-02", "GR-03", "GR-04", "GR-05", "GR-06")
REASONS = ("won_zero", "spend_missing", "beyond_data_complete_through", "unit_tripwire", "won_incomplete")
BASIS = "assumption: stage volumes and rates are not observed"


def _ts_key(ts):
    return (ts is not None, ts or datetime.min)


def current_rows(rows: list[dict]) -> dict[tuple, dict]:
    """Latest row per (scenario_id, from_stage_code): changed_at DESC NULLS LAST,
    then a deterministic tie-break (the view uses the same order)."""
    out: dict[tuple, dict] = {}
    for r in rows:
        k = (r["scenario_id"], r["from_stage_code"])
        cur = out.get(k)
        if cur is None or _order(r) > _order(cur):
            out[k] = r
    return out


def _order(r):
    return (_ts_key(r["changed_at"]), r["to_stage_code"] or "", r["rate"] if r["rate"] is not None else Decimal(-1),
            r["changed_by"] or "", r["change_reason"] or "", r["scenario_label"] or "")


def scenario_status(rows: list[dict], cfg: dict, now: datetime) -> dict[str, dict]:
    pattern = re.compile(cfg["base_seed"]["scenario_id_pattern"])
    pairs = set(cfg["transitions"])
    froms = {f for f, _ in cfg["transitions"]}
    cur = current_rows(rows)
    counts: dict[tuple, int] = {}
    for r in rows:
        k = (r["scenario_id"], r["from_stage_code"], r["changed_at"])
        counts[k] = counts.get(k, 0) + 1
    by_s: dict[str, list[dict]] = {}
    for (sid, _), r in cur.items():
        by_s.setdefault(sid, []).append(r)
    limit = now + timedelta(minutes=cfg["params"]["future_tolerance_minutes"])
    out = {}
    for sid, cr in by_s.items():
        failed = []
        if sid is None or not pattern.fullmatch(sid):
            failed.append("GR-01")
        if any((r["from_stage_code"], r["to_stage_code"]) not in pairs for r in cr):
            failed.append("GR-02")
        if any(r["rate"] is None or not (Decimal(0) < r["rate"] <= Decimal(1)) for r in cr):
            failed.append("GR-03")
        if len(cr) != 6 or {r["from_stage_code"] for r in cr} != froms:
            failed.append("GR-04")
        if any(counts[(sid, r["from_stage_code"], r["changed_at"])] > 1 for r in cr):
            failed.append("GR-05")
        if any(not (r["changed_by"] or "").strip() or not (r["change_reason"] or "").strip()
               or r["changed_at"] is None or r["changed_at"] > limit for r in cr):
            failed.append("GR-06")
        latest = max(cr, key=_order)
        out[sid] = {"status": "invalid" if failed else "valid", "failed_checks": failed,
                    "scenario_label": latest["scenario_label"], "latest": latest,
                    "rates": {r["from_stage_code"]: r["rate"] for r in cr}}
    return out


def valid_rates(rows: list[dict], cfg: dict, now: datetime) -> dict[str, dict[str, Decimal]]:
    return {sid: s["rates"] for sid, s in scenario_status(rows, cfg, now).items() if s["status"] == "valid"}


def base_matches_seed(rows: list[dict], cfg: dict) -> bool:
    cur = current_rows(rows)
    seed = {r["from_stage_code"]: (r["to_stage_code"], Decimal(r["rate"])) for r in cfg["base_seed"]["rates"]}
    got = {f: (r["to_stage_code"], r["rate"]) for (sid, f), r in cur.items() if sid == "base"}
    return got == seed


def rows_sha256(rows: list[dict]) -> str:
    lines = sorted(json.dumps([r["scenario_id"], r["scenario_label"], r["from_stage_code"], r["to_stage_code"],
                               None if r["rate"] is None else str(r["rate"]),
                               None if r["changed_at"] is None else r["changed_at"].isoformat(),
                               r["changed_by"], r["change_reason"]], ensure_ascii=False) for r in rows)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def history_missing(old: list[dict], new: list[dict]) -> int:
    """Rows of the earlier snapshot that are no longer in the table (multiset)."""
    key = lambda r: (r["scenario_id"], r["scenario_label"], r["from_stage_code"], r["to_stage_code"],  # noqa: E731
                     r["rate"], r["changed_at"], r["changed_by"], r["change_reason"])
    have: dict = {}
    for r in new:
        have[key(r)] = have.get(key(r), 0) + 1
    missing = 0
    for r in old:
        k = key(r)
        if have.get(k, 0) > 0:
            have[k] -= 1
        else:
            missing += 1
    return missing


# --------------------------------------------------------------------------- #
# Funnel arithmetic (exact)                                                   #
# --------------------------------------------------------------------------- #

def downstream(rates: dict[str, Decimal], cfg: dict) -> dict[str, Fraction]:
    """Π of the rates from each stage down to WON (1 for WON)."""
    out, acc = {}, Fraction(1)
    out[cfg["stage_codes"][-1]] = acc
    for f, _ in reversed(cfg["transitions"]):
        acc *= Fraction(rates[f])
        out[f] = acc
    return out


def cost_null_reason(won: int | None, m: dict, dct: str | None) -> str | None:
    if not won:
        return "won_zero"
    if m["spend_total_value"] is None:
        return "spend_missing"
    if dct is None or m["month"] > dct:
        return "beyond_data_complete_through"
    if m["is_unit_tripwire"]:
        return "unit_tripwire"
    if m["won_is_complete"] is False:
        return "won_incomplete"
    return None


def stage_rows(won: int, spend, rates: dict[str, Decimal], cfg: dict, reason: str | None) -> list[dict]:
    d = downstream(rates, cfg)
    out = []
    for s in cfg["stages"]:
        code, p = s["stage_code"], d[s["stage_code"]]
        count = Fraction(won) / p
        cost = None
        if reason is None:
            cost = qfrac(Fraction(spend) * p / won, "0.01")
        out.append({"stage_code": code, "stage_key": s["stage_key"], "stage_count": qfrac(count, "0.000001"),
                    "stage_count_exact": count, "downstream_rate_product": qfrac(p, "0.000000000001"),
                    "cost_per_unit_value": cost, "cost_null_reason": reason,
                    "real_or_estimated": "Real" if s["is_observed"] else "Estimated"})
    return out


def won_of(m: dict, definition: str) -> int | None:
    return m["won_count"] if definition == "first_payment" else m["won_new_logo_count"]


def funnel_month(months: list[dict], rates: dict[str, Decimal], definition: str, dct: str | None, cfg: dict):
    """months: agg_acquisition_month rows joined with dim_month.month, reportable only."""
    out = {}
    for m in months:
        won = won_of(m, definition)
        reason = cost_null_reason(won, m, dct)
        out[m["month"]] = stage_rows(won, m["spend_total_value"], rates, cfg, reason)
    return out


def periods(months: list[dict], dct: str | None) -> dict[tuple[str, str], list[dict]]:
    """(period_type, period_id) -> the reportable months up to data_complete_through."""
    out: dict[tuple[str, str], list[dict]] = {}
    for m in months:
        if dct is None or m["month"] > dct:
            continue
        for key in (("full", "full"), ("year", m["month"][:4]), ("quarter", m["year_quarter"]),
                    ("sm_regime", m["sm_regime"])):
            out.setdefault(key, []).append(m)
    return out


def period_reason(ms: list[dict], definition: str, dct: str | None) -> str | None:
    won = sum(won_of(m, definition) or 0 for m in ms)
    if not won:
        return "won_zero"
    reasons = [cost_null_reason(won_of(m, definition), m, dct) for m in ms]
    present = [r for r in REASONS if r in reasons]
    return present[0] if present else None


def funnel_period(months: list[dict], rates: dict[str, Decimal], definition: str, dct: str | None, cfg: dict):
    out = {}
    for key, ms in periods(months, dct).items():
        won = sum(won_of(m, definition) or 0 for m in ms)
        spends = [m["spend_total_value"] for m in ms]
        spend = sum(spends) if all(s is not None for s in spends) else None
        reason = period_reason(ms, definition, dct)
        rows = stage_rows(won, spend, rates, cfg, reason)
        n = len(ms)
        extra = {"months_in_period": n, "first_month": ms[0]["month"], "last_month": ms[-1]["month"],
                 "won_count": won, "spend_total_value": spend,
                 "won_per_month": qfrac(Fraction(won, n), "0.000001"),
                 "spend_per_month_value": qfrac(Fraction(spend) / n, "0.01") if spend is not None else None}
        out[key] = (extra, rows)
    return out


def overall(rates: dict[str, Decimal]) -> Fraction:
    p = Fraction(1)
    for v in rates.values():
        p *= Fraction(v)
    return p


def compare(won: int, spend, rates: dict[str, Decimal], base: dict[str, Decimal]) -> dict:
    o, ob = overall(rates), overall(base)
    implied = Fraction(won) * o / ob
    new_base = Fraction(won) / ob
    new_req = Fraction(won) / o
    q6 = lambda f: qfrac(f, "0.000001")  # noqa: E731
    with localcontext() as ctx:
        ctx.prec = 80
        new_required_delta = q6(new_req) - q6(new_base)
    return {"overall_rate": qfrac(o, "0.000000000001"), "overall_rate_base": qfrac(ob, "0.000000000001"),
            "new_estimated_base": q6(new_base), "won_implied_same_new": q6(implied),
            "won_implied_delta": q6(implied - won),
            "won_implied_delta_pct": q6((o - ob) * 100 / ob),
            "new_required_same_won": q6(new_req), "new_required_delta": new_required_delta,
            "new_required_delta_pct": q6((ob - o) * 100 / o),
            "cost_per_won_implied_value": (qfrac(Fraction(spend) * ob / (Fraction(won) * o), "0.01")
                                           if won and spend is not None else None)}


def sensitivity(won_full: int, rate: Decimal, point: Decimal = Decimal("0.01")) -> dict:
    r = Fraction(rate)
    if r + Fraction(point) > 1:
        return {"won_pct_change_per_point": None, "won_change_per_point_full_period": None,
                "new_required_pct_change_per_point": None}
    return {"won_pct_change_per_point": qfrac(Fraction(point) * 100 / r, "0.000001"),
            "won_change_per_point_full_period": qfrac(Fraction(won_full) * Fraction(point) / r, "0.000001"),
            "new_required_pct_change_per_point": qfrac(-Fraction(point) * 100 / (r + Fraction(point)), "0.000001")}
