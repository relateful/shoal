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

Clusters in different processes need a shared `IdentifyLimiter` (so together they never exceed
`max_concurrency`) and a shared `SessionStore`. Both are protocols; a Redis implementation is on the
[roadmap](../roadmap.md).

## Sessions that survive restarts

```python
from shoal.gateway import FileSessionStore

manager = ShardManager(..., session_store=FileSessionStore("sessions/"))
...
await manager.close()  # keeps the sessions resumable and saves them
```

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
