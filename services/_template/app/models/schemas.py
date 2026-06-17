"""The shapes this service accepts and returns (its public data contract)."""

from __future__ import annotations

from pydantic import BaseModel


class EchoIn(BaseModel):
    message: str


class Echo(BaseModel):
    message: str
    length: int
