"""Multi-tenancy foundation.

Every tenant-scoped entity carries a `tenant_id`; the tenant tree
(`parent_tenant_id`) supports hierarchical scoping (an operator sees its whole
subtree). The Tenant entity itself is owned by the central management service —
this module gives EVERY service the mixin + the pure scoping helpers so the
behaviour is identical everywhere.

See docs/mimari-vizyon.md §5 (Çok Kiracılılık).
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import Column, String
from sqlalchemy.orm import declared_attr


class TenantScopedMixin:
    """Mixin that stamps a model's rows with the owning tenant.

        class Panel(TenantScopedMixin, Base):
            __tablename__ = "panels"
            ...
    """

    @declared_attr
    def tenant_id(cls):  # noqa: N805
        return Column(String(64), nullable=False, index=True)


def tenant_subtree(root_id: str, parent_of: dict) -> set:
    """All tenant ids in the subtree rooted at `root_id` (inclusive), given a
    ``{child_id: parent_id}`` map. Used for hierarchical authz and billing
    roll-up — e.g. TÜSEB sees TÜSEB + its sub-distributors + their hospitals.
    """
    children: dict = {}
    for child, parent in parent_of.items():
        children.setdefault(parent, []).append(child)

    out: set = set()
    stack = [root_id]
    while stack:
        t = stack.pop()
        if t in out:
            continue
        out.add(t)
        stack.extend(children.get(t, []))
    return out


def scope_query(query, model, tenant_ids: Iterable[str]):
    """Restrict a SQLAlchemy query to rows owned by the given tenant(s).
    Pass a single id's subtree for hierarchical reads."""
    ids = list(tenant_ids)
    return query.filter(model.tenant_id.in_(ids))
