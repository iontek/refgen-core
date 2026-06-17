from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class PanelIn(BaseModel):
    label: str
    type: str = "DNA"
    details: Optional[str] = None


class PanelPatch(BaseModel):
    label: Optional[str] = None
    type: Optional[str] = None
    details: Optional[str] = None


class PanelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: Optional[str] = None
    label: str
    type: str
    status: str
    created_by: Optional[str] = None
    tenant_id: str
    current_version: Optional[str] = None
    parent_id: Optional[str] = None
    details: Optional[str] = None
    created_at: Optional[datetime] = None


class AddGenesIn(BaseModel):
    symbols: List[str]
    target: Optional[str] = None


class GeneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    panel_id: int
    symbol: str
    hgnc_id: Optional[str] = None
    target: Optional[str] = None
    transcript_override: Optional[str] = None


class LockIn(BaseModel):
    bump: str = "minor"
    note: Optional[str] = None
    signed_off_by: Optional[str] = None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    panel_id: int
    version: str
    content_hash: str
    parent_hash: Optional[str] = None
    bump_kind: Optional[str] = None
    note: Optional[str] = None
    locked_by: Optional[str] = None
    signed_off_by: Optional[str] = None
    created_at: Optional[datetime] = None
