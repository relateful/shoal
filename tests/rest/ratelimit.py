import asyncio

import pytest

from shoal.core.metrics import REST_INVALID_REQUESTS, InMemoryMetrics
from shoal.payloads import RateLimitScope
from shoal.rest import endpoints
from shoal.rest.ratelimit import InvalidRequestGuard, LocalRateLimiter, RateLimitHeaders
from tests.support.fakes import FakeClock, ManualClock, settle

ROUTE = endpoints.GET_CHANNEL.compile(channel_id=1)
OTHER_CHANNEL = endpoints.GET_CHANNEL.compile(channel_id=2)


def headers(remaining: int, reset_after: float = 1.0, bucket: str = "abc", **extra: str) -> RateLimitHeaders:
    return RateLimitHeaders.parse(
        {
            "x-ratelimit-limit": "2",
            "x-ratelimit-remaining": str(remaining),
            "x-ratelimit-reset-after": str(reset_after),
            "x-ratelimit-bucket": bucket,
            **extra,
        }
    )


def test_headers_parse_and_ignore_garbage() -> None:
    parsed = RateLimitHeaders.parse(
        {
            "x-ratelimit-limit": "nope",
            "x-ratelimit-reset-after": "x",
            "x-ratelimit-global": "true",
            "x-ratelimit-scope": "shared",
        }
    )
    assert parsed.limit is None
    assert parsed.reset_after is None
    assert parsed.is_global
    assert parsed.scope is RateLimitScope.SHARED


async def test_first_request_on_a_route_discovers_the_bucket_alone() -> None:
    clock = FakeClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    second = asyncio.create_task(limiter.acquire(ROUTE))
    await asyncio.sleep(0)
    assert not second.done()
    limiter.release(ROUTE, 200, headers(remaining=1), None)
    await second
    limiter.release(ROUTE, 200, headers(remaining=0, reset_after=2.0), None)
    started = clock.monotonic()
    await limiter.acquire(ROUTE)
    assert clock.monotonic() - started >= 2.0


async def test_buckets_are_separate_per_major_parameter() -> None:
    clock = FakeClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    limiter.release(ROUTE, 200, headers(remaining=0, reset_after=10.0), None)
    started = clock.monotonic()
    await limiter.acquire(OTHER_CHANNEL)
    assert clock.monotonic() == started
    assert limiter.bucket_key(ROUTE) == "abc|channel_id=1"


async def test_routes_without_headers_are_unlimited() -> None:
    clock = FakeClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    for _ in range(5):
        await limiter.acquire(ROUTE)
        limiter.release(ROUTE, 200, RateLimitHeaders.parse({}), None)
    assert clock.sleeps == []


async def test_network_failure_releases_discovery() -> None:
    limiter = LocalRateLimiter(clock=FakeClock(), global_per_second=None)
    await limiter.acquire(ROUTE)
    limiter.release(ROUTE, None, None, None)
    await asyncio.wait_for(limiter.acquire(ROUTE), timeout=1)


async def test_route_429_blocks_the_bucket_for_retry_after() -> None:
    clock = FakeClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    limiter.release(ROUTE, 429, headers(remaining=0, reset_after=5.0, **{"x-ratelimit-scope": "user"}), 5.0)
    await limiter.acquire(ROUTE)
    assert clock.sleeps == [5.0]


async def test_global_429_pauses_every_route() -> None:
    clock = FakeClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    global_headers = RateLimitHeaders.parse({"x-ratelimit-global": "true", "x-ratelimit-scope": "global"})
    limiter.release(ROUTE, 429, global_headers, 3.0)
    await limiter.acquire(OTHER_CHANNEL)
    assert clock.sleeps == [3.0]


async def test_a_refilled_bucket_hands_out_only_its_limit_before_discord_answers() -> None:
    clock = ManualClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    limiter.release(ROUTE, 200, headers(remaining=0, reset_after=1.0), None)
    await clock.advance(2.0)
    waiters = [asyncio.create_task(limiter.acquire(ROUTE)) for _ in range(5)]
    await settle()
    assert sum(waiter.done() for waiter in waiters) == 2
    limiter.release(ROUTE, 200, headers(remaining=0, reset_after=1.0), None)
    await settle()
    assert sum(waiter.done() for waiter in waiters) == 2
    await clock.advance(1.0)
    assert sum(waiter.done() for waiter in waiters) == 4
    for waiter in waiters:
        waiter.cancel()


async def test_waiters_follow_the_route_to_the_bucket_discord_names() -> None:
    clock = ManualClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    waiting = [asyncio.create_task(limiter.acquire(ROUTE)) for _ in range(2)]
    await settle()
    limiter.release(ROUTE, 200, headers(remaining=1, bucket="hashed"), None)
    late = asyncio.create_task(limiter.acquire(ROUTE))
    await settle()
    assert sum(task.done() for task in [*waiting, late]) == 1
    for task in [*waiting, late]:
        task.cancel()


async def test_requests_that_never_answer_give_a_refilled_bucket_back() -> None:
    clock = ManualClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    limiter.release(ROUTE, 200, headers(remaining=0, reset_after=1.0), None)
    await clock.advance(2.0)
    await limiter.acquire(ROUTE)
    await limiter.acquire(ROUTE)
    waiting = asyncio.create_task(limiter.acquire(ROUTE))
    await settle()
    assert not waiting.done()
    limiter.release(ROUTE, None, None, None)
    limiter.release(ROUTE, 503, RateLimitHeaders.parse({}), None)
    await asyncio.wait_for(waiting, timeout=1)


async def test_a_second_major_parameter_still_discovering_is_not_stranded() -> None:
    clock = ManualClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    await limiter.acquire(OTHER_CHANNEL)
    behind = asyncio.create_task(limiter.acquire(OTHER_CHANNEL))
    await settle()
    limiter.release(ROUTE, 200, headers(remaining=1, bucket="hashed"), None)
    limiter.release(OTHER_CHANNEL, 200, headers(remaining=1, bucket="hashed"), None)
    await asyncio.wait_for(behind, timeout=1)


async def test_waiters_follow_a_route_whose_bucket_is_renamed() -> None:
    clock = ManualClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    limiter.release(ROUTE, 200, headers(remaining=0, bucket="first"), None)
    await clock.advance(2.0)
    await limiter.acquire(ROUTE)
    await limiter.acquire(ROUTE)
    waiting = asyncio.create_task(limiter.acquire(ROUTE))
    await settle()
    assert not waiting.done()
    limiter.release(ROUTE, 200, headers(remaining=1, bucket="second"), None)
    await asyncio.wait_for(waiting, timeout=1)


async def test_cancelled_global_wait_releases_the_bucket() -> None:
    clock = FakeClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=1)
    await limiter.acquire(OTHER_CHANNEL)
    limiter.release(OTHER_CHANNEL, 200, RateLimitHeaders.parse({}), None)
    blocked = asyncio.create_task(limiter.acquire(ROUTE))
    await asyncio.sleep(0)
    blocked.cancel()
    with pytest.raises(asyncio.CancelledError):
        await blocked
    await asyncio.wait_for(limiter.acquire(ROUTE), timeout=1)


async def test_global_limit_spaces_requests() -> None:
    clock = FakeClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=2)
    for _ in range(4):
        await limiter.acquire(OTHER_CHANNEL)
        limiter.release(OTHER_CHANNEL, 200, RateLimitHeaders.parse({}), None)
    assert clock.sleeps == pytest.approx([0.5, 0.5])


async def test_invalid_guard_counts_only_invalid_statuses() -> None:
    clock = FakeClock()
    metrics = InMemoryMetrics()
    guard = InvalidRequestGuard(clock, limit=10, window=60.0, safety_margin=2, metrics=metrics)
    guard.record(200, None)
    guard.record(404, None)
    guard.record(429, RateLimitScope.SHARED)
    assert guard.count == 0
    guard.record(401, None)
    guard.record(403, None)
    guard.record(429, RateLimitScope.USER)
    assert guard.count == 3
    assert metrics.gauges[InMemoryMetrics.key(REST_INVALID_REQUESTS)] == 3


async def test_invalid_guard_holds_requests_until_the_window_frees() -> None:
    clock = FakeClock()
    guard = InvalidRequestGuard(clock, limit=4, window=60.0, safety_margin=1)
    for _ in range(3):
        guard.record(403, None)
    started = clock.monotonic()
    await guard.acquire()
    assert clock.monotonic() - started >= 60.0
    assert guard.count == 0


def test_invalid_guard_validates_margin() -> None:
    with pytest.raises(ValueError, match="safety_margin"):
        InvalidRequestGuard(FakeClock(), limit=10, safety_margin=10)


async def test_idle_buckets_are_pruned() -> None:
    clock = FakeClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    for channel in range(1100):
        route = endpoints.GET_CHANNEL.compile(channel_id=channel)
        await limiter.acquire(route)
        limiter.release(route, 200, RateLimitHeaders.parse({}), None)
    assert limiter.bucket_count < 1100
