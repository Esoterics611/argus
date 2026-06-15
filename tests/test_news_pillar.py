"""
Tests for src/argus/pillars/news/ — normalize, dedup, tag, score, harvester, pipeline.
No live network. Feedparser results are built from synthetic dicts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from argus.core.contracts import NewsItem
from argus.core.source_card import RssFeed, SourceCard
from argus.pillars.news.dedup import deduplicate
from argus.pillars.news.normalize import (
    _compute_hash,
    _parse_ts,
    normalize_entry,
    normalize_feed,
)
from argus.pillars.news.score import NoOpImpactScorer, importance_score
from argus.pillars.news.tag import AssetTagger
from argus.sinks.memory import MemorySink

# ── Helpers ───────────────────────────────────────────────────────────────────

_FETCHED = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

# feedparser represents time as a UTC 9-tuple (struct_time)
_TIME_STRUCT = (2024, 6, 15, 11, 55, 0, 5, 167, 0)  # 11:55 UTC


def _entry(
    title: str = "Bitcoin hits $100k",
    link: str = "https://coindesk.com/1",
    summary: str = "BTC surges past $100,000 for the first time.",
    published_parsed: tuple | None = _TIME_STRUCT,
    updated_parsed: tuple | None = None,
) -> dict:
    e: dict = {"title": title, "link": link, "summary": summary}
    if published_parsed is not None:
        e["published_parsed"] = published_parsed
    if updated_parsed is not None:
        e["updated_parsed"] = updated_parsed
    return e


def _parsed_feed(entries: list[dict], language: str = "en") -> dict:
    return {"feed": {"language": language}, "entries": entries}


def _news_item(
    source_id: str = "coindesk",
    headline: str = "Bitcoin hits $100k",
    published_ts: datetime | None = None,
    importance: int = 1,
    assets: list[str] | None = None,
) -> NewsItem:
    published_ts = published_ts or _FETCHED - timedelta(minutes=5)
    return NewsItem(
        source_id=source_id,
        url="https://example.com/1",
        headline=headline,
        fetched_ts=_FETCHED,
        published_ts=published_ts,
        latency_ms=300_000,
        assets=assets or [],
        importance=importance,  # type: ignore[arg-type]
        dedup_hash=_compute_hash(headline, published_ts),
        corroborations=[],
    )


def _card(source_id: str = "coindesk") -> SourceCard:
    return SourceCard(
        id=source_id,
        name="CoinDesk",
        url="https://coindesk.com/rss",
        pillar="news",
        tier=0,
        rss_feeds=[RssFeed(url="https://coindesk.com/arc/outboundfeeds/rss/")],
    )


# ── normalize.py ──────────────────────────────────────────────────────────────


def test_parse_ts_returns_utc_datetime():
    ts = _parse_ts(_TIME_STRUCT)
    assert ts is not None
    assert ts.tzinfo is UTC
    assert ts.hour == 11
    assert ts.minute == 55


def test_parse_ts_none_returns_none():
    assert _parse_ts(None) is None


def test_normalize_entry_basic():
    entry = _entry()
    item = normalize_entry(entry, "coindesk", {"language": "en"}, _FETCHED)
    assert item is not None
    assert item.source_id == "coindesk"
    assert item.headline == "Bitcoin hits $100k"
    assert item.published_ts is not None
    assert item.published_ts.tzinfo is UTC
    assert item.latency_ms == 5 * 60 * 1000  # 5 minutes
    assert item.dedup_hash != ""
    assert item.revision_of is None


def test_normalize_entry_skips_empty_headline():
    entry = _entry(title="  ")
    item = normalize_entry(entry, "coindesk", {}, _FETCHED)
    assert item is None


def test_normalize_entry_revision_detected():
    # updated_parsed differs from published_parsed by more than 60s
    updated = (2024, 6, 15, 12, 30, 0, 5, 167, 0)  # 35 min later
    entry = _entry(updated_parsed=updated)
    item = normalize_entry(entry, "coindesk", {}, _FETCHED)
    assert item is not None
    assert item.revision_of is not None


def test_normalize_entry_no_revision_when_same_ts():
    # updated_parsed same as published_parsed → no revision
    entry = _entry(updated_parsed=_TIME_STRUCT)
    item = normalize_entry(entry, "coindesk", {}, _FETCHED)
    assert item is not None
    assert item.revision_of is None


def test_normalize_entry_future_ts_clamped():
    future = (2024, 6, 16, 12, 0, 0, 5, 167, 0)  # 24h in future
    entry = _entry(published_parsed=future)
    item = normalize_entry(entry, "coindesk", {}, _FETCHED)
    assert item is not None
    # Clamped to fetched_ts
    assert item.published_ts == _FETCHED


def test_normalize_feed_returns_list():
    feed = _parsed_feed([_entry(), _entry(title="ETH up 10%", link="https://coindesk.com/2")])
    items = normalize_feed(feed, "coindesk", _FETCHED)
    assert len(items) == 2
    assert all(i.source_id == "coindesk" for i in items)


def test_normalize_feed_stale_item_skipped():
    old = (2024, 5, 1, 0, 0, 0, 0, 121, 0)  # >30 days before fetched_ts
    feed = _parsed_feed([_entry(published_parsed=old)])
    items = normalize_feed(feed, "coindesk", _FETCHED)
    assert len(items) == 0


def test_dedup_hash_stable():
    h1 = _compute_hash("Bitcoin hits $100k", _FETCHED)
    h2 = _compute_hash("Bitcoin hits $100k", _FETCHED)
    assert h1 == h2
    assert len(h1) == 16


# ── dedup.py ──────────────────────────────────────────────────────────────────


def test_dedup_merges_same_headline_same_time():
    ts = _FETCHED - timedelta(minutes=2)
    item_a = _news_item(
        source_id="coindesk", headline="Bitcoin ETF approved by SEC", published_ts=ts
    )
    item_b = _news_item(
        source_id="theblock", headline="Bitcoin ETF Approved By SEC", published_ts=ts
    )

    result = deduplicate([item_a, item_b])
    assert len(result) == 1
    assert "theblock" in result[0].corroborations


def test_dedup_keeps_distinct_stories():
    ts = _FETCHED - timedelta(minutes=2)
    item_a = _news_item(source_id="coindesk", headline="Bitcoin ETF approved", published_ts=ts)
    item_b = _news_item(
        source_id="theblock", headline="Ethereum upgrade goes live", published_ts=ts
    )

    result = deduplicate([item_a, item_b])
    assert len(result) == 2


def test_dedup_outside_window_not_merged():
    item_a = _news_item(
        source_id="coindesk",
        headline="Fed cuts rates by 50bp",
        published_ts=_FETCHED - timedelta(hours=2),
    )
    item_b = _news_item(
        source_id="theblock", headline="Fed Cuts Rates by 50bp", published_ts=_FETCHED
    )  # 2 hours later — outside window

    result = deduplicate([item_a, item_b])
    assert len(result) == 2


def test_dedup_empty_list():
    assert deduplicate([]) == []


def test_dedup_single_item():
    item = _news_item()
    result = deduplicate([item])
    assert len(result) == 1


# ── tag.py ────────────────────────────────────────────────────────────────────


@pytest.fixture
def tagger(tmp_path: Path) -> AssetTagger:
    aliases = tmp_path / "asset_aliases.yaml"
    aliases.write_text(
        "BTC:\n  - bitcoin\n  - btc\n"
        "ETH:\n  - ethereum\n  - eth\n"
        "MACRO:CPI:\n  - consumer price index\n  - cpi\n"
    )
    return AssetTagger.load(aliases)


def test_tagger_matches_btc(tagger: AssetTagger):
    tags = tagger.tag("Bitcoin hits $100k", "BTC surges past six figures.")
    assert "BTC" in tags


def test_tagger_matches_macro_cpi(tagger: AssetTagger):
    tags = tagger.tag("CPI report shows 3.2% inflation")
    assert "MACRO:CPI" in tags


def test_tagger_no_match(tagger: AssetTagger):
    tags = tagger.tag("Local weather forecast for Tuesday")
    assert tags == []


def test_tagger_multiple_assets(tagger: AssetTagger):
    tags = tagger.tag("Bitcoin and Ethereum both rally as CPI cools")
    assert "BTC" in tags
    assert "ETH" in tags
    assert "MACRO:CPI" in tags


def test_tagger_case_insensitive(tagger: AssetTagger):
    tags = tagger.tag("BITCOIN AT ALL TIME HIGH")
    assert "BTC" in tags


def test_tagger_returns_sorted(tagger: AssetTagger):
    tags = tagger.tag("bitcoin ethereum cpi")
    assert tags == sorted(tags)


def test_tagger_load_real_aliases():
    """The real asset_aliases.yaml must load without error."""
    real_path = Path("db/asset_aliases.yaml")
    if real_path.exists():
        t = AssetTagger.load(real_path)
        # Spot check
        assert "BTC" in t.tag("bitcoin rallies")
        assert "MACRO:FOMC" in t.tag("FOMC rate decision")


# ── score.py ──────────────────────────────────────────────────────────────────


def test_score_fed_source_is_3():
    item = _news_item(source_id="fed_press")
    assert importance_score(item) == 3


def test_score_bls_source_is_3():
    item = _news_item(source_id="bls_releases")
    assert importance_score(item) == 3


def test_score_fomc_keyword_is_3():
    item = _news_item(source_id="coindesk", headline="FOMC holds rates steady at 5.25%")
    assert importance_score(item) == 3


def test_score_rate_hike_keyword_is_3():
    item = _news_item(source_id="coindesk", headline="Fed delivers surprise rate hike of 25bp")
    assert importance_score(item) == 3


def test_score_bitcoin_keyword_is_2():
    item = _news_item(source_id="cointelegraph", headline="Bitcoin breaks $90k resistance")
    assert importance_score(item) == 2


def test_score_hack_keyword_is_2():
    item = _news_item(source_id="decrypt", headline="DeFi protocol suffers $50M hack")
    assert importance_score(item) == 2


def test_score_macro_etf_tag_is_2():
    item = _news_item(
        source_id="theblock", headline="Spot fund gains traction", assets=["MACRO:ETF"]
    )
    assert importance_score(item) == 2


def test_score_default_is_1():
    item = _news_item(source_id="cointelegraph", headline="Weekly roundup: market movers")
    assert importance_score(item) == 1


def test_no_op_impact_scorer_returns_item():
    scorer = NoOpImpactScorer()
    item = _news_item()
    result = scorer.score_impact(item)
    assert result is item


# ── harvester + pipeline (no live network) ────────────────────────────────────


@pytest.fixture
def fake_feed() -> dict:
    """Synthetic feedparser-style result — no published_parsed so no staleness check."""
    return _parsed_feed(
        [
            _entry(
                title="Bitcoin ETF approved by SEC",
                link="https://coindesk.com/btc-etf",
                published_parsed=None,
            ),
            _entry(
                title="Ethereum upgrade goes live",
                link="https://coindesk.com/eth-upgrade",
                published_parsed=None,
            ),
        ]
    )


async def test_harvester_normalize_returns_news_items(fake_feed):
    from argus.pillars.news.harvesters import NewsRssHarvester

    card = _card("coindesk")
    sink = MemorySink()
    harvester = NewsRssHarvester(card, sink)

    items = list(harvester.normalize([fake_feed]))
    assert len(items) == 2
    assert all(isinstance(i, NewsItem) for i in items)
    assert all(i.source_id == "coindesk" for i in items)


async def test_harvester_extract_calls_feed(fake_feed):
    from argus.pillars.news.harvesters import NewsRssHarvester

    card = _card("coindesk")
    sink = MemorySink()
    harvester = NewsRssHarvester(card, sink)

    with patch.object(harvester, "fetch_feed", new=AsyncMock(return_value=fake_feed)):
        raw = await harvester.extract()

    assert len(raw) == 1  # one feed configured


async def test_pipeline_run_cards_writes_to_sink(fake_feed, tmp_path):
    from argus.pillars.news.pipeline import NewsPipeline

    aliases = tmp_path / "aliases.yaml"
    aliases.write_text("BTC:\n  - bitcoin\n  - btc\nMACRO:SEC:\n  - sec\n")

    pipeline = NewsPipeline.create(aliases_path=aliases)
    sink = MemorySink()
    card = _card("coindesk")

    from argus.pillars.news.harvesters import NewsRssHarvester

    async def fake_extract(self_):
        return [fake_feed]

    with patch.object(NewsRssHarvester, "fetch_feed", new=AsyncMock(return_value=fake_feed)):
        n = await pipeline.run_cards([card], sink)

    assert n > 0
    rows = sink.read("news")
    assert len(rows) == n
    # All rows should have dedup_hash set
    assert all(r["dedup_hash"] != "" for r in rows)


def test_pipeline_dedup_across_sources():
    """Same headline from two sources → one row with corroboration."""
    ts = _FETCHED - timedelta(minutes=2)
    item_a = _news_item(
        source_id="coindesk", headline="Bitcoin ETF approved by SEC", published_ts=ts
    )
    item_b = _news_item(
        source_id="theblock", headline="Bitcoin ETF Approved By SEC", published_ts=ts
    )

    deduped = deduplicate([item_a, item_b])
    assert len(deduped) == 1
    assert "theblock" in deduped[0].corroborations


async def test_pipeline_blocked_source_skipped(tmp_path):
    """A BLOCKED source card is skipped without error."""
    from argus.pillars.news.pipeline import NewsPipeline

    aliases = tmp_path / "aliases.yaml"
    aliases.write_text("BTC:\n  - bitcoin\n")
    pipeline = NewsPipeline.create(aliases_path=aliases)
    sink = MemorySink()

    blocked_card = SourceCard(
        id="blocked_source",
        name="Blocked",
        url="https://example.com",
        pillar="news",
        tier=0,
        status="BLOCKED",
        rss_feeds=[RssFeed(url="https://example.com/rss")],
    )
    n = await pipeline.run_cards([blocked_card], sink)
    assert n == 0


# ── Source Card loading ───────────────────────────────────────────────────────


def test_all_news_source_cards_load():
    """Every YAML in sources/news/ must parse without error."""
    from argus.core.source_card import load

    cards_dir = Path("sources/news")
    yaml_files = [p for p in cards_dir.glob("*.yaml") if not p.name.startswith("_")]
    assert yaml_files, "No source cards found in sources/news/"

    for p in yaml_files:
        card = load(p)
        assert card.pillar == "news"
        assert 0 <= card.tier <= 6


def test_all_news_source_cards_have_rss_feeds():
    """All Tier-0 news cards must have at least one rss_feed configured."""
    from argus.core.source_card import load_all

    cards = load_all(pillar="news")
    tier0 = [c for c in cards if c.tier == 0]
    assert tier0, "No Tier-0 news source cards found"
    for card in tier0:
        assert card.rss_feeds, f"{card.id} is Tier-0 but has no rss_feeds"
