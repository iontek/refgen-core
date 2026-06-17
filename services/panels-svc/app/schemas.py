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
    label: str
    type: str
    status: str
    owner: Optional[str] = None
    tenant_id: str
    current_version: Optional[str] = None
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
    target: Optional[str] = None


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
    note: Optional[str] = None
    locked_by: Optional[str] = None
    created_at: Optional[datetime] = None
