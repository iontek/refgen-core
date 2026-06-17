"""svc_base — the shared barebone framework for refgen-core microservices.

Every service is built by calling `create_app(settings)` with its own
`Settings` (subclass of `BaseServiceSettings`). The base provides the parts
every service needs identically: /healthz, /version, structured logging with
request-ids, JWT auth, uniform error handling, and DB helpers.
"""

from .app import create_app
from .config import BaseServiceSettings

__all__ = ["create_app", "BaseServiceSettings"]
__version__ = "0.2.0"
