"""
Asset tagger — maps headline + body to asset tags via db/asset_aliases.yaml.

Pluggable: swap _tag_impl with a model-backed tagger without changing the pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_ALIASES_PATH = Path("db/asset_aliases.yaml")


class AssetTagger:
    """Keyword-based asset tagger loaded from a YAML alias map."""

    def __init__(self, aliases: dict[str, list[str]]) -> None:
        # Pre-compile: tag → list of compiled patterns
        self._patterns: list[tuple[str, re.Pattern[str]]] = []
        for tag, keywords in aliases.items():
            for kw in keywords:
                pat = re.compile(r"\b" + re.escape(kw.lower()) + r"\b")
                self._patterns.append((tag, pat))

    @classmethod
    def load(cls, path: Path | str = _DEFAULT_ALIASES_PATH) -> AssetTagger:
        raw: dict[str, Any] = yaml.safe_load(Path(path).read_text())
        aliases: dict[str, list[str]] = {}
        for tag, kws in raw.items():
            aliases[tag] = [str(k) for k in (kws or [])]
        return cls(aliases)

    def tag(self, headline: str, body: str | None = None) -> list[str]:
        """Return sorted deduplicated asset tags matched in headline + body."""
        text = (headline + " " + (body or "")).lower()
        matched: set[str] = set()
        for tag, pat in self._patterns:
            if pat.search(text):
                matched.add(tag)
        return sorted(matched)
