# Source Card Schema

Each source has one YAML file under `sources/<pillar>/<id>.yaml`.
The Cartographer writes the first draft; harvesters read it; the registry (`db/sources.yaml`) indexes it.

```yaml
id: <slug>                        # unique, kebab-case, stable
name: <human name>
url: <canonical entry URL>
pillar: news | derivs | macro
tier: 0                           # winning extraction tier (0-6)
status: LIVE | BLOCKED | DEGRADED

# ── Tier 0 ──────────────────────────────────────────────────
rss_feeds:
  - url: <feed URL>
    format: rss | atom | json_feed

# ── Tier 1 — discovered JSON/GraphQL endpoints ───────────────
discovered_endpoints:
  - method: GET | POST
    url_template: "https://..."   # {symbol}, {exchange} placeholders ok
    headers_required:             # headers the browser sent; required for replay
      Referer: "..."
      x-requested-with: "..."
    auth: none | cookie | bearer  # how auth is carried
    params:
      symbol: BTC
      interval: 1h
    response_path: "data.list"    # jmespath to the records array
    data_likelihood: 0.95         # Cartographer score

# ── Tier 3 — WebSocket ──────────────────────────────────────
websocket:
  url: "wss://..."
  subscribe_msg: '{"op":"subscribe","args":["funding"]}'
  frame_path: "data"              # jmespath into each received frame

# ── Tier 2 — embedded JS state ──────────────────────────────
state_extraction:
  global: "__NEXT_DATA__"         # window global to evaluate
  path: "props.pageProps.data"

# ── Tier 5 — canvas ─────────────────────────────────────────
canvas_strategy: chart_hook | tooltip_walk | ocr | null
canvas_notes: "TradingView Lightweight Charts — hook series._data"

# ── Defenses ────────────────────────────────────────────────
defenses:
  vendor: cloudflare | akamai | datadome | none
  evasion_rung: vanilla | stealth | patchright | camoufox

# ── Output contract ─────────────────────────────────────────
schema: NewsItem | MacroEvent | FundingPoint | LiquidationPoint | ...
cadence: 60s | 5m | 1h | on_schedule   # harvest cadence
sink_subject: "argus.news.fed_press"    # NATS subject

# ── Compliance ──────────────────────────────────────────────
robots_ok: true | false | unknown
terms_note: "Public page, no login required. ToS §3 permits automated access for personal use."

# ── Provenance ──────────────────────────────────────────────
last_verified_ts: "2026-06-15T00:00:00Z"
har_path: "traces/har/coinglass-funding-20260615.har"
trace_path: "traces/trace/coinglass-funding-20260615.zip"
notes: |
  Cartographer found /api/v3/funding_rate XHR returning JSON array.
  Cloudflare present; patchright + residential proxy passes FP lab.
```

## Registry index (`db/sources.yaml`)

A flat index the scheduler reads — one entry per source:

```yaml
sources:
  - id: fed_press
    pillar: news
    tier: 0
    cadence: 5m
    enabled: true
    ci_safe: true          # safe to run in CI (no live network cost)
  - id: coinglass_funding
    pillar: derivs
    tier: 1
    cadence: 60s
    enabled: true
    ci_safe: false
```
