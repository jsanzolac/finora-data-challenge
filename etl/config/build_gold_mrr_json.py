"""Generate etl/config/gold_mrr.json, the gold MRR model config, from
docs/mrr_discounts_model.md §6 (Gold build spec, CDO, 2026-11-17).

The line domain (§6.3), the classification parameters (§6.4) and the industry
keys (conformed with the acquisition model: the same seed as
gold_acquisition.json, so industry_key joins finora_gold.dim_industry) are
written here once. `_gold_model_version` of every MRR row is the SHA-256 of the
generated JSON (without that field), and `spec_sha256` pins the version of the
CDO document it was built from (a test fails if the document changes).

Run: python3 etl/config/build_gold_mrr_json.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "mrr_discounts_model.md"
OUT = Path(__file__).resolve().parent / "gold_mrr.json"
ACQ = Path(__file__).resolve().parent / "gold_acquisition.json"

# (line, line_order, section, driver, label, observable on cash_proxy, inferred) -- §6.3 / §6.4
LINES = [
    ("opening", 0, "mrr", None, "Opening MRR", True, False),
    ("new", 1, "mrr", "behaviour", "New", True, False),
    ("reactivation", 2, "mrr", "behaviour", "Reactivation", True, False),
    ("expansion", 3, "mrr", "behaviour", "Expansion", True, False),
    ("contraction", 4, "mrr", "behaviour", "Contraction", True, False),
    ("churn", 5, "mrr", "behaviour", "Churn", True, False),
    ("pause", 6, "mrr", "behaviour", "Pause (unpaid, not churn)", True, True),
    ("resume", 7, "mrr", "behaviour", "Resume after a pause", True, True),
    ("grace_drop", 8, "mrr", "behaviour", "Unpaid, in grace (provisional)", True, False),
    ("list_price_change", 9, "mrr", "pricing", "List-price changes", False, False),
    ("inferred_price_step", 10, "mrr", "pricing", "Price steps (inferred)", True, True),
    ("discount_start", 11, "mrr", "discount", "Discounts started", False, False),
    ("discount_change", 12, "mrr", "discount", "Discount changes", False, False),
    ("discount_base_effect", 13, "mrr", "discount", "Discount base effect", False, False),
    ("discount_end", 14, "mrr", "discount", "Discounts ended", False, False),
    ("discount_released_on_churn", 15, "mrr", "discount", "Discounts released on churn", False, False),
    ("first_payment_multiple", 16, "mrr", "timing", "Prepaid first invoice (inferred)", True, True),
    ("closing", 17, "mrr", None, "Closing MRR", True, False),
    ("timing_arrears", 20, "cash", "timing", "Arrears (paid later)", True, False),
    ("timing_prepay", 21, "cash", "timing", "Prepayments", True, False),
    ("timing_split", 22, "cash", "timing", "Split payments", True, False),
    ("timing_uneven_split", 23, "cash", "timing", "Uneven splits", True, False),
    ("timing_late_price_step", 24, "cash", "timing", "Late price step catch-up (inferred)", True, True),
    ("collected", 25, "cash", None, "Collected (cash)", True, False),
]

PARAMS = {
    "mrr_basis": "cash_proxy",
    "active_states": ["new", "paying", "reactivated", "settled_gap"],
    "price_step_states": ["paying"],            # GLD-MRR-01: all four window months
    "first_payment_multiples": [2, 3],           # GLD-MRR-02 7b, exact
    "flag_return_months": [1, 2, 3],             # GLD-MRR-03
    "timing_types": ["arrears", "prepay", "split", "uneven_split", "late_price_step"],
    "no_item": "-",                              # item_id / discount_id today (PK members, not NULL)
    "null_reason_cash_proxy": "no_billing_data",
    "page_size": 200,                            # serving movement pages (contract v1 decision 5)
}

INFERENCE_RULE = {"pause": "GLD-MRR-02.pause", "resume": "GLD-MRR-02.resume",
                  "inferred_price_step": "GLD-MRR-01", "first_payment_multiple": "GLD-MRR-02.7b"}


def build() -> dict:
    acq = json.loads(ACQ.read_text(encoding="utf-8"))
    cfg = {
        "version": 1,
        "model_doc": "docs/mrr_discounts_model.md §6",
        "spec_sha256": hashlib.sha256(DOC.read_bytes()).hexdigest(),
        "database": "finora_gold",
        "lines": [{"line": n, "line_order": o, "section": s, "driver": d, "label": lb,
                   "observable_on_cash_proxy": obs, "is_inferred": inf,
                   "inference_rule": INFERENCE_RULE.get(n)} for n, o, s, d, lb, obs, inf in LINES],
        "params": PARAMS,
        "industries": [{"industry_key": i["industry_key"], "industry_code": i["industry_code"]}
                       for i in acq["industries"]],
        "unmapped_industry_key": -2,
    }
    text = json.dumps(cfg, sort_keys=True, ensure_ascii=False, indent=1)
    cfg["gold_model_version"] = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    return cfg


if __name__ == "__main__":
    c = build()
    OUT.write_text(json.dumps(c, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({c['gold_model_version']})")
