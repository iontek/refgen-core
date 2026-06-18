"""Probe-design models — ported from the platform's probe_design app.

Operational, transactional state (runs/steps/artifacts/oligos) owned here via ORM
(NOT behind an MCP — see mimari-vizyon §13). Cross-service references to a panel
are loose strings ({panel_id, panel_version}), not FKs into panels-svc. The heavy
pipeline that fills these is Phase 2; Phase 1 stands up the schema + catalog +
MCP passthrough.
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import (
    JSON, BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from svc_base.db import Base
from svc_base.tenancy import TenantScopedMixin


def _uuid_hex() -> str:
    return uuid.uuid4().hex


class ProbeRun(TenantScopedMixin, Base):
    """A pipeline run. Pins the locked panel version it computed against
    (panel_id + panel_version) for reproducibility. parent_run chains stages."""

    __tablename__ = "probe_runs"

    id = Column(String(64), primary_key=True, default=_uuid_hex)
    pipeline_slug = Column(String(80), default="create-target-bed")
    panel_id = Column(String(80))            # cross-service → panels-svc Panel.code
    panel_version = Column(String(80))       # cross-service → panels-svc PanelVersion
    gene_symbol = Column(String(80))
    status = Column(String(20), default="queued")  # queued/running/success/failed/canceled
    params = Column(JSON, default=dict)
    params_hash = Column(String(72), default="")   # sha256: over params (reproducibility)
    workspace_dir = Column(String(300), default="")
    summary = Column(JSON, default=dict)
    error = Column(Text, default="")
    parent_run_id = Column(String(64), ForeignKey("probe_runs.id"), nullable=True)
    triggered_by = Column(String(80), default="")
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    steps = relationship("ProbeRunStep", back_populates="run",
                         cascade="all, delete-orphan")
    artifacts = relationship("ProbeArtifact", back_populates="run",
                             cascade="all, delete-orphan")


class ProbeRunStep(Base):
    __tablename__ = "probe_run_steps"
    __table_args__ = (UniqueConstraint("run_id", "step_order", name="uq_run_step"),)

    id = Column(Integer, primary_key=True)
    run_id = Column(String(64), ForeignKey("probe_runs.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    step_order = Column(Integer, nullable=False)
    step_name = Column(String(80), nullable=False)
    status = Column(String(20), default="pending")  # pending/running/success/failed/skipped
    tool_id = Column(String(120), default="")       # e.g. nf-mcp.run_workflow
    args = Column(JSON, default=dict)
    result = Column(JSON, default=dict)
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    log_excerpt = Column(Text, default="")

    run = relationship("ProbeRun", back_populates="steps")


class ProbeArtifact(Base):
    __tablename__ = "probe_artifacts"

    id = Column(Integer, primary_key=True)
    run_id = Column(String(64), ForeignKey("probe_runs.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    step_id = Column(Integer, ForeignKey("probe_run_steps.id"), nullable=True)
    kind = Column(String(40), nullable=False)   # target_bed/baits_fasta/qc_json/…
    path = Column(String(400), default="")
    size_bytes = Column(BigInteger, default=0)
    sha256 = Column(String(72), default="")     # content hash of the deliverable
    mime_type = Column(String(80), default="")
    is_locked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    run = relationship("ProbeRun", back_populates="artifacts")


class ProbeOligo(Base):
    """Per-oligo QC index over the FASTA/JSON deliverables. adapter_set_hash pins
    the exact adapter version assembled in."""

    __tablename__ = "probe_oligos"

    id = Column(Integer, primary_key=True)
    run_id = Column(String(64), ForeignKey("probe_runs.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    panel_id = Column(String(80), index=True)
    name = Column(String(120), nullable=False)
    gene_symbol = Column(String(80), default="")
    chr = Column(String(10), default="")
    start = Column(BigInteger)
    end = Column(BigInteger)
    capture_seq = Column(Text, default="")      # bait only, no adapters
    full_seq = Column(Text, default="")         # capture + adapters (post-assemble)
    adapter_set_id = Column(Integer, ForeignKey("adapter_sets.id"), nullable=True)
    adapter_set_hash = Column(String(80), default="")
    pool = Column(String(40), default="")
    length = Column(Integer)
    gc_capture = Column(Float)
    gc_full = Column(Float)
    tm = Column(Float)
    offtarget_hits = Column(Integer)
    low_complexity = Column(Boolean)
    status = Column(String(24), default="ok")   # ok/flagged_gc/flagged_tm/…
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AdapterSet(Base):
    """Versioned 5'/3' adapter definition — immutable per content_hash (global
    catalog, not tenant-scoped). Oligos pin the exact hash they assembled with."""

    __tablename__ = "adapter_sets"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    platform = Column(String(20), default="twist_dna")
    adapter_5p = Column(String(200), default="")
    adapter_3p = Column(String(200), default="")
    has_t7 = Column(Boolean, default=False)
    purpose = Column(String(120), default="")
    content_hash = Column(String(80), default="")
    note = Column(Text, default="")
    created_by = Column(String(80), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def compute_hash(self) -> str:
        canon = f"{self.platform}|{self.adapter_5p}|{self.adapter_3p}"
        return "sha256:" + hashlib.sha256(canon.encode()).hexdigest()


class Recipe(Base):
    """Named, versioned run-method (ADR-0005) — immutable per (name, version) +
    content_hash. spec = molecule/applies_to/target/design/steps. Global catalog."""

    __tablename__ = "recipes"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_recipe_name_version"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    version = Column(String(20), default="1.0.0")
    content_hash = Column(String(80), unique=True, nullable=False)
    spec = Column(JSON, default=dict)
    description = Column(String(400), default="")
    status = Column(String(20), default="published")  # draft/published/archived
    created_by = Column(String(80), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
