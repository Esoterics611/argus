"""
Anti-bot module — rung selection, proxy rotation, human cadence, Fingerprint Lab.

LEGAL LINE (module invariant): this package normalises fingerprint/IP/behavior
for PUBLIC pages only.  It contains NO CAPTCHA solving, login bypass, or paywall
defeat.  Sources requiring those are marked status=BLOCKED and skipped.
"""

from argus.antibot.cadence import human_click, human_scroll, reading_pause, short_pause
from argus.antibot.proxy import clear_sticky, get_proxy_for_context, rotate_proxy
from argus.antibot.rung import Rung, select_rung

__all__ = [
    # Rung selection
    "select_rung",
    "Rung",
    # Proxy rotation
    "get_proxy_for_context",
    "rotate_proxy",
    "clear_sticky",
    # Human cadence
    "short_pause",
    "reading_pause",
    "human_click",
    "human_scroll",
]
