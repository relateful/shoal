# Big bot

How a bot meant for thousands of servers is set up: a package with its settings, its wiring and its
features apart; Prometheus metrics with a Grafana dashboard; a cache sized for scale; restarts that
resume instead of reconnecting from scratch; a watchdog for the event loop; and resharding without
downtime. It runs under Docker Compose with Prometheus and Grafana beside it.

```
bigbot/
  .env.example         settings: copy to .env
  Dockerfile           the bot's image, with Shoal from PyPI
  docker-compose.yml   the bot, Prometheus and Grafana
  prometheus.yml       Prometheus scrapes the bot
  grafana/             a provisioned data source and dashboard
  bigbot/
    __main__.py        `python -m bigbot`: settings, logging, run
    config.py          settings from the environment, checked at start
    bot.py             the wiring: metrics, cache, sessions, snapshot, watchdog, extensions
    cogs/              one extension per feature, all loaded at start
      general.py       /ping, /about
      owner.py         !shards, !stats, !reshard, !reload, !sync
      diagnostics.py   !block and !burst: prove the safeguards work
      lifecycle.py     shards, servers joined and left, command errors
```

## Run it

```bash
cp .env.example .env          # then put your token in .env
docker compose up --build
```

Grafana is at <http://localhost:3000> (dashboard **Shoal bot**), Prometheus at
<http://localhost:9090>. Both listen on localhost only, and the bot's metrics port is not published at
all: Prometheus reaches it on the Compose network.

Without Docker, from this folder:

```bash
pip install --pre "shoal[prometheus,zstd]"   # Shoal from PyPI
set -a; . ./.env; set +a
python -m bigbot                             # metrics on http://127.0.0.1:9100/metrics
```

Then, as the bot's owner, run `!sync` once to register the slash commands.

## What each part is for

- **Metrics.** `PrometheusMetrics` receives what every layer measures: gateway events and latency
  per shard, REST requests, latency and rate limits by route, the invalid request count that leads to
  Discord's 10,000-per-10-minutes ban, cache hits, event delay and event loop lag. The dashboard
  shows them; the [metrics guide](../../guide/metrics.md) lists every series.
- **A cache sized for scale.** Presences are not cached at all (they are the busiest event), members
  expire after six hours, messages and users are bounded. Change `cache_config()` to what your
  features read.
- **Warm restarts.** `FileSessionStore` keeps each shard's session, and `cache_snapshot` the cache.
  On restart each shard resumes where it stopped (no identify, no flood of `GUILD_CREATE`), and the
  cache comes back marked stale until Discord confirms it. Sessions older than three minutes are not
  resumed; that shard identifies again. In Compose, `/data` is a volume, and `stop_grace_period`
  leaves time to save both on shutdown.
- **The event loop watchdog.** `LoopMonitor` logs the line of your code that blocks the event loop,
  while it blocks (`requests.get`, `time.sleep`, a slow query), and records each block.
- **Proving it.** `!block 1.5` blocks the event loop with `time.sleep` on purpose: the log names
  `diagnostics.py` and the line while it blocks, then how long it lasted, and
  `shoal_loop_blocks_total` goes up. `!burst 12` sends twelve messages at once: the rate limiter
  spaces them to the channel's bucket (about 8 seconds), and `shoal_rest_rate_limited_total` stays at
  zero because no request reaches Discord early enough to be refused.
- **Resharding.** `!reshard 4` starts four new shards beside the running ones; once they are all
  ready, the bot switches over in one step and closes the old ones. Nothing goes offline.
- **Member chunking** is off here: the bot does not ask for the Server Members intent. A bot that
  needs every member should weigh `chunk_guilds_at_startup` (each guild's member list fetched as it
  arrives) against fetching them only where needed with `await guild.chunk()`.
- **Slash commands are synced by hand** (`!sync`, or `!sync here` for one server): syncing on every
  start is rate limited, and a big bot restarts often.
- **Features are extensions.** Each file in `cogs/` is loaded at start; `!reload general` swaps in
  edited code without a restart.

For several processes or hosts sharing one bot, see [clusters](../clusters/) and
[workers](../workers/).
