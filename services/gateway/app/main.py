"""Edge gateway — the single front door.

Presents one public API under /api/* and forwards to the right service. It
verifies the JWT centrally (then forwards it for the service to re-check) and
preserves the dx contract: dx points DX_SERVER here and works unchanged.

Routing (after stripping the /api prefix), by first path segment:
    auth, users, access      -> identity-svc
    panels, versions,
    panel-genes              -> panels-svc
Public (no token): POST /api/auth/token, POST /api/auth/refresh.
"""

from __future__ import annotations

import httpx
from fastapi import HTTPException, Request, Response

from svc_base import create_app
from svc_base.auth import _decode

from .config import settings

app = create_app(settings)

_ROUTES = {
    "auth": settings.identity_url,
    "users": settings.identity_url,
    "access": settings.identity_url,
    "panels": settings.panels_url,
    "versions": settings.panels_url,
    "panel-genes": settings.panels_url,
    "registry": settings.registry_url,     # MCP catalog + lifecycle
    "mcp-status": settings.registry_url,   # MCP health summary
}

_PUBLIC = {
    ("POST", "/api/auth/token"),
    ("POST", "/api/auth/refresh"),
}

_HOP = {"host", "content-length", "transfer-encoding", "connection", "keep-alive"}


@app.on_event("startup")
async def _startup():
    app.state.client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)


@app.on_event("shutdown")
async def _shutdown():
    await app.state.client.aclose()


@app.api_route("/api/{path:path}",
               methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request):
    segment = path.split("/", 1)[0]
    base = _ROUTES.get(segment)
    if base is None:
        raise HTTPException(status_code=404, detail="no route for /api/" + path)

    # auth gate (public paths skip it); tolerant of trailing slashes
    if (request.method, "/api/" + path.rstrip("/")) not in _PUBLIC:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="authentication required")
        _decode(header.split(" ", 1)[1], settings)   # raises 401 if invalid

    target = base + "/" + path.rstrip("/")
    body = await request.body()
    fwd_headers = {k: v for k, v in request.headers.items()
                   if k.lower() not in _HOP}

    upstream = await app.state.client.request(
        request.method, target,
        params=dict(request.query_params), content=body, headers=fwd_headers,
    )
    resp_headers = {k: v for k, v in upstream.headers.items()
                    if k.lower() not in _HOP}
    return Response(content=upstream.content, status_code=upstream.status_code,
                    headers=resp_headers)
