"""BrowserFactory — async context factory with stealth seam, proxy, HAR, and tracing."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import BrowserContext, async_playwright

from argus.core.stealth import get_backend

_HAR_DIR = Path("traces/har")
_TRACE_DIR = Path("traces/trace")

# Realistic UA per backend (Chromium builds; camoufox uses Firefox UA internally)
_UA = {
    "vanilla": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "stealth": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "patchright": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "camoufox": "",  # camoufox manages its own realistic UA
}


class BrowserFactory:
    """
    Async context-manager factory.  Yields a BrowserContext wired with:
    - chosen stealth backend
    - optional per-context proxy
    - HAR recording  → traces/har/<source>-<ts>.har
    - Playwright tracing → traces/trace/<source>-<ts>.zip
    - locale + timezone pinned to UTC
    """

    def __init__(
        self,
        stealth_backend: str = "vanilla",
        proxy: dict[str, str] | None = None,
        record_har: bool = True,
        record_trace: bool = True,
        source_slug: str = "unknown",
    ) -> None:
        self.stealth_backend = stealth_backend
        self.proxy = proxy
        self.record_har = record_har
        self.record_trace = record_trace
        self.source_slug = source_slug

    @asynccontextmanager
    async def new_context(self) -> AsyncIterator[BrowserContext]:
        """Yield a configured BrowserContext; flush HAR + trace on exit."""
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        har_path = _HAR_DIR / f"{self.source_slug}-{ts}.har"
        trace_path = _TRACE_DIR / f"{self.source_slug}-{ts}.zip"

        _HAR_DIR.mkdir(parents=True, exist_ok=True)
        _TRACE_DIR.mkdir(parents=True, exist_ok=True)

        backend = get_backend(self.stealth_backend)

        async with async_playwright() as pw:
            ctx_kwargs: dict = {
                "locale": "en-US",
                "timezone_id": "UTC",
                "viewport": {"width": 1280, "height": 800},
            }

            ua = _UA.get(self.stealth_backend, "")
            if ua:
                ctx_kwargs["user_agent"] = ua

            if self.record_har:
                ctx_kwargs["record_har_path"] = str(har_path)

            ctx: BrowserContext = await backend.new_context(
                pw,
                proxy=self.proxy,
                **ctx_kwargs,
            )

            if self.record_trace:
                await ctx.tracing.start(screenshots=True, snapshots=True, sources=True)

            try:
                yield ctx
            finally:
                if self.record_trace:
                    await ctx.tracing.stop(path=str(trace_path))
                await ctx.close()
