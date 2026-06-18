from __future__ import annotations

import json
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from svc_base import mcp_client
from svc_base.auth import Principal, assert_tenant_access, require_auth
from svc_base.tenancy import scope_query

from . import pipeline
from .config import settings
from .db import SessionLocal, get_db
from .models import AdapterSet, ProbeArtifact, ProbeRun, ProbeRunStep, Recipe
from .schemas import (
    AdapterIn, AdapterOut, AgentRunIn, AnalystIn, LitIn, RecipeIn, RecipeOut,
    RunDetailOut, RunIn, RunOut,
)
from .seed_recipes import recipe_hash

router = APIRouter()

# Engine MCP endpoints (service-name:port on refgen-net; env-overridable).
CLINVAR = lambda: mcp_client.mcp_url("clinvar-mcp", 3008)   # noqa: E731
PUBMED = lambda: mcp_client.mcp_url("pubmed-mcp", 3021)     # noqa: E731
AGENT = lambda: mcp_client.mcp_url("agent-mcp", 3020)       # noqa: E731

_LIT_ALLOWED = {
    "pubmed_search", "pubmed_fetch", "pubmed_gene", "pubmed_similar",
    "lit_save", "lit_search", "lit_list", "lit_index", "lit_ask",
    "zotero_index", "zotero_sync", "rag_list", "rag_erase", "lit_url",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _scope(actor: Principal):
    return actor.scope or ([actor.tenant_id] if actor.tenant_id else [])


def _ms(dt):
    return int(dt.timestamp() * 1000) if dt else None


def _mcp_call(base_url: str, tool: str, args: dict, timeout: float = 60.0):
    """Thin passthrough to an MCP. Clean 502 on unreachable / RPC error."""
    try:
        resp = mcp_client.call_tool(base_url, tool, args, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — any transport/HTTP failure
        raise HTTPException(status_code=502, detail=f"MCP unreachable: {type(exc).__name__}")
    if isinstance(resp, dict) and resp.get("error"):
        err = resp["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise HTTPException(status_code=502, detail=msg)
    return resp.get("result", {}) if isinstance(resp, dict) else {}


def _result_text(result) -> str:
    if isinstance(result, dict):
        if "text" in result:
            return result["text"]
        content = result.get("content")
        if content and isinstance(content, list):
            return content[0].get("text", "")
    return ""


def _run_out(r: ProbeRun) -> dict:
    return {
        "id": r.id, "pipeline_slug": r.pipeline_slug, "panel_id": r.panel_id,
        "panel_version": r.panel_version, "gene_symbol": r.gene_symbol,
        "status": r.status, "params": r.params or {}, "params_hash": r.params_hash,
        "summary": r.summary or {}, "error": r.error, "triggered_by": r.triggered_by,
        "created_at": _ms(r.created_at), "started_at": _ms(r.started_at),
        "ended_at": _ms(r.ended_at),
    }


# ── recipes (catalog) ─────────────────────────────────────────────────────────

@router.get("/probe-design/runs/recipes", tags=["recipes"])
def list_recipes(db: Session = Depends(get_db),
                 actor: Principal = Depends(require_auth)):
    rows = (db.query(Recipe).filter_by(status="published")
            .order_by(Recipe.name, Recipe.version).all())
    return {"recipes": [RecipeOut.model_validate(r).model_dump() for r in rows]}


@router.post("/probe-design/runs/recipes", response_model=RecipeOut, status_code=201,
             tags=["recipes"])
def create_recipe(body: RecipeIn, db: Session = Depends(get_db),
                  actor: Principal = Depends(require_auth)):
    if db.query(Recipe).filter_by(name=body.name, version=body.version).first():
        raise HTTPException(status_code=409, detail="recipe name+version already exists")
    chash = recipe_hash(body.name, body.version, body.spec)
    if db.query(Recipe).filter_by(content_hash=chash).first():
        raise HTTPException(status_code=409, detail="identical recipe content already exists")
    r = Recipe(name=body.name, version=body.version, description=body.description,
               spec=body.spec, content_hash=chash, status="published",
               created_by=actor.subject)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ── adapter sets (catalog) ────────────────────────────────────────────────────

@router.get("/probe-design/adapter-sets", response_model=list[AdapterOut], tags=["adapters"])
def list_adapters(db: Session = Depends(get_db),
                  actor: Principal = Depends(require_auth)):
    return db.query(AdapterSet).order_by(AdapterSet.name).all()


@router.post("/probe-design/adapter-sets", response_model=AdapterOut, status_code=201,
             tags=["adapters"])
def create_adapter(body: AdapterIn, db: Session = Depends(get_db),
                   actor: Principal = Depends(require_auth)):
    if db.query(AdapterSet).filter_by(name=body.name).first():
        raise HTTPException(status_code=409, detail="adapter set name already exists")
    a = AdapterSet(name=body.name, platform=body.platform, adapter_5p=body.adapter_5p,
                   adapter_3p=body.adapter_3p, has_t7=body.has_t7, purpose=body.purpose,
                   note=body.note, created_by=actor.subject)
    a.content_hash = a.compute_hash()
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ── MCP passthrough (thin — design-svc is the engine-facing layer) ────────────

@router.get("/probe-design/clinvar/{gene}", tags=["evidence"])
def clinvar(gene: str, actor: Principal = Depends(require_auth)):
    result = _mcp_call(CLINVAR(), "clinvar_summary", {"gene": gene}, timeout=45)
    return {"gene": gene, "summary": _result_text(result)}


@router.post("/probe-design/lit", tags=["lit"])
def lit(body: LitIn, actor: Principal = Depends(require_auth)):
    if body.tool not in _LIT_ALLOWED:
        raise HTTPException(status_code=400,
                            detail=f"tool '{body.tool}' not allowed")
    return _mcp_call(PUBMED(), body.tool, body.args, timeout=1800)


@router.get("/probe-design/agents", tags=["agents"])
def agents(actor: Principal = Depends(require_auth)):
    return _mcp_call(AGENT(), "list_agents", {}, timeout=30)


@router.get("/probe-design/agents/graph", tags=["agents"])
def agent_graph(name: str = "analyst", fmt: str = "ascii",
                actor: Principal = Depends(require_auth)):
    return _mcp_call(AGENT(), "agent_graph", {"name": name, "fmt": fmt}, timeout=30)


@router.post("/probe-design/agents/run", tags=["agents"])
def agent_run(body: AgentRunIn, request: Request,
              actor: Principal = Depends(require_auth)):
    # thread the caller's JWT so the agent acts AS the user (panel operations)
    token = request.headers.get("authorization", "").replace("Bearer ", "")
    args = {"task": body.task, "agent": body.agent, "token": token,
            "history": body.history}
    if body.model:
        args["model"] = body.model
    return _mcp_call(AGENT(), "run_agent", args, timeout=180)


@router.post("/probe-design/analyst", tags=["agents"])
def analyst(body: AnalystIn, actor: Principal = Depends(require_auth)):
    return _mcp_call(AGENT(), "run_analyst", {"variant": body.variant}, timeout=180)


# ── runs ──────────────────────────────────────────────────────────────────────

@router.post("/probe-design/runs", response_model=RunDetailOut, status_code=201,
             tags=["runs"])
def create_run(body: RunIn, request: Request, db: Session = Depends(get_db),
               actor: Principal = Depends(require_auth)):
    """Create a run and launch it in the background. A panel run is gated on the
    panel being locked and pins its current version (reproducibility anchor)."""
    if not body.panel_id and not body.gene_symbol:
        raise HTTPException(status_code=400, detail="panel_id or gene_symbol required")
    if not actor.tenant_id:
        raise HTTPException(status_code=403, detail="caller has no tenant")
    panel_version = None
    if body.panel_id:
        tok = request.headers.get("authorization", "")     # forward caller's JWT
        try:
            r = httpx.get(f"{settings.panels_url}/panels/{body.panel_id}",
                          headers={"Authorization": tok}, timeout=20)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502,
                                detail=f"panels-svc unreachable: {type(exc).__name__}")
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="panel not found")
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="panel lookup failed")
        panel = r.json()
        if panel.get("status") != "locked":
            raise HTTPException(
                status_code=409,
                detail=f"panel is '{panel.get('status')}'; lock it before designing")
        panel_version = panel.get("current_version")
    params = dict(body.params or {})
    run = ProbeRun(pipeline_slug=body.pipeline_slug, panel_id=body.panel_id,
                   gene_symbol=body.gene_symbol, panel_version=panel_version,
                   status="queued", params=params,
                   params_hash=pipeline.params_hash(params),
                   triggered_by=actor.subject, tenant_id=actor.tenant_id)
    db.add(run)
    db.commit()
    db.refresh(run)
    pipeline.launch_run(run.id, SessionLocal)          # background daemon thread
    out = _run_out(run)
    out["steps"], out["artifacts"] = [], []
    return out


@router.get("/probe-design/runs", response_model=list[RunOut], tags=["runs"])
def list_runs(pipeline_slug: str | None = None, db: Session = Depends(get_db),
              actor: Principal = Depends(require_auth)):
    q = scope_query(db.query(ProbeRun), ProbeRun, _scope(actor))
    if pipeline_slug:
        q = q.filter(ProbeRun.pipeline_slug == pipeline_slug)
    return [_run_out(r) for r in q.order_by(ProbeRun.created_at.desc()).all()]


@router.get("/probe-design/runs/{rid}", response_model=RunDetailOut, tags=["runs"])
def get_run(rid: str, db: Session = Depends(get_db),
            actor: Principal = Depends(require_auth)):
    r = db.get(ProbeRun, rid)
    if not r:
        raise HTTPException(status_code=404, detail="run not found")
    assert_tenant_access(actor, r.tenant_id)
    out = _run_out(r)
    out["steps"] = (db.query(ProbeRunStep).filter_by(run_id=r.id)
                    .order_by(ProbeRunStep.step_order).all())
    out["artifacts"] = db.query(ProbeArtifact).filter_by(run_id=r.id).all()
    return out


def _get_run(db: Session, rid: str, actor: Principal) -> ProbeRun:
    r = db.get(ProbeRun, rid)
    if not r:
        raise HTTPException(status_code=404, detail="run not found")
    assert_tenant_access(actor, r.tenant_id)
    return r


@router.get("/probe-design/runs/{rid}/provenance", tags=["runs"])
def provenance(rid: str, db: Session = Depends(get_db),
               actor: Principal = Depends(require_auth)):
    """The run-integrity record (manifest.json, schema refgen.provenance/1)."""
    r = _get_run(db, rid, actor)
    path = os.path.join(r.workspace_dir or "", "manifest.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="no manifest (run not completed?)")
    with open(path) as fh:
        return json.load(fh)


@router.get("/probe-design/runs/{rid}/graph", tags=["runs"])
def graph(rid: str, db: Session = Depends(get_db),
          actor: Principal = Depends(require_auth)):
    r = _get_run(db, rid, actor)
    steps = (db.query(ProbeRunStep).filter_by(run_id=r.id)
             .order_by(ProbeRunStep.step_order).all())
    lines = ["flowchart TD", f'  IN["{r.panel_id or r.gene_symbol or r.id}"]']
    prev = "IN"
    for s in steps:
        nid = f"S{s.step_order}"
        lines.append(f'  {nid}["{s.step_order} · {s.step_name}<br/>'
                     f'{s.tool_id} · {s.duration_ms or 0}ms · {s.status}"]')
        lines.append(f"  {prev} --> {nid}")
        prev = nid
    return {"run": r.id, "status": r.status, "mermaid": "\n".join(lines)}


@router.get("/probe-design/runs/{rid}/artifact", tags=["runs"])
def artifact(rid: str, name: str, db: Session = Depends(get_db),
             actor: Principal = Depends(require_auth)):
    r = _get_run(db, rid, actor)
    ws = os.path.normpath(r.workspace_dir or "")
    target = os.path.normpath(os.path.join(ws, name))
    if not (ws and (target == ws or target.startswith(ws + os.sep))):
        raise HTTPException(status_code=400, detail="bad artifact path")
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(target, filename=os.path.basename(target))
