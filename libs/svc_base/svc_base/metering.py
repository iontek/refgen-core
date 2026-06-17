"""Metering foundation — usage events with an OUTBOX flag.

A billable action records a usage event locally (reported=False). A relay ships
unreported events to the central metering/billing collector and marks them
reported — so usage is never lost, even if the central plane is briefly
unreachable. The same event is invoice-line + proof-of-use.

See docs/mimari-vizyon.md §6/§7 (metering, distributed engine).
"""

from __future__ import annotations

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Integer, String, func,
)

from .db import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    feature = Column(String(64), nullable=False)        # e.g. "analysis"
    quantity = Column(Integer, nullable=False, default=1)
    actor = Column(String(64))
    detail = Column(JSON)
    reported = Column(Boolean, nullable=False, default=False, index=True)  # outbox
    created_at = Column(DateTime(timezone=True), server_default=func.now())


def record_usage(db, *, tenant_id, feature, quantity=1, actor=None, detail=None):
    """Record one billable usage event (outbox row). Caller commits."""
    ev = UsageEvent(
        tenant_id=tenant_id, feature=feature, quantity=quantity,
        actor=actor, detail=detail or {},
    )
    db.add(ev)
    return ev


def unreported(db, limit: int = 100):
    """Unshipped usage events, oldest first — what the relay sends centrally."""
    return (
        db.query(UsageEvent)
        .filter_by(reported=False)
        .order_by(UsageEvent.id)
        .limit(limit)
        .all()
    )
