"""Tests for SourceCard load / validate / reject-malformed."""

from pathlib import Path

import pytest
import yaml

from argus.core.source_card import SourceCard, load, save


def _write_card(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "card.yaml"
    p.write_text(yaml.dump(data))
    return p


# ── Valid card round-trips ────────────────────────────────────────────────────


def test_load_minimal_valid_card(tmp_path):
    data = {
        "id": "fed_press",
        "name": "Federal Reserve Press Releases",
        "url": "https://www.federalreserve.gov/feeds/press_all.htm",
        "pillar": "news",
        "tier": 0,
        "status": "LIVE",
        "robots_ok": True,
    }
    p = _write_card(tmp_path, data)
    card = load(p)
    assert card.id == "fed_press"
    assert card.pillar == "news"
    assert card.tier == 0
    assert card.status == "LIVE"


def test_load_card_with_endpoints(tmp_path):
    data = {
        "id": "coinglass_funding",
        "name": "Coinglass Funding Rates",
        "url": "https://www.coinglass.com/FundingRate",
        "pillar": "derivs",
        "tier": 1,
        "status": "LIVE",
        "discovered_endpoints": [
            {
                "method": "GET",
                "url_template": "https://fapi.coinglass.com/api/fundingRate",
                "headers_required": {"Referer": "https://www.coinglass.com/"},
                "auth": "none",
                "response_path": "data.list",
                "data_likelihood": 0.95,
            }
        ],
        "defenses": {"vendor": "cloudflare", "evasion_rung": "patchright"},
    }
    p = _write_card(tmp_path, data)
    card = load(p)
    assert card.tier == 1
    assert len(card.discovered_endpoints) == 1
    assert card.discovered_endpoints[0].data_likelihood == 0.95
    assert card.defenses.vendor == "cloudflare"
    assert card.defenses.evasion_rung == "patchright"


def test_save_and_reload(tmp_path):
    card = SourceCard(
        id="test_source",
        name="Test Source",
        url="https://example.com",
        pillar="news",
        tier=0,
    )
    out = save(card, tmp_path / "test_source.yaml")
    reloaded = load(out)
    assert reloaded.id == "test_source"
    assert reloaded.tier == 0


# ── Validation errors ────────────────────────────────────────────────────────


def test_reject_missing_required_fields(tmp_path):
    from pydantic import ValidationError

    data = {"id": "broken"}  # missing name, url, pillar, tier
    p = _write_card(tmp_path, data)
    with pytest.raises(ValidationError):
        load(p)


def test_reject_invalid_pillar(tmp_path):
    from pydantic import ValidationError

    data = {
        "id": "x",
        "name": "X",
        "url": "https://x.com",
        "pillar": "INVALID",
        "tier": 0,
    }
    p = _write_card(tmp_path, data)
    with pytest.raises(ValidationError):
        load(p)


def test_reject_tier_out_of_range(tmp_path):
    from pydantic import ValidationError

    data = {
        "id": "x",
        "name": "X",
        "url": "https://x.com",
        "pillar": "news",
        "tier": 99,
    }
    p = _write_card(tmp_path, data)
    with pytest.raises(ValidationError):
        load(p)


def test_reject_invalid_status(tmp_path):
    from pydantic import ValidationError

    data = {
        "id": "x",
        "name": "X",
        "url": "https://x.com",
        "pillar": "news",
        "tier": 0,
        "status": "UNKNOWN",
    }
    p = _write_card(tmp_path, data)
    with pytest.raises(ValidationError):
        load(p)
