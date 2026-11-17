"""Query spec -> one governed SELECT (docs/semantic_layer.md §2, catalog sl-2026-11-17).

Kimi K3 fills the spec through tool use; this module validates it (every id, value
and op against the catalog, §2.3 rule 1), routes the deterministic out-of-scope
cases (§3: a month after data_complete_through, an HR value, a not_available metric),
picks one source for all metrics (allowed joins only, rule 2), and builds the SQL with
sqlglot (Trino dialect) from catalog fragments. Every value that comes from the spec
is a `?` parameter (Athena ExecutionParameters) after validation; the only literals
are catalog text and the run context (snapshot ids, month keys) read from our own
run reports. The result is parsed back and checked: exactly one SELECT, only
allowlisted finora_gold objects, customer_id only inside an aggregate, a LIMIT.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

from . import catalog as C

RUN_ID_RE = re.compile(r"r[0-9]{8}T[0-9]{6}Z")
MONTH = re.compile(r"20[0-9]{2}-(0[1-9]|1[0-2])")
QUARTER = re.compile(r"20[0-9]{2}-Q[1-4]")
HALF = re.compile(r"20[0-9]{2}-H[12]")
YEAR_TEXT = re.compile(r"20[0-9]{2}")
RULE_ID = re.compile(r"[A-Z]{2,3}-[0-9]{2}[a-z]?")
SCENARIO = re.compile(r"[a-z0-9_]{1,40}")
METRIC_ID = re.compile(r"(dq|acq|mrr)\.[a-z0-9_]+")
LINE = re.compile(r"[a-z_]{3,30}")
DIMS = set(C.DIMENSIONS)
FILTER_ENUMS = {
    "industry": set(C.INDUSTRIES), "spend_category": set(C.SPEND_CATEGORIES), "spend_group": set(C.SPEND_GROUPS),
    "funnel_stage": set(C.STAGES), "dataset_id": set(C.DATASETS), "rule_status": {"pass", "warn", "fail", "na"},
    "driver": set(C.DRIVERS),
}
TIME_KEYS = {"from", "to", "year", "quarter", "period_code", "relative"}
RELATIVE = {"latest_month", "latest_quarter", "latest_year", "full_window", "latest_run"}
DERIVED_OPS = {"ratio", "share", "growth", "rank", "lever_scenario"}
MAX_ROWS = 200
DEFAULT_LIMIT = 12


class CompileError(Exception):
    """The spec names something outside the catalog (or an unsupported combination).
    `errors` goes back to Kimi for the one allowed retry."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class OutOfScope(Exception):
    def __init__(self, reason_code: str, slots: dict | None = None):
        super().__init__(reason_code)
        self.reason_code, self.slots = reason_code, slots or {}


@dataclass
class Context:
    """The run context the compiler resolves (§1.0), never the model."""
    gold_run_id: str
    dq_run_id: str
    data_complete_through: str          # YYYY-MM
    window_start_month: str             # YYYY-MM (Won starts the month after)
    churn_confirmed_through: str        # YYYY-MM
    snapshots: dict = field(default_factory=dict)   # gold table -> Iceberg snapshot id of gold_run_id
    figures: dict = field(default_factory=dict)     # caveat figures templated from gold at refresh

    @property
    def dct_key(self) -> int:
        return int(self.data_complete_through.replace("-", ""))


@dataclass
class Compiled:
    kind: str                           # sql | dq | lever
    spec: dict
    spec_hash: str
    metrics: list
    dims: list                          # requested + implicit grain dims (output order)
    source: str = ""
    sql: str = ""
    params: list = field(default_factory=list)
    sql_hash: str = ""
    columns: list = field(default_factory=list)       # SQL output columns
    meta: dict = field(default_factory=dict)          # column -> {fmt, unit, metric, dim}
    time: dict = field(default_factory=dict)          # resolved time window
    derived: dict | None = None
    sort: dict | None = None
    limit: int = DEFAULT_LIMIT
    chart_type: str = "table"
    title_es: str = ""
    evidence: str = "observado"
    caveats: list = field(default_factory=list)
    kpi_ids: list = field(default_factory=list)
    allowed_roles: list = field(default_factory=lambda: list(C.ROLES))
    won_definition: str = "first_payment"
    plan: dict = field(default_factory=dict)          # dq / lever specifics


# ---------------------------------------------------------------------------- #
# Validation (§2.1 schema, enforced in code)                                    #
# ---------------------------------------------------------------------------- #

def _canon(spec: dict) -> str:
    return json.dumps(spec, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def spec_hash(spec: dict) -> str:
    return hashlib.sha256(_canon(spec).encode()).hexdigest()[:32]


def validate(raw: Any) -> dict:
    """The normalized spec, or CompileError with every problem found."""
    errs: list[str] = []
    if not isinstance(raw, dict):
        raise CompileError(["the spec must be an object"])
    allowed = {"catalog_version", "intent", "domain", "metrics", "derived", "dimensions", "filters", "won_definition",
               "sort", "limit", "chart", "out_of_scope"}
    extra = set(raw) - allowed
    if extra:
        errs.append(f"unknown keys: {sorted(extra)}")
    if raw.get("catalog_version") != C.VERSION:
        errs.append(f"catalog_version must be {C.VERSION}")
    intent = raw.get("intent")
    if intent not in ("answer", "out_of_scope"):
        errs.append("intent must be answer or out_of_scope")
    spec: dict[str, Any] = {"catalog_version": C.VERSION, "intent": intent}
    if intent == "out_of_scope":
        oos = raw.get("out_of_scope")
        code = oos.get("reason_code") if isinstance(oos, dict) else None
        if code not in C.OOS:
            errs.append("out_of_scope.reason_code is not a catalog reason code")
        slots = oos.get("slots") if isinstance(oos, dict) else None
        clean_slots = {}
        if isinstance(slots, dict):
            for k, v in list(slots.items())[:3]:
                if isinstance(k, str) and isinstance(v, str) and not re.search(r"\d", v):
                    clean_slots[k[:20]] = v[:40]  # slots carry labels, never numbers (§2.1)
        if errs:
            raise CompileError(errs)
        spec["out_of_scope"] = {"reason_code": code, "slots": clean_slots}
        # keep the metrics/time if given: the alternative (OOS-06) reuses them
        for k in ("domain", "metrics", "dimensions", "filters", "won_definition"):
            if k in raw:
                spec[k] = raw[k]
        return spec
    if "out_of_scope" in raw and raw.get("out_of_scope"):
        errs.append("an answer cannot carry out_of_scope")
    domain = raw.get("domain")
    if domain not in ("dq", "acquisition", "mrr"):
        errs.append("domain must be dq, acquisition or mrr")
    metrics = raw.get("metrics")
    if not isinstance(metrics, list) or not 1 <= len(metrics) <= 3 or len(set(map(str, metrics))) != len(metrics):
        errs.append("metrics must list 1 to 3 distinct metric ids")
        metrics = []
    for mid in metrics:
        if not isinstance(mid, str) or not METRIC_ID.fullmatch(mid) or mid not in C.METRICS:
            errs.append(f"unknown metric {str(mid)[:40]}")
    dims = raw.get("dimensions") or []
    if not isinstance(dims, list) or len(dims) > 2 or len(set(map(str, dims))) != len(dims) or \
            not all(d in DIMS for d in dims):
        errs.append("dimensions must be up to 2 distinct catalog dimensions")
        dims = []
    filters = raw.get("filters")
    if not isinstance(filters, dict):
        errs.append("filters is required (with time)")
        filters = {}
    f_errs, f_clean = _validate_filters(filters)
    errs += f_errs
    wd = raw.get("won_definition", "first_payment")
    if wd not in ("first_payment", "new_logo"):
        errs.append("won_definition must be first_payment or new_logo")
    derived = raw.get("derived") or []
    if not isinstance(derived, list) or len(derived) > 1:
        errs.append("derived takes at most one operation")
        derived = []
    d_clean = None
    if derived:
        d_errs, d_clean = _validate_derived(derived[0])
        errs += d_errs
    sort = raw.get("sort")
    s_clean = None
    if sort is not None:
        if not isinstance(sort, dict) or set(sort) - {"by", "dir"} or sort.get("dir") not in ("asc", "desc") or \
                not isinstance(sort.get("by"), str):
            errs.append("sort must be {by, dir: asc|desc}")
        else:
            s_clean = {"by": sort["by"][:60], "dir": sort["dir"]}
    limit = raw.get("limit", DEFAULT_LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        errs.append("limit must be an integer from 1 to 50")
        limit = DEFAULT_LIMIT
    chart = raw.get("chart")
    ctype = chart.get("type") if isinstance(chart, dict) else None
    if ctype not in ("kpi", "bar", "line", "table"):
        errs.append("chart.type must be kpi, bar, line or table")
    if errs:
        raise CompileError(errs)
    spec.update({"domain": domain, "metrics": list(metrics), "dimensions": list(dims), "filters": f_clean,
                 "won_definition": wd, "limit": limit, "chart": {"type": ctype}})
    if d_clean:
        spec["derived"] = [d_clean]
    if s_clean:
        spec["sort"] = s_clean
    return spec


def _validate_filters(f: dict) -> tuple[list[str], dict]:
    errs: list[str] = []
    out: dict[str, Any] = {}
    allowed = {"time", "industry", "spend_category", "spend_group", "funnel_stage", "scenario_id", "rule_id",
               "dataset_id", "rule_status", "mrr_line", "driver", "customer_scope"}
    if set(f) - allowed:
        errs.append(f"unknown filters: {sorted(set(f) - allowed)}")
    t = f.get("time")
    if not isinstance(t, dict) or set(t) - TIME_KEYS or len(t) > 2:
        errs.append("filters.time must be an object with at most 2 of from, to, year, quarter, period_code, relative")
        t = {}
    tc: dict[str, Any] = {}
    for k, v in t.items():
        ok = ((k in ("from", "to") and isinstance(v, str) and MONTH.fullmatch(v)) or
              (k == "year" and isinstance(v, int) and not isinstance(v, bool) and 2020 <= v <= 2035) or
              (k == "quarter" and isinstance(v, str) and QUARTER.fullmatch(v)) or
              (k == "period_code" and v in ("pre_2023_06", "from_2023_06", "full")) or
              (k == "relative" and v in RELATIVE))
        if not ok:
            errs.append(f"filters.time.{k} is not valid")
        else:
            tc[k] = v
    out["time"] = tc
    for k, enum in FILTER_ENUMS.items():
        if k in f:
            v = f[k]
            if not isinstance(v, list) or not v or len(v) > 8 or not all(x in enum for x in v):
                errs.append(f"filters.{k} must list catalog values")
            else:
                out[k] = sorted(set(v))
    if "rule_id" in f:
        v = f["rule_id"]
        if not isinstance(v, list) or not v or len(v) > 10 or not all(isinstance(x, str) and RULE_ID.fullmatch(x) for x in v):
            errs.append("filters.rule_id must list rule ids like SB-11")
        else:
            out["rule_id"] = sorted(set(v))
    if "mrr_line" in f:
        v = f["mrr_line"]
        if not isinstance(v, list) or not v or not all(isinstance(x, str) and LINE.fullmatch(x) and x in C.MRR_LINES for x in v):
            errs.append("filters.mrr_line must list catalog MRR lines")
        else:
            out["mrr_line"] = sorted(set(v))
    if "scenario_id" in f:
        v = f["scenario_id"]
        if not isinstance(v, str) or not SCENARIO.fullmatch(v):
            errs.append("filters.scenario_id is not valid")
        elif v != "base":
            out["scenario_id"] = v
    if "customer_scope" in f:
        if f["customer_scope"] not in C.CUSTOMER_SCOPES:
            errs.append("filters.customer_scope is not valid")
        else:
            out["customer_scope"] = f["customer_scope"]
    return errs, out


def _validate_derived(d: Any) -> tuple[list[str], dict | None]:
    if not isinstance(d, dict) or d.get("op") not in DERIVED_OPS:
        return ["derived.op must be ratio, share, growth, rank or lever_scenario"], None
    allowed = {"op", "of", "over", "from_period", "to_period", "baseline_period", "ticket_pct", "spend_pct", "mix",
               "conversion_scenario_id"}
    errs = [f"unknown derived keys: {sorted(set(d) - allowed)}"] if set(d) - allowed else []
    out: dict[str, Any] = {"op": d["op"]}
    for k in ("of", "over", "from_period", "to_period"):
        if k in d:
            if not isinstance(d[k], str) or len(d[k]) > 40:
                errs.append(f"derived.{k} must be a short string")
            else:
                out[k] = d[k]
    if "baseline_period" in d:
        if d["baseline_period"] not in ("pre_2023_06", "from_2023_06"):
            errs.append("derived.baseline_period is not valid")
        else:
            out["baseline_period"] = d["baseline_period"]
    for k in ("ticket_pct", "spend_pct"):
        if k in d:
            v = d[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not -50 <= v <= 100:
                errs.append(f"derived.{k} must be a number from -50 to 100")
            else:
                out[k] = v
    if "mix" in d:
        mx = d["mix"]
        ok = isinstance(mx, dict) and mx.get("from_industry") in C.INDUSTRIES and mx.get("to_industry") in C.INDUSTRIES \
            and mx.get("from_industry") != mx.get("to_industry") and isinstance(mx.get("points"), (int, float)) \
            and not isinstance(mx.get("points"), bool) and 1 <= mx["points"] <= 50
        if not ok:
            errs.append("derived.mix needs two different catalog industries and 1 to 50 points")
        else:
            out["mix"] = {"from_industry": mx["from_industry"], "to_industry": mx["to_industry"], "points": mx["points"]}
    if "conversion_scenario_id" in d:
        if not isinstance(d["conversion_scenario_id"], str) or not SCENARIO.fullmatch(d["conversion_scenario_id"]):
            errs.append("derived.conversion_scenario_id is not valid")
        else:
            out["conversion_scenario_id"] = d["conversion_scenario_id"]
    return errs, out


# ---------------------------------------------------------------------------- #
# Time (§2.1 "How Kimi fills it", §2.3 rule 4)                                  #
# ---------------------------------------------------------------------------- #

def _months(a: str, b: str) -> list[str]:
    ya, ma = map(int, a.split("-"))
    yb, mb = map(int, b.split("-"))
    out = []
    while (ya, ma) <= (yb, mb):
        out.append(f"{ya:04d}-{ma:02d}")
        ma += 1
        if ma == 13:
            ya, ma = ya + 1, 1
    return out


def _quarter_months(qtxt: str) -> tuple[str, str]:
    y, qn = qtxt.split("-Q")
    first = (int(qn) - 1) * 3 + 1
    return f"{y}-{first:02d}", f"{y}-{first + 2:02d}"


def resolve_time(t: dict, ctx: Context) -> dict:
    """{'from','to'} months (clipped to the window) and/or 'period_code'. Raises
    OutOfScope(beyond_data_complete_through) for anything after the data."""
    dct, ws = ctx.data_complete_through, ctx.window_start_month
    lo, hi, period = ws, dct, None
    asked = None
    rel = t.get("relative")
    if rel == "latest_month":
        lo = hi = dct
    elif rel == "latest_quarter":
        y, m = map(int, dct.split("-"))
        lo, hi = _quarter_months(f"{y}-Q{(m - 1) // 3 + 1}")
    elif rel == "latest_year":
        lo, hi = f"{dct[:4]}-01", f"{dct[:4]}-12"
    if "year" in t:
        y = int(t["year"])
        lo, hi = max(lo, f"{y:04d}-01"), min(hi, f"{y:04d}-12") if hi != dct else f"{y:04d}-12"
        asked = str(y)
        if f"{y:04d}-01" > dct:
            raise OutOfScope("beyond_data_complete_through", {"asked": asked})
    if "quarter" in t:
        a, b = _quarter_months(t["quarter"])
        asked = t["quarter"]
        if a > dct:
            raise OutOfScope("beyond_data_complete_through", {"asked": asked})
        lo, hi = max(lo, a), b if hi in (dct, f"{dct[:4]}-12") else min(hi, b)
    if "from" in t:
        lo = max(lo, t["from"]) if "year" in t or "quarter" in t else t["from"]
        if t["from"] > dct:
            raise OutOfScope("beyond_data_complete_through", {"asked": t["from"]})
    if "to" in t:
        if t["to"] > dct and "from" not in t:
            raise OutOfScope("beyond_data_complete_through", {"asked": t["to"]})
        hi = t["to"] if "year" not in t and "quarter" not in t else min(hi, t["to"])
    if "period_code" in t and t["period_code"] != "full":
        period = t["period_code"]
    lo, hi = max(lo, ws), min(hi, dct)
    explicit = any(k in t for k in ("from", "to", "year", "quarter")) or rel in ("latest_month", "latest_quarter",
                                                                                  "latest_year")
    if lo > hi:
        raise CompileError([f"the time range {lo}..{hi} has no data (window {ws}..{dct})"])
    months = _months(lo, hi)
    if len(months) > 34:
        months = months[-34:]
        lo = months[0]
    return {"from": lo, "to": hi, "period_code": period, "explicit": explicit, "months": months,
            "single_month": lo == hi and explicit}


def check_beyond(spec: dict, ctx: Context) -> None:
    t = (spec.get("filters") or {}).get("time") or {}
    try:
        resolve_time(t, ctx)
    except CompileError:
        pass
    d = (spec.get("derived") or [None])[0] or {}
    for k in ("from_period", "to_period"):
        v = d.get(k)
        if isinstance(v, str) and ((MONTH.fullmatch(v) and v > ctx.data_complete_through) or
                                   (YEAR_TEXT.fullmatch(v) and v > ctx.data_complete_through[:4])):
            raise OutOfScope("beyond_data_complete_through", {"asked": v})


# ---------------------------------------------------------------------------- #
# Compile                                                                       #
# ---------------------------------------------------------------------------- #

def route_deterministic(spec: dict, role: str, ctx: Context) -> None:
    """§3: the compiler applies these even when Kimi said `answer`."""
    metrics = [C.METRICS[m] for m in spec.get("metrics") or [] if m in C.METRICS]
    if any(m.status == "not_available" for m in metrics):
        raise OutOfScope("discounts_billing")
    lines = set((spec.get("filters") or {}).get("mrr_line") or [])
    if lines & C.MRR_LINES_NA or "discount" in set((spec.get("filters") or {}).get("driver") or []):
        raise OutOfScope("discounts_billing")
    cats = set((spec.get("filters") or {}).get("spend_category") or [])
    if any(m.status == "hr" for m in metrics) or cats & C.HR_CATEGORIES:
        # §2.3 rule 7: Finance only, and only in a Finance-only workgroup, which does not exist:
        # hr_restricted for every role until it does.
        raise OutOfScope("hr_restricted", {"role": role})
    check_beyond(spec, ctx)


def compile_spec(spec: dict, role: str, ctx: Context) -> Compiled:
    if role not in C.ROLES:
        raise OutOfScope("hr_restricted", {"role": role})
    if spec.get("intent") == "out_of_scope":
        raise OutOfScope(spec["out_of_scope"]["reason_code"], spec["out_of_scope"].get("slots"))
    route_deterministic(spec, role, ctx)
    metrics = [C.METRICS[m] for m in spec["metrics"]]
    derived = (spec.get("derived") or [None])[0]
    domains = {m.domain for m in metrics}
    if len(domains) > 1:
        raise CompileError(["all metrics of one question must belong to one domain"])
    if derived and derived["op"] == "lever_scenario":
        return _compile_lever(spec, ctx)
    if metrics[0].status == "dq" or spec["domain"] == "dq":
        if any(m.status != "dq" for m in metrics):
            raise CompileError(["dq metrics cannot be combined with gold metrics"])
        return _compile_dq(spec, ctx)
    return _compile_sql(spec, ctx)


def _growth_dim(v: str) -> str | None:
    if v in ("pre_2023_06", "from_2023_06"):
        return "period"
    if MONTH.fullmatch(v):
        return "month"
    if QUARTER.fullmatch(v):
        return "quarter"
    if HALF.fullmatch(v):
        return "cohort_half"
    if YEAR_TEXT.fullmatch(v):
        return "year"
    return None


def _time_mode_ok(src: C.Source, binding: C.Binding, t: dict, dims: list[str]) -> bool:
    explicit_months = t["explicit"]
    if src.time == "month":
        return "cohort_half" not in dims
    if src.time == "period":
        return not explicit_months and not (set(dims) & {"month", "quarter", "year", "cohort_half"})
    if src.time == "cohort":
        return not explicit_months and t["period_code"] is None and not (set(dims) & {"month", "quarter", "year", "period"})
    if src.time == "funnel_period":
        n = len(set(dims) & {"year", "quarter", "period", "month"})
        return "month" not in dims and n <= 1 and not (explicit_months and not
                                                     (set(dims) & {"year", "quarter"}))
    return not explicit_months and t["period_code"] is None and not (set(dims) & {"month", "quarter", "year", "period"})


def _choose(metrics: list[C.Metric], dims: list[str], filters: dict, t: dict) -> tuple[C.Source, dict]:
    used_filters = {k for k in filters if k not in ("time",)}
    candidates: list[str] = []
    for m in metrics:
        for b in m.bindings:
            if b.source not in candidates:
                candidates.append(b.source)
    for sid in candidates:
        src = C.SOURCES[sid]
        chosen = {}
        for m in metrics:
            for b in m.bindings:
                if b.source != sid:
                    continue
                if not set(dims) <= set(src.dims):
                    continue
                if not used_filters - {"scenario_id"} <= set(src.filters):
                    continue
                if "scenario_id" in used_filters and "scenario_id" not in src.filters:
                    continue
                if not _time_mode_ok(src, b, t, dims):
                    continue
                if "month" in b.needs and "month" not in dims and not t["single_month"]:
                    continue
                chosen[m.id] = b
                break
        if len(chosen) == len(metrics):
            return src, chosen
    raise CompileError([f"no single catalog source serves {[m.id for m in metrics]} by {dims or 'total'} "
                        f"with these filters; ask for fewer metrics or another cut"])


def _won_sub(expr: str, wd: str) -> str:
    return expr.replace("{won}", "won_count" if wd == "first_payment" else "won_new_logo_count") \
        .replace("{rev}", "new_revenue_value" if wd == "first_payment" else "new_revenue_new_logo_value")


class _Params:
    def __init__(self):
        self.values: list[str] = []

    def add(self, v: Any) -> exp.Expression:
        """A validated value as an Athena execution parameter (its SQL literal text)."""
        if isinstance(v, bool):
            raise ValueError("no booleans")
        if isinstance(v, int):
            self.values.append(str(v))
        else:
            s = str(v)
            if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", s):
                raise ValueError("parameter outside the validated alphabet")
            self.values.append("'" + s + "'")
        return exp.Placeholder()


def _tbl(name: str, alias: str, ctx: Context, is_view: bool) -> str:
    snap = ctx.snapshots.get(name)
    version = f" FOR VERSION AS OF {int(snap)}" if snap and not is_view else ""
    return f"{C.GOLD_DB}.{name}{version} AS {alias}"


def _compile_sql(spec: dict, ctx: Context) -> Compiled:
    metrics = [C.METRICS[m] for m in spec["metrics"]]
    filters = spec["filters"]
    wd = spec["won_definition"]
    derived = (spec.get("derived") or [None])[0]
    t = resolve_time(filters.get("time") or {}, ctx)
    dims = list(spec["dimensions"])
    if derived and derived["op"] in ("ratio", "share", "growth", "rank"):
        of = derived.get("of")
        if derived["op"] in ("ratio", "share", "growth", "rank") and of not in spec["metrics"]:
            raise CompileError(["derived.of must be one of the spec's metrics"])
        if derived["op"] == "ratio" and derived.get("over") not in spec["metrics"]:
            raise CompileError(["ratio needs derived.over to be one of the spec's metrics"])
        if derived["op"] == "share":
            over = derived.get("over")
            if over not in dims:
                if over in C.DIMENSIONS and len(dims) < 2:
                    dims.append(over)
                else:
                    raise CompileError(["share needs derived.over to be a catalog dimension of the spec"])
            if over in C.TIME_DIMS and any(b == "stock" for b in [x.kind for m in metrics for x in m.bindings]):
                raise CompileError(["a stock (MRR, customers) is never shared or summed over months"])
        if derived["op"] == "growth":
            fp, tp = derived.get("from_period"), derived.get("to_period")
            gdim = _growth_dim(fp or "")
            if not fp or not tp or gdim is None or gdim != _growth_dim(tp):
                raise CompileError(["growth needs from_period and to_period of the same kind (period code, year, "
                                    "quarter, month or cohort half)"])
            if fp == tp:
                raise CompileError(["growth needs two different periods"])
            if gdim not in dims:
                dims.append(gdim)
            if gdim in TIME_GROWTH_FILTER:
                filters = dict(filters)
                lo, hi = sorted([fp, tp])
                tt = dict(filters.get("time") or {})
                tt.pop("period_code", None)
                if gdim == "month":
                    tt.update({"from": lo, "to": hi})
                elif gdim == "quarter":
                    tt.update({"from": _quarter_months(lo)[0], "to": _quarter_months(hi)[1]})
                elif gdim == "year":
                    tt.update({"from": f"{lo}-01", "to": f"{hi}-12"})
                tt.pop("year", None)
                tt.pop("quarter", None)
                tt.pop("relative", None)
                filters["time"] = tt
                t = resolve_time(tt, ctx)
    src, chosen = _choose(metrics, dims, filters, t)
    stock_on_customers = src.customer_grain and any(b.kind == "stock" for b in chosen.values())
    if stock_on_customers and set(dims) & {"quarter", "year"}:
        raise CompileError(["a customer-level stock is answered per month or for one month, not per quarter/year"])
    # implicit grain dims (pre-aggregated rows)
    single = {k for k, v in filters.items() if isinstance(v, list) and len(v) == 1}
    for g in src.grain:
        if g not in dims and not (g == "period" and t["period_code"]) and g not in single and \
                not (g == "industry" and "industry" in single) and not (g == "customer_scope" and "customer_scope" in filters):
            dims.append(g)
    params = _Params()
    a = src.alias
    select: list[str] = []
    meta: dict[str, dict] = {}
    group: list[str] = []
    for d in dims:
        code, label = src.dims[d]
        if src.time == "funnel_period" and d in ("year", "quarter", "period"):
            code = "f.period_id"
        select.append(f"{code} AS {d}")
        group.append(code)
        meta[d] = {"dim": d}
        if label:
            select.append(f"MAX({label}) AS {d}_label")
            meta[f"{d}_label"] = {"dim": d, "label": True}
    seen_cols = set(meta)
    line_filters = {b.line_filter for b in chosen.values() if b.line_filter}
    if len(line_filters) > 1:
        raise CompileError(["these metrics cannot be read together; ask for them one at a time"])
    for m in metrics:
        b = chosen[m.id]
        for i, (col, expr) in enumerate(b.cols):
            if col in seen_cols:
                continue
            seen_cols.add(col)
            select.append(f"{_won_sub(expr, wd)} AS {col}")
            meta[col] = {"metric": m.id, "fmt": m.fmt if i == 0 else _aux_fmt(col), "unit": m.unit if i == 0 else
                         ("count" if _aux_fmt(col) == "int" else m.unit), "main": i == 0, "kind": b.kind}
        if b.customers and "customers" not in seen_cols:
            seen_cols.add("customers")
            select.append(f"{b.customers} AS customers")
            meta["customers"] = {"aux": True, "fmt": "int", "unit": "count"}
    if src.id in ("wmi", "li", "ip", "fp", "fm") and "is_low_n" not in seen_cols:
        low = {"wmi": "w", "li": "li", "ip": "ip", "fp": "f", "fm": "f"}[src.id]
        select.append(f"BOOL_OR({low}.is_low_n) AS is_low_n")
        meta["is_low_n"] = {"aux": True}
    where: list[str] = list(src.mandatory)
    where += list(line_filters)
    if src.time == "month" or any(j[1] == "m" for j in src.joins):
        where.append(f"m.month_key <= {ctx.dct_key}")
        if any(b.reportable for b in chosen.values()):
            where.append("m.is_won_reportable = true")
    if src.won_col:
        where.append(f"{src.won_col} = {params.add(wd).sql()}")
    # time filters
    if src.time == "month":
        months = t["months"]
        if stock_on_customers and "month" not in dims:
            months = [months[-1]]  # a stock over a range is its last month (§2.3 rule 6)
        if t["explicit"] or stock_on_customers:
            where.append(f"m.month BETWEEN {params.add(months[0]).sql()} AND {params.add(months[-1]).sql()}")
        if t["period_code"]:
            where.append(f"m.sm_regime = {params.add(t['period_code']).sql()}")
    elif src.time == "period":
        col = src.dims["period"][0]
        if t["period_code"]:
            where.append(f"{col} = {params.add(t['period_code']).sql()}")
    elif src.time == "funnel_period":
        ptype = "year" if ("year" in dims or "year" in (filters.get("time") or {})) else \
            "quarter" if ("quarter" in dims or "quarter" in (filters.get("time") or {})) else \
            "sm_regime" if ("period" in dims or t["period_code"]) else "full"
        where.append(f"f.period_type = {params.add(ptype).sql()}")
        tf = filters.get("time") or {}
        if "year" in tf:
            where.append(f"f.period_id = {params.add(str(tf['year'])).sql()}")
        elif "quarter" in tf:
            where.append(f"f.period_id = {params.add(tf['quarter']).sql()}")
        elif t["period_code"]:
            where.append(f"f.period_id = {params.add(t['period_code']).sql()}")
        elif ptype == "full":
            where.append("f.period_id = 'full'")
        where.append(f"f.scenario_id = {params.add(filters.get('scenario_id', 'base')).sql()}")
    if src.id == "fm":
        where.append(f"f.scenario_id = {params.add(filters.get('scenario_id', 'base')).sql()}")
    if src.id == "sens":
        where.append(f"r.scenario_id = {params.add(filters.get('scenario_id', 'base')).sql()}")
    if src.id == "ip" and "customer_scope" not in filters and "customer_scope" not in dims:
        where.append("ip.customer_scope = 'all'")
    if src.id == "corr":
        where.append("cs.method IN ('diff', 'within_regime', 'level')")
    for k, v in filters.items():
        if k in ("time", "scenario_id"):
            continue
        col = src.filters.get(k)
        if col is None:
            continue
        vals = v if isinstance(v, list) else [v]
        if k == "industry" and ("UNKNOWN" in vals or "UNMAPPED" in vals):
            vals = sorted(set(vals) | {"UNKNOWN", "UNMAPPED"})
        where.append(f"{col} IN ({', '.join(params.add(x).sql() for x in vals)})")
    if src.id == "corr":
        select.insert(0, "cs.method AS method")
        group.insert(0, "cs.method")
        dims.insert(0, "method")
        meta = {"method": {"dim": "method"}, **meta}
    order: list[str] = []
    limit = MAX_ROWS + 1
    sort = spec.get("sort")
    in_code = bool(derived)
    main_cols = {m.id: chosen[m.id].cols[0][0] for m in metrics}
    if sort and not in_code:
        by = main_cols.get(sort["by"]) or (sort["by"] if sort["by"] in dims else None)
        if by:
            order.append(f"{by} {sort['dir'].upper()}")
            limit = spec["limit"]
    for d in dims:
        if d in ("month", "quarter", "year", "period", "cohort_half", "method"):
            order.append(d)
    if not order and dims:
        order.append(dims[0])
    from_sql = _tbl(src.table, a, ctx, src.view)
    for (jt, ja, on, jv) in src.joins:
        from_sql += f" JOIN {_tbl(jt, ja, ctx, jv)} ON {on}"
    if src.extra_from:
        from_sql += " " + src.extra_from
    sql = f"SELECT {', '.join(select)} FROM {from_sql}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if group:
        sql += " GROUP BY " + ", ".join(group)
    if order:
        sql += " ORDER BY " + ", ".join(order)
    sql += f" LIMIT {int(limit)}"
    final = guard(sql, len(params.values))
    columns = list(meta)
    comp = Compiled(kind="sql", spec=spec, spec_hash=spec_hash(spec), metrics=spec["metrics"], dims=dims,
                    source=src.id, sql=final, params=params.values,
                    sql_hash=hashlib.sha256((final + "|" + json.dumps(params.values)).encode()).hexdigest()[:32],
                    columns=columns, meta=meta, time=t, derived=derived, sort=sort, limit=spec["limit"],
                    won_definition=wd)
    _decorate(comp, ctx)
    return comp


TIME_GROWTH_FILTER = {"month", "quarter", "year"}


def _aux_fmt(col: str) -> str:
    if col.endswith("_count") or col.endswith("_eligible") or col in ("customers", "signals", "tests_with_r",
                                                                      "run_rate_customers", "paying_customers",
                                                                      "line_events") or col.endswith("_events"):
        return "int"
    if col == "expected_by_chance":
        return "dec1"
    if col.endswith("_value"):
        return "money"
    if col.endswith("_pct_change_per_point"):
        return "pct1"
    return "dec1"


def guard(sql: str, n_params: int | None = None) -> str:
    """Parse the compiled SQL back: one SELECT, allowlisted gold objects only,
    customer_id only inside an aggregate, a LIMIT. Returns the sqlglot-rendered SQL."""
    trees = sqlglot.parse(sql, read="trino")
    if len(trees) != 1 or not isinstance(trees[0], exp.Select):
        raise CompileError(["internal: the compiled query is not exactly one SELECT"])
    tree = trees[0]
    for node in tree.find_all(exp.Insert, exp.Delete, exp.Update, exp.Create, exp.Drop, exp.Command, exp.Merge):
        raise CompileError([f"internal: {type(node).__name__} is never allowed"])
    for tbl in tree.find_all(exp.Table):
        if tbl.name == "" and isinstance(tbl.this, exp.Unnest):
            continue
        if tbl.db != C.GOLD_DB or tbl.name not in C.ALLOWED_TABLES:
            raise CompileError([f"internal: {tbl.db}.{tbl.name} is not a governed object"])
    for col in tree.find_all(exp.Column):
        if col.name == "customer_id":
            agg = col.find_ancestor(exp.AggFunc)
            if agg is None or col.find_ancestor(exp.Where, exp.Group, exp.Order, exp.Having):
                raise CompileError(["internal: customer_id outside an aggregate"])
    if not tree.args.get("limit"):
        raise CompileError(["internal: missing LIMIT"])
    if n_params is not None and len(list(tree.find_all(exp.Placeholder))) != n_params:
        raise CompileError(["internal: parameter count mismatch"])
    return tree.sql(dialect="trino")


# ---------------------------------------------------------------------------- #
# Evidence, caveats, kpi_ids, chart (§2.3 rule 8, §1.6)                         #
# ---------------------------------------------------------------------------- #

def _weakest(levels: list[str]) -> str:
    return max(levels, key=C.EVIDENCE_ORDER.index) if levels else "observado"


def _decorate(c: Compiled, ctx: Context) -> None:
    metrics = [C.METRICS[m] for m in c.metrics]
    spec = c.spec
    filters = spec.get("filters") or {}
    caveats: list[str] = []
    levels = [m.evidence for m in metrics]

    def add(cid: str) -> None:
        if cid not in caveats:
            caveats.append(cid)
    if any(m.unit == "money" for m in metrics):
        add("C-CUR")
    if any(m.domain == "mrr" for m in metrics):
        add("C-MRR-PROXY")
        if c.time.get("months") and (c.kind == "sql" and c.time["months"][-1] > ctx.churn_confirmed_through and
                                     (c.time.get("explicit") or not c.time.get("explicit"))):
            add("C-PROV")
    stages = set(filters.get("funnel_stage") or [])
    if any(m.id in ("acq.funnel_stage_count", "acq.funnel_cost_per_stage", "acq.rate_sensitivity") for m in metrics) \
            or (stages and stages != {"WON"}):
        add("C-FUNNEL")
        levels.append("supuesto")
    for m in metrics:
        for cv in m.caveats:
            add(cv)
    if "period" in c.dims or (c.time or {}).get("period_code") or \
            (c.derived and _growth_dim(c.derived.get("from_period") or "") == "period"):
        add("C-REGIME")
    if "acq.run_rate_per_won" in c.metrics:
        last_won = (c.time or {}).get("period_code") in (None, "from_2023_06") or "cohort_half" in c.dims
        if not last_won:
            caveats.remove("C-IMMATURE")
    if "spend_group" in c.dims or "people" in set(filters.get("spend_group") or []):
        add("C-PEOPLE")
    if c.kind == "sql" and (c.time or {}).get("explicit") or set(c.dims) & {"year", "quarter"}:
        if _partials(c, ctx):
            add("C-PARTIAL")
    if c.derived and c.derived.get("op") == "lever_scenario":
        moved = []
        if c.derived.get("mix") or c.derived.get("ticket_pct"):
            add("C-MIX")
            moved.append("observado")
        if c.derived.get("spend_pct"):
            moved.append("no probado")
        levels = moved or ["observado"]
    c.caveats = [x for x in C.CAVEAT_ORDER if x in caveats]
    if "C-CUR" in c.caveats and len(c.caveats) > 1:
        c.caveats = [x for x in c.caveats if x != "C-CUR"] + ["C-CUR"]
    c.evidence = _weakest(levels)
    c.kpi_ids = _kpi_ids(c)
    ctype = (spec.get("chart") or {}).get("type") or "table"
    if ctype == "kpi":
        ctype = "table"
    if ctype == "table" and c.dims and c.dims[0] in ("month", "quarter", "year") and (spec.get("chart") or {}).get("type") != "table":
        ctype = "line"
    c.chart_type = ctype
    c.title_es = _title(c)


def _partials(c: Compiled, ctx: Context) -> list[tuple[str, int]]:
    """Partial years/quarters inside the result range: (label, Won months)."""
    first_won = _months(ctx.window_start_month, ctx.window_start_month)[0]
    months = [m for m in (c.time or {}).get("months", []) if m > first_won]
    out = []
    for y in sorted({m[:4] for m in months}):
        n = len([m for m in _months(f"{y}-01", f"{y}-12") if first_won < m <= ctx.data_complete_through])
        if n < 12 and ("year" in c.dims or "year" in ((c.spec.get("filters") or {}).get("time") or {})
                       or (c.time or {}).get("months", [""])[0][:4] == y and len(months) >= n > 0 and
                       "quarter" not in c.dims and "month" not in c.dims):
            out.append((y, n))
    return out


def partial_text(c: Compiled, ctx: Context) -> str:
    parts = _partials(c, ctx)
    if not parts:
        return ""
    return " ".join(f"{y} tiene {n} meses de datos." for y, n in parts)


def _kpi_ids(c: Compiled) -> list[str]:
    out = []
    f = c.spec.get("filters") or {}
    for mid in c.metrics:
        k = C.METRICS[mid].kpi_id
        if "<dataset_id>" in k:
            for ds in f.get("dataset_id") or list(C.DATASETS):
                kk = k.replace("<dataset_id>", ds)
                if "<rule_id>" in kk:
                    for r in f.get("rule_id") or []:
                        out.append(kk.replace("<rule_id>", r))
                else:
                    out.append(kk)
            continue
        if "<line>" in k:
            for ln in f.get("mrr_line") or []:
                out.append(k.replace("<line>", ln))
            if not f.get("mrr_line"):
                out.append("mrr.why.hero")
            continue
        if "<driver>" in k:
            for d in f.get("driver") or ["behaviour", "pricing", "timing"]:
                out.append(k.replace("<driver>", d))
            continue
        if mid == "acq.run_rate_per_won":
            k = "acq.lost.ticket_by_industry" if "industry" in c.dims else \
                "acq.lost.ticket_by_cohort" if "cohort_half" in c.dims else k
        out.append(k)
    seen, uniq = set(), []
    for k in out:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    return uniq[:6]


def _title(c: Compiled) -> str:
    names = [C.METRICS[m].name_es for m in c.metrics]
    head = names[0][:1].upper() + names[0][1:]
    if len(names) > 1:
        head += " y " + names[1]
    by = [C.DIMENSIONS.get(d, d) for d in c.dims if d in C.DIMENSIONS]
    title = head + (" por " + " y ".join(by) if by else "")
    return title[:80]


# ---------------------------------------------------------------------------- #
# DQ (§1.3): the snapshot of the same silver run, a lookup in code              #
# ---------------------------------------------------------------------------- #

DQ_DATASET_METRICS = {"dq.row_compliance_pct": "row_compliance_pct", "dq.rows_read": "rows_read",
                      "dq.rows_excluded": "rows_excluded", "dq.rows_flagged": "rows_flagged",
                      "dq.rules_failing": "rules_failing"}
DQ_RULE_METRICS = {"dq.rule_failed_count": "failed", "dq.rule_compliance_pct": "compliance_pct",
                   "dq.rule_status": "status"}


def _compile_dq(spec: dict, ctx: Context) -> Compiled:
    mids = spec["metrics"]
    fam = {"dataset" if m in DQ_DATASET_METRICS else "rule" if m in DQ_RULE_METRICS else "trend" for m in mids}
    if len(fam) > 1:
        raise CompileError(["dataset metrics, rule metrics and the trend are separate questions"])
    family = fam.pop()
    f = spec["filters"]
    t = f.get("time") or {}
    if set(t) - {"relative"} or t.get("relative") not in (None, "latest_run", "latest_month", "full_window"):
        raise CompileError(["data-quality answers are per run: use time.relative = latest_run"])
    if family == "rule":
        dims = ["rule", "dataset"]
        cols = ["rule", "rule_title", "dataset", "dataset_label"] + [DQ_RULE_METRICS[m] for m in mids]
        if "dq.rule_status" not in mids:
            cols.append("status")
    elif family == "dataset":
        dims = ["dataset"]
        cols = ["dataset", "dataset_label"] + [DQ_DATASET_METRICS[m] for m in mids]
    else:
        dims = ["run", "dataset"]
        cols = ["run_id", "as_of_month", "dataset", "dataset_label", "row_compliance_pct"]
    meta = {}
    for col in cols:
        mid = next((m for m in mids if DQ_DATASET_METRICS.get(m) == col or DQ_RULE_METRICS.get(m) == col), None)
        if mid:
            meta[col] = {"metric": mid, "fmt": C.METRICS[mid].fmt, "unit": C.METRICS[mid].unit, "main": True}
        elif col == "row_compliance_pct":
            meta[col] = {"metric": "dq.compliance_trend", "fmt": "pct_dq", "unit": "pct", "main": True}
        else:
            meta[col] = {"dim": col}
    comp = Compiled(kind="dq", spec=spec, spec_hash=spec_hash(spec), metrics=mids, dims=dims, source="dq_snapshot",
                    columns=cols, meta=meta, sort=spec.get("sort"), limit=spec["limit"],
                    plan={"family": family, "dq_run_id": ctx.dq_run_id})
    comp.sql_hash = hashlib.sha256(("dq|" + _canon(spec) + "|" + ctx.dq_run_id).encode()).hexdigest()[:32]
    comp.time = {"months": []}
    _decorate(comp, ctx)
    comp.chart_type = "bar" if family != "trend" else "line"
    if (spec.get("chart") or {}).get("type") == "table":
        comp.chart_type = "table"
    return comp


def run_dq(comp: Compiled, snapshot: dict) -> list[list]:
    """Rows of a DQ question from the DQ serving snapshot (values as exact strings)."""
    f = comp.spec["filters"]
    family = comp.plan["family"]
    dss = set(f.get("dataset_id") or C.DATASETS)
    rows: list[list] = []
    if family == "dataset":
        for d in snapshot.get("datasets", []):
            if d["dataset_id"] in dss:
                rows.append([d["dataset_id"], C.DATASETS.get(d["dataset_id"], d["dataset_id"])] +
                            [_s(d.get(DQ_DATASET_METRICS[m])) for m in comp.metrics])
    elif family == "rule":
        statuses = set(f.get("rule_status") or ["pass", "warn", "fail", "na"])
        rules = set(f.get("rule_id") or [])
        for r in snapshot.get("rules", []):
            if rules and r["rule_id"] not in rules:
                continue
            for ds, res in (r.get("results") or {}).items():
                if ds not in dss or res.get("status") not in statuses:
                    continue
                row = [r["rule_id"], r.get("title", ""), ds, C.DATASETS.get(ds, ds)]
                row += [_s(res.get(DQ_RULE_METRICS[m])) for m in comp.metrics]
                if "dq.rule_status" not in comp.metrics:
                    row.append(res.get("status"))
                rows.append(row)
    else:
        for tr in snapshot.get("trend", [])[-24:]:
            for ds in sorted(dss):
                if ds in tr:
                    rows.append([tr["run_id"], tr.get("as_of_month"), ds, C.DATASETS.get(ds, ds), _s(tr[ds])])
    sort = comp.sort
    if sort and family != "trend":
        mains = [c for c in comp.columns if comp.meta.get(c, {}).get("main")]
        by = next((DQ_DATASET_METRICS.get(sort["by"]) or DQ_RULE_METRICS.get(sort["by"]) for _ in [0]
                   if sort["by"] in DQ_DATASET_METRICS or sort["by"] in DQ_RULE_METRICS), None) or (mains[0] if mains else None)
        if by in comp.columns and by != "status":
            i = comp.columns.index(by)
            from decimal import Decimal
            rows.sort(key=lambda r: Decimal(r[i]) if r[i] not in (None, "") else Decimal(0),
                      reverse=sort["dir"] == "desc")
            rows = rows[: comp.limit]
    return rows[:MAX_ROWS]


def _s(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float):
        from decimal import Decimal
        return format(Decimal(repr(v)).normalize(), "f")
    return str(v)


# ---------------------------------------------------------------------------- #
# lever_scenario (§2.2, gold model §16.3): one SELECT, arithmetic in code       #
# ---------------------------------------------------------------------------- #

def _compile_lever(spec: dict, ctx: Context) -> Compiled:
    d = spec["derived"][0]
    if d.get("conversion_scenario_id"):
        raise OutOfScope("outside_catalog", {"falta": "un escenario de conversión por voz",
                                             "closest": "el planificador de la página de Adquisición"})
    if not any(k in d for k in ("mix", "ticket_pct", "spend_pct")):
        raise CompileError(["lever_scenario needs mix, ticket_pct or spend_pct"])
    base = d.get("baseline_period", "from_2023_06")
    params = _Params()
    wd = spec["won_definition"]
    mix = d.get("mix")
    sel = ("SELECT p.period_code AS period, MAX(p.won_per_month) AS won_per_month, "
           "MAX(p.run_rate_mrr_per_won_value) AS run_rate_value, MAX(p.new_mrr_per_month_value) AS new_mrr_per_month_value, "
           "MAX(p.cost_per_won_value) AS cost_per_won_value, MAX(p.payback_months) AS payback_months")
    frm = f" FROM {_tbl('agg_acq_lever_period', 'p', ctx, False)}"
    if mix:  # placeholders are positional: add them in the order they appear in the text
        sel += (", MAX(li.run_rate_mrr_per_won_value) FILTER (WHERE i.industry_code = "
                f"{params.add(mix['from_industry']).sql()}) AS from_industry_value, "
                "MAX(li.run_rate_mrr_per_won_value) FILTER (WHERE i.industry_code = "
                f"{params.add(mix['to_industry']).sql()}) AS to_industry_value, "
                "BOOL_OR(li.is_low_n) AS is_low_n")
        frm += (f" JOIN {_tbl('agg_acq_lever_industry', 'li', ctx, False)} ON li.period_code = p.period_code "
                f"AND li.won_definition = p.won_definition JOIN {_tbl('dim_industry', 'i', ctx, False)} "
                "ON li.industry_key = i.industry_key")
    where = [f"p.won_definition = {params.add(wd).sql()}", f"p.period_code = {params.add(base).sql()}"]
    group = " GROUP BY p.period_code"
    sql = guard(sel + frm + " WHERE " + " AND ".join(where) + group + " LIMIT 2", len(params.values))
    cols = ["period", "won_per_month", "run_rate_value", "new_mrr_per_month_value", "cost_per_won_value",
            "payback_months"] + (["from_industry_value", "to_industry_value", "is_low_n"] if mix else [])
    comp = Compiled(kind="lever", spec=spec, spec_hash=spec_hash(spec), metrics=spec["metrics"], dims=["metric"],
                    source="lp", sql=sql, params=params.values,
                    sql_hash=hashlib.sha256((sql + json.dumps(params.values)).encode()).hexdigest()[:32],
                    columns=cols, meta={}, derived=d, limit=spec["limit"], won_definition=wd,
                    plan={"baseline": base})
    comp.time = {"months": [], "period_code": base}
    _decorate(comp, ctx)
    comp.kpi_ids = ["acq.plan.won", "acq.plan.new_mrr", "acq.plan.payback"] + \
        (["acq.lever.mix"] if mix else []) + (["acq.lever.ticket"] if d.get("ticket_pct") else []) + \
        (["acq.lever.spend"] if d.get("spend_pct") else [])
    comp.chart_type = "table"
    comp.title_es = "Escenario de palancas sobre " + ("el periodo actual" if base == "from_2023_06" else
                                                     "el periodo anterior a junio de 2023")
    return comp
