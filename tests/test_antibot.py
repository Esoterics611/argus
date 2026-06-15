"""
Tests for src/argus/antibot/ — rung selection, proxy rotation, public-surface contract.
No live network.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from argus.antibot.proxy import _domain_of, clear_sticky, get_proxy_for_context
from argus.antibot.rung import (
    RUNG_ORDER,
    _rung_from_lab,
    maximum_rung,
    minimum_rung,
    select_rung,
)
from argus.core.source_card import Defenses, SourceCard

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _card(vendor: str = "cloudflare", evasion_rung: str = "vanilla") -> SourceCard:
    return SourceCard(
        id="test_source",
        name="Test",
        url="https://www.coinglass.com/FundingRate",
        pillar="derivs",
        tier=1,
        defenses=Defenses(vendor=vendor, evasion_rung=evasion_rung),  # type: ignore[arg-type]
    )


# ── select_rung ───────────────────────────────────────────────────────────────


def test_select_rung_explicit_override():
    """If the card has an explicit evasion_rung != vanilla, that wins."""
    card = _card(vendor="cloudflare", evasion_rung="camoufox")
    assert select_rung(card) == "camoufox"


def test_select_rung_cloudflare_default_no_lab():
    """Without lab results, cloudflare defaults to patchright."""
    card = _card(vendor="cloudflare", evasion_rung="vanilla")
    with patch("argus.antibot.rung._load_fp_results", return_value={}):
        rung = select_rung(card)
    assert rung == "patchright"


def test_select_rung_none_vendor_default_no_lab():
    """No defenses → vanilla is sufficient."""
    card = _card(vendor="none", evasion_rung="vanilla")
    with patch("argus.antibot.rung._load_fp_results", return_value={}):
        rung = select_rung(card)
    assert rung == "vanilla"


def test_select_rung_uses_lab_results_for_cloudflare(tmp_path, monkeypatch):
    """
    When lab results exist showing patchright PASSES for cloudflare,
    select_rung returns 'patchright' (lowest passing rung).
    """
    lab_data = {
        "cloudflare": {
            "vanilla": {"passed": False, "score": 0.0},
            "stealth": {"passed": False, "score": 0.1},
            "patchright": {"passed": True, "score": 0.8},
            "camoufox": {"passed": True, "score": 0.95},
        }
    }
    fp_path = tmp_path / "sources" / "_fingerprint_results.json"
    fp_path.parent.mkdir(parents=True)
    fp_path.write_text(json.dumps(lab_data))

    with patch("argus.antibot.rung._FP_RESULTS_PATH", fp_path):
        card = _card(vendor="cloudflare", evasion_rung="vanilla")
        rung = select_rung(card)

    assert rung == "patchright", f"Expected patchright (lowest passing), got {rung}"


def test_select_rung_uses_lab_stealth_for_akamai(tmp_path):
    """stealth is sufficient for akamai per lab results — don't escalate unnecessarily."""
    lab_data = {
        "akamai": {
            "vanilla": {"passed": False, "score": 0.05},
            "stealth": {"passed": True, "score": 0.7},
            "patchright": {"passed": True, "score": 0.9},
        }
    }
    fp_path = tmp_path / "sources" / "_fingerprint_results.json"
    fp_path.parent.mkdir(parents=True)
    fp_path.write_text(json.dumps(lab_data))

    with patch("argus.antibot.rung._FP_RESULTS_PATH", fp_path):
        card = _card(vendor="akamai", evasion_rung="vanilla")
        rung = select_rung(card)

    assert rung == "stealth"


def test_rung_from_lab_returns_lowest_passing():
    results = {
        "vanilla": {"passed": False},
        "stealth": {"passed": False},
        "patchright": {"passed": True},
        "camoufox": {"passed": True},
    }
    assert _rung_from_lab("cloudflare", results) == "patchright"


def test_rung_from_lab_returns_camoufox_when_nothing_passes():
    results = {
        "vanilla": {"passed": False},
        "stealth": {"passed": False},
        "patchright": {"passed": False},
        "camoufox": {"passed": False},
    }
    assert _rung_from_lab("cloudflare", results) == "camoufox"


def test_minimum_rung():
    assert minimum_rung("vanilla", "patchright") == "vanilla"
    assert minimum_rung("camoufox", "stealth") == "stealth"


def test_maximum_rung():
    assert maximum_rung("vanilla", "patchright") == "patchright"
    assert maximum_rung("camoufox", "stealth") == "camoufox"


def test_rung_order_is_ascending():
    """RUNG_ORDER must go from cheapest to most expensive."""
    assert RUNG_ORDER == ["vanilla", "stealth", "patchright", "camoufox"]


# ── Proxy rotation ────────────────────────────────────────────────────────────


def test_get_proxy_returns_none_without_env(monkeypatch):
    monkeypatch.delenv("PROXY_POOL_URL", raising=False)
    clear_sticky()
    result = get_proxy_for_context("https://www.coinglass.com/")
    assert result is None


def test_get_proxy_returns_dict_with_env(monkeypatch):
    monkeypatch.setenv("PROXY_POOL_URL", "http://user:secret@proxy.example.com:8080")
    clear_sticky()
    result = get_proxy_for_context("https://www.coinglass.com/")
    assert result is not None
    assert "server" in result
    assert "proxy.example.com" in result["server"]


def test_proxy_per_domain_stickiness(monkeypatch):
    """Two calls for the same domain return the same proxy object."""
    monkeypatch.setenv("PROXY_POOL_URL", "http://user:secret@proxy.example.com:8080")
    clear_sticky()
    p1 = get_proxy_for_context("https://www.coinglass.com/funding")
    p2 = get_proxy_for_context("https://www.coinglass.com/liquidation")
    assert p1 == p2


def test_proxy_distinct_across_domains(monkeypatch):
    """Different domains get independently assigned proxies (may differ in session token)."""
    monkeypatch.setenv("PROXY_POOL_URL", "http://user:secret@proxy.example.com:8080")
    clear_sticky()
    p1 = get_proxy_for_context("https://www.coinglass.com/")
    p2 = get_proxy_for_context("https://www.forexfactory.com/")
    # Same server (one pool gateway) but different session tokens in the username
    assert p1 is not None and p2 is not None
    assert _domain_of("https://www.coinglass.com/") != _domain_of("https://www.forexfactory.com/")
    # They must have different usernames (different session tokens)
    assert p1.get("username") != p2.get("username")


def test_domain_of():
    assert _domain_of("https://www.coinglass.com/funding?symbol=BTC") == "www.coinglass.com"
    assert _domain_of("https://api.example.com/v1/data") == "api.example.com"


# ── HARD CONSTRAINT: no CAPTCHA / login / paywall code paths ─────────────────


def test_no_captcha_solver_in_public_surface():
    """
    The antibot module must NOT export any CAPTCHA-solving, login-defeat,
    or paywall-bypass functionality.  This test documents and enforces the legal line.
    """
    import argus.antibot as ab
    import argus.antibot.cadence as cadence_mod
    import argus.antibot.fingerprint_lab as fp_mod
    import argus.antibot.proxy as proxy_mod
    import argus.antibot.rung as rung_mod

    forbidden_names = {
        "captcha",
        "recaptcha",
        "hcaptcha",
        "solvecaptcha",
        "solve_captcha",
        "bypass_login",
        "login_defeat",
        "paywall",
        "bypass_paywall",
        "crack",
    }

    for mod in (ab, cadence_mod, fp_mod, proxy_mod, rung_mod):
        public_names = {n.lower() for n in dir(mod) if not n.startswith("_")}
        overlap = public_names & forbidden_names
        assert not overlap, (
            f"Module {mod.__name__} exposes forbidden names: {overlap}. "
            "The anti-bot module must NEVER contain CAPTCHA solving, "
            "login defeat, or paywall bypass."
        )


def test_no_forbidden_strings_in_source():
    """Source files must not contain CAPTCHA-solving or login-defeat implementation."""
    antibot_dir = Path("src/argus/antibot")
    forbidden = ["solve_captcha", "bypass_login", "defeat_paywall", "two_factor"]
    for py_file in antibot_dir.glob("*.py"):
        source = py_file.read_text().lower()
        for term in forbidden:
            assert term not in source, (
                f"{py_file.name} contains forbidden term '{term}'. " "Legal line: public data only."
            )
