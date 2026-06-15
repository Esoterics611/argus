"""SourceCard — load, validate, and write Source Card YAML files."""

from __future__ import annotations

import contextlib
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

SOURCES_ROOT = Path("sources")


# ── Sub-models ───────────────────────────────────────────────────────────────


class DiscoveredEndpoint(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH"] = "GET"
    url_template: str
    headers_required: dict[str, str] = Field(default_factory=dict)
    auth: Literal["none", "cookie", "bearer"] = "none"
    params: dict[str, Any] = Field(default_factory=dict)
    response_path: str = ""
    data_likelihood: float = Field(default=0.0, ge=0.0, le=1.0)


class WebSocketConfig(BaseModel):
    url: str
    subscribe_msg: str = ""
    frame_path: str = ""


class StateExtraction(BaseModel):
    global_var: str = Field(alias="global", default="")
    path: str = ""

    model_config = {"populate_by_name": True}


class Defenses(BaseModel):
    vendor: Literal["cloudflare", "akamai", "datadome", "none"] = "none"
    evasion_rung: Literal["vanilla", "stealth", "patchright", "camoufox"] = "vanilla"


class RssFeed(BaseModel):
    url: str
    format: Literal["rss", "atom", "json_feed"] = "rss"


# ── SourceCard ───────────────────────────────────────────────────────────────


class SourceCard(BaseModel):
    id: str
    name: str
    url: str
    pillar: Literal["news", "derivs", "macro"]
    tier: int = Field(ge=0, le=6)
    status: Literal["LIVE", "BLOCKED", "DEGRADED"] = "LIVE"

    # Tier 0
    rss_feeds: list[RssFeed] = Field(default_factory=list)

    # Tier 1
    discovered_endpoints: list[DiscoveredEndpoint] = Field(default_factory=list)

    # Tier 3
    websocket: WebSocketConfig | None = None

    # Tier 2
    state_extraction: StateExtraction | None = None

    # Tier 5
    canvas_strategy: Literal["chart_hook", "tooltip_walk", "ocr", "none"] | None = None
    canvas_notes: str = ""

    # Defenses
    defenses: Defenses = Field(default_factory=Defenses)

    # Output
    schema_name: str = Field(alias="schema", default="")
    cadence: str = "5m"
    sink_subject: str = ""

    # Compliance
    robots_ok: bool | None = None
    terms_note: str = ""

    # Provenance
    last_verified_ts: datetime | None = None
    har_path: str = ""
    trace_path: str = ""
    notes: str = ""

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _check_tier_has_config(self) -> SourceCard:
        if self.tier == 0 and not self.rss_feeds and not self.discovered_endpoints:
            pass  # Tier-0 cards may be written before feeds are discovered
        return self


def load(path: Path | str) -> SourceCard:
    """Load and validate a Source Card from a YAML file."""
    p = Path(path)
    raw = yaml.safe_load(p.read_text())
    return SourceCard.model_validate(raw)


def save(card: SourceCard, path: Path | str | None = None) -> Path:
    """Write a Source Card to YAML. Defaults to sources/<pillar>/<id>.yaml."""
    if path is None:
        path = SOURCES_ROOT / card.pillar / f"{card.id}.yaml"
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = card.model_dump(by_alias=True, exclude_none=True)
    p.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    return p


def load_all(pillar: str | None = None) -> list[SourceCard]:
    """Load all Source Cards, optionally filtered by pillar."""
    root = SOURCES_ROOT
    pattern = f"{pillar}/*.yaml" if pillar else "*/*.yaml"
    cards = []
    for p in sorted(root.glob(pattern)):
        if "cartograph" in p.name or "_fingerprint" in p.name:
            continue
        with contextlib.suppress(Exception):
            cards.append(load(p))
    return cards
