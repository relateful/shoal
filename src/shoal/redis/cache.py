"""A cache shared by every process of a bot, in Redis.

    cache = CacheStore(collections=RedisCollections(redis))

Each enabled entity kind is stored in Redis: a hash per entry holding the entry and the guild it
belongs to (expiring as its policy's `ttl` says), and sorted sets indexing the kind's entries, all of
them and per guild, so a guild's entries are found without scanning. Index members are scored by
when their entry expires, so the indexes drop expired entries as Redis's clock passes them. Every
write, delete and cleanup runs as one script: two processes never leave an entry out of its indexes.

Reads go to Redis; the synchronous `peek` reads answer from what this process last wrote or read,
kept in a local copy bounded by the policy's `max_entries`. Redis's memory limit bounds what Redis
keeps: use the `noeviction` or a `volatile-*` policy, so Redis never evicts an index. Entries are
msgpack, the same encoding as cache snapshots; the client must return bytes (no
`decode_responses`). Run one Redis (or a replicated one behind Sentinel), not Redis Cluster: each
script touches several keys.
"""

from collections.abc import Hashable, Sequence
from typing import Final, cast, final, override

from shoal.cache.collection import CacheCollection, CollectionFactory, MemoryCollection
from shoal.cache.entry import Entry
from shoal.cache.policy import CachePolicy, EntityKind
from shoal.core.clock import Clock, SystemClock
from shoal.core.codec import decode_json, decode_msgpack, encode_json, encode_msgpack
from shoal.core.snowflake import Snowflake
from shoal.redis.base import NOW_MS, Redis, key_of, text_of
from shoal.redis.defaults import KEY_BATCH, KEY_PREFIX

_NO_SCOPE: Final = "none"
"""The scope name of entries that belong to no guild."""

_SET: Final = (
    NOW_MS
    + """
local ttl = tonumber(ARGV[4])
local expiry = '+inf'
if ttl > 0 then expiry = now + ttl end
local old = redis.call('HGET', KEYS[1], 's')
if old and old ~= ARGV[3] then
  redis.call('ZREM', ARGV[5] .. old, ARGV[1])
end
redis.call('HSET', KEYS[1], 'd', ARGV[2], 's', ARGV[3])
if ttl > 0 then
  redis.call('PEXPIRE', KEYS[1], ttl)
else
  redis.call('PERSIST', KEYS[1])
end
redis.call('ZADD', KEYS[2], expiry, ARGV[1])
redis.call('ZADD', KEYS[3], expiry, ARGV[1])
redis.call('SADD', KEYS[4], KEYS[3])
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', now)
return 0
"""
)
"""Store an entry and index it, moving it out of its old guild's index.

KEYS: the entry, the kind's index, the entry's guild index, the set of guild indexes. ARGV: the
field, the entry, the guild's name, the TTL in ms (0: none), what guild index keys start with.
"""

_DELETE: Final = """
local found = redis.call('HMGET', KEYS[1], 'd', 's')
redis.call('DEL', KEYS[1])
redis.call('ZREM', KEYS[2], ARGV[1])
if found[2] then
  redis.call('ZREM', ARGV[2] .. found[2], ARGV[1])
end
return found[1]
"""
"""Remove an entry and its index members; returns the entry, or nil.

KEYS: the entry, the kind's index. ARGV: the field, what guild index keys start with.
"""

_READ: Final = """
local out = {}
for index = 1, #ARGV - 1 do
  local field = ARGV[index + 1]
  local data = redis.call('HGET', ARGV[1] .. field, 'd')
  if data then
    table.insert(out, field)
    table.insert(out, data)
  else
    redis.call('ZREM', KEYS[1], field)
  end
end
return out
"""
"""Read the entries of some members of an index, dropping members whose entry is gone.

KEYS: the index. ARGV: what entry keys start with, then the fields.
"""

_SCAN: Final = "return redis.call('ZSCAN', KEYS[1], ARGV[1], 'COUNT', ARGV[2])"
"""One page of an index. KEYS: the index. ARGV: the cursor, how many members to ask for."""

_SIZE: Final = (
    NOW_MS
    + """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
return redis.call('ZCARD', KEYS[1])
"""
)
"""How many entries an index lists that have not expired."""


@final
class RedisCollection[K: Hashable, V](CacheCollection[K, V]):
    """One entity kind's entries in Redis, with a local copy for synchronous reads.

    Args:
        redis: The client to store entries with; it must return bytes.
        name: The kind's name in the keys (`member`).
        key_type: The type of its keys, to read them back.
        entry_type: The type of its entries, to read them back.
        ttl: Seconds an entry lives after it is written; `None` keeps it.
        local: The local copy `peek` reads from.
        prefix: What the keys start with; give each bot its own.
    """

    __slots__ = ("_entry_type", "_key_type", "_local", "_name", "_prefix", "_redis", "_ttl")

    def __init__(
        self,
        redis: Redis,
        *,
        name: str,
        key_type: type[K],
        entry_type: type[Entry[V]],
        ttl: float | None,
        local: MemoryCollection[K, V],
        prefix: str = KEY_PREFIX,
    ) -> None:
        """Create a collection; see the class docstring for the arguments."""
        self._redis: Redis = redis
        self._name: str = name
        self._key_type: type[K] = key_type
        self._entry_type: type[Entry[V]] = entry_type
        self._ttl: float | None = ttl
        self._local: MemoryCollection[K, V] = local
        self._prefix: str = prefix

    def _entry_key(self, field: str) -> str:
        return key_of(self._prefix, "cache", self._name, "entry", field)

    def _all_key(self) -> str:
        return key_of(self._prefix, "cache", self._name, "all")

    def _scopes_key(self) -> str:
        return key_of(self._prefix, "cache", self._name, "scopes")

    def _scope_key(self, scope: Snowflake | None) -> str:
        return key_of(self._prefix, "cache", self._name, "scope", _scope_name(scope))

    def _field(self, key: K) -> str:
        return encode_json(key).decode()

    def _read_key(self, field: bytes | str) -> K:
        return decode_json(text_of(field), self._key_type)

    @override
    async def get(self, key: K) -> Entry[V] | None:
        data = await self._redis.hget(self._entry_key(self._field(key)), "d")
        if data is None:
            await self._local.delete(key)
            return None
        entry = decode_msgpack(text_of(data), self._entry_type)
        await self._local.set(key, entry)
        return entry

    @override
    async def set(self, key: K, entry: Entry[V]) -> None:
        field = self._field(key)
        keys = [self._entry_key(field), self._all_key(), self._scope_key(entry.scope), self._scopes_key()]
        ttl = 0 if self._ttl is None else max(round(self._ttl * 1000), 1)
        scope_prefix = self._scope_key(None).removesuffix(_NO_SCOPE)
        arguments: list[str | bytes] = [
            field,
            encode_msgpack(entry),
            _scope_name(entry.scope),
            str(ttl),
            scope_prefix,
        ]
        await self._redis.eval(_SET, len(keys), *keys, *arguments)
        await self._local.set(key, entry)

    @override
    async def delete(self, key: K) -> Entry[V] | None:
        field = self._field(key)
        scope_prefix = self._scope_key(None).removesuffix(_NO_SCOPE)
        keys = [self._entry_key(field), self._all_key()]
        data: object = await self._redis.eval(_DELETE, len(keys), *keys, field, scope_prefix)
        await self._local.delete(key)
        if not isinstance(data, bytes | str):
            return None
        return decode_msgpack(text_of(data), self._entry_type)

    async def _read(self, index: str) -> list[tuple[K, Entry[V]]]:
        """The live entries `index` lists, dropping members whose entry is gone."""
        found: list[tuple[K, Entry[V]]] = []
        entry_prefix = self._entry_key("")
        cursor = 0
        while True:
            cursor, fields = await self._scan(index, cursor)
            if fields:
                answer: object = await self._redis.eval(_READ, 1, index, entry_prefix, *fields)
                found.extend(self._entries_of(answer))
            if cursor == 0:
                return found

    async def _scan(self, index: str, cursor: int) -> tuple[int, list[str]]:
        """One page of an index's members, and the cursor of the next (0 after the last)."""
        answer: object = await self._redis.eval(_SCAN, 1, index, str(cursor), str(KEY_BATCH))
        # ZSCAN answers [next cursor, [member, score, member, score...]].
        page = cast("tuple[bytes | str, Sequence[bytes | str]]", answer)
        return int(page[0]), [text_of(member).decode() for member in page[1][::2]]

    def _entries_of(self, answer: object) -> list[tuple[K, Entry[V]]]:
        # The read script answers a flat list of field, entry, field, entry...
        flat = cast("Sequence[bytes | str]", answer)
        return [
            (self._read_key(flat[index]), decode_msgpack(text_of(flat[index + 1]), self._entry_type))
            for index in range(0, len(flat), 2)
        ]

    @override
    async def items(self) -> list[tuple[K, Entry[V]]]:
        return await self._read(self._all_key())

    @override
    async def scoped(self, scope: Snowflake | None) -> list[tuple[K, Entry[V]]]:
        return await self._read(self._scope_key(scope))

    @override
    async def clear(self) -> None:
        cursor = 0
        while True:
            cursor, fields = await self._scan(self._all_key(), cursor)
            entries = [self._entry_key(field) for field in fields]
            if entries:
                await self._redis.delete(*entries)
            if cursor == 0:
                break
        scopes = [text_of(scope).decode() for scope in await self._redis.smembers(self._scopes_key())]
        await self._redis.delete(self._all_key(), self._scopes_key(), *scopes)
        await self._local.clear()

    @override
    async def size(self) -> int:
        count: object = await self._redis.eval(_SIZE, 1, self._all_key())
        return count if isinstance(count, int) else 0

    @override
    def peek(self, key: K) -> Entry[V] | None:
        return self._local.peek(key)

    @override
    def peek_scoped(self, scope: Snowflake | None) -> list[tuple[K, Entry[V]]]:
        return self._local.peek_scoped(scope)

    @override
    def peek_items(self) -> list[tuple[K, Entry[V]]]:
        return self._local.peek_items()


def _scope_name(scope: Snowflake | None) -> str:
    return _NO_SCOPE if scope is None else str(scope)


@final
class RedisCollections(CollectionFactory):
    """Stores every enabled kind in Redis: `CacheStore(collections=RedisCollections(redis))`.

    Args:
        redis: The client to store entries with.
        prefix: What the keys start with; give each bot its own.
        clock: Times the local copies.

    Raises:
        ValueError: The client decodes responses to text; entries are binary.
    """

    __slots__ = ("_clock", "_prefix", "_redis")

    def __init__(self, redis: Redis, *, prefix: str = KEY_PREFIX, clock: Clock | None = None) -> None:
        """Create the factory; see the class docstring for the arguments."""
        if redis.connection_pool.connection_kwargs.get("decode_responses"):
            msg = "the cache stores binary entries: create the Redis client without decode_responses"
            raise ValueError(msg)
        self._redis: Redis = redis
        self._prefix: str = prefix
        self._clock: Clock = clock or SystemClock()

    @property
    @override
    def shared(self) -> bool:
        return True

    @override
    def __call__[K: Hashable, V](
        self, kind: EntityKind, policy: CachePolicy, key: type[K], entry: type[Entry[V]]
    ) -> CacheCollection[K, V]:
        return RedisCollection[K, V](
            self._redis,
            name=kind.value,
            key_type=key,
            entry_type=entry,
            ttl=policy.ttl,
            local=MemoryCollection[K, V](self._clock, max_entries=policy.max_entries, ttl=policy.ttl),
            prefix=self._prefix,
        )
