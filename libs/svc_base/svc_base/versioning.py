"""Versioning / immutability foundation.

Reusable across any versioned aggregate (panels, recipes, …): a deterministic
content hash, semver bumping, an immutability guard, the clinical reference-data
pin, and the data-validity preconditions for a lock. The aggregate stays inside
ONE service so lock/snapshot is a single transaction.

Mirrors the platform's `apps/panels/state.py` so dxm has the SAME versioning
semantics. See docs/mimari-vizyon.md §5/§13 + dx-yapisi-ve-goc.md.
"""

from __future__ import annotations

import hashlib
import json
import os

from fastapi import HTTPException


# ── content hash ──────────────────────────────────────────────────────────────

def content_hash(data) -> str:
    """Deterministic sha256 over canonical JSON — key order doesn't matter, so
    the same logical content always hashes the same (basis for reproducibility).

    Prefixed `sha256:` to match the platform format, so the cross-service
    reference `{panel_id, version, content_hash}` is byte-for-byte comparable."""
    canon = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ── semver ──────────────────────────────────────────────────────────────────

def bump_semver(parent, level: str = "minor") -> str:
    """Next semver. First lock (no/blank parent) = 1.0.0; afterwards bump the
    parent by `level` (major/minor/patch). Matches platform `state.bump_semver`."""
    if not parent or not isinstance(parent, str):
        return "1.0.0"
    parts = parent.split(".")
    if len(parts) != 3:
        return "1.0.0"
    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return "1.0.0"
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return f"{major}.{minor + 1}.0"


# ── immutability ──────────────────────────────────────────────────────────────

IMMUTABLE_STATES = ("locked", "archived")


def assert_mutable(status: str, *, immutable=IMMUTABLE_STATES) -> None:
    """Raise 409 if the object's status makes it immutable (e.g. locked panels
    are never edited — they are forked instead)."""
    if status in immutable:
        raise HTTPException(status_code=409, detail=f"object is {status} (immutable)")


# ── clinical reference-data pin ───────────────────────────────────────────────

# Same defaults as the platform, so a fresh deployment pins the same reference
# data when no registry is configured.
_REF_DEFAULTS = {
    "genome_build": "GRCh38",
    "mane_release": "1.5",
    "_note": "registry missing — defaults",
}


def reference_versions() -> dict:
    """Versions of the reference data a design depends on (genome build, MANE,
    HGNC, ClinVar, gnomAD). Folding this into the snapshot means a reference-data
    update changes the content_hash → a new version in the lineage.

    Source (in order): `REF_VERSIONS_JSON` (inline JSON) > `REF_VERSIONS_PATH`
    (a JSON file) > built-in defaults. Isolated here so that when the central
    management plane lands, only this function changes (edge pulls from centre)."""
    raw = os.environ.get("REF_VERSIONS_JSON")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    path = os.environ.get("REF_VERSIONS_PATH")
    if path:
        try:
            with open(path) as fh:
                return json.load(fh)
        except Exception:
            pass
    return dict(_REF_DEFAULTS)


# ── data-validity preconditions (mirror platform can_validate / can_lock) ─────

def validate_blockers(status: str, gene_count: int) -> list[str]:
    """Reasons a panel cannot be validated (draft + ≥1 gene)."""
    issues = []
    if status != "draft":
        issues.append(f"status is '{status}', expected 'draft'")
    if gene_count < 1:
        issues.append("panel has no genes")
    return issues


def lock_blockers(status: str, gene_count: int) -> list[str]:
    """Reasons a panel cannot be locked (validated + ≥1 gene). Extend with more
    clinical checks later (MANE coverage, off-target, …)."""
    issues = []
    if status != "validated":
        issues.append(f"status is '{status}', expected 'validated'")
    if gene_count < 1:
        issues.append("panel has no genes")
    return issues


def assert_validatable(status: str, gene_count: int) -> None:
    issues = validate_blockers(status, gene_count)
    if issues:
        raise HTTPException(status_code=422, detail="; ".join(issues))


def assert_lockable(status: str, gene_count: int) -> None:
    issues = lock_blockers(status, gene_count)
    if issues:
        raise HTTPException(status_code=422, detail="; ".join(issues))
