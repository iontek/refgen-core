"""JWT issuing + verification shared by every service.

identity-svc issues tokens with `issue_token`; every service verifies them
locally with the shared signing key (no network call on the hot path):

    @router.get("/me")
    def me(principal: Principal = Depends(require_auth)):
        return {"user": principal.subject}
"""

from __future__ import annotations

import datetime
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request


class Principal:
    """The authenticated caller, decoded from the bearer token."""

    def __init__(self, subject: Optional[str], roles: list, claims: dict):
        self.subject = subject
        self.roles = roles
        self.claims = claims


def issue_token(
    settings,
    subject: str,
    roles: Optional[list] = None,
    extra: Optional[dict] = None,
    expires_minutes: int = 720,
) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": subject,
        "user_id": subject,
        "roles": roles or [],
        "iat": now,
        "exp": now + datetime.timedelta(minutes=expires_minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode(token: str, settings) -> dict:
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}")


def get_principal(request: Request) -> Optional[Principal]:
    settings = request.app.state.settings
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        if settings.auth_required:
            raise HTTPException(status_code=401, detail="missing bearer token")
        return None
    claims = _decode(header.split(" ", 1)[1], settings)
    return Principal(
        subject=claims.get("user_id") or claims.get("sub"),
        roles=claims.get("roles", []),
        claims=claims,
    )


def require_auth(principal: Optional[Principal] = Depends(get_principal)) -> Principal:
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return principal


def require_roles(*roles: str):
    """Dependency factory for endpoints that need a specific role."""

    def checker(principal: Principal = Depends(require_auth)) -> Principal:
        if not set(roles) & set(principal.roles or []):
            raise HTTPException(status_code=403, detail="insufficient role")
        return principal

    return checker
