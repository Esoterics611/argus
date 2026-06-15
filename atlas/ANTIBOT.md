# Anti-Bot Strategy

## The hard legal line (non-negotiable)

- **Public data only.** Coinglass, ForexFactory, and all other v1 targets are publicly viewable
  with no login. "Anti-bot" here means **fingerprint / IP / behavior normalization for public pages**,
  nothing more.
- **Honor `robots.txt` and rate limits.** Polite concurrency, exponential backoff (tenacity),
  per-domain caps. Record `robots_ok` in every Source Card.
- **NEVER** solve CAPTCHAs, defeat a login, or bypass a paywall.
  A source that requires any of these is marked `status: BLOCKED` in its Source Card and skipped —
  not cracked. The elegant techniques (find the JSON, tap the WS, liberate the canvas) are what
  make this interesting; brute force isn't the point.
- **Prefer Web Bot Auth** (Cloudflare's declared-agent protocol, 2026) on sites that opt in —
  signing in as a declared agent beats evasion every time.

## The evasion ladder

Pick the **lowest rung that passes the Fingerprint Lab** for this target. Do not stack tools.

```
RUNG 0  vanilla Playwright
        — CDP flags exposed, navigator.webdriver=true, headless tells visible
        — sufficient for Tier-0/1 on non-defended public pages

RUNG 1  playwright-stealth (JS-layer patches)
        — hides navigator.webdriver, basic canvas/WebGL normalization
        — sufficient for lightly defended public pages

RUNG 2  patchright (CDP-leak patched Chromium fork)
        — eliminates CDP-level headless signals; passes most bot-detection JS checks
        — use for Cloudflare-fronted pages that pass at Rung 2 in the Fingerprint Lab

RUNG 3  camoufox (Firefox fork, C++-level fingerprint spoofing)
        — deepest browser-level spoofing; different TLS/JA3 from Chrome
        — last rung before BLOCKED; use only when Rung 2 fails
```

## IP reputation — the real wall

A perfect fingerprint from a datacenter ASN still gets flagged. Residential proxy rotation is
required for any Tier-6 target. Rules:
- Per-context proxy assignment (not per-session).
- Per-domain stickiness: same exit IP for all requests to a domain within one harvest cycle.
- Pool URL in `PROXY_POOL_URL` env var; never in code.
- Rotate on 407/403/Cloudflare challenge (never retry same IP more than once).

## The Fingerprint Lab

`argus fingerprint [--backend vanilla|stealth|patchright|camoufox]` opens each backend against a
public fingerprint detection page and records:

- `navigator.webdriver` value
- Canvas/WebGL/Audio entropy scores
- Headless browser tells (window.chrome, permissions API, etc.)
- TLS/JA3 shape (reported by the FP page if available)
- Overall pass/fail per detection vendor

Results persisted to `sources/_fingerprint_results.json`. `select_rung()` reads this to auto-select
the minimum rung per target's `defenses.vendor`.

## BLOCKED decision tree

```
Target requires CAPTCHA solve?  → BLOCKED immediately
Target requires login?          → BLOCKED immediately
Target hides data behind paywall? → harvest headline/preview only; BLOCKED for full content
Rung 3 (camoufox) still fails?  → BLOCKED; do not escalate further
```

A BLOCKED source is a feature, not a failure — it proves the legal line held.
