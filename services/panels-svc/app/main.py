from __future__ import annotations

import svc_base.audit  # noqa: F401 — registers audit_events on Base
from svc_base import create_app
from svc_base.db import init_db

from . import models  # noqa: F401 — registers panel tables on Base
from .api import router
from .config import settings
from .db import engine

app = create_app(settings)
app.include_router(router)


@app.on_event("startup")
def _startup():
    init_db(engine)
