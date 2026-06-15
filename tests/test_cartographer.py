"""Tests for the Cartographer — route-mocked pages, no live network."""

from __future__ import annotations

import json

import pytest

from argus.cartographer.capture import CapturedRequest, NetworkCapture, _looks_like_json
from argus.cartographer.classify import (
    classify_all,
    recommend_tier,
    score_request,
    top_data_endpoints,
)
from argus.cartographer.emit import CartographResult, emit_source_card
from argus.core.browser import BrowserFactory

# ── Unit tests for classify.py (no browser) ──────────────────────────────────


def _make_req(
    url: str = "https://api.example.com/v1/funding",
    method: str = "GET",
    status: int = 200,
    content_type: str = "application/json",
    body_json: object = None,
    body_bytes: int = 500,
    resource_type: str = "xhr",
) -> CapturedRequest:
    return CapturedRequest(
        request_id="test-id",
        method=method,
        url=url,
        resource_type=resource_type,
        request_headers={"Referer": "https://example.com/"},
        status=status,
        content_type=content_type,
        body_bytes=body_bytes,
        body_json=body_json,
    )


def test_score_json_api_endpoint():
    req = _make_req(
        url="https://fapi.coinglass.com/api/v3/fundingRate",
        body_json=[{"rate": 0.0001, "symbol": "BTC"}],
    )
    score = score_request(req)
    assert score >= 0.35, f"Expected high score, got {score}"


def test_score_static_asset_is_low():
    req = _make_req(
        url="https://cdn.example.com/static/chunk.js",
        content_type="application/javascript",
        body_json=None,
        resource_type="script",
    )
    score = score_request(req)
    assert score < 0.10


def test_score_non_200_is_zero():
    req = _make_req(status=404)
    assert score_request(req) == 0.0


def test_score_numeric_series_boosts_score():
    # Array of price floats (len > 1) → strongest financial data signal
    req = _make_req(body_json=[1.0, 2.0, 3.0, 4.0, 5.0])
    score_with = score_request(req)
    # Dict with non-numeric values — same JSON content-type, same path, but no numeric series
    req_plain = _make_req(body_json={"key": "value", "name": "test"})
    score_without = score_request(req_plain)
    assert score_with > score_without


def test_recommend_tier_with_json_endpoints():
    req = _make_req()
    req.data_likelihood = 0.80
    assert recommend_tier([req]) == 1


def test_recommend_tier_websocket_fallback():
    assert recommend_tier([], has_websocket=True) == 3


def test_recommend_tier_embedded_state_fallback():
    assert recommend_tier([], has_embedded_state=True) == 2


def test_recommend_tier_dom_fallback():
    assert recommend_tier([]) == 4


def test_top_data_endpoints_filters_by_threshold():
    reqs = [_make_req() for _ in range(5)]
    reqs[0].data_likelihood = 0.90
    reqs[1].data_likelihood = 0.70
    reqs[2].data_likelihood = 0.20  # below threshold
    reqs[3].data_likelihood = 0.05
    reqs[4].data_likelihood = 0.50
    top = top_data_endpoints(reqs)
    assert all(r.data_likelihood >= 0.35 for r in top)
    assert len(top) == 3  # 0.90, 0.70, 0.50


def test_looks_like_json():
    assert _looks_like_json('{"key": 1}')
    assert _looks_like_json("[1, 2, 3]")
    assert not _looks_like_json("hello world")
    assert not _looks_like_json("")


# ── Integration tests with route-mocked browser ───────────────────────────────


@pytest.fixture
def tmp_traces(tmp_path, monkeypatch):
    import argus.core.browser as bmod

    monkeypatch.setattr(bmod, "_HAR_DIR", tmp_path / "har")
    monkeypatch.setattr(bmod, "_TRACE_DIR", tmp_path / "trace")


@pytest.fixture
def tmp_sources(tmp_path, monkeypatch):
    import argus.cartographer.emit as emod
    import argus.core.source_card as scmod

    monkeypatch.setattr(scmod, "SOURCES_ROOT", tmp_path / "sources")
    monkeypatch.setattr(emod, "SOURCES_ROOT", tmp_path / "sources")
    return tmp_path / "sources"


FUNDING_DATA = json.dumps([{"exchange": "Binance", "symbol": "BTCUSDT", "fundingRate": 0.0001}])

FIXTURE_HTML = """
<html><body>
<h1>Fake Exchange</h1>
<script>
  // Fire XHR to the data endpoint
  fetch('/api/v1/funding')
    .then(r => r.json())
    .then(d => { document.title = 'loaded'; });
</script>
</body></html>
"""


async def test_cartographer_classifies_xhr_as_data_endpoint(tmp_traces, tmp_sources):
    """Cartographer must classify the /api/v1/funding XHR as a top data endpoint."""

    async def _run():
        factory = BrowserFactory(
            stealth_backend="vanilla",
            record_har=False,
            record_trace=False,
            source_slug="test",
        )
        async with factory.new_context() as ctx:
            page = await ctx.new_page()
            capture = NetworkCapture(page)
            await capture.attach()

            async def _handle(route):
                if "/api/v1/funding" in route.request.url:
                    await route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=FUNDING_DATA,
                    )
                else:
                    await route.fulfill(
                        status=200,
                        content_type="text/html",
                        body=FIXTURE_HTML,
                    )

            await page.route("**/*", _handle)
            await page.goto("https://fake.exchange/")
            await page.wait_for_timeout(800)
            await capture.wait_for_bodies(timeout=3.0)

        classified = classify_all(capture.captured_requests)
        top = top_data_endpoints(classified)
        return classified, top

    classified, top = await _run()

    funding_reqs = [r for r in classified if "/api/v1/funding" in r.url]
    assert funding_reqs, "Cartographer did not capture the /api/v1/funding request"
    assert (
        funding_reqs[0].data_likelihood >= 0.35
    ), f"Expected data_likelihood >= 0.35, got {funding_reqs[0].data_likelihood}"
    assert any(
        "/api/v1/funding" in r.url for r in top
    ), "Funding endpoint not in top data endpoints"


async def test_cartographer_recommends_tier1_for_json_endpoint(tmp_traces, tmp_sources):
    """When a JSON endpoint is found, recommended tier must be 1."""
    factory = BrowserFactory(
        stealth_backend="vanilla",
        record_har=False,
        record_trace=False,
        source_slug="test",
    )
    async with factory.new_context() as ctx:
        page = await ctx.new_page()
        capture = NetworkCapture(page)
        await capture.attach()

        async def _handle(route):
            if "/api/v1/funding" in route.request.url:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=FUNDING_DATA,
                )
            else:
                await route.fulfill(status=200, content_type="text/html", body=FIXTURE_HTML)

        await page.route("**/*", _handle)
        await page.goto("https://fake.exchange/")
        await page.wait_for_timeout(800)
        await capture.wait_for_bodies(timeout=3.0)

    classified = classify_all(capture.captured_requests)
    tier = recommend_tier(classified)
    assert tier == 1, f"Expected tier 1, got {tier}"


async def test_cartographer_emits_source_card(tmp_traces, tmp_sources):
    """emit_source_card must write a valid YAML with tier and discovered_endpoints."""
    from argus.core.source_card import load

    req = _make_req(url="https://api.example.com/v1/funding")
    req.data_likelihood = 0.85

    result = CartographResult(
        source_id="test_exchange",
        pillar="derivs",
        url="https://example.com",
        recommended_tier=1,
        top_endpoints=[req],
        websockets=[],
        embedded_states=[],
        all_requests=[req],
    )
    card_path = emit_source_card(result)
    assert card_path.exists()

    card = load(card_path)
    assert card.id == "test_exchange"
    assert card.tier == 1
    assert len(card.discovered_endpoints) == 1
    assert "api.example.com" in card.discovered_endpoints[0].url_template


def test_ws_capture_records_subscribe_frame():
    """
    Unit test: _on_websocket handler correctly records sent frames.

    Note: page.route_web_socket (Playwright 1.48+) intercepts before page.on("websocket")
    fires, so WS capture is validated here via the internal handler directly.
    The full live-WS path is exercised by the Cartographer integration tests against
    real sources (Coinglass WS — Prompt 06).
    """
    from unittest.mock import MagicMock

    from argus.cartographer.capture import NetworkCapture

    WS_SUBSCRIBE = '{"op":"subscribe","args":["funding"]}'
    RECEIVE_FRAME = '{"data":{"rate":0.0001}}'

    # Build a fake Page (we only need to call _on_websocket directly)
    fake_page = MagicMock()
    capture = NetworkCapture(fake_page)

    # Simulate a WebSocket object arriving from Playwright's on("websocket") event
    fake_ws = MagicMock()
    fake_ws.url = "wss://fake.exchange/ws"

    # Capture the on() callbacks registered on the fake WS
    callbacks: dict[str, object] = {}
    fake_ws.on.side_effect = lambda event, cb: callbacks.update({event: cb})

    capture._on_websocket(fake_ws)

    # Simulate JS sending the subscribe frame
    assert "framesent" in callbacks
    sent_frame = MagicMock()
    sent_frame.payload = WS_SUBSCRIBE
    callbacks["framesent"](sent_frame)

    # Simulate receiving a data frame
    assert "framereceived" in callbacks
    recv_frame = MagicMock()
    recv_frame.payload = RECEIVE_FRAME
    callbacks["framereceived"](recv_frame)

    assert len(capture.websockets) == 1
    ws = capture.websockets[0]
    assert "fake.exchange" in ws.url

    sent = ws.subscribe_frames
    assert sent, "No sent frames recorded"
    assert sent[0].payload == WS_SUBSCRIBE
    assert sent[0].decoded == {"op": "subscribe", "args": ["funding"]}

    received = ws.sample_received
    assert received, "No received frames recorded"
    assert received[0].decoded == {"data": {"rate": 0.0001}}
