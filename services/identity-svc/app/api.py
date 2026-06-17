from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from svc_base.audit import record_audit
from svc_base.auth import (
    Principal, _decode, issue_token, require_auth, require_roles,
)

from .config import settings
from .db import get_db
from .domain import caps, hash_password, to_user_out, verify_password
from .models import User
from .schemas import AccessOut, LoginIn, RefreshIn, TokenOut, UserIn, UserOut

router = APIRouter()

ACCESS_MIN = 720            # 12h
REFRESH_MIN = 60 * 24 * 7   # 7d


def _issue_pair(user: User):
    access = issue_token(
        settings, subject=str(user.id), roles=[user.role],
        tenant_id=user.tenant_id, scope=[user.tenant_id], entitlements=[],
        extra={"username": user.username, "role": user.role},
        expires_minutes=ACCESS_MIN,
    )
    refresh = issue_token(
        settings, subject=str(user.id), tenant_id=user.tenant_id,
        extra={"type": "refresh"}, expires_minutes=REFRESH_MIN,
    )
    return access, refresh


# ── auth ────────────────────────────────────────────────────────────────────

@router.post("/auth/token", response_model=TokenOut, tags=["auth"])
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(username=body.username, is_active=True).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    access, refresh = _issue_pair(u)
    return TokenOut(access=access, refresh=refresh)


@router.post("/auth/refresh", response_model=AccessOut, tags=["auth"])
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    claims = _decode(body.refresh, settings)
    if claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="not a refresh token")
    u = db.get(User, int(claims["user_id"]))
    if not u or not u.is_active:
        raise HTTPException(status_code=401, detail="user inactive")
    access, _ = _issue_pair(u)
    return AccessOut(access=access)


# ── users ─────────────────────────────────────────────────────────────────

@router.get("/users/me", response_model=UserOut, tags=["users"])
def me(principal: Principal = Depends(require_auth), db: Session = Depends(get_db)):
    u = db.get(User, int(principal.subject))
    if not u:
        raise HTTPException(status_code=404, detail="not found")
    return to_user_out(u)


@router.get("/users", response_model=list[UserOut], tags=["users"])
def list_users(db: Session = Depends(get_db),
               _: Principal = Depends(require_roles("admin"))):
    return [to_user_out(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/users", response_model=UserOut, status_code=201, tags=["users"])
def create_user(body: UserIn, db: Session = Depends(get_db),
                actor: Principal = Depends(require_roles("admin"))):
    if db.query(User).filter_by(username=body.username).first():
        raise HTTPException(status_code=409, detail="username exists")
    u = User(
        username=body.username, password_hash=hash_password(body.password),
        role=body.role, display_name=body.display_name, email=body.email,
        tenant_id=body.tenant_id or actor.tenant_id, is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    record_audit(db, action="user.create", actor=actor.subject,
                 tenant_id=u.tenant_id, entity_type="user", entity_id=u.id,
                 detail={"role": u.role})
    db.commit()
    return to_user_out(u)


@router.post("/users/{uid}/set-password", tags=["users"])
def set_password(uid: int, body: dict, db: Session = Depends(get_db),
                 _: Principal = Depends(require_roles("admin"))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(status_code=404, detail="not found")
    pw = body.get("password")
    if not pw:
        raise HTTPException(status_code=400, detail="password required")
    u.password_hash = hash_password(pw)
    db.commit()
    return {"status": "ok"}


@router.delete("/users/{uid}", status_code=204, tags=["users"])
def delete_user(uid: int, db: Session = Depends(get_db),
                _: Principal = Depends(require_roles("admin"))):
    u = db.get(User, uid)
    if u:
        db.delete(u)
        db.commit()


@router.post("/users/{uid}/enable", response_model=UserOut, tags=["users"])
def enable_user(uid: int, db: Session = Depends(get_db),
                _: Principal = Depends(require_roles("admin"))):
    return _set_active(uid, True, db)


@router.post("/users/{uid}/disable", response_model=UserOut, tags=["users"])
def disable_user(uid: int, db: Session = Depends(get_db),
                 _: Principal = Depends(require_roles("admin"))):
    return _set_active(uid, False, db)


def _set_active(uid: int, active: bool, db: Session):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(status_code=404, detail="not found")
    u.is_active = active
    db.commit()
    return to_user_out(u)


# ── access (permission view for the caller) ─────────────────────────────────

@router.get("/access", tags=["access"])
def access(principal: Principal = Depends(require_auth)):
    role = principal.claims.get("role") or (principal.roles[0] if principal.roles else None)
    return {
        "role": role,
        "tenant_id": principal.tenant_id,
        "is_admin": role == "admin",
        **caps(role or ""),
        "scope": principal.scope,
        "entitlements": principal.entitlements,
    }
