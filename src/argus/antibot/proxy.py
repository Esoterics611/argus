"""
Proxy pool management — per-context residential proxy rotation with per-domain stickiness.

LEGAL LINE: proxies are used to avoid IP-reputation blocking of PUBLIC pages only.
This module contains no CAPTCHA solving, login defeat, or paywall bypass.
"""

from __future__ import annotations

import hashlib
import os
import random
from urllib.parse import urlparse

import structlog

log = structlog.get_logger()

# Env var for the residential proxy pool endpoint.
# Format: http://user:pass@gateway.provider.com:PORT
# The gateway distributes requests across the residential pool.
_POOL_ENV = "PROXY_POOL_URL"

# Per-domain sticky assignment: domain → proxy dict
_domain_sticky: dict[str, dict[str, str]] = {}


def get_proxy_for_context(url: str, force_new: bool = False) -> dict[str, str] | None:
    """
    Return a Playwright-compatible proxy dict for *url*, or None if no pool configured.

    Per-domain stickiness: the same exit IP is reused for all requests to a domain
    within one harvest cycle.  Pass force_new=True on 407/403 to rotate.

    The proxy dict format Playwright expects:
        {"server": "http://host:port", "username": "...", "password": "..."}
    """
    pool_url = os.getenv(_POOL_ENV, "")
    if not pool_url:
        return None

    domain = _domain_of(url)

    if not force_new and domain in _domain_sticky:
        return _domain_sticky[domain]

    proxy = _build_proxy(pool_url, domain)
    _domain_sticky[domain] = proxy
    log.debug("proxy.assigned", domain=domain, server=proxy["server"])
    return proxy


def rotate_proxy(url: str) -> dict[str, str] | None:
    """Force a new proxy assignment for *url*'s domain. Call on 407/403."""
    log.info("proxy.rotating", domain=_domain_of(url))
    return get_proxy_for_context(url, force_new=True)


def clear_sticky() -> None:
    """Clear all sticky assignments. Call between harvest cycles."""
    _domain_sticky.clear()


def _domain_of(url: str) -> str:
    return urlparse(url).netloc


def _build_proxy(pool_url: str, domain: str) -> dict[str, str]:
    """
    Build a Playwright proxy dict from the pool URL.

    Many residential providers support session-pinning via a username suffix like
    user-session-XXXX:pass@gateway, which makes the gateway route through a stable exit.
    We embed a deterministic-but-rotating token derived from domain + a random salt
    so the same domain always hits the same exit for one harvest run.
    """
    parsed = urlparse(pool_url)
    # Generate a short session token: hash(domain + random_salt)[:8]
    salt = str(random.randint(0, 999999))
    token = hashlib.sha256(f"{domain}{salt}".encode()).hexdigest()[:8]

    username = parsed.username or ""
    password = parsed.password or ""

    # Append session token if the provider supports it (no-op if they don't)
    if username:
        username = f"{username}-session-{token}"

    server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 80}"
    return {"server": server, "username": username, "password": password}
