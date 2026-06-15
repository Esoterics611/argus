"""
News pipeline: harvest → normalize → dedup → tag → score → sink.

Entry point: NewsPipeline.run(cards, sink).
Each stage is independently testable; the pipeline wires them together.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from argus.core.contracts import NewsItem
from argus.core.source_card import SourceCard, load_all
from argus.pillars.news.dedup import deduplicate
from argus.pillars.news.harvesters import build_harvester
from argus.pillars.news.score import ImpactScorer, NoOpImpactScorer, importance_score
from argus.pillars.news.tag import AssetTagger
from argus.sinks.base import Sink

log = structlog.get_logger()

_ALIASES_PATH = Path("db/asset_aliases.yaml")


class NewsPipeline:
    """
    Orchestrates the full news harvest cycle across multiple sources.

    Usage:
        pipeline = NewsPipeline.create()
        n = await pipeline.run(sink)
    """

    def __init__(
        self,
        tagger: AssetTagger,
        impact_scorer: ImpactScorer | None = None,
        dedup_threshold: int = 85,
    ) -> None:
        self._tagger = tagger
        self._impact_scorer = impact_scorer or NoOpImpactScorer()
        self._dedup_threshold = dedup_threshold

    @classmethod
    def create(
        cls,
        aliases_path: Path = _ALIASES_PATH,
        impact_scorer: ImpactScorer | None = None,
        dedup_threshold: int = 85,
    ) -> NewsPipeline:
        tagger = AssetTagger.load(aliases_path)
        return cls(tagger=tagger, impact_scorer=impact_scorer, dedup_threshold=dedup_threshold)

    async def run_cards(self, cards: list[SourceCard], sink: Sink) -> int:
        """
        Run the pipeline for a specific list of Source Cards.
        Returns total rows written across all sources.
        """
        sink.ensure_schema("news", NewsItem)

        # Stage 1: Harvest all sources
        all_items: list[NewsItem] = []
        for card in cards:
            if card.status == "BLOCKED":
                log.warning("pipeline.source_blocked", source_id=card.id)
                continue
            try:
                harvester = build_harvester(card, sink)
                raw = await harvester.extract()
                items = list(harvester.normalize(raw))
                log.info("pipeline.harvested", source_id=card.id, count=len(items))
                all_items.extend(items)
            except Exception as exc:
                log.error("pipeline.harvest_failed", source_id=card.id, error=str(exc))

        if not all_items:
            log.info("pipeline.empty")
            return 0

        # Stage 2: Dedup across outlets
        deduped = deduplicate(all_items, threshold=self._dedup_threshold)
        log.info(
            "pipeline.deduped",
            before=len(all_items),
            after=len(deduped),
            merged=len(all_items) - len(deduped),
        )

        # Stage 3: Asset tagging
        for item in deduped:
            item.assets = self._tagger.tag(item.headline, item.body_snippet)

        # Stage 4: Importance scoring
        for item in deduped:
            item.importance = importance_score(item)  # type: ignore[assignment]

        # Stage 5: Impact scoring (no-op by default; MCP-backed scorer can replace)
        scored = [self._impact_scorer.score_impact(item) for item in deduped]

        # Stage 6: Sink
        n = sink.write("news", scored)
        log.info("pipeline.written", rows=n)
        return n

    async def run(self, sink: Sink, pillar: str = "news") -> int:
        """Load all enabled news Source Cards and run the pipeline."""
        cards = [c for c in load_all(pillar=pillar) if c.status != "BLOCKED"]
        return await self.run_cards(cards, sink)
