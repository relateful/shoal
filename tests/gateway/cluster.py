import asyncio
import contextlib

import msgspec
import pytest

from shoal.core.codec import PayloadDecodeError
from shoal.core.snowflake import Snowflake
from shoal.gateway.cluster import GatewayCommand, MemoryCommandRouter, MemoryShardDirectory, ShardStatus
from shoal.gateway.shard import ShardState
from shoal.payloads import GatewayOpcode
from shoal.payloads.gateway_events import RequestSoundboardSounds
from tests.support.fakes import FakeClock


def status(shard_id: int, shard_count: int, reported_at: float) -> ShardStatus:
    return ShardStatus(
        shard_id=shard_id,
        shard_count=shard_count,
        cluster="a",
        state=ShardState.READY,
        latency=0.05,
        reported_at=reported_at,
    )


def command(shard_id: int, data: bytes = b'{"guild_ids":["1"]}') -> GatewayCommand:
    return GatewayCommand(
        shard_id=shard_id,
        shard_count=2,
        opcode=GatewayOpcode.REQUEST_SOUNDBOARD_SOUNDS,
        data=msgspec.Raw(data),
    )


async def test_the_directory_keeps_each_count_apart_and_forgets_silent_clusters() -> None:
    clock = FakeClock()
    directory = MemoryShardDirectory(ttl=15, clock=clock)
    await directory.report(
        [status(0, 2, clock.wall()), status(1, 2, clock.wall() - 20), status(0, 4, clock.wall())]
    )
    assert list(await directory.statuses(2)) == [0]
    assert list(await directory.statuses(4)) == [0]
    clock.advance(16)
    assert await directory.statuses(4) == {}


def test_a_routed_command_decodes_into_its_payload() -> None:
    assert command(0).payload() == RequestSoundboardSounds(guild_ids=[Snowflake(1)])
    with pytest.raises(PayloadDecodeError):
        command(0, b"{}").payload()
    heartbeat = GatewayCommand(
        shard_id=0, shard_count=1, opcode=GatewayOpcode.HEARTBEAT, data=msgspec.Raw(b"1")
    )
    with pytest.raises(ValueError, match="not a gateway command"):
        heartbeat.payload()


async def test_the_router_delivers_to_the_receiver_of_each_shard_and_drops_the_oldest() -> None:
    router = MemoryCommandRouter(queue_size=2)
    assert not await router.send(command(0))
    async with contextlib.aclosing(router.receive(2, [0, 1])) as received:
        first = asyncio.ensure_future(anext(received))
        await asyncio.sleep(0)
        assert await router.send(command(1))
        assert (await first).shard_id == 1
        for shard_id in (0, 1, 0):
            assert await router.send(command(shard_id))
        assert [(await anext(received)).shard_id for _ in range(2)] == [1, 0]
    assert not await router.send(command(0))
