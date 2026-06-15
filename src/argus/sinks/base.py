"""Sink swap-seam interface."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class Sink(Protocol):
    """Storage swap-seam. All implementations are idempotent."""

    def ensure_schema(self, table: str, model: type[BaseModel]) -> None:
        """Create or migrate the table to match the model's fields."""
        ...

    def write(self, table: str, rows: Sequence[BaseModel]) -> int:
        """Write rows idempotently. Returns the number of rows actually inserted."""
        ...
