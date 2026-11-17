import hashlib
from pathlib import Path

from common import config
from common.records import make_bronze, strip_bronze
from silver_build.engine import DatasetInput, build

ROOT = Path(__file__).resolve().parents[2]
FILES = {"transactions": ("transactions/Transactions.csv", "Transactions.csv"),
         "industry": ("industry/Industry.csv", "Industry.csv"),
         "sm_spend": ("s_and_m/S&M_spend.csv", "S&M_spend.csv")}
TS = "2026-11-16T04:10:00Z"


def inputs_from(data: dict[str, bytes]):
    out = {}
    for ds, raw in data.items():
        bronze = make_bronze(raw, TS)
        staging, _ = strip_bronze(bronze) if bronze else (b"", [])
        out[ds] = DatasetInput(staging=staging, source_key=FILES[ds][0],
                               sha256=hashlib.sha256(raw).hexdigest(), ingested_at=TS)
    return out


def golden_inputs():
    return inputs_from({ds: (ROOT / "data" / f).read_bytes() for ds, (_, f) in FILES.items()})


def run(data=None, previous=None, run_id="r20261116T041000Z"):
    cfg = config.load()
    return build(inputs_from(data) if data is not None else golden_inputs(), cfg, run_id, previous), cfg
