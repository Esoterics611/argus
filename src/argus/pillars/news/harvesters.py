"""
News pillar harvesters.

NewsRssHarvester handles any Tier-0 source with an rss_feeds[] Source Card entry.
The pillar code never hardcodes a URL — all endpoints live in Source Cards.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import structlog

from argus.core.contracts import NewsItem
from argus.core.harvester import Harvester, Tier0Mixin
from argus.core.source_card import SourceCard
from argus.pillars.news.normalize import normalize_feed
from argus.sinks.base import Sink

log = structlog.get_logger()


class NewsRssHarvester(Harvester, Tier0Mixin):
    """
    Tier-0 RSS/Atom harvester for any news Source Card with rss_feeds[].
    Fetches all configured feeds and normalizes entries to NewsItem.
    """

    table = "news"

    def __init__(self, card: SourceCard, sink: Sink) -> None:
        super().__init__(card, sink)
        if not card.rss_feeds:
            raise ValueError(f"Source card {card.id!r} has no rss_feeds configured")

    async def extract(self) -> list[Any]:
        """Fetch all RSS feeds for this source. Returns list of feedparser results."""
        results = []
        for feed_cfg in self.card.rss_feeds:
            self._log.info("rss.fetch", url=feed_cfg.url)
            try:
                parsed = await self.fetch_feed(feed_cfg.url)
                results.append(parsed)
            except Exception as exc:
                self._log.warning("rss.fetch_failed", url=feed_cfg.url, error=str(exc))
        return results

    def normalize(self, raw: list[Any]) -> Sequence[NewsItem]:
        fetched_ts = datetime.now(UTC)
        items: list[NewsItem] = []
        for parsed_feed in raw:
            items.extend(normalize_feed(parsed_feed, self.card.id, fetched_ts))
        return items


def build_harvester(card: SourceCard, sink: Sink) -> Harvester:
    """Factory: return the right harvester for a news Source Card."""
    if card.tier == 0 and card.rss_feeds:
        return NewsRssHarvester(card, sink)
    raise NotImplementedError(
        f"No harvester implemented for news source {card.id!r} at tier {card.tier}. "
        "Run argus cartograph first to discover endpoints."
    )
