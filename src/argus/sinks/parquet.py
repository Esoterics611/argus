"""Parquet cold-layer Sink — one file per (table, UTC date), written with Polars."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from pydantic import BaseModel

from argus.sinks.base import Sink

_DEFAULT_DIR = Path("data/parquet")


class ParquetSink:
    """
    Writes rows to Parquet partitioned by table and UTC date.
    Idempotent: loads the existing partition, deduplicates on the natural key,
    then overwrites.
    """

    def __init__(
        self,
        base_dir: Path | str = _DEFAULT_DIR,
        idempotency_fields: dict[str, list[str]] | None = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self._idem: dict[str, list[str]] = idempotency_fields or {}

    def ensure_schema(self, table: str, model: type[BaseModel]) -> None:
        self.base_dir.joinpath(table).mkdir(parents=True, exist_ok=True)

    def write(self, table: str, rows: Sequence[BaseModel]) -> int:
        if not rows:
            return 0

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        partition_dir = self.base_dir / table
        partition_dir.mkdir(parents=True, exist_ok=True)
        path = partition_dir / f"{today}.parquet"

        new_df = pl.DataFrame([json.loads(r.model_dump_json()) for r in rows])

        if path.exists():
            existing = pl.read_parquet(path)
            combined = pl.concat([existing, new_df])
        else:
            combined = new_df

        key_fields = self._idem.get(table)
        if key_fields and all(f in combined.columns for f in key_fields):
            before = len(combined)
            combined = combined.unique(subset=key_fields, keep="last")
            inserted = len(combined) - (before - len(new_df))
        else:
            inserted = len(new_df)

        combined.write_parquet(path)
        return max(inserted, 0)


assert isinstance(ParquetSink(), Sink)
