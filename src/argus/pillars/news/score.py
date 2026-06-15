"""
Importance scoring (1–3) for NewsItem records.

Rule-based primary scorer + a pluggable ImpactScorer interface stub.
The stub ships a no-op; a Claude-via-MCP implementation can replace it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from argus.core.contracts import NewsItem

# Source IDs that are inherently importance=3 (primary regulatory / macro)
_TIER3_SOURCE_IDS = frozenset(
    {"fed_press", "sec_press", "sec_8k", "bls_releases", "us_treasury", "ecb_press"}
)

# Headline keywords that bump importance to 3
_TIER3_KEYWORDS = frozenset(
    {
        "rate decision",
        "fomc",
        "federal reserve",
        "interest rate",
        "rate hike",
        "rate cut",
        "quantitative tightening",
        "emergency meeting",
        "sec charges",
        "sec lawsuit",
        "sec approval",
        "etf approved",
        "etf rejected",
        "cpi report",
        "nonfarm payrolls",
        "non-farm payrolls",
        "jobs report",
        "inflation",
        "ecb decision",
        "bank of england",
    }
)

# Headline keywords that bump to at least importance=2
_TIER2_KEYWORDS = frozenset(
    {
        "bitcoin",
        "btc",
        "ethereum",
        "eth",
        "regulation",
        "regulatory",
        "enforcement",
        "hack",
        "exploit",
        "bankruptcy",
        "insolvency",
        "sanctions",
        "treasury",
        "stablecoin",
        "cbdc",
    }
)

# Asset tags that bump to at least importance=2
_TIER2_MACRO_TAGS = frozenset(
    {
        "MACRO:CPI",
        "MACRO:NFP",
        "MACRO:FOMC",
        "MACRO:PCE",
        "MACRO:ETF",
        "MACRO:SEC",
    }
)


def importance_score(item: NewsItem) -> int:
    """
    Rule-based importance 1–3.
    3 = primary-source regulatory / breaking macro
    2 = named-asset + moderate relevance
    1 = background / filler
    """
    if item.source_id in _TIER3_SOURCE_IDS:
        return 3

    headline_lower = item.headline.lower()
    snippet_lower = (item.body_snippet or "").lower()
    combined = headline_lower + " " + snippet_lower

    for kw in _TIER3_KEYWORDS:
        if kw in combined:
            return 3

    # Check macro asset tags
    if any(t in _TIER2_MACRO_TAGS for t in item.assets):
        return 2

    for kw in _TIER2_KEYWORDS:
        if kw in combined:
            return 2

    return 1


@runtime_checkable
class ImpactScorer(Protocol):
    """
    Interface for market-impact scoring. Ships as a no-op stub.
    A Claude-via-MCP implementation can replace this without changing pipeline.py.
    """

    def score_impact(self, item: NewsItem) -> NewsItem:
        """Return item with updated importance/category fields. No-op by default."""
        ...


class NoOpImpactScorer:
    """Default stub — returns item unchanged. Off by default."""

    def score_impact(self, item: NewsItem) -> NewsItem:
        return item
