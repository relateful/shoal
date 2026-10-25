"""Shard routing and identify concurrency.

Discord: https://docs.discord.com/developers/events/gateway#sharding
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol, final, override

from shoal.core.clock import Clock, SystemClock
from shoal.payloads.gateway import IDENTIFY_WINDOW


def shard_for_guild(guild_id: int, shard_count: int) -> int:
    """Which shard receives a guild's events: `(guild_id >> 22) % shard_count`.

    Discord: https://docs.discord.com/developers/events/gateway#sharding-sharding-formula
    """
    if shard_count < 1:
        msg = "shard_count must be at least 1"
        raise ValueError(msg)
    return (guild_id >> 22) % shard_count


def rate_limit_key(shard_id: int, max_concurrency: int) -> int:
    """The identify bucket of a shard: `shard_id % max_concurrency`.

    Discord: https://docs.discord.com/developers/events/gateway#sharding-max-concurrency
    """
    if max_concurrency < 1:
        msg = "max_concurrency must be at least 1"
        raise ValueError(msg)
    return shard_id % max_concurrency


class IdentifyLimiter(Protocol):
    """Grants identify slots.

    Replace the local one with a shared implementation when shards of one bot run in several
    processes, so they never exceed `max_concurrency` together.
    """

    def slot(self, shard_id: int) -> AbstractAsyncContextManager[None]:
        """An async context manager held while the shard identifies."""
        ...


@final
class LocalIdentifyLimiter(IdentifyLimiter):
    """Lets up to `max_concurrency` shards identify at once, one per bucket every five seconds.

    discord.py identifies one shard every five seconds regardless of `max_concurrency`; a bot with
    `max_concurrency` 16 and 512 shards starts in about 2.7 minutes here instead of 43.

    Discord: https://docs.discord.com/developers/events/gateway#sharding-max-concurrency
    """

    __slots__ = ("_clock", "_last", "_locks", "_max_concurrency", "_window")

    def __init__(
        self, max_concurrency: int, *, clock: Clock | None = None, window: float = IDENTIFY_WINDOW
    ) -> None:
        """Create a limiter for a bot's `max_concurrency` from Get Gateway Bot."""
        if max_concurrency < 1:
            msg = "max_concurrency must be at least 1"
            raise ValueError(msg)
        self._max_concurrency: int = max_concurrency
        self._clock: Clock = clock or SystemClock()
        self._window: float = window
        self._locks: dict[int, asyncio.Lock] = {}
        self._last: dict[int, float] = {}

    @property
    def max_concurrency(self) -> int:
        """The number of identify buckets."""
        return self._max_concurrency

    @override
    @asynccontextmanager
    async def slot(self, shard_id: int) -> AsyncGenerator[None]:
        key = rate_limit_key(shard_id, self._max_concurrency)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            last = self._last.get(key)
            if last is not None:
                await self._clock.sleep(last + self._window - self._clock.monotonic())
            try:
                yield
            finally:
                self._last[key] = self._clock.monotonic()
