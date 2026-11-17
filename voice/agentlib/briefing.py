"""The briefing of each gold refresh (docs/semantic_layer.md §4; contract v1.1).

1. The KPI table (§4.2), by code: one compiled spec per candidate on the published gold
   snapshot (the same compiler and Athena path as /ask) plus the DQ snapshot of the same
   silver run. Changes and percentages are computed here. No HR category, no customer value.
2. Kimi K3 (Bedrock us-east-1) picks and phrases 5-8 facts through `submit_briefing`.
3. Every fact passes §4.4 (exact display match both ways, direction, lexical guards).
4. §4.5: regenerate the failed facts once, then the candidate's template, then drop; fill
   to 5 from unused templates; `degraded` below 5. A mismatched number is never published.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

from . import bedrock
from . import catalog as C
from . import compiler as K
from . import fmt as F
from . import numbers as N
from . import post as P

CLASS_ORDER = {"lever": 0, "state": 1, "trust": 2, "null": 3}
MONTH_WORDS = "|".join(F.MONTHS_ES)
DATE_RX = re.compile(rf"\b({MONTH_WORDS}) de (\d{{4}})\b", re.I)
NUMBER_WORDS = re.compile(
    r"\b(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|veinte|veinti\w+|"
    r"treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento|doscient\w+|trescient\w+|"
    r"cuatrocient\w+|quinient\w+|seiscient\w+|setecient\w+|ochocient\w+|novecient\w+|mil|millón|millon)\b", re.I)
HR_WORDS = re.compile(r"\b(equipo|nómina|nomina|freelance|team|payroll\w*)\b", re.I)
UP_WORDS = re.compile(r"^(sub\w*|crec\w*|aument\w*|sum\w*|más|mas|mejor\w*|super\w*)$", re.I)
DOWN_WORDS = re.compile(r"^(baj\w*|ca[yí]\w*|ca[ií]d\w*|rest\w*|perd\w*|perdimos|menos|disminu\w*|redu\w*|sali\w*)$", re.I)


@dataclass
class Value:
    key: str
    kpi_id: str
    value: str          # the exact decimal string from gold (or computed by code)
    fmt: str
    unit: str
    signed: bool = False

    @property
    def display(self) -> str:
        return F.display(self.value if not self.signed else abs(F.dec(self.value)), self.fmt)


@dataclass
class Candidate:
    candidate_id: str
    slug: str
    klass: str
    page: str
    kpi_ids: list
    evidence: str
    values: list = field(default_factory=list)
    template_es: str = ""
    metrics: list = field(default_factory=list)      # for definitions[]
    caveats: list = field(default_factory=list)
    dates: list = field(default_factory=list)        # "octubre de 2024" phrases a fact may use
    magnitude: Decimal = Decimal(0)

    def by_key(self) -> dict:
        return {v.key: v for v in self.values}


# ---------------------------------------------------------------------------- #
# 1. The KPI table                                                              #
# ---------------------------------------------------------------------------- #

def _spec(domain: str, metrics: list, dims: list | None = None, time_: dict | None = None, **kw) -> dict:
    s = {"catalog_version": C.VERSION, "intent": "answer", "domain": domain, "metrics": metrics,
         "dimensions": dims or [], "filters": {"time": time_ or {}}, "chart": {"type": "table"}}
    s.update(kw)
    return s


def _rows(table: P.Table | None) -> list[dict]:
    return [dict(zip(table.columns, r)) for r in table.rows] if table else []


def _pct(a: Any, b: Any, places: int = 1) -> str | None:
    """(b / a - 1) x 100, HALF_UP."""
    da, db_ = F.dec(a), F.dec(b)
    if da in (None, 0) or db_ is None:
        return None
    return format(F.q((db_ - da) / da * 100, places), "f")


def build_kpi_table(ctx: K.Context, run: Callable[[dict], P.Table | None], dq: dict) -> list[Candidate]:
    """`run(spec)` compiles a spec (role data: nothing HR) and returns its table."""
    out: list[Candidate] = []
    dct_es = F.month_es(ctx.data_complete_through)
    lp = {r["period"]: r for r in _rows(run(_spec("acquisition", ["acq.won_per_month", "acq.run_rate_per_won"], ["period"])))}
    pre, cur = lp.get("pre_2023_06"), lp.get("from_2023_06")
    if pre and cur:
        won_ch, rr_ch = _pct(pre["won_per_month"], cur["won_per_month"]), _pct(pre["run_rate_value"], cur["run_rate_value"])
        if won_ch and rr_ch:
            v = [Value("won_change", "acq.lost.new_customers", won_ch, "pct0", "pct_change", True),
                 Value("rr_change", "acq.lost.starting_revenue", rr_ch, "pct0", "pct_change", True),
                 Value("rr_pre", "acq.lost.starting_revenue", pre["run_rate_value"], "money", "money"),
                 Value("rr_cur", "acq.lost.starting_revenue", cur["run_rate_value"], "money", "money")]
            d = {x.key: x.display for x in v}
            up = F.dec(won_ch) >= 0
            more = F.dec(rr_ch) >= 0
            t = (f"Los clientes nuevos por mes {'subieron' if up else 'bajaron'} {d['won_change']}, pero cada uno empieza "
                 f"pagando {d['rr_change']} {'más' if more else 'menos'}: de {d['rr_pre']} a {d['rr_cur']} al mes.") \
                if up != more else \
                (f"Los clientes nuevos por mes {'subieron' if up else 'bajaron'} {d['won_change']} y cada uno empieza "
                 f"pagando {d['rr_change']} {'más' if more else 'menos'}: de {d['rr_pre']} a {d['rr_cur']} al mes.")
            out.append(Candidate("B01", "acq_ticket_drop", "lever", "acquisition",
                                 ["acq.lost.starting_revenue", "acq.lost.new_customers"], "observado", v, t,
                                 ["acq.won_per_month", "acq.run_rate_per_won"], ["C-REGIME", "C-IMMATURE"],
                                 magnitude=abs(F.dec(rr_ch))))
    # B02 within-industry share of the ticket change; the biggest drop; the industries that rose
    vc = _rows(run(_spec("acquisition", ["acq.ticket_change_mix", "acq.ticket_change_within"])))
    li = _rows(run(_spec("acquisition", ["acq.run_rate_per_won"], ["period", "industry"])))
    named = {}
    for r in li:
        if r.get("industry") in ("UNKNOWN", "UNMAPPED") or r.get("is_low_n") == "true":
            continue
        named.setdefault(r["industry"], {})[r["period"]] = r.get("run_rate_value")
    changes = {i: _pct(p.get("pre_2023_06"), p.get("from_2023_06")) for i, p in named.items()
               if p.get("pre_2023_06") and p.get("from_2023_06")}
    if vc and changes:
        mix, within = F.dec(vc[0].get("mix_value")), F.dec(vc[0].get("within_value"))
        if mix is not None and within is not None and (mix + within) != 0:
            share = format(F.q(within / (mix + within) * 100, 1), "f")
            worst = min(changes, key=lambda i: F.dec(changes[i]))
            rose = [i for i in changes if F.dec(changes[i]) > 0]
            v = [Value("within_share", "acq.lost.ticket_by_industry", share, "pct0", "pct"),
                 Value(f"change_{worst}", "acq.lost.ticket_by_industry", changes[worst], "pct0", "pct_change", True)]
            d = {x.key: x.display for x in v}
            where = "dentro de cada industria, no por mezcla" if F.dec(share) >= 50 else "por la mezcla de industrias"
            t = f"La caída del ticket es {where}: explica el {d['within_share']}. {C.INDUSTRIES[worst]} cayó {d[f'change_{worst}']}"
            if len(rose) == 1:
                v.append(Value(f"change_{rose[0]}", "acq.lost.ticket_by_industry", changes[rose[0]], "pct0",
                               "pct_change", True))
                t += f" y solo {C.INDUSTRIES[rose[0]]} subió, {v[-1].display}."
            elif not rose:
                t += " y ninguna industria subió."
            else:
                t += " y subieron " + " y ".join(C.INDUSTRIES[i] for i in rose) + "."
            out.append(Candidate("B02", "acq_ticket_within", "lever", "acquisition", ["acq.lost.ticket_by_industry"],
                                 "observado", v, t, ["acq.ticket_change_within", "acq.ticket_change_mix"], ["C-REGIME"],
                                 magnitude=abs(F.dec(changes[worst]))))
        # B03 the mix lever between the lowest- and highest-ticket industries of the current period
        cur_v = {i: F.dec(p["from_2023_06"]) for i, p in named.items() if p.get("from_2023_06")}
        if len(cur_v) >= 2:
            # The catalog's reference move (§4.2 B03, gold model §16.3): Retail -> Technology.
            lo, hi = ("RETAIL", "TECHNOLOGY") if {"RETAIL", "TECHNOLOGY"} <= set(cur_v) else \
                (min(cur_v, key=cur_v.get), max(cur_v, key=cur_v.get))
            dmix = format(F.q(Decimal(10) / 100 * (cur_v[hi] - cur_v[lo]), 2), "f")
            v = [Value("points", "acq.lever.mix", "10", "int", "count"),
                 Value("dmix", "acq.lever.mix", dmix, "money", "money")]
            t = (f"Pasar {v[0].display} puntos de clientes nuevos de {C.INDUSTRIES[lo]} a {C.INDUSTRIES[hi]} subiría el "
                 f"ticket en {v[1].display} al mes, si cada industria mantiene su ticket.")
            out.append(Candidate("B03", "acq_mix_lever", "lever", "acquisition", ["acq.lever.mix"], "observado", v, t,
                                 ["acq.run_rate_per_won", "acq.won_share"], ["C-MIX"]))
    # B04 cost per Won and payback, both periods
    cp = {r["period"]: r for r in _rows(run(_spec("acquisition", ["acq.cost_per_won", "acq.payback_months"], ["period"])))}
    if cp.get("pre_2023_06") and cp.get("from_2023_06") and all(cp[p].get("cost_per_won_value") and cp[p].get("payback_months")
                                                               for p in cp):
        a, b = cp["pre_2023_06"], cp["from_2023_06"]
        v = [Value("cost_pre", "acq.funnel.won_cost", a["cost_per_won_value"], "money", "money"),
             Value("cost_cur", "acq.funnel.won_cost", b["cost_per_won_value"], "money", "money"),
             Value("pay_pre", "acq.plan.payback", a["payback_months"], "dec1", "months"),
             Value("pay_cur", "acq.plan.payback", b["payback_months"], "dec1", "months")]
        d = {x.key: x.display for x in v}
        verb = "bajó" if F.dec(b["cost_per_won_value"]) < F.dec(a["cost_per_won_value"]) else "subió"
        t = (f"El gasto S&M por cliente nuevo {verb} de {d['cost_pre']} a {d['cost_cur']}, y el payback simple de "
             f"{d['pay_pre']} a {d['pay_cur']} meses.")
        out.append(Candidate("B04", "acq_cost_payback", "state", "acquisition", ["acq.plan.payback", "acq.funnel.won_cost"],
                             "inferido", v, t, ["acq.cost_per_won", "acq.payback_months"],
                             ["C-NOT-CAC", "C-PAYBACK", "C-REGIME"],
                             magnitude=abs(F.dec(_pct(a["cost_per_won_value"], b["cost_per_won_value"]) or 0))))
    # B05 retention at month 12, both periods
    rt = {r["period"]: r for r in _rows(run(_spec("acquisition", ["acq.paying_m12_share"], ["period"])))}
    if rt.get("pre_2023_06", {}).get("paying_m12_share") and rt.get("from_2023_06", {}).get("paying_m12_share"):
        a, b = rt["pre_2023_06"]["paying_m12_share"], rt["from_2023_06"]["paying_m12_share"]
        v = [Value("m12_cur", "acq.lost.keep_paying", b, "share_pct1", "share"),
             Value("m12_pre", "acq.lost.keep_paying", a, "share_pct1", "share")]
        same = F.dec(b) >= F.dec(a) - Decimal("0.01")
        t = (f"Los clientes nuevos siguen pagando {'igual o más' if same else 'menos'}: al mes 12 paga el {v[0].display}, "
             f"frente al {v[1].display} antes de junio de 2023.")
        out.append(Candidate("B05", "acq_retention", "state", "acquisition", ["acq.lost.keep_paying"], "observado", v, t,
                             ["acq.paying_m12_share"], ["C-RETENTION"]))
    # B06 / B08 the MRR level and the last month's change
    last = _rows(run(_spec("mrr", ["mrr.closing", "mrr.paying_customers"], [], {"relative": "latest_month"})))
    if last and last[0].get("mrr_closing_value"):
        v = [Value("closing", "mrr.bridge.closing", last[0]["mrr_closing_value"], "money", "money"),
             Value("customers", "mrr.bridge.closing", last[0]["paying_customers"], "int", "count")]
        t = (f"El MRR, calculado sobre pagos, cerró {dct_es} en {v[0].display}, con {v[1].display} clientes pagando.")
        out.append(Candidate("B06", "mrr_level", "state", "mrr", ["mrr.bridge.closing"], "inferido", v, t,
                             ["mrr.closing", "mrr.paying_customers"], ["C-MRR-PROXY"], [dct_es]))
    full = _rows(run(_spec("mrr", ["mrr.net_change"])))
    drv = {r["driver"]: r for r in _rows(run(_spec("mrr", ["mrr.driver_amount"], ["driver"])))}
    if full and full[0].get("mrr_opening_value") and drv.get("behaviour") and drv.get("timing"):
        net = F.dec(full[0]["mrr_closing_value"]) - F.dec(full[0]["mrr_opening_value"])
        v = [Value("net", "mrr.why.hero", format(net, "f"), "money", "money", True),
             Value("behaviour", "mrr.why.driver.behaviour", drv["behaviour"]["driver_amount_value"], "money", "money", True),
             Value("timing", "mrr.why.driver.timing", drv["timing"]["driver_amount_value"], "money", "money", True)]
        d = {x.key: x.display for x in v}
        start_es = F.month_es(ctx.window_start_month)
        t = (f"Desde {start_es} el MRR {'creció' if net >= 0 else 'bajó'} {d['net']}: el comportamiento de los clientes "
             f"{'suma' if F.dec(v[1].value) >= 0 else 'resta'} {d['behaviour']} y los primeros pagos adelantados "
             f"{'suman' if F.dec(v[2].value) >= 0 else 'restan'} {d['timing']}.")
        out.append(Candidate("B07", "mrr_growth_drivers", "state", "mrr",
                             ["mrr.why.hero", "mrr.why.driver.behaviour", "mrr.why.driver.timing"], "inferido", v, t,
                             ["mrr.net_change", "mrr.driver_amount"], ["C-MRR-PROXY"], [start_es]))
    lm = _rows(run(_spec("mrr", ["mrr.net_change"], [], {"relative": "latest_month"})))
    if lm and lm[0].get("mrr_opening_value") and lm[0].get("mrr_closing_value"):
        op, cl = F.dec(lm[0]["mrr_opening_value"]), F.dec(lm[0]["mrr_closing_value"])
        ch = cl - op
        v = [Value("change", "mrr.why.hero", format(ch, "f"), "money", "money", True),
             Value("change_pct", "mrr.why.hero", format(F.q(ch / op * 100, 1), "f"), "pct1", "pct_change", True)]
        prov = ctx.data_complete_through > ctx.churn_confirmed_through
        t = (f"En {dct_es} el MRR {'subió' if ch >= 0 else 'bajó'} {v[0].display}, un {v[1].display}"
             + ("; el dato es provisional." if prov else "."))
        out.append(Candidate("B08", "mrr_last_month", "state", "mrr", ["mrr.why.hero"], "inferido", v, t,
                             ["mrr.net_change"], ["C-MRR-PROXY"] + (["C-PROV"] if prov else []), [dct_es],
                             magnitude=abs(F.dec(v[1].value))))
    # B09 / B10 trust (DQ snapshot of the same silver run)
    dss = {d["dataset_id"]: d for d in dq.get("datasets", [])}
    if dss:
        v = [Value(f"pct_{ds}", f"dq.scorecard.{ds}", K._s(dss[ds]["row_compliance_pct"]), "pct_dq", "pct")
             for ds in ("transactions", "sm_spend", "industry") if ds in dss]
        full_ = [x for x in v if F.dec(x.value) == 100]
        part = [x for x in v if F.dec(x.value) != 100]
        names = lambda xs: " y ".join(C.DATASETS[x.key[4:]] for x in xs)  # noqa: E731
        if full_ and part:
            t = (f"Los datos de hoy son confiables: {names(full_)} cumple{'n' if len(full_) > 1 else ''} al 100 % y "
                 + ", ".join(f"{C.DATASETS[x.key[4:]]} al {x.display}" for x in part))
            empty = [x for x in part if dss[x.key[4:]].get("rows_excluded") == 1]
            t += (", por un registro vacío." if len(part) == 1 and empty and _excluded_by(dq, empty[0].key[4:]) == ["SQ-02"]
                  else ".")
            v = full_[:1] + part if len(full_) > 1 else v  # "100 %" is written once
        elif full_:
            t = f"Los datos de hoy son confiables: {names(full_)} cumplen al 100 %."
            v = full_[:1]
        else:
            t = "Cumplimiento de filas: " + ", ".join(f"{C.DATASETS[x.key[4:]]} {x.display}" for x in part) + "."
        out.append(Candidate("B09", "dq_status", "trust", "dq", [f"dq.scorecard.{ds}" for ds in dss], "observado", v, t,
                             ["dq.row_compliance_pct"]))
    warns = [(r["rule_id"], ds, res.get("failed")) for r in dq.get("rules", []) for ds, res in (r.get("results") or {}).items()
             if res.get("status") in ("warn", "fail")]
    if warns:
        warns.sort(key=lambda x: -(x[2] or 0))
        cells = [f"dq.rule_cell.{r}.{d}" for r, d, _ in warns[:4]]
        v = [Value("warnings", cells[0], str(len(warns)), "int", "count")]
        bits = []
        for rid, ds, n in warns:
            gl = DQ_GLOSS.get(rid)
            if n == 1:
                bits.append("un " + (gl[0] if gl else f"caso de la regla {rid}"))
            elif len(v) < 4:
                v.append(Value(f"{rid}.{ds}", f"dq.rule_cell.{rid}.{ds}", str(n), "int", "count"))
                bits.append(f"{v[-1].display} " + (gl[1] if gl else f"casos de la regla {rid}"))
        kind = "avisos que no bloquean" if all(dq_status(dq, r, d) == "warn" for r, d, _ in warns) else "hallazgos"
        t = f"Hay {v[0].display} {kind}: " + (", ".join(bits[:-1]) + " y " + bits[-1] if len(bits) > 1 else bits[0]) + "."
        out.append(Candidate("B10", "dq_warnings", "trust", "dq", cells, "observado", v, t,
                             ["dq.rule_failed_count", "dq.rule_status"]))
    # B11 the spend-link null result (§16.6 rule)
    cs = {r["method"]: r for r in _rows(run(_spec("acquisition", ["acq.corr_signals"])))}
    if cs.get("diff") and cs.get("within_regime"):
        dfr, wr = cs["diff"], cs["within_regime"]
        quiet = all(F.dec(x["signals"]) <= 2 * F.dec(x["expected_by_chance"]) for x in (dfr, wr))
        if quiet:
            v = [Value("signals", "acq.signals", dfr["signals"], "int", "count"),
                 Value("tests", "acq.signals", dfr["tests_with_r"], "int", "count"),
                 Value("expected", "acq.signals", dfr["expected_by_chance"], "dec1", "dec")]
            t = (f"Estos datos no muestran un vínculo medible entre gasto y clientes nuevos: {v[0].display} de "
                 f"{v[1].display} pruebas sin tendencia salen positivas, casi lo que da el azar, {v[2].display}.")
        else:
            v = []
            t = ("Algunas pruebas sin tendencia muestran un vínculo entre gasto y clientes nuevos; revísalas con el "
                 "equipo de datos antes de usarlo.")
        out.append(Candidate("B11", "acq_spend_link", "null", "acquisition", ["acq.signals", "acq.lever.spend"],
                             "no probado", v, t, ["acq.corr_signals"], ["C-CORR"]))
    out.append(Candidate("B12", "mrr_discounts_na", "null", "mrr", ["mrr.leakage"], "observado", [],
                         "Los descuentos aún no se pueden medir: faltan los datos de facturación.", ["mrr.discount_leakage"]))
    for c in out:
        c.dates = list(dict.fromkeys(c.dates + [dct_es, "junio de 2023", F.month_es(ctx.window_start_month)]))
    return out


DQ_GLOSS = {"SB-11": ("pago repartido de forma desigual", "pagos repartidos de forma desigual"),
            "SB-10": ("mes con gasto de nómina negativo", "meses con gasto de nómina negativo"),
            "SQ-02": ("registro vacío", "registros vacíos")}


def dq_status(dq: dict, rule_id: str, ds: str) -> str:
    for r in dq.get("rules", []):
        if r["rule_id"] == rule_id:
            return ((r.get("results") or {}).get(ds) or {}).get("status", "")
    return ""


def _excluded_by(dq: dict, ds: str) -> list[str]:
    return [r["rule_id"] for r in dq.get("rules", []) if r.get("action") == "exclude"
            and (((r.get("results") or {}).get(ds) or {}).get("failed") or 0) > 0]


# ---------------------------------------------------------------------------- #
# 3. The number check (§4.4)                                                    #
# ---------------------------------------------------------------------------- #

def check_fact(fact: dict, cand: Candidate) -> list[str]:
    """[] when the fact passes; else the reasons (the first failed token first)."""
    errs: list[str] = []
    text = str(fact.get("text_es") or "")
    if not text or len(text.split()) > 35:
        errs.append("text_es must have 1 to 35 words")
    if fact.get("page") != cand.page:
        errs.append(f"page must be {cand.page}")
    kpis = fact.get("kpi_ids") or []
    if not isinstance(kpis, list) or not kpis or not set(kpis) <= set(cand.kpi_ids):
        errs.append(f"kpi_ids must be a subset of {cand.kpi_ids}")
    numbers = fact.get("numbers") or []
    if not isinstance(numbers, list):
        numbers, errs = [], errs + ["numbers must be a list"]
    vals = {(v.kpi_id, F.dec(v.value)): v for v in cand.values}
    entries = []
    for e in numbers:
        if not isinstance(e, dict):
            errs.append("numbers entries must be objects")
            continue
        v = vals.get((e.get("kpi_id"), F.dec(e.get("value"))))
        if v is None:
            errs.append(f"number {e.get('kpi_id')}={e.get('value')} is not a value of the KPI table")
            continue
        if e.get("unit") not in (None, v.unit):
            errs.append(f"unit of {v.key} must be {v.unit}")
        entries.append(v)
    tokens = N.extract(text)
    if len(tokens) > 4:
        errs.append("at most 4 numbers per fact")
    cores = {F.core(v.display) for v in entries}
    for sp in tokens:
        c = F.core(sp.text)
        if c not in cores:
            errs.append(f"token '{sp.text}' is not the display of a numbers[] entry")
    token_cores = [F.core(sp.text) for sp in tokens]
    for v in entries:
        if F.core(v.display) not in token_cores:
            errs.append(f"numbers[] entry {v.key} ({v.display}) is not in the text")
        if v.signed and F.dec(v.value) != 0:
            want = "up" if F.dec(v.value) > 0 else "down"
            got = _direction_near(text, v.display)
            if got and got != want:
                errs.append(f"direction of {v.key} must be {'subió' if want == 'up' else 'bajó'}")
    if NUMBER_WORDS.search(text):
        errs.append("numbers must be written as digits")
    for sp in tokens:
        window = text[max(0, sp.start - 30): sp.start + len(sp.text) + 30]
        v = next((x for x in entries if F.core(x.display) == F.core(sp.text)), None)
        if v and v.unit == "money" and HR_WORDS.search(window):
            errs.append("no HR category next to an amount")
    if re.search(r"customer_id|cliente\s+\d", text, re.I):
        errs.append("no customer-level content")
    for m in DATE_RX.finditer(text):
        if m.group(0).lower() not in {d.lower() for d in cand.dates}:
            errs.append(f"date '{m.group(0)}' is not a period of the cited KPIs")
    if re.search(r"gracias a|por el gasto|caus[óo]", text, re.I):
        errs.append("no causal verb linking spend to customers")
    return errs


def _direction_near(text: str, display: str) -> str | None:
    """The direction word nearest to the figure: 6 words before, then 3 after."""
    i = text.find(display.split(" ")[0])
    if i < 0:
        return None
    before = re.findall(r"[\wáéíóúñ]+", text[:i])[-6:]
    after = re.findall(r"[\wáéíóúñ]+", text[i + len(display):])[:3]
    for w in reversed(before):
        if DOWN_WORDS.match(w):
            return "down"
        if UP_WORDS.match(w):
            return "up"
    for w in after:
        if DOWN_WORDS.match(w):
            return "down"
        if UP_WORDS.match(w):
            return "up"
    return None


# ---------------------------------------------------------------------------- #
# 2 + 4. Kimi, then the fallback chain                                          #
# ---------------------------------------------------------------------------- #

BRIEFING_PROMPT = """Piensa poco y responde directo. Eres el analista de Finora que escribe el resumen hablado de cada actualización de datos, en español, para un agente de voz. Llamas a submit_briefing una vez con 5 a 8 hechos elegidos de la tabla de KPI candidatos. Reglas obligatorias:
1. Cubre las tres páginas: al menos 1 hecho de dq, 1 de acquisition y 1 de mrr.
2. Orden: primero las palancas (lever), luego el estado (state), luego la confianza (trust), al final como máximo 1 resultado nulo (null). B01 es obligatorio y va primero. B11 solo puede ir si también va B01 o B04.
3. Máximo 35 palabras y 4 números por hecho. Cada número escrito en cifras con notación española: "." para miles, "," para decimales, " %" con espacio, "millones" para montos de un millón o más, exactamente como la columna display. Nada de números en palabras (salvo "un/una" como artículo).
4. Cada número del texto debe estar en numbers[] con su kpi_id, su value exacto y su unit, tal como en la tabla; y cada entrada de numbers[] debe aparecer en el texto. No calcules ni redondees números nuevos.
5. Los cambios negativos se dicen con el valor absoluto y un verbo de dirección (bajó, cayó, restó, menos); los positivos con subió, creció, aumentó, más.
6. Nada de clientes individuales, nada de montos de personal (equipo, nómina, freelance), ningún verbo causal entre gasto y clientes ("gracias a", "por el gasto", "causó").
7. Nombra la evidencia cuando no es observado: "estimado", "supuesto", "provisional".
8. Puedes reformular la plantilla (template_es) para que suene natural, pero si dudas, úsala tal cual.
"""


def _brief_tool() -> dict:
    return bedrock.tool_spec("submit_briefing", "Publica los hechos del resumen.", {
        "type": "object", "required": ["facts"], "properties": {"facts": {
            "type": "array", "minItems": 5, "maxItems": 8, "items": {
                "type": "object", "required": ["candidate_id", "page", "kpi_ids", "text_es", "numbers"],
                "properties": {
                    "candidate_id": {"type": "string"}, "page": {"type": "string", "enum": ["dq", "acquisition", "mrr"]},
                    "kpi_ids": {"type": "array", "items": {"type": "string"}}, "text_es": {"type": "string"},
                    "numbers": {"type": "array", "items": {"type": "object", "required": ["kpi_id", "value", "unit"],
                                                           "properties": {"kpi_id": {"type": "string"},
                                                                          "value": {"type": "string"},
                                                                          "unit": {"type": "string"}}}}}}}}})


def _table_text(cands: list[Candidate]) -> str:
    rows = []
    for c in cands:
        rows.append({"candidate_id": c.candidate_id, "class": c.klass, "page": c.page, "kpi_ids": c.kpi_ids,
                     "evidence": c.evidence,
                     "values": [{"kpi_id": v.kpi_id, "value": v.value, "unit": v.unit, "display": v.display,
                                 "signed": v.signed} for v in c.values],
                     "template_es": c.template_es})
    return json.dumps(rows, ensure_ascii=False)


def _definitions(cands: list[Candidate]) -> str:
    seen = {m for c in cands for m in c.metrics}
    return json.dumps({m: C.METRICS[m].definition_es for m in sorted(seen) if m in C.METRICS}, ensure_ascii=False)


@dataclass
class Briefing:
    facts: list
    status: str
    stats: dict
    definitions: list
    caveats: list


def generate(cands: list[Candidate], ask_model: Callable[[str, str], dict] | None = None,
             log: Callable[..., None] = lambda *a, **k: None) -> Briefing:
    """Kimi chooses and phrases; code verifies (§4.3-4.5)."""
    by_id = {c.candidate_id: c for c in cands}
    stats = {"generated": 0, "regenerated": 0, "replaced": 0, "dropped": 0, "model": "none"}
    model = ask_model or _ask_kimi
    user = ("Tabla de KPI candidatos (JSON):\n" + _table_text(cands) + "\nDefiniciones:\n" + _definitions(cands))
    facts: list[dict] = []
    try:
        got = model(BRIEFING_PROMPT, user)
        facts = [f for f in (got.get("facts") or []) if isinstance(f, dict)][:8]
        stats["model"] = bedrock.model_id()
    except bedrock.ModelError as err:
        log("briefing_model_failed", kind=err.kind)
    stats["generated"] = len(facts)
    chosen: dict[str, dict] = {}
    failed: dict[str, list[str]] = {}
    for f in facts:
        cid = f.get("candidate_id")
        cand = by_id.get(cid)
        if not cand or cid in chosen:
            continue
        errs = check_fact(f, cand)
        if errs:
            failed[cid] = errs
            chosen[cid] = None  # placeholder keeps Kimi's choice
        else:
            chosen[cid] = {**f, "source": "model"}
    if failed and stats["model"] != "none":
        stats["regenerated"] = len(failed)
        retry_user = user + "\nEstos hechos fallaron la verificación; reescríbelos (mismos candidate_id): " + \
            json.dumps(failed, ensure_ascii=False)
        try:
            got = model(BRIEFING_PROMPT, retry_user)
            for f in got.get("facts") or []:
                cid = f.get("candidate_id") if isinstance(f, dict) else None
                if cid in failed and not check_fact(f, by_id[cid]):
                    chosen[cid] = {**f, "source": "model"}
                    failed.pop(cid)
        except bedrock.ModelError as err:
            log("briefing_model_failed", kind=err.kind, attempt=2)
    for cid, errs in failed.items():
        cand = by_id[cid]
        stats["replaced"] += 1
        log("briefing_fact_replaced", candidate_id=cid, token=errs[0][:120])
        chosen[cid] = _template_fact(cand)
    # rule 2: B01 first and mandatory while it exists
    if "B01" in by_id and "B01" not in chosen:
        chosen["B01"] = _template_fact(by_id["B01"])
    out = [f for f in chosen.values() if f]
    # coverage, null rules, fill to 5 (§4.3 order), at most 8
    out = _enforce(out, by_id, stats, log)
    status = "ok" if len(out) >= 5 else "degraded"
    for f in out:
        f["evidence"] = by_id[f["candidate_id"]].evidence
        f["id"] = by_id[f["candidate_id"]].slug
    cited = [by_id[f["candidate_id"]] for f in out]
    definitions = [{"metric_id": m, "text_es": C.METRICS[m].definition_es}
                   for m in dict.fromkeys(m for c in cited for m in c.metrics) if m in C.METRICS]
    cav_ids = [x for x in C.CAVEAT_ORDER if any(x in c.caveats for c in cited)]
    caveats = [{"caveat_id": x, "text_es": C.CAVEATS[x]} for x in cav_ids if "{" not in C.CAVEATS[x]]
    return Briefing(out, status, stats, definitions, caveats)


def _template_fact(c: Candidate) -> dict:
    return {"candidate_id": c.candidate_id, "page": c.page, "kpi_ids": c.kpi_ids, "text_es": c.template_es,
            "numbers": [{"kpi_id": v.kpi_id, "value": v.value, "unit": v.unit} for v in c.values], "source": "template"}


def _enforce(facts: list[dict], by_id: dict, stats: dict, log) -> list[dict]:
    def key(f):
        c = by_id[f["candidate_id"]]
        return (0 if c.candidate_id == "B01" else 1, CLASS_ORDER[c.klass], -c.magnitude, c.candidate_id)
    facts = sorted(facts, key=key)
    nulls = [f for f in facts if by_id[f["candidate_id"]].klass == "null"]
    keep_null = None
    for f in nulls:
        if f["candidate_id"] == "B11" and not any(x["candidate_id"] in ("B01", "B04") for x in facts):
            continue
        keep_null = f
        break
    facts = [f for f in facts if by_id[f["candidate_id"]].klass != "null"]
    used = {f["candidate_id"] for f in facts}
    for page in ("dq", "acquisition", "mrr"):
        if not any(f["page"] == page for f in facts):
            add = next((c for c in by_id.values() if c.page == page and c.klass != "null" and c.candidate_id not in used),
                       None)
            if add:
                facts.append(_template_fact(add))
                used.add(add.candidate_id)
    for c in sorted(by_id.values(), key=lambda c: (CLASS_ORDER[c.klass], c.candidate_id)):
        if len(facts) + (1 if keep_null else 0) >= 5:
            break
        if c.candidate_id not in used and c.klass != "null":
            facts.append(_template_fact(c))
            used.add(c.candidate_id)
    facts = sorted(facts, key=key)[: 8 - (1 if keep_null else 0)]
    if keep_null is None and len(facts) < 5:
        keep_null = next((_template_fact(c) for c in by_id.values() if c.klass == "null" and c.candidate_id != "B11"),
                         None)
    if keep_null:
        facts.append(keep_null)
    for f in facts:
        cand = by_id[f["candidate_id"]]
        if f["source"] == "template" and check_fact(f, cand):
            stats["dropped"] += 1
            log("briefing_fact_dropped", candidate_id=cand.candidate_id, reason=check_fact(f, cand)[0][:120])
    return [f for f in facts if f["source"] != "template" or not check_fact(f, by_id[f["candidate_id"]])]


def _ask_kimi(system: str, user: str) -> dict:
    got = bedrock.call_tool(system, user, _brief_tool(), max_tokens=16000, timeout_s=120, log_event="kimi.briefing")
    if isinstance(got.get("facts"), str):
        try:
            got["facts"] = json.loads(got["facts"])
        except ValueError:
            got["facts"] = []
    return got


def document(b: Briefing, ctx: K.Context, refreshed_at: str) -> dict:
    """The contract v1.1 shape (plus run metadata)."""
    return {"as_of_month": ctx.data_complete_through, "refreshed_at": refreshed_at, "status": b.status,
            "gold_run_id": ctx.gold_run_id, "dq_run_id": ctx.dq_run_id, "catalog_version": C.VERSION,
            "facts": [{k: f[k] for k in ("id", "candidate_id", "page", "kpi_ids", "text_es", "numbers", "evidence",
                                         "source")} for f in b.facts],
            "definitions": b.definitions, "caveats": b.caveats, "stats": b.stats}
