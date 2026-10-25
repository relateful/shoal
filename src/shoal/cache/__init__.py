"""A policy-driven cache that survives restarts and knows how fresh every entry is.

See `shoal.cache.store` for how freshness, snapshots and reconciliation fit together.
"""

from shoal.cache import defaults
from shoal.cache.collection import CacheCollection, MemoryCollection, NullCollection
from shoal.cache.entry import Entry, Freshness, Source
from shoal.cache.guild import CachedGuild
from shoal.cache.policy import DEFAULT_POLICIES, CacheConfig, CachePolicy, EntityKind, RestartStrategy
from shoal.cache.store import CacheStore, GuildUserKey, ShardMark, Snapshot
from shoal.cache.updater import CacheUpdater

__all__ = [
    "DEFAULT_POLICIES",
    "CacheCollection",
    "CacheConfig",
    "CachePolicy",
    "CacheStore",
    "CacheUpdater",
    "CachedGuild",
    "EntityKind",
    "Entry",
    "Freshness",
    "GuildUserKey",
    "MemoryCollection",
    "NullCollection",
    "RestartStrategy",
    "ShardMark",
    "Snapshot",
    "Source",
    "defaults",
]
