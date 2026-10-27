import logging
import time

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from shoal.redis.jobs import RedisJobStore
from shoal.tasks.jobs import Job, JobStoreError

PAST = time.time() - 3600
"""Due by Redis's clock, which claims compare with."""

FUTURE = time.time() + 3600


def job(job_id: str, due: float, *, name: str = "reminder", cron: str | None = None) -> Job:
    return Job(id=job_id, name=name, due=due, data={"user": 1}, cron=cron)


async def test_each_due_job_is_claimed_by_one_process(redis: Redis, other: Redis) -> None:
    first, second = RedisJobStore(redis), RedisJobStore(other)
    assert first.shared
    await first.add(job("a", PAST))
    await first.add(job("b", PAST + 1))
    await first.add(job("later", FUTURE))
    assert await second.next_due() == pytest.approx(PAST, abs=0.001)
    assert [claimed.id for claimed in await first.claim(0, 1)] == ["a"]
    assert [claimed.id for claimed in await second.claim(0, 10)] == ["b"]
    assert await first.claim(0, 10) == []
    # Claimed jobs are leased until done; the leases end before the later job is due.
    next_due = await first.next_due()
    assert next_due is not None
    assert next_due < FUTURE


async def test_done_forgets_a_job_unless_it_was_scheduled_again(redis: Redis) -> None:
    store = RedisJobStore(redis)
    await store.add(job("once", PAST))
    await store.add(job("every", PAST, cron="* * * * *"))
    once, every = await store.claim(0, 10)
    assert await store.reschedule(job("every", FUTURE, cron="* * * * *"))
    await store.done(once)
    await store.done(every)
    assert await store.get("once") is None
    assert await store.get("every") == job("every", FUTURE, cron="* * * * *")


async def test_a_job_cancelled_while_it_runs_is_not_rescheduled(redis: Redis) -> None:
    store = RedisJobStore(redis)
    await store.add(job("every", PAST, cron="* * * * *"))
    (claimed,) = await store.claim(0, 10)
    assert await store.cancel("every")
    assert not await store.reschedule(job("every", FUTURE, cron="* * * * *"))
    await store.done(claimed)
    assert await store.jobs() == []


async def test_a_job_whose_lease_ran_out_is_claimed_again_as_due_now(redis: Redis) -> None:
    store = RedisJobStore(redis, lease=0)
    await store.add(job("a", PAST))
    assert len(await store.claim(0, 10)) == 1
    # Its process died without finishing it: the next claim runs it again, due now (not missed).
    (retried,) = await store.claim(12345, 10)
    assert (retried.id, retried.due) == ("a", 12345)


async def test_an_unreadable_job_is_dropped_without_holding_up_the_rest(
    redis: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    store = RedisJobStore(redis)
    await store.add(job("good", PAST))
    await redis.hset("shoal:jobs:data", "broken", b"\xc1")
    await redis.zadd("shoal:jobs:due", {"broken": 0})
    with caplog.at_level(logging.WARNING, logger="shoal.redis"):
        assert [claimed.id for claimed in await store.claim(0, 10)] == ["good"]
    assert "could not be read" in caplog.text
    assert await redis.hexists("shoal:jobs:data", "broken") == 0
    await redis.hset("shoal:jobs:data", "broken", b"\xc1")
    assert await store.jobs() == [job("good", PAST)]
    with pytest.raises(JobStoreError, match="could not be read"):
        _ = await store.get("broken")


async def test_jobs_are_listed_cancelled_and_isolated_by_prefix(redis: Redis) -> None:
    store = RedisJobStore(redis)
    await store.add(job("a", FUTURE))
    await store.add(job("b", FUTURE, name="digest"))
    assert [listed.id for listed in await store.jobs("digest")] == ["b"]
    assert len(await store.jobs()) == 2
    assert await RedisJobStore(redis, prefix="another-bot").jobs() == []
    assert await store.cancel("a")
    assert not await store.cancel("a")
    assert await store.get("a") is None
    assert await RedisJobStore(redis, prefix="another-bot").next_due() is None


async def test_an_unreachable_redis_raises_job_store_errors(
    redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = RedisJobStore(redis)

    async def refuse(*_: object, **__: object) -> object:
        msg = "refused"
        raise RedisConnectionError(msg)

    for method in ("eval", "hget", "hvals"):
        monkeypatch.setattr(redis, method, refuse)
    with pytest.raises(JobStoreError, match="refused"):
        _ = await store.claim(0, 10)
    with pytest.raises(JobStoreError, match="refused"):
        _ = await store.get("a")
    with pytest.raises(JobStoreError, match="refused"):
        _ = await store.jobs()


async def test_unexpected_answers_raise_job_store_errors(
    redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = RedisJobStore(redis)

    async def answer(*_: object, **__: object) -> object:
        return 7

    monkeypatch.setattr(redis, "eval", answer)
    with pytest.raises(JobStoreError, match="answered a job claim with 7"):
        _ = await store.claim(0, 10)
    with pytest.raises(JobStoreError, match="where a job was expected"):
        _ = await store.next_due()
