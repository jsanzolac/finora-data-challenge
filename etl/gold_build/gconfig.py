"""Gold config loader. etl/config/gold_acquisition.json is generated with the
YAML by etl/config/build_gold_yaml.py from docs/gold_acquisition_model.md. In
the Glue library zip it is gold_build/gold_acquisition.json, read with pkgutil."""

from __future__ import annotations

import json
import os
import pkgutil
from functools import lru_cache
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / "config" / "gold_acquisition.json"


@lru_cache(maxsize=1)
def load() -> dict:
    env = os.environ.get("GOLD_CONFIG_PATH")
    if env:
        text = Path(env).read_text(encoding="utf-8")
    elif _DEFAULT.exists():
        text = _DEFAULT.read_text(encoding="utf-8")
    else:
        data = pkgutil.get_data("gold_build", "gold_acquisition.json")
        if data is None:
            raise FileNotFoundError("gold_acquisition.json is not packaged with gold_build/")
        text = data.decode("utf-8")
    cfg = json.loads(text)
    cfg["stage_codes"] = [s["stage_code"] for s in cfg["stages"]]
    cfg["transitions"] = [(s["stage_code"], s["next_stage_code"]) for s in cfg["stages"] if s["next_stage_code"]]
    cfg["industry_by_code"] = {i["industry_code"]: i for i in cfg["industries"]}
    cfg["category_by_code"] = {c["category_code"]: c for c in cfg["spend_categories"]}
    return cfg
