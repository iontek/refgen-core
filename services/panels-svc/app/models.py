from __future__ import annotations

from sqlalchemy import (
    JSON, BigInteger, Column, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
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
    __table_args__ = (
        UniqueConstraint("panel_id", "version", name="uq_panel_version"),
    )

    id = Column(Integer, primary_key=True)
    panel_id = Column(Integer, ForeignKey("panels.id"), nullable=False, index=True)
    version = Column(String(16), nullable=False)
    content_hash = Column(String(128), nullable=False, unique=True)  # immutable identity
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
    # A version is "consumed" once a downstream run uses it. While unset, a
    # mistaken lock can be undone (unlock → draft); once set, the only path
    # forward is a fork. design-svc stamps this via the mark-consumed callback.
    consumed_at = Column(DateTime(timezone=True))
    consumed_by = Column(String(128))          # e.g. the run id that consumed it


class PanelCustomRegion(Base):
    """Designer-curated region added to a panel's target beyond MANE CDS + auto
    hotspots — promoter, clinical UTR, founder/PGx position, paralog-discriminating
    base. Part of the locked snapshot, so it pins into the content_hash. Reached
    only via its panel (like PanelGene), so it inherits the panel's tenant scope."""

    __tablename__ = "panel_custom_regions"

    id = Column(Integer, primary_key=True)
    panel_id = Column(Integer, ForeignKey("panels.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    chr = Column(String(10), nullable=False)
    start = Column(BigInteger, nullable=False)   # 0-based half-open
    end = Column(BigInteger, nullable=False)
    name = Column(String(120), nullable=False)
    kind = Column(String(20), default="other")   # promoter/utr/founder/pgx/paralog/…
    hgvs = Column(String(200))
    note = Column(Text)
    added_by = Column(String(64))
    added_at = Column(DateTime(timezone=True), server_default=func.now())


class PanelMember(Base):
    """A user assigned to a panel (project) with a role. `username` is a
    cross-service string reference to identity-svc — NOT a FK (users live in
    another service). Reached only via its panel."""

    __tablename__ = "panel_members"
    __table_args__ = (UniqueConstraint("panel_id", "username", name="uq_panel_member"),)

    ROLES = ("owner", "designer", "reviewer", "observer", "external")

    id = Column(Integer, primary_key=True)
    panel_id = Column(Integer, ForeignKey("panels.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    username = Column(String(80), nullable=False)
    role = Column(String(20), default="observer")
    added_by = Column(String(80), default="")
    added_at = Column(DateTime(timezone=True), server_default=func.now())
