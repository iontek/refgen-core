from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict


# ── recipes ───────────────────────────────────────────────────────────────────

class RecipeIn(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str = ""
    spec: dict = {}          # molecule / applies_to / target / design / steps


class RecipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    version: str
    description: Optional[str] = None
    content_hash: str
    status: str
    created_by: Optional[str] = None
    spec: dict = {}


# ── adapter sets ──────────────────────────────────────────────────────────────

class AdapterIn(BaseModel):
    name: str
    platform: str = "twist_dna"
    adapter_5p: str = ""
    adapter_3p: str = ""
    has_t7: bool = False
    purpose: str = ""
    note: str = ""


class AdapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    platform: str
    adapter_5p: Optional[str] = None
    adapter_3p: Optional[str] = None
    has_t7: bool = False
    purpose: Optional[str] = None
    content_hash: Optional[str] = None
    note: Optional[str] = None
    created_by: Optional[str] = None


# ── runs (read scaffolding in Phase 1) ────────────────────────────────────────

class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    step_order: int
    step_name: str
    status: str
    tool_id: Optional[str] = None
    result: dict = {}
    duration_ms: Optional[int] = None


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    path: Optional[str] = None
    size_bytes: int = 0
    sha256: Optional[str] = None
    is_locked: bool = False


class RunOut(BaseModel):
    id: str
    pipeline_slug: str
    panel_id: Optional[str] = None
    panel_version: Optional[str] = None
    gene_symbol: Optional[str] = None
    status: str
    params: dict = {}
    params_hash: Optional[str] = None
    summary: dict = {}
    error: Optional[str] = None
    triggered_by: Optional[str] = None
    created_at: Optional[int] = None      # ms epoch
    started_at: Optional[int] = None
    ended_at: Optional[int] = None


class RunDetailOut(RunOut):
    steps: List[StepOut] = []
    artifacts: List[ArtifactOut] = []


# ── MCP passthrough bodies ────────────────────────────────────────────────────

class LitIn(BaseModel):
    tool: str
    args: dict = {}


class AgentRunIn(BaseModel):
    task: str
    agent: str = "oligo-assistant"
    history: list = []
    model: Optional[str] = None


class AnalystIn(BaseModel):
    variant: str
