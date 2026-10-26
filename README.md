# Shoal

A fully typed Discord API library for Python, built for bots that grow: easy for a bot in one server,
and still the right tool at a million.

> **Status: pre-alpha.** Built and tested: typed payloads, a REST client that covers every endpoint
> Discord documents, the gateway with clusters and resumable sessions, a restart-aware cache,
> inter-process communication, state shared through Redis, a REST proxy, resharding without
> downtime, metrics and diagnostics, and the bot API on top: a `Client` with models, slash
> commands, prefix and hybrid commands with cogs and extensions, views, modals and Components V2
> layouts, voice messages, end-to-end encrypted voice, the application's emojis, and `shoal.compat`
> for bots moving over.
> Interactions arrive over the gateway or a signed HTTP endpoint. See the
> [guide to writing a bot](docs/guide/bot.md) and the [roadmap](docs/roadmap.md).

## Why Shoal

| | discord.py | Shoal |
| --- | --- | --- |
| Shard startup | One shard every 5 s; `max_concurrency` ignored | Identifies by `max_concurrency` bucket, as Discord documents |
| Separate processes | Bring your own IPC | Built in: gateway processes stream events to worker processes |
| Restarts | Cache and sessions lost | Sessions resumed after a restart; cache restored from a snapshot and marked stale until Discord confirms it |
| A dead resume URL | Falls back only on a 5xx handshake, and then starts a new session | Any failure (timeout, 5xx, early close) falls back to the main gateway and still resumes there, as Discord recommends |
| Cloudflare IP bans | Not tracked | 401/403/429 counted; requests held back before Discord's 10,000-per-10-minutes ban |
| A revoked token | Keeps sending requests that fail | Stops after the first 401 |
| Cache | One fixed in-memory cache | A policy per entity (size, TTL, persist); every entry knows its source and age |
| A blocked event loop | A raw stack trace once the heartbeat has been stuck for 10 s | A configurable threshold (0.25 s by default), the blocking line of your code named, the block's duration logged, and metrics |
| Late events | Invisible | Delay from creation to arrival measured and warned about |
| Absent vs `null` | Both become `None` | `UNSET` and `None` stay distinct |
| New Discord enum values | `unknown_<value>` proxy objects that are not members of the enum | Decoded as real members of the enum; the value is kept |
| REST without a bot | Undocumented `Client.http` | Public, standalone `RestClient`, with OAuth2 bearer tokens for dashboards |
| Metrics | None | Prometheus export of requests, rate limits, shards, cache, IPC and loop health |
| Discord's docs | Separate | Every type and endpoint links to its section, verified in CI |

## Install

```bash
pip install shoal
pip install "shoal[prometheus]"   # Prometheus metrics
pip install "shoal[zstd]"         # zstd gateway compression on Python 3.12 and 3.13
pip install "shoal[interactions]" # receive interactions over HTTP, without a gateway
pip install "shoal[redis]"        # share limits, sessions, cache, events and shards across processes
pip install "shoal[voice]"        # join voice channels and play audio, end-to-end encrypted
pip install "shoal[all]"          # every optional feature above
```

Each extra adds a dependency only some bots need, so a plain install stays small.

Shoal needs Python 3.12 or newer.

## A taste

The REST client works on its own, from a bot, a worker or a web backend:

```python
import asyncio

from shoal.payloads import AllowedMentions, CreateMessageParams
from shoal.rest import RestClient, Token


async def main() -> None:
    async with RestClient(Token.bot("YOUR_TOKEN")) as rest:
        me = await rest.users.get_me()
        print(me.username, me.id.created_at)
        await rest.messages.create(
            1234567890,
            CreateMessageParams(content="hello from shoal", allowed_mentions=AllowedMentions.none()),
        )


asyncio.run(main())
```

Running shards, keeping a cache and exporting metrics:

```python
from shoal.cache import CacheStore, CacheUpdater
from shoal.gateway import FileSessionStore, LocalIdentifyLimiter, ShardManager
from shoal.metrics.prometheus import PrometheusMetrics
from shoal.payloads import Intents
from shoal.rest import RestClient, Token


async def main(token: str) -> None:
    metrics = PrometheusMetrics()
    metrics.serve(9100)

    async with RestClient(Token.bot(token), metrics=metrics) as rest:
        gateway = await rest.gateway.get_bot()

    intents = Intents.default()
    store = CacheStore(metrics=metrics)
    await store.load_snapshot("cache.msgpack")  # before connecting
    updater = CacheUpdater(store, intents=intents)

    manager = ShardManager(
        token=token,
        intents=intents,
        dispatch=updater.apply,
        shard_count=gateway.shards,
        gateway_url=gateway.url,
        identify_limiter=LocalIdentifyLimiter(gateway.session_start_limit.max_concurrency),
        session_store=FileSessionStore("sessions/"),
        metrics=metrics,
    )
    try:
        await manager.run()
    finally:
        await manager.close()  # saves every session, so the next start resumes
        await store.save_snapshot("cache.msgpack")  # and the cache, ending at the same event
```

## Documentation

- Guides: [architecture](docs/guide/architecture.md), [caching and restarts](docs/guide/caching.md),
  [scaling, sharding and IPC](docs/guide/scaling.md), [dashboards and REST](docs/guide/dashboards.md),
  [metrics and Grafana](docs/guide/metrics.md), [diagnosing a slow bot](docs/guide/diagnostics.md),
  [commands and interactions](docs/guide/interactions.md),
  [migrating from discord.py](docs/guide/migrating-from-discord-py.md).
- The API reference is generated from the docstrings: `uv run --group docs mkdocs serve`.
- [Discord API coverage](docs/coverage.md) lists every endpoint Discord documents and whether Shoal
  implements it. It is generated from Discord's docs source and checked weekly.

## Quality

- pyright and mypy in strict mode over the library and its tests; `Any` is banned.
- Every module with behaviour has a test module; coverage is held above 95%.
- `tests/conventions.py` enforces the project's rules across the whole tree: docs links, ordering,
  constants defined once, slots, exports, test layout.
- CI runs on Python 3.12, 3.13 and 3.14 on Linux, Windows and macOS.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the rules, the layout and every check CI runs.

## License

[MIT](LICENSE)
