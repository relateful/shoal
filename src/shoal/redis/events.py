"""Dispatch events carried between processes by a Redis stream: a broker for IPC.

    # gateway process
    stream = RedisEventStream(redis)
    manager = ShardManager(..., dispatch=stream.publish)

    # each worker process
    async for event in RedisEventConsumer(redis, group="workers", consumer=f"worker-{n}"):
        ...

Unlike `EventServer`, the gateway process holds no connection to its workers: events wait in Redis
until read, so a worker that restarts picks up where it left off, and workers in a `group` share
the events between them, each event going to one of them. A group starts with the events published
after its first consumer joined. Without a group every consumer receives every event published
after it started.

The stream keeps the last `max_length` events (about; Redis trims in whole blocks), so a consumer
that stays away longer loses the oldest. Event data travels as Discord's original JSON bytes, which
hold message contents and interaction tokens: keep Redis on a private network, behind a password.
"""

import asyncio
import contextlib
import logging
import random
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from typing import Final, cast, final

import msgspec
from redis.exceptions import RedisError, ResponseError

from shoal.core.backoff import backoff_delay
from shoal.core.clock import Clock, SystemClock, sleep_unless
from shoal.core.dispatch import DispatchEvent
from shoal.redis.base import Redis, key_of, text_of
from shoal.redis.defaults import (
    EVENT_BATCH,
    EVENT_CLAIM_AFTER,
    EVENT_GROUP_BATCH,
    EVENT_READ_BLOCK,
    EVENT_RECONNECT_BACKOFF_CAP,
    EVENT_STREAM_MAX_LENGTH,
    KEY_PREFIX,
)

_log = logging.getLogger("shoal.redis")

_NEW: Final = b">"
"""A group read's position for events no consumer of the group has read yet."""

_NO_SEQUENCE: Final = b""

type _Entries = list[tuple[bytes, Mapping[bytes, bytes]]]


@final
class RedisEventStream:
    """Publishes dispatch events to a Redis stream.

    Args:
        redis: The client to publish with.
        prefix: What the stream's key starts with; give each bot its own.
        max_length: About how many events the stream keeps.
    """

    __slots__ = ("_key", "_max_length", "_redis")

    def __init__(
        self, redis: Redis, *, prefix: str = KEY_PREFIX, max_length: int = EVENT_STREAM_MAX_LENGTH
    ) -> None:
        """Create a publisher; see the class docstring for the arguments."""
        self._redis: Redis = redis
        self._key: str = key_of(prefix, "events")
        self._max_length: int = max_length

    async def publish(self, event: DispatchEvent) -> None:
        """Add `event` to the stream. Usable directly as a shard's `dispatch` handler.

        Raises:
            RedisError: Redis could not be reached.
        """
        await self._redis.xadd(
            self._key,
            {
                b"shard": str(event.shard_id).encode(),
                b"name": event.name.encode(),
                b"sequence": _NO_SEQUENCE if event.sequence is None else str(event.sequence).encode(),
                b"data": bytes(event.data),
            },
            maxlen=self._max_length,
            approximate=True,
        )


@final
class RedisEventConsumer:
    """Reads dispatch events from a Redis stream.

    Args:
        redis: The client to read with.
        group: Share the events with every consumer of this group, each event going to one of them;
            `None` receives every event published after the consumer starts.
        consumer: This consumer's name within its group. Give each process its own and keep it
            across restarts: events it had read but not finished are read again when it comes back.
        prefix: What the stream's key starts with.
        shard_ids: Only yield events from these shards. `None` means all.
        events: Only yield these dispatch names. `None` means all.
        claim_after: Seconds after which a group's event read by a consumer that never finished it
            (one that stopped for good) is taken over by another.
        clock: Time source for reconnect backoff.
        random_source: Random source for reconnect jitter.

    In a group, an event is acknowledged once the loop asks for the next one, so an event whose
    handling was cut short by a crash is read again. Give every consumer of a group the same
    `shard_ids` and `events`: an event one of them skips is acknowledged, and so lost to the group.
    A group consumer reads `EVENT_GROUP_BATCH` events at a time; keep `claim_after` well above how
    long handling that many takes, or another consumer takes over events still waiting their turn.
    """

    __slots__ = (
        "_claim_after",
        "_clock",
        "_closing",
        "_consumer",
        "_events",
        "_group",
        "_key",
        "_position",
        "_random_source",
        "_reading",
        "_redis",
        "_shard_ids",
        "_stopped",
    )

    def __init__(
        self,
        redis: Redis,
        *,
        group: str | None = None,
        consumer: str = "worker",
        prefix: str = KEY_PREFIX,
        shard_ids: Sequence[int] | None = None,
        events: Sequence[str] | None = None,
        claim_after: float = EVENT_CLAIM_AFTER,
        clock: Clock | None = None,
        random_source: random.Random | None = None,
    ) -> None:
        """Create a consumer; iterate it to read events."""
        self._redis: Redis = redis
        self._group: str | None = group
        self._consumer: str = consumer
        self._key: str = key_of(prefix, "events")
        self._shard_ids: frozenset[int] | None = frozenset(shard_ids) if shard_ids is not None else None
        self._events: frozenset[str] | None = frozenset(events) if events is not None else None
        self._claim_after: float = claim_after
        self._clock: Clock = clock or SystemClock()
        self._random_source: random.Random = random_source or random.Random()  # noqa: S311 - jitter, not security
        self._closing: bool = False
        self._stopped: asyncio.Event = asyncio.Event()
        self._position: bytes | None = None
        """Where reading continues: the last entry handled, or `_NEW` for a group's new events."""
        self._reading: asyncio.Event = asyncio.Event()

    def __aiter__(self) -> AsyncIterator[DispatchEvent]:
        return self.events()

    def close(self) -> None:
        """Stop reading: an active iteration ends within `EVENT_READ_BLOCK` seconds."""
        self._closing = True
        self._stopped.set()

    async def reading(self) -> None:
        """Return once the consumer reads from the stream: events published from then on reach it."""
        await self._reading.wait()

    def _stopping(self) -> bool:
        return self._closing

    def _wants(self, event: DispatchEvent) -> bool:
        return (self._shard_ids is None or event.shard_id in self._shard_ids) and (
            self._events is None or event.name in self._events
        )

    async def events(self) -> AsyncGenerator[DispatchEvent]:
        """Read and yield events until `close` is called, retrying with backoff while Redis is away.

        Iterate one `events()` at a time per consumer.

        Raises:
            ResponseError: Redis refused a read for good (a key of another type, a Redis too old
                for consumer groups): retrying would never succeed.
        """
        failures = 0
        while not self._stopping():
            try:
                entries = await self._next_entries()
            except RedisError as error:
                if isinstance(error, ResponseError):
                    if self._group is None or "NOGROUP" not in str(error):
                        raise
                    self._position = None  # the stream was deleted with its group: join again
                failures += 1
                delay = backoff_delay(
                    failures, cap=EVENT_RECONNECT_BACKOFF_CAP, random_source=self._random_source
                )
                _log.warning("reading events from Redis failed (%r); retrying in %.1fs", error, delay)
                await sleep_unless(self._clock, delay, self._stopped)
                continue
            failures = 0
            for entry_id, fields in entries:
                event = _event_of(fields)
                if event is not None and self._wants(event):
                    yield event
                if self._group is not None:
                    with contextlib.suppress(RedisError):  # left unacknowledged: read again later
                        await self._redis.xack(self._key, self._group, entry_id)

    async def _next_entries(self) -> _Entries:
        """The next entries to handle, after the last ones returned.

        Raises:
            RedisError: Redis could not be reached.
        """
        block = round(EVENT_READ_BLOCK * 1000)
        if self._group is None:
            if self._position is None:
                # `$` means "after the newest" at each call: pin it once so nothing between reads is lost.
                newest = _entries_of_range(await self._redis.xrevrange(self._key, count=1))
                self._position = newest[0][0] if newest else b"0-0"
                self._reading.set()
            entries = _entries_of(
                await self._redis.xread({self._key: self._position}, count=EVENT_BATCH, block=block)
            )
            if entries:
                self._position = entries[-1][0]
            return entries
        if self._position is None:
            with contextlib.suppress(ResponseError):  # BUSYGROUP: the group exists
                await self._redis.xgroup_create(self._key, self._group, id="$", mkstream=True)
            self._position = b"0"  # this consumer's unfinished events first
            self._reading.set()
        if self._position != _NEW:
            entries = _entries_of(
                await self._redis.xreadgroup(
                    self._group, self._consumer, {self._key: self._position}, count=EVENT_GROUP_BATCH
                )
            )
            if entries:
                self._position = entries[-1][0]
                return entries
            self._position = _NEW
        claimed = _claimed_of(
            await self._redis.xautoclaim(
                self._key,
                self._group,
                self._consumer,
                min_idle_time=round(self._claim_after * 1000),
                count=EVENT_GROUP_BATCH,
            )
        )
        if claimed:
            return claimed
        return _entries_of(
            await self._redis.xreadgroup(
                self._group, self._consumer, {self._key: _NEW}, count=EVENT_GROUP_BATCH, block=block
            )
        )


def _entries_of(answer: object) -> _Entries:
    """The entries of an XREAD or XREADGROUP answer for one stream (RESP2 list or RESP3 map)."""
    if isinstance(answer, dict):
        # isinstance narrows to dict[Unknown, Unknown]; RESP3 maps the stream's key to [entries].
        streams = cast("dict[object, list[_Entries]]", answer)
        return [entry for entries in streams.values() for entry in entries[0]]
    if isinstance(answer, list) and answer:
        # isinstance narrows to list[Unknown]; RESP2 lists [key, entries] for each stream.
        return cast("list[tuple[object, _Entries]]", answer)[0][1]
    return []


def _entries_of_range(answer: object) -> _Entries:
    """The entries of an XRANGE or XREVRANGE answer."""
    # The client types range answers loosely; they are [id, fields] pairs.
    return cast("_Entries", answer)


def _claimed_of(answer: object) -> _Entries:
    """The entries an XAUTOCLAIM took over, from [next start, entries, deleted ids]."""
    # The client types the answer as a list of anything; its second element is the entries, with
    # `None` for any deleted since they were read (Redis 6.2; later versions list those apart).
    parts = cast("list[list[tuple[bytes, Mapping[bytes, bytes]] | None]]", answer)
    return [entry for entry in parts[1] if entry is not None]


def _event_of(fields: Mapping[bytes, bytes]) -> DispatchEvent | None:
    """The event an entry holds, or `None` for an entry that is not one (logged)."""
    try:
        sequence = text_of(fields[b"sequence"])
        return DispatchEvent(
            int(text_of(fields[b"shard"])),
            text_of(fields[b"name"]).decode(),
            int(sequence) if sequence else None,
            msgspec.Raw(text_of(fields[b"data"])),
        )
    except (KeyError, ValueError):
        _log.warning("skipping a stream entry that is not a dispatch event")
        return None
