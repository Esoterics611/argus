"""Tests for BrowserFactory — vanilla context, route-mocked page, no live network."""

import pytest
from playwright.async_api import Route

from argus.core.browser import BrowserFactory


@pytest.fixture
def tmp_traces(tmp_path, monkeypatch):
    """Redirect trace/HAR dirs to tmp_path so tests don't pollute the repo."""
    import argus.core.browser as bmod

    monkeypatch.setattr(bmod, "_HAR_DIR", tmp_path / "har")
    monkeypatch.setattr(bmod, "_TRACE_DIR", tmp_path / "trace")


async def test_browser_factory_vanilla_loads_page(tmp_traces):
    factory = BrowserFactory(
        stealth_backend="vanilla",
        record_har=False,
        record_trace=False,
        source_slug="test",
    )
    async with factory.new_context() as ctx:
        page = await ctx.new_page()
        await page.route(
            "**/*",
            lambda route, _: route.fulfill(
                status=200,
                content_type="text/html",
                body="<html><body><h1>hello argus</h1></body></html>",
            ),
        )
        await page.goto("https://fake.local/")
        title = await page.inner_text("h1")
        assert title == "hello argus"


async def test_browser_factory_intercepts_json_xhr(tmp_traces):
    """Confirms XHR interception works — foundation for Cartographer tests."""
    factory = BrowserFactory(
        stealth_backend="vanilla",
        record_har=False,
        record_trace=False,
        source_slug="test",
    )
    captured: list[dict] = []

    async with factory.new_context() as ctx:
        page = await ctx.new_page()

        async def _handle(route: Route) -> None:
            if "/api/data" in route.request.url:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"items": [{"price": 42.0}]}',
                )
            else:
                await route.fulfill(
                    status=200,
                    content_type="text/html",
                    body="""
                    <html><body>
                    <script>
                      fetch('/api/data').then(r => r.json()).then(d => {
                        document.title = d.items[0].price;
                      });
                    </script>
                    </body></html>
                    """,
                )

        page.on(
            "response",
            lambda resp: (
                captured.append({"url": resp.url, "status": resp.status})
                if "/api/data" in resp.url
                else None
            ),
        )
        await page.route("**/*", _handle)
        await page.goto("https://fake.local/")
        await page.wait_for_timeout(500)

    assert any("/api/data" in r["url"] for r in captured)


async def test_browser_factory_utc_timezone(tmp_traces):
    """Confirms context locale/tz is pinned to UTC."""
    factory = BrowserFactory(
        stealth_backend="vanilla",
        record_har=False,
        record_trace=False,
        source_slug="test",
    )
    async with factory.new_context() as ctx:
        page = await ctx.new_page()
        tz = await page.evaluate("() => Intl.DateTimeFormat().resolvedOptions().timeZone")
        assert tz == "UTC"
