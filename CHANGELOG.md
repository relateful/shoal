# Changelog

All notable changes are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `shoal.core`: `Snowflake`, immutable `BaseFlags` bitfields, open enums that accept values Discord adds
  later, the msgspec JSON and msgpack codec, the `Clock` protocol with an interruptible sleep, a shared
  backoff function, owner-only atomic file writes, and the metrics catalog with the `Metrics` protocol.
- `shoal.payloads`: typed payloads, one module per Discord domain (API constants, users, permissions,
  emoji, guilds, channels, messages, voice, gateway, gateway events, rate limits, errors), each linked to
  its section of Discord's docs. Includes message search parameters and results, presences, voice states, reactions and
  thread events, and handling for obfuscated channels (`Channel.is_obfuscated`, `Channel.visible_name`).
- `shoal.rest`: `RestClient` with bot and bearer tokens, typed routes with docs links, per-bucket and
  global rate limiting, the invalid request guard, stop-after-401, and Search Guild Messages with
  retries while Discord builds the index.
- `shoal.gateway`: zlib-stream and zstd-stream decompression, shard routing, `max_concurrency` identify
  scheduling, persistent sessions, heartbeat tracking, the send limiter, event delay tracking, a
  resumable `Shard` that falls back from a failing resume URL to the main gateway, and `ShardManager`
  with cluster assignment (`cluster_shard_ids`).
- `shoal.cache`: per-entity cache policies, per-shard freshness tracking, scope-indexed collections,
  snapshots that line up with resumed sessions, restart strategies, and a `CacheUpdater` that applies
  every cache-relevant gateway event (guilds, channels, threads, roles, emojis, members, users,
  messages, reactions, presences and voice states).
- `shoal.ipc`: `EventServer` and `EventClient` to stream gateway events between processes over TCP, with
  token authentication, optional TLS, event filtering and reconnects.
- `shoal.metrics.prometheus`: `PrometheusMetrics`, exporting every metric in the catalog.
- `shoal.diagnostics`: `LoopMonitor`, which names the code blocking the event loop while it blocks.
- Documentation site with generated API reference, guides, and a Discord API coverage page checked
  weekly against Discord's docs.
