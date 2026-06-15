"""Sink swap-seam — storage backends behind one interface."""

from argus.sinks.base import Sink
from argus.sinks.memory import MemorySink
from argus.sinks.nats import NatsSink
from argus.sinks.parquet import ParquetSink
from argus.sinks.questdb import QuestDBSink

__all__ = ["Sink", "MemorySink", "ParquetSink", "QuestDBSink", "NatsSink", "get_sink"]

import os


def get_sink(name: str | None = None, **kwargs) -> Sink:
    """Return a Sink instance from env var ARGUS_SINK or explicit *name*."""
    backend = (name or os.getenv("ARGUS_SINK", "memory")).lower()
    match backend:
        case "memory":
            return MemorySink(**kwargs)
        case "parquet":
            return ParquetSink(**kwargs)
        case "questdb":
            return QuestDBSink(**kwargs)
        case "nats":
            return NatsSink(**kwargs)
        case _:
            raise ValueError(f"Unknown sink: {backend!r}")
