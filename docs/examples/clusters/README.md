# Clusters

One bot spread over several processes (or hosts), each running a share of the shards, that still
acts as one bot: shards identify in turn across every cluster, the REST rate limits are counted
together, any cluster can see every shard, and the cache is shared. Redis carries all of it.

```
clusters/
  .env.example        settings: copy to .env
  Dockerfile          one image for every cluster
  docker-compose.yml  Redis and two clusters
  cluster/
    __main__.py       `python -m cluster`
    config.py         CLUSTER_ID, CLUSTER_COUNT, SHARD_COUNT, ... checked at start
    bot.py            the shared wiring: identify, sessions, directory, router, rate limits, cache
    cogs/fleet.py     !where, !fleet, !servers, !ping
```

## Run it

```bash
cp .env.example .env          # then put your token in .env
docker compose up --build
```

Each cluster logs the shards it runs. In a server with the bot, `!fleet` lists every shard of every
cluster, whichever cluster answers. Without Docker, start a Redis, then one process per cluster:

```bash
pip install --pre "shoal[redis,zstd]"   # Shoal from PyPI
export DISCORD_TOKEN=... REDIS_URL=redis://localhost:6379/0 SHARD_COUNT=2 CLUSTER_COUNT=2
CLUSTER_ID=0 python -m cluster
CLUSTER_ID=1 python -m cluster          # in another terminal, or on another host
```

## What Redis shares

| Piece | Without it |
| --- | --- |
| `RedisIdentifyLimiter` | clusters identify at the same time and Discord refuses them: only `max_concurrency` shards may identify every five seconds, for the whole bot |
| `RedisRateLimiter` | each process counts REST limits alone, while Discord counts them per bot (and the invalid request ban per IP address) |
| `RedisSessionStore` | a cluster restarted on another host cannot resume its shards |
| `RedisShardDirectory` | a cluster only knows its own shards; `!fleet` could not show the rest |
| `RedisCommandRouter` | a gateway command for a guild (joining a voice channel, requesting soundboard sounds) only works on the cluster running its shard |
| `RedisCollections` | each cluster caches only its own guilds; `!servers` would count only those |

- `SHARD_COUNT` is fixed and every cluster agrees on it: `cluster_shard_ids` splits the shards
  evenly (cluster 0 of 2 runs shard 0, cluster 1 runs shard 1). Set `MAX_CONCURRENCY` from
  `GET /gateway/bot` (`session_start_limit.max_concurrency`).
- A message reaches only the cluster running its guild's shard, so each command is answered once.
- Keep Redis private and behind a password (`redis://:password@host:6379/0`): it holds session IDs
  and carries commands sent as the bot.
- Resharding a clustered bot: each cluster calls `bot.reshard(new_count, cluster_shard_ids(...))`
  with its share; the directory tells them when every new shard is ready, and they switch together.

To run the bot's logic apart from the gateway connections, see [workers](../workers/).
