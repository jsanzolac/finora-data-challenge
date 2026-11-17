"""After the query: derived operations in code (exact decimals, HALF_UP), small cells,
and the spoken summary (docs/semantic_layer.md §2.2, §2.3 rules 3, 4, 6, 10).

The summary is a template per spec shape (kpi / comparison / ranking / trend / list),
filled with values formatted by code (fmt.display). It cites at most 5 values, never a
money value from fewer than 5 customers, never an HR amount, and names the evidence
level when it is not `observado`. `Summary.displays` is every figure the template put
in; the number check (numbers.check_summary) verifies the text against it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from . import catalog as C
from . import fmt as F
from .compiler import Compiled, Context, partial_text

MAX_SPOKEN = 5
SMALL_CELL = 5
NOUN = {"acq.won_count": ("cliente nuevo", "clientes nuevos"), "mrr.paying_customers": ("cliente pagando", "clientes pagando"),
        "mrr.line_events": ("movimiento", "movimientos"), "dq.rows_excluded": ("fila excluida", "filas excluidas"),
        "dq.rows_read": ("fila leída", "filas leídas"), "dq.rows_flagged": ("fila marcada", "filas marcadas"),
        "dq.rules_failing": ("regla con hallazgos", "reglas con hallazgos")}


def noun(metric_id: str, value) -> str:
    n = NOUN.get(metric_id)
    if not n:
        return ""
    v = F.dec(value)
    return n[0] if v is not None and abs(v) == 1 else n[1]
RULE_GLOSS_ES = {"SQ-02": "registro vacío", "SB-10": "gasto negativo", "SB-11": "pagos repartidos de forma desigual"}


@dataclass
class Table:
    columns: list
    rows: list
    meta: dict
    chart: dict


@dataclass
class Summary:
    text: str
    displays: list = field(default_factory=list)
    source: str = "template"
    caveats_es: list = field(default_factory=list)


def _d(v: Any) -> Decimal | None:
    return F.dec(v)


def _q(v: Decimal, places: int) -> Decimal:
    return v.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _s(v: Decimal | None) -> str | None:
    return None if v is None else format(v, "f")


# ---------------------------------------------------------------------------- #
# Derived operations (§2.2) and the table the browser gets                       #
# ---------------------------------------------------------------------------- #

def to_table(comp: Compiled, header: list[str], rows: list[list[Any]]) -> Table:
    if comp.kind == "lever":
        return _lever_table(comp, header, rows)
    cols = [c.lower() for c in header] if header else list(comp.columns)
    meta = {c: dict(comp.meta.get(c, {})) for c in cols}
    data = [list(r) for r in rows]
    if "customers" in cols:
        i = cols.index("customers")
        cols.append("is_small_cell")
        meta["is_small_cell"] = {"aux": True}
        for r in data:
            n = _d(r[i])
            r.append("true" if n is not None and n < SMALL_CELL else "false")
    d = comp.derived
    if d and d["op"] == "growth":
        cols, data, meta = _growth(comp, cols, data, meta)
    elif d and d["op"] == "share":
        cols, data, meta = _share(comp, cols, data, meta)
    elif d and d["op"] == "ratio":
        cols, data, meta = _ratio(comp, cols, data, meta)
    if d:
        data = _sort_limit(comp, cols, data, meta)
    data = data[:200]
    dims = [c for c in cols if meta.get(c, {}).get("dim") and not meta[c].get("label")]
    x = next((f"{dd}_label" for dd in dims if f"{dd}_label" in cols), dims[0] if dims else None)
    ys = [c for c in cols if meta.get(c, {}).get("main")]
    unit = next((meta[c].get("unit") for c in ys), None)
    return Table(cols, data, meta, {"type": comp.chart_type, "x": x, "y": ys, "unit": unit})


def _main_col(comp: Compiled, meta: dict, metric_id: str) -> str | None:
    return next((c for c, m in meta.items() if m.get("metric") == metric_id and m.get("main")), None)


def _growth(comp, cols, data, meta):
    d = comp.derived
    from .compiler import _growth_dim
    gdim = _growth_dim(d["from_period"])
    vcol = _main_col(comp, meta, d["of"])
    gi = cols.index(gdim)
    others = [c for c in cols if meta.get(c, {}).get("dim") and c not in (gdim, f"{gdim}_label")]
    keep_aux = [c for c in cols if c in ("customers", "is_small_cell", "is_low_n", "run_rate_customers")]
    groups: dict[tuple, dict] = {}
    for r in data:
        key = tuple(r[cols.index(c)] for c in others)
        groups.setdefault(key, {})[str(r[gi])] = r
    out_cols = others + [f"{vcol}_from", f"{vcol}_to", f"{vcol}_change", f"{vcol}_change_pct"] + keep_aux
    fm = meta[vcol]
    out_meta = {c: meta[c] for c in others}
    out_meta.update({f"{vcol}_from": {**fm, "main": True, "role": "from", "period": d["from_period"]},
                     f"{vcol}_to": {**fm, "main": True, "role": "to", "period": d["to_period"]},
                     f"{vcol}_change": {**fm, "main": False, "role": "change", "signed": True},
                     f"{vcol}_change_pct": {"metric": d["of"], "fmt": "pct1", "unit": "pct_change", "main": False,
                                            "role": "change_pct", "signed": True}})
    for c in keep_aux:
        out_meta[c] = meta.get(c, {"aux": True})
    vi = cols.index(vcol)
    out = []
    for key, by in groups.items():
        a, b = by.get(str(d["from_period"])), by.get(str(d["to_period"]))
        va, vb = (_d(a[vi]) if a else None), (_d(b[vi]) if b else None)
        change = (vb - va) if va is not None and vb is not None else None
        pct = _q((vb - va) / va * 100, 1) if change is not None and va not in (None, 0) else None
        aux = [((b or a)[cols.index(c)] if (b or a) else None) for c in keep_aux]
        if "is_small_cell" in keep_aux and a and b:
            j = cols.index("is_small_cell")
            aux[keep_aux.index("is_small_cell")] = "true" if "true" in (a[j], b[j]) else "false"
        out.append(list(key) + [_s(va), _s(vb), _s(change), _s(pct)] + aux)
    return out_cols, out, out_meta


def _share(comp, cols, data, meta):
    d = comp.derived
    vcol = _main_col(comp, meta, d["of"])
    vi = cols.index(vcol)
    total = sum((_d(r[vi]) or Decimal(0)) for r in data)
    cols = cols + [f"{vcol}_share"]
    meta = {**meta, f"{vcol}_share": {"metric": d["of"], "fmt": "share_pct1", "unit": "share", "main": True,
                                      "role": "share"}}
    for r in data:
        v = _d(r[vi])
        r.append(_s(_q(v / total, 4)) if v is not None and total else None)
    return cols, data, meta


def _ratio(comp, cols, data, meta):
    d = comp.derived
    a, b = _main_col(comp, meta, d["of"]), _main_col(comp, meta, d["over"])
    ai, bi = cols.index(a), cols.index(b)
    of_m, over_m = C.METRICS[d["of"]], C.METRICS[d["over"]]
    fmt = "money" if of_m.unit == "money" and over_m.unit == "count" else "dec1"
    cols = cols + ["ratio_value"]
    meta = {**meta, "ratio_value": {"metric": d["of"], "fmt": fmt, "unit": "money" if fmt == "money" else "dec",
                                    "main": True, "role": "ratio"}}
    for r in data:
        x, y = _d(r[ai]), _d(r[bi])
        r.append(_s(_q(x / y, 2)) if x is not None and y not in (None, 0) else None)
    return cols, data, meta


def _sort_limit(comp, cols, data, meta):
    sort = comp.sort
    if not sort:
        return data
    by = None
    if comp.derived and comp.derived["op"] == "growth":
        by = next((c for c in cols if meta.get(c, {}).get("role") == "change_pct"), None)
    if comp.derived and comp.derived["op"] == "share" and sort["by"] == comp.derived.get("of"):
        by = next((c for c in cols if meta.get(c, {}).get("role") == "share"), None)
    if by is None:
        by = _main_col(comp, meta, sort["by"]) or next((c for c in cols if meta.get(c, {}).get("role") == "ratio"), None)
    if by is None:
        return data
    i = cols.index(by)
    present = [r for r in data if _d(r[i]) is not None]
    missing = [r for r in data if _d(r[i]) is None]
    present.sort(key=lambda r: _d(r[i]), reverse=sort["dir"] == "desc")
    return (present + missing)[: comp.limit]


# ---------------------------------------------------------------------------- #
# The lever planner (§16.3 of the gold model), exact decimals                   #
# ---------------------------------------------------------------------------- #

def _lever_table(comp, header, rows):
    cols = [c.lower() for c in header]
    if not rows:
        return Table(["metric", "base", "scenario"], [], {}, {"type": "table", "x": "metric", "y": ["base", "scenario"]})
    r = dict(zip(cols, rows[0]))
    d = comp.derived
    won = _d(r["won_per_month"])
    rr = _d(r["run_rate_value"])
    cost = _d(r["cost_per_won_value"])
    f = Decimal(1)
    dmix = Decimal(0)
    if d.get("mix"):
        va, vb = _d(r.get("from_industry_value")), _d(r.get("to_industry_value"))
        if va is not None and vb is not None:
            dmix = _q(Decimal(str(d["mix"]["points"])) / 100 * (vb - va), 2)
    t = Decimal(str(d.get("ticket_pct", 0))) / 100
    g = Decimal(str(d.get("spend_pct", 0))) / 100
    won2 = _q(won * f, 6)
    rr2 = _q((rr + dmix) * (1 + t), 2)
    mrr2 = _q(won2 * rr2, 2)
    cost2 = _q(cost * (1 + g) / f, 2) if cost is not None else None
    pay2 = _q(cost2 / rr2, 1) if cost2 is not None and rr2 else None
    base_mrr = _d(r["new_mrr_per_month_value"])
    base_pay = _d(r["payback_months"])
    out = [["Clientes nuevos al mes", r["won_per_month"], _s(won2)], ["Ticket inicial", r["run_rate_value"], _s(rr2)],
           ["MRR nuevo al mes", r["new_mrr_per_month_value"], _s(mrr2)],
           ["Costo por cliente nuevo", r["cost_per_won_value"], _s(cost2)], ["Payback (meses)", r["payback_months"], _s(pay2)]]
    if d.get("mix"):
        out.append(["Cambio del ticket por mezcla", None, _s(dmix)])
    meta = {"metric": {"dim": "metric"}, "base": {"main": True}, "scenario": {"main": True},
            "_lever": {"won": won, "won2": won2, "rr": rr, "rr2": rr2, "mrr": base_mrr, "mrr2": mrr2, "cost": cost,
                       "cost2": cost2, "pay": base_pay, "pay2": pay2, "dmix": dmix, "low_n": r.get("is_low_n") == "true"}}
    return Table(["metric", "base", "scenario"], out, meta, {"type": "table", "x": "metric", "y": ["base", "scenario"],
                                                            "unit": "money"})


# ---------------------------------------------------------------------------- #
# Summaries (§2.3 rule 10)                                                      #
# ---------------------------------------------------------------------------- #

class _Say:
    def __init__(self):
        self.displays: list[str] = []

    def v(self, value: Any, fmt: str) -> str:
        s = F.display(value, fmt)
        self.displays.append(s)
        return s

    def n(self) -> int:
        return len(self.displays)


def _label(row: dict, comp: Compiled, dims: list[str]) -> str:
    parts = []
    for d in dims:
        val = row.get(f"{d}_label") or row.get(d)
        if d == "period":
            parts.append(F.period_es(str(val)).capitalize())
        elif d == "cohort_half":
            parts.append(F.cohort_es(str(val)).capitalize())
        elif d == "month":
            parts.append(F.month_es(str(val)).capitalize())
        elif d == "quarter":
            parts.append(F.quarter_es(str(val)).capitalize())
        elif d == "industry":
            parts.append(C.INDUSTRIES.get(str(row.get("industry")), str(val)))
        elif d == "dataset":
            parts.append(C.DATASETS.get(str(row.get("dataset")), str(val)))
        elif d == "spend_category":
            parts.append(C.SPEND_CATEGORIES.get(str(val), str(val)).capitalize())
        elif d == "spend_group":
            parts.append(C.SPEND_GROUPS.get(str(val), str(val)).capitalize())
        elif d == "mrr_line":
            parts.append(C.MRR_LINES.get(str(val), str(val)).capitalize())
        elif d == "driver":
            parts.append(C.DRIVERS.get(str(val), str(val)).capitalize())
        elif d == "funnel_stage":
            parts.append(C.STAGES.get(str(val), str(val)).capitalize())
        elif d == "customer_scope":
            parts.append(C.CUSTOMER_SCOPES.get(str(val), str(val)).capitalize())
        elif d == "method":
            parts.append({"diff": "Sin tendencia (diferencias)", "within_regime": "Dentro de cada periodo",
                          "level": "En niveles"}.get(str(val), str(val)))
        else:
            parts.append(str(val))
    return ", ".join(p for p in parts if p)


def _time_phrase(comp: Compiled, ctx: Context, stock: bool) -> str:
    t = comp.time or {}
    tf = (comp.spec.get("filters") or {}).get("time") or {}
    if t.get("period_code"):
        return F.period_es(t["period_code"])
    if not t.get("explicit"):
        return ""
    lo, hi = t["from"], t["to"]
    if lo == hi:
        return ("a " if stock else "en ") + F.month_es(hi)
    if "year" in tf or (lo[5:] == "01" and hi[:4] == lo[:4] and (hi[5:] == "12" or hi == ctx.data_complete_through)):
        return f"en {lo[:4]}"
    return f"de {F.month_es(lo)} a {F.month_es(hi)}"


def _evidence_sentence(comp: Compiled) -> str:
    if comp.evidence == "observado":
        return ""
    return " " + C.EVIDENCE_SPOKEN[comp.evidence][:1].upper() + C.EVIDENCE_SPOKEN[comp.evidence][1:] + "."


def _money_ok(row: dict, meta_c: dict) -> bool:
    return not (meta_c.get("unit") == "money" and row.get("is_small_cell") == "true")


def _value_text(say: _Say, row: dict, col: str, meta: dict) -> str:
    m = meta[col]
    if not _money_ok(row, m):
        return "menos de 5 clientes"
    val = row.get(col)
    s = say.v(val, m["fmt"])
    nn = noun(m.get("metric", ""), val)
    return f"{s} {nn}" if nn and m.get("main") else s


def summarize(comp: Compiled, table: Table, ctx: Context) -> Summary:
    say = _Say()
    if comp.kind == "lever":
        text = _sum_lever(comp, table, say)
    elif comp.kind == "dq":
        text = _sum_dq(comp, table, say)
    elif not table.rows:
        text = "No hay datos para ese corte."
    elif comp.derived and comp.derived["op"] == "growth":
        text = _sum_growth(comp, table, say, ctx)
    else:
        text = _sum_rows(comp, table, say, ctx)
    text = text.strip() + _evidence_sentence(comp)
    return Summary(text=text, displays=say.displays, caveats_es=caveats_es(comp, table, ctx))


def _rows(table: Table) -> list[dict]:
    return [dict(zip(table.columns, r)) for r in table.rows]


def _sum_growth(comp, table, say, ctx):
    d = comp.derived
    name = C.METRICS[d["of"]].name_es
    rows = _rows(table)
    dims = [c for c in table.columns if table.meta.get(c, {}).get("dim") and not table.meta[c].get("label")]
    fcol = next(c for c in table.columns if table.meta.get(c, {}).get("role") == "from")
    tcol = next(c for c in table.columns if table.meta.get(c, {}).get("role") == "to")
    pcol = next(c for c in table.columns if table.meta.get(c, {}).get("role") == "change_pct")
    fm = table.meta[fcol]["fmt"]
    from .compiler import _growth_dim
    gd = _growth_dim(d["from_period"])

    def per(v):
        return {"period": F.period_es, "month": F.month_es, "quarter": F.quarter_es, "cohort_half": F.cohort_es}.get(
            gd, lambda x: f"en {x}")(str(v))
    head = f"{name[:1].upper()}{name[1:]}, {per(d['from_period'])} frente a {per(d['to_period'])}"
    parts = []
    for r in rows[: max(1, MAX_SPOKEN // 3)]:
        if r.get(pcol) is None:
            continue
        pct = _d(r[pcol])
        word = "menos" if pct < 0 else "más"
        lab = _label(r, comp, dims)
        if not _money_ok(r, table.meta[fcol]):
            parts.append(f"{lab}: menos de 5 clientes")
            continue
        parts.append(f"{lab + ': ' if lab else ''}de {say.v(r[fcol], fm)} a {say.v(r[tcol], fm)}, "
                     f"{say.v(abs(pct), 'pct1')} {word}")
    if comp.sort and dims and parts:
        first = rows[0]
        verb = "bajó" if (_d(first.get(pcol)) or 0) < 0 else "subió"
        lead = f"{_label(first, comp, dims)} es la que más {verb}"
        return f"{head}. {lead}: {parts[0].split(': ', 1)[-1]}."
    return f"{head}: " + "; ".join(parts) + "." if parts else "No hay datos para comparar esos periodos."


def _sum_rows(comp, table, say, ctx):
    rows = _rows(table)
    meta = table.meta
    dims = [c for c in table.columns if meta.get(c, {}).get("dim") and not meta[c].get("label")]
    mains = [c for c in table.columns if meta.get(c, {}).get("main")]
    stock = any(meta[c].get("kind") == "stock" for c in mains)
    tp = _time_phrase(comp, ctx, stock)
    names = {c: C.METRICS[meta[c]["metric"]].name_es for c in mains}
    time_dims = [x for x in dims if x in ("month", "quarter", "year")]
    # net change (mrr.net_change): closing(last) - opening(first)
    if "mrr.net_change" in comp.metrics and len(rows) == 1 and not dims:
        r = rows[0]
        op, cl = _d(r.get("mrr_opening_value")), _d(r.get("mrr_closing_value"))
        if op is not None and cl is not None:
            ch = cl - op
            pct = _q(ch / op * 100, 1) if op else None
            verb = "creció" if ch >= 0 else "bajó"
            return (f"El MRR {verb} {say.v(abs(ch), 'money')}{' ' + tp if tp else ''}, "
                    f"un {say.v(abs(pct), 'pct1')}, de {say.v(op, 'money')} a {say.v(cl, 'money')}.")
    # one row: a KPI
    if len(rows) == 1 and (not dims or comp.chart_type in ("table",) and len(dims) <= 1):
        r = rows[0]
        lab = _label(r, comp, dims)
        bits = []
        line = ((comp.spec.get("filters") or {}).get("mrr_line") or [None])[0]
        for c in mains[:MAX_SPOKEN]:
            val = _d(r.get(c))
            if line and meta[c].get("unit") == "money" and val is not None and val < 0 and _money_ok(r, meta[c]):
                bits.append(f"perdimos {say.v(abs(val), meta[c]['fmt'])} por {C.MRR_LINES.get(line, line)}")
                continue
            v = _signed_value(say, r, c, meta)
            bits.append(v if noun(meta[c].get("metric", ""), r.get(c)) else f"{names[c]} {v}")
        pre = ", ".join(x for x in (lab, tp) if x)
        pre = pre[:1].upper() + pre[1:] if pre else ""
        return (pre + ": " if pre else "") + "; ".join(bits) + "."
    # a trend over time
    if time_dims and not comp.sort and len(rows) > 1:
        c = mains[0]
        if meta[c].get("kind") == "stock":
            a, b = rows[0], rows[-1]
            return (f"{names[c][:1].upper()}{names[c][1:]}: de {_signed_value(say, a, c, meta)} "
                    f"({_label(a, comp, time_dims)}) a {_signed_value(say, b, c, meta)} ({_label(b, comp, time_dims)}).")
        tot = {cc: sum((_d(r.get(cc)) or Decimal(0)) for r in rows) for cc in mains if meta[cc].get("unit") != "share"}
        bits = []
        for cc in mains:
            if cc not in tot:
                continue
            v = tot[cc]
            line = ((comp.spec.get("filters") or {}).get("mrr_line") or [None])
            if meta[cc].get("unit") == "money" and v < 0:
                lab = C.MRR_LINES.get(line[0], "") if line[0] else ""
                bits.append(f"perdimos {say.v(abs(v), 'money')}" + (f" por {lab}" if lab else ""))
            else:
                nn = noun(meta[cc].get("metric", ""), v) or names[cc]
                bits.append(f"{say.v(v, meta[cc]['fmt'])} {nn}" if meta[cc].get("unit") == "count"
                            else f"{names[cc]} {say.v(v, meta[cc]['fmt'])}")
        pre = tp[:1].upper() + tp[1:] + ", " if tp else "En total, "
        return pre + ", en ".join(bits) + "."
    # a list or a ranking over categories
    aux_pairs = [(c, c.replace("_share", "_count"), c.replace("_share", "_eligible")) for c in mains
                 if c.endswith("_share") and c.replace("_share", "_count") in table.columns]
    n_main = len(mains)
    n_rows = max(1, min(len(rows), 3, MAX_SPOKEN // max(1, n_main)))
    if comp.sort:
        n_rows = max(1, min(n_rows, comp.limit))
    budget = MAX_SPOKEN - n_rows * n_main
    parts = []
    for r in rows[:n_rows]:
        vals = []
        for c in mains:
            v = _signed_value(say, r, c, meta)
            pair = next((p for p in aux_pairs if p[0] == c), None)
            if pair and budget >= 2 and r.get(pair[1]) is not None:
                v += f" ({say.v(r[pair[1]], 'int')} de {say.v(r[pair[2]], 'int')})"
                budget -= 2
            if c.endswith("_share") and meta[c].get("role") == "share":
                v += " del total"
            vals.append(v)
        lab = _label(r, comp, dims)
        parts.append((lab[:1].lower() + lab[1:] if dims and dims[0] == "period" else lab) + ", " + " y ".join(vals))
    mnames = [names[c] for c in mains]
    head = " y ".join(mnames[:2])
    head = head[:1].upper() + head[1:] + (" por " + C.DIMENSIONS[dims[0]] if dims and dims[0] in C.DIMENSIONS else "")
    if tp:
        head += " " + tp
    if comp.sort and dims:
        order = "de mayor a menor" if comp.sort["dir"] == "desc" else "de menor a mayor"
        return f"{head}, {order}: " + "; ".join(parts) + "."
    return f"{head}: " + "; ".join(parts) + "."


def _signed_value(say, row, col, meta):
    m = meta[col]
    v = _d(row.get(col))
    if not _money_ok(row, m):
        return "menos de 5 clientes"
    if v is not None and v < 0 and m.get("unit") == "money":
        return f"{say.v(abs(v), m['fmt'])} en contra"
    return _value_text(say, row, col, meta)


def _sum_lever(comp, table, say):
    L = table.meta.get("_lever")
    if not L:
        return "No encontré la base del periodo para calcular el escenario."
    d = comp.derived
    if d.get("mix"):
        fr = C.INDUSTRIES[d["mix"]["from_industry"]]
        to = C.INDUSTRIES[d["mix"]["to_industry"]]
        lead = f"Con ese cambio de mezcla de {fr} a {to}"
    elif d.get("ticket_pct"):
        lead = "Con ese cambio de ticket"
    else:
        lead = "Con ese cambio de gasto"
    if d.get("spend_pct") and not d.get("mix") and not d.get("ticket_pct"):
        return (f"{lead}, el costo por cliente nuevo pasaría de {say.v(L['cost'], 'money')} a {say.v(L['cost2'], 'money')} "
                f"y el payback de {say.v(L['pay'], 'months1')} a {say.v(L['pay2'], 'months1')}; los clientes nuevos "
                "se mantienen fijos porque el efecto del gasto no está probado.")
    delta = L["rr2"] - L["rr"]
    verb = "subiría" if delta >= 0 else "bajaría"
    return (f"{lead}, el MRR nuevo pasaría de {say.v(L['mrr'], 'money')} a {say.v(L['mrr2'], 'money')} al mes; "
            f"el ticket inicial {verb} {say.v(abs(delta), 'money')}, a {say.v(L['rr2'], 'money')}, y el payback "
            f"quedaría en {say.v(L['pay2'], 'months1')}.")


def _sum_dq(comp, table, say):
    rows = _rows(table)
    fam = comp.plan["family"]
    if not rows:
        return "No hay resultados de calidad para ese filtro."
    if fam == "rule":
        f = comp.spec["filters"]
        statuses = [s for s in ("warn", "fail") if s in (f.get("rule_status") or [])]
        counts = []
        for s in statuses:
            n = sum(1 for r in rows if r.get("status") == s)
            counts.append(f"{say.v(n, 'int')} en {C.RULE_STATUS_ES[s]}")
        items = []
        fc = "failed" if "failed" in table.columns else None
        for r in rows:
            if say.n() >= MAX_SPOKEN:
                break
            lab = f"{r['rule']} {C.DATASETS.get(r['dataset'], r['dataset'])}"
            if fc and r.get(fc) is not None:
                lab += f" {say.v(r[fc], 'int')}"
            elif "compliance_pct" in table.columns:
                lab += f" {say.v(r['compliance_pct'], 'pct_dq')}"
            elif "status" in table.columns:
                lab += f" {C.RULE_STATUS_ES.get(r.get('status'), r.get('status'))}"
            items.append(lab)
        head = ", ".join(counts)
        return (head + ": " if head else "Reglas: ") + "; ".join(items) + "."
    if fam == "trend":
        last = rows[-3:] if len(rows) >= 3 else rows
        return "Cumplimiento en la última corrida: " + "; ".join(
            f"{r['dataset_label'] if r['dataset'] not in C.DATASETS else C.DATASETS[r['dataset']]} "
            f"{say.v(r['row_compliance_pct'], 'pct_dq')}" for r in last) + "."
    mains = [c for c in table.columns if table.meta.get(c, {}).get("main")]
    if comp.sort and len(rows) >= 1 and comp.limit == 1:
        r = rows[0]
        which = "más bajo" if comp.sort["dir"] == "asc" else "más alto"
        lab = C.DATASETS.get(r["dataset"], r["dataset"])
        vals = [_value_text(say, r, c, table.meta) for c in mains]
        tail = ""
        if "rows_excluded" in r and (_d(r.get("rows_excluded")) or 0) > 0:
            rules = comp.plan.get("exclusion_rules", {}).get(r["dataset"]) or []
            if rules:
                tail = " por la regla " + ", ".join(f"{x} ({RULE_GLOSS_ES.get(x, 'regla de exclusión')})" for x in rules)
        name = C.METRICS[table.meta[mains[0]]["metric"]].name_es
        return f"{lab} tiene el {name} {which}: " + ", ".join(vals) + tail + "."
    parts = []
    for r in rows[: max(1, MAX_SPOKEN // max(1, len(mains)))]:
        parts.append(f"{C.DATASETS.get(r['dataset'], r['dataset'])} " + ", ".join(_value_text(say, r, c, table.meta)
                                                                                   for c in mains))
    name = C.METRICS[table.meta[mains[0]]["metric"]].name_es
    return f"{name[:1].upper()}{name[1:]}: " + "; ".join(parts) + "."


# ---------------------------------------------------------------------------- #
# Caveats (§2.3 rule 8): templated from the result, never literal figures        #
# ---------------------------------------------------------------------------- #

def caveats_es(comp: Compiled, table: Table, ctx: Context) -> list[str]:
    ids = list(comp.caveats)
    rows = _rows(table)
    if any(r.get("is_low_n") == "true" for r in rows) or (table.meta.get("_lever") or {}).get("low_n"):
        ids.insert(max(0, len(ids) - 1 if "C-CUR" in ids else len(ids)), "C-LOWN")
    out = []
    for cid in ids:
        text = C.CAVEATS[cid]
        if cid == "C-MULT":
            tot = sum((_d(r.get("new_revenue_value")) or Decimal(0)) for r in rows)
            mul = sum((_d(r.get("new_revenue_multiple_value")) or Decimal(0)) for r in rows)
            text = text.replace("{mult_pct}", F.display(_q(mul / tot * 100, 1), "pct1")) if tot and mul else \
                "Incluye primeros pagos dobles o triples."
        elif cid == "C-PARTIAL":
            text = partial_text(comp, ctx)
            if not text:
                continue
        elif cid == "C-OUTLIER":
            continue
        out.append(text)
    if "acq.avg_monthly_payment" in comp.metrics:
        for r in rows:
            if r.get("industry") == "RESTAURANTS" and r.get("customer_scope", "all") in ("all", "left_censored") \
                    and r.get("avg_monthly_payment_ex_outlier_value"):
                out.insert(0, C.CAVEATS["C-OUTLIER"].replace(
                    "{ex_outlier}", F.display(r["avg_monthly_payment_ex_outlier_value"], "money")))
                break
    return out
