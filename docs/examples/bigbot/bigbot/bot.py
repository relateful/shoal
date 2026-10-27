"""The bot: everything a large bot wires together once, and nothing about what it does.

What it does lives in `bigbot.cogs`, one extension per feature, loaded at start and reloadable.
"""

import logging
import pkgutil
import time

import shoal
from bigbot import cogs
from bigbot.config import Settings
from shoal import commands
from shoal.cache import CacheConfig, CachePolicy, CacheStore, EntityKind
from shoal.diagnostics import LoopMonitor
from shoal.gateway import FileSessionStore
from shoal.metrics.prometheus import PrometheusMetrics
from shoal.payloads import TransportCompression

log = logging.getLogger(__name__)

EXTENSIONS = [f"{cogs.__name__}.{module.name}" for module in pkgutil.iter_modules(cogs.__path__)]


def cache_config() -> CacheConfig:
    """Cache what the bot reads, bounded; skip what it never reads. Presences are the biggest stream."""
    return CacheConfig(
        policies={
            EntityKind.PRESENCE: CachePolicy.disabled(),
            EntityKind.MEMBER: CachePolicy(max_entries=500_000, ttl=6 * 3600),
            EntityKind.MESSAGE: CachePolicy(max_entries=10_000),
            EntityKind.USER: CachePolicy(max_entries=500_000),
        }
    )


class BigBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.metrics = PrometheusMetrics(namespace_labels={"bot": settings.bot_name})
        self.started = time.monotonic()
        self.monitor = LoopMonitor(threshold=0.25, metrics=self.metrics)
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        super().__init__(
            commands.when_mentioned_or(settings.prefix),
            intents=shoal.Intents.default().with_flags(message_content=True),
            help_command=commands.MinimalHelpCommand(),
            cache=CacheStore(cache_config(), metrics=self.metrics),
            metrics=self.metrics,
            # A restart resumes every shard instead of identifying again, and the cache is restored
            # from its snapshot, marked stale until Discord confirms each entry.
            session_store=FileSessionStore(settings.data_dir / "sessions"),
            cache_snapshot=settings.data_dir / "cache.snapshot",
            compression=TransportCompression.ZLIB_STREAM,
            large_threshold=50,
        )

    async def setup_hook(self) -> None:
        self.metrics.serve(self.settings.metrics_port, self.settings.metrics_address)
        log.info("metrics on http://%s:%d/metrics", self.settings.metrics_address, self.settings.metrics_port)
        await self.monitor.start()
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        log.info("loaded %d extensions: %s", len(EXTENSIONS), ", ".join(EXTENSIONS))
        # Slash commands are not synced at every start: a big bot restarts often, and syncing is
        # rate limited. The owner runs `!sync` after changing them.

    async def close(self) -> None:
        await self.monitor.stop()
        await super().close()  # sessions and the cache snapshot are saved here
