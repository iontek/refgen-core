"""Run-execution engine (Phase 2a): a single-gene run drives the full
create-target-bed chain with mocked MCP responses, then builds the provenance
manifest. Proves status transitions, step recording, BED construction, artifacts
(sha256), and the integrity manifest — without needing the live MCP fleet."""

import json
import os

import app.pipeline as pipeline_mod
import app.steps as steps_mod
from svc_base import mcp_client

from app.models import ProbeArtifact, ProbeRun, ProbeRunStep


def _canned_call_tool(base, tool, args, **kw):
    if tool == "gene_catalog_bulk_validate":
        return {"result": {"text": json.dumps({"results": [
            {"submitted": "BRCA1", "status": "approved",
             "hgnc_id": "HGNC:1100", "current_symbol": "BRCA1"}]})}}
    if tool == "mane_exons":
        return {"result": {"text": json.dumps({"results": [{
            "symbol": "BRCA1", "hgnc_id": "HGNC:1100", "transcript_id": "NM_007294.4",
            "chr": "chr17", "strand": "-", "exons": [
                {"exon_rank": 2, "exon_start": 43124017, "exon_end": 43124115,
                 "cds_start": 43124017, "cds_end": 43124096, "is_cds": 1},
                {"exon_rank": 3, "exon_start": 43115726, "exon_end": 43115779,
                 "cds_start": 43115726, "cds_end": 43115779, "is_cds": 1}]}]})}}
    if tool == "bed_merge":
        return {"result": {"text": "merged ok"}}
    return {"result": {"text": "{}"}}


class _Resp:
    def json(self):
        return {"version": "1.0.0", "tools": []}


def test_gene_run_full_chain_and_provenance(ctx, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_mod, "WORKSPACE", str(tmp_path))
    monkeypatch.setattr(steps_mod, "WORKSPACE", str(tmp_path))
    monkeypatch.setattr(mcp_client, "call_tool", _canned_call_tool)
    monkeypatch.setattr(steps_mod.httpx, "get", lambda *a, **k: _Resp())

    db = ctx.Session()
    run = ProbeRun(id="testrun01", pipeline_slug="create-target-bed",
                   gene_symbol="BRCA1", status="queued",
                   params={"cds_only": True, "padding_bp": 20}, tenant_id="refgen",
                   triggered_by="admin")
    run.params_hash = pipeline_mod.params_hash(run.params)
    db.add(run)
    db.commit()
    db.close()

    pipeline_mod.execute_run("testrun01", ctx.Session)        # synchronous (no thread)

    db = ctx.Session()
    run = db.get(ProbeRun, "testrun01")
    assert run.status == "success", run.error
    names = [s.step_name for s in db.query(ProbeRunStep)
             .filter_by(run_id="testrun01").order_by(ProbeRunStep.step_order)]
    assert names == ["hgnc_validate", "cds_extract", "padding", "merge", "summary"]

    arts = {a.kind: a for a in db.query(ProbeArtifact).filter_by(run_id="testrun01")}
    assert "target_bed" in arts and "manifest" in arts
    assert arts["target_bed"].sha256.startswith("sha256:")
    assert run.summary.get("manifest_sha256", "").startswith("sha256:")

    # BED is 0-based half-open: cds_start 43124017 → 43124016
    bed = open(os.path.join(run.workspace_dir, "target.bed")).read()
    assert "chr17\t43124016\t43124096\tBRCA1_ex2" in bed

    # provenance manifest captures the integrity fields
    man = json.load(open(os.path.join(run.workspace_dir, "manifest.json")))
    assert man["schema"] == "refgen.provenance/1"
    assert man["params_hash"] == run.params_hash
    assert man["software"]["design-svc"] == "0.1.0"
    assert "reference_versions" in man
    assert any(c["step"] == "cds_extract" for c in man["chain"])
    db.close()
