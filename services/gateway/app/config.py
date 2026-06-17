from __future__ import annotations

from svc_base import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "edge-gateway"
    service_version: str = "0.1.0"

    identity_url: str = "http://identity-svc:8000"
    panels_url: str = "http://panels-svc:8000"


settings = Settings()
