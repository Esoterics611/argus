"""Classification heuristics — score each captured request for data likelihood."""

from __future__ import annotations

import re
from typing import Any

from argus.cartographer.capture import CapturedRequest

# Path tokens that strongly suggest a data API
_DATA_PATH_TOKENS = re.compile(
    r"/(api|v\d|graphql|gql|query|data|feed|stream|ws|socket|price|funding|"
    r"liquidat|oi|openinterest|longshort|ticker|candle|kline|trade|order|market|"
    r"calendar|event|release|rate|stat|metric|historical|live|realtime)/",
    re.IGNORECASE,
)

# Path tokens that suggest assets/tracking (already filtered, but belt-and-suspenders)
_NOISE_PATH_TOKENS = re.compile(
    r"/(static|assets|images|icons|fonts|css|js|chunks|_next/static|__webpack|"
    r"analytics|track|log|beacon|ping|pixel|collect|batch)/",
    re.IGNORECASE,
)

# Minimum body size to be a meaningful data response (bytes)
_MIN_DATA_BODY = 50


def score_request(req: CapturedRequest) -> float:
    """
    Return a data-likelihood score in [0.0, 1.0].
    Higher = more likely to be a data endpoint worth replaying.
    """
    score = 0.0
    url_lower = req.url.lower()
    path_lower = req.path.lower()

    # Fast disqualifiers
    if req.status not in range(200, 300):
        return 0.0
    if _NOISE_PATH_TOKENS.search(path_lower):
        return 0.0

    # Content-type: JSON is the strongest signal
    if "json" in req.content_type:
        score += 0.40
    elif "msgpack" in req.content_type or "cbor" in req.content_type:
        score += 0.30

    # Path tokens
    if _DATA_PATH_TOKENS.search(path_lower):
        score += 0.25

    # File extension check — API paths don't have .js/.css/.woff etc.
    if re.search(r"\.(js|css|woff2?|ttf|eot|svg|png|jpg|gif|ico|map|txt|xml)(\?|$)", path_lower):
        score -= 0.30

    # Body analysis
    if req.body_bytes >= _MIN_DATA_BODY:
        score += 0.10
    if req.body_json is not None:
        score += 0.10
        if _has_numeric_series(req.body_json):
            score += 0.15  # arrays of numbers → almost certainly financial data

    # Method: POST to /graphql or /query is very likely data
    if req.method == "POST" and ("graphql" in url_lower or "query" in url_lower):
        score += 0.20

    # XHR/fetch resource types
    if req.resource_type in ("xhr", "fetch"):
        score += 0.10

    return max(0.0, min(1.0, score))


def classify_all(requests: list[CapturedRequest]) -> list[CapturedRequest]:
    """Score, mark noise, and sort requests by data_likelihood descending."""
    for req in requests:
        req.data_likelihood = score_request(req)
        req.is_noise = req.data_likelihood < 0.10
    return sorted(requests, key=lambda r: r.data_likelihood, reverse=True)


def top_data_endpoints(
    requests: list[CapturedRequest], threshold: float = 0.35, limit: int = 10
) -> list[CapturedRequest]:
    """Return the top-ranked data endpoints above *threshold*."""
    return [r for r in requests if r.data_likelihood >= threshold][:limit]


def recommend_tier(
    requests: list[CapturedRequest],
    has_websocket: bool = False,
    has_embedded_state: bool = False,
) -> int:
    """
    Recommend the cheapest viable tier given what the Cartographer found.
    Follows the Extraction Strategy Ladder: prefer lower tiers.
    """
    top = top_data_endpoints(requests)
    if top:
        return 1  # Tier 1: hidden JSON endpoint replay
    if has_websocket:
        return 3  # Tier 3: WebSocket tap
    if has_embedded_state:
        return 2  # Tier 2: embedded JS state
    return 4  # Tier 4: DOM scrape as fallback


def _has_numeric_series(obj: Any, depth: int = 0) -> bool:
    """Return True if obj contains an array of numbers (financial data signal)."""
    if depth > 4:
        return False
    if isinstance(obj, list) and len(obj) > 1:
        if all(isinstance(v, (int, float)) for v in obj[:5]):
            return True
        # Array of objects (e.g. [{price: 1, vol: 2}, ...])
        if all(isinstance(v, dict) for v in obj[:3]):
            return any(isinstance(v, (int, float)) for item in obj[:3] for v in item.values())
    if isinstance(obj, dict):
        return any(_has_numeric_series(v, depth + 1) for v in obj.values())
    return False
