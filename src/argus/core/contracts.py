"""Pydantic v2 record contracts — the canonical output types for all Argus harvesters."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    source_id: str
    url: str
    headline: str
    body_snippet: str | None = None
    published_ts: datetime | None = None
    fetched_ts: datetime
    latency_ms: int | None = None
    assets: list[str] = Field(default_factory=list)
    category: str | None = None
    importance: Literal[1, 2, 3] = 1
    lang: str = "en"
    dedup_hash: str = ""
    corroborations: list[str] = Field(default_factory=list)
    revision_of: str | None = None


class MacroEvent(BaseModel):
    source_id: str
    event: str
    country: str
    currency: str
    importance: Literal[1, 2, 3]
    scheduled_ts: datetime
    actual: Decimal | None = None
    forecast: Decimal | None = None
    previous: Decimal | None = None
    revision: Decimal | None = None
    surprise: Decimal | None = None
    unit: str | None = None
    fetched_ts: datetime
    latency_ms: int | None = None


class FundingPoint(BaseModel):
    source_id: str
    exchange: str
    symbol: str
    funding_rate: Decimal
    interval_h: int = 8
    next_funding_ts: datetime
    ts: datetime
    fetched_ts: datetime


class LiquidationPoint(BaseModel):
    source_id: str
    exchange: str
    symbol: str
    side: Literal["long", "short"]
    notional_usd: Decimal
    ts: datetime
    fetched_ts: datetime


class OpenInterestPoint(BaseModel):
    source_id: str
    exchange: str
    symbol: str
    open_interest_usd: Decimal
    ts: datetime
    fetched_ts: datetime


class LongShortRatioPoint(BaseModel):
    source_id: str
    exchange: str
    symbol: str
    long_ratio: Decimal
    short_ratio: Decimal
    ts: datetime
    fetched_ts: datetime


class LiqHeatmapCell(BaseModel):
    source_id: str
    symbol: str
    price_level: Decimal
    magnitude: Decimal
    as_of_ts: datetime
    fetched_ts: datetime


class ReactionRow(BaseModel):
    event_id: str
    event_ts: datetime
    asset: str
    ret_30s: Decimal | None = None
    ret_5m: Decimal | None = None
    ret_1h: Decimal | None = None
    vol_spike: Decimal | None = None
    vwap_move: Decimal | None = None
    pre_vol: Decimal | None = None
    post_vol: Decimal | None = None
