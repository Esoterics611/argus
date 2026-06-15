"""NATS Sink — publishes each row as JSON to 'argus.<table>.<source_id>'."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence

from pydantic import BaseModel

from argus.sinks.base import Sink

_DEFAULT_URL = "nats://localhost:4222"


class NatsSink:
    """
    Async NATS publisher.  Subject pattern: argus.<table>.<source_id>.
    Call ensure_connected() before use in async contexts; or use as async ctx-manager.
    Idempotency is NOT enforced here — NATS is a bus, consumers deduplicate.
    """

    def __init__(self, url: str = _DEFAULT_URL) -> None:
        self.url = url
        self._nc: object | None = None

    async def connect(self) -> None:
        import nats  # type: ignore[import-untyped]

        self._nc = await nats.connect(self.url)

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.close()  # type: ignore[union-attr]
            self._nc = None

    def ensure_schema(self, table: str, model: type[BaseModel]) -> None:
        pass  # NATS is schema-free

    def write(self, table: str, rows: Sequence[BaseModel]) -> int:
        """Synchronous write — runs async publish in a new event loop or existing one."""
        if not rows:
            return 0
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule as a task; caller must await flush separately
                loop.create_task(self._publish_all(table, rows))
            else:
                loop.run_until_complete(self._publish_all(table, rows))
        except RuntimeError:
            asyncio.run(self._publish_all(table, rows))
        return len(rows)

    async def write_async(self, table: str, rows: Sequence[BaseModel]) -> int:
        """Preferred async path."""
        if not rows:
            return 0
        await self._publish_all(table, rows)
        return len(rows)

    async def _publish_all(self, table: str, rows: Sequence[BaseModel]) -> None:
        if self._nc is None:
            await self.connect()
        for row in rows:
            data = json.loads(row.model_dump_json())
            source_id = data.get("source_id", "unknown")
            subject = f"argus.{table}.{source_id}"
            payload = json.dumps(data).encode()
            await self._nc.publish(subject, payload)  # type: ignore[union-attr]


assert isinstance(NatsSink(), Sink)
