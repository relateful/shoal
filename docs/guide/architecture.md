# Architecture

Shoal is a set of layers. Lower layers never import higher ones, and the transport layers (the
middle row) never import each other. `import-linter` enforces this in CI.

```
                                compat
                                   |
                               commands
                                   |
                         ui    app_commands
                            \    /
                             client
                               |
                             emojis
                               |
                             models
                               |
                         redis   voice
                               |
rest   gateway   cache   ipc   metrics   diagnostics   endpoint   tasks
   \       |        |      |       |           |           |       /
                              payloads
                                 |
                               core
```

| Layer | Depends on | Purpose |
| --- | --- | --- |
| `core` | standard library, msgspec | snowflakes, flags, open enums, codec, clock, metrics catalog, dispatch event, Ogg pages |
| `payloads` | core | one msgspec struct per Discord JSON object |
| `rest` | core, payloads, aiohttp | HTTP client, routes, rate limiting, the REST proxy |
| `gateway` | core, payloads, aiohttp | shards, compression, sessions, clusters |
| `cache` | core, payloads | the cache store and the dispatch-to-cache updater |
| `ipc` | core | carries dispatch events between processes, over TCP or a Unix socket |
| `metrics` | core, prometheus-client | exporters |
| `diagnostics` | core | event loop health |
| `endpoint` | core, payloads, aiohttp, cryptography | receives interactions over HTTP, for bots without a gateway |
| `tasks` | core | background loops, cron expressions, and the job scheduler with its in-memory store |
| `redis` | the transport layers, redis-py | what a bot's processes share: rate limits, identify, sessions, cache, events, the shard directory, command routing and scheduled jobs |
| `voice` | the transport layers, cryptography, davey | voice connections: the voice gateway, UDP, transport encryption, DAVE and audio |
| `models` | the layers below | `Guild`, `Member`, `Message` and the rest: objects with methods, reading the cache and calling REST |
| `emojis` | models | the application's emojis: a registry used across the bot, and a sync from a folder |
| `client` | the layers below | `Client`: connects shards, keeps the cache, turns events into models, routes interactions |
| `ui` | client | views, buttons, selects and modals |
| `app_commands` | client | slash commands, context menus, the command tree and its checks |
| `commands` | ui, app_commands | prefix and hybrid commands: `Bot`, cogs, converters, extensions, help |
| `compat` | every layer | familiar names for migrating bots: `import shoal.compat as discord` |

Because the top-row layers share only `core` and `payloads`, any of them can move to another process:

- a gateway process runs shards and an `EventServer`;
- worker processes run your commands with an `EventClient`, a `CacheUpdater` and a `RestClient`;
- a dashboard backend uses only `RestClient`, and can serve interactions with `Endpoint`.

## The event path

1. A `Shard` receives a frame, decompresses it and reads the envelope (`GatewayPayload`). The event
   data stays raw JSON (`msgspec.Raw`).
2. The shard hands a `DispatchEvent` to its `dispatch` callback, in order.
3. Whoever consumes it decodes only what it needs: the `CacheUpdater` decodes `GUILD_CREATE` into
   `GuildCreate`; an `EventServer` forwards the raw bytes to workers without decoding at all.

## Where things go

| You are adding | It goes in |
| --- | --- |
| A Discord JSON object | `shoal/payloads/<domain>.py`, linked to its docs section |
| A Discord-documented constant | next to its types in `shoal/payloads/<domain>.py` |
| A Shoal default (timeout, threshold) | `shoal/<layer>/defaults.py` |
| An HTTP endpoint | a `Route` in `shoal/rest/endpoints.py`, a method in `shoal/rest/resources/<resource>.py`, and an `EndpointCase` in `tests/rest/resources/<resource>.py` |
| A metric | `shoal/core/metrics.py`, then record it where it happens |
| Tests for `src/shoal/<layer>/<module>.py` | `tests/<layer>/<module>.py` |
