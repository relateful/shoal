"""The shard directory and command routing of a bot's clusters, in Redis.

    manager = ShardManager(
        ...,
        directory=RedisShardDirectory(redis),
        router=RedisCommandRouter(redis),
        name=f"cluster-{cluster_id}",
    )

Each shard's status is a key that expires `ttl` seconds after its last report, so a cluster that
stops drops out of the directory by itself. Commands travel over Redis pub/sub, one channel per
shard: a command is delivered only to a process listening at that moment, which is how a gateway
command behaves anyway (one sent while a shard reconnects is lost too).
"""

import contextlib
import logging
from collections.abc import AsyncGenerator, Collection, Sequence
from typing import Protocol, cast, final, override

from shoal.core.codec import PayloadDecodeError, decode_json, encode_json
from shoal.gateway.cluster import CommandRouter, GatewayCommand, ShardDirectory, ShardStatus
from shoal.gateway.defaults import SHARD_STATUS_TTL
from shoal.redis.base import Redis, key_of, text_of
from shoal.redis.defaults import EVENT_READ_BLOCK, KEY_BATCH, KEY_PREFIX

_log = logging.getLogger("shoal.redis")


class _Subscription(Protocol):
    """The part of a redis-py pub/sub object the router uses."""

    __slots__ = ()

    async def subscribe(self, *channels: str) -> object: ...

    async def get_message(self, *, timeout: float) -> object: ...  # noqa: ASYNC109 - redis-py's signature

    async def aclose(self) -> None: ...


class _PubSub(Protocol):
    """The pub/sub calls of a redis-py client, as the router uses them."""

    __slots__ = ()

    async def publish(self, channel: str, message: bytes) -> int: ...

    def pubsub(self, *, ignore_subscribe_messages: bool) -> _Subscription: ...


@final
class RedisShardDirectory(ShardDirectory):
    """Every cluster's shards, in Redis.

    Args:
        redis: The client to store statuses with.
        prefix: What the keys start with; give each bot its own.
        ttl: Seconds a status lives after it was reported.
    """

    __slots__ = ("_prefix", "_redis", "_ttl")

    def __init__(self, redis: Redis, *, prefix: str = KEY_PREFIX, ttl: float = SHARD_STATUS_TTL) -> None:
        """Create a directory; see the class docstring for the arguments."""
        self._redis: Redis = redis
        self._prefix: str = prefix
        self._ttl: float = ttl

    def _key(self, shard_count: int, shard_id: int) -> str:
        return key_of(self._prefix, "shards", shard_count, shard_id)

    @override
    async def report(self, statuses: Sequence[ShardStatus]) -> None:
        async with self._redis.pipeline(transaction=False) as pipe:
            for status in statuses:
                # A pipeline queues each command (redis-py types them as the client's awaitables).
                _ = pipe.set(
                    self._key(status.shard_count, status.shard_id),
                    encode_json(status),
                    px=round(self._ttl * 1000),
                )
            await pipe.execute()

    @override
    async def statuses(self, shard_count: int) -> dict[int, ShardStatus]:
        found: dict[int, ShardStatus] = {}
        for start in range(0, shard_count, KEY_BATCH):
            ids = range(start, min(start + KEY_BATCH, shard_count))
            values = await self._redis.mget([self._key(shard_count, shard_id) for shard_id in ids])
            for shard_id, value in zip(ids, values, strict=True):
                if value is None:
                    continue
                try:
                    found[shard_id] = decode_json(text_of(value), ShardStatus)
                except PayloadDecodeError:
                    _log.warning("skipping an unreadable status of shard %d", shard_id)
        return found


@final
class RedisCommandRouter(CommandRouter):
    """Gateway commands carried to the process running their shard, over Redis pub/sub.

    Args:
        redis: The client to publish and subscribe with.
        prefix: What the channels start with; give each bot its own.
    """

    __slots__ = ("_prefix", "_redis")

    def __init__(self, redis: Redis, *, prefix: str = KEY_PREFIX) -> None:
        """Create a router; see the class docstring for the arguments."""
        # redis-py leaves its pub/sub calls partly untyped; these are the signatures it implements.
        self._redis: _PubSub = cast("_PubSub", redis)
        self._prefix: str = prefix

    def _channel(self, shard_count: int, shard_id: int) -> str:
        return key_of(self._prefix, "commands", shard_count, shard_id)

    @override
    async def send(self, command: GatewayCommand) -> bool:
        receivers = await self._redis.publish(
            self._channel(command.shard_count, command.shard_id), encode_json(command)
        )
        return receivers > 0

    @override
    async def receive(self, shard_count: int, shard_ids: Collection[int]) -> AsyncGenerator[GatewayCommand]:
        channels = [self._channel(shard_count, shard_id) for shard_id in shard_ids]
        subscription = self._redis.pubsub(ignore_subscribe_messages=True)
        try:
            await subscription.subscribe(*channels)
            while True:
                message: object = await subscription.get_message(timeout=EVENT_READ_BLOCK)
                command = _command_of(message)
                if command is not None:
                    yield command
        finally:
            with contextlib.suppress(Exception):  # closing a subscription Redis already dropped
                await subscription.aclose()


def _command_of(message: object) -> GatewayCommand | None:
    """The command a pub/sub message carries, or `None` for anything else (logged)."""
    # isinstance narrows to dict[Unknown, Unknown]; a pub/sub message maps names to values.
    data = cast("dict[str, object]", message).get("data") if isinstance(message, dict) else None
    if not isinstance(data, bytes | str):
        return None
    try:
        return decode_json(text_of(data), GatewayCommand)
    except PayloadDecodeError:
        _log.warning("skipping a message on a command channel that is not a gateway command")
        return None
