#!/usr/bin/env python3
"""Finora DQ data lake: staging -> bronze -> silver + DQ store -> gold (AWS Glue), auth, DQ/acquisition API and hosting.

Account 962482423379, us-west-2. Import mode (`-c import_mode=true`) synthesizes
FinoraDlStorage with only the three existing buckets, exactly as they are today,
for `cdk import`. A normal synth adds versioning, notifications, policies,
lifecycle rules and the two new buckets.
"""

import shutil
import sys
from pathlib import Path

import aws_cdk as cdk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "etl"))
sys.path.insert(0, str(ROOT / "voice"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stacks.api import DqApiStack  # noqa: E402
from stacks.auth import DqAuthStack  # noqa: E402
from stacks.etl import DlEtlStack  # noqa: E402
from stacks.storage import DlStorageStack  # noqa: E402
from stacks.web import DqWebStack  # noqa: E402


def build_api_asset() -> Path:
    """One zip for the auth and dq_api Lambdas: authlib + both handlers."""
    out = Path(__file__).resolve().parent / "build" / "api"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    shutil.copytree(ROOT / "auth" / "authlib", out / "authlib", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "auth" / "handler.py", out / "auth_handler.py")
    shutil.copy(ROOT / "dq_api" / "handler.py", out / "dq_handler.py")
    return out


def build_api_dq_asset() -> Path:
    """The dq_api Lambda's own zip: authlib + the DQ routes (handler.py, unchanged)
    + the acquisition routes (acq.py) + the MRR routes (mrr.py) + the entry point api_handler.py."""
    out = Path(__file__).resolve().parent / "build" / "api_dq"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    shutil.copytree(ROOT / "auth" / "authlib", out / "authlib", ignore=shutil.ignore_patterns("__pycache__"))
    for f in ("handler.py", "acq.py", "mrr.py", "api_handler.py"):
        shutil.copy(ROOT / "dq_api" / f, out / f)
    return out


def build_glue_gold_lib() -> Path:
    """The gold job's --extra-py-files zip: common + gold_build, with the gold config
    as gold_build/gold_acquisition.json (read with pkgutil)."""
    out = Path(__file__).resolve().parent / "build" / "glue_lib_gold"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for pkg in ("common", "gold_build"):
        shutil.copytree(ROOT / "etl" / pkg, out / pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy(ROOT / "etl" / "config" / "gold_acquisition.json", out / "gold_build" / "gold_acquisition.json")
    return out


def build_glue_gold_mrr_lib() -> Path:
    """The gold MRR job's --extra-py-files zip: common + gold_mrr, with the MRR config
    as gold_mrr/gold_mrr.json (read with pkgutil)."""
    out = Path(__file__).resolve().parent / "build" / "glue_lib_gold_mrr"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for pkg in ("common", "gold_mrr"):
        shutil.copytree(ROOT / "etl" / pkg, out / pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy(ROOT / "etl" / "config" / "gold_mrr.json", out / "gold_mrr" / "gold_mrr.json")
    return out


def build_glue_lib() -> Path:
    """The Glue jobs' --extra-py-files zip (CDK zips this directory): the shared
    packages plus the rules config as common/dl_rules.json (read with pkgutil)."""
    out = Path(__file__).resolve().parent / "build" / "glue_lib"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for pkg in ("common", "bronze_ingest", "silver_build", "dq_publish"):
        shutil.copytree(ROOT / "etl" / pkg, out / pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy(ROOT / "etl" / "config" / "dl_rules.json", out / "common" / "dl_rules.json")
    return out


def _vendor_sqlglot(out: Path) -> None:
    """sqlglot (pure Python, pinned in requirements.txt) copied from this venv: no network at synth."""
    import sqlglot
    src = Path(sqlglot.__file__).resolve().parent
    shutil.copytree(src, out / "sqlglot", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def build_api_agent_asset() -> Path:
    """The finora-dq-agent Lambda's zip: authlib + agentlib + sqlglot + agent_api.py."""
    out = Path(__file__).resolve().parent / "build" / "api_agent"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    shutil.copytree(ROOT / "auth" / "authlib", out / "authlib", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "voice" / "agentlib", out / "agentlib", ignore=shutil.ignore_patterns("__pycache__"))
    _vendor_sqlglot(out)
    shutil.copy(ROOT / "dq_api" / "agent_api.py", out / "agent_api.py")
    return out


def build_glue_briefing_lib() -> Path:
    """The briefing job's --extra-py-files zip: agentlib + sqlglot."""
    out = Path(__file__).resolve().parent / "build" / "glue_lib_briefing"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    shutil.copytree(ROOT / "voice" / "agentlib", out / "agentlib", ignore=shutil.ignore_patterns("__pycache__"))
    _vendor_sqlglot(out)
    return out


def voice_config() -> dict:
    """infra/voice_agent.json: the ElevenLabs agent_id and the voice budget (config, not secrets;
    written by scripts/push_voice_agent.py)."""
    import json
    f = Path(__file__).resolve().parent / "voice_agent.json"
    return json.loads(f.read_text()) if f.exists() else {}


app = cdk.App()
env = cdk.Environment(account="962482423379", region="us-west-2")
import_mode = app.node.try_get_context("import_mode") == "true"
if not import_mode:
    cdk.Tags.of(app).add("project", "finora-dq")

DlStorageStack(app, "FinoraDlStorage", env=env, import_mode=import_mode)
if not import_mode:
    DlEtlStack(app, "FinoraDlEtl", env=env, etl_dir=ROOT / "etl", glue_lib_dir=build_glue_lib(),
               gold_lib_dir=build_glue_gold_lib(), mrr_lib_dir=build_glue_gold_mrr_lib(),
               briefing_lib_dir=build_glue_briefing_lib())
    api_asset = build_api_asset()
    auth = DqAuthStack(app, "FinoraDqAuth", env=env, asset_dir=api_asset)
    api = DqApiStack(app, "FinoraDqApi", env=env, asset_dir=api_asset, dq_asset_dir=build_api_dq_asset(), auth=auth,
                     agent_asset_dir=build_api_agent_asset(), voice=voice_config())
    # -c web_src=<dir> pins the site content (used to diff FinoraDqWeb against what is deployed).
    web_src = Path(app.node.try_get_context("web_src") or ROOT / "dashboard" / "out")
    if not (web_src / "index.html").exists():
        web_src = Path(__file__).resolve().parent / "placeholder"
    DqWebStack(app, "FinoraDqWeb", env=env, api=api, web_src=web_src)

app.synth()
