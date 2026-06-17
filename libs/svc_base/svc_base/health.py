"""The two endpoints every service exposes the same way: a liveness probe
(used by the Docker healthcheck) and a version stamp.
"""

from __future__ import annotations

from fastapi import APIRouter

from .config import BaseServiceSettings


def health_router(settings: BaseServiceSettings) -> APIRouter:
    router = APIRouter(tags=["meta"])

    @router.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "service": settings.service_name}

    @router.get("/version")
    def version() -> dict:
        return {
            "service": settings.service_name,
            "version": settings.service_version,
        }

    return router
