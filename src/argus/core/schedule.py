"""Async worker pool — runs N sources concurrently at per-source cadence."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from urllib.robotparser import RobotFileParser

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from argus.core.source_card import SourceCard

log = structlog.get_logger()

# Per-domain semaphores for rate limiting
_domain_locks: dict[str, asyncio.Semaphore] = {}
_DOMAIN_CONCURRENCY = 2  # max concurrent requests per domain


def _parse_cadence(cadence: str) -> float:
    """Convert cadence string like '60s', '5m', '1h' to seconds."""
    match = re.fullmatch(r"(\d+)(s|m|h)", cadence.strip())
    if not match:
        return 300.0  # default 5 min
    val, unit = int(match.group(1)), match.group(2)
    return val * {"s": 1, "m": 60, "h": 3600}[unit]


def _domain_of(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).netloc


async def _check_robots(url: str) -> bool:
    """Return True if the URL is allowed by robots.txt."""
    from urllib.parse import urljoin, urlparse

    parsed = urlparse(url)
    robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(robots_url)
        rp = RobotFileParser()
        rp.parse(resp.text.splitlines())
        return rp.can_fetch("Argus", url)
    except Exception:
        return True  # assume allowed on network error


class Scheduler:
    """
    Runs harvest callables for a list of SourceCards on their declared cadences.
    Enforces per-domain concurrency and robots.txt.
    """

    def __init__(self, concurrency: int = 8) -> None:
        self._concurrency = concurrency
        self._sem = asyncio.Semaphore(concurrency)
        self._running = False

    async def run_once(
        self,
        cards: list[SourceCard],
        harvest_fn: Callable[[SourceCard], Awaitable[int]],
    ) -> dict[str, int]:
        """Run harvest_fn for each card once. Returns {source_id: rows_written}."""
        results: dict[str, int] = {}

        async def _one(card: SourceCard) -> None:
            if card.robots_ok is False:
                log.warning("robots.blocked", source=card.id)
                results[card.id] = 0
                return
            if card.robots_ok is None:
                allowed = await _check_robots(card.url)
                if not allowed:
                    log.warning("robots.disallowed", source=card.id, url=card.url)
                    results[card.id] = 0
                    return

            domain = _domain_of(card.url)
            if domain not in _domain_locks:
                _domain_locks[domain] = asyncio.Semaphore(_DOMAIN_CONCURRENCY)

            async with self._sem, _domain_locks[domain]:
                try:
                    n = await _harvest_with_backoff(card, harvest_fn)
                    results[card.id] = n
                except Exception as exc:
                    log.error("harvest.failed", source=card.id, error=str(exc))
                    results[card.id] = -1

        await asyncio.gather(*[_one(c) for c in cards])
        return results

    async def run_continuous(
        self,
        cards: list[SourceCard],
        harvest_fn: Callable[[SourceCard], Awaitable[int]],
    ) -> None:
        """Run harvest_fn for each card continuously at their declared cadence."""
        self._running = True

        async def _loop(card: SourceCard) -> None:
            cadence_s = _parse_cadence(card.cadence)
            while self._running:
                start = asyncio.get_event_loop().time()
                try:
                    await _harvest_with_backoff(card, harvest_fn)
                except Exception as exc:
                    log.error("harvest.error", source=card.id, error=str(exc))
                elapsed = asyncio.get_event_loop().time() - start
                await asyncio.sleep(max(0, cadence_s - elapsed))

        await asyncio.gather(*[_loop(c) for c in cards])

    def stop(self) -> None:
        self._running = False


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, ConnectionError)),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def _harvest_with_backoff(
    card: SourceCard,
    harvest_fn: Callable[[SourceCard], Awaitable[int]],
) -> int:
    return await harvest_fn(card)
