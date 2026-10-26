import asyncio

import pytest

from shoal.gateway.sharding import (
    LocalIdentifyLimiter,
    SessionStartsExhaustedError,
    rate_limit_key,
    shard_for_guild,
    wait_for_session_starts,
)
from shoal.payloads import SessionStartLimit
from tests.support.fakes import FakeClock, ManualClock, settle


@pytest.mark.parametrize(
    ("guild_id", "count", "expected"), [(41771983423143937, 1, 0), (41771983423143937, 4, 2)]
)
def test_shard_for_guild_matches_the_documented_formula(guild_id: int, count: int, expected: int) -> None:
    assert shard_for_guild(guild_id, count) == expected
    assert shard_for_guild(guild_id, count) == (guild_id >> 22) % count


def test_sharding_helpers_validate() -> None:
    with pytest.raises(ValueError, match="shard_count"):
        shard_for_guild(1, 0)
    with pytest.raises(ValueError, match="max_concurrency"):
        rate_limit_key(1, 0)
    with pytest.raises(ValueError, match="max_concurrency"):
        LocalIdentifyLimiter(0)
    assert rate_limit_key(17, 16) == 1


async def test_identify_limiter_lets_each_bucket_identify_once_per_window() -> None:
    clock = FakeClock()
    limiter = LocalIdentifyLimiter(4, clock=clock)
    times: dict[int, float] = {}

    async def identify(shard_id: int) -> None:
        async with limiter.slot(shard_id):
            times[shard_id] = clock.monotonic()

    await asyncio.gather(*(identify(shard_id) for shard_id in range(8)))
    first_round = {times[shard_id] for shard_id in range(4)}
    assert first_round == {1_000.0}
    for shard_id in range(4, 8):
        assert times[shard_id] - times[shard_id - 4] >= 5.0
    assert limiter.max_concurrency == 4


def limit(remaining: int, total: int = 1000) -> SessionStartLimit:
    return SessionStartLimit(total=total, remaining=remaining, reset_after=3_600_000, max_concurrency=1)


async def test_session_starts_wait_for_the_daily_reset_when_too_few_are_left() -> None:
    clock = ManualClock()
    await wait_for_session_starts(limit(16), 16, clock=clock)
    waiting = asyncio.create_task(wait_for_session_starts(limit(3), 16, clock=clock))
    await settle()
    assert not waiting.done()
    await clock.advance(3600)
    await waiting
    with pytest.raises(SessionStartsExhaustedError, match="only 1000 a day"):
        await wait_for_session_starts(limit(3), 1001, clock=clock)
