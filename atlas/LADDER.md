# Extraction Strategy Ladder

Given any target, the engine descends until something works — **cheapest first, brute force last**.
This abstraction is what makes Argus a *system* and not 200 brittle scrapers.

```
TIER 0  Public API / RSS / Atom   → ingest direct, NO browser. Record in Source Card.
                                     (The registry becomes an API map of the financial internet.)

TIER 1  Hidden JSON / GraphQL     → Cartographer sniffs every XHR/fetch the SPA fires, classifies
                                     data endpoints, replays them with browser-acquired cookies/headers
                                     (or curl_cffi for JA3-matched replay at scale). ← top leverage

TIER 2  Embedded state            → data already in __NEXT_DATA__ / window.__INITIAL_STATE__ /
                                     Redux / Apollo cache. page.evaluate() lifts it whole.

TIER 3  WebSocket stream          → tap live frames (page.on("websocket") → ws.on("framereceived")).

TIER 4  Rendered DOM              → classic scrape: virtualized tables, infinite scroll, pagination.

TIER 5  Canvas / visual only      → no export, data is pixels. Hook the chart lib's internal series
                                     in JS, or harvest tooltips, or screenshot→OCR as last resort.

TIER 6  Defended                  → anti-bot evasion layered on whichever tier above:
                                     stealth fingerprint + residential IP + human cadence.
```

## Binding rules

1. **The Cartographer runs first on every new source.** Never hand-write a Tier-4 DOM scraper before
   proving no Tier-0/1/2/3 path exists.

2. **Sources self-heal by falling DOWN the ladder.** When a tier breaks (Tier-1 endpoint killed →
   Tier-3 WS → Tier-4 DOM), the ladder module tries the next tier automatically and emits a
   `DEGRADED` note to the Source Card. The pillar code never changes.

3. **Tier 0 is always tried first, even for "obviously" browser-only sites.** Surprising how often a
   React SPA exposes an RSS feed nobody documents.

4. **Record the winning tier in the Source Card.** The tier field is authoritative; harvesters
   read it and dispatch accordingly.

5. **Never combine conflicting stealth tools.** Pick the lowest rung on the evasion ladder that
   passes the Fingerprint Lab for this target. Do not stack playwright-stealth on top of patchright.
