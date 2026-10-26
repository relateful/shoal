"""Storage for one entity kind.

`CacheCollection` is async so an implementation can live outside the process (Redis, a database) and
be shared by several shards or a dashboard. `MemoryCollection` is the in-process default.

`CacheStore` reads an entry and then writes it (`edit`, reconciling, sweeping). In memory nothing runs
in between; an implementation shared by several processes must make each call atomic and accept that
a write from another process between a read and a write is overwritten.

The `peek` methods read synchronously what this process holds, for lookups that cannot await, like
`guild.get_member`. An implementation backed by a remote store answers them from a local
copy it keeps, or with nothing.
"""

from collections import OrderedDict
from collections.abc import Hashable
from typing import Protocol, final, override

from shoal.cache.entry import Entry
from shoal.core.clock import Clock
from shoal.core.snowflake import Snowflake


class CacheCollection[K: Hashable, V](Protocol):
    """Keyed storage of cache entries for one entity kind."""

    async def get(self, key: K) -> Entry[V] | None:
        """Return the entry for `key`, or `None` if absent or expired."""
        ...

    async def set(self, key: K, entry: Entry[V]) -> None:
        """Insert or replace the entry for `key`."""
        ...

    async def delete(self, key: K) -> Entry[V] | None:
        """Remove and return the entry for `key`, if present."""
        ...

    async def items(self) -> list[tuple[K, Entry[V]]]:
        """Every live entry. Used for snapshots and sweeps, not on hot paths."""
        ...

    async def scoped(self, scope: Snowflake | None) -> list[tuple[K, Entry[V]]]:
        """Every live entry whose `scope` is `scope` (`None`: entries that belong to no guild).

        Guild events (a reconcile, a role or channel deletion) touch one guild, so this must cost
        in proportion to that guild, not to the whole cache.
        """
        ...

    async def clear(self) -> None:
        """Remove every entry."""
        ...

    async def size(self) -> int:
        """How many entries are stored (expired ones may still be counted until accessed)."""
        ...

    def peek(self, key: K) -> Entry[V] | None:
        """`get`, synchronously, from what this process holds."""
        ...

    def peek_scoped(self, scope: Snowflake | None) -> list[tuple[K, Entry[V]]]:
        """`scoped`, synchronously, from what this process holds."""
        ...

    def peek_items(self) -> list[tuple[K, Entry[V]]]:
        """`items`, synchronously, from what this process holds."""
        ...


@final
class MemoryCollection[K: Hashable, V](CacheCollection[K, V]):
    """An in-process LRU with optional size bound and TTL, indexed by scope.

    Args:
        clock: Time source; TTL is measured against `Freshness.observed_at` (wall time), so entries
            restored from a snapshot age correctly across the restart.
        max_entries: Evict the least recently used entry beyond this size. `None` is unbounded.
        ttl: Seconds an entry stays valid after it was observed. `None` never expires.
    """

    __slots__ = ("_clock", "_entries", "_max_entries", "_scopes", "_ttl")

    def __init__(self, clock: Clock, *, max_entries: int | None = None, ttl: float | None = None) -> None:
        """Create an empty collection; see the class docstring for the arguments."""
        self._clock: Clock = clock
        self._max_entries: int | None = max_entries
        self._ttl: float | None = ttl
        self._entries: OrderedDict[K, Entry[V]] = OrderedDict()
        self._scopes: dict[Snowflake | None, set[K]] = {}

    def _expired(self, entry: Entry[V], now: float) -> bool:
        return self._ttl is not None and now - entry.freshness.observed_at >= self._ttl

    def _remove(self, key: K) -> Entry[V] | None:
        entry = self._entries.pop(key, None)
        if entry is not None:
            keys = self._scopes[entry.scope]
            keys.discard(key)
            if not keys:
                del self._scopes[entry.scope]
        return entry

    @override
    async def get(self, key: K) -> Entry[V] | None:
        return self.peek(key)

    @override
    def peek(self, key: K) -> Entry[V] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if self._expired(entry, self._clock.wall()):
            self._remove(key)
            return None
        self._entries.move_to_end(key)
        return entry

    @override
    async def set(self, key: K, entry: Entry[V]) -> None:
        previous = self._entries.get(key)
        if previous is not None and previous.scope != entry.scope:
            self._remove(key)
        self._entries[key] = entry
        self._entries.move_to_end(key)
        self._scopes.setdefault(entry.scope, set()).add(key)
        if self._max_entries is not None:
            while len(self._entries) > self._max_entries:
                self._remove(next(iter(self._entries)))

    @override
    async def delete(self, key: K) -> Entry[V] | None:
        return self._remove(key)

    @override
    async def items(self) -> list[tuple[K, Entry[V]]]:
        return self.peek_items()

    @override
    def peek_items(self) -> list[tuple[K, Entry[V]]]:
        now = self._clock.wall()
        for key in [key for key, entry in self._entries.items() if self._expired(entry, now)]:
            self._remove(key)
        return list(self._entries.items())

    @override
    async def scoped(self, scope: Snowflake | None) -> list[tuple[K, Entry[V]]]:
        return self.peek_scoped(scope)

    @override
    def peek_scoped(self, scope: Snowflake | None) -> list[tuple[K, Entry[V]]]:
        now = self._clock.wall()
        live: list[tuple[K, Entry[V]]] = []
        for key in list(self._scopes.get(scope, ())):
            entry = self._entries[key]
            if self._expired(entry, now):
                self._remove(key)
            else:
                live.append((key, entry))
        return live

    @override
    async def clear(self) -> None:
        self._entries.clear()
        self._scopes.clear()

    @override
    async def size(self) -> int:
        return len(self._entries)


@final
class NullCollection[K: Hashable, V](CacheCollection[K, V]):
    """Stores nothing. Used for kinds whose policy is disabled, so callers never branch on it."""

    __slots__ = ()

    @override
    async def get(self, key: K) -> Entry[V] | None:
        return None

    @override
    async def set(self, key: K, entry: Entry[V]) -> None:
        return

    @override
    async def delete(self, key: K) -> Entry[V] | None:
        return None

    @override
    async def items(self) -> list[tuple[K, Entry[V]]]:
        return []

    @override
    async def scoped(self, scope: Snowflake | None) -> list[tuple[K, Entry[V]]]:
        return []

    @override
    async def clear(self) -> None:
        return

    @override
    async def size(self) -> int:
        return 0

    @override
    def peek(self, key: K) -> Entry[V] | None:
        return None

    @override
    def peek_scoped(self, scope: Snowflake | None) -> list[tuple[K, Entry[V]]]:
        return []

    @override
    def peek_items(self) -> list[tuple[K, Entry[V]]]:
        return []
