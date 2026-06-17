"""The front counter: this service's HTTP endpoints. Thin — they validate
input, call the domain layer, and return. No business logic lives here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from svc_base.auth import Principal, require_auth

from ..domain import services
from ..models.schemas import Echo, EchoIn

router = APIRouter(tags=["template"])


@router.get("/ping")
def ping() -> dict:
    return {"pong": True}


@router.post("/echo", response_model=Echo)
def echo(body: EchoIn) -> Echo:
    return services.make_echo(body.message)


@router.get("/whoami")
def whoami(principal: Principal = Depends(require_auth)) -> dict:
    """Example of a protected endpoint — requires a valid bearer token."""
    return {"subject": principal.subject, "roles": principal.roles}
