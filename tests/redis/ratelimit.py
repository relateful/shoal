import asyncio
import logging

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from shoal.core.clock import Clock
from shoal.redis.ratelimit import RedisRateLimiter
from shoal.rest import endpoints
from shoal.rest.ratelimit import RateLimitHeaders, WaitTooLongError
from tests.support.fakes import FakeClock, ManualClock
from tests.support.redis import keys_of

ROUTE = endpoints.GET_CHANNEL.compile(channel_id=1)
OTHER = endpoints.GET_CHANNEL.compile(channel_id=2)


def headers(remaining: int, reset_after: float, **extra: str) -> RateLimitHeaders:
    return RateLimitHeaders.parse(
        {
            "x-ratelimit-limit": "5",
            "x-ratelimit-remaining": str(remaining),
            "x-ratelimit-reset-after": str(reset_after),
            "x-ratelimit-bucket": "abc",
            **extra,
        }
    )


def limiter(redis: Redis, clock: Clock, **options: int | None) -> RedisRateLimiter:
    global_per_second = options.get("global_per_second")
    threshold = options.get("invalid_threshold")
    return RedisRateLimiter(
        redis,
        clock=clock,
        global_per_second=global_per_second,
        invalid_threshold=threshold if threshold is not None else 10,
    )


async def test_an_empty_bucket_holds_every_process(redis: Redis, other: Redis) -> None:
    clock = FakeClock()
    first, second = limiter(redis, clock), limiter(other, clock)
    await first.acquire(ROUTE)
    first.release(ROUTE, 200, headers(remaining=0, reset_after=10.0), None)
    await first.drain()
    # Redis keeps its own time: the tests read each hold through `max_wait` rather than wait it out.
    with pytest.raises(WaitTooLongError) as held:
        await second.acquire(ROUTE, max_wait=1.0)
    assert 9.0 < held.value.seconds <= 10.0
    # A route of another bucket is not held.
    await second.acquire(OTHER)
    assert clock.sleeps == []


async def test_what_is_left_is_counted_down_across_processes(redis: Redis, other: Redis) -> None:
    clock = FakeClock()
    first, second = limiter(redis, clock), limiter(other, clock)
    await first.acquire(ROUTE)
    first.release(ROUTE, 200, headers(remaining=2, reset_after=10.0), None)
    await first.drain()
    await second.acquire(ROUTE)
    second.release(ROUTE, None, None, None)  # sent; the answer is not back yet
    await second.acquire(OTHER)  # another bucket costs this one nothing
    await first.acquire(ROUTE)
    first.release(ROUTE, None, None, None)
    assert clock.sleeps == []
    with pytest.raises(WaitTooLongError):
        await second.acquire(ROUTE, max_wait=1.0)
    # An answer sent before the last requests were counted cannot raise what is left.
    first.release(ROUTE, 200, headers(remaining=1, reset_after=10.0), None)
    await first.drain()
    with pytest.raises(WaitTooLongError):
        await second.acquire(ROUTE, max_wait=1.0)


async def test_a_new_window_replaces_what_was_left(redis: Redis) -> None:
    clock = FakeClock()
    shared = limiter(redis, clock)
    await shared.acquire(ROUTE)
    shared.release(ROUTE, 200, headers(remaining=0, reset_after=1.0), None)
    await shared.drain()
    shared.release(ROUTE, 200, headers(remaining=4, reset_after=20.0), None)
    await shared.drain()
    assert await redis.hget((await keys_of(redis, "shoal:rest:bucket:*"))[0], "remaining") == b"4"


async def test_the_global_limit_is_shared(redis: Redis, other: Redis) -> None:
    clock = FakeClock()
    first = limiter(redis, clock, global_per_second=2)
    second = limiter(other, clock, global_per_second=2)
    await first.acquire(ROUTE)
    await second.acquire(OTHER)
    third = endpoints.GET_CHANNEL.compile(channel_id=3)
    with pytest.raises(WaitTooLongError) as held:
        await second.acquire(third, max_wait=0.0)
    assert 0 < held.value.seconds <= 0.5


async def test_a_global_429_pauses_every_process_and_a_route_429_its_bucket(
    redis: Redis, other: Redis
) -> None:
    clock = FakeClock()
    first, second = limiter(redis, clock), limiter(other, clock)
    await first.acquire(ROUTE)
    first.release(ROUTE, 429, RateLimitHeaders.parse({"x-ratelimit-global": "true"}), 30.0)
    await first.drain()
    with pytest.raises(WaitTooLongError) as paused:
        await second.acquire(OTHER, max_wait=1.0)
    assert 29.0 < paused.value.seconds <= 30.0
    # A route's own 429 holds only that bucket; it does not end a longer pause.
    await redis.delete("shoal:rest:global:paused")
    await first.acquire(OTHER)
    first.release(OTHER, 429, headers(remaining=0, reset_after=5.0), 5.0)
    await first.drain()
    with pytest.raises(WaitTooLongError) as blocked:
        await second.acquire(OTHER, max_wait=1.0)
    assert 4.0 < blocked.value.seconds <= 5.0


async def test_invalid_responses_are_counted_per_ip_across_processes(
    redis: Redis, other: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FakeClock()
    first = limiter(redis, clock, invalid_threshold=2)
    second = limiter(other, clock, invalid_threshold=2)
    for _ in range(2):
        await first.acquire(OTHER)
        first.release(OTHER, 403, None, None)
    # A shared-scope 429 costs nothing.
    await first.acquire(OTHER)
    first.release(OTHER, 429, headers(remaining=1, reset_after=1.0, **{"x-ratelimit-scope": "shared"}), 0.1)
    await first.drain()
    with pytest.raises(WaitTooLongError) as held:
        await second.acquire(ROUTE, max_wait=60.0)
    assert 590.0 < held.value.seconds <= 600.0
    waiting = limiter(other, ManualClock(), invalid_threshold=2)  # sleeps until the test moves it
    with caplog.at_level(logging.ERROR, logger="shoal.redis"), pytest.raises(TimeoutError):
        async with asyncio.timeout(0.1):
            await waiting.acquire(ROUTE)
    assert "invalid request ban" in caplog.text


async def test_token_routes_never_reach_a_redis_key(redis: Redis) -> None:
    clock = FakeClock()
    shared = limiter(redis, clock)
    route = endpoints.DELETE_WEBHOOK_WITH_TOKEN.compile(webhook_id=9, webhook_token="secret-token-123")
    await shared.acquire(route)
    shared.release(route, 200, headers(remaining=1, reset_after=1.0), None)
    await shared.drain()
    keys = await keys_of(redis)
    assert keys
    assert not any("secret" in key for key in keys)
    assert shared.local.bucket_count >= 1


async def test_a_refused_shared_wait_gives_the_local_quota_back(redis: Redis) -> None:
    clock = FakeClock()
    shared = limiter(redis, clock, global_per_second=1)
    await shared.acquire(ROUTE)
    with pytest.raises(WaitTooLongError):
        await shared.acquire(OTHER, max_wait=0.0)
    # The local limiter was released for the refused request: the route is not stuck discovering.
    shared.release(ROUTE, 200, headers(remaining=3, reset_after=5.0), None)
    await shared.drain()
    with pytest.raises(WaitTooLongError):
        await shared.acquire(OTHER, max_wait=0.0)


async def test_a_redis_failure_while_recording_is_logged(
    redis: Redis, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    shared = limiter(redis, clock)
    await shared.acquire(ROUTE)

    async def gone(*_: object) -> object:
        raise ConnectionError

    monkeypatch.setattr(redis, "eval", gone)
    with caplog.at_level(logging.ERROR, logger="shoal.redis"):
        shared.release(ROUTE, 200, headers(remaining=1, reset_after=1.0), None)
        await shared.drain()
    assert "could not record" in caplog.text


async def test_only_the_script_answer_is_understood(redis: Redis, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    answers: list[object] = [[2, -5], [0, 0], "nope", [1, "x"]]

    async def answer(*_: object) -> object:
        return answers.pop(0)

    monkeypatch.setattr(redis, "eval", answer)
    shared = limiter(redis, clock)
    await shared.acquire(ROUTE)  # a negative wait is no wait
    assert clock.sleeps == [0]
    shared.release(ROUTE, None, None, None)
    for _ in range(2):
        with pytest.raises(TypeError, match="rate limit script"):
            await shared.acquire(ROUTE)


async def test_requests_keep_the_local_limits_while_redis_is_away(
    redis: Redis, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FakeClock()
    shared = limiter(redis, clock)
    real = redis.eval

    async def gone(*_: object) -> object:
        raise RedisConnectionError

    monkeypatch.setattr(redis, "eval", gone)
    with caplog.at_level(logging.INFO, logger="shoal.redis"):
        await shared.acquire(ROUTE)
        shared.release(ROUTE, None, None, None)
        await shared.acquire(ROUTE)
        shared.release(ROUTE, None, None, None)
        assert caplog.text.count("Redis cannot be reached") == 1
        monkeypatch.setattr(redis, "eval", real)
        await shared.acquire(OTHER)
    assert "can be reached again" in caplog.text


async def test_max_wait_bounds_the_whole_wait(redis: Redis) -> None:
    clock = FakeClock()
    shared = limiter(redis, clock, global_per_second=1)
    await shared.acquire(ROUTE)
    # The global limit holds the next request about a second, past what `max_wait` leaves.
    with pytest.raises(WaitTooLongError):
        await shared.acquire(OTHER, max_wait=0.5)
