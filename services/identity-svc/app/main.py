from __future__ import annotations

import svc_base.audit  # noqa: F401 — registers the audit_events table on Base
from svc_base import create_app
from svc_base.db import init_db

from . import models  # noqa: F401 — registers the users table on Base
from .api import router
from .config import settings
from .db import SessionLocal, engine
from .domain import seed_admin

app = create_app(settings)
app.include_router(router)


@app.on_event("startup")
def _startup():
    init_db(engine)
    seed_admin(SessionLocal, settings)
