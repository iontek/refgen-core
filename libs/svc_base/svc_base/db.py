"""Shared database helpers. Each service owns its OWN database; this just
removes the boilerplate of engine/session setup and table-creation-with-retry
(Postgres may not accept connections the instant a service container boots).
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

log = logging.getLogger(__name__)

# Each service process imports its own models against this Base, so its
# metadata only ever contains that service's tables.
Base = declarative_base()


def make_engine(database_url: str) -> Engine:
    connect_args = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def make_session_factory(engine: Engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(engine: Engine, base=Base, retries: int = 30, delay: float = 1.0) -> None:
    """Wait for the database to accept connections, then create tables."""
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            base.metadata.create_all(engine)
            log.info("database ready (%d tables)", len(base.metadata.tables))
            return
        except Exception as exc:  # noqa: BLE001 - retry on anything until ready
            last_error = exc
            log.warning("db not ready (attempt %d/%d): %s", attempt, retries, exc)
            time.sleep(delay)
    raise RuntimeError(f"database never became ready: {last_error}")
