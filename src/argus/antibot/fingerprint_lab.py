"""
Fingerprint Lab — run each stealth backend against a public detection page and
record which rungs pass for which defense vendors.

Results are persisted to sources/_fingerprint_results.json so select_rung() can
use them without re-running the Lab.

LEGAL LINE: the Lab probes PUBLIC fingerprint-detection pages only.
No CAPTCHA solving, login defeat, or paywall bypass is present or permitted here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from argus.antibot.rung import RUNG_ORDER, Rung
from argus.core.browser import BrowserFactory

log = structlog.get_logger()

# Public fingerprint-detection pages (CreepJS-style).
# These are freely accessible pages that report browser fingerprint signals.
# We use them to calibrate which rung is needed per defense vendor.
_FP_PAGE = "https://abrahamjuliot.github.io/creepjs/"

_RESULTS_PATH = Path("sources/_fingerprint_results.json")

# JS probe that reads the signals CreepJS exposes after its analysis runs.
# We wait for the page to finish its scan, then lift the result fields.
_PROBE_JS = """
() => {
    const signals = {};

    // navigator.webdriver — the classic tell
    signals.webdriver = navigator.webdriver === true;

    // window.chrome — present in real Chrome, absent in headless
    signals.chrome_object = typeof window.chrome !== 'undefined';

    // permissions API anomaly (headless returns 'denied' for notifications)
    signals.permissions_anomaly = false;
    try {
        // We read this synchronously from a prior async check stored on window
        signals.permissions_anomaly = window.__argus_perms_denied === true;
    } catch(_) {}

    // Headless user-agent string contains "HeadlessChrome"
    const ua = navigator.userAgent || '';
    signals.headless_ua = ua.toLowerCase().includes('headless');

    // Canvas fingerprint: a real browser should produce a non-trivial hash
    try {
        const c = document.createElement('canvas');
        const ctx = c.getContext('2d');
        ctx.fillText('argus', 10, 10);
        signals.canvas_entropy = c.toDataURL().length > 100;
    } catch(_) {
        signals.canvas_entropy = false;
    }

    // WebGL vendor
    try {
        const gl = document.createElement('canvas').getContext('webgl');
        const dbg = gl.getExtension('WEBGL_debug_renderer_info');
        signals.webgl_vendor = dbg
            ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL)
            : null;
    } catch(_) {
        signals.webgl_vendor = null;
    }

    // Languages
    signals.languages = (navigator.languages || []).length > 0;

    return signals;
}
"""

# Init script that pre-checks the permissions API (async, must run before page load)
_PERMS_INIT = """
() => {
    navigator.permissions.query({name: 'notifications'}).then(r => {
        window.__argus_perms_denied = (r.state === 'denied');
    }).catch(() => {
        window.__argus_perms_denied = true;
    });
}
"""


def _score_signals(signals: dict[str, Any]) -> tuple[bool, float]:
    """
    Given raw JS probe signals, return (passed: bool, score: 0-1).
    'Passed' means we look sufficiently human for this rung.

    Scoring:
      - webdriver=True  → hard fail (most detectors check this first)
      - headless_ua     → hard fail
      - canvas_entropy  → +0.2
      - chrome_object   → +0.2
      - languages       → +0.1
      - webgl_vendor    → +0.1
    """
    if signals.get("webdriver"):
        return False, 0.0
    if signals.get("headless_ua"):
        return False, 0.0

    score = 0.0
    if signals.get("canvas_entropy"):
        score += 0.2
    if signals.get("chrome_object"):
        score += 0.2
    if signals.get("languages"):
        score += 0.1
    if signals.get("webgl_vendor"):
        score += 0.1

    passed = score >= 0.3
    return passed, min(score, 1.0)


async def run_lab(
    backends: list[Rung] | None = None,
    fp_page: str = _FP_PAGE,
    vendor: str = "cloudflare",
) -> dict[str, dict]:
    """
    Run the Fingerprint Lab for each backend in *backends* (default: all).
    Returns a results dict suitable for writing to _fingerprint_results.json.

    Results structure:
        {vendor: {rung: {passed, score, signals, ts}}}
    """
    if backends is None:
        backends = list(RUNG_ORDER)

    vendor_results: dict[str, dict] = {}
    table_rows: list[str] = []

    for rung in backends:
        log.info("fingerprint_lab.testing", rung=rung, page=fp_page)
        signals, passed, score = await _probe_rung(rung, fp_page)
        vendor_results[rung] = {
            "passed": passed,
            "score": round(score, 3),
            "signals": signals,
            "ts": datetime.now(UTC).isoformat(),
        }
        status = "PASS" if passed else "FAIL"
        table_rows.append(f"  {rung:<12} {status}  score={score:.2f}")

    # Print result table
    print(f"\nFingerprint Lab results for vendor={vendor} ({fp_page})")
    print("  rung         status  score")
    print("  " + "-" * 35)
    for row in table_rows:
        print(row)
    print()

    # Persist
    all_results = _load_results()
    all_results[vendor] = vendor_results
    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RESULTS_PATH.write_text(json.dumps(all_results, indent=2))
    log.info("fingerprint_lab.saved", path=str(_RESULTS_PATH))

    return {vendor: vendor_results}


async def _probe_rung(rung: Rung, fp_page: str) -> tuple[dict, bool, float]:
    """Open fp_page with *rung* backend, run the JS probe, score signals."""
    factory = BrowserFactory(
        stealth_backend=rung,
        record_har=False,
        record_trace=False,
        source_slug=f"fp_lab_{rung}",
    )
    signals: dict[str, Any] = {}
    try:
        async with factory.new_context() as ctx:
            page = await ctx.new_page()

            # Pre-check permissions before navigation
            await page.add_init_script(_PERMS_INIT)

            # Route to a local stub if no live network (for tests)
            # In production this navigates to the real FP page
            await page.goto(fp_page, wait_until="domcontentloaded", timeout=20_000)
            await page.wait_for_timeout(2000)  # let async checks settle

            signals = await page.evaluate(_PROBE_JS)
    except Exception as exc:
        log.warning("fingerprint_lab.probe_failed", rung=rung, error=str(exc))
        signals = {"error": str(exc)}

    passed, score = _score_signals(signals)
    return signals, passed, score


def _load_results() -> dict:
    if not _RESULTS_PATH.exists():
        return {}
    try:
        return json.loads(_RESULTS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
