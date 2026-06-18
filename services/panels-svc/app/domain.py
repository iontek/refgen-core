"""Panel state machine + the snapshot that gets hashed at lock time."""

from __future__ import annotations

from fastapi import HTTPException

from svc_base.versioning import reference_versions

VALID_TYPES = {"DNA", "RNA", "MIXED"}

# action -> (required from-state, to-state)
# unlock is retained but the API gates it on the version being un-consumed
# (a mistaken lock can be undone; a used version can only be forked).
_TRANSITIONS = {
    "validate":  ("draft", "validated"),
    "reject":    ("validated", "draft"),
    "lock":      ("validated", "locked"),
    "deprecate": ("locked", "archived"),
    "unlock":    ("locked", "draft"),
}


def transition(panel, action: str) -> None:
    rule = _TRANSITIONS.get(action)
    if not rule:
        raise HTTPException(status_code=400, detail=f"unknown action: {action}")
    frm, to = rule
    if panel.status != frm:
        raise HTTPException(
            status_code=409, detail=f"cannot {action} from '{panel.status}'"
        )
    panel.status = to


def _ms(dt):
    return int(dt.timestamp() * 1000) if dt else None


def panel_snapshot(panel, genes, regions=()) -> dict:
    """Canonical content of a panel — what the content_hash is computed over.

    Pins EVERYTHING that affects the design: identity, composition, designer-
    curated regions, AND the reference-data versions in force. Lists are sorted
    so the hash is order-independent (reproducibility). Including the panel
    identity keeps two distinct panels with identical genes from colliding under
    the unique content_hash. Mirrors platform `state.panel_snapshot`."""
    genes_snap = sorted(
        (
            {
                "symbol": g.symbol,
                "hgnc_id": g.hgnc_id,
                "target": g.target,
                "transcript_override": g.transcript_override,
                "added_by": g.added_by,
            }
            for g in genes
        ),
        key=lambda x: (x["symbol"] or ""),
    )
    regions_snap = sorted(
        (
            {
                "chr": r.chr,
                "start": r.start,
                "end": r.end,
                "name": r.name,
                "kind": r.kind,
                "hgvs": r.hgvs,
            }
            for r in regions
        ),
        key=lambda x: (x["chr"] or "", x["start"] or 0, x["name"] or ""),
    )
    return {
        "panel_id": panel.code,
        "label": panel.label,
        "type": panel.type,
        "details": panel.details or "",
        "deadline": _ms(panel.deadline),
        "created_by": panel.created_by,
        "created_at": _ms(panel.created_at),
        "n_genes": len(genes_snap),
        "genes": genes_snap,
        "custom_regions": regions_snap,
        "reference_versions": reference_versions(),
        "_v": 2,
    }
