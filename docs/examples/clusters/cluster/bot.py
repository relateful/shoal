"""One cluster: its share of the shards, and everything the clusters share through Redis."""

import logging
import pkgutil
from urllib.parse import urlsplit

from redis.asyncio import Redis

import shoal
from cluster import cogs
from cluster.config import Settings
from shoal import commands
from shoal.cache import CacheConfig, CachePolicy, CacheStore, EntityKind
from shoal.gateway import cluster_shard_ids
from shoal.redis import (
    RedisCollections,
    RedisCommandRouter,
    RedisIdentifyLimiter,
    RedisRateLimiter,
    RedisSessionStore,
    RedisShardDirectory,
)
from shoal.rest import RestClient

log = logging.getLogger(__name__)

EXTENSIONS = [f"{cogs.__name__}.{module.name}" for module in pkgutil.iter_modules(cogs.__path__)]


def connect_redis(url: str) -> Redis:
    """A client for `redis://[:password@]host[:port][/db]`."""
    parts = urlsplit(url)
    return Redis(
        host=parts.hostname or "localhost",
        port=parts.port or 6379,
        db=int(parts.path.strip("/") or 0),
        password=parts.password,
        # A Redis that stops answering must not hold every request: past this, the rate limiter
        # falls back to local limits until Redis is back.
        socket_timeout=5,
    )


class ClusterBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # One connection pool for everything the clusters share.
        self.redis = connect_redis(settings.redis_url)
        self.directory = RedisShardDirectory(self.redis)
        shard_ids = cluster_shard_ids(settings.cluster_id, settings.cluster_count, settings.shard_count)
        rate_limiter = RedisRateLimiter(self.redis)
        super().__init__(
            commands.when_mentioned_or(settings.prefix),
            intents=shoal.Intents.default().with_flags(message_content=True),
            shard_count=settings.shard_count,
            shard_ids=list(shard_ids),
            cluster_name=settings.name,
            # Shards of every cluster identify through one limiter: never more than
            # `max_concurrency` at a time for the whole bot, as Discord requires.
            identify_limiter=RedisIdentifyLimiter(self.redis, max_concurrency=settings.max_concurrency),
            # A cluster restarted on another host resumes its shards' sessions.
            session_store=RedisSessionStore(self.redis),
            # Every cluster reports its shards; any cluster can show the whole bot.
            shard_directory=self.directory,
            # A gateway command for a guild goes out on the cluster that runs its shard.
            command_router=RedisCommandRouter(self.redis),
            # One cache for every cluster: what one cluster sees, all can read.
            cache=CacheStore(
                CacheConfig(policies={EntityKind.PRESENCE: CachePolicy.disabled()}),
                collections=RedisCollections(self.redis),
            ),
            # REST limits are per bot, not per process: the clusters count them together.
            rest=lambda token: RestClient(token, rate_limiter=rate_limiter),
        )

    async def setup_hook(self) -> None:
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        shards = cluster_shard_ids(
            self.settings.cluster_id, self.settings.cluster_count, self.settings.shard_count
        )
        log.info("%s runs shards %s of %d", self.settings.name, list(shards), self.settings.shard_count)

    async def close(self) -> None:
        await super().close()
        await self.redis.aclose()
