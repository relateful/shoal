"""State shared by every process of a bot, in Redis (`pip install 'shoal[redis]'`).

    from redis.asyncio import Redis

    redis = Redis.from_url("redis://localhost")
    manager = ShardManager(
        ...,
        identify_limiter=RedisIdentifyLimiter(redis, max_concurrency=16),
        session_store=RedisSessionStore(redis),
    )
    rest = RestClient(token, rate_limiter=RedisRateLimiter(redis))
    cache = CacheStore(collections=RedisCollections(redis))

Clusters on several hosts then never identify more shards at once than Discord allows, resume each
other's sessions after a move, stay under the bot's global and per-IP request limits together, and
read one cache. `RedisEventStream` and `RedisEventConsumer` carry dispatch events from gateway
processes to workers through a Redis stream, as a broker in place of `shoal.ipc`;
`RedisShardDirectory` and `RedisCommandRouter` let clusters see each other's shards, send commands
for guilds another cluster runs, and reshard together; `RedisJobStore` keeps scheduled jobs
(`shoal.tasks`) that survive restarts, each run by one process. Every key starts
with `prefix` (`shoal` by default): give each bot its own. Times come from Redis's own clock, so the
hosts' clocks never matter.

Discord: https://docs.discord.com/developers/topics/rate-limits
"""

from shoal.redis import defaults
from shoal.redis.cache import RedisCollection, RedisCollections
from shoal.redis.cluster import RedisCommandRouter, RedisShardDirectory
from shoal.redis.events import RedisEventConsumer, RedisEventStream
from shoal.redis.identify import RedisIdentifyLimiter
from shoal.redis.jobs import RedisJobStore
from shoal.redis.ratelimit import RedisRateLimiter
from shoal.redis.sessions import RedisSessionStore

__all__ = [
    "RedisCollection",
    "RedisCollections",
    "RedisCommandRouter",
    "RedisEventConsumer",
    "RedisEventStream",
    "RedisIdentifyLimiter",
    "RedisJobStore",
    "RedisRateLimiter",
    "RedisSessionStore",
    "RedisShardDirectory",
    "defaults",
]
