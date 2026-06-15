"""Cartographer — point at any URL, get a full endpoint inventory + draft Source Card."""

from __future__ import annotations

from pathlib import Path

import structlog

from argus.cartographer.capture import NetworkCapture
from argus.cartographer.classify import classify_all, recommend_tier, top_data_endpoints
from argus.cartographer.emit import CartographResult, emit_json, emit_snippets, emit_source_card
from argus.core.browser import BrowserFactory

log = structlog.get_logger()

# How long to wait after page load for lazy XHR to fire (seconds)
_SETTLE_MS = 2000
_SCROLL_STEPS = 3


class Cartographer:
    """
    Profiles a URL by observing all network traffic, classifies data endpoints,
    and emits a draft Source Card + replay snippets.

    Usage:
        result = await Cartographer("https://example.com", pillar="news", id="example").run()
    """

    def __init__(
        self,
        url: str,
        pillar: str,
        source_id: str,
        stealth_backend: str = "vanilla",
        hint_clicks: list[str] | None = None,
        record_har: bool = True,
        record_trace: bool = True,
    ) -> None:
        self.url = url
        self.pillar = pillar
        self.source_id = source_id
        self.stealth_backend = stealth_backend
        self.hint_clicks = hint_clicks or []
        self.record_har = record_har
        self.record_trace = record_trace

    async def run(self) -> CartographResult:
        log.info("cartographer.start", url=self.url, id=self.source_id)
        factory = BrowserFactory(
            stealth_backend=self.stealth_backend,
            record_har=self.record_har,
            record_trace=self.record_trace,
            source_slug=self.source_id,
        )

        async with factory.new_context() as ctx:
            page = await ctx.new_page()
            capture = NetworkCapture(page)
            await capture.attach()

            # Navigate
            await page.goto(self.url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_load_state("networkidle", timeout=15_000)

            # Exercise the page to trigger lazy data loads
            await self._exercise(page)

            # Wait for body-fetch tasks to finish
            await capture.wait_for_bodies(timeout=8.0)

            # Probe embedded state
            await capture.probe_embedded_state()

            # Classify
            all_requests = classify_all(capture.captured_requests)
            top = top_data_endpoints(all_requests)
            tier = recommend_tier(
                all_requests,
                has_websocket=bool(capture.websockets),
                has_embedded_state=bool(capture.embedded_states),
            )

            # Resolve HAR/trace paths (written by BrowserFactory on ctx close)
            from datetime import UTC, datetime

            ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            har_path = str(Path("traces/har") / f"{self.source_id}-{ts}.har")
            trace_path = str(Path("traces/trace") / f"{self.source_id}-{ts}.zip")

        result = CartographResult(
            source_id=self.source_id,
            pillar=self.pillar,
            url=self.url,
            recommended_tier=tier,
            top_endpoints=top,
            websockets=capture.websockets,
            embedded_states=capture.embedded_states,
            all_requests=all_requests,
            har_path=har_path,
            trace_path=trace_path,
        )

        # Emit outputs
        json_path = emit_json(result)
        card_path = emit_source_card(result)
        snippet_path = emit_snippets(result)

        log.info(
            "cartographer.done",
            tier=tier,
            top_endpoints=len(top),
            websockets=len(capture.websockets),
            json=str(json_path),
            card=str(card_path),
            snippets=str(snippet_path),
        )
        return result

    async def _exercise(self, page) -> None:
        """Scroll, wait, and click hint tabs to trigger lazy data loads."""
        # Scroll down in steps to trigger virtualized content
        for _ in range(_SCROLL_STEPS):
            await page.evaluate("() => window.scrollBy(0, window.innerHeight * 0.8)")
            await page.wait_for_timeout(_SETTLE_MS // _SCROLL_STEPS)

        # Click any hint tabs the caller specified
        for label in self.hint_clicks:
            try:
                # Try text match first, then aria-label
                locator = page.get_by_text(label, exact=False).first
                if await locator.count() > 0:
                    await locator.click(timeout=3000)
                    await page.wait_for_timeout(1000)
                    log.debug("cartographer.hint_click", label=label)
            except Exception:
                pass  # hint click failure is non-fatal

        # Final settle
        await page.wait_for_timeout(_SETTLE_MS)
