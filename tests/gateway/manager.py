import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator, Collection, Sequence
from typing import override

import msgspec
import pytest

from shoal.core.dispatch import DispatchEvent
from shoal.core.snowflake import Snowflake
from shoal.gateway.cluster import (
    CommandRouter,
    GatewayCommand,
    MemoryCommandRouter,
    MemoryShardDirectory,
    ShardDirectory,
    ShardStatus,
)
from shoal.gateway.connection import GatewayConnection, GatewayConnector
from shoal.gateway.manager import ShardManager, cluster_shard_ids
from shoal.gateway.session import MemorySessionStore
from shoal.gateway.shard import GatewayFatalError, PrivilegedIntentsRequiredError, ShardState
from shoal.payloads import GatewayOpcode, Intents, StatusType
from shoal.payloads.gateway_events import RequestSoundboardSounds, UpdatePresence, UpdateVoiceState
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
    with pytest.raises(GatewayFatalError) as raised:
        await asyncio.wait_for(task, timeout=2)
    # 4014 is the one most bots hit: its own type, and a message saying what to change.
    assert isinstance(raised.value, PrivilegedIntentsRequiredError)
    assert "Developer Portal" in str(raised.value)
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
    await store.delete(0, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    saved = await store.load(0, 1)
    assert saved is not None
    assert saved.session_id == "s0"


def typing(sequence: int) -> bytes:
    return gateway_message(
        0, {"channel_id": "1", "user_id": "2", "timestamp": 1}, s=sequence, t="TYPING_START"
    )


async def test_a_reshard_hands_over_once_every_new_shard_is_ready() -> None:
    events: list[DispatchEvent] = []

    async def dispatch(event: DispatchEvent) -> None:
        events.append(event)

    clock = ManualClock()
    store = MemorySessionStore()
    old = connection_for(0, 1)
    connector = FakeConnector(old)
    manager = ShardManager(
        token="t",
        intents=Intents.none(),
        dispatch=dispatch,
        shard_count=1,
        connector=connector,
        compression=None,
        clock=clock,
        session_store=store,
    )
    with pytest.raises(RuntimeError, match="running"):
        await manager.reshard(2)
    task = asyncio.create_task(manager.run())
    await settle()
    new_zero, new_one = connection_for(0, 2), connection_for(1, 2)
    connector.connections.extend([new_zero, new_one])
    resharding = asyncio.create_task(manager.reshard(2))
    await settle()
    with pytest.raises(RuntimeError, match="in progress"):
        await manager.reshard(3)
    # The old shard still handles every event; the new shards' events are held back.
    old.push(typing(2))
    new_zero.push(typing(2))
    await settle()
    assert [(event.name, event.shard_id) for event in events] == [("READY", 0), ("TYPING_START", 0)]
    reported = {(status.shard_count, status.shard_id) for status in manager.statuses()}
    assert reported == {(1, 0), (2, 0), (2, 1)}
    assert manager.shard_count == 1
    for _ in range(3):
        await clock.advance(5)
    await asyncio.wait_for(resharding, timeout=2)
    assert manager.shard_count == 2
    assert sorted(manager.shards) == [0, 1]
    assert old.close_codes == [1000]  # the old session ends for good
    old.push(typing(3))
    new_one.push(typing(2))
    await settle()
    assert [(event.name, event.shard_id) for event in events[2:]] == [("TYPING_START", 1)]
    # The new shards keep their sessions in the store now that the old ones are gone.
    saved = await store.load(1, 2)
    assert saved is not None
    assert saved.session_id == "s1"
    await manager.close()
    await asyncio.wait_for(task, timeout=2)


async def test_an_abandoned_reshard_leaves_the_old_shards_running() -> None:
    async def dispatch(event: DispatchEvent) -> None:
        del event

    clock = ManualClock()
    connector = FakeConnector(connection_for(0, 1))
    manager = ShardManager(
        token="t",
        intents=Intents.none(),
        dispatch=dispatch,
        shard_count=1,
        connector=connector,
        compression=None,
        clock=clock,
    )
    task = asyncio.create_task(manager.run())
    await settle()
    resharding = asyncio.create_task(manager.reshard(2))  # no connection prepared: never ready
    await settle()
    resharding.cancel()
    with pytest.raises(asyncio.CancelledError):
        await resharding
    assert manager.shard_count == 1
    assert manager.shards[0].state is ShardState.READY
    assert [status.shard_count for status in manager.statuses()] == [1]
    with pytest.raises(ValueError, match="already runs 1 shards"):
        await manager.reshard(1)
    # Closing during a reshard closes its new shards too, and the reshard ends without switching.
    pending = connection_for(0, 2)
    connector.connections.append(pending)
    resharding = asyncio.create_task(manager.reshard(2))
    await settle()
    await manager.close()
    await asyncio.wait_for(task, timeout=2)
    with pytest.raises(RuntimeError, match="closed during the reshard"):
        await asyncio.wait_for(resharding, timeout=2)
    assert manager.shard_count == 1
    assert pending.close_codes == [1000]


async def test_commands_for_another_managers_shard_are_routed_to_it() -> None:
    async def dispatch(event: DispatchEvent) -> None:
        del event

    clock = ManualClock()
    router = MemoryCommandRouter()
    zero, one = connection_for(0, 2), connection_for(1, 2)
    managers = [
        ShardManager(
            token="t",
            intents=Intents.none(),
            dispatch=dispatch,
            shard_count=2,
            shard_ids=[shard_id],
            connector=FakeConnector(connection),
            compression=None,
            clock=clock,
            router=router,
            name=f"cluster-{shard_id}",
        )
        for shard_id, connection in [(0, zero), (1, one)]
    ]
    tasks = [asyncio.create_task(manager.run()) for manager in managers]
    await settle()
    on_one = 1 << 22
    leave = UpdateVoiceState(guild_id=Snowflake(on_one), channel_id=None, self_mute=False, self_deaf=False)
    await managers[0].send_to_guild(on_one, GatewayOpcode.VOICE_STATE_UPDATE, leave)
    await managers[0].request_soundboard_sounds([on_one, 0])
    await settle()
    assert [msgspec.json.decode(sent)["op"] for sent in one.sent[-2:]] == [4, 31]
    assert msgspec.json.decode(zero.sent[-1])["op"] == 31
    idle = UpdatePresence(since=None, activities=[], status=StatusType.IDLE, afk=False)
    with pytest.raises(ValueError, match="managed by the shard"):
        await managers[0].send_command(1, GatewayOpcode.HEARTBEAT, idle)
    await managers[1].close()
    await asyncio.wait_for(tasks[1], timeout=2)
    await settle()
    with pytest.raises(ValueError, match="no other manager"):
        await managers[0].send_to_guild(
            on_one, GatewayOpcode.REQUEST_SOUNDBOARD_SOUNDS, RequestSoundboardSounds(guild_ids=[])
        )
    await managers[0].update_presence(idle)
    assert msgspec.json.decode(zero.sent[-1])["op"] == 3
    await managers[0].close()
    await asyncio.wait_for(tasks[0], timeout=2)


async def test_clusters_report_to_the_directory_and_reshard_together() -> None:
    async def dispatch(event: DispatchEvent) -> None:
        del event

    clock = ManualClock()
    directory = MemoryShardDirectory(clock=clock)
    connectors = [FakeConnector(connection_for(0, 2)), FakeConnector(connection_for(1, 2))]
    managers = [
        ShardManager(
            token="t",
            intents=Intents.none(),
            dispatch=dispatch,
            shard_count=2,
            shard_ids=[shard_id],
            connector=connectors[shard_id],
            compression=None,
            clock=clock,
            directory=directory,
            name=f"cluster-{shard_id}",
        )
        for shard_id in (0, 1)
    ]
    assert managers[1].name == "cluster-1"
    tasks = [asyncio.create_task(manager.run()) for manager in managers]
    await settle()
    await clock.advance(5)
    seen = await directory.statuses(2)
    assert {shard_id: status.cluster for shard_id, status in seen.items()} == {0: "cluster-0", 1: "cluster-1"}
    assert all(status.state is ShardState.READY for status in seen.values())
    # Each cluster takes half of four new shards; neither switches until all four are ready.
    for cluster, connector in enumerate(connectors):
        connector.connections.extend(
            connection_for(shard_id, 4) for shard_id in cluster_shard_ids(cluster, 2, 4)
        )
    first = asyncio.create_task(managers[0].reshard(4, cluster_shard_ids(0, 2, 4)))
    for _ in range(3):
        await clock.advance(5)
    assert not first.done()
    assert managers[0].shard_count == 2
    second = asyncio.create_task(managers[1].reshard(4, cluster_shard_ids(1, 2, 4)))
    for _ in range(4):
        await clock.advance(5)
    await asyncio.wait_for(asyncio.gather(first, second), timeout=2)
    assert [manager.shard_count for manager in managers] == [4, 4]
    await clock.advance(5)
    assert sorted(await directory.statuses(4)) == [0, 1, 2, 3]
    for manager in managers:
        await manager.close()
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)


async def test_a_failing_directory_or_a_bad_routed_command_never_stops_the_shards(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def dispatch(event: DispatchEvent) -> None:
        del event

    class Unreachable(ShardDirectory):
        @override
        async def report(self, statuses: Sequence[ShardStatus]) -> None:
            msg = "the directory is down"
            raise ConnectionError(msg)

        @override
        async def statuses(self, shard_count: int) -> dict[int, ShardStatus]:
            return {}

    clock = ManualClock()
    router = MemoryCommandRouter()
    manager = ShardManager(
        token="t",
        intents=Intents.none(),
        dispatch=dispatch,
        shard_count=2,
        shard_ids=[0],
        connector=FakeConnector(connection_for(0, 2)),
        compression=None,
        clock=clock,
        directory=Unreachable(),
        router=router,
    )
    with caplog.at_level(logging.WARNING, logger="shoal.gateway.manager"):
        task = asyncio.create_task(manager.run())
        await settle()
        broken = GatewayCommand(
            shard_id=0, shard_count=2, opcode=GatewayOpcode.REQUEST_SOUNDBOARD_SOUNDS, data=msgspec.Raw(b"{}")
        )
        assert await router.send(broken)
        await settle()
    assert "could not report the shards" in caplog.text
    assert "could not send a routed REQUEST_SOUNDBOARD_SOUNDS on shard 0" in caplog.text
    assert manager.shards[0].state is ShardState.READY
    await manager.close()
    await asyncio.wait_for(task, timeout=2)


async def test_a_reshard_keeps_up_with_presence_and_finishes_when_its_caller_gives_up() -> None:
    async def dispatch(event: DispatchEvent) -> None:
        del event

    clock = ManualClock()
    store = MemorySessionStore()
    connector = FakeConnector(connection_for(0, 1))
    manager = ShardManager(
        token="t",
        intents=Intents.none(),
        dispatch=dispatch,
        shard_count=1,
        connector=connector,
        compression=None,
        clock=clock,
        session_store=store,
    )
    task = asyncio.create_task(manager.run())
    await settle()
    new_zero, new_one = connection_for(0, 2), connection_for(1, 2)
    connector.connections.extend([new_zero, new_one])
    resharding = asyncio.create_task(manager.reshard(2))
    await clock.advance(5)  # the identify window: new shard 0 identifies, shard 1 waits its turn
    # New shard 0 is ready and takes the presence at once; shard 1 identifies with it later.
    idle = UpdatePresence(since=None, activities=[], status=StatusType.IDLE, afk=False)
    await manager.update_presence(idle)
    assert msgspec.json.decode(new_zero.sent[-1])["op"] == 3
    for _ in range(3):
        await clock.advance(5)
    identify = next(
        msgspec.json.decode(sent) for sent in new_one.sent if msgspec.json.decode(sent)["op"] == 2
    )
    assert identify["d"]["presence"]["status"] == "idle"
    await asyncio.wait_for(resharding, timeout=2)
    assert await store.load(1, 2) is not None
    await manager.close()
    await asyncio.wait_for(task, timeout=2)


async def test_routed_commands_survive_a_failing_router_and_a_command_for_another_shard(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def dispatch(event: DispatchEvent) -> None:
        del event

    class Flaky(CommandRouter):
        def __init__(self) -> None:
            self.inner = MemoryCommandRouter()
            self.attempts = 0

        @override
        async def send(self, command: GatewayCommand) -> bool:
            return await self.inner.send(command)

        @override
        async def receive(
            self, shard_count: int, shard_ids: Collection[int]
        ) -> AsyncGenerator[GatewayCommand]:
            self.attempts += 1
            if self.attempts == 1:
                msg = "the router went away"
                raise ConnectionError(msg)
            # A command whose body names a shard this manager does not run, on this shard's channel.
            yield GatewayCommand(
                shard_id=1,
                shard_count=2,
                opcode=GatewayOpcode.REQUEST_SOUNDBOARD_SOUNDS,
                data=msgspec.Raw(b"{}"),
            )
            async with contextlib.aclosing(self.inner.receive(shard_count, shard_ids)) as commands:
                async for command in commands:
                    yield command

    clock = ManualClock()
    router = Flaky()
    zero = connection_for(0, 2)
    manager = ShardManager(
        token="t",
        intents=Intents.none(),
        dispatch=dispatch,
        shard_count=2,
        shard_ids=[0],
        connector=FakeConnector(zero),
        compression=None,
        clock=clock,
        router=router,
    )
    with caplog.at_level(logging.WARNING, logger="shoal.gateway.manager"):
        task = asyncio.create_task(manager.run())
        await settle()
        assert "receiving routed gateway commands failed" in caplog.text
        await clock.advance(5)
        assert router.attempts == 2
        await settle()
    assert "for shard 1, which is not run here" in caplog.text
    await manager.send_to_guild(
        0, GatewayOpcode.REQUEST_SOUNDBOARD_SOUNDS, RequestSoundboardSounds(guild_ids=[])
    )
    assert msgspec.json.decode(zero.sent[-1])["op"] == 31
    await manager.close()
    await asyncio.wait_for(task, timeout=2)


async def test_a_reshard_waits_out_a_directory_it_cannot_read(caplog: pytest.LogCaptureFixture) -> None:
    async def dispatch(event: DispatchEvent) -> None:
        del event

    class Unreadable(ShardDirectory):
        def __init__(self) -> None:
            self.inner = MemoryShardDirectory()
            self.failures = 1

        @override
        async def report(self, statuses: Sequence[ShardStatus]) -> None:
            await self.inner.report(statuses)

        @override
        async def statuses(self, shard_count: int) -> dict[int, ShardStatus]:
            if self.failures:
                self.failures -= 1
                msg = "the directory is down"
                raise ConnectionError(msg)
            return await self.inner.statuses(shard_count)

    clock = ManualClock()
    connector = FakeConnector(connection_for(0, 1))
    manager = ShardManager(
        token="t",
        intents=Intents.none(),
        dispatch=dispatch,
        shard_count=1,
        connector=connector,
        compression=None,
        clock=clock,
        directory=Unreadable(),
    )
    task = asyncio.create_task(manager.run())
    await settle()
    connector.connections.extend([connection_for(0, 2), connection_for(1, 2)])
    with caplog.at_level(logging.ERROR, logger="shoal.gateway.manager"):
        resharding = asyncio.create_task(manager.reshard(2))
        for _ in range(4):
            await clock.advance(5)
        await asyncio.wait_for(resharding, timeout=2)
    assert "could not read the shard directory" in caplog.text
    assert manager.shard_count == 2
    await manager.close()
    await asyncio.wait_for(task, timeout=2)
