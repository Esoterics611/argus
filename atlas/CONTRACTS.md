# Data Contracts

All records are Pydantic v2 models. All timestamps are `datetime` with `tzinfo=UTC`.
`fetched_ts` is mandatory on every record — Argus is a *latency-aware* harvester.

## Records

```python
class NewsItem(BaseModel):
    source_id: str
    url: str
    headline: str
    body_snippet: str | None
    published_ts: datetime | None          # claimed by source, UTC
    fetched_ts: datetime                   # observed by Argus, UTC
    latency_ms: int | None                 # fetched_ts - published_ts in ms
    assets: list[str]                      # ["BTC", "ETH", "MACRO:CPI"]
    category: str | None
    importance: Literal[1, 2, 3]           # 1=low, 3=breaking/regulatory
    lang: str                              # ISO 639-1
    dedup_hash: str                        # sha256(normalized headline + published_ts)
    corroborations: list[str]              # other source_ids reporting same story
    revision_of: str | None                # dedup_hash of the original item

class MacroEvent(BaseModel):
    source_id: str
    event: str                             # "Non-Farm Payrolls"
    country: str                           # ISO 3166-1 alpha-2
    currency: str                          # ISO 4217
    importance: Literal[1, 2, 3]
    scheduled_ts: datetime                 # UTC
    actual: Decimal | None
    forecast: Decimal | None
    previous: Decimal | None
    revision: Decimal | None               # revised previous, if source updates it
    surprise: Decimal | None               # actual - forecast
    unit: str | None                       # "K", "%", "B"
    fetched_ts: datetime
    latency_ms: int | None

class FundingPoint(BaseModel):
    source_id: str
    exchange: str
    symbol: str
    funding_rate: Decimal
    interval_h: int                        # funding interval in hours (usually 8)
    next_funding_ts: datetime
    ts: datetime                           # timestamp the rate is valid from
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
    long_ratio: Decimal                    # 0.0–1.0
    short_ratio: Decimal
    ts: datetime
    fetched_ts: datetime

class LiqHeatmapCell(BaseModel):
    source_id: str
    symbol: str
    price_level: Decimal
    magnitude: Decimal                     # relative liquidation density
    as_of_ts: datetime
    fetched_ts: datetime

class ReactionRow(BaseModel):
    event_id: str                          # dedup_hash for news; (source_id,event,scheduled_ts) key for macro
    event_ts: datetime
    asset: str
    ret_30s: Decimal | None
    ret_5m: Decimal | None
    ret_1h: Decimal | None
    vol_spike: Decimal | None              # post/pre volume ratio
    vwap_move: Decimal | None
    pre_vol: Decimal | None
    post_vol: Decimal | None
```

## Sink interface

```python
class Sink(Protocol):
    def ensure_schema(self, table: str, model: type[BaseModel]) -> None:
        """Create or migrate the table to match the model's schema."""

    def write(self, table: str, rows: Sequence[BaseModel]) -> int:
        """Idempotent write. Natural key is (source_id, <primary ts field>).
        Returns number of rows actually inserted (0 if all duplicates)."""
```

## Idempotency keys by table

| Table | Idempotency key |
|-------|----------------|
| news | `(source_id, dedup_hash)` |
| macro_events | `(source_id, event, scheduled_ts)` |
| funding | `(source_id, exchange, symbol, ts)` |
| liquidations | `(source_id, exchange, symbol, side, ts)` |
| open_interest | `(source_id, exchange, symbol, ts)` |
| long_short_ratio | `(source_id, exchange, symbol, ts)` |
| liq_heatmap | `(source_id, symbol, price_level, as_of_ts)` |
| reactions | `(event_id, asset)` |
