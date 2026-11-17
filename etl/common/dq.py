"""DQ metrics (approved_data_rules.md § DQ metric definitions) and DQ records.

The ETL computes every number; the dashboard computes nothing.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from common.dec import pct

MAX_CHARS = 1000
TRUNC = "…[truncated]"


def _cap(v: str) -> str:
    return v if len(v) <= MAX_CHARS else v[:MAX_CHARS] + TRUNC


def status_of(rule: dict, ds: str, ev: int, failed: int, cfg: dict) -> str:
    if ds not in rule["applies_to"] or ev == 0:
        return "na"
    if failed == 0:
        return "pass"
    _, raw = pct(ev, failed)
    warn_min = Decimal(str(cfg["dq"]["status_warn_min_pct"]))
    if not rule["counts_toward_compliance"] or raw >= warn_min:
        return "warn"
    return "fail"


def dashboard_rules(cfg: dict) -> list[dict]:
    return [r for r in cfg["rule_catalog"] if r["kind"] in ("row", "finding")]


def records_for(res: dict, cfg: dict) -> dict[tuple[str, str], list[dict]]:
    """{(rule_id, dataset_id): [record]} for every dashboard rule x applicable dataset."""
    reg = cfg["datasets"]
    order_idx = {r["id"]: i for i, r in enumerate(cfg["rule_catalog"])}
    out: dict[tuple[str, str], list[dict]] = {}
    for rule in dashboard_rules(cfg):
        for ds in rule["applies_to"]:
            out[(rule["id"], ds)] = []
    for ds in cfg["dataset_order"]:
        cols = reg[ds]["columns"]
        keys = reg[ds]["key_columns"]
        for r in res["rows"][ds]:
            if not r.hits:
                continue
            ids = []
            for h in r.hits:
                if h.rule_id not in ids:
                    ids.append(h.rule_id)
            ids.sort(key=lambda x: order_idx.get(x, 999))
            for h in r.hits:
                bucket = out.get((h.rule_id, ds))
                if bucket is None:
                    continue
                bucket.append({
                    "source_line": r.source_line,
                    "key": {k: _cap(r.values.get(k, "")) for k in keys},
                    "values": {c: _cap(r.values.get(c, "")) for c in cols},
                    "failed_columns": list(h.failed_columns),
                    "reason": h.reason,
                    "action": h.action,
                    "other_failed_rules": [x for x in ids if x != h.rule_id],
                })
    for f in res["findings"]:
        bucket = out.get((f["rule_id"], f["dataset"]))
        if bucket is not None:
            bucket.append({"source_line": None, "key": f["key"], "values": {}, "failed_columns": [],
                           "reason": f["reason"], "action": "finding", "other_failed_rules": []})
    return out


def summarize(res: dict, cfg: dict, run: dict) -> dict:
    """The summary.json payload, without `trend` (dq_publish adds it)."""
    cnt = res["counter"]
    order = cfg["dataset_order"]
    rules_out = []
    for rule in dashboard_rules(cfg):
        results = {}
        for ds in order:
            if ds in rule["applies_to"]:
                ev, fl = cnt.ev.get((rule["id"], ds), 0), cnt.fail.get((rule["id"], ds), 0)
            else:
                ev, fl = 0, 0
            published, _ = pct(ev, fl)
            results[ds] = {"evaluated": ev, "failed": fl, "compliance_pct": published,
                           "status": status_of(rule, ds, ev, fl, cfg)}
        rules_out.append({
            "rule_id": rule["id"], "title": rule["title"], "description": rule.get("description", ""),
            "layer": rule["layer"], "kind": rule["kind"], "action": rule["action"],
            "inferred": rule["inferred"], "counts_toward_compliance": rule["counts_toward_compliance"],
            "applies_to": rule["applies_to"], "results": results,
        })
    row_flag_rules = {r["id"] for r in dashboard_rules(cfg) if r["kind"] == "row" and r["action"] == "flag"}
    datasets = []
    for ds in order:
        rows = res["rows"][ds]
        read = len(rows)
        excluded = sum(1 for r in rows if r.excluded)
        flagged = sum(1 for r in rows if not r.excluded and any(h.rule_id in row_flag_rules for h in r.hits))
        published, raw = pct(read, excluded)
        counted = [r for r in rules_out if r["counts_toward_compliance"] and ds in r["applies_to"]
                   and r["results"][ds]["evaluated"] > 0]
        datasets.append({
            "dataset_id": ds, "label": cfg["datasets"][ds]["label"], "rows_read": read,
            "rows_excluded": excluded, "rows_flagged": flagged, "row_compliance_pct": published,
            "rules_evaluated": len(counted),
            "rules_failing": sum(1 for r in counted if r["results"][ds]["failed"] > 0),
            "_raw": raw,
        })
    fixed = {ds: i for i, ds in enumerate(order)}

    def sort_key(d: dict) -> tuple:
        raw = d["_raw"]
        flag_ratio = Decimal(d["rows_flagged"]) / Decimal(d["rows_read"]) if d["rows_read"] else Decimal(0)
        return (raw is None, -(raw or Decimal(0)), d["rules_failing"], flag_ratio, fixed[d["dataset_id"]])

    datasets.sort(key=sort_key)
    for i, d in enumerate(datasets, start=1):
        d["rank"] = i
        d.pop("_raw")
    return {"run": run, "datasets": datasets, "rules": rules_out}


def hr_split(ds: str, values: dict[str, str], hr_cols: set[str], restricted: str) -> tuple[dict, dict]:
    """(values with HR columns masked, the HR columns only). Only sm_spend has HR columns."""
    if ds != "sm_spend":
        return values, {}
    masked = {c: (restricted if c in hr_cols else v) for c, v in values.items()}
    hr = {c: v for c, v in values.items() if c in hr_cols}
    return masked, hr


def dq_store_rows(res: dict, cfg: dict, records: dict[tuple[str, str], list[dict]]) -> dict[str, Any]:
    """Rows for the DQ Parquet store. HR-sensitive values sit only in the
    hr_sensitive=true partition (CDO-11); the general partition carries them as
    `__restricted__`."""
    p11 = cfg["rules_by_id"]["CDO-11"]["params"]
    hr_cols, restricted = set(p11["hr_sensitive_columns"]), p11["restricted_value"]
    lin = res["lineage"]
    act = {"exclude": "excluded", "flag": "flagged", "finding": "finding"}
    findings = {False: [], True: []}
    for (rule_id, ds), recs in records.items():
        for rec in recs:
            raw = {c: rec["values"].get(c, "") for c in rec["failed_columns"]} if rec["values"] else {}
            masked, hr = hr_split(ds, raw, hr_cols, restricted)
            base = {"rule_id": rule_id, "dataset_id": ds, "action": act[rec["action"]],
                    "source_line": rec["source_line"], "key_json": json.dumps(rec["key"], ensure_ascii=False),
                    "failed_columns": rec["failed_columns"], "reason": rec["reason"],
                    **{k: v for k, v in lin[ds].items() if k != "_source_line"}}
            findings[False].append({**base, "raw_values_json": json.dumps(masked, ensure_ascii=False)})
            if hr:
                findings[True].append({**base, "raw_values_json": json.dumps(hr, ensure_ascii=False)})
    excluded: dict[str, dict[bool, list]] = {ds: {False: [], True: []} for ds in cfg["dataset_order"]}
    for ds in cfg["dataset_order"]:
        keys = cfg["datasets"][ds]["key_columns"]
        cols = cfg["datasets"][ds]["columns"]
        for r in res["rows"][ds]:
            if not r.excluded:
                continue
            values = {c: _cap(r.values.get(c, "")) for c in cols}
            masked, hr = hr_split(ds, values, hr_cols, restricted)
            failed = []
            for h in r.hits:
                if h.rule_id not in failed:
                    failed.append(h.rule_id)
            base = {"dataset_id": ds, "source_line": r.source_line,
                    "key_json": json.dumps({k: values.get(k, "") for k in keys}, ensure_ascii=False),
                    "failed_rules": failed,
                    "reasons_json": json.dumps([{"rule_id": h.rule_id, "reason": h.reason,
                                                 "failed_columns": h.failed_columns} for h in r.hits]),
                    **lin[ds]}
            excluded[ds][False].append({**base, "values_json": json.dumps(masked, ensure_ascii=False)})
            if hr:
                excluded[ds][True].append({**base, "values_json": json.dumps(hr, ensure_ascii=False)})
    return {"findings": findings, "excluded": excluded}
