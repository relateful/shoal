# Scaling, sharding and IPC

## Shards and identify concurrency

Discord lets a bot identify `max_concurrency` shards every five seconds. Shoal follows that exactly:

```python
from shoal.gateway import LocalIdentifyLimiter, ShardManager
from shoal.payloads import Intents
from shoal.rest import RestClient, Token

async with RestClient(Token.bot(token)) as rest:
    gateway = await rest.gateway.get_bot()

manager = ShardManager(
    token=token,
    intents=Intents.default(),
    dispatch=handle,
    shard_count=gateway.shards,
    gateway_url=gateway.url,
    identify_limiter=LocalIdentifyLimiter(gateway.session_start_limit.max_concurrency),
)
await manager.run()
```

With `max_concurrency` 16 and 512 shards that is under three minutes of startup instead of the 43
discord.py takes by identifying one shard every five seconds.

## Clusters

Split the shards into clusters, one per process or host:

```python
from shoal.gateway import cluster_shard_ids

shard_ids = cluster_shard_ids(cluster_id, cluster_count, gateway.shards)
manager = ShardManager(..., shard_count=gateway.shards, shard_ids=shard_ids)
```

Clusters in different processes still act as one bot. Four protocols carry what they share, and
`shoal.redis` implements each of them (install `shoal[redis]`):

```python
from redis.asyncio import Redis
from shoal.redis import (
    RedisCommandRouter,
    RedisIdentifyLimiter,
    RedisSessionStore,
    RedisShardDirectory,
)

redis = Redis.from_url("redis://localhost")
manager = ShardManager(
    ...,
    identify_limiter=RedisIdentifyLimiter(redis, max_concurrency=gateway.session_start_limit.max_concurrency),
    session_store=RedisSessionStore(redis),
    directory=RedisShardDirectory(redis),
    router=RedisCommandRouter(redis),
    name=f"cluster-{cluster_id}",
)
```

- **Identify** (`IdentifyLimiter`): one shard per bucket (`shard_id % max_concurrency`) identifies
  every five seconds across every cluster, timed by Redis's clock so hosts with drifting clocks
  still agree.
- **Sessions** (`SessionStore`): a cluster restarted on another host resumes its shards.
- **The shard directory** (`ShardDirectory`): every manager reports its shards (state, latency,
  which cluster) every five seconds, so any process can show the whole bot with
  `await directory.statuses(shard_count)`. A cluster that stops reporting drops out after 15
  seconds.
- **Command routing** (`CommandRouter`): a gateway command for a guild goes out on that guild's
  shard, whichever cluster runs it. `manager.send_to_guild(guild_id, opcode, payload)` and
  `request_soundboard_sounds` route through it, so joining a voice channel or requesting soundboard
  sounds works from any cluster. The answers (voice server details, `SOUNDBOARD_SOUNDS`) arrive as
  events on the cluster running the shard; with `shoal.ipc` or a Redis stream they reach every
  worker that subscribes.

`Client` takes the same through `identify_limiter=`, `session_store=`, `shard_directory=`,
`command_router=` and `cluster_name=`, and `client.shard_manager.send_to_guild(...)` sends a command
for any guild. Give each bot its own `prefix=` when several share one Redis, and keep Redis on a
private network behind a password: it holds session IDs and, through the router, takes commands
sent as the bot. For clusters in one process, `MemoryShardDirectory` and `MemoryCommandRouter` do the
same in memory.

## Rate limits across processes

REST limits are counted per process: each `RestClient` keeps its own buckets, global limit and
invalid request guard, while Discord counts the global limit per bot and the invalid request ban
(10,000 in 10 minutes) per IP address. Processes of one bot should share a `RedisRateLimiter`:

```python
from shoal.redis import RedisRateLimiter
from shoal.rest import RestClient, Token

rest = RestClient(Token.bot(token), rate_limiter=RedisRateLimiter(redis))
```

Each process still orders its own requests with a local limiter; Redis holds the counts every
process shares: what is left in each route's bucket, the global limit, global 429 pauses and the
invalid responses of the last ten minutes. Processes of different bots on one IP share the invalid
request window by passing the same `invalid_key=`. Responses are recorded in the background, so a
slow Redis never delays a request's answer. While Redis cannot be reached, each process keeps to its
own limits and the outage is logged; give the Redis client a `socket_timeout`, or a Redis that stops
answering holds every request.

### A REST proxy

Without Redis, route every process's REST through one `RestProxy`, which holds the token and the
rate limits:

```python
from shoal.rest import RestClient, RestProxy, Token

# the proxy process: the only one with the bot token
async with RestProxy(Token.bot(bot_token), secret=proxy_secret, host="10.0.0.5", port=8080):
    await asyncio.Event().wait()

# every other process: only the proxy's secret
rest = RestClient(None, base_url="http://10.0.0.5:8080/api", proxy_secret=proxy_secret)
```

The proxy matches each request to the route Discord documents for it and waits in its own limiter,
so all the processes together stay under the bucket, global and invalid request limits. It sends
each request once: a 429 or error from Discord goes back to the caller, whose client retries it
through the proxy. A request the limiter would hold longer than `max_rate_limit_wait` is answered
with a 429 of the `shared` scope, which the caller's client does not count as an invalid request.

Every request must carry the proxy's secret, routes authorised by a token in their path (webhooks,
interaction responses) included, so nothing else that reaches the port can spend the bot's limits.
The bot token never leaves the proxy. A path that matches no documented route is answered with a 404
and never reaches Discord. Pass `ssl=` to serve HTTPS beyond one host, and give the proxy a
`RedisRateLimiter` to run several side by side.

## Resharding without downtime

Discord lets sessions with different shard counts run side by side, so a bot can move to a new
shard count while the old shards keep serving:

```python
# in every cluster, with its share of the new shards
await manager.reshard(new_count, cluster_shard_ids(cluster_id, cluster_count, new_count))
```

The new shards identify beside the running ones, through the same identify limiter, and their
events are held back. Once the directory shows every shard of the new count ready, in every
cluster, each manager switches to the new shards in one step and closes the old ones, whose
sessions end. Each new shard then keeps its session in the session store, which keeps sessions per
shard count, so the two counts never overwrite each other's.

- An event Discord sends to both sessions around the switch can be dispatched twice, and clusters
  switch within about a second of each other; handlers that must never repeat should check IDs.
- Every new shard is a new session: `Client.reshard` waits for the day's session starts first.
- Without a directory, a manager switches once its own new shards are ready, which is right only
  when it runs every shard.
- A presence set during the reshard reaches the new shards too.
- Cancel `reshard` to abandon it before the switch: the new shards close and the old ones keep
  running. Closing the manager abandons it the same way.

## Sessions that survive restarts

```python
from shoal.gateway import FileSessionStore

manager = ShardManager(..., session_store=FileSessionStore("sessions/"))
...
await manager.close()  # keeps the sessions resumable and saves them
```

Session files hold what resumes a session, so they are created readable by the bot's user only. On
Windows that mode is not enforced and the files take the directory's access rules: use a directory
only the bot's user can read.

On the next start each shard resumes its saved session instead of identifying, so a deploy costs no
session starts and no `GUILD_CREATE` storm. Sessions older than three minutes are not attempted.

If a resume URL stops working (a timeout, an HTTP 503 during the handshake, an early close), the shard
resumes through the main gateway instead, and identifies a new session if that fails too, as Discord
recommends.

## Separate processes with IPC

Run the gateway in one process and your bot logic in others:

```python
# gateway process
server = EventServer(token=secret, host="127.0.0.1", port=7700)
await server.start()
manager = ShardManager(..., dispatch=server.publish)

# each worker process
async with EventClient("127.0.0.1", 7700, token=secret, events=["INTERACTION_CREATE"]) as client:
    async for event in client:
        ...
```

- Workers subscribe by shard and by event name; the server only sends what each asked for.
- Event data travels as Discord's original JSON bytes and is never re-encoded.
- Each worker has a bounded queue. One that falls behind is disconnected and reconnects, instead of
  growing the gateway process's memory.
- The token is checked in constant time. Across hosts, pass an `ssl` context to both ends.
- Restarting a worker never touches the gateway connection or its sessions.

On one host, listen on a Unix socket instead of TCP (not on Windows). The socket is created readable
and writable by the bot's user only:

```python
server = EventServer(token=secret, path="/run/bot/events.sock")
client = EventClient.unix("/run/bot/events.sock", token=secret, events=["INTERACTION_CREATE"])
```

### Through a Redis stream

With a broker, the gateway process holds no connection to its workers: events wait in a Redis stream
until read. Workers in a `group` share the events, each going to one of them, so adding a worker
spreads the load; an event a worker read but never finished (it crashed) is read again when it comes
back under the same `consumer` name, or taken over by another after `claim_after` seconds:

```python
from shoal.redis import RedisEventConsumer, RedisEventStream

# gateway process
stream = RedisEventStream(redis)
manager = ShardManager(..., dispatch=stream.publish)

# each worker process
async for event in RedisEventConsumer(redis, group="workers", consumer=f"worker-{n}"):
    ...
```

Without a `group`, every consumer receives every event published after it started; a new group
starts with the events published after its first consumer joined. Give every consumer of a group
the same `shard_ids` and `events`: an event one of them skips is acknowledged, and so lost to the
group. Group consumers read ten events at a time, so keep `claim_after` (60 seconds) well above how
long ten take to handle. The stream keeps about the last 100,000 events (`max_length=`), so a worker
away for longer loses the oldest. Groups need Redis 6.2 or later.

Events hold message contents and interaction tokens: keep Redis on a private network, behind a
password.

On one host, a Unix socket (`EventServer(path=...)`) is created readable by the bot's user only once
it is bound: put it in a directory only that user can enter.
