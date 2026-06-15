"""
Rung selection — pick the LOWEST evasion rung that passes for a given source.

LEGAL LINE (enforced here): this module normalises fingerprint/IP/behavior for
PUBLIC pages ONLY.  It does NOT contain and MUST NOT be extended to contain any
CAPTCHA solver, login bypass, or paywall defeat.  Sources requiring those are
marked status=BLOCKED by the caller and skipped entirely.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from argus.core.source_card import SourceCard

# Canonical rung names in ascending cost order
Rung = Literal["vanilla", "stealth", "patchright", "camoufox"]
RUNG_ORDER: list[Rung] = ["vanilla", "stealth", "patchright", "camoufox"]

_FP_RESULTS_PATH = Path("sources/_fingerprint_results.json")

# Default minimum rung per defense vendor when no Fingerprint Lab data exists.
# These are conservative starting points — the Lab refines them.
_VENDOR_DEFAULT_RUNG: dict[str, Rung] = {
    "none": "vanilla",
    "cloudflare": "patchright",  # Cloudflare's bot score requires at least CDP-patching
    "akamai": "stealth",
    "datadome": "patchright",
}


def select_rung(card: SourceCard) -> Rung:
    """
    Return the lowest evasion rung expected to pass for *card*.

    Decision order:
    1. Card's evasion_rung field (explicitly set by the operator after Lab run).
    2. Fingerprint Lab results for the card's vendor.
    3. Conservative vendor default.

    NEVER returns a rung that implies CAPTCHA solving, login, or paywall bypass —
    those code paths do not exist in this module.
    """
    # Explicit override wins
    explicit: Rung = card.defenses.evasion_rung  # type: ignore[assignment]
    if explicit and explicit != "vanilla":
        # Still respect it, but log that the card has been manually set
        return explicit

    vendor = card.defenses.vendor

    # Check Fingerprint Lab results
    lab_results = _load_fp_results()
    if vendor in lab_results:
        return _rung_from_lab(vendor, lab_results[vendor])

    return _VENDOR_DEFAULT_RUNG.get(vendor, "vanilla")


def minimum_rung(a: Rung, b: Rung) -> Rung:
    """Return whichever rung is lower (cheaper) on the evasion ladder."""
    return a if RUNG_ORDER.index(a) <= RUNG_ORDER.index(b) else b


def maximum_rung(a: Rung, b: Rung) -> Rung:
    """Return whichever rung is higher (stronger) on the evasion ladder."""
    return a if RUNG_ORDER.index(a) >= RUNG_ORDER.index(b) else b


def _rung_from_lab(vendor: str, vendor_results: dict) -> Rung:
    """
    Given lab results for a vendor, return the lowest rung that PASSED.
    Format: {rung_name: {"passed": bool, "score": float}}.
    """
    for rung in RUNG_ORDER:
        result = vendor_results.get(rung, {})
        if result.get("passed", False):
            return rung  # type: ignore[return-value]
    # Nothing passed — return the strongest rung; caller may mark BLOCKED
    return "camoufox"


def _load_fp_results() -> dict:
    """Load persisted Fingerprint Lab results. Returns {} if file absent."""
    if not _FP_RESULTS_PATH.exists():
        return {}
    try:
        return json.loads(_FP_RESULTS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
