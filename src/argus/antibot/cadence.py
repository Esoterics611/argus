"""
Human-cadence helpers — randomised delays, mouse movement, scroll.

All delays use asyncio (page.wait_for_timeout / asyncio.sleep).
NEVER use time.sleep — that blocks the event loop.

LEGAL LINE: cadence humanisation is used for public pages only to avoid
triggering behavioural bot-detection.  No CAPTCHA solving or login defeat.
"""

from __future__ import annotations

import asyncio
import random

from playwright.async_api import Page

# ── Delay primitives ─────────────────────────────────────────────────────────


async def short_pause(page: Page, base_ms: int = 300, jitter_ms: int = 200) -> None:
    """Brief inter-action pause (e.g. between clicks)."""
    delay = base_ms + random.randint(0, jitter_ms)
    await page.wait_for_timeout(delay)


async def reading_pause(page: Page, base_ms: int = 1200, jitter_ms: int = 800) -> None:
    """Simulate a human reading the page before the next action."""
    delay = base_ms + random.randint(0, jitter_ms)
    await page.wait_for_timeout(delay)


async def think_pause(base_ms: int = 500, jitter_ms: int = 400) -> None:
    """
    Pause outside a Page context (e.g. between context creation and navigation).
    Uses asyncio.sleep — acceptable here since we are not inside a browser event loop.
    """
    delay = (base_ms + random.randint(0, jitter_ms)) / 1000
    await asyncio.sleep(delay)


# ── Mouse helpers ─────────────────────────────────────────────────────────────


async def human_move_to(page: Page, x: int, y: int, steps: int = 8) -> None:
    """
    Move the mouse to (x, y) with intermediate waypoints and jitter.
    Avoids the instant teleport that bot detectors flag.
    """
    current = await page.evaluate("() => ({x: window.__argus_mx||0, y: window.__argus_my||0})")
    cx, cy = current.get("x", 0), current.get("y", 0)

    for i in range(1, steps + 1):
        t = i / steps
        # Ease-in-out lerp with small perpendicular jitter
        nx = int(cx + (x - cx) * t + random.randint(-3, 3))
        ny = int(cy + (y - cy) * t + random.randint(-3, 3))
        await page.mouse.move(nx, ny)
        await page.wait_for_timeout(random.randint(10, 30))

    # Track position for next call
    await page.evaluate(f"() => {{ window.__argus_mx={x}; window.__argus_my={y}; }}")


async def human_click(page: Page, selector: str) -> None:
    """Locate element, move mouse to it naturally, then click."""
    element = page.locator(selector).first
    box = await element.bounding_box()
    if box:
        # Click somewhere within the element, not always dead-centre
        tx = int(box["x"] + box["width"] * random.uniform(0.3, 0.7))
        ty = int(box["y"] + box["height"] * random.uniform(0.3, 0.7))
        await human_move_to(page, tx, ty)
        await short_pause(page, base_ms=80, jitter_ms=120)
    await element.click()


# ── Scroll helpers ────────────────────────────────────────────────────────────


async def human_scroll(
    page: Page,
    distance_px: int = 600,
    steps: int = 5,
    direction: str = "down",
) -> None:
    """
    Scroll in increments with jitter, mimicking human wheel behaviour.
    direction: "down" | "up"
    """
    sign = 1 if direction == "down" else -1
    per_step = (distance_px // steps) * sign
    for _ in range(steps):
        jitter = random.randint(-20, 20)
        await page.evaluate(f"() => window.scrollBy(0, {per_step + jitter})")
        await page.wait_for_timeout(random.randint(60, 180))


async def scroll_to_bottom(page: Page, max_scrolls: int = 10) -> None:
    """Scroll to page bottom in human cadence, stopping early if no new content."""
    prev_height = -1
    for _ in range(max_scrolls):
        height = await page.evaluate("() => document.body.scrollHeight")
        if height == prev_height:
            break
        prev_height = height
        await human_scroll(page, distance_px=random.randint(400, 900))
        await reading_pause(page, base_ms=600, jitter_ms=400)
