from __future__ import annotations

from sqlalchemy import (
    JSON, Column, DateTime, ForeignKey, Integer, String, Text, func,
)

from svc_base.db import Base
from svc_base.tenancy import TenantScopedMixin


class Panel(TenantScopedMixin, Base):
    __tablename__ = "panels"

    id = Column(Integer, primary_key=True)
    label = Column(String(255), nullable=False)
    type = Column("ptype", String(8), nullable=False, default="DNA")   # DNA/RNA/MIXED
    status = Column(String(16), nullable=False, default="draft")
    owner = Column(String(64))
    current_version = Column(String(16))
    details = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())


class PanelGene(Base):
    __tablename__ = "panel_genes"

    id = Column(Integer, primary_key=True)
    panel_id = Column(Integer, ForeignKey("panels.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    symbol = Column(String(32), nullable=False)
    target = Column(String(8), default="DNA")


class PanelVersion(TenantScopedMixin, Base):
    """Immutable snapshot created at lock time (the traceability record)."""

    __tablename__ = "panel_versions"

    id = Column(Integer, primary_key=True)
    panel_id = Column(Integer, ForeignKey("panels.id"), nullable=False, index=True)
    version = Column(String(16), nullable=False)
    content_hash = Column(String(64), nullable=False)
    snapshot = Column(JSON, nullable=False)
    note = Column(Text)
    locked_by = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
