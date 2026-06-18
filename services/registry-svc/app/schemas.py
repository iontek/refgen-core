from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    server_id: str
    name: str
    description: Optional[str] = None
    input_schema: dict = {}
    is_deprecated: bool = False


class ServerOut(BaseModel):
    id: str
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    host: str
    port: int
    protocol: str
    category: str
    version: Optional[str] = None
    is_enabled: bool = True
    base_url: str
    tool_count: int = 0
    last_synced: Optional[datetime] = None
    last_status: Optional[str] = None


class ServerDetailOut(ServerOut):
    tools: List[ToolOut] = []


class StatusServer(BaseModel):
    name: str
    port: int
    category: str
    status: str            # up / degraded / down
    latency_ms: int
    error: Optional[str] = None


class StatusSummary(BaseModel):
    up: int = 0
    degraded: int = 0
    down: int = 0
    total: int = 0


class StatusOut(BaseModel):
    summary: StatusSummary
    servers: List[StatusServer]
    checked_at: int        # epoch ms
    cached: bool = False


class SyncServerResult(BaseModel):
    name: str
    tools: int = 0
    error: Optional[str] = None


class SyncOut(BaseModel):
    synced: int
    results: List[SyncServerResult]
