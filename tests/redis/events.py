import asyncio
import logging
import random
from collections.abc import AsyncGenerator, Sequence

import msgspec
import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from shoal.core.dispatch import DispatchEvent
from shoal.redis import events as module
from shoal.redis.events import RedisEventConsumer, RedisEventStream
from tests.support.fakes import FakeClock

STREAM = "shoal:events"


@pytest.fixture(autouse=True)
def short_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "EVENT_READ_BLOCK", 0.05)


def event(sequence: int | None, name: str = "MESSAGE_CREATE", shard_id: int = 0) -> DispatchEvent:
    return DispatchEvent(shard_id, name, sequence, msgspec.Raw(b'{"n":%d}' % (sequence or 0)))


def consumer(
    redis: Redis,
    *,
    group: str | None = None,
    name: str = "worker",
    shard_ids: Sequence[int] | None = None,
    events: Sequence[str] | None = None,
    claim_after: float = 60.0,
    clock: FakeClock | None = None,
) -> RedisEventConsumer:
    return RedisEventConsumer(
        redis,
        group=group,
        consumer=name,
        shard_ids=shard_ids,
        events=events,
        claim_after=claim_after,
        clock=clock or FakeClock(),
        random_source=random.Random(0),
    )


async def take(stream: AsyncGenerator[DispatchEvent], count: int) -> list[DispatchEvent]:
    return [await asyncio.wait_for(anext(stream), timeout=5) for _ in range(count)]


async def started(
    reader: RedisEventConsumer, stream: AsyncGenerator[DispatchEvent]
) -> "asyncio.Future[DispatchEvent]":
    """Ask for the first event, and return once the consumer reads from the stream."""
    first = asyncio.ensure_future(anext(stream))
    await asyncio.wait_for(reader.reading(), timeout=5)
    return first


async def test_a_consumer_receives_what_is_published_after_it_starts(redis: Redis, other: Redis) -> None:
    publisher = RedisEventStream(redis)
    await publisher.publish(event(1))  # before the consumer: not received
    reader = consumer(other, shard_ids=[0], events=["MESSAGE_CREATE"])
    stream = reader.events()
    first = await started(reader, stream)
    await publisher.publish(event(2, "TYPING_START"))
    await publisher.publish(event(3, shard_id=1))
    await publisher.publish(event(4))
    await publisher.publish(event(None))
    assert await asyncio.wait_for(first, timeout=5) == event(4)
    assert await take(stream, 1) == [event(None)]
    reader.close()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), timeout=5)


async def test_a_group_shares_the_events_between_its_consumers(redis: Redis, other: Redis) -> None:
    publisher = RedisEventStream(redis)
    first, second = consumer(redis, group="workers", name="a"), consumer(other, group="workers", name="b")
    first_stream, second_stream = first.events(), second.events()
    to_first = await started(first, first_stream)
    to_second = await started(second, second_stream)
    await publisher.publish(event(1))
    done, waiting = await asyncio.wait({to_first, to_second}, timeout=5, return_when=asyncio.FIRST_COMPLETED)
    assert [future.result() for future in done] == [event(1)]
    # The consumer that took event 1 is handling it, so the next goes to the other.
    await publisher.publish(event(2))
    assert await asyncio.wait_for(waiting.pop(), timeout=5) == event(2)
    first.close()
    second.close()
    await first_stream.aclose()
    await second_stream.aclose()


async def test_an_unfinished_event_is_read_again_when_its_consumer_returns(redis: Redis) -> None:
    publisher = RedisEventStream(redis)
    reader = consumer(redis, group="workers")
    stream = reader.events()
    first = await started(reader, stream)
    await publisher.publish(event(1))
    await publisher.publish(event(2))
    assert await asyncio.wait_for(first, timeout=5) == event(1)
    await stream.aclose()  # crashed while handling event 1: neither is acknowledged
    again = consumer(redis, group="workers").events()
    assert await take(again, 2) == [event(1), event(2)]
    await publisher.publish(event(3))
    assert await take(again, 1) == [event(3)]
    await again.aclose()
    pending = await redis.xpending(STREAM, "workers")
    assert pending["pending"] == 1  # event 3: the loop never asked for the next one


async def test_another_consumer_takes_over_what_a_stopped_one_left(redis: Redis) -> None:
    publisher = RedisEventStream(redis)
    leaving = consumer(redis, group="workers", name="gone")
    gone = leaving.events()
    first = await started(leaving, gone)
    await publisher.publish(event(1))
    assert await asyncio.wait_for(first, timeout=5) == event(1)
    await gone.aclose()
    taker = consumer(redis, group="workers", name="taker", claim_after=0.0).events()
    assert await take(taker, 1) == [event(1)]
    await taker.aclose()


async def test_an_entry_that_is_not_an_event_is_skipped(
    redis: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    reader = consumer(redis)
    stream = reader.events()
    first = await started(reader, stream)
    with caplog.at_level(logging.WARNING, logger="shoal.redis"):
        await redis.xadd(STREAM, {b"other": b"thing"})
        await RedisEventStream(redis).publish(event(1))
        assert await asyncio.wait_for(first, timeout=5) == event(1)
    assert "not a dispatch event" in caplog.text
    await stream.aclose()


async def test_reading_retries_while_redis_is_away(
    redis: Redis, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FakeClock()
    reader = consumer(redis, clock=clock)
    calls = 0
    real = redis.xrevrange

    async def flaky(name: str, count: int | None = None) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RedisConnectionError
        return await real(name, count=count)

    monkeypatch.setattr(redis, "xrevrange", flaky)
    stream = reader.events()
    with caplog.at_level(logging.WARNING, logger="shoal.redis"):
        first = await started(reader, stream)
    assert "retrying" in caplog.text
    assert len(clock.sleeps) == 1
    await RedisEventStream(redis).publish(event(1))
    assert await asyncio.wait_for(first, timeout=5) == event(1)
    await stream.aclose()


async def test_a_group_whose_stream_was_deleted_is_joined_again(redis: Redis) -> None:
    publisher = RedisEventStream(redis)
    reader = consumer(redis, group="workers")
    stream = reader.events()
    first = await started(reader, stream)
    await redis.delete(STREAM)
    for _ in range(500):  # until the consumer has found its group gone and made it again
        if await redis.eval("return redis.call('EXISTS', KEYS[1])", 1, STREAM):
            break
        await asyncio.sleep(0.01)
    await publisher.publish(event(1))
    assert await asyncio.wait_for(first, timeout=5) == event(1)
    await stream.aclose()


async def test_the_stream_keeps_about_max_length_events(redis: Redis) -> None:
    publisher = RedisEventStream(redis, max_length=10)
    for sequence in range(500):
        await publisher.publish(event(sequence))
    # Redis trims in whole blocks of (by default) 100 entries.
    assert await redis.xlen(STREAM) <= 10 + 100


async def test_answers_in_either_protocol_version_are_read(
    redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    fields = {b"shard": b"0", b"name": b"READY", b"sequence": b"7", b"data": b"{}"}
    answers: list[object] = [{STREAM.encode(): [[(b"2-0", fields)]]}]  # RESP3 maps each stream to its entries

    async def mapped(*_: object, **__: object) -> object:
        return answers.pop(0) if answers else {}

    monkeypatch.setattr(redis, "xread", mapped)
    stream = consumer(redis).events()
    assert await take(stream, 1) == [DispatchEvent(0, "READY", 7, msgspec.Raw(b"{}"))]
    await stream.aclose()


async def test_a_read_redis_refuses_for_good_ends_the_iteration(redis: Redis) -> None:
    await redis.set(STREAM, b"not a stream")
    stream = consumer(redis).events()
    with pytest.raises(ResponseError, match="WRONGTYPE"):
        await asyncio.wait_for(anext(stream), timeout=5)
