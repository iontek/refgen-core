"""MCP client — JSON-RPC 2.0 over HTTP to reach the MCP substrate (the engine).

The MCPs (nf-mcp, r-mcp, db-mcp, …) are independent services on refgen-net; this
is the shared helper dxm services use to discover (`tools/list`) and call
(`tools/call`) their tools, plus a `/healthz` probe. Mirrors the platform's
probe_design/steps/_common.py + mcp_registry sync.

Only engine-adjacent services (registry-svc, design-svc) import this — the
customer-facing services never touch the MCPs directly (the IP wall).
"""

from __future__ import annotations

import os

import httpx


def mcp_url(service: str, port: int) -> str:
    """Base URL for an MCP. Defaults to the compose service name on refgen-net
    (e.g. http://nf-mcp:3004/), overridable via <SERVICE>_URL (e.g. NF_MCP_URL)
    for remote / non-Docker deployments."""
    env = f"{service.upper().replace('-', '_')}_URL"
    return os.environ.get(env, f"http://{service}:{port}/")


def _rpc_endpoint(base_url: str) -> str:
    return base_url.rstrip("/") + "/"


def _normalize_tools(raw) -> list[dict]:
    """Normalise a JSON-RPC `result.tools[]` payload to our stored shape. MCP
    uses camelCase `inputSchema`; we keep `input_schema`. Drops nameless tools."""
    out = []
    for t in raw or []:
        name = (t.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name": name,
            "description": t.get("description") or "",
            "input_schema": t.get("inputSchema") or t.get("input_schema") or {},
        })
    return out


def list_tools(base_url: str, *, timeout: float = 3.0) -> list[dict]:
    """JSON-RPC `tools/list` → [{name, description, input_schema}]. Raises on
    transport/HTTP error so the caller can record last_status."""
    r = httpx.post(_rpc_endpoint(base_url),
                   json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                   timeout=timeout)
    r.raise_for_status()
    return _normalize_tools((r.json().get("result") or {}).get("tools"))


def call_tool(base_url: str, name: str, arguments: dict | None = None,
              *, timeout: float = 60.0) -> dict:
    """JSON-RPC `tools/call` → raw response dict. design-svc uses this to
    delegate compute to nf-mcp/r-mcp/etc."""
    r = httpx.post(_rpc_endpoint(base_url),
                   json={"jsonrpc": "2.0", "method": "tools/call", "id": 1,
                         "params": {"name": name, "arguments": arguments or {}}},
                   timeout=timeout)
    r.raise_for_status()
    return r.json()


def healthz(base_url: str, *, timeout: float = 1.5):
    """Probe /healthz → (ok: bool, http_status: int|None, error: str|None)."""
    try:
        r = httpx.get(base_url.rstrip("/") + "/healthz", timeout=timeout)
        ok = r.status_code == 200
        return ok, r.status_code, (None if ok else f"HTTP {r.status_code}")
    except httpx.HTTPError as exc:
        return False, None, type(exc).__name__
