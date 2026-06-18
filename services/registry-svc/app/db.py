from __future__ import annotations

from svc_base.db import make_engine, make_session_factory

from .config import settings

engine = make_engine(settings.database_url)
SessionLocal = make_session_factory(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
