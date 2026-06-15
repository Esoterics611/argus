# CLAUDE.md — Argus

**Thesis:** The browser is the API of last resort. Argus harvests market-moving data that has no
clean public API — JS-rendered SPAs, WebSocket-only feeds, canvas-only charts, anti-bot walls.

Read `atlas/` at the start of every session. Do not re-derive what is written there.

---

## Binding rules

1. **Extraction Strategy Ladder** — descend Tier 0→6, cheapest first. See `atlas/LADDER.md`.
2. **Cartographer first** — never write a Tier-4 DOM scraper before proving no higher tier exists.
3. **Source Cards own endpoints/selectors/WS messages** — pillar code never hardcodes a URL, selector, or header.
4. **All timestamps UTC** — `datetime.now(timezone.utc)`, never `datetime.utcnow()`.
5. **Every record carries `fetched_ts`** — this is Argus's signature.
6. **Decimal for rates/money** — never float.
7. **Storage behind the Sink seam** — no direct disk/db/nats writes. Tests use `MemorySink`.
8. **Stealth behind the stealth seam** — no direct `async_playwright()` calls in pillars. Tests use `vanilla`.
9. **uv only** — no pip, no conda.
10. **Async Playwright only** — no sync API, no `time.sleep`. Use `wait_for_*` / `expect`.
11. **Full type hints + ruff + black** on every file.
12. **pytest asyncio_mode=auto** — no live network by default. Use `page.route` for fixture data.
13. **Legal line** — public data only. NEVER solve CAPTCHAs, defeat logins, or bypass paywalls. Mark such sources `BLOCKED`. See `atlas/ANTIBOT.md`.
14. **SESSION LOG** — append an entry after every prompt. Format: `## YYYY-MM-DD — Prompt NN: <title>`.

---

## File map

```
atlas/              authoritative spec — read every session
  LADDER.md         the 7-tier extraction strategy
  ARCHITECTURE.md   engine layers + swap-seams + data flow
  SOURCE_CARD_SCHEMA.md  Source Card YAML schema
  CONTRACTS.md      Pydantic record contracts + Sink interface
  ANTIBOT.md        evasion ladder + legal line
  PILLARS.md        per-pillar data specs + edge cases

sources/            Source Registry — one YAML card per target
  news/             Pillar 1
  derivs/           Pillar 2
  macro/            Pillar 3

src/argus/
  core/             browser factory, stealth seam, harvester ABC, ladder, scheduler, source_card
  sinks/            Sink seam: memory, parquet, questdb, nats
  cartographer/     network recon → endpoint map → draft Source Card
  antibot/          rung selection, proxy rotation, Fingerprint Lab
  canvas/           Canvas Liberation toolkit
  pillars/          news/, coinglass/, calendar/
  fusion/           event-to-price fusion → ReactionRow
  pricetape/        Tier-0 price tape (Binance/Pyth WS, no browser)
  cli.py            typer CLI: profile|cartograph|fingerprint|harvest|fuse|report

db/sources.yaml     registry index: source → tier, cadence, enabled
.claude/skills/     maintenance playbooks
```

## Skills table

| Skill | Trigger |
|-------|---------|
| `source-profiler` | new URL to add |
| `cartographer` | need to map endpoints for a source |
| `canvas-liberation` | source has canvas-only data |
| `antibot-escalation` | harvester getting blocked |
| `harvester-codegen` | profiled source needs a harvester |
| `drift-triage` | harvester breaks in prod |
| `registry-sync` | Source Cards drift from code/registry |

---

## SESSION LOG

## 2026-06-15 — Prompt 00: Orientation
Confirmed Extraction Strategy Ladder, house conventions, legal line. Agreed build order:
01→02→03→04→05→08→06→07→09→10.

## 2026-06-15 — Prompt 01: Repo bootstrap + atlas
Created full directory tree, pyproject.toml (uv), docker-compose.yml (QuestDB+NATS), init_env.sh,
.env.example, .gitignore, LICENSE. Wrote all six atlas/ docs and CLAUDE.md.

## 2026-06-15 — Prompt 02: Core engine
Stealth swap-seam (vanilla/stealth/patchright/camoufox backends). Sink swap-seam (memory/parquet/
questdb/nats). BrowserFactory with HAR+trace, UTC locale, proxy. SourceCard Pydantic model with
load/save/validate. All Pydantic contracts (NewsItem, MacroEvent, FundingPoint, LiqHeatmapCell,
ReactionRow, etc.). Harvester ABC with Tier0/1/4 mixins. Ladder fall-down logic. Async Scheduler
with per-domain semaphores and tenacity backoff. 22 tests, all green.

## 2026-06-15 — Prompt 03: Cartographer
NetworkCapture (CDP session + page.on listeners for XHR/fetch/WS, response body via
Network.getResponseBody). classify.py (data_likelihood scorer, numeric-series detection, tier
recommender). emit.py (cartograph.json inventory, draft Source Card YAML, httpx+curl_cffi replay
snippets). Cartographer class (scroll/hint-click page exercise, probe_embedded_state). CLI
`argus cartograph` wired. 36 tests, all green. WS capture tested via unit mock (Playwright 1.60
route_web_socket intercepts before page.on fires; documented). Branch: prompt-03-cartographer.

## 2026-06-15 — Prompt 04: Anti-bot
rung.py: select_rung() picks lowest-cost passing rung (explicit card override → Fingerprint Lab
→ conservative vendor default). RUNG_ORDER = vanilla→stealth→patchright→camoufox. proxy.py:
per-context proxy rotation with per-domain stickiness; session tokens embedded in proxy username;
returns None when PROXY_POOL_URL not set. cadence.py: short_pause/reading_pause/think_pause,
human_move_to (interpolated mouse + jitter), human_click (bbox randomisation), human_scroll
(incremental with jitter), scroll_to_bottom. fingerprint_lab.py: run_lab() probes each backend
against public CreepJS-style page; scores webdriver/headless_ua (hard fail) + canvas/chrome/
languages/webgl; persists to sources/_fingerprint_results.json. CLI `argus fingerprint` wired.
Hard-constraint tests: no captcha/login/paywall names in public surface or source files.
53 tests total, all green. Branch: prompt-04-antibot.
