"""Test harness for design-svc: app from create_app + router, fresh in-memory
SQLite per test (recipes seeded), auth stubbed to admin."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("AUTH_REQUIRED", "false")

from dataclasses import dataclass  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from svc_base import create_app  # noqa: E402
from svc_base.auth import Principal, require_auth  # noqa: E402
from svc_base.db import Base  # noqa: E402

from app import models  # noqa: E402,F401 — registers probe-design tables
from app.api import router  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import get_db  # noqa: E402
from app.seed_recipes import seed_recipes  # noqa: E402


@dataclass
class Ctx:
    client: TestClient
    Session: object


@pytest.fixture
def ctx():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    seed_recipes(TestingSession)

    app = create_app(settings)
    app.include_router(router)

    def _get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    def _principal():
        return Principal(subject="admin", roles=["admin"],
                         claims={"tenant_id": "refgen", "scope": ["refgen"]})

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[require_auth] = _principal
    yield Ctx(client=TestClient(app), Session=TestingSession)
    app.dependency_overrides.clear()
