"""Versioning / immutability foundation.

Reusable across any versioned aggregate (panels, recipes, …): a deterministic
content hash, semver bumping, and an immutability guard. The aggregate stays
inside ONE service so lock/snapshot is a single transaction.

See docs/mimari-vizyon.md §5 + dx-yapisi-ve-goc.md (state machine, content_hash).
"""

from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException


def content_hash(data) -> str:
    """Deterministic sha256 over canonical JSON — key order doesn't matter, so
    the same logical content always hashes the same (basis for reproducibility)."""
    canon = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def bump_semver(version: str, level: str = "minor") -> str:
    major, minor, patch = (list(map(int, version.split("."))) + [0, 0, 0])[:3]
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return f"{major}.{minor + 1}.0"


IMMUTABLE_STATES = ("locked", "archived")


def assert_mutable(status: str, *, immutable=IMMUTABLE_STATES) -> None:
    """Raise 409 if the object's status makes it immutable (e.g. locked panels
    are never edited — they are forked instead)."""
    if status in immutable:
        raise HTTPException(status_code=409, detail=f"object is {status} (immutable)")
