"""Rules config loader. The JSON is generated with the YAML by
etl/config/build_rules_yaml.py (the job runtime needs no PyYAML).

In the repo the file is etl/config/dl_rules.json. In the Glue library zip it is
common/dl_rules.json, read with pkgutil because the zip is imported, not
extracted."""

from __future__ import annotations

import json
import os
import pkgutil
from functools import lru_cache
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / "config" / "dl_rules.json"


def _read_default() -> str:
    if _DEFAULT.exists():
        return _DEFAULT.read_text(encoding="utf-8")
    data = pkgutil.get_data("common", "dl_rules.json")
    if data is None:
        raise FileNotFoundError("dl_rules.json is not packaged with common/")
    return data.decode("utf-8")


@lru_cache(maxsize=1)
def load() -> dict:
    env = os.environ.get("DL_RULES_PATH")
    cfg = json.loads(Path(env).read_text(encoding="utf-8") if env else _read_default())
    cfg["rules_by_id"] = {r["id"]: r for r in cfg["rule_catalog"]}
    return cfg


def dataset_for_key(cfg: dict, key: str) -> str | None:
    """Map a staging key to its dataset id by registered prefix. The key is
    data: it is compared, never interpolated into a path or command."""
    for ds_id, ds in cfg["datasets"].items():
        if key.startswith(ds["staging_prefix"]):
            return ds_id
    return None
