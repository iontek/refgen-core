from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access: str
    refresh: str


class RefreshIn(BaseModel):
    refresh: str


class AccessOut(BaseModel):
    access: str


class UserIn(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "designer"
    display_name: Optional[str] = None
    tenant_id: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    role: str
    tenant_id: str
    is_active: bool
    can_lock: bool
    can_order: bool
