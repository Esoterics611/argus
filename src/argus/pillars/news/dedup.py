"""
Headline deduplication across news sources.

Same story from N outlets → one NewsItem with corroborations[] listing the others.
Uses rapidfuzz token_set_ratio on normalized headlines within a rolling time window.
"""

from __future__ import annotations

import re
from datetime import timedelta

from rapidfuzz import fuzz  # type: ignore[import-untyped]

from argus.core.contracts import NewsItem

_DEFAULT_THRESHOLD = 85  # rapidfuzz score 0–100
_DEFAULT_WINDOW = timedelta(minutes=30)


def _normalize_headline(headline: str) -> str:
    """Lowercase + collapse whitespace + strip punctuation for comparison."""
    h = headline.lower()
    h = re.sub(r"[^\w\s]", " ", h)
    return re.sub(r"\s+", " ", h).strip()


def deduplicate(
    items: list[NewsItem],
    threshold: int = _DEFAULT_THRESHOLD,
    window: timedelta = _DEFAULT_WINDOW,
) -> list[NewsItem]:
    """
    Merge duplicate stories. Returns a deduplicated list where the
    first-fetched item wins and corroborations[] accumulates later matches.

    Items with no published_ts are placed at the end of their bucket
    (sorted by fetched_ts) and compared against all items in the window.
    """
    if not items:
        return []

    # Sort by published_ts (nulls last), then fetched_ts for stable ordering
    def sort_key(it: NewsItem):
        ts = it.published_ts or it.fetched_ts
        return (ts, it.fetched_ts)

    sorted_items = sorted(items, key=sort_key)

    # Each slot: (winner NewsItem, normalized headline)
    buckets: list[tuple[NewsItem, str]] = []

    for item in sorted_items:
        item_ts = item.published_ts or item.fetched_ts
        item_norm = _normalize_headline(item.headline)
        matched = False

        for winner, winner_norm in buckets:
            winner_ts = winner.published_ts or winner.fetched_ts
            # Skip comparison if outside time window
            if abs(item_ts - winner_ts) > window:
                continue
            score = fuzz.token_set_ratio(item_norm, winner_norm)
            if score >= threshold:
                # Fold into winner's corroborations (avoid double-adding)
                if item.source_id not in winner.corroborations:
                    winner.corroborations.append(item.source_id)
                matched = True
                break

        if not matched:
            buckets.append((item, item_norm))

    return [winner for winner, _ in buckets]
