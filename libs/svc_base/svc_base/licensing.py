"""Licensing / entitlements foundation.

A tenant is licensed for a SELECTED SCOPE of services/modules (entitlements);
billing then charges for actual usage within that scope. Entitlements are
defined centrally and ride in the token; every service enforces locally.

See docs/mimari-vizyon.md §6 (Lisanslama ve Faturalama).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from .auth import Principal, require_auth


def has_entitlement(principal: Principal, feature: str) -> bool:
    return feature in (principal.entitlements or [])


def require_entitlement(feature: str):
    """Dependency: 403 unless the caller's TENANT is licensed for `feature`
    (e.g. the 'analysis' or 'design' module)."""

    def checker(principal: Principal = Depends(require_auth)) -> Principal:
        if feature not in (principal.entitlements or []):
            raise HTTPException(
                status_code=403, detail=f"not licensed for: {feature}"
            )
        return principal

    return checker
