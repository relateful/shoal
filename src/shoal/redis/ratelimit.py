"""REST rate limits shared by every process of a bot (and every process on one IP), in Redis.

    rest = RestClient(Token.bot(token), rate_limiter=RedisRateLimiter(redis))

Discord counts a bot's global limit across all its processes, its route buckets per bot, and the
invalid request ban per IP address. A `LocalRateLimiter` keeps each process's own requests in order;
the shared counts in Redis make the processes stay under every limit together: a request waits until
its bucket, the global limit and the invalid request window all allow it. Responses update Redis in
the background, so recording one never waits on the network.

Shared buckets are counted per route and major parameter, which every process knows before its
first response; routes Discord groups under one bucket hash are still grouped by each process's own
limiter. Bucket keys can hold webhook and interaction tokens, so Redis stores a hash of each.

While Redis cannot be reached, requests go out under each process's own limits, and the outage is
logged. Give the client a `socket_timeout`, or a Redis that stops answering holds every request.

Discord: https://docs.discord.com/developers/topics/rate-limits
"""

import asyncio
import hashlib
import logging
import secrets
from collections.abc import Awaitable
from http import HTTPStatus
from typing import Final, cast, final, override

from redis.exceptions import RedisError

from shoal.core.clock import Clock, SystemClock
from shoal.core.tasks import spawn
from shoal.payloads.rate_limits import (
    GLOBAL_REQUESTS_PER_SECOND,
    INVALID_REQUEST_LIMIT,
    INVALID_REQUEST_WINDOW,
)
from shoal.redis.base import NOW_MS, Redis, key_of
from shoal.redis.defaults import KEY_PREFIX
from shoal.rest.defaults import INVALID_REQUEST_SAFETY_MARGIN
from shoal.rest.ratelimit import (
    LocalRateLimiter,
    RateLimiter,
    RateLimitHeaders,
    WaitTooLongError,
    is_invalid,
)
from shoal.rest.route import CompiledRoute

_log = logging.getLogger("shoal.redis")

_CLEAR: Final = 0
_HELD_INVALID: Final = 1
_HELD_BUCKET: Final = 2
_HELD_GLOBAL: Final = 3

_ACQUIRE: Final = (
    NOW_MS
    + """
local window = tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', KEYS[4], '-inf', now - window)
if redis.call('ZCARD', KEYS[4]) >= tonumber(ARGV[3]) then
  local oldest = redis.call('ZRANGE', KEYS[4], 0, 0, 'WITHSCORES')
  return {1, tonumber(oldest[2]) + window - now}
end
local remaining = redis.call('HGET', KEYS[1], 'remaining')
local reset_at = tonumber(redis.call('HGET', KEYS[1], 'reset_at') or '0')
local tracked = remaining and now < reset_at
if tracked and tonumber(remaining) <= 0 then
  return {2, reset_at - now}
end
if ARGV[2] == '1' then
  local paused = tonumber(redis.call('GET', KEYS[3]) or '0')
  if now < paused then
    return {3, paused - now}
  end
  local rate = tonumber(ARGV[1])
  if rate > 0 then
    local tokens = tonumber(redis.call('HGET', KEYS[2], 'tokens') or ARGV[1])
    local updated = tonumber(redis.call('HGET', KEYS[2], 'updated') or now)
    tokens = math.min(rate, tokens + (now - updated) * rate / 1000)
    if tokens < 1 then
      return {3, math.ceil((1 - tokens) * 1000 / rate)}
    end
    redis.call('HSET', KEYS[2], 'tokens', tostring(tokens - 1), 'updated', now)
    redis.call('PEXPIRE', KEYS[2], 2000)
  end
end
if tracked then
  redis.call('HINCRBY', KEYS[1], 'remaining', -1)
end
return {0, 0}
"""
)
"""Take one request from the bucket and the global limit when all three limits allow it.

KEYS: bucket, global token bucket, global pause, invalid window. ARGV: global per second (0: no
limit), whether the route counts against the global limit, invalid threshold, window in ms.
Returns {0, 0}, or which limit holds the request ({1, 2, 3}) and for how many ms.
"""

_RELEASE: Final = (
    NOW_MS
    + """
if ARGV[1] == '1' then
  redis.call('ZADD', KEYS[3], now, ARGV[2])
  redis.call('PEXPIRE', KEYS[3], tonumber(ARGV[3]))
end
local pause = tonumber(ARGV[4])
if pause > 0 then
  local until_ms = now + pause
  if until_ms > tonumber(redis.call('GET', KEYS[2]) or '0') then
    redis.call('SET', KEYS[2], until_ms, 'PX', pause)
  end
end
local block = tonumber(ARGV[7])
if block > 0 then
  redis.call('HSET', KEYS[1], 'remaining', 0, 'reset_at', now + block)
  redis.call('PEXPIRE', KEYS[1], block + 1000)
elseif ARGV[5] ~= '' then
  local reset_after = tonumber(ARGV[6])
  local reset_at = now + reset_after
  local remaining = tonumber(ARGV[5])
  local known_reset = tonumber(redis.call('HGET', KEYS[1], 'reset_at') or '0')
  if known_reset > now and math.abs(known_reset - reset_at) < 1000 then
    -- The same window as what is known: an older answer must never raise what is left.
    remaining = math.min(remaining, tonumber(redis.call('HGET', KEYS[1], 'remaining') or ARGV[5]))
  end
  redis.call('HSET', KEYS[1], 'remaining', remaining, 'reset_at', reset_at)
  redis.call('PEXPIRE', KEYS[1], reset_after + 1000)
end
return 0
"""
)
"""Learn from one response.

KEYS: bucket, global pause, invalid window. ARGV: whether it was invalid, a unique member, window
in ms, global pause in ms (0: none), remaining ('' when the headers gave none), reset after in ms,
bucket block in ms (a route 429; 0: none).
"""


@final
class RedisRateLimiter(RateLimiter):
    """Rate limits counted across every process sharing the Redis keys under `prefix`.

    Args:
        redis: The client to count with.
        prefix: What the keys start with. Give each bot its own; processes on one IP that should
            share the invalid request window share `invalid_key` too.
        global_per_second: The bot's global requests per second, or `None` if Discord lifted it.
        invalid_threshold: Invalid responses in `INVALID_REQUEST_WINDOW` after which requests wait;
            kept `INVALID_REQUEST_SAFETY_MARGIN` below Discord's limit, for requests in flight.
        invalid_key: The key of the invalid request window, shared per IP address (by default per
            bot, under `prefix`).
        local: The limiter keeping this process's own requests in order; a new one by default.
        clock: Time source for waiting.
    """

    __slots__ = (
        "_clock",
        "_global_per_second",
        "_invalid_key",
        "_invalid_threshold",
        "_local",
        "_prefix",
        "_recording",
        "_redis",
        "_unreachable",
    )

    def __init__(
        self,
        redis: Redis,
        *,
        prefix: str = KEY_PREFIX,
        global_per_second: int | None = GLOBAL_REQUESTS_PER_SECOND,
        invalid_threshold: int = INVALID_REQUEST_LIMIT - INVALID_REQUEST_SAFETY_MARGIN,
        invalid_key: str | None = None,
        local: LocalRateLimiter | None = None,
        clock: Clock | None = None,
    ) -> None:
        """Create a limiter; see the class docstring for the arguments."""
        self._redis: Redis = redis
        self._prefix: str = prefix
        self._global_per_second: int | None = global_per_second
        self._invalid_threshold: int = invalid_threshold
        self._invalid_key: str = invalid_key or key_of(prefix, "rest", "invalid")
        self._clock: Clock = clock or SystemClock()
        self._local: LocalRateLimiter = local or LocalRateLimiter(
            clock=self._clock, global_per_second=global_per_second
        )
        self._recording: set[asyncio.Task[None]] = set()
        self._unreachable: bool = False
        """Whether the last shared acquire failed to reach Redis, so an outage is logged once."""

    @property
    def local(self) -> LocalRateLimiter:
        """The limiter keeping this process's own requests in order."""
        return self._local

    def _bucket_key(self, route: CompiledRoute) -> str:
        # Keyed by the route, not Discord's bucket hash: a process that has not seen the hash yet
        # must find the same key. The major parameter can be a webhook or interaction token, so
        # Redis gets a hash of the key.
        identity = f"{route.route.key}|{route.major}"
        digest = hashlib.sha256(identity.encode()).hexdigest()
        return key_of(self._prefix, "rest", "bucket", digest)

    @override
    async def acquire(self, route: CompiledRoute, *, max_wait: float | None = None) -> None:
        """Wait until this process's limits and the shared ones allow `route`.

        `max_wait` bounds the whole wait, local and shared together. While Redis cannot be reached,
        the request goes out under this process's own limits alone (logged once per outage).

        Raises:
            WaitTooLongError: The limits would hold the request longer than `max_wait`.
        """
        deadline = None if max_wait is None else self._clock.monotonic() + max_wait
        await self._local.acquire(route, max_wait=max_wait)
        try:
            await self._acquire_shared(route, deadline)
        except BaseException:
            self._local.release(route, None, None, None)
            raise

    async def _acquire_shared(self, route: CompiledRoute, deadline: float | None) -> None:
        keys = [
            self._bucket_key(route),
            key_of(self._prefix, "rest", "global"),
            key_of(self._prefix, "rest", "global", "paused"),
            self._invalid_key,
        ]
        arguments = [
            str(self._global_per_second or 0),
            "1" if route.route.global_limit else "0",
            str(self._invalid_threshold),
            str(round(INVALID_REQUEST_WINDOW * 1000)),
        ]
        while True:
            try:
                answer: object = await self._redis.eval(_ACQUIRE, len(keys), *keys, *arguments)
            except RedisError:
                if not self._unreachable:
                    self._unreachable = True
                    _log.exception(
                        "Redis cannot be reached; requests keep only this process's own rate limits"
                    )
                return
            if self._unreachable:
                self._unreachable = False
                _log.info("Redis can be reached again; requests keep the shared rate limits")
            held, waited = _held_for(answer)
            if held == _CLEAR:
                return
            seconds = waited / 1000
            if deadline is not None and self._clock.monotonic() + seconds > deadline:
                raise WaitTooLongError(seconds)
            if held == _HELD_INVALID:
                _log.error("holding requests to stay under Discord's invalid request ban (shared)")
            await self._clock.sleep(seconds)

    @override
    def release(
        self,
        route: CompiledRoute,
        status: int | None,
        headers: RateLimitHeaders | None,
        retry_after: float | None,
    ) -> None:
        self._local.release(route, status, headers, retry_after)
        if status is None:
            return
        rate_limited = status == HTTPStatus.TOO_MANY_REQUESTS and retry_after is not None
        global_pause = retry_after if rate_limited and headers is not None and headers.is_global else None
        block = retry_after if rate_limited and global_pause is None else None
        known = headers is not None and headers.remaining is not None and headers.reset_after is not None
        keys = [
            self._bucket_key(route),
            key_of(self._prefix, "rest", "global", "paused"),
            self._invalid_key,
        ]
        arguments = [
            "1" if is_invalid(status, headers.scope if headers is not None else None) else "0",
            secrets.token_hex(8),
            str(round(INVALID_REQUEST_WINDOW * 1000)),
            str(_ms(global_pause)),
            str(headers.remaining) if known and headers is not None else "",
            str(_ms(headers.reset_after if headers is not None else None)),
            str(_ms(block)),
        ]
        task = spawn(
            self._record(self._redis.eval(_RELEASE, len(keys), *keys, *arguments)), name="shoal-redis-release"
        )
        self._recording.add(task)
        task.add_done_callback(self._recording.discard)

    async def drain(self) -> None:
        """Wait until every response released so far is recorded in Redis, such as before exiting."""
        while self._recording:
            await asyncio.gather(*self._recording)

    async def _record(self, update: Awaitable[object]) -> None:
        try:
            await update
        except Exception:  # noqa: BLE001 - logged; this process's own limiter still holds the limits
            _log.exception("could not record a response's rate limits in Redis")


def _ms(seconds: float | None) -> int:
    return 0 if seconds is None else max(round(seconds * 1000), 0)


def _held_for(answer: object) -> tuple[int, int]:
    """Which limit holds the request, and for how many milliseconds, from the acquire script.

    Raises:
        TypeError: The script answered something else.
    """
    if isinstance(answer, list):
        # isinstance narrows to list[Unknown]; the script answers a list of two integers.
        parts = cast("list[object]", answer)
        if len(parts) == 2 and isinstance(parts[0], int) and isinstance(parts[1], int):  # noqa: PLR2004 - {held, ms}
            return parts[0], max(parts[1], 0)
    msg = f"the rate limit script returned {answer!r}"
    raise TypeError(msg)
