"""QuestDB Sink — writes via ILP (InfluxDB Line Protocol) over TCP on port 9009."""

from __future__ import annotations

import json
import socket
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from argus.sinks.base import Sink

_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 9009


def _to_ilp_value(v: object) -> str:
    """Render a Python value as an ILP field value string."""
    if isinstance(v, bool):
        return "t" if v else "f"
    if isinstance(v, int):
        return f"{v}i"
    if isinstance(v, float):
        return str(v)
    if isinstance(v, Decimal):
        return str(float(v))
    if isinstance(v, datetime):
        return str(int(v.timestamp() * 1e9))  # nanoseconds
    return f'"{v}"'


class QuestDBSink:
    """
    Sends rows to QuestDB over ILP TCP.
    Idempotency relies on QuestDB's dedup feature (requires DEDUP ON the table).
    """

    def __init__(self, host: str = _DEFAULT_HOST, port: int = _DEFAULT_PORT) -> None:
        self.host = host
        self.port = port

    def ensure_schema(self, table: str, model: type[BaseModel]) -> None:
        # QuestDB creates tables on first write; schema inferred from ILP
        pass

    def write(self, table: str, rows: Sequence[BaseModel]) -> int:
        if not rows:
            return 0
        lines: list[str] = []
        for row in rows:
            data = json.loads(row.model_dump_json())
            ts_ns: int | None = None
            fields: list[str] = []
            tags: list[str] = []

            for k, v in data.items():
                if v is None:
                    continue
                if k in ("source_id",):
                    tags.append(f"{k}={v}")
                elif k in ("ts", "fetched_ts", "scheduled_ts"):
                    if isinstance(v, str):
                        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                        ts_ns = int(dt.timestamp() * 1e9)
                    fields.append(f"{k}={_to_ilp_value(v)}")
                else:
                    fields.append(f"{k}={_to_ilp_value(v)}")

            tag_str = "," + ",".join(tags) if tags else ""
            field_str = ",".join(fields) if fields else "placeholder=1i"
            ts_str = f" {ts_ns}" if ts_ns is not None else ""
            lines.append(f"{table}{tag_str} {field_str}{ts_str}")

        payload = "\n".join(lines) + "\n"
        with socket.create_connection((self.host, self.port), timeout=5) as sock:
            sock.sendall(payload.encode())
        return len(rows)


assert isinstance(QuestDBSink(), Sink)
