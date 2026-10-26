import pytest
from redis.asyncio import Redis

from shoal.redis.identify import RedisIdentifyLimiter
from tests.support.fakes import FakeClock
from tests.support.redis import keys_of


async def test_one_shard_per_bucket_identifies_every_window_across_processes(
    redis: Redis, other: Redis
) -> None:
    clock = FakeClock()
    first = RedisIdentifyLimiter(redis, max_concurrency=2, clock=clock)
    second = RedisIdentifyLimiter(other, max_concurrency=2, clock=clock)
    async with first.slot(0):
        pass
    async with second.slot(1):
        pass  # bucket 1: no wait
    async with second.slot(2):
        pass  # bucket 0 again, from another process: waits for the window
    no_wait, other_bucket, same_bucket = clock.sleeps
    assert no_wait == other_bucket == 0
    assert 4.5 < same_bucket <= 5.0
    assert first.max_concurrency == 2


async def test_keys_differ_per_concurrency_and_prefix(redis: Redis) -> None:
    clock = FakeClock()
    async with RedisIdentifyLimiter(redis, max_concurrency=1, clock=clock, window=1.0).slot(0):
        pass
    async with RedisIdentifyLimiter(redis, max_concurrency=4, clock=clock).slot(0):
        pass
    async with RedisIdentifyLimiter(redis, max_concurrency=1, clock=clock, prefix="other").slot(0):
        pass
    assert clock.sleeps == [0, 0, 0]
    assert await keys_of(redis) == [
        "other:identify:1:0",
        "shoal:identify:1:0",
        "shoal:identify:4:0",
    ]


def test_a_limiter_needs_a_concurrency(redis: Redis) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        RedisIdentifyLimiter(redis, max_concurrency=0)


async def test_only_a_number_of_milliseconds_is_understood(
    redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def answer(*_: object) -> object:
        return b"5"

    monkeypatch.setattr(redis, "eval", answer)
    with pytest.raises(TypeError, match="not a number of milliseconds"):
        async with RedisIdentifyLimiter(redis, max_concurrency=1, clock=FakeClock()).slot(0):
            pass
