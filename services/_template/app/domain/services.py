"""The back room: the actual work this service does. Pure logic, no HTTP —
so it's trivial to unit-test and reuse.
"""

from __future__ import annotations

from ..models.schemas import Echo


def make_echo(message: str) -> Echo:
    return Echo(message=message, length=len(message))
