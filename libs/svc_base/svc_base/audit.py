"""Audit foundation — append-only log, written as a SHARED LIBRARY (not a
network service) so audit events can't be lost. Each service writes audit rows
into its OWN database; the central plane can aggregate later.

See docs/mimari-vizyon.md §14 (Güvenlik ve Uyum).
"""

from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, Integer, String, func

from .db import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(64), index=True)
    actor = Column(String(64))
    action = Column(String(128), nullable=False)
    entity_type = Column(String(64))
    entity_id = Column(String(64))
    detail = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


def record_audit(db, *, action, actor=None, tenant_id=None,
                 entity_type=None, entity_id=None, detail=None):
    """Append an immutable audit row. Caller commits the surrounding transaction."""
    ev = AuditEvent(
        action=action,
        actor=actor,
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail or {},
    )
    db.add(ev)
    return ev
