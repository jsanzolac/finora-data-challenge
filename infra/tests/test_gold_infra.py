"""Synthesized FinoraDlEtl / FinoraDqApi / FinoraDlStorage: the gold step runs only
after the DQ publish and its failure never reaches RecordFailedRun (dq/*); the gold
role's explicit denies on the rates table; the API role's S3 scope (no HR data,
writes only to the rates table and the Athena results prefix); the gold bucket."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[1]
ROOT = INFRA.parent
sys.path.insert(0, str(INFRA))
sys.path.insert(0, str(ROOT / "etl"))

cdk = pytest.importorskip("aws_cdk")


@pytest.fixture(scope="module")
def templates():
    import importlib.util

    spec = importlib.util.spec_from_file_location("finora_app_build", INFRA / "app.py")
    src = (INFRA / "app.py").read_text().replace("app = cdk.App()", "app = cdk.App(outdir=OUTDIR)") \
        .replace("app.synth()", "ASSEMBLY = app.synth()")
    out = tempfile.mkdtemp(prefix="finora-cdk-")
    ns = {"__file__": str(INFRA / "app.py"), "__name__": "finora_app_build", "OUTDIR": out}
    exec(compile(src, str(INFRA / "app.py"), "exec"), ns)
    asm = ns["ASSEMBLY"]
    return {s.stack_name: s.template for s in asm.stacks}


def resources(t, typ):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == typ}


def definition(t):
    sm = next(iter(resources(t, "AWS::StepFunctions::StateMachine").values()))
    body = sm["Properties"]["DefinitionString"]
    parts = body["Fn::Join"][1] if isinstance(body, dict) else [body]
    return json.loads("".join(p if isinstance(p, str) else "REF" for p in parts))


def test_gold_runs_after_publish_and_its_failure_never_touches_dq(templates):
    d = definition(templates["FinoraDlEtl"])
    st = d["States"]
    assert st["DqPublish"]["Next"] == "GoldBuild"
    assert st["GoldBuild"]["Next"] == "GoldRefreshed" and st["GoldRefreshed"]["Next"] == "GoldMrrBuild"
    # gold MRR (finora-dl-gold-mrr) runs after the acquisition publish and its event, with its own Fail state
    assert st["GoldMrrBuild"]["Next"] == "AgentBriefing"
    # the voice briefing (finora-dl-agent-briefing) runs last, with its own Fail state
    assert st["AgentBriefing"]["Next"] == "Published"
    assert [c["Next"] for c in st["AgentBriefing"]["Catch"]] == ["BriefingFailed"] and st["BriefingFailed"]["Type"] == "Fail"
    assert st["AgentBriefing"]["Parameters"]["JobName"] == "finora-dl-agent-briefing"
    assert [c["Next"] for c in st["GoldMrrBuild"]["Catch"]] == ["GoldMrrFailed"] and st["GoldMrrFailed"]["Type"] == "Fail"
    assert st["GoldMrrBuild"]["Parameters"]["JobName"] == "finora-dl-gold-mrr"
    assert [c["Next"] for c in st["GoldBuild"]["Catch"]] == ["GoldFailed"] and st["GoldFailed"]["Type"] == "Fail"
    assert [c["Next"] for c in st["SilverBuild"]["Catch"]] == ["RecordFailedRun"]
    assert [c["Next"] for c in st["DqPublish"]["Catch"]] == ["RecordFailedRun"]
    # nothing reachable from GoldBuild runs the DQ publish job again
    seen, todo = set(), ["GoldBuild"]
    while todo:
        s = todo.pop()
        if s in seen:
            continue
        seen.add(s)
        x = st[s]
        todo += [x["Next"]] if "Next" in x else []
        todo += [c["Next"] for c in x.get("Catch", [])]
    assert seen == {"GoldBuild", "GoldRefreshed", "GoldMrrBuild", "GoldMrrFailed", "AgentBriefing", "BriefingFailed",
                    "Published", "GoldFailed"}
    assert all(st[s].get("Parameters", {}).get("JobName") != "finora-dl-dq-publish" for s in seen)
    assert st["GoldBuild"]["Parameters"]["JobName"] == "finora-dl-gold-build"
    assert any("Glue.ConcurrentRunsExceededException" in r["ErrorEquals"] for r in st["GoldBuild"]["Retry"])
    entry = st["GoldRefreshed"]["Parameters"]["Entries"][0]
    assert entry["DetailType"] == "gold.refreshed" and entry["Source"] == "finora.dl"


def test_gold_job_settings(templates):
    t = templates["FinoraDlEtl"]
    job = next(v["Properties"] for v in resources(t, "AWS::Glue::Job").values()
               if v["Properties"]["Name"] == "finora-dl-gold-build")
    assert (job["GlueVersion"], job["WorkerType"], job["NumberOfWorkers"], job["MaxRetries"], job["Timeout"],
            job["ExecutionProperty"]["MaxConcurrentRuns"]) == ("5.0", "G.1X", 2, 0, 15, 1)
    args = job["DefaultArguments"]
    assert args["--datalake-formats"] == "iceberg" and args["--iceberg_warehouse"] == "s3://al-test-dl-gold/iceberg/"
    assert args["--job-bookmark-option"] == "job-bookmark-disable" and "--STAGING_BUCKET" not in args
    dbs = {v["Properties"]["DatabaseInput"]["Name"] for v in resources(t, "AWS::Glue::Database").values()}
    assert dbs == {"finora_silver", "finora_dq", "finora_gold"}


def _statements(t, role_name):
    role_id = next(k for k, v in resources(t, "AWS::IAM::Role").items() if v["Properties"].get("RoleName") == role_name)
    out = []
    for v in resources(t, "AWS::IAM::Policy").values():
        if {"Ref": role_id} in v["Properties"]["Roles"]:
            out += v["Properties"]["PolicyDocument"]["Statement"]
    return out


def _res(s):
    r = s["Resource"]
    return [json.dumps(x) for x in (r if isinstance(r, list) else [r])]


def _acts(s):
    a = s["Action"]
    return a if isinstance(a, list) else [a]


def test_gold_role_denies_the_rates_table_and_cannot_delete(templates):
    st = _statements(templates["FinoraDlEtl"], "finora-dl-glue-gold")
    deny = [s for s in st if s["Effect"] == "Deny"]
    assert {a for s in deny for a in _acts(s)} >= {"s3:PutObject", "s3:DeleteObject", "glue:UpdateTable",
                                                   "glue:DeleteTable", "glue:CreateTable"}
    assert any("funnel_conversion_rate/*" in r for s in deny for r in _res(s))
    assert any("table/finora_gold/funnel_conversion_rate" in r for s in deny for r in _res(s))
    allow = [s for s in st if s["Effect"] == "Allow"]
    assert not any(a in ("s3:DeleteObject", "s3:*") for s in allow for a in _acts(s))
    serving = [r for s in allow if "s3:PutObject" in _acts(s) for r in _res(s) if "al-test-dl-serving" in r]
    assert serving and all("/acq/*" in r for r in serving)


def test_api_role_scope(templates):
    t = templates["FinoraDqApi"]
    fn = next(v["Properties"] for v in resources(t, "AWS::Lambda::Function").values()
              if v["Properties"].get("FunctionName") == "finora-dq-api")
    assert fn["Handler"] == "api_handler.handler" and fn["Timeout"] == 28
    role_id = fn["Role"]["Fn::GetAtt"][0]
    st = []
    for v in resources(t, "AWS::IAM::Policy").values():
        if {"Ref": role_id} in v["Properties"]["Roles"]:
            st += v["Properties"]["PolicyDocument"]["Statement"]
    text = json.dumps(st)
    assert "hr_sensitive" not in text and "fact_sm_spend" not in text and "al-test-dl-silver" not in text
    writes = [r for s in st for r in _res(s) if "s3:PutObject" in _acts(s)]
    assert writes and all(("funnel_conversion_rate/*" in r) or ("al-test-dl-athena-results/finora-dl/*" in r)
                          for r in writes)
    gold_reads = [r for s in st for r in _res(s) if "s3:GetObject" in _acts(s) and "al-test-dl-gold" in r]
    assert sorted(gold_reads) == sorted(['"arn:aws:s3:::al-test-dl-gold/iceberg/finora_gold/funnel_conversion_rate/*"',
                                         '"arn:aws:s3:::al-test-dl-gold/iceberg/finora_gold/dim_funnel_stage/*"'])
    glue_writes = [r for s in st for r in _res(s) if "glue:UpdateTable" in _acts(s)]
    assert glue_writes == ['"arn:aws:glue:us-west-2:962482423379:table/finora_gold/funnel_conversion_rate"']
    routes = {v["Properties"]["RouteKey"] for v in resources(t, "AWS::ApiGatewayV2::Route").values()}
    assert {"GET /api/acq/summary", "GET /api/acq/scenarios", "POST /api/acq/scenarios"} <= routes


def test_gold_bucket(templates):
    t = templates["FinoraDlStorage"]
    gold = next((k, v) for k, v in resources(t, "AWS::S3::Bucket").items()
                if v["Properties"]["BucketName"] == "al-test-dl-gold")
    p = gold[1]["Properties"]
    assert gold[1]["DeletionPolicy"] == "Retain" and p["VersioningConfiguration"]["Status"] == "Enabled"
    rule = p["LifecycleConfiguration"]["Rules"][0]
    assert rule["NoncurrentVersionExpiration"]["NoncurrentDays"] == 30
    pol = [v for v in resources(t, "AWS::S3::BucketPolicy").values() if v["Properties"]["Bucket"] == {"Ref": gold[0]}]
    assert pol and "aws:SecureTransport" in json.dumps(pol)


def test_gold_mrr_role_writes_only_its_own_outputs(templates):
    """finora-dl-glue-mrr: writes only the MRR tables, its run report and mrr/*; no delete,
    no acquisition table, no dq/* or acq/*; the MRR job has its own library zip."""
    t = templates["FinoraDlEtl"]
    pol = next(v for k, v in resources(t, "AWS::IAM::Policy").items() if k.startswith("MrrRole"))
    writes = set()
    for stmt in pol["Properties"]["PolicyDocument"]["Statement"]:
        acts = stmt["Action"] if isinstance(stmt["Action"], list) else [stmt["Action"]]
        res = stmt["Resource"] if isinstance(stmt["Resource"], list) else [stmt["Resource"]]
        assert not any("Delete" in a for a in acts) and stmt["Effect"] == "Allow"
        if any(a in ("s3:PutObject", "glue:CreateTable", "glue:UpdateTable") for a in acts):
            writes |= {r for r in res if isinstance(r, str)}
    from gold_mrr import schemas as mrr_schemas

    want = {f"arn:aws:s3:::al-test-dl-gold/iceberg/finora_gold/{x}/*" for x in mrr_schemas.TABLE_NAMES}
    want |= {f"arn:aws:glue:us-west-2:962482423379:table/finora_gold/{x}" for x in mrr_schemas.TABLE_NAMES}
    want |= {"arn:aws:s3:::al-test-dl-gold/_glue_tmp/mrr/*", "arn:aws:s3:::al-test-dl-gold/_runs/run_id=*/mrr_report.json",
             "arn:aws:s3:::al-test-dl-serving/mrr/*", "arn:aws:glue:us-west-2:962482423379:catalog",
             "arn:aws:glue:us-west-2:962482423379:database/finora_gold"}
    assert writes == want
    assert not any("/dq/" in w or "/acq/" in w or "funnel_conversion_rate" in w for w in writes)
    jobs = {v["Properties"]["Name"]: v["Properties"] for v in resources(t, "AWS::Glue::Job").values()}
    mrr, gold = jobs["finora-dl-gold-mrr"], jobs["finora-dl-gold-build"]
    assert mrr["DefaultArguments"]["--extra-py-files"] != gold["DefaultArguments"]["--extra-py-files"]
    assert mrr["ExecutionProperty"]["MaxConcurrentRuns"] == 1 and mrr["MaxRetries"] == 0 and mrr["Timeout"] == 15
