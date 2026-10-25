"""The cache: one collection per entity kind, per-shard freshness, and snapshots.

**Freshness.** Every write gets the next *revision* of a store-wide counter and records the shard
that delivered it. When a shard starts a new gateway session, everything that shard wrote before
becomes *stale*: it may still be correct, but Discord has not confirmed it in the current session.
Other shards are unaffected, so one shard re-identifying never invalidates the rest of the cache.
Reads can ask for fresh data only (`fresh_only=True`) or accept stale data for speed.

**Warm restarts.** `save_snapshot` writes every persisted kind to disk, together with the last
sequence number the cache applied from each shard; `load_snapshot` brings it back on the next start,
with every entry stale. `CacheUpdater` then settles each shard as it comes back:

- **Resumed:** Discord replays what the shard missed. If the replay starts right after the sequence
  the snapshot was taken at, snapshot plus replay is exact and the shard's restored entries become
  fresh again. Otherwise (the snapshot was saved before the session, or long after) they stay stale,
  and are replaced as events update them. Save the snapshot after `ShardManager.close()` so the two
  line up.
- **New session:** each `GUILD_CREATE` replaces its guild's data and `reconcile_guild` drops whatever
  that guild no longer has. `sweep_stale()`, called once every shard is ready, removes what is left:
  guilds the bot left while it was offline. Guilds in an outage are kept.

Either way the bot answers from the snapshot during startup instead of from an empty cache.

Every kind is registered once in `__init__`; cleanup and sweeping iterate that registry, so a kind can
never be forgotten by one of them.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, final

import msgspec

from shoal.cache.collection import CacheCollection, MemoryCollection, NullCollection
from shoal.cache.defaults import SNAPSHOT_FORMAT
from shoal.cache.entry import Entry, Freshness, Source
from shoal.cache.guild import CachedGuild
from shoal.cache.policy import CacheConfig, EntityKind, RestartStrategy
from shoal.core.clock import Clock, SystemClock
from shoal.core.codec import PayloadDecodeError, decode_msgpack, encode_msgpack
from shoal.core.files import write_private
from shoal.core.metrics import CACHE_LOOKUPS, Metrics, NoopMetrics
from shoal.core.snowflake import Snowflake
from shoal.payloads.channel import Channel
from shoal.payloads.emoji import Emoji
from shoal.payloads.gateway_events import Presence
from shoal.payloads.guild import GuildMember
from shoal.payloads.message import Message
from shoal.payloads.permissions import Role
from shoal.payloads.user import User
from shoal.payloads.voice import VoiceState

_log = logging.getLogger("shoal.cache")

_RESTORE_BATCH: Final = 1000
"""Entries restored between yields to the event loop, so loading a large snapshot never blocks it."""

type GuildUserKey = tuple[Snowflake, Snowflake]
"""Members, presences and voice states are keyed by `(guild_id, user_id)`."""

type Rows[K, V] = list[tuple[K, Entry[V]]]


class ShardMark(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Where one shard's session stood when a snapshot was taken."""

    stale_before: int
    """Entries from this shard with a lower revision were already stale."""
    sequence: int | None
    """The last sequence number applied from the shard, if any."""


class Snapshot(msgspec.Struct, kw_only=True, gc=False):
    """The on-disk form of a cache. Each kind's field is named after its `EntityKind`'s collection."""

    format: int
    saved_at: float
    revision: int
    shards: dict[int, ShardMark] = msgspec.field(default_factory=dict[int, ShardMark])
    channels: Rows[Snowflake, Channel] = msgspec.field(default_factory=list[tuple[Snowflake, Entry[Channel]]])
    emojis: Rows[Snowflake, Emoji] = msgspec.field(default_factory=list[tuple[Snowflake, Entry[Emoji]]])
    guilds: Rows[Snowflake, CachedGuild] = msgspec.field(
        default_factory=list[tuple[Snowflake, Entry[CachedGuild]]]
    )
    members: Rows[GuildUserKey, GuildMember] = msgspec.field(
        default_factory=list[tuple[GuildUserKey, Entry[GuildMember]]]
    )
    messages: Rows[Snowflake, Message] = msgspec.field(default_factory=list[tuple[Snowflake, Entry[Message]]])
    presences: Rows[GuildUserKey, Presence] = msgspec.field(
        default_factory=list[tuple[GuildUserKey, Entry[Presence]]]
    )
    roles: Rows[Snowflake, Role] = msgspec.field(default_factory=list[tuple[Snowflake, Entry[Role]]])
    users: Rows[Snowflake, User] = msgspec.field(default_factory=list[tuple[Snowflake, Entry[User]]])
    voice_states: Rows[GuildUserKey, VoiceState] = msgspec.field(
        default_factory=list[tuple[GuildUserKey, Entry[VoiceState]]]
    )


class _SnapshotFormat(msgspec.Struct, gc=False):
    """Read first, so a snapshot of another format is recognised without decoding its entries."""

    format: int


type _Doomed = Callable[[Freshness, Snowflake | None], bool]
"""Decides from an entry's provenance and scope whether it is removed."""


def _everything(freshness: Freshness, scope: Snowflake | None) -> bool:
    del freshness, scope
    return True


class _Drop(Protocol):
    def __call__(self, scope: Snowflake | None, doomed: _Doomed, *, every_scope: bool) -> Awaitable[int]: ...


@dataclass(frozen=True, slots=True)
class _Registration:
    """Type-erased operations on one kind's collection, so the store can loop over every kind."""

    kind: EntityKind
    drop: _Drop
    """Removes the entries `doomed` selects, in `scope` or (with `every_scope`) everywhere."""


@final
class CacheStore:
    """Every cached entity, with freshness tracking and snapshots.

    Args:
        config: Policies and restart strategy. Defaults to `CacheConfig()`.
        clock: Time source.
        metrics: Receives lookup results (hit, stale, miss) per entity kind.

    Guild entries are stored without their `roles` and `emojis` lists; those live in the `roles` and
    `emojis` collections, so each object has exactly one cached copy.
    """

    __slots__ = (
        "_clock",
        "_config",
        "_first_sequence",
        "_floor",
        "_identified",
        "_kinds",
        "_metrics",
        "_registry",
        "_restored",
        "_revision",
        "_sequences",
        "_stale_before",
        "_unavailable",
        "channels",
        "emojis",
        "guilds",
        "members",
        "messages",
        "presences",
        "roles",
        "users",
        "voice_states",
    )

    def __init__(
        self, config: CacheConfig | None = None, *, clock: Clock | None = None, metrics: Metrics | None = None
    ) -> None:
        """Create an empty store; see the class docstring for the arguments."""
        self._config: CacheConfig = config or CacheConfig()
        self._clock: Clock = clock or SystemClock()
        self._metrics: Metrics = metrics or NoopMetrics()
        self._revision: int = 0
        self._floor: int = 0
        """Entries below this revision are stale unless their shard's session says otherwise."""
        self._stale_before: dict[int, int] = {}
        """Per shard with a session in this process: entries it wrote below this revision are stale."""
        self._sequences: dict[int, int] = {}
        self._restored: dict[int, ShardMark] = {}
        """Shards in the loaded snapshot that have neither resumed nor identified yet."""
        self._first_sequence: dict[int, int] = {}
        self._unavailable: set[Snowflake] = set()
        self._identified: set[int] = set()
        """Shards that started a new session in this process; only their entries can be swept."""
        self._kinds: dict[int, EntityKind] = {}
        self._registry: list[_Registration] = []
        self.channels: CacheCollection[Snowflake, Channel] = self._register(
            EntityKind.CHANNEL, NullCollection[Snowflake, Channel]()
        )
        self.emojis: CacheCollection[Snowflake, Emoji] = self._register(
            EntityKind.EMOJI, NullCollection[Snowflake, Emoji]()
        )
        self.guilds: CacheCollection[Snowflake, CachedGuild] = self._register(
            EntityKind.GUILD, NullCollection[Snowflake, CachedGuild]()
        )
        self.members: CacheCollection[GuildUserKey, GuildMember] = self._register(
            EntityKind.MEMBER, NullCollection[GuildUserKey, GuildMember]()
        )
        self.messages: CacheCollection[Snowflake, Message] = self._register(
            EntityKind.MESSAGE, NullCollection[Snowflake, Message]()
        )
        self.presences: CacheCollection[GuildUserKey, Presence] = self._register(
            EntityKind.PRESENCE, NullCollection[GuildUserKey, Presence]()
        )
        self.roles: CacheCollection[Snowflake, Role] = self._register(
            EntityKind.ROLE, NullCollection[Snowflake, Role]()
        )
        self.users: CacheCollection[Snowflake, User] = self._register(
            EntityKind.USER, NullCollection[Snowflake, User]()
        )
        self.voice_states: CacheCollection[GuildUserKey, VoiceState] = self._register(
            EntityKind.VOICE_STATE, NullCollection[GuildUserKey, VoiceState]()
        )

    def _register[K: Hashable, V](
        self, kind: EntityKind, disabled: NullCollection[K, V]
    ) -> CacheCollection[K, V]:
        policy = self._config.policy(kind)
        collection: CacheCollection[K, V] = disabled
        if policy.enabled:
            collection = MemoryCollection[K, V](self._clock, max_entries=policy.max_entries, ttl=policy.ttl)
        self._kinds[id(collection)] = kind

        async def drop(scope: Snowflake | None, doomed: _Doomed, *, every_scope: bool) -> int:
            rows = await collection.items() if every_scope else await collection.scoped(scope)
            removed = 0
            for key, entry in rows:
                if doomed(entry.freshness, entry.scope):
                    await collection.delete(key)
                    removed += 1
            return removed

        self._registry.append(_Registration(kind, drop))
        return collection

    @property
    def config(self) -> CacheConfig:
        """The configuration the store was created with."""
        return self._config

    @property
    def revision(self) -> int:
        """The revision of the latest write. The next write gets a higher one."""
        return self._revision

    @property
    def kinds(self) -> frozenset[EntityKind]:
        """Every kind the store has a collection for (enabled or not)."""
        return frozenset(registration.kind for registration in self._registry)

    def observe(self, shard_id: int, sequence: int) -> None:
        """Record that the dispatch with `sequence` from `shard_id` is being applied."""
        if shard_id in self._restored:
            self._first_sequence.setdefault(shard_id, sequence)
        self._sequences[shard_id] = sequence

    def session_started(self, shard_id: int) -> None:
        """`shard_id` identified a new session: everything it delivered so far becomes stale."""
        self._revision += 1
        self._stale_before[shard_id] = self._revision
        self._identified.add(shard_id)
        self._restored.pop(shard_id, None)
        self._first_sequence.pop(shard_id, None)

    def session_resumed(self, shard_id: int) -> None:
        """`shard_id` resumed its session.

        Within one process nothing changes: the session never ended. After a restart, the shard's
        restored entries become fresh only if Discord's replay started right after the sequence the
        snapshot was taken at; otherwise events were missed or applied twice and they stay stale.
        """
        mark = self._restored.pop(shard_id, None)
        first = self._first_sequence.pop(shard_id, None)
        if mark is None:
            return
        if mark.sequence is not None and first == mark.sequence + 1:
            self._stale_before[shard_id] = mark.stale_before
            _log.info("shard %d resumed where the cache snapshot ended; its entries are fresh", shard_id)
            return
        self._stale_before[shard_id] = self._floor
        _log.warning(
            "shard %d resumed from sequence %s but the cache snapshot ends at %s; its restored entries "
            "stay stale until updated (save the snapshot after closing the shards to avoid this)",
            shard_id,
            None if first is None else first - 1,
            mark.sequence,
        )

    def mark_unavailable(self, guild_id: Snowflake) -> None:
        """The guild is in an outage: `sweep_stale` keeps its entries."""
        self._unavailable.add(guild_id)

    def mark_available(self, guild_id: Snowflake) -> None:
        """The guild's `GUILD_CREATE` arrived."""
        self._unavailable.discard(guild_id)

    def is_fresh[V](self, entry: Entry[V]) -> bool:
        """Whether Discord has confirmed `entry` in the current session of the shard that wrote it."""
        return entry.freshness.revision >= self._threshold(entry.freshness)

    def _threshold(self, freshness: Freshness) -> int:
        if freshness.shard is None:
            return self._floor
        return self._stale_before.get(freshness.shard, self._floor)

    def freshness(self, source: Source, *, shard: int | None = None) -> Freshness:
        """Provenance for a value observed now; takes the next revision."""
        self._revision += 1
        return Freshness(source=source, observed_at=self._clock.wall(), revision=self._revision, shard=shard)

    async def put[K: Hashable, V](
        self,
        collection: CacheCollection[K, V],
        key: K,
        value: V,
        source: Source,
        *,
        scope: Snowflake | None = None,
        shard: int | None = None,
    ) -> None:
        """Store `value` observed now from `source` (through `shard`, for gateway data)."""
        entry = Entry(value=value, freshness=self.freshness(source, shard=shard), scope=scope)
        await collection.set(key, entry)

    async def edit[K: Hashable, V](
        self, collection: CacheCollection[K, V], key: K, change: Callable[[V], V]
    ) -> bool:
        """Apply a partial update to a cached value, keeping its provenance. Returns whether it existed.

        A partial event (a reaction, a pin, a member count) confirms only what it changes, so a stale
        entry stays stale and a fresh one stays fresh.
        """
        entry = await collection.get(key)
        if entry is None:
            return False
        await collection.set(key, msgspec.structs.replace(entry, value=change(entry.value)))
        return True

    async def value[K: Hashable, V](
        self, collection: CacheCollection[K, V], key: K, *, fresh_only: bool = False
    ) -> V | None:
        """Read a value. With `fresh_only`, stale entries count as missing."""
        entry = await collection.get(key)
        kind = self._kinds.get(id(collection))
        label = kind.value if kind is not None else "custom"
        if entry is None:
            self._metrics.increment(CACHE_LOOKUPS, {"kind": label, "result": "miss"})
            return None
        fresh = self.is_fresh(entry)
        self._metrics.increment(CACHE_LOOKUPS, {"kind": label, "result": "hit" if fresh else "stale"})
        if fresh_only and not fresh:
            return None
        return entry.value

    async def get_channel(self, channel_id: int, *, fresh_only: bool = False) -> Channel | None:
        """A cached channel or thread. Check `Channel.is_obfuscated` before trusting its metadata."""
        return await self.value(self.channels, Snowflake(channel_id), fresh_only=fresh_only)

    async def get_emoji(self, emoji_id: int, *, fresh_only: bool = False) -> Emoji | None:
        """A cached custom emoji."""
        return await self.value(self.emojis, Snowflake(emoji_id), fresh_only=fresh_only)

    async def get_guild(self, guild_id: int, *, fresh_only: bool = False) -> CachedGuild | None:
        """A cached guild (without roles and emojis; see the class docstring)."""
        return await self.value(self.guilds, Snowflake(guild_id), fresh_only=fresh_only)

    async def get_member(
        self, guild_id: int, user_id: int, *, fresh_only: bool = False
    ) -> GuildMember | None:
        """A cached guild member."""
        return await self.value(
            self.members, (Snowflake(guild_id), Snowflake(user_id)), fresh_only=fresh_only
        )

    async def get_message(self, message_id: int, *, fresh_only: bool = False) -> Message | None:
        """A cached message."""
        return await self.value(self.messages, Snowflake(message_id), fresh_only=fresh_only)

    async def get_presence(self, guild_id: int, user_id: int, *, fresh_only: bool = False) -> Presence | None:
        """A user's cached presence in a guild."""
        key = (Snowflake(guild_id), Snowflake(user_id))
        return await self.value(self.presences, key, fresh_only=fresh_only)

    async def get_role(self, role_id: int, *, fresh_only: bool = False) -> Role | None:
        """A cached role."""
        return await self.value(self.roles, Snowflake(role_id), fresh_only=fresh_only)

    async def get_user(self, user_id: int, *, fresh_only: bool = False) -> User | None:
        """A cached user."""
        return await self.value(self.users, Snowflake(user_id), fresh_only=fresh_only)

    async def get_voice_state(
        self, guild_id: int, user_id: int, *, fresh_only: bool = False
    ) -> VoiceState | None:
        """A user's cached voice state in a guild (absent when not in a voice channel)."""
        key = (Snowflake(guild_id), Snowflake(user_id))
        return await self.value(self.voice_states, key, fresh_only=fresh_only)

    async def reconcile_guild(
        self, guild_id: Snowflake, *, since: int, members: bool = True, presences: bool = True
    ) -> int:
        """Drop a guild's entries that its `GUILD_CREATE` did not contain.

        Call it after applying the `GUILD_CREATE`, with `since` set to `revision` from just before:
        every entry of the guild written at or before `since` was not in the guild's current state,
        so it no longer exists. Messages are never part of `GUILD_CREATE` and are left alone. Pass
        `members=False` or `presences=False` when the `GUILD_CREATE` did not list them all (see
        `CacheUpdater`); those stay until chunking or member events update them. Returns how many
        entries were removed.
        """
        skipped = {EntityKind.GUILD, EntityKind.MESSAGE}
        if not members:
            skipped.add(EntityKind.MEMBER)
        if not presences:
            skipped.add(EntityKind.PRESENCE)

        def doomed(freshness: Freshness, scope: Snowflake | None) -> bool:
            del scope
            return freshness.revision <= since

        removed = 0
        for registration in self._registry:
            if registration.kind not in skipped:
                removed += await registration.drop(guild_id, doomed, every_scope=False)
        return removed

    async def forget_guild(self, guild_id: Snowflake) -> int:
        """Remove a guild and everything scoped to it (the bot left or was removed)."""
        self._unavailable.discard(guild_id)
        removed = 0
        for registration in self._registry:
            removed += await registration.drop(guild_id, _everything, every_scope=False)
        return removed

    async def sweep_stale(self) -> int:
        """Remove what the bot lost while it was offline, once every shard is ready.

        Only entries from shards that identified a new session in this process are judged: their
        `GUILD_CREATE`s replaced everything that still exists. Entries of resumed shards (Discord
        replays their changes), of shards this process never saw, and written outside the gateway
        are kept, and so are guilds in an outage: they are still there, Discord just cannot send
        them yet.
        """

        def doomed(freshness: Freshness, scope: Snowflake | None) -> bool:
            if scope in self._unavailable or freshness.shard not in self._identified:
                return False
            return freshness.revision < self._threshold(freshness)

        removed = 0
        for registration in self._registry:
            removed += await registration.drop(None, doomed, every_scope=True)
        if removed:
            _log.info("removed %d stale cache entries after startup", removed)
        return removed

    async def snapshot(self) -> Snapshot:
        """Capture every kind whose policy has `persist` set, with each shard's position."""

        async def rows[K: Hashable, V](kind: EntityKind, collection: CacheCollection[K, V]) -> Rows[K, V]:
            return await collection.items() if self._config.policy(kind).persist else []

        shards = dict(self._restored)
        for shard_id, stale_before in self._stale_before.items():
            shards[shard_id] = ShardMark(stale_before=stale_before, sequence=self._sequences.get(shard_id))
        return Snapshot(
            format=SNAPSHOT_FORMAT,
            saved_at=self._clock.wall(),
            revision=self._revision,
            shards=shards,
            channels=await rows(EntityKind.CHANNEL, self.channels),
            emojis=await rows(EntityKind.EMOJI, self.emojis),
            guilds=await rows(EntityKind.GUILD, self.guilds),
            members=await rows(EntityKind.MEMBER, self.members),
            messages=await rows(EntityKind.MESSAGE, self.messages),
            presences=await rows(EntityKind.PRESENCE, self.presences),
            roles=await rows(EntityKind.ROLE, self.roles),
            users=await rows(EntityKind.USER, self.users),
            voice_states=await rows(EntityKind.VOICE_STATE, self.voice_states),
        )

    async def save_snapshot(self, path: str | Path) -> None:
        """Write a snapshot to `path` atomically, readable by the bot's user only.

        The snapshot holds member, user and guild data. Save it after closing the shards
        (`ShardManager.close()`), so it ends exactly where the saved sessions resume.
        """
        snapshot = await self.snapshot()
        await asyncio.to_thread(_write_snapshot, Path(path), snapshot)

    async def load_snapshot(self, path: str | Path) -> bool:
        """Replace the cache with a snapshot written by `save_snapshot`, marking every entry stale.

        Load before the shards connect: entries written while loading would be overwritten by the
        snapshot's older ones. Returns whether anything was loaded. Nothing is loaded when the
        restart strategy is `RestartStrategy.COLD`. A missing, unreadable or incompatible snapshot is
        skipped with a log line, and the cache starts cold. Kinds whose policy no longer persists are
        not restored.
        """
        if self._config.restart is RestartStrategy.COLD:
            return False
        target = Path(path)
        try:
            snapshot = await asyncio.to_thread(_read_snapshot, target)
        except FileNotFoundError:
            return False
        except (OSError, PayloadDecodeError, _FormatMismatchError) as error:
            _log.warning("cache snapshot %s cannot be used (%s); starting cold", target, error)
            return False
        for registration in self._registry:
            await registration.drop(None, _everything, every_scope=True)
        self._revision = snapshot.revision
        self._floor = snapshot.revision + 1
        self._stale_before.clear()
        self._identified.clear()
        self._unavailable.clear()
        self._sequences.clear()
        self._first_sequence.clear()
        self._restored = dict(snapshot.shards)
        await self._restore(EntityKind.CHANNEL, self.channels, snapshot.channels)
        await self._restore(EntityKind.EMOJI, self.emojis, snapshot.emojis)
        await self._restore(EntityKind.GUILD, self.guilds, snapshot.guilds)
        await self._restore(EntityKind.MEMBER, self.members, snapshot.members)
        await self._restore(EntityKind.MESSAGE, self.messages, snapshot.messages)
        await self._restore(EntityKind.PRESENCE, self.presences, snapshot.presences)
        await self._restore(EntityKind.ROLE, self.roles, snapshot.roles)
        await self._restore(EntityKind.USER, self.users, snapshot.users)
        await self._restore(EntityKind.VOICE_STATE, self.voice_states, snapshot.voice_states)
        _log.info("restored cache snapshot from %s (revision %d)", target, snapshot.revision)
        return True

    async def _restore[K: Hashable, V](
        self, kind: EntityKind, collection: CacheCollection[K, V], rows: Rows[K, V]
    ) -> None:
        if not self._config.policy(kind).persist:
            return
        for index, (key, entry) in enumerate(rows, start=1):
            freshness = msgspec.structs.replace(entry.freshness, source=Source.SNAPSHOT)
            await collection.set(key, msgspec.structs.replace(entry, freshness=freshness))
            if index % _RESTORE_BATCH == 0:
                await asyncio.sleep(0)


class _FormatMismatchError(Exception):
    def __init__(self, found: int) -> None:
        super().__init__(f"format {found}, expected {SNAPSHOT_FORMAT}")


def _write_snapshot(path: Path, snapshot: Snapshot) -> None:
    write_private(path, encode_msgpack(snapshot))


def _read_snapshot(path: Path) -> Snapshot:
    data = path.read_bytes()
    found = decode_msgpack(data, _SnapshotFormat).format
    if found != SNAPSHOT_FORMAT:
        raise _FormatMismatchError(found)
    return decode_msgpack(data, Snapshot)
