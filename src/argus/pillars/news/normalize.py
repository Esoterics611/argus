"""
Normalize raw feedparser entries to NewsItem contracts.

Handles UTC parsing, latency, dedup_hash, revision detection, and
timestamp clamping per sources/news/EDGE_CASES.md.
"""

from __future__ import annotations

import calendar
import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from argus.core.contracts import NewsItem

log = structlog.get_logger()

# Timestamps more than this far in the future are clamped to fetched_ts.
_MAX_FUTURE_SKEW = timedelta(hours=1)
# Items older than this are skipped as stale feed cache.
_MAX_AGE = timedelta(days=30)
# Revision detected when updated_parsed differs from published_parsed by more than this.
_REVISION_MIN_DELTA = timedelta(seconds=60)


def _get(entry: Any, key: str) -> Any:
    """Fetch a field from a feedparser entry (dict-like or attribute-based)."""
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


def _parse_ts(time_struct: Any) -> datetime | None:
    """Convert a feedparser time_struct (UTC 9-tuple) to an aware UTC datetime."""
    if time_struct is None:
        return None
    try:
        epoch = calendar.timegm(time_struct)
        return datetime.fromtimestamp(epoch, tz=UTC)
    except (TypeError, OverflowError, OSError):
        return None


def _clamp_ts(published_ts: datetime | None, fetched_ts: datetime) -> datetime | None:
    """Clamp far-future timestamps; return None for very stale ones."""
    if published_ts is None:
        return None
    if published_ts > fetched_ts + _MAX_FUTURE_SKEW:
        log.debug("normalize.ts_clamped_future", original=published_ts.isoformat())
        return fetched_ts
    if fetched_ts - published_ts > _MAX_AGE:
        return None  # caller will skip this item
    return published_ts


def _compute_hash(headline: str, published_ts: datetime | None) -> str:
    ts_str = published_ts.isoformat() if published_ts else ""
    normalized = re.sub(r"\s+", " ", headline.lower().strip())
    return hashlib.sha256(f"{normalized}|{ts_str}".encode()).hexdigest()[:16]


def _body_snippet(entry: Any) -> str | None:
    """Extract a short body preview from the feed entry."""
    summary = _get(entry, "summary")
    if summary:
        clean = re.sub(r"<[^>]+>", "", str(summary)).strip()
        return clean[:500] if clean else None
    return None


def _entry_lang(feed: Any) -> str:
    """Best-effort language from feed channel."""
    lang = _get(feed, "language") or "en"
    return str(lang)[:2].lower()


def normalize_entry(
    entry: Any,
    source_id: str,
    feed: Any,
    fetched_ts: datetime,
) -> NewsItem | None:
    """
    Convert one feedparser entry to a NewsItem.
    Returns None if the entry is too stale or otherwise invalid.
    """
    headline = (_get(entry, "title") or "").strip()
    if not headline:
        return None

    url = (_get(entry, "link") or "").strip()
    raw_published_ts = _parse_ts(_get(entry, "published_parsed"))
    updated_ts = _parse_ts(_get(entry, "updated_parsed"))

    published_ts = _clamp_ts(raw_published_ts, fetched_ts)
    if published_ts is None and raw_published_ts is not None:
        # Had a timestamp but _clamp_ts discarded it → stale or clamped-to-None; skip
        log.debug("normalize.stale_skipped", source_id=source_id, headline=headline[:60])
        return None

    latency_ms: int | None = None
    if published_ts is not None:
        delta = fetched_ts - published_ts
        latency_ms = max(0, int(delta.total_seconds() * 1000))

    dedup_hash = _compute_hash(headline, published_ts)

    # Revision detection: updated differs from published by more than threshold
    revision_of: str | None = None
    if (
        updated_ts is not None
        and published_ts is not None
        and abs(updated_ts - published_ts) > _REVISION_MIN_DELTA
    ):
        # Hash the original (published_ts) version
        revision_of = _compute_hash(headline, published_ts)

    return NewsItem(
        source_id=source_id,
        url=url,
        headline=headline,
        body_snippet=_body_snippet(entry),
        published_ts=published_ts,
        fetched_ts=fetched_ts,
        latency_ms=latency_ms,
        assets=[],  # filled by tagger
        category=None,
        importance=1,  # filled by scorer
        lang=_entry_lang(feed),
        dedup_hash=dedup_hash,
        corroborations=[],
        revision_of=revision_of,
    )


def normalize_feed(
    parsed_feed: Any,
    source_id: str,
    fetched_ts: datetime | None = None,
) -> list[NewsItem]:
    """Normalize all entries in a parsed feedparser result."""
    if fetched_ts is None:
        fetched_ts = datetime.now(UTC)

    items: list[NewsItem] = []
    feed = parsed_feed.get("feed", {})
    for entry in parsed_feed.get("entries", []):
        item = normalize_entry(entry, source_id, feed, fetched_ts)
        if item is not None:
            items.append(item)
    return items
