# News Pillar — Edge Cases

## Paywalls
Harvest only what the RSS feed exposes (headline + summary + URL). Never follow the article URL
to defeat a paywall. If a source requires login to see any content, mark `status: BLOCKED`.

## Syndicated duplicates
The deduplicator runs `rapidfuzz.fuzz.token_set_ratio` on normalized headlines within a rolling
30-minute window. The first-fetched item wins; all later versions are folded into its
`corroborations[]` list. Threshold is configurable (default 85).

## Timezone normalization
All `published_ts` are parsed and stored as UTC. feedparser may return time structs in local
time — always convert via `calendar.timegm(entry.published_parsed)` → UTC epoch → `datetime.UTC`.
Never trust a source-local timezone label; treat ambiguous timestamps as UTC.

## Edited articles (revision detection)
If `entry.updated_parsed` differs from `entry.published_parsed` by > 60 seconds, the pipeline
emits a new `NewsItem` with `revision_of = <original dedup_hash>`. The original item is not
mutated so the audit trail is preserved.

## Far-future / far-past published_ts
If `published_ts` is more than 1 hour in the future relative to `fetched_ts`, it is clamped to
`fetched_ts` and the item gets a `notes` flag. If more than 30 days in the past, the item is
skipped (stale feed cache). Both thresholds are constants in `normalize.py`.

## Breaking-news bursts
A single story may hit 5+ outlets within seconds. The deduplicator handles fan-out gracefully:
first item wins, rest become `corroborations`. NATS JetStream provides backpressure downstream.

## Feed-level errors
If a feed URL returns non-200 or unparseable XML, the harvester logs a warning and returns `[]`.
The scheduler's tenacity backoff retries with exponential delay. After 4 failures the source
is marked `DEGRADED` in its Source Card.

## Empty feeds
An empty feed (0 entries) is valid — not an error. Log at DEBUG level.

## lang detection
Set `lang` from the feed channel's `language` attribute when present. Fall back to `"en"` for
feeds that omit it. Do not run ML language detection — the alias map covers EN only for now.
