"""create_app() — the factory every service calls to get a wired FastAPI app
with the shared cross-cutting concerns already in place.
"""

from __future__ import annotations

from fastapi import FastAPI, Request

from .config import BaseServiceSettings
from .errors import install_error_handlers
from .health import health_router
from .logging import new_request_id, request_id_var, setup_logging


def create_app(settings: BaseServiceSettings) -> FastAPI:
    setup_logging(settings.service_name, settings.log_level)

    app = FastAPI(title=settings.service_name, version=settings.service_version)
    app.state.settings = settings

    @app.middleware("http")
    async def _request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or new_request_id()
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = rid
        return response

    install_error_handlers(app)
    app.include_router(health_router(settings))
    return app
