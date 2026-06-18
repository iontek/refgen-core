"""Run-execution engine — ported from the platform's probe_design/pipeline.py.

design-svc is the thin orchestrator: it owns run state (ORM) and runs the steps,
delegating the heavy work to MCPs (db-mcp gene/exon reads, nf-mcp bedtools). Each
run executes in a daemon thread with its OWN DB session (the request returns the
queued run immediately; `dx run watch` polls). Celery later.
"""

from __future__ import annotations

import hashlib
import threading
import traceback
from datetime import datetime, timezone

from svc_base.auth import issue_token

from . import steps as S
from .config import settings
from .models import ProbeArtifact, ProbeRun, ProbeRunStep

WORKSPACE = "/workspace"               # shared mcp-workspace volume (with nf-mcp)


def _now():
    return datetime.now(timezone.utc)


def _ms(dt):
    return int(dt.timestamp() * 1000) if dt else None


def params_hash(params: dict) -> str:
    import json
    canon = json.dumps(params or {}, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canon.encode()).hexdigest()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def ensure_workspace(run: ProbeRun) -> str:
    # Use a dxm-owned subtree under the shared mount; /workspace/users|projects
    # pre-exist with restrictive platform ownership. dirs are made 0777 so nf-mcp
    # (a different uid on the shared workspace) can write merged outputs back in.
    import os
    root = os.path.join(WORKSPACE, "dxm")
    sub = (("projects", run.panel_id) if run.panel_id
           else ("users", run.triggered_by or "anon"))
    d = os.path.join(root, sub[0], sub[1], "runs", run.id)
    os.makedirs(d, exist_ok=True)
    try:
        p = root
        os.chmod(p, 0o777)
        for part in os.path.relpath(d, root).split(os.sep):
            p = os.path.join(p, part)
            os.chmod(p, 0o777)
    except OSError:
        pass
    return d


def save_artifact(db, run: ProbeRun, step, kind: str, path: str,
                  mime: str = "text/plain") -> ProbeArtifact:
    import os
    a = ProbeArtifact(run_id=run.id, step_id=(step.id if step else None), kind=kind,
                      path=path, size_bytes=os.path.getsize(path),
                      sha256=_sha256_file(path), mime_type=mime)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def build_pipeline(run: ProbeRun):
    plan = [
        ("hgnc_validate", "db-mcp.gene_catalog_bulk_validate", S.step_hgnc_validate),
        ("cds_extract",   "db-mcp.mane_exons",                 S.step_cds_extract),
    ]
    if run.panel_id:
        plan.append(("custom_regions", "panels-svc.regions", S.step_custom_regions))
    plan += [
        ("padding", "local.slop",      S.step_padding),
        ("merge",   "nf-mcp.bed_merge", S.step_merge),
        ("summary", "local.manifest",  S.step_summary),
    ]
    return [(i + 1, name, tool, h) for i, (name, tool, h) in enumerate(plan)]


def _run_step(db, run, ctx, order, name, tool, handler):
    step = ProbeRunStep(run_id=run.id, step_order=order, step_name=name,
                        tool_id=tool, status="running", started_at=_now())
    db.add(step)
    db.commit()
    db.refresh(step)
    t0 = _now()
    try:
        result = handler(db, run, step, ctx) or {}
        step.status, step.result = "success", result
    except Exception as exc:  # noqa: BLE001
        step.status = "failed"
        step.log_excerpt = (str(exc) + "\n" + traceback.format_exc())[-2000:]
        step.ended_at = _now()
        step.duration_ms = int((step.ended_at - t0).total_seconds() * 1000)
        db.commit()
        raise
    step.ended_at = _now()
    step.duration_ms = int((step.ended_at - t0).total_seconds() * 1000)
    db.commit()
    return result


def execute_run(run_id: str, session_factory):
    """Top-level orchestrator (runs in a daemon thread, own DB session)."""
    db = session_factory()
    try:
        run = db.get(ProbeRun, run_id)
        if not run:
            return
        run.status, run.started_at = "running", _now()
        run.workspace_dir = ensure_workspace(run)
        db.commit()
        # service token so steps can call panels-svc (genes/regions) as the run's tenant
        ctx = {"ws": run.workspace_dir,
               "token": issue_token(settings, "design-svc", roles=["admin"],
                                    tenant_id=run.tenant_id)}
        try:
            for order, name, tool, handler in build_pipeline(run):
                _run_step(db, run, ctx, order, name, tool, handler)
            run.status, run.ended_at = "success", _now()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = (str(exc) + "\n" + traceback.format_exc())[-3000:]
            run.ended_at = _now()
            db.commit()
    finally:
        db.close()


def launch_run(run_id: str, session_factory):
    threading.Thread(target=execute_run, args=(run_id, session_factory),
                     daemon=True).start()
