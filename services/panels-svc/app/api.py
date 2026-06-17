from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from svc_base.audit import record_audit
from svc_base.auth import Principal, assert_tenant_access, require_auth, require_roles
from svc_base.tenancy import scope_query
from svc_base.versioning import assert_mutable, bump_semver, content_hash

from .db import get_db
from .domain import VALID_TYPES, panel_snapshot, transition
from .models import Panel, PanelGene, PanelVersion
from .schemas import (
    AddGenesIn, GeneOut, LockIn, PanelIn, PanelOut, PanelPatch, VersionOut,
)

router = APIRouter()


def _scope(actor: Principal):
    return actor.scope or ([actor.tenant_id] if actor.tenant_id else [])


def _get(db: Session, pid: int, actor: Principal) -> Panel:
    p = db.get(Panel, pid)
    if not p:
        raise HTTPException(status_code=404, detail="panel not found")
    assert_tenant_access(actor, p.tenant_id)
    return p


def _audit(db, action, actor, panel, **detail):
    record_audit(db, action=action, actor=actor.subject, tenant_id=panel.tenant_id,
                 entity_type="panel", entity_id=panel.id, detail=detail or {})


# ── collection / literal routes (BEFORE /panels/{pid}) ──────────────────────

@router.get("/panels", response_model=list[PanelOut], tags=["panels"])
def list_panels(include_archived: bool = False, db: Session = Depends(get_db),
                actor: Principal = Depends(require_auth)):
    q = scope_query(db.query(Panel), Panel, _scope(actor))
    if not include_archived:
        q = q.filter(Panel.status != "archived")
    return q.order_by(Panel.id).all()


@router.post("/panels", response_model=PanelOut, status_code=201, tags=["panels"])
def create_panel(body: PanelIn, db: Session = Depends(get_db),
                 actor: Principal = Depends(require_auth)):
    if body.type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail="bad type")
    if not actor.tenant_id:
        raise HTTPException(status_code=403, detail="caller has no tenant")
    p = Panel(label=body.label, type=body.type, details=body.details,
              owner=actor.subject, tenant_id=actor.tenant_id, status="draft")
    db.add(p)
    db.commit()
    db.refresh(p)
    _audit(db, "panel.create", actor, p)
    db.commit()
    return p


@router.get("/panels/pending", response_model=list[PanelOut], tags=["panels"])
def pending(db: Session = Depends(get_db), actor: Principal = Depends(require_auth)):
    return (scope_query(db.query(Panel), Panel, _scope(actor))
            .filter(Panel.status == "validated").order_by(Panel.id).all())


@router.get("/versions", response_model=list[VersionOut], tags=["versions"])
def versions(db: Session = Depends(get_db), actor: Principal = Depends(require_auth)):
    return (scope_query(db.query(PanelVersion), PanelVersion, _scope(actor))
            .order_by(PanelVersion.id.desc()).all())


@router.delete("/panel-genes/{gid}", status_code=204, tags=["genes"])
def delete_gene(gid: int, db: Session = Depends(get_db),
                actor: Principal = Depends(require_auth)):
    g = db.get(PanelGene, gid)
    if not g:
        return
    p = _get(db, g.panel_id, actor)
    assert_mutable(p.status)
    db.delete(g)
    db.commit()


# ── single-panel routes ─────────────────────────────────────────────────────

@router.get("/panels/{pid}", response_model=PanelOut, tags=["panels"])
def get_panel(pid: int, db: Session = Depends(get_db),
              actor: Principal = Depends(require_auth)):
    return _get(db, pid, actor)


@router.patch("/panels/{pid}", response_model=PanelOut, tags=["panels"])
def patch_panel(pid: int, body: PanelPatch, db: Session = Depends(get_db),
                actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    assert_mutable(p.status)                      # locked → 409 (immutability)
    if body.label is not None:
        p.label = body.label
    if body.type is not None:
        if body.type not in VALID_TYPES:
            raise HTTPException(status_code=400, detail="bad type")
        p.type = body.type
    if body.details is not None:
        p.details = body.details
    db.commit()
    db.refresh(p)
    return p


@router.post("/panels/{pid}/add-genes", response_model=list[GeneOut], tags=["genes"])
def add_genes(pid: int, body: AddGenesIn, db: Session = Depends(get_db),
              actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    assert_mutable(p.status)
    added = []
    for sym in body.symbols:
        g = PanelGene(panel_id=p.id, symbol=sym.upper(), target=body.target or p.type)
        db.add(g)
        added.append(g)
    db.commit()
    for g in added:
        db.refresh(g)
    return added


@router.get("/panels/{pid}/genes", response_model=list[GeneOut], tags=["genes"])
def list_genes(pid: int, db: Session = Depends(get_db),
               actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    return (db.query(PanelGene).filter_by(panel_id=p.id)
            .order_by(PanelGene.symbol).all())


@router.get("/panels/{pid}/history", response_model=list[VersionOut], tags=["versions"])
def history(pid: int, db: Session = Depends(get_db),
            actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    return (db.query(PanelVersion).filter_by(panel_id=p.id)
            .order_by(PanelVersion.id).all())


# ── state machine ───────────────────────────────────────────────────────────

def _transition_route(pid, action, db, actor):
    p = _get(db, pid, actor)
    transition(p, action)
    db.commit()
    db.refresh(p)
    _audit(db, f"panel.{action}", actor, p)
    db.commit()
    return p


@router.post("/panels/{pid}/validate", response_model=PanelOut, tags=["state"])
def validate(pid: int, db: Session = Depends(get_db),
             actor: Principal = Depends(require_auth)):
    return _transition_route(pid, "validate", db, actor)


@router.post("/panels/{pid}/reject", response_model=PanelOut, tags=["state"])
def reject(pid: int, db: Session = Depends(get_db),
           actor: Principal = Depends(require_auth)):
    return _transition_route(pid, "reject", db, actor)


@router.post("/panels/{pid}/lock", response_model=PanelOut, tags=["state"])
def lock(pid: int, body: LockIn, db: Session = Depends(get_db),
         actor: Principal = Depends(require_roles("admin", "reviewer"))):
    p = _get(db, pid, actor)
    transition(p, "lock")                         # must be 'validated'
    genes = db.query(PanelGene).filter_by(panel_id=p.id).all()
    snap = panel_snapshot(p, genes)
    chash = content_hash(snap)
    new_version = bump_semver(p.current_version or "0.0.0", body.bump)
    db.add(PanelVersion(
        panel_id=p.id, version=new_version, content_hash=chash, snapshot=snap,
        note=body.note, locked_by=body.signed_off_by or actor.subject,
        tenant_id=p.tenant_id,
    ))
    p.current_version = new_version
    db.commit()
    db.refresh(p)
    _audit(db, "panel.lock", actor, p, version=new_version, content_hash=chash)
    db.commit()
    return p


@router.post("/panels/{pid}/deprecate", response_model=PanelOut, tags=["state"])
def deprecate(pid: int, db: Session = Depends(get_db),
              actor: Principal = Depends(require_roles("admin", "reviewer"))):
    return _transition_route(pid, "deprecate", db, actor)


@router.post("/panels/{pid}/unlock", response_model=PanelOut, tags=["state"])
def unlock(pid: int, db: Session = Depends(get_db),
           actor: Principal = Depends(require_roles("admin"))):
    # governance-gated: locked → draft (the prior immutable version is retained)
    return _transition_route(pid, "unlock", db, actor)


@router.post("/panels/{pid}/archive", response_model=PanelOut, tags=["state"])
def archive(pid: int, db: Session = Depends(get_db),
            actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    if p.status not in ("draft", "validated"):
        raise HTTPException(
            status_code=409,
            detail=f"cannot archive from '{p.status}' (use deprecate for locked)",
        )
    p.status = "archived"
    db.commit()
    db.refresh(p)
    _audit(db, "panel.archive", actor, p)
    db.commit()
    return p
