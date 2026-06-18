from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from svc_base import mcp_client
from svc_base.auth import Principal, require_auth

from .db import get_db
from .models import McpServer, McpTool
from .schemas import ServerDetailOut, ServerOut, StatusOut, SyncOut

router = APIRouter()

# mcp-status is hot (the dx TUI polls it) but the answer is the same for ~10s;
# an in-process TTL cache avoids hammering every MCP on each call (no Redis in dxm).
_STATUS_CACHE: dict = {"payload": None, "ts": 0.0}
_STATUS_TTL = 10.0


def _server_out(srv: McpServer, tool_count: int) -> dict:
    return {
        "id": srv.id, "name": srv.name, "display_name": srv.display_name,
        "description": srv.description, "host": srv.host, "port": srv.port,
        "protocol": srv.protocol, "category": srv.category, "version": srv.version,
        "is_enabled": srv.is_enabled, "base_url": srv.base_url,
        "tool_count": tool_count, "last_synced": srv.last_synced,
        "last_status": srv.last_status,
    }


def _resolve(db: Session, ident: str) -> McpServer | None:
    return (db.get(McpServer, ident)
            or db.query(McpServer).filter_by(name=ident).first())


@router.get("/registry/mcp-servers", response_model=list[ServerOut], tags=["registry"])
def list_servers(db: Session = Depends(get_db),
                 actor: Principal = Depends(require_auth)):
    servers = db.query(McpServer).order_by(McpServer.category, McpServer.name).all()
    counts = dict(db.query(McpTool.server_id, func.count(McpTool.id))
                  .group_by(McpTool.server_id).all())
    return [_server_out(s, counts.get(s.id, 0)) for s in servers]


@router.get("/registry/mcp-servers/{ident}", response_model=ServerDetailOut,
            tags=["registry"])
def server_detail(ident: str, db: Session = Depends(get_db),
                  actor: Principal = Depends(require_auth)):
    srv = _resolve(db, ident)
    if not srv:
        raise HTTPException(status_code=404, detail="server not found")
    tools = (db.query(McpTool).filter_by(server_id=srv.id)
             .order_by(McpTool.name).all())
    out = _server_out(srv, len(tools))
    out["tools"] = tools
    return out


@router.get("/mcp-status", response_model=StatusOut, tags=["mcp"])
def mcp_status(db: Session = Depends(get_db),
               actor: Principal = Depends(require_auth)):
    now = time.time()
    if _STATUS_CACHE["payload"] and (now - _STATUS_CACHE["ts"] < _STATUS_TTL):
        return {**_STATUS_CACHE["payload"], "cached": True}

    servers = (db.query(McpServer).filter_by(is_enabled=True)
               .order_by(McpServer.category, McpServer.name).all())
    entries = [(s.name, s.base_url, s.port, s.category) for s in servers]

    def _probe(entry):
        name, base_url, port, category = entry
        t0 = time.perf_counter()
        ok, _code, err = mcp_client.healthz(base_url)
        status = "up" if ok else ("degraded" if err and err.startswith("HTTP") else "down")
        return {"name": name, "port": port, "category": category, "status": status,
                "latency_ms": int((time.perf_counter() - t0) * 1000), "error": err}

    results = []
    if entries:
        with ThreadPoolExecutor(max_workers=min(len(entries), 16)) as ex:
            results = list(ex.map(_probe, entries))

    payload = {
        "summary": {
            "up":       sum(1 for r in results if r["status"] == "up"),
            "degraded": sum(1 for r in results if r["status"] == "degraded"),
            "down":     sum(1 for r in results if r["status"] == "down"),
            "total":    len(results),
        },
        "servers": results,
        "checked_at": int(now * 1000),
        "cached": False,
    }
    _STATUS_CACHE["payload"], _STATUS_CACHE["ts"] = payload, now
    return payload


@router.post("/registry/sync", response_model=SyncOut, tags=["registry"])
def sync(db: Session = Depends(get_db), actor: Principal = Depends(require_auth)):
    """Discover each server's tools via JSON-RPC tools/list; upsert McpTool rows
    and flag vanished tools as deprecated. Records last_synced / last_status."""
    servers = db.query(McpServer).filter_by(is_enabled=True).all()
    results, synced = [], 0
    for srv in servers:
        if srv.protocol == "static":
            results.append({"name": srv.name, "tools": 0, "error": "static (no tools)"})
            continue
        try:
            tools = mcp_client.list_tools(srv.base_url)
        except Exception as exc:  # noqa: BLE001 — record any transport/HTTP error
            srv.last_status = "down"
            db.commit()
            results.append({"name": srv.name, "tools": 0,
                            "error": type(exc).__name__})
            continue
        seen = set()
        for t in tools:
            seen.add(t["name"])
            row = (db.query(McpTool)
                   .filter_by(server_id=srv.id, name=t["name"]).first())
            if row is None:
                db.add(McpTool(server_id=srv.id, name=t["name"],
                               description=t["description"],
                               input_schema=t["input_schema"], is_deprecated=False))
            else:
                row.description = t["description"]
                row.input_schema = t["input_schema"]
                row.is_deprecated = False
        stale = db.query(McpTool).filter_by(server_id=srv.id, is_deprecated=False)
        if seen:
            stale = stale.filter(~McpTool.name.in_(seen))
        for s in stale.all():
            s.is_deprecated = True
        srv.last_synced = datetime.now(timezone.utc)
        srv.last_status = "up"
        synced += 1
        db.commit()
        results.append({"name": srv.name, "tools": len(tools), "error": None})
    return {"synced": synced, "results": results}
