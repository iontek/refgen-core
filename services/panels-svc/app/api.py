from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from svc_base.audit import record_audit
from svc_base.auth import Principal, assert_tenant_access, require_auth, require_roles
from svc_base.tenancy import scope_query
from svc_base.versioning import (
    assert_lockable, assert_mutable, assert_validatable, bump_semver, content_hash,
)

from .db import get_db
from .domain import VALID_TYPES, panel_snapshot, transition
from .models import Panel, PanelCustomRegion, PanelGene, PanelMember, PanelVersion
from .schemas import (
    AddGenesIn, GeneOut, LockIn, MarkConsumedIn, MemberIn, MemberOut, PanelIn,
    PanelOut, PanelPatch, RegionIn, RegionOut, UnlockIn, VersionOut,
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
    # Fork: clone genes + curated regions from a source panel into a new draft.
    # This is how a locked panel is "changed" — it is never edited in place.
    src = None
    if body.parent_id:
        src = _resolve(db, body.parent_id)
        if not src:
            raise HTTPException(status_code=404, detail="parent panel not found")
        assert_tenant_access(actor, src.tenant_id)
    p = Panel(label=body.label, type=body.type, details=body.details,
              created_by=actor.subject, tenant_id=actor.tenant_id, status="draft",
              parent_id=src.code if src else None)
    db.add(p)
    db.flush()
    p.code = _next_code(db)
    if src:
        for g in db.query(PanelGene).filter_by(panel_id=src.id).all():
            db.add(PanelGene(panel_id=p.id, symbol=g.symbol, hgnc_id=g.hgnc_id,
                             target=g.target, transcript_override=g.transcript_override,
                             notes=g.notes, added_by=actor.subject))
        for r in db.query(PanelCustomRegion).filter_by(panel_id=src.id).all():
            db.add(PanelCustomRegion(panel_id=p.id, chr=r.chr, start=r.start, end=r.end,
                                     name=r.name, kind=r.kind, hgvs=r.hgvs, note=r.note,
                                     added_by=actor.subject))
    db.commit()
    db.refresh(p)
    _audit(db, "panel.create", actor, p, parent_id=src.code if src else None)
    db.commit()
    return _out(db, p)


@router.get("/panels/pending", response_model=list[PanelOut], tags=["panels"])
def pending(db: Session = Depends(get_db), actor: Principal = Depends(require_auth)):
    panels = (scope_query(db.query(Panel), Panel, _scope(actor))
              .filter(Panel.status == "validated").order_by(Panel.id).all())
    counts = _counts_all(db, [p.id for p in panels])
    return [_panel_out(p, *(lambda c: (c.get("total", 0), c.get("DNA", 0), c.get("RNA", 0)))(counts.get(p.id, {})))
            for p in panels]


def _code(p: Panel) -> str:
    return p.code or f"panel-{p.id:04d}"


@router.get("/panels/compare", tags=["panels"])
def compare(ids: str = "", db: Session = Depends(get_db),
            actor: Principal = Depends(require_auth)):
    """Set algebra over the panels' gene symbols (dxm keys on symbol — no HGNC
    catalog). shared = intersection, union = all, only = per-panel exclusives."""
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    if len(id_list) < 2:
        raise HTTPException(status_code=400, detail="compare needs >=2 panel ids")
    panels, gene_sets = [], {}
    for pid in id_list:
        p = _get(db, pid, actor)
        syms = {g.symbol for g in db.query(PanelGene).filter_by(panel_id=p.id).all()}
        gene_sets[_code(p)] = syms
        panels.append({"id": _code(p), "label": p.label, "status": p.status,
                       "gene_count": len(syms)})
    sets = list(gene_sets.values())
    shared = sorted(set.intersection(*sets))
    union = sorted(set.union(*sets))
    only = {k: sorted(s - set.union(*[o for kk, o in gene_sets.items() if kk != k]))
            for k, s in gene_sets.items()}
    return {"panels": panels, "shared": shared, "shared_count": len(shared),
            "union": union, "union_count": len(union), "only": only}


@router.get("/panels/with-gene", tags=["panels"])
def with_gene(symbols: str = "", db: Session = Depends(get_db),
              actor: Principal = Depends(require_auth)):
    """Reverse lookup: which (non-archived) panels contain each gene symbol."""
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    out = {}
    for sym in syms:
        rows = (scope_query(db.query(Panel), Panel, _scope(actor))
                .join(PanelGene, PanelGene.panel_id == Panel.id)
                .filter(PanelGene.symbol == sym, Panel.status != "archived")
                .order_by(Panel.id).distinct().all())
        out[sym] = {"symbol": sym,
                    "panels": [{"id": _code(p), "label": p.label, "status": p.status}
                               for p in rows]}
    return out


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


# ── curated regions (part of the locked snapshot) ───────────────────────────

@router.get("/panels/{pid}/regions", response_model=list[RegionOut], tags=["regions"])
def list_regions(pid: str, db: Session = Depends(get_db),
                 actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    return (db.query(PanelCustomRegion).filter_by(panel_id=p.id)
            .order_by(PanelCustomRegion.chr, PanelCustomRegion.start).all())


@router.post("/panels/{pid}/regions", response_model=RegionOut, status_code=201,
             tags=["regions"])
def add_region(pid: str, body: RegionIn, db: Session = Depends(get_db),
               actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    assert_mutable(p.status)                      # locked → 409 (immutability)
    r = PanelCustomRegion(panel_id=p.id, chr=body.chr, start=body.start, end=body.end,
                          name=body.name, kind=body.kind or "other", hgvs=body.hgvs,
                          note=body.note, added_by=actor.subject)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.delete("/panels/{pid}/regions/{rid}", status_code=204, tags=["regions"])
def delete_region(pid: str, rid: int, db: Session = Depends(get_db),
                  actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    assert_mutable(p.status)
    r = db.get(PanelCustomRegion, rid)
    if r and r.panel_id == p.id:
        db.delete(r)
        db.commit()


@router.get("/panels/{pid}/history", response_model=list[VersionOut], tags=["versions"])
def history(pid: str, db: Session = Depends(get_db),
            actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    return (db.query(PanelVersion).filter_by(panel_id=p.id)
            .order_by(PanelVersion.id).all())


# ── members (project access control) ────────────────────────────────────────

def _member_out(code: str, m: PanelMember) -> dict:
    return {"id": m.id, "panel_id": code, "username": m.username, "role": m.role,
            "added_by": m.added_by, "added_at": _ms(m.added_at)}


def _can_manage_members(db: Session, panel: Panel, actor: Principal) -> bool:
    """admin, the panel creator, or an owner-member may manage membership."""
    if "admin" in (actor.roles or []):
        return True
    if actor.subject and actor.subject == panel.created_by:
        return True
    return (db.query(PanelMember)
            .filter_by(panel_id=panel.id, username=actor.subject, role="owner")
            .first() is not None)


@router.get("/panels/{pid}/members", response_model=list[MemberOut], tags=["members"])
def list_members(pid: str, db: Session = Depends(get_db),
                 actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    rows = (db.query(PanelMember).filter_by(panel_id=p.id)
            .order_by(PanelMember.role, PanelMember.username).all())
    return [_member_out(_code(p), m) for m in rows]


@router.post("/panels/{pid}/members", response_model=MemberOut, tags=["members"])
def add_member(pid: str, body: MemberIn, response: Response,
               db: Session = Depends(get_db),
               actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    if body.role not in PanelMember.ROLES:
        raise HTTPException(status_code=400,
                            detail=f"bad role; one of {list(PanelMember.ROLES)}")
    if not _can_manage_members(db, p, actor):
        raise HTTPException(status_code=403,
                            detail="only an owner, the creator, or an admin can manage members")
    m = db.query(PanelMember).filter_by(panel_id=p.id, username=body.username).first()
    created = m is None
    if m is None:                                  # idempotent upsert
        m = PanelMember(panel_id=p.id, username=body.username, role=body.role,
                        added_by=actor.subject)
        db.add(m)
    else:
        m.role = body.role
    db.commit()
    db.refresh(m)
    _audit(db, "panel.member_add" if created else "panel.member_update", actor, p,
           username=body.username, role=body.role)
    db.commit()
    response.status_code = 201 if created else 200
    return _member_out(_code(p), m)


@router.delete("/panels/{pid}/members/{mid}", status_code=204, tags=["members"])
def remove_member(pid: str, mid: int, db: Session = Depends(get_db),
                  actor: Principal = Depends(require_auth)):
    p = _get(db, pid, actor)
    if not _can_manage_members(db, p, actor):
        raise HTTPException(status_code=403,
                            detail="only an owner, the creator, or an admin can manage members")
    m = db.get(PanelMember, mid)
    if not m or m.panel_id != p.id:
        return                                     # idempotent
    if m.role == "owner":
        owners = db.query(PanelMember).filter_by(panel_id=p.id, role="owner").count()
        if owners <= 1:
            raise HTTPException(status_code=400, detail="cannot remove the last owner")
    uname = m.username
    db.delete(m)
    db.commit()
    _audit(db, "panel.member_remove", actor, p, username=uname)
    db.commit()


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
    p = _get(db, pid, actor)
    total, _, _ = _counts_for(db, p.id)
    assert_validatable(p.status, total)           # draft + ≥1 gene
    transition(p, "validate")
    db.commit()
    db.refresh(p)
    _audit(db, "panel.validate", actor, p)
    db.commit()
    return _out(db, p)


@router.post("/panels/{pid}/reject", response_model=PanelOut, tags=["state"])
def reject(pid: str, db: Session = Depends(get_db),
           actor: Principal = Depends(require_auth)):
    return _transition_route(pid, "reject", db, actor)


@router.post("/panels/{pid}/lock", response_model=PanelOut, tags=["state"])
def lock(pid: str, body: LockIn, db: Session = Depends(get_db),
         actor: Principal = Depends(require_roles("admin", "reviewer"))):
    p = _get(db, pid, actor)
    genes = db.query(PanelGene).filter_by(panel_id=p.id).all()
    assert_lockable(p.status, len(genes))         # validated + ≥1 gene
    regions = db.query(PanelCustomRegion).filter_by(panel_id=p.id).all()
    snap = panel_snapshot(p, genes, regions)      # pins genes + regions + ref versions
    chash = content_hash(snap)
    # No-op re-lock: identical content yields the same hash. Reject cleanly
    # instead of letting the unique constraint surface as a 500.
    if db.query(PanelVersion).filter_by(content_hash=chash).first():
        raise HTTPException(status_code=409,
                            detail="content unchanged since last lock — nothing to version")
    transition(p, "lock")
    prev = (db.query(PanelVersion).filter_by(panel_id=p.id)
            .order_by(PanelVersion.id.desc()).first())
    new_version = bump_semver(p.current_version, body.bump)   # first lock → 1.0.0
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
def unlock(pid: str, body: UnlockIn, db: Session = Depends(get_db),
           actor: Principal = Depends(require_roles("admin"))):
    """Undo a mistaken lock: locked → draft, keeping the immutable version row.
    Allowed ONLY while the current locked version has not been consumed by a
    run. Once a run has used it, the only path forward is a fork."""
    p = _get(db, pid, actor)
    cur = (db.query(PanelVersion).filter_by(panel_id=p.id)
           .order_by(PanelVersion.id.desc()).first())
    if cur and cur.consumed_at is not None:
        raise HTTPException(
            status_code=409,
            detail="locked version already used by a run — fork instead of unlocking",
        )
    transition(p, "unlock")                       # locked → draft
    db.commit()
    db.refresh(p)
    _audit(db, "panel.unlock", actor, p, reason=body.reason,
           version=cur.version if cur else None)
    db.commit()
    return _out(db, p)


@router.post("/versions/{vid}/mark-consumed", response_model=VersionOut,
             tags=["versions"])
def mark_consumed(vid: int, body: MarkConsumedIn, db: Session = Depends(get_db),
                  actor: Principal = Depends(require_auth)):
    """Internal callback: design-svc stamps a version when a run consumes it,
    which seals off the unlock escape hatch. Idempotent — the first run wins."""
    v = db.get(PanelVersion, vid)
    if not v:
        raise HTTPException(status_code=404, detail="version not found")
    assert_tenant_access(actor, v.tenant_id)
    if v.consumed_at is None:
        v.consumed_at = datetime.now(timezone.utc)
        v.consumed_by = body.run_id
        record_audit(db, action="version.consumed", actor=actor.subject,
                     tenant_id=v.tenant_id, entity_type="version", entity_id=v.id,
                     detail={"version": v.version, "run_id": body.run_id})
        db.commit()
        db.refresh(v)
    return v


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
