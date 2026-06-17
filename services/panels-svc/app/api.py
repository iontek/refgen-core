from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
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


# ── helpers ─────────────────────────────────────────────────────────────────

def _scope(actor: Principal):
    return actor.scope or ([actor.tenant_id] if actor.tenant_id else [])


def _ms(dt):
    return int(dt.timestamp() * 1000) if dt else None


def _panel_out(p: Panel, total: int = 0, dna: int = 0, rna: int = 0) -> dict:
    """Serialize to the dx contract: id = legacy code, gene counts, ms timestamps."""
    return {
        "id": p.code or f"panel-{p.id:04d}",
        "code": p.code,
        "label": p.label,
        "type": p.type,
        "status": p.status,
        "created_by": p.created_by,
        "tenant_id": p.tenant_id,
        "current_version": p.current_version,
        "parent_id": p.parent_id,
        "details": p.details,
        "gene_count": total,
        "dna_count": dna,
        "rna_count": rna,
        "updated_at": _ms(p.updated_at),
        "created_at": _ms(p.created_at),
    }


def _counts_for(db: Session, panel_id: int):
    rows = (db.query(PanelGene.target, func.count(PanelGene.id))
            .filter_by(panel_id=panel_id).group_by(PanelGene.target).all())
    by = {t: n for t, n in rows}
    return sum(by.values()), by.get("DNA", 0), by.get("RNA", 0)


def _counts_all(db: Session, panel_ids: list):
    out = {}
    if not panel_ids:
        return out
    rows = (db.query(PanelGene.panel_id, PanelGene.target, func.count(PanelGene.id))
            .filter(PanelGene.panel_id.in_(panel_ids))
            .group_by(PanelGene.panel_id, PanelGene.target).all())
    for pid, t, n in rows:
        d = out.setdefault(pid, {"total": 0, "DNA": 0, "RNA": 0})
        d["total"] += n
        if t in ("DNA", "RNA"):
            d[t] += n
    return out


def _resolve(db: Session, pid: str):
    """Look up a panel by legacy code ('panel-0015') or by integer id."""
    p = db.query(Panel).filter_by(code=pid).first()
    if p is None and str(pid).isdigit():
        p = db.get(Panel, int(pid))
    return p


def _get(db: Session, pid: str, actor: Principal) -> Panel:
    p = _resolve(db, pid)
    if not p:
        raise HTTPException(status_code=404, detail="panel not found")
    assert_tenant_access(actor, p.tenant_id)
    return p


def _next_code(db: Session) -> str:
    last = (db.query(Panel.code).filter(Panel.code.like("panel-%"))
            .order_by(Panel.code.desc()).first())
    n = 1
    if last and last[0]:
        try:
            n = int(last[0].split("-")[1]) + 1
        except (IndexError, ValueError):
            n = 1
    return f"panel-{n:04d}"


def _audit(db, action, actor, panel, **detail):
    record_audit(db, action=action, actor=actor.subject, tenant_id=panel.tenant_id,
                 entity_type="panel", entity_id=panel.id, detail=detail or {})


def _out(db, p):
    total, dna, rna = _counts_for(db, p.id)
    return _panel_out(p, total, dna, rna)


# ── collection / literal routes (BEFORE /panels/{pid}) ──────────────────────

@router.get("/panels", response_model=list[PanelOut], tags=["panels"])
def list_panels(include_archived: bool = False, db: Session = Depends(get_db),
                actor: Principal = Depends(require_auth)):
    q = scope_query(db.query(Panel), Panel, _scope(actor))
    if not include_archived:
        q = q.filter(Panel.status != "archived")
    panels = q.order_by(Panel.id).all()
    counts = _counts_all(db, [p.id for p in panels])
    out = []
    for p in panels:
        c = counts.get(p.id, {})
        out.append(_panel_out(p, c.get("total", 0), c.get("DNA", 0), c.get("RNA", 0)))
    return out


@router.post("/panels", response_model=PanelOut, status_code=201, tags=["panels"])
def create_panel(body: PanelIn, db: Session = Depends(get_db),
                 actor: Principal = Depends(require_auth)):
    if body.type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail="bad type")
    if not actor.tenant_id:
        raise HTTPException(status_code=403, detail="caller has no tenant")
    p = Panel(label=body.label, type=body.type, details=body.details,
              created_by=actor.subject, tenant_id=actor.tenant_id, status="draft")
    db.add(p)
    db.flush()
    p.code = _next_code(db)
    db.commit()
    db.refresh(p)
    _audit(db, "panel.create", actor, p)
    db.commit()
    return _out(db, p)


@router.get("/panels/pending", response_model=list[PanelOut], tags=["panels"])
def pending(db: Session = Depends(get_db), actor: Principal = Depends(require_auth)):
    panels = (scope_query(db.query(Panel), Panel, _scope(actor))
              .filter(Panel.status == "validated").order_by(Panel.id).all())
    counts = _counts_all(db, [p.id for p in panels])
    return [_panel_out(p, *(lambda c: (c.get("total", 0), c.get("DNA", 0), c.get("RNA", 0)))(counts.get(p.id, {})))
            for p in panels]


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
    p = _get(db, str(g.panel_id), actor)
    assert_mutable(p.status)
    db.delete(g)
    db.commit()


# ── single-panel routes (pid = legacy code or int) ──────────────────────────

@router.get("/panels/{pid}", response_model=PanelOut, tags=["panels"])
def get_panel(pid: str, db: Session = Depends(get_db),
              actor: Principal = Depends(require_auth)):
    return _out(db, _get(db, pid, actor))


@router.patch("/panels/{pid}", response_model=PanelOut, tags=["panels"])
def patch_panel(pid: str, body: PanelPatch, db: Session = Depends(get_db),
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
    return _out(db, p)


@router.post("/panels/{pid}/add-genes", response_model=list[GeneOut], tags=["genes"])
def add_genes(pid: str, body: AddGenesIn, db: Session = Depends(get_db),
              actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    assert_mutable(p.status)
    added = []
    for sym in body.symbols:
        g = PanelGene(panel_id=p.id, symbol=sym.upper(),
                      target=body.target or p.type, added_by=actor.subject)
        db.add(g)
        added.append(g)
    db.commit()
    for g in added:
        db.refresh(g)
    return added


@router.get("/panels/{pid}/genes", response_model=list[GeneOut], tags=["genes"])
def list_genes(pid: str, db: Session = Depends(get_db),
               actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    return (db.query(PanelGene).filter_by(panel_id=p.id)
            .order_by(PanelGene.symbol).all())


@router.get("/panels/{pid}/history", response_model=list[VersionOut], tags=["versions"])
def history(pid: str, db: Session = Depends(get_db),
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
    return _out(db, p)


@router.post("/panels/{pid}/validate", response_model=PanelOut, tags=["state"])
def validate(pid: str, db: Session = Depends(get_db),
             actor: Principal = Depends(require_auth)):
    return _transition_route(pid, "validate", db, actor)


@router.post("/panels/{pid}/reject", response_model=PanelOut, tags=["state"])
def reject(pid: str, db: Session = Depends(get_db),
           actor: Principal = Depends(require_auth)):
    return _transition_route(pid, "reject", db, actor)


@router.post("/panels/{pid}/lock", response_model=PanelOut, tags=["state"])
def lock(pid: str, body: LockIn, db: Session = Depends(get_db),
         actor: Principal = Depends(require_roles("admin", "reviewer"))):
    p = _get(db, pid, actor)
    transition(p, "lock")                         # must be 'validated'
    genes = db.query(PanelGene).filter_by(panel_id=p.id).all()
    snap = panel_snapshot(p, genes)
    chash = content_hash(snap)
    prev = (db.query(PanelVersion).filter_by(panel_id=p.id)
            .order_by(PanelVersion.id.desc()).first())
    new_version = bump_semver(p.current_version or "0.0.0", body.bump)
    db.add(PanelVersion(
        panel_id=p.id, version=new_version, content_hash=chash,
        parent_hash=prev.content_hash if prev else None,   # version lineage
        bump_kind=body.bump, status="locked", snapshot=snap, note=body.note,
        locked_by=actor.subject, signed_off_by=body.signed_off_by,
        locked_at=datetime.now(timezone.utc), tenant_id=p.tenant_id,
    ))
    p.current_version = new_version
    db.commit()
    db.refresh(p)
    _audit(db, "panel.lock", actor, p, version=new_version, content_hash=chash)
    db.commit()
    return _out(db, p)


@router.post("/panels/{pid}/deprecate", response_model=PanelOut, tags=["state"])
def deprecate(pid: str, db: Session = Depends(get_db),
              actor: Principal = Depends(require_roles("admin", "reviewer"))):
    return _transition_route(pid, "deprecate", db, actor)


@router.post("/panels/{pid}/unlock", response_model=PanelOut, tags=["state"])
def unlock(pid: str, db: Session = Depends(get_db),
           actor: Principal = Depends(require_roles("admin"))):
    # governance-gated: locked → draft (the prior immutable version is retained)
    return _transition_route(pid, "unlock", db, actor)


@router.post("/panels/{pid}/archive", response_model=PanelOut, tags=["state"])
def archive(pid: str, db: Session = Depends(get_db),
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
    return _out(db, p)
