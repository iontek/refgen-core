"""Panel state machine + the snapshot that gets hashed at lock time."""

from __future__ import annotations

from fastapi import HTTPException

VALID_TYPES = {"DNA", "RNA", "MIXED"}

# action -> (required from-state, to-state)
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


def panel_snapshot(panel, genes) -> dict:
    """Canonical content of a panel — what the content_hash is computed over.
    Genes sorted so the hash is order-independent (reproducibility)."""
    return {
        "label": panel.label,
        "type": panel.type,
        "details": panel.details or "",
        "genes": sorted(
            ({"symbol": g.symbol, "target": g.target} for g in genes),
            key=lambda x: x["symbol"],
        ),
    }
