"""Security helpers, role capabilities, and the admin seed."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os

from .models import User

log = logging.getLogger(__name__)

# Role → capability flags (mirrors the platform's role model).
ROLE_CAPS = {
    "admin":    {"can_lock": True,  "can_order": True},
    "reviewer": {"can_lock": True,  "can_order": False},
    "lab_tech": {"can_lock": False, "can_order": True},
    "designer": {"can_lock": False, "can_order": False},
    "observer": {"can_lock": False, "can_order": False},
}


def caps(role: str) -> dict:
    return ROLE_CAPS.get(role, {"can_lock": False, "can_order": False})


def to_user_out(u: User) -> dict:
    c = caps(u.role)
    return {
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name,
        "email": u.email,
        "role": u.role,
        "tenant_id": u.tenant_id,
        "is_active": u.is_active,
        "can_lock": c["can_lock"],
        "can_order": c["can_order"],
    }


# ── password hashing (stdlib pbkdf2 — no extra deps) ────────────────────────

def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + "$" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    # Django format (migrated users): pbkdf2_sha256$<iters>$<salt>$<b64-hash>
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _algo, iters, salt, h = stored.split("$", 3)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(),
                                     int(iters))
            return hmac.compare_digest(base64.b64encode(dk).decode().strip(), h)
        except Exception:
            return False
    # native format: <salt_hex>$<dk_hex>
    try:
        salt_hex, dk_hex = stored.split("$")
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
    return hmac.compare_digest(dk.hex(), dk_hex)


def seed_admin(session_factory, settings) -> None:
    db = session_factory()
    try:
        if not db.query(User).filter_by(username=settings.admin_username).first():
            db.add(User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role="admin",
                display_name="Administrator",
                tenant_id=settings.admin_tenant,
                is_active=True,
            ))
            db.commit()
            log.info("seeded admin '%s' (tenant=%s)",
                     settings.admin_username, settings.admin_tenant)
    finally:
        db.close()
