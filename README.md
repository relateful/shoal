# Shoal

A fully typed Discord API library for Python, built for bots that grow. It keeps the names you know
from discord.py (`commands.Bot`, `interaction.response.send_message`, `ui.View`, `tree.sync()`) and
fixes what makes discord.py painful once a bot gets big.

> [!NOTE]
> **Status: pre-alpha.** Everything below is built and tested, but names can still change before
> the first release. See the [roadmap](docs/roadmap.md).

> [!IMPORTANT]
> Shoal is not on PyPI yet. Install it from a clone (see [Install](#install)).

## Why not discord.py?

discord.py is a good library for a bot in a few servers. Shoal is for bots that keep growing, and it
is just as easy for the small ones.

### It starts fast, however many shards you run

discord.py identifies its shards one after another, about five seconds apart, and ignores the
`max_concurrency` Discord gives large bots. Shoal identifies `max_concurrency` shards at a time, as
Discord documents. At 512 shards with a concurrency of 16, that is under three minutes instead of
about 43.

### Restarts and deploys don't cost you the gateway

- **Sessions survive restarts.** discord.py keeps the session only in memory, so every restart
  identifies every shard again, and Discord sends every guild again. Shoal saves sessions (to files,
  or Redis) and resumes them on the next start.
- **The cache survives restarts.** Shoal restores the cache from a snapshot, marked stale until
  Discord confirms each entry, so the bot answers from a warm cache from the first second.
- **A failed resume still resumes.** discord.py falls back to the main gateway only when the resume
  URL answers with a 5xx, and then starts a new session. Shoal falls back on any failure (a timeout,
  a 5xx, an early close) and resumes there, as Discord recommends.
- **Change shard counts without downtime.** `bot.reshard(new_count)` connects the new shards beside
  the running ones and switches over once they are all ready. discord.py has no way to do this short
  of a restart.

### More than one process is built in

discord.py leaves IPC to you. Shoal includes it:

- **Gateway and workers.** One process holds the shards and streams events (`shoal.ipc`, over TCP
  or a Unix socket, or through a Redis stream). Workers run your commands and can restart as often
  as you deploy.
- **Clusters.** Several processes or hosts run one bot through Redis. They share one identify
  limiter, the REST rate limits, sessions, a directory of every shard, a command router (join a
  voice channel from any cluster) and the cache.
- **A REST proxy.** One process holds the token and the rate limits for all the others.

### It protects the bot from bans

- Discord bans an IP for 10,000 invalid requests in 10 minutes. discord.py does not count them.
  Shoal counts the 401, 403 and 429 responses Discord counts, and holds requests back before the
  limit.
- After a 401 (a revoked token), discord.py keeps sending requests that fail. Shoal stops at the
  first one.

### You can see what it is doing

- **Prometheus metrics** for gateway events and latency per shard, REST requests and rate limits by
  route, the cache, IPC, voice and event loop health. discord.py has none.
- **A blocked event loop is caught as it happens.** discord.py warns once the heartbeat has been
  stuck for 10 seconds, and again every 10 seconds after. Shoal's watchdog
  (`async with LoopMonitor():`) reports blocks over 0.25 seconds (configurable), names the line of
  your code that is blocking while it blocks, logs how long it lasted, and records it in metrics.
- **Late events are noticed.** Shoal measures how long each message and interaction took to arrive,
  and warns when they arrive more than five seconds late: the sign that events queue up before your
  code sees them.

### Typed, and true to Discord's docs

- Strict pyright and mypy over the library and its tests, with `Any` banned.
- Every type and endpoint links to its section of Discord's docs, and CI checks the links. Every
  HTTP endpoint Discord documents and every gateway event is covered, as the
  [coverage page](docs/coverage.md), generated from Discord's docs, shows.
- A field that is absent and a field that is `null` stay different (`UNSET` and `None`), so an edit
  can tell "leave it" from "clear it". discord.py turns most of them into `None`.
- When Discord adds an enum value, Shoal decodes it as a real member of the enum, with its value
  kept. discord.py makes an `unknown_<value>` stand-in that is not a member.
- REST is public and standalone: `RestClient` covers every endpoint as `rest.<resource>.<verb>`, with
  bot or OAuth2 bearer tokens, for workers and dashboards. discord.py's `Client.http` is internal and
  undocumented.

### And what a bot needs today

- Slash, prefix and hybrid commands, cogs and extensions, views, modals and Components V2 layouts.
- Interactions over the gateway, or over HTTP with no gateway at all (signed, verified endpoint).
  discord.py only has the gateway.
- Voice: play and **listen**, end-to-end encrypted (DAVE), as Opus packets or decoded PCM per user
  (decoding needs libopus). discord.py can play, but receiving audio takes a third-party extension.
- Voice messages, polls, the application's own emojis synced from a folder, and member chunking as
  guilds arrive (`chunk_guilds_at_startup`).
- A cache with a policy per entity (size, TTL, whether to snapshot, which fields to keep), instead
  of one fixed cache.
- Loops (`tasks.loop`) and a scheduler for reminders and cron jobs that survive restarts with
  Redis, without a sleeping task per job.

> [!TIP]
> Coming from discord.py? `import shoal.compat as discord` gives you the old names, so a bot can move
> file by file. See the [compat example](docs/examples/compat/) and the
> [migration guide](docs/guide/migrating-from-discord-py.md).

## Install

Shoal needs Python 3.12 or newer. From a clone of this repository:

```bash
pip install -e .                  # the core
pip install -e ".[voice]"         # join voice channels, play and listen
pip install -e ".[redis]"         # share limits, sessions, cache, events and shards across processes
pip install -e ".[prometheus]"    # Prometheus metrics
pip install -e ".[interactions]"  # receive interactions over HTTP, without a gateway
pip install -e ".[zstd]"          # zstd gateway compression on Python 3.12 and 3.13
pip install -e ".[all]"           # everything above
```

Each extra adds a dependency only some bots need, so the core install stays small.

## A taste

```python
import os

import shoal
from shoal import commands

bot = commands.Bot("!", intents=shoal.Intents.default().with_flags(message_content=True))


@bot.hybrid_command(description="Say hello")
async def hello(ctx: commands.Context, who: shoal.Member | None = None) -> None:
    await ctx.send(f"Hello {(who or ctx.author).mention}!")


bot.run(os.environ["DISCORD_TOKEN"])
```

`!hello` and `/hello` both work (sync the slash command once with `await bot.tree.sync()`).

## Examples

[29 runnable bots](docs/examples/), each with its own README and each run against Discord, from
the [smallest bot](docs/examples/hello/) to [role menus](docs/examples/roles/buttons/),
[tickets](docs/examples/tickets/), [music](docs/examples/voice/music/) and
[a big bot](docs/examples/bigbot/) with Prometheus, Grafana, warm restarts and resharding, plus
[clusters](docs/examples/clusters/) and [workers](docs/examples/workers/).

## Documentation

- Guides: [writing a bot](docs/guide/bot.md), [commands and interactions](docs/guide/interactions.md),
  [caching and restarts](docs/guide/caching.md), [scaling, sharding and IPC](docs/guide/scaling.md),
  [voice](docs/guide/voice.md), [loops and scheduled jobs](docs/guide/tasks.md),
  [dashboards and REST](docs/guide/dashboards.md),
  [metrics and Grafana](docs/guide/metrics.md), [diagnosing a slow bot](docs/guide/diagnostics.md),
  [architecture](docs/guide/architecture.md),
  [migrating from discord.py](docs/guide/migrating-from-discord-py.md).
- The API reference is generated from the docstrings: `uv run --group docs mkdocs serve`.
- [Discord API coverage](docs/coverage.md) lists every endpoint Discord documents and the Shoal method
  for it, generated from Discord's docs and checked weekly.

## Quality

- Every module with behaviour has a test module, and coverage is held above 95%.
- `tests/conventions.py` enforces the project's rules across the whole tree: docs links, ordering,
  constants defined once, slots, exports, test layout.
- CI runs on Python 3.12, 3.13 and 3.14, on Linux, Windows and macOS.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the rules, the layout and every check CI runs.

## License

[MIT](LICENSE)
