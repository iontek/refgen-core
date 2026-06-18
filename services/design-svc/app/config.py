from __future__ import annotations

from svc_base import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "design-svc"
    service_version: str = "0.1.0"
    database_url: str = "postgresql+psycopg2://postgres:postgres@postgres:5432/design"
    panels_url: str = "http://panels-svc:8000"   # cross-service: locked gate + panel genes/regions


settings = Settings()
