"""Harvester ABC — lifecycle: profile → extract → normalize → sink."""

from __future__ import annotations

import abc
from collections.abc import Sequence
from typing import Any

import structlog
from pydantic import BaseModel

from argus.core.source_card import SourceCard
from argus.sinks.base import Sink

log = structlog.get_logger()


class Harvester(abc.ABC):
    """
    Abstract base for all pillar harvesters.
    Subclasses implement extract() and normalize(); the run() loop is provided.
    """

    #: Declare which table this harvester writes to
    table: str = ""

    def __init__(self, card: SourceCard, sink: Sink) -> None:
        self.card = card
        self.sink = sink
        self._log = log.bind(source_id=card.id, tier=card.tier)

    @abc.abstractmethod
    async def extract(self) -> Any:
        """Fetch raw data from the source. Returns source-specific raw payload."""
        ...

    @abc.abstractmethod
    def normalize(self, raw: Any) -> Sequence[BaseModel]:
        """Transform raw payload into a list of Pydantic contract records."""
        ...

    async def run(self) -> int:
        """Full lifecycle. Returns the number of rows written."""
        if self.card.status == "BLOCKED":
            self._log.warning("source is BLOCKED — skipping")
            return 0

        self._log.info("harvest.start")
        raw = await self.extract()
        rows = self.normalize(raw)
        if not rows:
            self._log.info("harvest.empty")
            return 0

        if self.table:
            self.sink.ensure_schema(self.table, type(rows[0]))
            n = self.sink.write(self.table, rows)
        else:
            n = 0

        self._log.info("harvest.done", rows_written=n)
        return n


# ── Tier mixins ───────────────────────────────────────────────────────────────
# Pillar harvesters compose the right mixin to get the extraction plumbing
# without re-implementing browser/HTTP boilerplate.


class Tier0Mixin:
    """RSS/Atom/JSON-feed harvester helpers. No browser."""

    async def fetch_feed(self, url: str) -> Any:
        import feedparser  # type: ignore[import-untyped]
        import httpx

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(
                url, headers={"User-Agent": "Argus/0.1 (+https://github.com/Esoterics611/argus)"}
            )
            resp.raise_for_status()
        return feedparser.parse(resp.text)

    async def fetch_json(self, url: str, **kwargs) -> Any:
        import httpx

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, **kwargs)
            resp.raise_for_status()
            return resp.json()


class Tier1Mixin:
    """Endpoint-replay harvester helpers. Uses curl_cffi for JA3-matched requests."""

    async def replay_endpoint(
        self,
        url: str,
        method: str = "GET",
        headers: dict | None = None,
        params: dict | None = None,
        cookies: dict | None = None,
    ) -> Any:
        from curl_cffi.requests import AsyncSession  # type: ignore[import-untyped]

        async with AsyncSession(impersonate="chrome124") as session:
            resp = await session.request(
                method,
                url,
                headers=headers or {},
                params=params or {},
                cookies=cookies or {},
            )
            resp.raise_for_status()
            return resp.json()


class Tier4Mixin:
    """DOM-scrape helpers — uses BrowserFactory context."""

    @property
    def _browser_factory(self):
        from argus.core.browser import BrowserFactory

        return BrowserFactory(
            stealth_backend=self.card.defenses.evasion_rung,  # type: ignore[attr-defined]
            source_slug=self.card.id,  # type: ignore[attr-defined]
        )
