from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func

from svc_base.db import Base
from svc_base.tenancy import TenantScopedMixin


class User(TenantScopedMixin, Base):
    """A user belongs to one tenant (TenantScopedMixin adds tenant_id)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="designer")
    display_name = Column(String(255))
    email = Column(String(255))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
