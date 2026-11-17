"""Silver build engine: a pure function from the bronze snapshots to silver rows,
the DQ store and the DQ metrics. No I/O here, so the golden run and the dirty
fixtures test exactly what the Lambda runs.

Implements docs/approved_data_rules.md (stages A-F). In the Glue job the
row-level checks that DQDL expresses are decided by Glue Data Quality through
`predicates` (common.dqdl.Predicates), and the per-customer lifecycle runs on
Spark executors through `lifecycle_map`; both default to in-process. Policy: no file is ever
rejected. A row that fails an exclude rule is kept out of silver and stored with
every rule it failed; findings record absences; run controls fail the run only
on a defect of our own pipeline.
"""

from __future__ import annotations

import calendar
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from typing import Any

from common import dec
from common.dec import Q0, Q2, Q3, Q6, WIDE, month_add, month_range
from common.dqdl import Predicates

G_ID = re.compile(r"[1-9][0-9]*")
G_INDUSTRY_ID = re.compile(r"Cliente ([1-9][0-9]*)")
G_TX_MONTH = re.compile(r"(1[0-2]|[1-9])/(3[01]|[12][0-9]|[1-9])/([0-9]{4})")
G_AMOUNT = re.compile(r"-?[0-9]+(\.[0-9]+)?")
G_SM_MONTH = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")
G_SPEND = re.compile(r"-?\$[0-9]{1,6}\.[0-9]{3}")
BOM = b"\xef\xbb\xbf"
MAX_CHARS = 1000
TRUNC = "…[truncated]"


class RunControlError(Exception):
    """A pipeline-integrity assertion failed. Never raised by file content."""


@dataclass
class Hit:
    rule_id: str
    failed_columns: list[str]
    reason: str
    action: str  # exclude | flag | finding


@dataclass
class Row:
    dataset: str
    source_line: int
    values: dict[str, str]
    stage_a_failed: bool = False
    hits: list[Hit] = field(default_factory=list)
    parsed: dict[str, Any] = field(default_factory=dict)

    @property
    def excluded(self) -> bool:
        return any(h.action == "exclude" for h in self.hits)

    def flag(self, rule_id: str, cols: list[str], reason: str) -> None:
        self.hits.append(Hit(rule_id, cols, reason, "flag"))

    def exclude(self, rule_id: str, cols: list[str], reason: str) -> None:
        self.hits.append(Hit(rule_id, cols, reason, "exclude"))


@dataclass
class DatasetInput:
    staging: bytes  # the staging bytes, recovered from bronze by CTO-01
    source_key: str
    sha256: str
    ingested_at: str
    bronze_key: str = ""


def _cap(v: str) -> str:
    return v if len(v) <= MAX_CHARS else v[:MAX_CHARS] + TRUNC


class Counter:
    """evaluated / failed per (rule_id, dataset)."""

    def __init__(self) -> None:
        self.ev: dict[tuple[str, str], int] = defaultdict(int)
        self.fail: dict[tuple[str, str], int] = defaultdict(int)

    def add(self, rule: str, ds: str, evaluated: int = 1, failed: bool | int = False) -> None:
        self.ev[(rule, ds)] += evaluated
        self.fail[(rule, ds)] += int(failed)


# --------------------------------------------------------------------------- #
# Stage A: structure                                                           #
# --------------------------------------------------------------------------- #

def _positional(text: str, cols: list[str]) -> dict[str, str]:
    fields = text.split(",")
    n = len(cols)
    if len(fields) > n:
        fields = fields[:n - 1] + [",".join(fields[n - 1:])]
    fields += [""] * (n - len(fields))
    return dict(zip(cols, fields))


def parse_rows(ds: str, staging: bytes, cols: list[str], cnt: Counter) -> tuple[list[Row], str | None]:
    from common.records import data_records

    header, recs = data_records(staging)
    header_text = None
    if header is not None:
        h = header[3:] if header.startswith(BOM) else header
        header_text = h.decode("utf-8", "replace")
    rows: list[Row] = []
    for i, rec in enumerate(recs, start=2):
        cnt.add("CDO-01", ds)
        try:
            text = rec.decode("utf-8")
            bad_ctrl = next((c for c in text if ord(c) < 0x20), None)
        except UnicodeDecodeError:
            text, bad_ctrl = None, None
        if text is None or bad_ctrl is not None:
            row = Row(ds, i, _positional(rec.decode("utf-8", "replace"), cols), stage_a_failed=True)
            if text is None:
                row.exclude("CDO-01", list(cols), "UNDECODABLE_LINE: the line is not valid UTF-8")
            else:
                row.exclude("CDO-01", list(cols),
                            f"CONTROL_CHAR: the line contains the control character U+{ord(bad_ctrl):04X}")
            cnt.add("CDO-01", ds, 0, True)
            rows.append(row)
            continue
        fields = text.split(",")
        cnt.add("SQ-02", ds)
        if all(f == "" for f in fields):
            row = Row(ds, i, _positional(text, cols), stage_a_failed=True)
            row.exclude("SQ-02", list(cols), "EMPTY_RECORD: every source column is empty")
            cnt.add("SQ-02", ds, 0, True)
            rows.append(row)
            continue
        cnt.add("SQ-01", ds)
        if len(fields) != len(cols):
            row = Row(ds, i, _positional(text, cols), stage_a_failed=True)
            row.exclude("SQ-01", list(cols),
                        f"FIELD_COUNT: expected {len(cols)} fields, found {len(fields)}")
            cnt.add("SQ-01", ds, 0, True)
            rows.append(row)
            continue
        rows.append(Row(ds, i, dict(zip(cols, fields))))
    return rows, header_text


# --------------------------------------------------------------------------- #
# Stage B: cells and keys                                                      #
# --------------------------------------------------------------------------- #

def _precision_ok(raw: str, max_int: int, max_frac: int) -> bool:
    s = raw.lstrip("-")
    ip, _, fp = s.partition(".")
    return len(ip.lstrip("0")) <= max_int and len(fp.rstrip("0")) <= max_frac


def stage_b_transactions(rows: list[Row], cnt: Counter, pred: Predicates | None = None) -> None:
    ds = "transactions"
    pred = pred or Predicates()
    keyed: dict[tuple[int, str], list[Row]] = defaultdict(list)
    for r in rows:
        if r.stage_a_failed:
            continue
        v = r.values
        # SQ-05(a)
        cnt.add("SQ-05", ds)
        if not pred.fails(ds, "SQ-05:id_grammar", r.source_line, not G_ID.fullmatch(v["ID"])):
            r.parsed["customer_id"] = int(v["ID"])
        else:
            r.exclude("SQ-05", ["ID"], "BAD_ID: ID is not a positive integer without padding")
        # SQ-06
        cnt.add("SQ-06", ds)
        m = G_TX_MONTH.fullmatch(v["month"])
        ok = False
        if m:
            mo, day, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                ok = yr >= 1 and calendar.monthrange(yr, mo)[1] == day
            except (ValueError, calendar.IllegalMonthError):
                ok = False
        if not pred.fails(ds, "SQ-06:month_end_date", r.source_line, not ok):
            r.parsed["month"] = f"{yr:04d}-{mo:02d}"
        else:
            r.exclude("SQ-06", ["month"], "BAD_MONTH: month is not a non-padded M/D/YYYY month-end date")
        # SQ-07(a) then CDO-05
        cnt.add("SQ-07a", ds)
        if not pred.fails(ds, "SQ-07a:amount_grammar", r.source_line, not G_AMOUNT.fullmatch(v["amount"])):
            cnt.add("CDO-05", ds)
            if not pred.fails(ds, "CDO-05:amount_precision", r.source_line, not _precision_ok(v["amount"], 6, 6)):
                r.parsed["amount"] = Decimal(v["amount"]).quantize(Q6)
            else:
                r.exclude("CDO-05", ["amount"], "PRECISION: amount does not fit DECIMAL(12,6)")
                cnt.add("CDO-05", ds, 0, True)
        else:
            r.exclude("SQ-07a", ["amount"], "BAD_AMOUNT: amount is not a plain decimal number")
            cnt.add("SQ-07a", ds, 0, True)
        if "customer_id" in r.parsed and "month" in r.parsed:
            keyed[(r.parsed["customer_id"], r.parsed["month"])].append(r)
    # SQ-05(b): every copy of a duplicated key is excluded, whatever its amount.
    for copies in keyed.values():
        for r in copies:
            if pred.fails(ds, "SQ-05:key_unique", r.source_line, len(copies) > 1):
                r.exclude("SQ-05", ["ID", "month"],
                          f"DUPLICATE_KEY: the (ID, month) key appears on {len(copies)} rows")
    for r in rows:
        if not r.stage_a_failed:
            cnt.add("SQ-05", ds, 0, any(h.rule_id == "SQ-05" for h in r.hits))
            cnt.add("SQ-06", ds, 0, any(h.rule_id == "SQ-06" for h in r.hits))


def stage_b_industry(rows: list[Row], cnt: Counter, pred: Predicates | None = None) -> None:
    ds = "industry"
    pred = pred or Predicates()
    keyed: dict[int, list[Row]] = defaultdict(list)
    for r in rows:
        if r.stage_a_failed:
            continue
        cnt.add("SQ-03", ds)
        m = G_INDUSTRY_ID.fullmatch(r.values["ID"])
        if not pred.fails(ds, "SQ-03:id_grammar", r.source_line, m is None) and m:
            r.parsed["customer_id"] = int(m.group(1))
            keyed[r.parsed["customer_id"]].append(r)
        else:
            r.exclude("SQ-03", ["ID"], "BAD_CUSTOMER_ID: ID is not 'Cliente N' with N a positive integer")
    for copies in keyed.values():
        for r in copies:
            if pred.fails(ds, "SQ-03:id_unique", r.source_line, len(copies) > 1):
                r.exclude("SQ-03", ["ID"],
                          f"DUPLICATE_CUSTOMER_ID: the customer_id appears on {len(copies)} rows")
    for r in rows:
        if not r.stage_a_failed:
            cnt.add("SQ-03", ds, 0, any(h.rule_id == "SQ-03" for h in r.hits))


def stage_b_sm(rows: list[Row], spend_cols: list[str], cnt: Counter, pred: Predicates | None = None) -> None:
    ds = "sm_spend"
    pred = pred or Predicates()
    keyed: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        if r.stage_a_failed:
            continue
        cnt.add("SQ-09a", ds)
        if not pred.fails(ds, "SQ-09a:month_grammar", r.source_line, not G_SM_MONTH.fullmatch(r.values["Month"])):
            r.parsed["month"] = r.values["Month"]
            keyed[r.values["Month"]].append(r)
        else:
            r.exclude("SQ-09a", ["Month"], "BAD_MONTH: Month is not YYYY-MM")
        cnt.add("SQ-10", ds)
        bad = [c for c in spend_cols
               if pred.fails(ds, f"SQ-10:{c}", r.source_line, not G_SPEND.fullmatch(r.values[c]))]
        if bad:
            # The reason names columns only: HR-sensitive values never enter a reason (CDO-11).
            r.exclude("SQ-10", bad, f"BAD_SPEND_CELL: {', '.join(bad)} does not match G-SPEND")
            cnt.add("SQ-10", ds, 0, True)
        else:
            cnt.add("CDO-05", ds)  # cannot fail while G-SPEND stands
            r.parsed["spend"] = {c: Decimal(r.values[c].replace("$", "", 1)).quantize(Q3) for c in spend_cols}
    for copies in keyed.values():
        for r in copies:
            if pred.fails(ds, "SQ-09a:month_unique", r.source_line, len(copies) > 1):
                r.exclude("SQ-09a", ["Month"], f"DUPLICATE_MONTH: the Month appears on {len(copies)} lines")
    for r in rows:
        if not r.stage_a_failed:
            cnt.add("SQ-09a", ds, 0, any(h.rule_id == "SQ-09a" for h in r.hits))


# --------------------------------------------------------------------------- #
# Stage E: lifecycle per customer (SB-03..SB-08, SB-11, CDO-07, CRO-03/05, H1-H11)#
# --------------------------------------------------------------------------- #

def _approx(a: Decimal, b: Decimal, tol: Decimal) -> bool:
    return abs(a - b) <= tol * b


def _uneven_splits(cells: list[Decimal | None], W: list[str], paid: list[bool], state: list[str | None],
                   stype: list[str | None], sconf: list[str | None],
                   norm: list[Decimal | None]) -> tuple[list[str | None], list[int]]:
    """SB-11, uneven split of a two-month total (cdo_uneven_split.md § 11).

    Months m and m+1 are a pair when m-1, m, m+1 and m+2 are all known-paid,
    none of the four has a settlement_type (SB-06 or a pair already tagged),
    x[m+2] = x[m-1] = b, x[m] != b and x[m] + x[m+1] = 2b. Every test is an
    exact Decimal equality, with no tolerance and no quantize. Windows are
    tested from the earliest m upward; a tagged month is never re-tagged and
    never serves as a baseline. Sets settlement_type / confidence and
    amount_normalized = b on both months in place (amount never changes) and
    returns (uneven_split_start_month per month, pair start indexes)."""
    n = len(W)
    start: list[str | None] = [None] * n
    pairs: list[int] = []
    with localcontext(WIDE):
        for m in range(1, n - 2):  # needs m-1 >= 0 and m+2 <= n-1
            win = (m - 1, m, m + 1, m + 2)
            if not all(paid[i] for i in win):  # (1) no hole, no unpaid month
                continue
            if any(stype[i] is not None for i in win):  # (2) SB-06 or an earlier pair
                continue
            b = cells[m - 1]
            if cells[m + 2] != b or cells[m] == b or cells[m] + cells[m + 1] != 2 * b:  # (3) (4) (5)
                continue
            if state[m] != "paying" or state[m + 1] != "paying":
                # Unreachable by file content: a known-paid month after a known-paid
                # month is always `paying`. A failure here is a defect of this code.
                raise RunControlError(f"SB-11: pair month state is not paying ({state[m]}, {state[m + 1]})")
            for i in (m, m + 1):
                stype[i], sconf[i], norm[i], start[i] = "uneven_split", "high", b, W[m]
            pairs.append(m)
    return start, pairs


def lifecycle(cells: list[Decimal | None], W: list[str], p: dict) -> dict:
    n = len(W)
    tol = Decimal(str(p["settlement_tolerance"]))
    churn_k = int(p["churn_months"])
    hole = [c is None for c in cells]
    paid = [c is not None and c > 0 for c in cells]
    P = [i for i in range(n) if paid[i]]
    state: list[str | None] = [None] * n
    affected = [False] * n
    churn_ev = [False] * n
    stype: list[str | None] = [None] * n
    sconf: list[str | None] = [None] * n
    catch = [False] * n
    prepaid = [False] * n
    norm: list[Decimal | None] = list(cells)
    gaps: list[dict] = []
    ends: list[tuple[int, bool]] = []  # known-paid months that end an internal stretch
    react_unknown: list[int] = []
    out: dict[str, Any] = {"P": P}

    if not P:
        broken = any(hole)
        for i in range(n):
            state[i] = "unknown" if broken else "pre_acquisition"
            affected[i] = broken
    else:
        f, last = P[0], P[-1]
        lead_broken = any(hole[:f])
        for i in range(f):
            state[i] = "unknown" if lead_broken else "pre_acquisition"
            affected[i] = lead_broken
        if lead_broken:
            affected[f] = True  # H7: the known-paid month that ends a broken stretch
        for a, b in zip(P, P[1:]):
            if b - a == 1:
                continue
            k = b - a - 1
            if any(hole[a + 1:b]):
                for i in range(a + 1, b):
                    state[i], affected[i] = "unknown", True
                affected[b] = True
                ends.append((b, True))
                react_unknown.append(b)
                continue
            ends.append((b, False))
            xp, xq = cells[a], cells[b]
            t1 = _approx(xq, (k + 1) * xp, tol)
            t2 = t3 = False
            pm1 = a - 1
            pm1_hole = pm1 >= 0 and hole[pm1]
            if not t1 and pm1 >= 0 and not pm1_hole and cells[pm1] > 0:
                x0 = cells[pm1]
                t2 = _approx(xp, (k + 1) * x0, tol) and _approx(xq, x0, tol)
                t3 = (not t2) and _approx(xp + xq, (k + 2) * x0, tol)
            hole_aff = pm1_hole and not t1  # H6: only tests 2 and 3 are affected
            g = {"a": a, "b": b, "k": k, "test_arrears": t1, "test_prepay": t2, "test_split": t3,
                 "settlement_type": None, "settlement_confidence": None,
                 "settlement_hole_affected": hole_aff}
            if t1 or t2 or t3:
                typ = "arrears" if t1 else ("prepay" if t2 else "split")
                conf = "low" if typ == "split" else "high"
                g.update(settlement_type=typ, settlement_confidence=conf, outcome="settled")
                for i in range(a + 1, b):
                    state[i], stype[i], sconf[i] = "settled_gap", typ, conf
                settlers = {"arrears": [b], "prepay": [a], "split": [a, b]}[typ]
                for i in settlers:
                    stype[i], sconf[i] = typ, conf
                if typ == "arrears":
                    catch[b] = True
                    total, months, rem_at = xq, list(range(a + 1, b + 1)), b
                elif typ == "prepay":
                    prepaid[a] = True
                    total, months, rem_at = xp, list(range(a, b)), a
                else:
                    total, months, rem_at = xp + xq, list(range(a, b + 1)), b
                share = dec.trunc6(total / len(months))
                with localcontext(WIDE):
                    for i in months:
                        norm[i] = share
                    norm[rem_at] = total - share * (len(months) - 1)
            elif k >= churn_k:
                g["outcome"] = "churn_spell"
                for i in range(a + 1, b):
                    state[i] = "churned"
                churn_ev[a + 1] = True
                state[b] = "reactivated"
            else:
                g["outcome"] = "paused"
                for i in range(a + 1, b):
                    state[i] = "paused"
            if hole_aff:
                for i in range(a, b + 1):
                    affected[i] = True
            gaps.append(g)
        if last < n - 1:
            if any(hole[last + 1:]):
                for i in range(last + 1, n):
                    state[i], affected[i] = "unknown", True
            elif n - 1 - last >= churn_k:
                for i in range(last + 1, n):
                    state[i] = "churned"
                churn_ev[last + 1] = True
                out["open_churn"] = True
            else:
                for i in range(last + 1, n):
                    state[i] = "grace"
                out["grace"] = True
        # SB-04 / H5 / CRO-07
        nxt = P[1] if len(P) > 1 else None
        after_first_broken = any(hole[f + 1:(nxt if nxt is not None else n)])
        first, second = cells[f], (cells[nxt] if nxt is not None else None)
        ratio = j = implied = band = spike = None
        if not after_first_broken and second is not None:
            ratio = dec.quotient(first, second)
            for jj in p["censoring_multiples"]:
                if abs(first - jj * second) <= tol * jj * second:
                    j = int(jj)
                    break
            implied = month_add(W[f], -(j - 1)) if j else None
            spike_ratio = Decimal(str(p["spike_ratio"]))
            lo, hi = (Decimal(str(x)) for x in p["band_edges"])
            spike = first >= spike_ratio * second
            band = "<1.9" if first < lo * second else ("1.9–3" if first < hi * second else "≥3")
        if f == 0:
            cens = "left"
        elif lead_broken or after_first_broken:
            cens = "unknown"
        elif implied is not None and implied <= W[0]:
            cens = "probable_left"
        else:
            cens = "none"
        out.update(cohort_month=W[f], cohort_censoring=cens, first_paid_amount=first,
                   next_paid_amount=second if not after_first_broken else None,
                   first_payment_ratio=ratio, first_payment_multiple=j, implied_start_month=implied,
                   first_payment_band=band, is_first_month_spike=spike,
                   first_payment_hole_affected=after_first_broken, last_paid_month=W[last])
        if state[f] is None:
            state[f] = "new" if cens == "none" and not lead_broken else "paying"
        for i in P:
            if state[i] is None:
                state[i] = "paying"
    # SB-11: after SB-06 and every lifecycle state, before CRO-05 reads amount_normalized
    us_start, pairs = _uneven_splits(cells, W, paid, state, stype, sconf, norm)
    # CRO-05 / H9
    exp: list[Decimal | None] = [None] * n
    con: list[Decimal | None] = [None] * n
    lag: list[Decimal | None] = [None] * n
    mv_unknown = [False] * n
    zero = Decimal("0.000000")
    for t in range(n):
        if hole[t]:
            continue
        if t > 0 and hole[t - 1]:
            mv_unknown[t] = True
        elif t > 0 and state[t] == "paying" and state[t - 1] == "paying":
            d = norm[t] - norm[t - 1]
            exp[t], con[t] = max(d, zero), max(-d, zero)
        else:
            exp[t], con[t] = zero, zero
        if t >= 12:
            if hole[t - 12]:
                mv_unknown[t] = True
            else:
                lag[t] = norm[t - 12]
    last_paid = P[-1] if P else 0
    out.update(state=state, affected=affected, churn_ev=churn_ev, stype=stype, sconf=sconf, catch=catch,
               prepaid=prepaid, norm=norm, exp=exp, con=con, lag=lag, mv_unknown=mv_unknown, gaps=gaps,
               ends=ends, react_unknown=react_unknown, us_start=us_start, pairs=pairs,
               provisional=[i >= last_paid for i in range(n)])
    return out


# --------------------------------------------------------------------------- #
# The build                                                                    #
# --------------------------------------------------------------------------- #

def _key_str(parts: tuple) -> str:
    return "|".join(str(p) for p in parts)


def build(inputs: dict[str, DatasetInput | None], cfg: dict, run_id: str,
          previous: dict | None = None, predicates: Predicates | None = None,
          lifecycle_map=None) -> dict:
    """Run stages A-F. `previous` = {"run_id", "keys": {ds: {"delivered": [...],
    "included": {key: value}}}} of the previous succeeded run, or None.
    `predicates` decides the DQDL-expressible row checks (Glue DQ in the job).
    `lifecycle_map(cells_by_customer, W, params) -> {customer_id: lifecycle}`
    runs lifecycle() per customer (Spark applyInPandas in the job)."""
    pred = predicates or Predicates()
    rules = cfg["rules_by_id"]
    reg = cfg["datasets"]
    order = cfg["dataset_order"]
    rv = cfg["rules_version"]
    cnt = Counter()
    rows: dict[str, list[Row]] = {}
    headers: dict[str, str | None] = {}
    for ds in order:
        inp = inputs.get(ds)
        rows[ds], headers[ds] = parse_rows(ds, inp.staging if inp else b"", reg[ds]["columns"], cnt)
    stage_b_transactions(rows["transactions"], cnt, pred)
    stage_b_industry(rows["industry"], cnt, pred)
    spend_cols = rules["SQ-10"]["params"]["spend_columns"]
    hr_cols = set(rules["CDO-11"]["params"]["hr_sensitive_columns"])
    stage_b_sm(rows["sm_spend"], spend_cols, cnt, pred)

    inc = {ds: [r for r in rows[ds] if not r.excluded] for ds in order}
    findings: list[dict] = []  # {rule_id, dataset, key, reason}

    def finding(rule: str, ds: str, key: dict, reason: str) -> None:
        findings.append({"rule_id": rule, "dataset": ds, "key": key, "reason": reason})

    # ---- Stage C: row flags (included rows only)
    domain = rules["SQ-04"]["params"]["domain"]
    for r in inc["industry"]:
        cnt.add("SQ-04", "industry")
        nfc = unicodedata.normalize("NFC", r.values["Industria"])
        r.parsed["industria_nfc"] = nfc
        code = domain.get(nfc)
        if pred.fails("industry", "SQ-04:industry_domain", r.source_line, code is None) or code is None:
            r.parsed["industry_code"] = rules["SQ-04"]["params"]["unmapped_code"]
            r.flag("SQ-04", ["Industria"], "UNMAPPED_INDUSTRY: Industria is not one of the 6 registered values")
            cnt.add("SQ-04", "industry", 0, True)
        else:
            r.parsed["industry_code"] = code
    for r in inc["transactions"]:
        cnt.add("SQ-07b", "transactions")
        if pred.fails("transactions", "SQ-07b:amount_not_negative", r.source_line, r.parsed["amount"] < 0):
            r.flag("SQ-07b", ["amount"], "NEGATIVE_AMOUNT: amount is below 0")
            cnt.add("SQ-07b", "transactions", 0, True)

    # CDO-06: keys and typed values against the previous succeeded run
    def tkey(r: Row) -> str | None:
        if r.dataset == "transactions":
            return _key_str((r.parsed["customer_id"], r.parsed["month"])) if (
                "customer_id" in r.parsed and "month" in r.parsed) else None
        if r.dataset == "industry":
            return str(r.parsed["customer_id"]) if "customer_id" in r.parsed else None
        return r.parsed.get("month")

    def tval(r: Row) -> dict[str, str]:
        if r.dataset == "transactions":
            return {"amount": str(r.parsed["amount"])}
        if r.dataset == "industry":
            return {"Industria": r.parsed["industria_nfc"]}
        return {c: str(v) for c, v in r.parsed["spend"].items()}

    keys_now: dict[str, dict] = {}
    for ds in order:
        delivered = sorted({k for r in rows[ds] if not r.stage_a_failed and (k := tkey(r))})
        included = {tkey(r): tval(r) for r in inc[ds]}
        keys_now[ds] = {"delivered": delivered, "included": included}
    restatements: list[dict] = []
    for ds in order:
        prev = (previous or {}).get("keys", {}).get(ds)
        if not prev:
            continue
        now_set = set(keys_now[ds]["delivered"])
        for k in prev["delivered"]:
            cnt.add("CDO-06a", ds)
            if k not in now_set:
                cnt.add("CDO-06a", ds, 0, True)
                finding("CDO-06a", ds, _finding_key(ds, k), "REMOVED_KEY: delivered in the previous run, not now")
        for r in inc[ds]:
            k = tkey(r)
            old = prev["included"].get(k)
            if old is None:
                continue
            cnt.add("CDO-06b", ds)
            new = tval(r)
            changed = [c for c in new if old.get(c) != new[c]]
            if changed:
                r.parsed["is_restated"] = True
                r.flag("CDO-06b", changed, f"RESTATED_VALUE: {', '.join(changed)} changed since the previous run")
                cnt.add("CDO-06b", ds, 0, True)
                for c in changed:
                    restatements.append({"dataset_id": ds, "key_json": json.dumps(_finding_key(ds, k)),
                                         "column_name": c, "old_value": old.get(c), "new_value": new[c],
                                         "previous_run_id": previous["run_id"], "hr": c in hr_cols})

    # ---- Holes and the panel (Transactions)
    tx_ok = [r for r in rows["transactions"] if not r.stage_a_failed]
    U = sorted({r.parsed["customer_id"] for r in tx_ok if "customer_id" in r.parsed})
    known = {(r.parsed["customer_id"], r.parsed["month"]): r.parsed["amount"] for r in inc["transactions"]}
    excl_keys = {(r.parsed["customer_id"], r.parsed["month"]) for r in tx_ok
                 if r.excluded and "customer_id" in r.parsed and "month" in r.parsed}
    tx_months = sorted({m for _, m in known})
    W = month_range(tx_months[0], tx_months[-1]) if tx_months else []
    as_of = W[-1] if W else None
    sm_inc_months = sorted({r.parsed["month"] for r in inc["sm_spend"]})
    if as_of is None and sm_inc_months:
        as_of = sm_inc_months[-1]
    confirmed_through = month_add(W[-1], -int(rules["SB-05"]["params"]["churn_confirmed_lag_months"])) if W else None

    # SQ-08
    holes: dict[tuple[int, str], str] = {}
    for c in U:
        for m in W:
            cnt.add("SQ-08", "transactions")
            if (c, m) not in known:
                reason = "excluded" if (c, m) in excl_keys else "missing"
                holes[(c, m)] = reason
                if reason == "missing":
                    cnt.add("SQ-08", "transactions", 0, True)
                    finding("SQ-08", "transactions", {"ID": str(c), "month": m},
                            "MISSING_CUSTOMER_MONTH: no source row carries this customer-month")

    # SQ-09(b)
    sm_carried = {r.parsed["month"] for r in rows["sm_spend"] if "month" in r.parsed}
    if sm_inc_months:
        for m in month_range(sm_inc_months[0], sm_inc_months[-1]):
            cnt.add("SQ-09b", "sm_spend")
            if m not in sm_carried:
                cnt.add("SQ-09b", "sm_spend", 0, True)
                finding("SQ-09b", "sm_spend", {"Month": m}, "MONTH_GAP: no source line carries this month")

    # SQ-12
    ind_by_cid = {r.parsed["customer_id"]: r for r in inc["industry"]}
    tx_cids = sorted({c for c, _ in known})
    for c in tx_cids:
        cnt.add("SQ-12", "industry")
        if c not in ind_by_cid:
            cnt.add("SQ-12", "industry", 0, True)
            finding("SQ-12", "industry", {"ID": str(c)}, "NO_INDUSTRY_ROW: no included Industry row for this customer")

    # SQ-13
    tx_set, sm_set = set(tx_months), set(sm_inc_months)
    for m in sorted(tx_set | sm_set):
        for ds, have in (("transactions", tx_set), ("sm_spend", sm_set)):
            cnt.add("SQ-13", ds)
            if m not in have:
                cnt.add("SQ-13", ds, 0, True)
                kk = {"month": m} if ds == "transactions" else {"Month": m}
                finding("SQ-13", ds, kk, "MONTH_NOT_IN_DATASET: the other money dataset has this month")

    # ---- Stage E: business
    bp = {**rules["SB-06"]["params"], **rules["SB-05"]["params"], **rules["SB-04"]["params"],
          **rules["CRO-07"]["params"]}
    bp["censoring_multiples"] = rules["SB-04"]["params"]["censoring_multiples"]
    tx_by_key = {(r.parsed["customer_id"], r.parsed["month"]): r for r in inc["transactions"]}
    cells_by_c = {c: [known.get((c, m)) for m in W] for c in U}
    if lifecycle_map is None:
        lives: dict[int, dict] = {c: lifecycle(cells, W, bp) for c, cells in cells_by_c.items()}
    else:
        lives = lifecycle_map(cells_by_c, W, bp)
        if set(lives) != set(U):
            raise RunControlError("lifecycle_map did not return exactly one lifecycle per customer")
    all_paid = [a for a in known.values() if a > 0]
    port_med = dec.median(all_paid)
    op = rules["SB-08"]["params"]
    ratio_out, min_pay = Decimal(str(op["outlier_ratio"])), int(op["min_payments"])
    overrides = {int(o["customer_id"]): bool(o["is_outlier"]) for o in op.get("owner_overrides") or []}

    cm_rows: list[dict] = []
    gap_rows: list[dict] = []
    cust_rows: list[dict] = []
    figures = defaultdict(int)
    for c in U:
        L = lives[c]
        st = L["state"]
        hole_m = [m for m in W if (c, m) in holes]
        pair_of = {i: m0 for m0 in L["pairs"] for i in (m0, m0 + 1)}  # SB-11 month -> pair start
        figures["uneven_split_pairs"] += len(L["pairs"])
        figures["uneven_split_customers"] += int(bool(L["pairs"]))
        for i, m in enumerate(W):
            amt = known.get((c, m))
            is_hole = amt is None
            figures["state_" + st[i]] += 1
            figures["provisional"] += int(L["provisional"][i])
            cm_rows.append({
                "customer_id": c, "month": m, "amount": amt,
                "amount_value": (amt * 10000).quantize(Q2) if amt is not None else None,
                "is_hole": is_hole, "hole_reason": holes.get((c, m)),
                "is_paying": (amt > 0) if amt is not None else None, "lifecycle_state": st[i],
                "is_churn_event": L["churn_ev"][i], "is_provisional": L["provisional"][i],
                "is_hole_affected": L["affected"][i], "settlement_type": L["stype"][i],
                "settlement_confidence": L["sconf"][i], "uneven_split_start_month": L["us_start"][i],
                "is_catch_up": L["catch"][i],
                "is_prepaid": L["prepaid"][i], "amount_normalized": L["norm"][i],
                "expansion_amount": L["exp"][i], "contraction_amount": L["con"][i],
                "amount_lag12": L["lag"][i],
            })
            if not is_hole:
                r = tx_by_key[(c, m)]
                cnt.add("SB-05", "transactions")
                if st[i] == "unknown":
                    r.flag("SB-05", ["month"], "STATE_UNKNOWN: the month sits in a stretch broken by a hole")
                    cnt.add("SB-05", "transactions", 0, True)
                cnt.add("SB-11", "transactions")
                if i in pair_of:
                    m0 = pair_of[i]
                    r.flag("SB-11", ["amount"], f"UNEVEN_SPLIT: {W[m0]} and {W[m0 + 1]} sum to twice the amount "
                                                f"of {W[m0 - 1]} and {W[m0 + 2]}")
                    cnt.add("SB-11", "transactions", 0, True)
                cnt.add("CRO-05", "transactions")
                if L["mv_unknown"][i]:
                    r.flag("CRO-05", ["amount"], "MOVEMENT_UNKNOWN: month t-1 or t-12 is a hole")
                    cnt.add("CRO-05", "transactions", 0, True)
        for b, broken in L["ends"]:
            cnt.add("SB-07", "transactions", 1, broken)
            if broken:
                tx_by_key[(c, W[b])].flag("SB-07", ["month"],
                                          "REACTIVATION_UNKNOWN: the payment ends a stretch broken by a hole")
        for g in L["gaps"]:
            cnt.add("SB-06", "transactions", 1, g["settlement_hole_affected"])
            figures["gaps"] += 1
            figures["gap_" + g["outcome"]] += 1
            if g["settlement_type"]:
                figures["settled_" + g["settlement_type"]] += 1
            if g["outcome"] == "churn_spell":
                figures["reactivations"] += 1
            if g["settlement_hole_affected"]:
                finding("SB-06", "transactions", {"ID": str(c), "month": W[g["a"] + 1]},
                        "SETTLEMENT_HOLE: month p-1 of this gap is a hole")
            gap_rows.append({"customer_id": c, "p_month": W[g["a"]], "q_month": W[g["b"]],
                             "gap_start_month": W[g["a"] + 1], "k": g["k"],
                             "test_arrears": g["test_arrears"], "test_prepay": g["test_prepay"],
                             "test_split": g["test_split"], "settlement_type": g["settlement_type"],
                             "settlement_confidence": g["settlement_confidence"],
                             "settlement_hole_affected": g["settlement_hole_affected"], "outcome": g["outcome"]})
        figures["open_churn"] += int(bool(L.get("open_churn")))
        figures["grace_customers"] += int(bool(L.get("grace")))
        if any(g["outcome"] == "churn_spell" for g in L["gaps"]):
            figures["reactivated_customers"] += 1
        paid_amts = [known[(c, W[i])] for i in L["P"]]
        has_holes = bool(hole_m)
        med = dec.median(paid_amts)
        is_out = bool(len(paid_amts) >= min_pay and port_med is not None and med is not None
                      and med >= ratio_out * port_med)
        source = "rule"
        if c in overrides:
            is_out, source = overrides[c], "owner"
        ind = ind_by_cid.get(c)
        row = {"customer_id": c, "in_transactions": True,
               "industry_code": ind.parsed["industry_code"] if ind else rules["SQ-12"]["params"]["unknown_code"],
               "is_industry_unknown": ind is None,
               "is_industry_unmapped": bool(ind and ind.parsed["industry_code"] == "UNMAPPED"),
               "paid_months": len(paid_amts), "median_paid_amount": dec.quotient(med, Decimal(1)) if med is not None else None,
               "is_outlier_customer": is_out, "outlier_source": source,
               "outlier_multiple": dec.quotient(med, port_med) if med is not None and port_med else None,
               "has_excluded_months": has_holes, "hole_months": len(hole_m),
               "cohort_month": None, "cohort_censoring": None, "is_new_logo": False,
               "first_paid_amount": None, "next_paid_amount": None, "first_payment_ratio": None,
               "first_payment_multiple": None, "implied_start_month": None, "first_payment_band": None,
               "is_first_month_spike": None, "first_payment_hole_affected": None, "last_paid_month": None}
        if L["P"]:
            for k in ("cohort_month", "cohort_censoring", "first_paid_amount", "next_paid_amount",
                      "first_payment_ratio", "first_payment_multiple", "implied_start_month",
                      "first_payment_band", "is_first_month_spike", "first_payment_hole_affected",
                      "last_paid_month"):
                row[k] = L[k]
            row["is_new_logo"] = L["cohort_censoring"] == "none"
            cnt.add("SB-04", "transactions", 1, L["cohort_censoring"] == "unknown")
            cnt.add("SB-08", "transactions", 1, has_holes)
            cnt.add("CRO-07", "transactions", 1, L["first_payment_hole_affected"])
            if L["cohort_censoring"] == "unknown":
                finding("SB-04", "transactions", {"ID": str(c)}, "COHORT_UNKNOWN: a hole hides the cohort start")
            if has_holes:
                finding("SB-08", "transactions", {"ID": str(c)},
                        "OUTLIER_INCOMPLETE_HISTORY: the customer has excluded or missing months")
            if L["first_payment_hole_affected"]:
                finding("CRO-07", "transactions", {"ID": str(c)},
                        "FIRST_PAYMENT_UNKNOWN: a hole follows the first paid month")
            figures["cens_" + L["cohort_censoring"]] += 1
            if row["is_new_logo"]:
                figures["new_logos"] += 1
                if L["is_first_month_spike"]:
                    figures["spike_19"] += 1
                if L["first_payment_band"] == "≥3":
                    figures["spike_3"] += 1
        cust_rows.append(row)
    # Industry customers with no Transactions row are kept, not a finding.
    for cid, ind in sorted(ind_by_cid.items()):
        if cid in lives:
            continue
        cust_rows.append({"customer_id": cid, "in_transactions": False,
                          "industry_code": ind.parsed["industry_code"], "is_industry_unknown": False,
                          "is_industry_unmapped": ind.parsed["industry_code"] == "UNMAPPED",
                          "cohort_month": None, "cohort_censoring": None, "is_new_logo": False,
                          "first_paid_amount": None, "next_paid_amount": None, "first_payment_ratio": None,
                          "first_payment_multiple": None, "implied_start_month": None,
                          "first_payment_band": None, "is_first_month_spike": None,
                          "first_payment_hole_affected": None, "paid_months": 0, "last_paid_month": None,
                          "median_paid_amount": None, "is_outlier_customer": False, "outlier_source": "rule",
                          "outlier_multiple": None, "has_excluded_months": False, "hole_months": 0})

    # ---- S&M flags and month control
    sm_by_month = {r.parsed["month"]: r for r in inc["sm_spend"]}
    rev_by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0.000000"))
    for (c, m), a in known.items():
        rev_by_month[m] += a
    neg_expected = set(rules["SB-10"]["params"]["expected_negative_columns"])
    for r in inc["sm_spend"]:
        cnt.add("SB-10", "sm_spend")
        neg = [c for c in spend_cols if r.parsed["spend"][c] < 0]
        if neg:
            code = "NEGATIVE_SPEND_OTHER_CATEGORY" if set(neg) - neg_expected else "NEGATIVE_SPEND"
            r.flag("SB-10", neg, f"{code}: negative value in {', '.join(neg)}")
            cnt.add("SB-10", "sm_spend", 0, True)
    lo_b, hi_b = (Decimal(str(x)) for x in rules["CDO-08"]["params"]["tripwire_bounds"])
    tripped: set[str] = set()
    for r in inc["sm_spend"]:
        m = r.parsed["month"]
        if m not in tx_set:
            continue
        cnt.add("CDO-08", "sm_spend")
        S = sum((v * 100000000 for v in r.parsed["spend"].values()), Decimal(0))
        R = rev_by_month[m] * 10000
        if R <= 0 or S < lo_b * R or S > hi_b * R:
            tripped.add(m)
            r.flag("CDO-08", ["Month"], "UNIT_TRIPWIRE: S&M / revenue is outside the configured bounds")
            cnt.add("CDO-08", "sm_spend", 0, True)

    months_all = month_range(min(tx_set | sm_set), max(tx_set | sm_set)) if (tx_set or sm_set) else []
    hole_count = defaultdict(int)
    for (_, m) in holes:
        hole_count[m] += 1
    mc_rows = []
    per_month = defaultdict(lambda: defaultdict(int))
    for row in cm_rows:
        pm = per_month[row["month"]]
        pm["paying"] += int(bool(row["is_paying"]))
        pm["new"] += int(row["lifecycle_state"] == "new")
        pm["churn"] += int(row["is_churn_event"])
        pm["react"] += int(row["lifecycle_state"] == "reactivated")
    ratios = []
    for m in months_all:
        in_tx, in_sm = m in tx_set, m in sm_by_month
        rev = rev_by_month[m] if in_tx else None
        smt = sum(sm_by_month[m].parsed["spend"].values(), Decimal("0.000")) if in_sm else None
        ratio = None
        if in_tx and in_sm and rev != 0:
            ratio = dec.quotient(smt * 100000000, rev * 10000)
            ratios.append(ratio)
        confirmed = confirmed_through is not None and m <= confirmed_through
        mc_rows.append({
            "month": m, "in_transactions": in_tx, "in_sm_spend": in_sm,
            "revenue_total": rev, "revenue_value_total": (rev * 10000).quantize(Q2) if rev is not None else None,
            "hole_count": hole_count[m] if in_tx else 0,
            "revenue_is_complete": bool(in_tx and hole_count[m] == 0),
            "sm_total": smt, "sm_value_total": (smt * 100000000).quantize(Q0) if smt is not None else None,
            "sm_to_revenue_ratio": ratio, "is_unit_tripwire": (m in tripped) if (in_tx and in_sm) else None,
            "scope_status": rules["CFO-05"]["params"]["scope_status"],
            "paying_customers": per_month[m]["paying"] if in_tx else None,
            "new_logos": per_month[m]["new"] if in_tx else None,
            "churn_events": per_month[m]["churn"] if (in_tx and confirmed) else None,
            "reactivations": per_month[m]["react"] if in_tx else None,
            "is_churn_confirmed": confirmed,
        })

    # ---- Silver rows
    lin = {ds: _lineage(inputs.get(ds), run_id, rv, as_of) for ds in order}
    silver: dict[str, list[dict]] = {k: [] for k in ("transactions", "industry", "sm_spend", "customer",
                                                      "customer_month", "gap", "month_control",
                                                      "source_status", "restatement_log")}
    for r in inc["transactions"]:
        a = r.parsed["amount"]
        silver["transactions"].append({
            "customer_id": r.parsed["customer_id"], "month": r.parsed["month"], "amount": a,
            "amount_value": (a * 10000).quantize(Q2), "is_paying": a > 0, "is_negative_amount": a < 0,
            "is_restated": bool(r.parsed.get("is_restated")), "id_raw": r.values["ID"],
            "month_raw": r.values["month"], "amount_raw": r.values["amount"],
            **lin["transactions"], "_source_line": r.source_line})
    for r in inc["industry"]:
        silver["industry"].append({
            "customer_id": r.parsed["customer_id"], "industry_code": r.parsed["industry_code"],
            "industria_raw": r.values["Industria"], "industria_nfc": r.parsed["industria_nfc"],
            "is_industry_unmapped": r.parsed["industry_code"] == "UNMAPPED",
            "is_restated": bool(r.parsed.get("is_restated")), "id_raw": r.values["ID"],
            **lin["industry"], "_source_line": r.source_line})
    for r in inc["sm_spend"]:
        restated_cols = {c for h in r.hits if h.rule_id == "CDO-06b" for c in h.failed_columns}
        for c in spend_cols:
            v = r.parsed["spend"][c]
            silver["sm_spend"].append({
                "month": r.parsed["month"], "category": c, "spend": v,
                "spend_value": (v * 100000000).quantize(Q0), "spend_raw": r.values[c],
                "is_negative_spend": v < 0, "is_restated": c in restated_cols,
                "is_unit_tripwire": r.parsed["month"] in tripped, "hr_sensitive": c in hr_cols,
                **lin["sm_spend"], "_source_line": r.source_line})
    ind_sha = inputs["industry"].sha256 if inputs.get("industry") else None
    for row in cust_rows:
        silver["customer"].append({**row, **lin["transactions"], "_industry_source_sha256": ind_sha})
    for row in cm_rows:
        silver["customer_month"].append({**row, **lin["transactions"]})
    for row in gap_rows:
        silver["gap"].append({**row, **lin["transactions"]})
    sm_sha = inputs["sm_spend"].sha256 if inputs.get("sm_spend") else None
    for row in mc_rows:
        silver["month_control"].append({**row, **lin["transactions"], "_sm_source_sha256": sm_sha})
    cp = rules["CFO-03"]["params"]
    for ds in ("transactions", "sm_spend"):
        silver["source_status"].append({"dataset_id": ds, "currency_code": cp["currency_code"],
                                        "currency_status": cp["currency_status"],
                                        "basis_status": cp["basis_status"],
                                        "basis_hint": cp["basis_hint"][ds], **lin[ds]})
    for rs in restatements:
        silver["restatement_log"].append({**{k: v for k, v in rs.items() if k != "hr"},
                                          "hr_sensitive": rs["hr"], **lin[rs["dataset_id"]]})

    result = {
        "run_id": run_id, "as_of_month": as_of, "W": W, "rows": rows, "included": inc, "findings": findings,
        "counter": cnt, "silver": silver, "headers": headers, "keys": keys_now, "lineage": lin,
        "figures": dict(figures), "portfolio_median": port_med,
        "outliers": sorted(r["customer_id"] for r in cust_rows if r["is_outlier_customer"]),
        "sm_ratio_range": (min(ratios), max(ratios)) if ratios else None,
        "churn_confirmed_through": confirmed_through, "holes": holes, "predicates": pred,
    }
    result["controls"] = run_controls(result, inputs, cfg)
    return result


def _finding_key(ds: str, k: str) -> dict:
    if ds == "transactions":
        c, m = k.split("|")
        return {"ID": c, "month": m}
    if ds == "industry":
        return {"ID": k}
    return {"Month": k}


def _lineage(inp: DatasetInput | None, run_id: str, rv: str, as_of: str | None) -> dict:
    return {"_run_id": run_id, "_source_key": inp.source_key if inp else None,
            "_source_sha256": inp.sha256 if inp else None, "_ingested_at": inp.ingested_at if inp else None,
            "_rules_version": rv, "as_of_month": as_of}


# --------------------------------------------------------------------------- #
# Stage F: run controls                                                        #
# --------------------------------------------------------------------------- #

def _raw_sum(strings: list[str]) -> Decimal:
    """Independent recomputation from the source strings (CDO-04 (3))."""
    total = Decimal(0)
    with localcontext(WIDE):
        for s in strings:
            total += Decimal(s)
    return total


def run_controls(res: dict, inputs: dict[str, DatasetInput | None], cfg: dict) -> list[dict]:
    from common.records import data_records

    out: list[dict] = []
    order = cfg["dataset_order"]
    rules = cfg["rules_by_id"]
    silver = res["silver"]
    hr_cols = set(rules["CDO-11"]["params"]["hr_sensitive_columns"])

    def check(rule: str, ds: str, ok: bool, detail: str = "") -> None:
        out.append({"rule_id": rule, "dataset": ds, "evaluated": 1, "failed": 0 if ok else 1, "detail": detail})

    for ds in order:
        inp = inputs.get(ds)
        _, recs = data_records(inp.staging if inp else b"")
        rows, inc = res["rows"][ds], res["included"][ds]
        n_ex = sum(1 for r in rows if r.excluded)
        ok = (len(recs) == len(rows) == len(inc) + n_ex
              and all(any(h.action == "exclude" for h in r.hits) for r in rows if r.excluded)
              and all(not r.excluded for r in rows if any(h.action == "flag" for h in r.hits)))
        if ds == "transactions":
            ok = ok and len(silver["transactions"]) == len(inc)
            raw = _raw_sum([r.values["amount"] for r in inc])
            s_amt = sum((x["amount"] for x in silver["transactions"]), Decimal(0))
            s_val = sum((x["amount_value"] for x in silver["transactions"]), Decimal(0))
            ok = ok and raw == s_amt and s_val == s_amt * 10000
            ok = ok and len(silver["customer_month"]) == len(inc) + len(res["holes"]) == \
                len(set(r.parsed["customer_id"] for r in rows if "customer_id" in r.parsed and not r.stage_a_failed)) * len(res["W"])
        elif ds == "industry":
            ok = ok and len(silver["industry"]) == len(inc)
        else:
            spend_cols = rules["SQ-10"]["params"]["spend_columns"]
            ok = ok and len(silver["sm_spend"]) == 7 * len(inc)
            raw = _raw_sum([r.values[c].replace("$", "", 1) for r in inc for c in spend_cols])
            s_sp = sum((x["spend"] for x in silver["sm_spend"]), Decimal(0))
            s_val = sum((x["spend_value"] for x in silver["sm_spend"]), Decimal(0))
            ok = ok and raw == s_sp and s_val == s_sp * 100000000
        check("CDO-04", ds, ok)
    # CTO-06: lineage on every row
    req = ["_run_id", "_rules_version"]
    for t, rows_ in silver.items():
        for x in rows_:
            if any(x.get(k) is None for k in req) or "as_of_month" not in x:
                check("CTO-06", t, False, "missing lineage")
                break
    for ds in order:
        if inputs.get(ds) and any(x.get("_source_sha256") is None for x in silver.get(ds, [])):
            check("CTO-06", ds, False, "missing source lineage")
        else:
            check("CTO-06", ds, True)
    # SB-01, SB-03
    ok1 = all(x["amount_value"] / 10000 == x["amount"] for x in silver["transactions"])
    ok3 = all(x["is_paying"] == (x["amount"] > 0) for x in silver["transactions"])
    check("SB-01", "transactions", ok1)
    check("SB-03", "transactions", ok3)
    # SB-02
    ok2 = all(x["spend_value"] == x["spend_value"].to_integral_value() and
              x["spend_value"] / 100000000 == x["spend"] for x in silver["sm_spend"])
    check("SB-02", "sm_spend", ok2)
    # SB-09: one industry_code per customer
    seen: dict[int, int] = defaultdict(int)
    for x in silver["customer"]:
        seen[x["customer_id"]] += 1
    check("SB-09", "industry", all(v == 1 for v in seen.values()))
    # CDO-07: exactly one known state per panel cell
    states = set(rules["CDO-07"]["params"]["states"])
    cells = defaultdict(int)
    for x in silver["customer_month"]:
        cells[(x["customer_id"], x["month"])] += 1
    check("CDO-07", "transactions", all(v == 1 for v in cells.values()) and
          all(x["lifecycle_state"] in states for x in silver["customer_month"]))
    # CRO-03: Σ normalized = Σ amount per customer, exactly
    per = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for x in silver["customer_month"]:
        if x["amount"] is not None:
            per[x["customer_id"]][0] += x["amount"]
            per[x["customer_id"]][1] += x["amount_normalized"]
    check("CRO-03", "transactions", all(a == b for a, b in per.values()))
    # CFO-03 / CFO-05
    cp = rules["CFO-03"]["params"]
    ss = {x["dataset_id"]: x for x in silver["source_status"]}
    for ds in ("transactions", "sm_spend"):
        x = ss.get(ds)
        check("CFO-03", ds, bool(x) and x["currency_status"] == cp["currency_status"]
              and x["basis_status"] == cp["basis_status"] and x["basis_hint"] == cp["basis_hint"][ds])
    scope = rules["CFO-05"]["params"]["scope_status"]
    ok5 = all(x["scope_status"] == scope for x in silver["month_control"])
    check("CFO-05", "transactions", ok5)
    check("CFO-05", "sm_spend", ok5)
    # CDO-11: HR values never in a reason, and HR categories only in the hr partition
    # Reasons are built from templates with column names only; a leak would be a
    # code defect. Only money-shaped values are checked, so no file content can
    # trip this control.
    hr_vals = {r.values[c] for r in res["rows"]["sm_spend"] for c in hr_cols if "$" in r.values.get(c, "")}
    reasons = [h.reason for ds in order for r in res["rows"][ds] for h in r.hits] + \
              [f["reason"] for f in res["findings"]]
    leak = any(v in reason for v in hr_vals for reason in reasons)
    part_ok = all(x["hr_sensitive"] == (x["category"] in hr_cols) for x in silver["sm_spend"])
    for ds in order:
        check("CDO-11", ds, (not leak) and part_ok)
    return out


def assert_controls(res: dict) -> None:
    bad = [c for c in res["controls"] if c["failed"]]
    if bad:
        raise RunControlError("run controls failed: " + ", ".join(f"{c['rule_id']}/{c['dataset']}" for c in bad))
