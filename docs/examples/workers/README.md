# Workers

A bot in three kinds of process: the **gateway** holds the shards and streams events, **workers** run
the bot's logic, and a **REST proxy** holds the token and the rate limits. Deploying new features
restarts only the workers: the shards stay connected, sessions are never lost, and no event storm
follows a deploy.

```
workers/
  .env.example        DISCORD_TOKEN, IPC_SECRET, PROXY_SECRET: copy to .env
  Dockerfile          one image for the three roles
  docker-compose.yml  the proxy, the gateway and two workers
  app/
    config.py         addresses and secrets shared by the roles
    proxy.py          `python -m app.proxy`: REST for everyone, one set of rate limits
    gateway.py        `python -m app.gateway`: the shards, streaming events over IPC
    worker.py         `python -m app.worker`: commands, fed by the gateway, replying through the proxy
```

## Run it

```bash
cp .env.example .env          # the token and two long random secrets
docker compose up --build
```

Then, in a server with the bot, `!where`. To deploy new worker code:

```bash
docker compose up -d --build worker-a worker-b
```

The gateway logs the workers disconnecting and reconnecting, and nothing else: no identify, no
`GUILD_CREATE` flood. Without Docker, run the three roles from this folder, in this order:

```bash
pip install -e "../../..[zstd]"   # Shoal from this clone (not on PyPI yet)
set -a; . ./.env; set +a
python -m app.proxy
python -m app.gateway             # in another terminal
python -m app.worker              # in another, as many as you like
```

## How the pieces talk

- **Gateway to workers: `shoal.ipc`.** `EventServer` publishes every dispatch; each worker's
  `EventClient` subscribes to the event names it needs (`EVENTS`) and the shards it handles
  (`WORKER_SHARDS`), and the server sends nothing else. Events travel as Discord's original JSON.
  A worker that falls behind is disconnected and reconnects, so it cannot grow the gateway's memory.
  The IPC secret is checked on connect.
- **Workers are ordinary bots.** `commands.Bot` with commands as usual; instead of `run`, the worker
  logs in and `feed`s each event it receives.
- **Everyone to Discord: the REST proxy.** `RestProxy` matches each request to the route Discord
  documents and waits in one rate limiter, so all processes together stay under the per-bot limits.
  Workers never hold the bot token, only the proxy's secret; a path that matches no documented route
  is refused without reaching Discord.
- **Splitting the load.** Give each worker its own shards (`WORKER_SHARDS=0,2,4` and `1,3,5`): every
  event goes to exactly one worker. Two workers on the same shards would both answer.

For workers that share events from a queue instead, so any free worker takes the next event and a
crashed worker's events are retried, use `RedisEventStream` and `RedisEventConsumer` with a `group`
([scaling guide](../../guide/scaling.md#through-a-redis-stream)).
