import asyncio
from typing import override

import msgspec
import pytest

from shoal.core.dispatch import DispatchEvent
from shoal.gateway.connection import GatewayConnection, GatewayConnector
from shoal.gateway.manager import ShardManager, cluster_shard_ids
from shoal.gateway.session import MemorySessionStore
from shoal.gateway.shard import GatewayFatalError, ShardState
from shoal.payloads import Intents
from tests.support.fakes import FakeConnection, FakeConnector, ManualClock, gateway_message, settle

HELLO = gateway_message(10, {"heartbeat_interval": 40_000})


def ready(shard_id: int, shard_count: int) -> bytes:
    user = {"id": "1", "username": "bot", "discriminator": "0", "global_name": None, "avatar": None}
    data: dict[str, object] = {
        "v": 10,
        "user": user,
        "guilds": [],
        "session_id": f"s{shard_id}",
        "resume_gateway_url": "wss://resume.example",
        "shard": [shard_id, shard_count],
        "application": {"id": "3", "flags": 0},
    }
    return gateway_message(0, data, s=1, t="READY")


def connection_for(shard_id: int, shard_count: int) -> FakeConnection:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready(shard_id, shard_count))
    return connection


@pytest.mark.parametrize(("clusters", "shards"), [(1, 1), (3, 10), (4, 16), (7, 100)])
def test_cluster_split_covers_every_shard_exactly_once(clusters: int, shards: int) -> None:
    owned = [list(cluster_shard_ids(cluster, clusters, shards)) for cluster in range(clusters)]
    assert [shard for block in owned for shard in block] == list(range(shards))
    sizes = {len(block) for block in owned}
    assert max(sizes) - min(sizes) <= 1


def test_cluster_split_validates() -> None:
    with pytest.raises(ValueError, match="cluster_id"):
        cluster_shard_ids(3, 3, 9)
    with pytest.raises(ValueError, match="at least one"):
        cluster_shard_ids(0, 5, 4)


async def test_runs_its_shards_until_closed() -> None:
    events: list[DispatchEvent] = []

    async def dispatch(event: DispatchEvent) -> None:
        events.append(event)

    clock = ManualClock()
    connector = FakeConnector(connection_for(2, 4), connection_for(3, 4))
    manager = ShardManager(
        token="t",
        intents=Intents.none(),
        dispatch=dispatch,
        shard_count=4,
        shard_ids=cluster_shard_ids(1, 2, 4),
        connector=connector,
        compression=None,
        clock=clock,
    )
    assert sorted(manager.shards) == [2, 3]
    assert manager.shard_count == 4
    task = asyncio.create_task(manager.run())
    await settle()
    assert [event.shard_id for event in events] == [2]
    await clock.advance(5)
    assert sorted(event.shard_id for event in events) == [2, 3]
    assert all(shard.state is ShardState.READY for shard in manager.shards.values())
    guild_on_shard_two = 2 << 22
    assert manager.shard_for_guild(guild_on_shard_two) is manager.shards[2]
    assert manager.shard_for_guild(0) is None
    await manager.close()
    await asyncio.wait_for(task, timeout=2)
    assert not connector.closed


async def test_a_fatal_close_stops_every_shard() -> None:
    async def dispatch(event: DispatchEvent) -> None:
        del event

    bad = FakeConnection()
    bad.push(HELLO)
    bad.push_close(4014)
    clock = ManualClock()
    connector = FakeConnector(connection_for(0, 2), bad)
    manager = ShardManager(
        token="t",
        intents=Intents.all(),
        dispatch=dispatch,
        shard_count=2,
        connector=connector,
        compression=None,
        clock=clock,
    )
    task = asyncio.create_task(manager.run())
    await settle()
    await clock.advance(5)
    with pytest.raises(GatewayFatalError):
        await asyncio.wait_for(task, timeout=2)
    await settle()
    assert all(shard.state is ShardState.CLOSED for shard in manager.shards.values())


async def test_a_crashing_shard_closes_the_others_resumably() -> None:
    async def dispatch(event: DispatchEvent) -> None:
        del event

    class BrokenConnector(GatewayConnector):
        @override
        async def connect(self, url: str) -> GatewayConnection:
            msg = "a bug, not a network error"
            raise RuntimeError(msg)

        @override
        async def close(self) -> None:
            pass

    manager = ShardManager(
        token="t",
        intents=Intents.none(),
        dispatch=dispatch,
        shard_count=2,
        connector=BrokenConnector(),
        compression=None,
        clock=ManualClock(),
    )
    with pytest.raises(RuntimeError, match="a bug"):
        await asyncio.wait_for(manager.run(), timeout=2)
    assert all(shard.state is ShardState.CLOSED for shard in manager.shards.values())


def test_rejects_empty_or_duplicate_shard_ids() -> None:
    async def dispatch(event: DispatchEvent) -> None:
        del event

    with pytest.raises(ValueError, match="at least one"):
        ShardManager(token="t", intents=Intents.none(), dispatch=dispatch, shard_count=2, shard_ids=[])
    with pytest.raises(ValueError, match="duplicates"):
        ShardManager(token="t", intents=Intents.none(), dispatch=dispatch, shard_count=2, shard_ids=[1, 1])


async def test_soundboard_requests_go_to_each_guilds_shard() -> None:
    async def dispatch(event: DispatchEvent) -> None:
        del event

    clock = ManualClock()
    two, three = connection_for(2, 4), connection_for(3, 4)
    manager = ShardManager(
        token="t",
        intents=Intents.none(),
        dispatch=dispatch,
        shard_count=4,
        shard_ids=[2, 3],
        connector=FakeConnector(two, three),
        compression=None,
        clock=clock,
    )
    task = asyncio.create_task(manager.run())
    await settle()
    await clock.advance(5)
    on_two, on_three, also_on_two = 2 << 22, 3 << 22, (6 << 22) | 2 << 22
    await manager.request_soundboard_sounds([on_two, on_three, also_on_two])
    assert msgspec.json.decode(two.sent[-1]) == {
        "op": 31,
        "d": {"guild_ids": [str(on_two), str(also_on_two)]},
    }
    assert msgspec.json.decode(three.sent[-1]) == {"op": 31, "d": {"guild_ids": [str(on_three)]}}
    with pytest.raises(ValueError, match="does not run"):
        await manager.request_soundboard_sounds([0])
    await manager.close()
    await asyncio.wait_for(task, timeout=2)


async def test_a_cancelled_manager_saves_every_session() -> None:
    async def dispatch(event: DispatchEvent) -> None:
        del event

    clock = ManualClock()
    store = MemorySessionStore()
    manager = ShardManager(
        token="t",
        intents=Intents.none(),
        dispatch=dispatch,
        shard_count=1,
        connector=FakeConnector(connection_for(0, 1)),
        compression=None,
        clock=clock,
        session_store=store,
    )
    task = asyncio.create_task(manager.run())
    await settle()
    await store.delete(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    saved = await store.load(0, 1)
    assert saved is not None
    assert saved.session_id == "s0"
