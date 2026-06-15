"""Stealth backend implementations behind the Backend protocol."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from playwright.async_api import BrowserContext, BrowserType, Playwright


@runtime_checkable
class Backend(Protocol):
    """Stealth swap-seam interface. All implementations expose these two methods."""

    async def launch(self, playwright: Playwright, **kwargs: Any) -> BrowserType:
        """Return a launched browser (or browser-type handle for new_context)."""
        ...

    async def new_context(
        self,
        playwright: Playwright,
        proxy: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> BrowserContext:
        """Return a new BrowserContext with stealth applied."""
        ...


# ── Vanilla ──────────────────────────────────────────────────────────────────


class VanillaBackend:
    """Plain async_playwright — no patches. Default for tests."""

    async def launch(self, playwright: Playwright, **kwargs: Any) -> Any:
        return await playwright.chromium.launch(**kwargs)

    async def new_context(
        self,
        playwright: Playwright,
        proxy: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> BrowserContext:
        browser = await playwright.chromium.launch(headless=True)
        ctx_kwargs: dict[str, Any] = {**kwargs}
        if proxy:
            ctx_kwargs["proxy"] = proxy
        return await browser.new_context(**ctx_kwargs)


# ── playwright-stealth (JS-layer) ─────────────────────────────────────────────


class StealthBackend:
    """VanillaBackend + playwright-stealth JS-layer patches."""

    async def launch(self, playwright: Playwright, **kwargs: Any) -> Any:
        return await playwright.chromium.launch(**kwargs)

    async def new_context(
        self,
        playwright: Playwright,
        proxy: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> BrowserContext:
        from playwright_stealth import stealth_async  # type: ignore[import-untyped]

        browser = await playwright.chromium.launch(headless=True)
        ctx_kwargs: dict[str, Any] = {**kwargs}
        if proxy:
            ctx_kwargs["proxy"] = proxy
        ctx = await browser.new_context(**ctx_kwargs)
        page = await ctx.new_page()
        await stealth_async(page)
        await page.close()
        return ctx


# ── Patchright (CDP-leak patched Chromium fork) ───────────────────────────────


class PatchrightBackend:
    """Patchright fork — eliminates CDP-level headless signals."""

    async def launch(self, playwright: Playwright, **kwargs: Any) -> Any:
        from patchright.async_api import (
            async_playwright as patchright_playwright,  # type: ignore[import-untyped]
        )

        async with patchright_playwright() as pr:
            return await pr.chromium.launch(**kwargs)

    async def new_context(
        self,
        playwright: Playwright,
        proxy: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> BrowserContext:
        from patchright.async_api import (
            async_playwright as patchright_playwright,  # type: ignore[import-untyped]
        )

        # Patchright manages its own playwright instance
        self._pr_cm = patchright_playwright()
        pr = await self._pr_cm.__aenter__()
        browser = await pr.chromium.launch(headless=True)
        ctx_kwargs: dict[str, Any] = {**kwargs}
        if proxy:
            ctx_kwargs["proxy"] = proxy
        return await browser.new_context(**ctx_kwargs)


# ── Camoufox (Firefox fork, C++-level fingerprint spoofing) ──────────────────


class CamoufoxBackend:
    """Camoufox — Firefox fork with C++-level fingerprint spoofing."""

    async def launch(self, playwright: Playwright, **kwargs: Any) -> Any:
        from camoufox.async_api import AsyncCamoufox  # type: ignore[import-untyped]

        return AsyncCamoufox(headless=True, **kwargs)

    async def new_context(
        self,
        playwright: Playwright,
        proxy: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> BrowserContext:
        from camoufox.async_api import AsyncCamoufox  # type: ignore[import-untyped]

        fox_kwargs: dict[str, Any] = {**kwargs}
        if proxy:
            fox_kwargs["proxy"] = proxy
        browser = AsyncCamoufox(headless=True, **fox_kwargs)
        async with browser as b:
            # Camoufox returns a BrowserContext directly
            return await b.new_context()
