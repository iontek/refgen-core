from __future__ import annotations

from sqlalchemy import (
    JSON, Column, DateTime, ForeignKey, Integer, String, Text, func,
)

from svc_base.db import Base
from svc_base.tenancy import TenantScopedMixin


class Panel(TenantScopedMixin, Base):
    __tablename__ = "panels"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, index=True)   # legacy id e.g. "panel-0024"
    label = Column(String(255), nullable=False)
    type = Column("ptype", String(8), nullable=False, default="DNA")  # DNA/RNA/MIXED
    status = Column(String(16), nullable=False, default="draft")
    details = Column(Text)
    sub_a = Column(String(128))           # set-op provenance (source A)
    sub_b = Column(String(128))           # set-op provenance (source B)
    parent_id = Column(String(64))        # fork lineage (parent panel code)
    deadline = Column(DateTime(timezone=True))
    current_version = Column(String(64))
    created_by = Column(String(64))
    archived_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())


class PanelGene(Base):
    __tablename__ = "panel_genes"

    id = Column(Integer, primary_key=True)
    panel_id = Column(Integer, ForeignKey("panels.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    symbol = Column(String(64), nullable=False)
    hgnc_id = Column(String(32))
    target = Column(String(8), default="DNA")
    transcript_override = Column(String(64))   # clinically important
    notes = Column(Text)
    added_by = Column(String(64))
    added_at = Column(DateTime(timezone=True), server_default=func.now())


class PanelVersion(TenantScopedMixin, Base):
    """Immutable snapshot created at lock time — the traceability record."""

    __tablename__ = "panel_versions"

    id = Column(Integer, primary_key=True)
    panel_id = Column(Integer, ForeignKey("panels.id"), nullable=False, index=True)
    version = Column(String(16), nullable=False)
    content_hash = Column(String(128), nullable=False)
    parent_hash = Column(String(128))          # version lineage
    bump_kind = Column(String(8))
    status = Column(String(16))
    snapshot = Column(JSON, nullable=False)
    bait_files_path = Column(String(255))
    lock_file_path = Column(String(255))
    note = Column(Text)
    locked_by = Column(String(64))
    signed_off_by = Column(String(64))         # governance signature
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    locked_at = Column(DateTime(timezone=True))
