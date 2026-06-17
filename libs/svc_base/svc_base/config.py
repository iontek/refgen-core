"""Settings every service inherits. Values come from environment variables
(or a local .env file), so the same image behaves differently per deployment.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Identity of this service (each service overrides these defaults).
    service_name: str = "service"
    service_version: str = "0.0.0"
    log_level: str = "INFO"

    # JWT verification — aligns with the platform's djangorestframework-simplejwt
    # (HS256 + a shared signing key) so tokens issued by identity-svc are
    # accepted everywhere without a network round-trip.
    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"

    # When False (dev default), endpoints that ask for a principal still work
    # anonymously. The gateway and protected services flip this on.
    auth_required: bool = False
