"""Network capture — attaches listeners before navigation, collects all traffic."""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import structlog
from playwright.async_api import CDPSession, Page, WebSocket

log = structlog.get_logger()

# Resource types we never want to classify as data endpoints
_SKIP_TYPES = {
    "image",
    "media",
    "font",
    "stylesheet",
    "ping",
    "prefetch",
    "eventsource",  # we handle WS separately
}

# URL fragments that indicate tracking/analytics — exclude from data classification
_NOISE_FRAGMENTS = {
    "analytics",
    "tracking",
    "telemetry",
    "beacon",
    "pixel",
    "log",
    "metrics",
    "sentry",
    "datadog",
    "segment",
    "mixpanel",
    "amplitude",
    "gtm",
    "ga4",
    "hotjar",
    "clarity",
    "intercom",
    "drift",
    "hubspot",
}


@dataclass
class CapturedRequest:
    request_id: str
    method: str
    url: str
    resource_type: str
    request_headers: dict[str, str]
    # Filled in on response
    status: int = 0
    response_headers: dict[str, str] = field(default_factory=dict)
    content_type: str = ""
    body_bytes: int = 0
    body_text: str = ""
    body_json: Any = None
    # Classification output
    data_likelihood: float = 0.0
    is_noise: bool = False

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc

    @property
    def path(self) -> str:
        return urlparse(self.url).path


@dataclass
class CapturedFrame:
    direction: str  # "sent" | "received"
    payload: str
    decoded: Any = None  # parsed JSON if payload is JSON


@dataclass
class CapturedWebSocket:
    url: str
    frames: list[CapturedFrame] = field(default_factory=list)

    @property
    def subscribe_frames(self) -> list[CapturedFrame]:
        """First few sent frames — typically the subscribe/handshake messages."""
        return [f for f in self.frames[:10] if f.direction == "sent"]

    @property
    def sample_received(self) -> list[CapturedFrame]:
        return [f for f in self.frames if f.direction == "received"][:5]


@dataclass
class EmbeddedState:
    global_var: str
    path: str
    sample: Any  # truncated preview


class NetworkCapture:
    """
    Attaches to a Playwright Page before navigation and records all traffic.
    Uses a CDP session to pull response bodies that Playwright's API doesn't expose.
    """

    def __init__(self, page: Page) -> None:
        self._page = page
        self._cdp: CDPSession | None = None
        self._requests: dict[str, CapturedRequest] = {}  # requestId → CapturedRequest
        self._url_to_id: dict[str, str] = {}  # url → requestId (last seen)
        self.websockets: list[CapturedWebSocket] = []
        self.embedded_states: list[EmbeddedState] = []
        self._body_fetch_tasks: list[asyncio.Task] = []

    async def attach(self) -> None:
        """Must be called BEFORE page.goto(). Wires all listeners and enables CDP Network."""
        self._cdp = await self._page.context.new_cdp_session(self._page)
        await self._cdp.send("Network.enable", {})

        # CDP-level listeners (give us requestId + full headers + bodies)
        self._cdp.on("Network.requestWillBeSent", self._on_cdp_request)
        self._cdp.on("Network.responseReceived", self._on_cdp_response)
        self._cdp.on("Network.loadingFinished", self._on_cdp_loading_finished)

        # Playwright-level WS listener
        self._page.on("websocket", self._on_websocket)

    def _on_cdp_request(self, event: dict) -> None:
        req = event.get("request", {})
        req_id = event.get("requestId", "")
        url = req.get("url", "")
        resource_type = event.get("type", "Other").lower()

        if resource_type in _SKIP_TYPES:
            return
        if any(n in url.lower() for n in _NOISE_FRAGMENTS):
            return

        self._requests[req_id] = CapturedRequest(
            request_id=req_id,
            method=req.get("method", "GET"),
            url=url,
            resource_type=resource_type,
            request_headers=req.get("headers", {}),
        )
        self._url_to_id[url] = req_id

    def _on_cdp_response(self, event: dict) -> None:
        req_id = event.get("requestId", "")
        captured = self._requests.get(req_id)
        if captured is None:
            return
        resp = event.get("response", {})
        captured.status = resp.get("status", 0)
        captured.response_headers = {k.lower(): v for k, v in resp.get("headers", {}).items()}
        captured.content_type = captured.response_headers.get("content-type", "")

    def _on_cdp_loading_finished(self, event: dict) -> None:
        req_id = event.get("requestId", "")
        captured = self._requests.get(req_id)
        if captured is None:
            return
        # Fetch the body in the background — non-blocking
        task = asyncio.get_event_loop().create_task(self._fetch_body(req_id, captured))
        self._body_fetch_tasks.append(task)

    async def _fetch_body(self, req_id: str, captured: CapturedRequest) -> None:
        if self._cdp is None:
            return
        try:
            result = await self._cdp.send("Network.getResponseBody", {"requestId": req_id})
            body = result.get("body", "")
            captured.body_bytes = len(body.encode())
            if "json" in captured.content_type or _looks_like_json(body):
                captured.body_text = body[:4000]
                with contextlib.suppress(json.JSONDecodeError):
                    captured.body_json = json.loads(body)
        except Exception:
            pass  # body unavailable (e.g. redirected, cached, or CDPError)

    def _on_websocket(self, ws: WebSocket) -> None:
        captured_ws = CapturedWebSocket(url=ws.url)
        self.websockets.append(captured_ws)

        def _on_sent(payload: str) -> None:
            frame = CapturedFrame(direction="sent", payload=payload)
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                frame.decoded = json.loads(payload)
            captured_ws.frames.append(frame)

        def _on_received(payload: str) -> None:
            frame = CapturedFrame(direction="received", payload=payload)
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                frame.decoded = json.loads(payload)
            captured_ws.frames.append(frame)

        ws.on("framesent", lambda f: _on_sent(f.payload))
        ws.on("framereceived", lambda f: _on_received(f.payload))

    async def wait_for_bodies(self, timeout: float = 5.0) -> None:
        """Wait for in-flight body-fetch tasks to settle."""
        if self._body_fetch_tasks:
            await asyncio.wait(self._body_fetch_tasks, timeout=timeout)

    async def probe_embedded_state(self) -> None:
        """Probe common JS globals that embed server-rendered state."""
        globals_to_check = [
            ("__NEXT_DATA__", "props.pageProps"),
            ("__INITIAL_STATE__", ""),
            ("__REDUX_STATE__", ""),
            ("__apollo_state__", "ROOT_QUERY"),
            ("__APP_STATE__", ""),
            ("__PAGE_DATA__", ""),
        ]
        for var, path in globals_to_check:
            try:
                exists = await self._page.evaluate(f"() => typeof window['{var}'] !== 'undefined'")
                if exists:
                    sample = await self._page.evaluate(
                        f"() => JSON.stringify(window['{var}'])?.slice(0, 2000)"
                    )
                    parsed = None
                    if sample:
                        try:
                            parsed = json.loads(sample)
                        except json.JSONDecodeError:
                            parsed = sample
                    self.embedded_states.append(
                        EmbeddedState(global_var=var, path=path, sample=parsed)
                    )
                    log.debug("cartographer.embedded_state", var=var)
            except Exception:
                pass

    @property
    def captured_requests(self) -> list[CapturedRequest]:
        return list(self._requests.values())


def _looks_like_json(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(("{", "["))
