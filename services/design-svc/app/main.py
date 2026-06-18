from __future__ import annotations

from svc_base import create_app
from svc_base.db import init_db

from . import models  # noqa: F401 — registers probe-design tables on Base
from .api import router
from .config import settings
from .db import SessionLocal, engine
from .seed_recipes import seed_recipes

app = create_app(settings)
app.include_router(router)


@app.on_event("startup")
def _startup():
    init_db(engine)
    seed_recipes(SessionLocal)
