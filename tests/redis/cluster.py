import asyncio
import contextlib
import logging

import msgspec
import pytest
from redis.asyncio import Redis

from shoal.gateway.cluster import GatewayCommand, ShardStatus
from shoal.gateway.shard import ShardState
from shoal.payloads import GatewayOpcode
from shoal.redis.cluster import RedisCommandRouter, RedisShardDirectory


def status(shard_id: int, shard_count: int = 2) -> ShardStatus:
    return ShardStatus(
        shard_id=shard_id,
        shard_count=shard_count,
        cluster="cluster-0",
        state=ShardState.READY,
        latency=None,
        reported_at=1_750_000_000.0,
    )


def command(shard_id: int) -> GatewayCommand:
    return GatewayCommand(
        shard_id=shard_id,
        shard_count=2,
        opcode=GatewayOpcode.REQUEST_SOUNDBOARD_SOUNDS,
        data=msgspec.Raw(b'{"guild_ids":["1"]}'),
    )


async def test_every_process_reads_what_each_cluster_reported(redis: Redis, other: Redis) -> None:
    await RedisShardDirectory(redis, ttl=30).report([status(0), status(1), status(0, 4)])
    seen = await RedisShardDirectory(other).statuses(2)
    assert seen == {0: status(0), 1: status(1)}
    assert list(await RedisShardDirectory(other).statuses(4)) == [0]
    assert 29_000 < await redis.pttl("shoal:shards:2:0") <= 30_000
    assert await RedisShardDirectory(other, prefix="another-bot").statuses(2) == {}


async def test_an_unreadable_status_is_skipped(redis: Redis, caplog: pytest.LogCaptureFixture) -> None:
    await redis.set("shoal:shards:2:1", b"{not json")
    with caplog.at_level(logging.WARNING, logger="shoal.redis"):
        assert await RedisShardDirectory(redis).statuses(2) == {}
    assert "unreadable status of shard 1" in caplog.text


async def test_a_command_reaches_the_process_listening_for_its_shard(redis: Redis, other: Redis) -> None:
    sender, listener = RedisCommandRouter(redis), RedisCommandRouter(other)
    assert not await sender.send(command(1))  # nobody listens yet
    async with contextlib.aclosing(listener.receive(2, [1])) as received:
        first = asyncio.ensure_future(anext(received))
        for _ in range(100):  # until the subscription is in place
            if await sender.send(command(1)):
                break
            await asyncio.sleep(0.01)
        assert await asyncio.wait_for(first, timeout=5) == command(1)
        assert not await sender.send(command(0))  # nobody listens for shard 0


async def test_a_message_that_is_not_a_command_is_skipped(
    redis: Redis, other: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    listener = RedisCommandRouter(other)
    async with contextlib.aclosing(listener.receive(2, [0])) as received:
        first = asyncio.ensure_future(anext(received))
        with caplog.at_level(logging.WARNING, logger="shoal.redis"):
            for _ in range(100):
                if await redis.eval(
                    "return redis.call('PUBLISH', KEYS[1], ARGV[1])", 1, "shoal:commands:2:0", "{}"
                ):
                    break
                await asyncio.sleep(0.01)
            await RedisCommandRouter(redis).send(command(0))
            assert await asyncio.wait_for(first, timeout=5) == command(0)
    assert "not a gateway command" in caplog.text
