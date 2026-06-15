"""Tests for the Sink swap-seam — MemorySink round-trips and idempotency."""

from datetime import UTC, datetime

from argus.core.contracts import FundingPoint, NewsItem
from argus.sinks.memory import MemorySink

UTC = UTC
NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)


def make_news(dedup_hash: str = "abc123", source_id: str = "fed_press") -> NewsItem:
    return NewsItem(
        source_id=source_id,
        url="https://www.federalreserve.gov/news/1",
        headline="Fed holds rates steady",
        fetched_ts=NOW,
        dedup_hash=dedup_hash,
    )


def make_funding(exchange: str = "Binance", ts: datetime = NOW) -> FundingPoint:
    from decimal import Decimal

    return FundingPoint(
        source_id="coinglass_funding",
        exchange=exchange,
        symbol="BTCUSDT",
        funding_rate=Decimal("0.0001"),
        next_funding_ts=NOW,
        ts=ts,
        fetched_ts=NOW,
    )


# ── MemorySink basic round-trip ───────────────────────────────────────────────


def test_memory_sink_write_and_read():
    sink = MemorySink(idempotency_fields={"news": ["source_id", "dedup_hash"]})
    item = make_news()
    n = sink.write("news", [item])
    assert n == 1
    assert sink.count("news") == 1
    rows = sink.read("news")
    assert rows[0]["headline"] == "Fed holds rates steady"


def test_memory_sink_idempotency():
    sink = MemorySink(idempotency_fields={"news": ["source_id", "dedup_hash"]})
    item = make_news()
    sink.write("news", [item])
    n2 = sink.write("news", [item])  # same dedup_hash
    assert n2 == 0
    assert sink.count("news") == 1


def test_memory_sink_different_dedup_hashes():
    sink = MemorySink(idempotency_fields={"news": ["source_id", "dedup_hash"]})
    sink.write("news", [make_news("hash_a")])
    n = sink.write("news", [make_news("hash_b")])
    assert n == 1
    assert sink.count("news") == 2


def test_memory_sink_multi_table():
    sink = MemorySink()
    sink.write("news", [make_news()])
    sink.write("funding", [make_funding()])
    assert sink.count("news") == 1
    assert sink.count("funding") == 1


def test_memory_sink_clear():
    sink = MemorySink()
    sink.write("news", [make_news()])
    sink.clear()
    assert sink.count("news") == 0


# ── ensure_schema is a no-op for MemorySink ──────────────────────────────────


def test_memory_sink_ensure_schema_noop():
    sink = MemorySink()
    sink.ensure_schema("news", NewsItem)  # must not raise


# ── Multiple rows in one write ────────────────────────────────────────────────


def test_memory_sink_batch_write():
    sink = MemorySink(idempotency_fields={"news": ["source_id", "dedup_hash"]})
    rows = [make_news(f"h{i}") for i in range(5)]
    n = sink.write("news", rows)
    assert n == 5
    assert sink.count("news") == 5
