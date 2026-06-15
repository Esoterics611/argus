"""Tier selection and fall-down logic."""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from argus.core.source_card import SourceCard, save

log = structlog.get_logger()

# Ordered list of tiers from cheapest to most expensive
TIER_ORDER = [0, 1, 2, 3, 4, 5, 6]


def select_tier(card: SourceCard) -> int:
    """Return the tier declared on the card."""
    return card.tier


async def run_with_falldown(
    card: SourceCard,
    extract_fns: dict[int, Callable[[], Awaitable[Any]]],
    on_degraded: Callable[[SourceCard, int], None] | None = None,
) -> tuple[int, Any]:
    """
    Try extract_fns[card.tier]; on failure, descend to the next available tier.
    Returns (winning_tier, raw_result).
    Updates card.status to DEGRADED and persists the card if a falldown occurs.
    """
    start_idx = TIER_ORDER.index(card.tier) if card.tier in TIER_ORDER else 0
    tiers_to_try = [t for t in TIER_ORDER[start_idx:] if t in extract_fns]

    last_exc: Exception | None = None
    for tier in tiers_to_try:
        try:
            log.info("ladder.trying", source=card.id, tier=tier)
            result = await extract_fns[tier]()
            if tier != card.tier:
                # Fell down — mark DEGRADED
                log.warning("ladder.falldown", source=card.id, from_tier=card.tier, to_tier=tier)
                card.status = "DEGRADED"
                card.notes = (
                    f"{card.notes}\nDEGRADED: fell from tier {card.tier} to {tier}."
                ).strip()
                if on_degraded:
                    on_degraded(card, tier)
                with contextlib.suppress(Exception):
                    save(card)
            return tier, result
        except Exception as exc:
            log.warning("ladder.tier_failed", source=card.id, tier=tier, error=str(exc))
            last_exc = exc

    raise RuntimeError(
        f"All tiers exhausted for source '{card.id}'. Last error: {last_exc}"
    ) from last_exc
