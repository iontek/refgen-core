"""Idempotent seed of the built-in recipes (ported from core/recipes/*.yaml).
Embedded as dicts so no YAML dependency is needed. content_hash is taken over
{name, version, spec} so distinct named methods never collide on the unique
hash even when their knobs are identical (e.g. default vs hcs-dna)."""

from __future__ import annotations

from svc_base.versioning import content_hash

from .models import Recipe

_MANE_TARGET = {
    "cds_only": True, "transcript_mode": "mane_select",
    "padding_bp": 20, "merge_distance": 0,
}

BUILTIN = [
    {
        "name": "default", "version": "1.1.0",
        "description": "DNA · MANE Select · balanced bait design (FixedOffset, 120/80).",
        "spec": {"molecule": "DNA", "target": _MANE_TARGET,
                 "design": {"bait_size": 120, "bait_offset": 80, "min_baits": 2,
                            "design_strategy": "FixedOffset", "repeat_tolerance": 50,
                            "pool_size": 55000, "preset": "balanced"}},
    },
    {
        "name": "cgp-bait", "version": "1.0.0",
        "description": "Phase 1 · CGP DNA bait — HGNC validate → MANE Select → +20 pad → merge/sort → baits.",
        "spec": {"molecule": "DNA",
                 "target": {**_MANE_TARGET, "sort_order": "lexicographic"},
                 "design": {"bait_size": 120, "bait_offset": 60, "min_baits": 3,
                            "design_strategy": "FixedOffset", "repeat_tolerance": 40,
                            "pool_size": 55000, "preset": "stringent"}},
    },
    {
        "name": "cgp-stringent", "version": "1.1.0",
        "description": "DNA · MANE Select · CGP somatic — tighter off-target, denser tiling.",
        "spec": {"molecule": "DNA",
                 "target": {**_MANE_TARGET, "padding_bp": 25},
                 "design": {"bait_size": 120, "bait_offset": 60, "min_baits": 3,
                            "design_strategy": "FixedOffset", "repeat_tolerance": 40,
                            "pool_size": 55000, "preset": "stringent"}},
    },
    {
        "name": "hcs-dna", "version": "1.1.0",
        "description": "DNA · MANE Select · HCS hereditary cancer (germline) — balanced baits.",
        "spec": {"molecule": "DNA", "target": _MANE_TARGET,
                 "design": {"bait_size": 120, "bait_offset": 80, "min_baits": 2,
                            "design_strategy": "FixedOffset", "repeat_tolerance": 50,
                            "pool_size": 55000, "preset": "balanced"}},
    },
]


def recipe_hash(name: str, version: str, spec: dict) -> str:
    return content_hash({"name": name, "version": version, "spec": spec})


def seed_recipes(session_factory) -> int:
    db = session_factory()
    try:
        n = 0
        for r in BUILTIN:
            if db.query(Recipe).filter_by(name=r["name"], version=r["version"]).first():
                continue
            db.add(Recipe(
                name=r["name"], version=r["version"], description=r["description"],
                spec=r["spec"], content_hash=recipe_hash(r["name"], r["version"], r["spec"]),
                status="published", created_by="system",
            ))
            n += 1
        db.commit()
        return n
    finally:
        db.close()
