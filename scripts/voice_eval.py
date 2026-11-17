#!/usr/bin/env python3
"""The CDO's 20-question eval (docs/semantic_layer.md §5) against real Kimi K3.

    python scripts/voice_eval.py --lambda   # the deployed finora-dq-agent (IAM direct invoke)
    python scripts/voice_eval.py --local    # the same code in-process (real Kimi K3 + Athena)

Scoring (§5): the spec must match on intent, reason_code, metric set, dimensions, time
window and won_definition (sort and chart are advisory); the spoken answer (summary_es +
the first caveat, or reason_es + alternative_es) must contain the required figures as
exact display strings and no figure outside the allowed set; the mandatory caveats must
be attached. Writes evidence/voice_eval/<timestamp>.json. Never prints a credential.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "voice"))

from agentlib import catalog as C  # noqa: E402
from agentlib import compiler as K  # noqa: E402
from agentlib import fmt as F  # noqa: E402
from agentlib import numbers as N  # noqa: E402

LAT = "latest_month"
# n: (question, role(s), follow-up of, expected)
CASES = {
    1: ("¿Qué conjunto de datos tiene peor calidad hoy?", ["revops"], None,
        dict(intent="answer", metrics={"dq.row_compliance_pct", "dq.rows_excluded"}, dims={"dataset"},
             req=["99,95 %", "1"], allow=[], caveats=[])),
    2: ("¿Qué reglas de calidad están en advertencia?", ["revops"], None,
        dict(intent="answer", metrics={"dq.rule_failed_count"}, dims={"rule", "dataset"},
             req=["3", "22", "5", "1"], allow=["0"], caveats=[])),
    3: ("¿Cuántos clientes nuevos ganamos en 2022?", ["revops"], None,
        dict(intent="answer", metrics={"acq.won_count"}, dims=set(), time=("2022-01", "2022-12", None),
             req=["380"], allow=["11"], caveats=["C-PARTIAL"], wd="first_payment")),
    4: ("¿Y sin los que probablemente ya estaban activos?", ["revops"], 3,
        dict(intent="answer", metrics={"acq.won_count"}, dims=set(), time=("2022-01", "2022-12", None),
             req=["337"], allow=["43", "11"], caveats=["C-PARTIAL"], wd="new_logo")),
    5: ("¿Cuánto paga al mes un cliente nuevo hoy comparado con antes?", ["revops"], None,
        dict(intent="answer", metrics={"acq.run_rate_per_won"}, dims={"period"}, derived="growth",
             req=["55.768", "42.551", "23,7 %"], allow=[], caveats=["C-REGIME", "C-IMMATURE"])),
    6: ("¿Qué industria bajó más su ticket?", ["revops"], None,
        dict(intent="answer", metrics={"acq.run_rate_per_won"}, dims={"industry", "period"}, derived="growth",
             req=["43.671", "29.407", "32,7 %"], allow=[], caveats=["C-REGIME"])),
    7: ("¿Cuál es el payback de un cliente nuevo y cuánto nos cuesta?", ["revops"], None,
        dict(intent="answer", metrics={"acq.payback_months", "acq.cost_per_won"}, dims={"period"},
             req=["71,6", "3,05 millones", "136,1", "7,59 millones"], allow=[],
             caveats=["C-PAYBACK", "C-NOT-CAC", "C-REGIME"])),
    8: ("¿Qué porcentaje de los clientes nuevos sigue pagando al mes 12?", ["revops"], None,
        dict(intent="answer", metrics={"acq.paying_m12_share"}, dims={"period"},
             req=["90,0 %", "87,1 %"], allow=["332", "369", "528", "606"], caveats=["C-RETENTION"])),
    9: ("Si pasamos 10 puntos de clientes nuevos de Retail a Tecnología, ¿qué pasa con el MRR nuevo?", ["revops"], None,
        dict(intent="answer", metrics={"acq.new_mrr_per_month", "acq.run_rate_per_won", "acq.payback_months"},
             derived="lever_scenario", req=["2,45 millones", "2,59 millones", "44.998", "67,7"], allow=["2.447", "10"],
             caveats=["C-MIX"])),
    10: ("¿Cuánto gastamos en el equipo de S&M en 2023?", ["finance", "revops"], None,
         dict(intent="out_of_scope", reason="hr_restricted", req=[], allow=[])),
    11: ("¿Cuál es el MRR a octubre de 2024?", ["revops"], None,
         dict(intent="answer", metrics={"mrr.closing", "mrr.paying_customers"}, dims=set(),
              time=("2024-10", "2024-10", None), req=["96,4 millones", "1.678"], allow=[],
              caveats=["C-MRR-PROXY", "C-PROV"])),
    12: ("¿Cuánto MRR perdimos por bajas en 2024?", ["revops"], None,
         dict(intent="answer", metrics={"mrr.line_amount", "mrr.line_events"}, time=("2024-01", "2024-10", None),
              req=["11,7 millones", "110"], allow=["0", "10"], caveats=["C-MRR-PROXY", "C-PROV", "C-PARTIAL"])),
    13: ("¿Qué industria aporta más MRR hoy?", ["revops"], None,
         dict(intent="answer", metrics={"mrr.closing", "mrr.paying_customers"}, dims={"industry"},
              time=("2024-10", "2024-10", None), req=["31,2 millones", "32,4 %", "459"], allow=[],
              caveats=["C-MRR-PROXY", "C-PROV"])),
    14: ("¿Cuál es el cliente que más paga?", ["revops"], None,
         dict(intent="out_of_scope", reason="customer_level", req=[], allow=["57.426", "74.192"])),
    15: ("Si invertimos 20 % más en medios pagados, ¿cuántos clientes más ganamos?", ["revops"], None,
         dict(intent="out_of_scope", reason="causal_spend_won", req=[], allow=["3", "44", "2,2"])),
    16: ("¿En qué etapa del embudo perdemos más clientes?", ["revops"], None,
         dict(intent="out_of_scope", reason="funnel_stage_observed", req=[], allow=[])),
    17: ("¿Cuánto MRR perdemos por descuentos?", ["revops"], None,
         dict(intent="out_of_scope", reason="discounts_billing", req=[], allow=["31", "1,10 millones"])),
    18: ("¿Cuánto es eso en dólares?", ["revops"], None,
         dict(intent="out_of_scope", reason="currency", req=[], allow=[])),
    19: ("¿Cuánto gana el gerente de marketing?", ["revops", "finance"], None,
         dict(intent="out_of_scope", reason="single_person_pay", req=[], allow=[])),
    20: ("¿Cuántos clientes nuevos tuvimos en noviembre de 2024?", ["revops"], None,
         dict(intent="out_of_scope", reason="beyond_data_complete_through", req=[], allow=["50"])),
}


def spoken(reply: dict) -> str:
    if reply.get("status") == "answered":
        cav = (reply.get("caveats_es") or [])[:1]
        return " ".join([reply.get("summary_es", "")] + cav)
    return " ".join([reply.get("reason_es", ""), reply.get("alternative_es", "")])


def figures(text: str) -> list[str]:
    return [F.core(sp.text) for sp in N.extract(text)]


def score(n: int, role: str, reply: dict, ctx: K.Context) -> dict:
    exp = CASES[n][3]
    fails: list[str] = []
    spec = reply.get("spec") or {}
    status = reply.get("status")
    intent = "out_of_scope" if status == "out_of_scope" else "answer" if status == "answered" else status
    if intent != exp["intent"]:
        fails.append(f"intent {intent} != {exp['intent']}")
    if exp["intent"] == "out_of_scope" and reply.get("reason_code") != exp.get("reason"):
        fails.append(f"reason_code {reply.get('reason_code')} != {exp.get('reason')}")
    comp = None
    if exp["intent"] == "answer" and status == "answered":
        try:
            comp = K.compile_spec(K.validate(spec), role, ctx)
        except (K.CompileError, K.OutOfScope) as err:
            fails.append(f"recompile: {err}")
        if set(spec.get("metrics") or []) != exp["metrics"]:
            fails.append(f"metrics {sorted(spec.get('metrics') or [])} != {sorted(exp['metrics'])}")
        if comp and "dims" in exp and set(d for d in comp.dims if d != "method") != exp["dims"] and \
                not (exp.get("derived") == "growth" and set(comp.dims) - {"period"} == exp["dims"] - {"period"}):
            fails.append(f"dimensions {comp.dims} != {sorted(exp['dims'])}")
        if exp.get("derived") and ((spec.get("derived") or [{}])[0].get("op") != exp["derived"]):
            fails.append(f"derived {(spec.get('derived') or [{}])[0].get('op')} != {exp['derived']}")
        if comp and "time" in exp:
            t = comp.time
            got = (t["months"][0] if t.get("months") else None, t["months"][-1] if t.get("months") else None,
                   t.get("period_code"))
            if (got[0], got[1]) != exp["time"][:2]:
                fails.append(f"time {got} != {exp['time']}")
        if exp.get("wd") and spec.get("won_definition", "first_payment") != exp["wd"]:
            fails.append(f"won_definition {spec.get('won_definition')} != {exp['wd']}")
        if comp:
            missing = [c for c in exp.get("caveats", []) if c not in comp.caveats and
                       not (c == "C-PARTIAL" and any("meses de datos" in x for x in reply.get("caveats_es") or []))]
            if missing:
                fails.append(f"caveats missing {missing}")
    text = spoken(reply)
    got = figures(text)
    req = [F.core(x) for x in exp["req"]]
    allow = set(req) | {F.core(x) for x in exp["allow"]}
    for r in req:
        if r not in got:
            fails.append(f"figure {r[0]}{' ' + r[1] if r[1] else ''} missing")
    extra = [g for g in got if g not in allow and (g[0], "") not in allow]
    if extra:
        fails.append(f"unexpected figures {extra}")
    return {"n": n, "role": role, "question": CASES[n][0], "status": status, "pass": not fails, "fails": fails,
            "spoken": text, "spec": spec, "reason_code": reply.get("reason_code"), "evidence": reply.get("evidence"),
            "kpi_ids": reply.get("kpi_ids"), "result_id": reply.get("result_id"), "ms": reply.get("_ms")}


def run_lambda(question, role, prev_id, fn, client):
    t = time.monotonic()
    r = client.invoke(FunctionName=fn, Payload=json.dumps({"source": "finora.voice-eval", "question": question,
                                                           "role": role, "previous_result_id": prev_id}).encode())
    out = json.loads(r["Payload"].read() or b"{}")
    out["_ms"] = int((time.monotonic() - t) * 1000)
    return out


def run_local(question, role, prev, ctx):
    from agentlib import ask as A, context as CTX
    t = time.monotonic()
    deadline = t + 20
    o = A.plan(question, role, ctx, prev, deadline)
    out = {"spec": o.spec, "_ms": None}
    if o.status == "error":
        out.update({"status": "error", "reason_es": o.reason_es})
    elif o.status == "out_of_scope":
        out.update({"status": "out_of_scope", **A.oos_payload(o, role, ctx, lambda c: A.run_sync(
            c, ctx, time.monotonic() + 10, lambda: CTX.dq_snapshot(ctx)))})
    else:
        table = A.run_sync(o.compiled, ctx, deadline + 5, lambda: CTX.dq_snapshot(ctx))
        if table is None:
            out.update({"status": "pending"})
        else:
            out.update({"status": "answered", **A.answer_payload(o.compiled, table, ctx)})
    out["_ms"] = int((time.monotonic() - t) * 1000)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--lambda", dest="lam", action="store_true")
    g.add_argument("--local", action="store_true")
    ap.add_argument("--only", type=int, nargs="*")
    ap.add_argument("--function", default="finora-dq-agent")
    a = ap.parse_args()
    os.environ.setdefault("AWS_PROFILE", "alegra-test")
    os.environ.update({"AWS_DEFAULT_REGION": "us-west-2", "SERVING_BUCKET": "al-test-dl-serving",
                       "GOLD_BUCKET": "al-test-dl-gold", "ATHENA_WORKGROUP": "finora-dl"})
    import boto3
    from agentlib import context as CTX
    ctx = CTX.load()
    client = boto3.client("lambda", region_name="us-west-2") if a.lam else None
    results, prev_ids, prev_local = [], {}, {}
    for n in (a.only or sorted(CASES)):
        q, roles, follow, _ = CASES[n]
        for role in roles:
            if a.lam:
                reply = run_lambda(q, role, prev_ids.get(follow), a.function, client)
            else:
                reply = run_local(q, role, prev_local.get(follow), ctx)
            s = score(n, role, reply, ctx)
            results.append(s)
            prev_ids[n] = reply.get("result_id")
            prev_local[n] = {"spec": json.dumps(reply.get("spec")), "summary_es": reply.get("summary_es", ""),
                             "status": "answered"}
            print(f"#{n:>2} {role:<7} {'PASS' if s['pass'] else 'FAIL'} {s['ms']} ms | {s['spoken'][:150]}"
                  + ("" if s["pass"] else f"\n      -> {s['fails']}"))
    passed = sum(1 for r in results if r["pass"])
    print(f"\n{passed}/{len(results)} passed ({'deployed Lambda' if a.lam else 'local'}, gold {ctx.gold_run_id}, "
          f"catalog {C.VERSION})")
    out = ROOT / "evidence" / "voice_eval"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out / f"{stamp}_{'lambda' if a.lam else 'local'}.json").write_text(json.dumps(
        {"gold_run_id": ctx.gold_run_id, "catalog_version": C.VERSION, "mode": "lambda" if a.lam else "local",
         "passed": passed, "total": len(results), "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
