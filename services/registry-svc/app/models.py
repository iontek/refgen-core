from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from svc_base.db import Base


def _uuid_hex() -> str:
    return uuid.uuid4().hex


class McpServer(Base):
    """A registered MCP server (engine component). NOT tenant-scoped — the MCP
    substrate is shared infrastructure, the same for every tenant. Mirrors the
    platform's mcp_registry.McpServer."""

    __tablename__ = "mcp_servers"

    id = Column(String(64), primary_key=True, default=_uuid_hex)
    name = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(120), default="")
    description = Column(Text, default="")
    host = Column(String(120), default="host.docker.internal")  # on refgen-net = service name
    port = Column(Integer, nullable=False)
    protocol = Column(String(20), default="jsonrpc")   # jsonrpc / rest / static
    category = Column(String(30), default="custom")    # core/compute/pipeline/viz/knowledge/...
    version = Column(String(32), default="")
    tags = Column(JSON, default=list)
    docs_url = Column(String(255), default="")
    repo_url = Column(String(255), default="")
    is_enabled = Column(Boolean, default=True)
    last_synced = Column(DateTime(timezone=True))
    last_status = Column(String(16), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    tools = relationship("McpTool", back_populates="server",
                         cascade="all, delete-orphan")

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class McpTool(Base):
    """A tool exposed by an MCP server, discovered via JSON-RPC tools/list."""

    __tablename__ = "mcp_tools"
    __table_args__ = (UniqueConstraint("server_id", "name", name="uq_mcp_tool"),)

    id = Column(String(64), primary_key=True, default=_uuid_hex)
    server_id = Column(String(64), ForeignKey("mcp_servers.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, default="")
    input_schema = Column(JSON, default=dict)
    is_deprecated = Column(Boolean, default=False)
    tags = Column(JSON, default=list)
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now(),
                       onupdate=func.now())

    server = relationship("McpServer", back_populates="tools")
