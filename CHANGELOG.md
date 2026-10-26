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
- Every HTTP endpoint Discord documents (239), grouped by resource in `shoal.rest.resources`: users,
  voice, emoji, stickers, soundboard, channels, threads, invites, messages, reactions, pins, polls,
  webhooks, guilds, members, roles, bans, prune, widgets, onboarding, scheduled events, stage
  instances, templates, Auto Moderation, audit logs, applications, monetization, OAuth2 information,
  lobbies and application identity profiles, each with its payloads. The four endpoints Discord has
  deprecated or disabled are left out.
- File uploads: `File` (bytes, or read off the event loop with `File.from_path`) on every endpoint
  that takes files. Message-like requests describe new files in `attachments` themselves; edits only
  append, so existing attachments are never dropped by accident. `image_data` and `sound_data` build
  the data URIs Discord's image and sound fields take.
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
- Application commands: typed commands, options, choices and permissions, and the 15 live command
  endpoints. Creating or editing one guild command takes its own type, without the global-only
  fields.
- Components: every message and modal component, including Components V2 and the newer modal inputs,
  with layout unions that make invalid nesting a type error. Received components decode lazily
  (`parse_components`), so a component type newer than Shoal never breaks a message.
- Interactions: one class per interaction type and per response type, `parse_interaction` with an
  `UnknownInteraction` fallback, modal submissions, resolved data, and the eight response and
  follow-up endpoints. Interaction tokens never appear in logs, errors or metrics.
- `shoal.interaction_server`: receive interactions over HTTP without a gateway, with Ed25519
  signature checks, inline or callback answers, and handler timing against the 3-second deadline
  (`pip install 'shoal[interactions]'`).
- `shoal.metrics.prometheus`: `PrometheusMetrics`, exporting every metric in the catalog.
- `shoal.diagnostics`: `LoopMonitor`, which names the code blocking the event loop while it blocks.
- Documentation site with generated API reference, guides, and a Discord API coverage page checked
  weekly against Discord's docs.
