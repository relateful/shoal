import asyncio
import logging

import pytest

from shoal.core.metrics import REST_INVALID_REQUESTS, InMemoryMetrics
from shoal.payloads import RateLimitScope
from shoal.rest import endpoints
from shoal.rest.defaults import BUCKET_PRUNE_INTERVAL, BUCKET_PRUNE_THRESHOLD
from shoal.rest.ratelimit import InvalidRequestGuard, LocalRateLimiter, RateLimitHeaders, WaitTooLongError
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


async def test_waits_longer_than_the_caller_allows_are_refused_without_taking_anything() -> None:
    clock = FakeClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    limiter.release(ROUTE, 429, headers(remaining=0, reset_after=30.0), 30.0)
    with pytest.raises(WaitTooLongError) as bucket:
        await limiter.acquire(ROUTE, max_wait=10.0)
    assert bucket.value.seconds == pytest.approx(30.0)
    global_headers = RateLimitHeaders.parse({"x-ratelimit-global": "true", "x-ratelimit-scope": "global"})
    await limiter.acquire(OTHER_CHANNEL)
    limiter.release(OTHER_CHANNEL, 429, global_headers, 20.0)
    with pytest.raises(WaitTooLongError):
        await limiter.acquire(OTHER_CHANNEL, max_wait=10.0)
    # Within the limit, it waits as before; nothing was taken by the refused attempts.
    await limiter.acquire(OTHER_CHANNEL, max_wait=60.0)
    assert clock.sleeps == [20.0]
    guard = InvalidRequestGuard(clock, limit=4, window=60.0, safety_margin=1)
    for _ in range(3):
        guard.record(401, None)
    with pytest.raises(WaitTooLongError):
        await guard.acquire(max_wait=10.0)


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


async def test_invalid_guard_logs_a_hold_once_however_many_requests_wait(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = ManualClock()
    guard = InvalidRequestGuard(clock, limit=4, window=60.0, safety_margin=1)
    for _ in range(4):
        guard.record(403, None)
        await clock.advance(10.0)
    with caplog.at_level(logging.ERROR, logger="shoal.rest.ratelimit"):
        waiters = [asyncio.create_task(guard.acquire()) for _ in range(5)]
        await settle()
        await clock.advance(20.0)  # the oldest ages out, but the window is still at the threshold
        await settle()
        assert not any(waiter.done() for waiter in waiters)
        await clock.advance(10.0)
        await settle()
        assert all(waiter.done() for waiter in waiters)
        holds = [record for record in caplog.records if "holding requests" in record.message]
        assert len(holds) == 1
        # A later hold is logged again.
        for _ in range(3):
            guard.record(403, None)
        waiter = asyncio.create_task(guard.acquire())
        await settle()
        assert len([record for record in caplog.records if "holding requests" in record.message]) == 2
        waiter.cancel()


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


async def test_a_failed_response_without_headers_keeps_discovering() -> None:
    clock = ManualClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    waiting = [asyncio.create_task(limiter.acquire(ROUTE)) for _ in range(5)]
    await settle()
    limiter.release(ROUTE, 502, RateLimitHeaders.parse({}), None)
    await settle()
    assert sum(task.done() for task in waiting) == 1
    for task in waiting:
        task.cancel()


async def test_a_major_parameter_whose_discovery_fails_is_not_stranded() -> None:
    clock = ManualClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    await limiter.acquire(OTHER_CHANNEL)
    behind = asyncio.create_task(limiter.acquire(OTHER_CHANNEL))
    await settle()
    limiter.release(ROUTE, 200, headers(remaining=1, bucket="hashed"), None)
    limiter.release(OTHER_CHANNEL, None, None, None)
    await asyncio.wait_for(behind, timeout=1)


async def test_buckets_are_pruned_at_most_once_per_interval() -> None:
    clock = ManualClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)

    async def use(channel: int) -> None:
        route = endpoints.GET_CHANNEL.compile(channel_id=channel)
        await limiter.acquire(route)
        limiter.release(route, 200, RateLimitHeaders.parse({}), None)

    for channel in range(BUCKET_PRUNE_THRESHOLD):
        await use(channel)
    assert limiter.bucket_count < BUCKET_PRUNE_THRESHOLD
    for channel in range(BUCKET_PRUNE_THRESHOLD, 2 * BUCKET_PRUNE_THRESHOLD + 10):
        await use(channel)
    crowded = limiter.bucket_count
    assert crowded > BUCKET_PRUNE_THRESHOLD
    await clock.advance(BUCKET_PRUNE_INTERVAL)
    await use(10_000)
    assert limiter.bucket_count < crowded


async def test_a_late_response_never_raises_what_is_left_in_the_window() -> None:
    clock = FakeClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    limiter.release(ROUTE, 200, headers(remaining=1, reset_after=10.0), None)
    await limiter.acquire(ROUTE)  # the window's last request
    # An answer to an earlier request, sent before that one was counted, still says one is left.
    limiter.release(ROUTE, 200, headers(remaining=1, reset_after=10.0), None)
    await limiter.acquire(ROUTE)
    assert clock.sleeps == [10.0]


async def test_a_shorter_global_pause_never_cuts_a_longer_one() -> None:
    clock = FakeClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    global_headers = RateLimitHeaders.parse({"x-ratelimit-global": "true"})
    await limiter.acquire(ROUTE)
    await limiter.acquire(OTHER_CHANNEL)  # both in flight when the 429s come back
    limiter.release(ROUTE, 429, global_headers, 10.0)
    limiter.release(OTHER_CHANNEL, 429, global_headers, 1.0)
    await limiter.acquire(endpoints.GET_CHANNEL.compile(channel_id=3))
    assert clock.sleeps == [10.0]


async def test_handed_back_requests_never_exceed_the_bucket_limit() -> None:
    clock = ManualClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)
    limiter.release(ROUTE, 200, headers(remaining=1, reset_after=1.0), None)
    await clock.advance(2.0)
    await limiter.acquire(ROUTE)  # refilled to the limit of 2, one taken
    limiter.release(ROUTE, None, None, None)
    limiter.release(ROUTE, None, None, None)  # one more hand-back than was taken
    waiters = [asyncio.create_task(limiter.acquire(ROUTE)) for _ in range(3)]
    await settle()
    assert sum(waiter.done() for waiter in waiters) == 2
    limiter.release(ROUTE, 200, headers(remaining=2, reset_after=1.0), None)
    await clock.advance(2.0)
    await settle()
    assert all(waiter.done() for waiter in waiters)


async def test_a_global_429_while_discovering_lets_the_route_go_on() -> None:
    clock = FakeClock()
    limiter = LocalRateLimiter(clock=clock, global_per_second=None)
    await limiter.acquire(ROUTE)  # discovers the bucket
    waiter = asyncio.create_task(limiter.acquire(ROUTE))
    await settle()
    assert not waiter.done()
    limiter.release(ROUTE, 429, RateLimitHeaders.parse({"x-ratelimit-global": "true"}), 2.0)
    await asyncio.wait_for(waiter, timeout=5)
    assert clock.sleeps == [2.0]
