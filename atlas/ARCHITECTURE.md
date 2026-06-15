# Architecture

## Engine layers

```
┌─────────────────────────────────────────────────────────────┐
│  CLI  (argus profile | cartograph | fingerprint |           │
│         harvest | fuse | report)                            │
├─────────────────────────────────────────────────────────────┤
│  Scheduler  (asyncio worker pool, per-source cadence,       │
│              per-domain rate limits, tenacity backoff)      │
├───────────────────────┬─────────────────────────────────────┤
│  Harvester ABC        │  Cartographer                       │
│  (profile→extract     │  (network recon → endpoint map →   │
│   →normalize→sink)    │   draft Source Card → replay code)  │
├───────────────────────┼─────────────────────────────────────┤
│  Ladder               │  Anti-bot                           │
│  (tier dispatch +     │  (rung selection, proxy rotation,   │
│   fall-down logic)    │   Fingerprint Lab, human cadence)   │
├───────────────────────┴─────────────────────────────────────┤
│  ══ STEALTH SWAP-SEAM ══                                    │
│  vanilla | playwright-stealth | patchright | camoufox       │
│  (selected per Source Card; vanilla in tests)               │
├─────────────────────────────────────────────────────────────┤
│  BrowserFactory  (context, HAR, trace, locale=UTC)          │
├─────────────────────────────────────────────────────────────┤
│  Canvas Liberation  (chart-hook → tooltip walk → OCR)       │
├─────────────────────────────────────────────────────────────┤
│  Normalize  (raw → Pydantic contracts, UTC, Decimal)        │
├─────────────────────────────────────────────────────────────┤
│  ══ SINK SWAP-SEAM ══                                       │
│  memory | parquet | questdb | nats                          │
│  (configured per env; memory in tests)                      │
├─────────────────────────────────────────────────────────────┤
│  Price Tape  (Tier-0 Binance/Pyth WS — NO browser)         │
│  Fusion      (join events → price tape → ReactionRow)       │
└─────────────────────────────────────────────────────────────┘
```

## Data flow

```
profile(url)
  └→ Cartographer.run() → sources/<pillar>/<id>.yaml (Source Card)
       └→ Ladder.select_tier(card)
            └→ Harvester.extract(ctx)   [tier-specific]
                 └→ Harvester.normalize(raw) → list[BaseModel]
                      └→ Sink.write(table, rows)
                           ├→ parquet  (cold)
                           ├→ questdb  (hot)
                           └→ nats     (bus → argus.<table>.<source_id>)

pricetape.stream()  →  price tape (parquet + argus.price.<symbol>)

fusion.run(since)
  └→ join(news.fetched_ts | macro.scheduled_ts, price_tape)
       └→ ReactionRow  →  argus.fusion.reactions
```

## Layer rules (binding)

- **Source Cards own endpoints, selectors, WS subscribe messages, canvas strategy, and evasion
  rung.** Pillar code reads them; pillar code never hardcodes a URL, selector, or header.
- **Pillars compose `core` + `sinks`.** They own only normalization + the per-pillar contract.
- **The Cartographer, anti-bot module, and canvas toolkit are pillar-agnostic.** They are called
  from any pillar without modification.
- **The Sink seam is the only storage interface.** No pillar writes directly to disk, questdb, or
  nats. Tests substitute `MemorySink` at construction time.
- **The stealth seam is the only browser-launch interface.** No pillar calls `async_playwright()`
  directly. Tests substitute `vanilla`.
- **pricetape is deliberately Tier-0, browser-free.** Using a browser for data that has a clean
  public WS would contradict Argus's thesis.

## Two swap-seams in detail

### Stealth seam  (`src/argus/core/stealth/`)
```
Backend protocol:
  launch() → Browser
  new_context(proxy, **kw) → BrowserContext

Implementations:
  VanillaBackend    — async_playwright, no patches (default + tests)
  StealthBackend    — VanillaBackend + playwright-stealth JS injection
  PatchrightBackend — patchright fork (CDP-leak patched Chromium)
  CamoufoxBackend   — camoufox (Firefox, C++-level fingerprint spoofing)
```

### Sink seam  (`src/argus/sinks/`)
```
Sink protocol:
  ensure_schema(table, model_class)
  write(table, rows) → int          # returns rows written; idempotent

Implementations:
  MemorySink    — dict[table, list[dict]]  (tests)
  ParquetSink   — polars → pyarrow, one file per (table, date)
  QuestDBSink   — ILP over TCP to port 9009
  NatsSink      — publish each row JSON to "argus.<table>.<source_id>"
```
