"""HTTP rate limiting: per-route buckets, the global limit and the invalid request guard.

Three limits apply to every request, and `LocalRateLimiter` enforces all three in-process:

1. **Buckets.** Discord groups routes into buckets (`X-RateLimit-Bucket`), separately for each
   top-level resource. Until a route's first response names its bucket, requests on it go one at a
   time so the limit is learned before it can be exceeded.
2. **Global.** 50 requests per second per bot, unless Discord raised it for you. A global 429 pauses
   every request until it clears.
3. **Invalid requests.** 10,000 responses with 401, 403 or (non-shared) 429 in 10 minutes gets the
   IP temporarily restricted from the API (a Cloudflare ban). The guard counts them and holds
   requests back before the budget runs out.

`RateLimiter` is a protocol, so a shared (for example Redis-backed) limiter can replace the local one
when several processes use the same token.

Discord: https://docs.discord.com/developers/topics/rate-limits
"""

import asyncio
import logging
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from typing import Protocol, final, override

from shoal.core.clock import Clock, SystemClock
from shoal.core.errors import ShoalError
from shoal.core.metrics import REST_INVALID_REQUESTS, Metrics, NoopMetrics
from shoal.payloads.rate_limits import (
    GLOBAL_REQUESTS_PER_SECOND,
    INVALID_REQUEST_LIMIT,
    INVALID_REQUEST_STATUSES,
    INVALID_REQUEST_WINDOW,
    RateLimitScope,
)
from shoal.rest.defaults import BUCKET_PRUNE_INTERVAL, BUCKET_PRUNE_THRESHOLD, INVALID_REQUEST_SAFETY_MARGIN
from shoal.rest.route import CompiledRoute

_log = logging.getLogger("shoal.rest.ratelimit")


@dataclass(frozen=True, slots=True)
class RateLimitHeaders:
    """The rate limit headers of one response.

    Discord: https://docs.discord.com/developers/topics/rate-limits#header-format
    """

    limit: int | None
    remaining: int | None
    reset_after: float | None
    bucket: str | None
    is_global: bool
    scope: RateLimitScope | None

    @classmethod
    def parse(cls, headers: Mapping[str, str]) -> "RateLimitHeaders":
        """Read the headers from a lower-cased header mapping, ignoring malformed values."""
        scope_value = headers.get("x-ratelimit-scope")
        return cls(
            limit=_number(headers.get("x-ratelimit-limit"), int),
            remaining=_number(headers.get("x-ratelimit-remaining"), int),
            reset_after=_number(headers.get("x-ratelimit-reset-after"), float),
            bucket=headers.get("x-ratelimit-bucket"),
            is_global=headers.get("x-ratelimit-global", "").lower() == "true",
            scope=RateLimitScope(scope_value) if scope_value else None,
        )


def _number[T: (int, float)](value: str | None, kind: type[T]) -> T | None:
    """A header as a number; `None` when it is missing or not one."""
    if value is None:
        return None
    try:
        return kind(value)
    except ValueError:
        return None


class WaitTooLongError(ShoalError):
    """A rate limit would hold a request longer than the caller is willing to wait."""

    def __init__(self, seconds: float) -> None:
        """The request would wait `seconds`."""
        super().__init__(f"the rate limit would hold the request for {seconds:.2f}s")
        self.seconds: float = seconds


def _check_wait(seconds: float, max_wait: float | None) -> None:
    if max_wait is not None and seconds > max_wait:
        raise WaitTooLongError(seconds)


class RateLimiter(Protocol):
    """Decides when a request may be sent, and learns from every response."""

    __slots__ = ()

    async def acquire(self, route: CompiledRoute, *, max_wait: float | None = None) -> None:
        """Wait until `route` may be sent. Every `acquire` must be followed by exactly one `release`.

        Raises:
            WaitTooLongError: The wait would be longer than `max_wait` seconds; nothing was taken,
                so no `release` follows.
        """
        ...

    def release(
        self,
        route: CompiledRoute,
        status: int | None,
        headers: RateLimitHeaders | None,
        retry_after: float | None,
    ) -> None:
        """Record the outcome of a request. `status` is `None` when no response arrived."""
        ...


@final
class _Bucket:
    """One rate limit bucket for one set of major parameters."""

    __slots__ = ("_clock", "_responded", "discovering", "limit", "remaining", "reset_at")

    def __init__(self, clock: Clock) -> None:
        self._clock: Clock = clock
        self.limit: int | None = None
        self.remaining: int | None = None
        self.reset_at: float | None = None
        self.discovering: asyncio.Event | None = None
        self._responded: asyncio.Event | None = None

    async def acquire(self, max_wait: float | None) -> bool:
        """Take one request from the bucket, or wait and return `False`.

        After any wait the route may belong to another bucket (Discord named it, or renamed it), so
        the caller looks its bucket up again and retries.
        """
        if self.discovering is not None:
            await self.discovering.wait()
            return False
        now = self._clock.monotonic()
        if self.reset_at is not None and now >= self.reset_at:
            self.remaining = self.limit or None
            self.reset_at = None
        if self.limit is None:
            self.discovering = asyncio.Event()
            return True
        if self.remaining is None:
            return True
        if self.remaining > 0:
            self.remaining -= 1
            return True
        if self.reset_at is None:
            # The window's requests are used up and none has answered yet with the next reset.
            if self._responded is None:
                self._responded = asyncio.Event()
            await self._responded.wait()
            return False
        _check_wait(self.reset_at - now, max_wait)
        await self._clock.sleep(self.reset_at - now)
        return False

    def update(self, headers: RateLimitHeaders | None, *, succeeded: bool) -> None:
        """Learn where the bucket stands from a response's headers.

        A successful response without headers means the route has no limit. A failed one without
        headers (a Cloudflare error page, a proxy's 502) says nothing, so discovery goes on, one
        request at a time, rather than letting every waiting request through at once.
        """
        if headers is not None and headers.limit is not None:
            self.limit = headers.limit
            if headers.reset_after is None:
                # Without a reset time an exhausted bucket could never refill; stop enforcing it.
                self.remaining = None
            else:
                self.reset_at = self._clock.monotonic() + headers.reset_after
                if headers.remaining is not None:
                    self.remaining = (
                        headers.remaining
                        if self.remaining is None
                        else min(self.remaining, headers.remaining)
                    )
            self.wake()
        elif self.limit is None:
            if succeeded:
                self.limit = 0
                self.remaining = None
            self.wake()
        else:
            self.unanswered()

    def unanswered(self) -> None:
        """A request ended without saying where the bucket stands (no response, or no headers).

        While no reset time is known its request is handed back; otherwise every request could end
        this way and the bucket would wait for an answer that never comes.
        """
        if self.reset_at is None and self.limit and self.remaining is not None:
            self.remaining = min(self.limit, self.remaining + 1)
        self.wake()

    def block_for(self, seconds: float) -> None:
        self.remaining = 0
        if self.limit is None:
            self.limit = 1
        self.reset_at = self._clock.monotonic() + seconds
        self.wake()

    def wake(self) -> None:
        """Wake every waiter: the bucket's state, or the route's bucket, may have changed."""
        if self.discovering is not None:
            self.discovering.set()
            self.discovering = None
        if self._responded is not None:
            self._responded.set()
            self._responded = None

    def is_idle(self, now: float) -> bool:
        return (
            self.discovering is None
            and self._responded is None
            and (self.reset_at is None or now >= self.reset_at)
        )


@final
class _GlobalLimiter:
    """A token bucket refilled at `per_second`, plus a hard pause after a global 429."""

    __slots__ = ("_clock", "_paused_until", "_per_second", "_tokens", "_updated")

    def __init__(self, clock: Clock, per_second: int | None) -> None:
        self._clock: Clock = clock
        self._per_second: int | None = per_second
        self._tokens: float = float(per_second or 0)
        self._updated: float = clock.monotonic()
        self._paused_until: float = 0.0

    async def acquire(self, max_wait: float | None) -> None:
        while True:
            now = self._clock.monotonic()
            if now < self._paused_until:
                _check_wait(self._paused_until - now, max_wait)
                await self._clock.sleep(self._paused_until - now)
                continue
            if self._per_second is None:
                return
            elapsed = now - self._updated
            self._updated = now
            self._tokens = min(float(self._per_second), self._tokens + elapsed * self._per_second)
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            await self._clock.sleep((1.0 - self._tokens) / self._per_second)

    def pause(self, seconds: float) -> None:
        self._paused_until = max(self._paused_until, self._clock.monotonic() + seconds)


@final
class InvalidRequestGuard:
    """Counts invalid responses in a sliding window and holds requests back near the ban threshold.

    Args:
        clock: Time source.
        limit: Invalid responses allowed per window (Discord's is 10,000).
        window: Window length in seconds (Discord's is 600).
        safety_margin: How many invalid responses below `limit` to start holding requests. Requests
            that are already in flight can still fail, so the margin must cover your concurrency.
        metrics: Receives the current window count as `shoal_rest_invalid_requests`.

    Discord: https://docs.discord.com/developers/topics/rate-limits#invalid-request-limit-aka-cloudflare-bans
    """

    __slots__ = ("_clock", "_events", "_holding", "_metrics", "_threshold", "_warned", "_window")

    def __init__(
        self,
        clock: Clock,
        *,
        limit: int = INVALID_REQUEST_LIMIT,
        window: float = INVALID_REQUEST_WINDOW,
        safety_margin: int = INVALID_REQUEST_SAFETY_MARGIN,
        metrics: Metrics | None = None,
    ) -> None:
        """Create a guard; see the class docstring for the arguments."""
        if not 0 <= safety_margin < limit:
            msg = "safety_margin must be between 0 and limit - 1"
            raise ValueError(msg)
        self._clock: Clock = clock
        self._window: float = window
        self._threshold: int = limit - safety_margin
        self._events: deque[float] = deque()  # bounded by the window: pruned as events age out
        self._warned: bool = False
        self._holding: bool = False  # logged once per hold, not once per waiter per wake
        self._metrics: Metrics = metrics or NoopMetrics()

    @property
    def count(self) -> int:
        """Invalid responses recorded in the current window."""
        self._expire(self._clock.monotonic())
        return len(self._events)

    def record(self, status: int, scope: RateLimitScope | None) -> None:
        """Count a response if Discord counts it as invalid (shared-scope 429s are free)."""
        if status not in INVALID_REQUEST_STATUSES or (
            status == HTTPStatus.TOO_MANY_REQUESTS and scope is RateLimitScope.SHARED
        ):
            return
        now = self._clock.monotonic()
        self._expire(now)
        self._events.append(now)
        self._metrics.set(REST_INVALID_REQUESTS, len(self._events))
        if len(self._events) >= self._threshold // 2 and not self._warned:
            self._warned = True
            _log.warning(
                "invalid HTTP responses reached %d in the last %.0fs; Discord bans the IP at %d",
                len(self._events),
                self._window,
                INVALID_REQUEST_LIMIT,
            )

    async def acquire(self, max_wait: float | None = None) -> None:
        """Wait while the window is at the threshold.

        Raises:
            WaitTooLongError: The hold would be longer than `max_wait` seconds.
        """
        while True:
            now = self._clock.monotonic()
            self._expire(now)
            if len(self._events) < self._threshold:
                self._holding = False
                return
            wait = self._events[0] + self._window - now
            _check_wait(wait, max_wait)
            if not self._holding:
                self._holding = True
                _log.error("holding requests to stay under Discord's invalid request ban")
            await self._clock.sleep(wait)

    def _expire(self, now: float) -> None:
        cutoff = now - self._window
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()
        if not self._events:
            self._warned = False


@final
class LocalRateLimiter(RateLimiter):
    """An in-process `RateLimiter` enforcing route buckets, the global limit and the invalid guard.

    Args:
        clock: Time source; defaults to the system clock.
        global_per_second: Global requests per second, or `None` if Discord lifted the limit for you.
        invalid_guard: The invalid request guard; one with default settings is created if omitted.
        metrics: Passed to the default invalid request guard.
    """

    __slots__ = ("_buckets", "_clock", "_global", "_hashes", "_invalid", "_pruned_at")

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        global_per_second: int | None = GLOBAL_REQUESTS_PER_SECOND,
        invalid_guard: InvalidRequestGuard | None = None,
        metrics: Metrics | None = None,
    ) -> None:
        """Create a limiter; see the class docstring for the arguments."""
        self._clock: Clock = clock or SystemClock()
        self._global: _GlobalLimiter = _GlobalLimiter(self._clock, global_per_second)
        self._invalid: InvalidRequestGuard = invalid_guard or InvalidRequestGuard(
            self._clock, metrics=metrics
        )
        self._hashes: dict[str, str] = {}
        self._buckets: dict[str, _Bucket] = {}
        self._pruned_at: float | None = None

    @property
    def invalid_guard(self) -> InvalidRequestGuard:
        """The invalid request guard, for metrics."""
        return self._invalid

    @property
    def bucket_count(self) -> int:
        """Buckets currently tracked; idle ones are pruned once this passes a threshold."""
        return len(self._buckets)

    def bucket_key(self, route: CompiledRoute) -> str:
        """The key a route's bucket is stored under: Discord's hash once known, else the route."""
        identity = self._hashes.get(route.route.key, route.route.key)
        return f"{identity}|{route.major}"

    @override
    async def acquire(self, route: CompiledRoute, *, max_wait: float | None = None) -> None:
        await self._invalid.acquire(max_wait)
        while not await self._bucket(self.bucket_key(route)).acquire(max_wait):
            pass  # waited; the route's bucket may have changed meanwhile
        if route.route.global_limit:
            try:
                await self._global.acquire(max_wait)
            except BaseException:
                self.release(route, None, None, None)
                raise

    @override
    def release(
        self,
        route: CompiledRoute,
        status: int | None,
        headers: RateLimitHeaders | None,
        retry_after: float | None,
    ) -> None:
        if headers is not None and headers.bucket:
            self._learn_bucket(route, headers.bucket)
        bucket = self._bucket(self.bucket_key(route))
        if status is None:
            bucket.unanswered()
            return
        self._invalid.record(status, headers.scope if headers is not None else None)
        if status == HTTPStatus.TOO_MANY_REQUESTS and retry_after is not None:
            if headers is not None and headers.is_global:
                _log.warning("global rate limit hit; pausing every request for %.2fs", retry_after)
                self._global.pause(retry_after)
                bucket.unanswered()
            else:
                bucket.update(headers, succeeded=False)
                bucket.block_for(retry_after)
        else:
            bucket.update(headers, succeeded=HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES)
        self._prune()

    def _learn_bucket(self, route: CompiledRoute, named: str) -> None:
        """Record the bucket Discord named for `route`, moving waiters off the one they used.

        Until the first response, requests wait on a provisional `route|major` bucket; another major
        parameter's provisional bucket may still be discovering when the name is learned. Waiters on
        any bucket the route no longer uses are woken and look their bucket up again, so the two
        never hand out the same quota twice and nobody waits on a bucket no response will reach.
        """
        previous = self._hashes.get(route.route.key)
        if previous is None:
            # Provisional buckets exist only until the route's first name is learned: scanning for
            # them on every later response would cost a pass over every bucket each time.
            provisional = f"{route.route.key}|"
            for key in [key for key in self._buckets if key.startswith(provisional)]:
                self._buckets.pop(key).wake()
        if previous == named:
            return
        self._hashes[route.route.key] = named
        if previous is not None:
            # The old bucket may be shared with other routes, so it stays; its waiters re-check.
            old = self._buckets.get(f"{previous}|{route.major}")
            if old is not None:
                old.wake()

    def _bucket(self, key: str) -> _Bucket:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(self._clock)
            self._buckets[key] = bucket
        return bucket

    def _prune(self) -> None:
        """Forget idle buckets once there are many, at most once per `BUCKET_PRUNE_INTERVAL`.

        Never on every response: a large bot keeps more than the threshold active, and scanning them
        all for each response would cost more than the memory it frees.
        """
        if len(self._buckets) < BUCKET_PRUNE_THRESHOLD:
            return
        now = self._clock.monotonic()
        if self._pruned_at is not None and now - self._pruned_at < BUCKET_PRUNE_INTERVAL:
            return
        self._pruned_at = now
        for key in [key for key, bucket in self._buckets.items() if bucket.is_idle(now)]:
            del self._buckets[key]
