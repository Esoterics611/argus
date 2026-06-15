# Pillar Data Specs

## Pillar 1 — Market-moving news

### Source tiers (be honest)

**Tier 0 (no browser — ingest first):** Primary movers that expose RSS/Atom feeds:
- Federal Reserve: press releases, speeches, FOMC statements
- SEC: press releases, EDGAR 8-K feed, litigation releases Atom
- US Treasury: press releases
- BLS (Bureau of Labor Statistics): release calendar + data pages
- BEA (Bureau of Economic Analysis): release pages
- ECB: press releases, monetary policy statements
- Crypto outlets with feeds: CoinDesk, Cointelegraph, Decrypt, The Block

**Browser-earned (Tier 1/4):**
- Google News / Bing News — JS-rendered search results; Cartograph first, then Tier-1 XHR replay
- Feed-less / JS-gated outlets (Blockworks, regional newswires)

**Optional boss tier:**
- X/Twitter macro-account monitor — ONLY within the legal line (public timeline, no login defeat,
  ToS-respecting). If it cannot be done within the line → `status: BLOCKED`.

### Pipeline (`src/argus/pillars/news/pipeline.py`)

1. **Harvest** each source → raw items (via tier-appropriate harvester)
2. **Normalize** to `NewsItem`: parse `published_ts` to UTC; `fetched_ts = now(UTC)`;
   `latency_ms = fetched_ts - published_ts` when `published_ts` is known
3. **Dedup** across outlets: same story from N sources → one `NewsItem` with `corroborations[]`
   listing the others. Use rapidfuzz on normalized headline + a time window; expose threshold.
4. **Asset tagging**: populate `assets[]` via `db/asset_aliases.yaml` keyword/alias map.
   Pluggable — a model/MCP stage can replace it without touching the pipeline.
5. **Importance (1-3)**: primary-source / regulatory / breaking heuristic.
6. **Sink** to `argus.news.<source_id>` (NATS) + parquet. Idempotent on `dedup_hash`.
7. **Impact-scoring stage** (off by default): interface that could call Claude via MCP to rate
   headline market impact. Ship a no-op default + the interface only.

### Edge cases (`sources/news/EDGE_CASES.md`)

- Paywalls: headline + RSS + public preview only; never defeat
- Syndicated duplicates: dedup catches them; `corroborations[]` is the audit trail
- Timezone normalization: everything UTC — never trust source-local time
- Edited articles: detect `<updated>` ≠ `<published>`; set `revision_of` on new item
- Breaking-news bursts: cadence + backpressure; NATS handles the fan-out
- Feeds that lie about `published_ts`: `latency_ms` is computed from `fetched_ts`; a
  far-future `published_ts` is clamped and flagged

---

## Pillar 2 — Coinglass funding + liquidations

Coinglass is a Cloudflare-fronted React SPA. The public API is gated/paid but the **front-end XHR
endpoints feed the widgets**. Strategy: Cartographer maps the JSON endpoints → Tier-1 replay →
`curl_cffi` at scale.

### Targets

| Widget | Expected tier | Contract |
|--------|---------------|----------|
| Funding rates (per exchange + symbol + aggregated) | Tier 1 | `FundingPoint` |
| Liquidations (long/short, per exchange) | Tier 1 | `LiquidationPoint` |
| Open interest | Tier 1 | `OpenInterestPoint` |
| Long/short ratio | Tier 1 | `LongShortRatioPoint` |
| Liquidation heatmap | Tier 5 (canvas-only) | `LiqHeatmapCell` |

### Canvas Liberation (the showcase — `src/argus/canvas/`)

The liquidation heatmap renders to canvas with no backing JSON export.

Strategy order (record which wins in `canvas_strategy` on the Source Card):

1. **Chart-lib hook** — inject `add_init_script` before navigation to read the charting library's
   internal series data object before it hits canvas. TradingView Lightweight Charts exposes
   `series._data`; Highcharts exposes `chart.series[n].data`. This is the ideal path.
2. **Tooltip/grid walk** — hover the price-level grid systematically, harvest tooltip text into
   `LiqHeatmapCell` rows. Slower but works when the hook path fails.
3. **Screenshot → OCR** — last resort only. Document explicitly that this was used and why.

### Anti-bot

- Use `antibot.select_rung(card)` — likely patchright + residential proxy for Coinglass.
- Public pages only. If Cloudflare hard-blocks without a defeat → `DEGRADED` or `BLOCKED`.
- No CAPTCHA/login/paywall. The line holds.

---

## Pillar 3 — Economic calendars

### Sources

- **ForexFactory**: server-rendered `?day=MMDDYYYY` calendar. Timezone-configurable — **pin UTC**
  in the request. Mostly Tier-4 DOM scrape; Cartograph first for any JSON endpoints.
- **Trading Economics**: heavier defenses, more API-ish. Cartograph before writing a harvester.

### Two harvest modes

**Forward calendar** — daily/weekly harvest:
- Scheduled releases with importance, forecast, previous values.
- Normalize to `MacroEvent` with `scheduled_ts` UTC, `actual=None`.

**Release-time capture (the differentiator)** — event-driven tight-poll:
- For `importance >= 2` events: tight-poll the source around `scheduled_ts` to grab `actual`
  the instant it posts.
- Compute `surprise = actual - forecast`.
- Record `fetched_ts` and `latency_ms` (how fast Argus saw the print).
- Detect revision to `previous` when the source updates it post-release.

### Edge cases (`sources/macro/EDGE_CASES.md`)

- Tentative / all-day events: no precise `scheduled_ts`; store as date-only, skip tight-poll
- Timezone traps: force UTC via the ForexFactory timezone setting; never trust local render
- Calendar row mutates in place as data posts: detect and update the existing `MacroEvent`,
  don't create a duplicate
- Holidays / no-release: an empty calendar day is valid; don't error
- Revised `previous`: update `revision` field on the existing event; emit a corrected row

---

## Fusion (the payoff)

`pricetape/` pulls a **Tier-0** price tape (Binance public WS / Pyth Hermes SSE — *no browser*).

`fusion/` joins each news `fetched_ts` and each macro `scheduled_ts` to the price tape and
computes `ReactionRow`:
- `ret_30s`, `ret_5m`, `ret_1h` — log returns over post-event windows
- `vol_spike` — post-event volume / pre-event baseline volume
- `vwap_move` — VWAP shift
- `pre_vol`, `post_vol` — volatility windows

Output: a labeled **news/macro → market reaction** dataset that doesn't exist off-the-shelf.
Drops straight into Meridian as candidate signal, scored by the same honest gates.
