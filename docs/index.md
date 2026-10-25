# Shoal

A fully typed Discord API library for Python, built for bots that grow: easy for a bot in one server,
and still the right tool at a million.

!!! warning "Pre-alpha"
    The foundation is in place: typed payloads, the REST client, the gateway, the cache, IPC, metrics
    and diagnostics. The high-level bot API (models with methods, commands, components) is next; see
    the [roadmap](roadmap.md).

## What is here today

| Layer | What it gives you |
| --- | --- |
| `shoal.core` | Snowflakes, flag sets, open enums, the msgspec codec, metrics catalog, backoff |
| `shoal.payloads` | Typed mirrors of Discord's JSON, every type linked to its docs section |
| `shoal.rest` | A standalone HTTP client with bucket, global and invalid-request rate limiting |
| `shoal.gateway` | Shards, `max_concurrency` identify scheduling, resumable sessions, clusters |
| `shoal.cache` | Per-kind policies, freshness tracking, snapshots for warm restarts |
| `shoal.ipc` | Gateway and bot logic in separate processes, over authenticated TCP |
| `shoal.metrics` | Prometheus export for every metric Shoal records |
| `shoal.diagnostics` | Names the code blocking your event loop |

## Principles

- **Typed all the way down.** pyright and mypy run in strict mode over the library and its tests.
- **Every Discord fact links to Discord's docs.** CI checks each link and route against the docs source.
- **Nothing silent.** Dropped events, rate limits, slow consumers and blocked loops are logged and
  counted.
- **Layers you can split.** REST, gateway, cache and IPC never import each other.

Start with the [architecture](guide/architecture.md).
