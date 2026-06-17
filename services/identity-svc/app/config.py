from __future__ import annotations

from svc_base import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "identity-svc"
    service_version: str = "0.1.0"

    database_url: str = "postgresql+psycopg2://postgres:postgres@postgres:5432/identity"

    # Seeded on first boot.
    admin_username: str = "admin"
    admin_password: str = "admin"
    admin_tenant: str = "refgen"


settings = Settings()
