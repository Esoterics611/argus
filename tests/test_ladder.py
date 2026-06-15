"""Tests for ladder tier selection and fall-down logic."""

import pytest

from argus.core.ladder import run_with_falldown, select_tier
from argus.core.source_card import SourceCard


def _card(tier: int = 1) -> SourceCard:
    return SourceCard(
        id="test_source",
        name="Test",
        url="https://example.com",
        pillar="news",
        tier=tier,
    )


def test_select_tier_returns_card_tier():
    card = _card(tier=3)
    assert select_tier(card) == 3


async def test_ladder_succeeds_on_first_try():
    card = _card(tier=1)
    calls: list[int] = []

    async def tier1():
        calls.append(1)
        return {"data": "ok"}

    winning_tier, result = await run_with_falldown(card, {1: tier1})
    assert winning_tier == 1
    assert result == {"data": "ok"}
    assert calls == [1]


async def test_ladder_falls_down_on_failure(tmp_path, monkeypatch):
    card = _card(tier=1)

    # Prevent save() from touching the sources/ dir
    monkeypatch.setattr("argus.core.ladder.save", lambda c: None)

    async def tier1():
        raise ConnectionError("endpoint gone")

    async def tier4():
        return {"data": "dom"}

    winning_tier, result = await run_with_falldown(card, {1: tier1, 4: tier4})
    assert winning_tier == 4
    assert result == {"data": "dom"}
    assert card.status == "DEGRADED"


async def test_ladder_raises_when_all_tiers_exhausted(monkeypatch):
    card = _card(tier=1)
    monkeypatch.setattr("argus.core.ladder.save", lambda c: None)

    async def fail():
        raise RuntimeError("always fails")

    with pytest.raises(RuntimeError, match="All tiers exhausted"):
        await run_with_falldown(card, {1: fail, 4: fail})


async def test_ladder_falldown_calls_on_degraded_callback(monkeypatch):
    card = _card(tier=1)
    monkeypatch.setattr("argus.core.ladder.save", lambda c: None)

    degraded_calls: list[tuple] = []

    async def tier1():
        raise ConnectionError("gone")

    async def tier4():
        return "ok"

    await run_with_falldown(
        card,
        {1: tier1, 4: tier4},
        on_degraded=lambda c, t: degraded_calls.append((c.id, t)),
    )
    assert degraded_calls == [("test_source", 4)]
