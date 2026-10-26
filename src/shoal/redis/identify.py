"""Identify slots shared by every process of a bot, through Redis.

    limiter = RedisIdentifyLimiter(redis, max_concurrency=gateway.session_start_limit.max_concurrency)
    manager = ShardManager(..., identify_limiter=limiter)

Each of the bot's `max_concurrency` buckets lets one shard identify every five seconds, whichever
process it runs in: a script reserves the bucket's next free moment by Redis's clock, so a shard only
waits for its own turn, and a process that dies holding nothing blocks nobody.

Discord: https://docs.discord.com/developers/events/gateway#sharding-max-concurrency
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Final, final, override

from shoal.core.clock import Clock, SystemClock
from shoal.gateway.sharding import IdentifyLimiter, rate_limit_key
from shoal.payloads.gateway import IDENTIFY_WINDOW
from shoal.redis.base import NOW_MS, Redis, key_of
from shoal.redis.defaults import KEY_PREFIX

_RESERVE: Final = (
    NOW_MS
    + """
local window = tonumber(ARGV[1])
local start = math.max(now, tonumber(redis.call('GET', KEYS[1]) or '0'))
redis.call('SET', KEYS[1], start + window, 'PX', start - now + window)
return start - now
"""
)
"""Reserve the bucket's next moment: return how many milliseconds until it."""


@final
class RedisIdentifyLimiter(IdentifyLimiter):
    """Lets up to `max_concurrency` shards identify at once, across every process.

    Each bucket lets one shard identify every five seconds.

    Discord: https://docs.discord.com/developers/events/gateway#sharding-max-concurrency
    """

    __slots__ = ("_clock", "_max_concurrency", "_prefix", "_redis", "_window")

    def __init__(
        self,
        redis: Redis,
        *,
        max_concurrency: int,
        prefix: str = KEY_PREFIX,
        window: float = IDENTIFY_WINDOW,
        clock: Clock | None = None,
    ) -> None:
        """A limiter for a bot's `max_concurrency` (from Get Gateway Bot), its keys under `prefix`.

        Raises:
            ValueError: `max_concurrency` is below 1.
        """
        if max_concurrency < 1:
            msg = "max_concurrency must be at least 1"
            raise ValueError(msg)
        self._redis: Redis = redis
        self._max_concurrency: int = max_concurrency
        self._prefix: str = prefix
        self._window: float = window
        self._clock: Clock = clock or SystemClock()

    @property
    def max_concurrency(self) -> int:
        """The number of identify buckets."""
        return self._max_concurrency

    @override
    @asynccontextmanager
    async def slot(self, shard_id: int) -> AsyncGenerator[None]:
        bucket = rate_limit_key(shard_id, self._max_concurrency)
        key = key_of(self._prefix, "identify", self._max_concurrency, bucket)
        waited: object = await self._redis.eval(_RESERVE, 1, key, str(round(self._window * 1000)))
        if not isinstance(waited, int):
            msg = f"the identify script returned {waited!r}, not a number of milliseconds"
            raise TypeError(msg)
        await self._clock.sleep(waited / 1000)
        yield
