"""In-memory Sink — used in all tests. Thread-safe for asyncio single-thread use."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence

from pydantic import BaseModel

from argus.sinks.base import Sink


class MemorySink:
    """Dict-backed sink; idempotent on the model's natural key fields."""

    def __init__(self, idempotency_fields: dict[str, list[str]] | None = None) -> None:
        # table → list of row dicts
        self._store: dict[str, list[dict]] = defaultdict(list)
        # table → set of tuple(key values) already written
        self._seen: dict[str, set[tuple]] = defaultdict(set)
        # override per-table idempotency key fields; falls back to all fields
        self._idem: dict[str, list[str]] = idempotency_fields or {}

    def ensure_schema(self, table: str, model: type[BaseModel]) -> None:
        # No-op for in-memory; schema is implicit
        pass

    def write(self, table: str, rows: Sequence[BaseModel]) -> int:
        inserted = 0
        key_fields = self._idem.get(table)
        for row in rows:
            d = row.model_dump(mode="json")
            key = (
                tuple(d.get(f) for f in key_fields)
                if key_fields
                else json.dumps(d, sort_keys=True, default=str)
            )
            if key not in self._seen[table]:
                self._seen[table].add(key)
                self._store[table].append(d)
                inserted += 1
        return inserted

    def read(self, table: str) -> list[dict]:
        """Test helper — return all rows for a table."""
        return list(self._store[table])

    def count(self, table: str) -> int:
        return len(self._store[table])

    def clear(self) -> None:
        self._store.clear()
        self._seen.clear()


# Module-level type alias so tests can isinstance-check
assert isinstance(MemorySink(), Sink)
