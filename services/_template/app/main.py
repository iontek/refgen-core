"""Entry point. Builds the app from the shared base and mounts this
service's own routes under /api.
"""

from __future__ import annotations

from svc_base import create_app

from .api.routes import router
from .config import settings

app = create_app(settings)
app.include_router(router, prefix="/api")
