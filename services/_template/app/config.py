"""This service's settings: the shared base plus anything unique to it."""

from __future__ import annotations

from svc_base import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "template-svc"
    service_version: str = "0.1.0"

    # Each service owns its own database. SQLite by default so the template
    # runs with zero infrastructure; production points this at Postgres.
    database_url: str = "sqlite:///./template.db"


settings = Settings()
