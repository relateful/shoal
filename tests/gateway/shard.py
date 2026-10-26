import asyncio
import logging
import random
from datetime import UTC, datetime
from typing import override

import msgspec
import pytest

from shoal.core.dispatch import DispatchEvent
from shoal.core.metrics import (
    EVENTS_DROPPED,
    GATEWAY_EVENT_DELAY_SECONDS,
    GATEWAY_SHARD_READY,
    InMemoryMetrics,
)
from shoal.core.snowflake import Snowflake
from shoal.gateway.defaults import HELLO_TIMEOUT, RECONNECT_BACKOFF_CAP, RESUMABLE_CLOSE_CODE
from shoal.gateway.session import GatewaySession, MemorySessionStore, SessionStore
from shoal.gateway.shard import GatewayFatalError, Shard, ShardNotConnectedError, ShardState
from shoal.payloads import (
    ChannelInfoField,
    GatewayCapabilities,
    GatewayOpcode,
    Intents,
    RequestChannelInfo,
    RequestGuildMembers,
    RequestSoundboardSounds,
    StatusType,
    TransportCompression,
    UpdatePresence,
)
from tests.support.fakes import (
    FakeConnection,
    FakeConnector,
    ManualClock,
    gateway_message,
    settle,
    zlib_stream_frames,
)

HELLO = gateway_message(10, {"heartbeat_interval": 40_000})
USER: dict[str, object] = {
    "id": "1",
    "username": "bot",
    "discriminator": "0",
    "global_name": None,
    "avatar": None,
}


def ready(session_id: str = "s1", sequence: int = 1) -> bytes:
    data: dict[str, object] = {
        "v": 10,
        "user": USER,
        "guilds": [],
        "session_id": session_id,
        "resume_gateway_url": "wss://resume.example",
        "application": {"id": "3", "flags": 0},
    }
    return gateway_message(0, data, s=sequence, t="READY")


def state_of(shard: Shard) -> ShardState:
    """Read the state through a call, so the type checker does not narrow it across awaits."""
    return shard.state


def sent(connection: FakeConnection) -> list[dict[str, object]]:
    return [msgspec.json.decode(frame, type=dict[str, object]) for frame in connection.sent]


def ops(connection: FakeConnection) -> list[object]:
    return [frame["op"] for frame in sent(connection)]


class Harness:
    def __init__(
        self,
        *connections: FakeConnection | OSError,
        store: SessionStore | None = None,
        compression: TransportCompression | None = None,
        capabilities: GatewayCapabilities | None = None,
    ) -> None:
        self.clock = ManualClock()
        self.connector = FakeConnector(*connections)
        self.store: SessionStore = store or MemorySessionStore()
        self.events: list[DispatchEvent] = []
        self.metrics = InMemoryMetrics()
        self.shard = Shard(
            token="token",
            shard_id=0,
            shard_count=1,
            intents=Intents(guilds=True),
            dispatch=self.dispatch,
            connector=self.connector,
            session_store=self.store,
            gateway_url="wss://gateway.example",
            compression=compression,
            clock=self.clock,
            random_source=random.Random(0),
            metrics=self.metrics,
            capabilities=capabilities,
        )
        self.task: asyncio.Task[None] | None = None
        self.gate: asyncio.Event | None = None
        """When set, `TYPING_START` dispatches wait on it, like a slow handler."""

    async def dispatch(self, event: DispatchEvent) -> None:
        self.events.append(event)
        if self.gate is not None and event.name == "TYPING_START":
            await self.gate.wait()

    async def start(self) -> None:
        self.task = asyncio.create_task(self.shard.run())
        await settle()

    async def stop(self, *, resumable: bool = True) -> None:
        await self.shard.close(resumable=resumable)
        await settle()
        assert self.task is not None
        await asyncio.wait_for(self.task, timeout=1)


async def test_identifies_dispatches_and_saves_the_session_on_close() -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    harness = Harness(connection, capabilities=GatewayCapabilities(channel_obfuscation=True))
    await harness.start()

    identify = sent(connection)[0]
    assert identify["op"] == GatewayOpcode.IDENTIFY
    payload = msgspec.convert(identify["d"], type=dict[str, object])
    assert payload["token"] == "token"
    assert payload["intents"] == 1
    assert payload["shard"] == [0, 1]
    assert payload["capabilities"] == 1 << 15
    assert harness.connector.urls == ["wss://gateway.example/?v=10&encoding=json"]
    assert state_of(harness.shard) is ShardState.READY
    assert [event.name for event in harness.events] == ["READY"]
    assert harness.metrics.gauges[InMemoryMetrics.key(GATEWAY_SHARD_READY, {"shard": "0"})] == 1

    await harness.stop()
    assert connection.close_codes == [RESUMABLE_CLOSE_CODE]
    saved = await harness.store.load(0, 1)
    assert saved is not None
    assert saved.session_id == "s1"
    assert saved.sequence == 1
    assert state_of(harness.shard) is ShardState.CLOSED


async def test_closing_for_good_ends_the_session() -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    harness = Harness(connection)
    await harness.start()
    await harness.stop(resumable=False)
    assert connection.close_codes == [1000]
    assert await harness.store.load(0, 1) is None


async def test_resumes_a_saved_session_after_a_restart() -> None:
    store = MemorySessionStore()
    await store.save(
        GatewaySession(
            shard_id=0,
            shard_count=1,
            session_id="old",
            sequence=99,
            resume_gateway_url="wss://gateway-us-east1-b.discord.gg",
            saved_at=1_750_000_000.0,
        )
    )
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(gateway_message(0, None, s=100, t="RESUMED"))
    harness = Harness(connection, store=store)
    await harness.start()
    assert harness.connector.urls == ["wss://gateway-us-east1-b.discord.gg/?v=10&encoding=json"]
    resume = sent(connection)[0]
    assert resume["op"] == GatewayOpcode.RESUME
    assert resume["d"] == {"token": "token", "session_id": "old", "seq": 99}
    assert state_of(harness.shard) is ShardState.READY
    await harness.stop()


def saved_session(
    resume_gateway_url: str = "wss://gateway-us-east1-b.discord.gg", *, age: float = 0.0
) -> GatewaySession:
    return GatewaySession(
        shard_id=0,
        shard_count=1,
        session_id="old",
        sequence=5,
        resume_gateway_url=resume_gateway_url,
        saved_at=1_750_000_000.0 - age,
    )


async def test_failed_resume_url_falls_back_to_the_main_gateway_and_keeps_the_session() -> None:
    store = MemorySessionStore()
    await store.save(saved_session("wss://gateway-dead.discord.gg"))
    main = FakeConnection()
    main.push(HELLO)
    main.push_close(None)
    again = FakeConnection()
    again.push(HELLO)
    again.push(gateway_message(0, None, s=6, t="RESUMED"))
    harness = Harness(ConnectionError("503 Service Unavailable"), main, again, store=store)
    await harness.start()
    await harness.clock.advance(5)
    await harness.clock.advance(5)
    assert harness.connector.urls[0].startswith("wss://gateway-dead.discord.gg/")
    assert harness.connector.urls[1].startswith("wss://gateway.example/")
    assert harness.connector.urls[2].startswith("wss://gateway.example/")
    assert ops(main) == [GatewayOpcode.RESUME]
    assert ops(again) == [GatewayOpcode.RESUME]
    assert state_of(harness.shard) is ShardState.READY
    await harness.stop()


async def test_a_session_older_than_the_resume_window_is_not_resumed() -> None:
    store = MemorySessionStore()
    await store.save(saved_session(age=200))
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready("new"))
    harness = Harness(connection, store=store)
    await harness.start()
    assert harness.connector.urls[0].startswith("wss://gateway.example/")
    assert ops(connection)[0] == GatewayOpcode.IDENTIFY
    await harness.stop()


@pytest.mark.parametrize(
    "url",
    [
        "ws://somewhere.example",
        "wss://evil.example",
        "wss://gateway.discord.gg.evil.example",
        "wss://notdiscord.gg",
    ],
)
async def test_a_saved_resume_url_off_discords_hosts_is_never_used(url: str) -> None:
    store = MemorySessionStore()
    await store.save(saved_session(url))
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready("new"))
    harness = Harness(connection, store=store)
    await harness.start()
    assert harness.connector.urls[0].startswith("wss://gateway.example/")
    assert ops(connection)[0] == GatewayOpcode.IDENTIFY
    await harness.stop()


async def test_invalid_session_identifies_on_the_main_gateway() -> None:
    first = FakeConnection()
    first.push(HELLO)
    first.push(ready())
    first.push(gateway_message(9, d=False))
    second = FakeConnection()
    second.push(HELLO)
    second.push(ready("s2"))
    harness = Harness(first, second)
    await harness.start()
    await harness.clock.advance(5)
    await harness.clock.advance(5)
    assert first.close_codes == [RESUMABLE_CLOSE_CODE]
    assert harness.connector.urls[1].startswith("wss://gateway.example/")
    assert ops(second)[0] == GatewayOpcode.IDENTIFY
    await harness.stop()


async def test_reconnect_request_resumes_on_the_resume_url() -> None:
    first = FakeConnection()
    first.push(HELLO)
    first.push(ready())
    first.push(gateway_message(7))
    second = FakeConnection()
    second.push(HELLO)
    second.push(gateway_message(0, None, s=2, t="RESUMED"))
    harness = Harness(first, second)
    await harness.start()
    assert first.close_codes == [RESUMABLE_CLOSE_CODE]
    assert harness.connector.urls[1].startswith("wss://resume.example/")
    assert ops(second) == [GatewayOpcode.RESUME]
    await harness.stop()


async def test_fatal_close_codes_raise() -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push_close(4004)
    harness = Harness(connection)
    with pytest.raises(GatewayFatalError) as caught:
        await asyncio.wait_for(harness.shard.run(), timeout=1)
    assert caught.value.code == 4004


async def test_a_failing_heartbeat_reconnects_instead_of_going_quiet(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class BrokenHeartbeats(FakeConnection):
        @override
        async def send(self, data: bytes) -> None:
            if data.startswith(b'{"op":1,'):
                msg = "socket gone"
                raise OSError(msg)
            await super().send(data)

    first = BrokenHeartbeats()
    first.push(HELLO)
    first.push(ready(sequence=7))
    second = FakeConnection()
    harness = Harness(first, second)
    with caplog.at_level(logging.WARNING, logger="shoal.gateway"):
        await harness.start()
        await harness.clock.advance(40)
    assert "heartbeat failed; reconnecting" in caplog.text
    assert first.close_codes == [RESUMABLE_CLOSE_CODE]
    assert harness.shard.latency is None
    await harness.stop()


async def test_heartbeats_carry_the_sequence_and_zombies_reconnect() -> None:
    first = FakeConnection()
    first.push(HELLO)
    first.push(ready(sequence=7))
    second = FakeConnection()
    harness = Harness(first, second)
    await harness.start()
    await harness.clock.advance(40)
    assert sent(first)[-1] == {"op": 1, "d": 7}
    first.push(gateway_message(11))
    await settle()
    assert harness.shard.latency == 0
    await harness.clock.advance(40)
    await harness.clock.advance(40)
    assert first.close_codes == [RESUMABLE_CLOSE_CODE]
    assert harness.connector.urls[1].startswith("wss://resume.example/")
    await harness.stop()


async def test_server_requested_heartbeat_is_answered_immediately() -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready(sequence=3))
    connection.push(gateway_message(1))
    harness = Harness(connection)
    await harness.start()
    assert sent(connection)[-1] == {"op": 1, "d": 3}
    await harness.clock.advance(40)
    assert connection.close_codes == []
    await harness.stop()


async def test_a_busy_receive_loop_is_not_mistaken_for_a_dead_connection() -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    connection.push(gateway_message(0, {}, s=2, t="TYPING_START"))
    harness = Harness(connection)
    harness.gate = asyncio.Event()
    await harness.start()
    connection.push(gateway_message(11))
    for _ in range(3):
        await harness.clock.advance(40)
    assert connection.close_codes == []
    harness.gate.set()
    await settle()
    assert state_of(harness.shard) is ShardState.READY
    await harness.stop()


async def test_a_broken_connection_reconnects_instead_of_ending_the_shard() -> None:
    first = FakeConnection()
    first.push_binary(b"not a zlib stream" + b"\x00\x00\xff\xff")
    second = FakeConnection()
    for frame in zlib_stream_frames(HELLO, ready()):
        second.push_binary(frame)
    harness = Harness(first, second, compression=TransportCompression.ZLIB_STREAM)
    await harness.start()
    await harness.clock.advance(5)
    assert first.close_codes == [RESUMABLE_CLOSE_CODE]
    assert state_of(harness.shard) is ShardState.READY
    await harness.stop()


async def test_a_failing_session_store_does_not_end_the_shard(caplog: pytest.LogCaptureFixture) -> None:
    class BrokenStore(SessionStore):
        @override
        async def load(self, shard_id: int, shard_count: int) -> GatewaySession | None:
            return None

        @override
        async def save(self, session: GatewaySession) -> None:
            msg = "disk full"
            raise OSError(msg)

        @override
        async def delete(self, shard_id: int) -> None:
            pass

    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    harness = Harness(connection, store=BrokenStore())
    with caplog.at_level(logging.ERROR, logger="shoal.gateway"):
        await harness.start()
    assert state_of(harness.shard) is ShardState.READY
    assert "could not save the session" in caplog.text
    await harness.shard.close(resumable=False)
    assert harness.task is not None
    await asyncio.wait_for(harness.task, timeout=1)


async def test_no_hello_reconnects() -> None:
    silent = FakeConnection()
    second = FakeConnection()
    second.push(HELLO)
    second.push(ready())
    harness = Harness(silent, second)
    await harness.start()
    await harness.clock.advance(HELLO_TIMEOUT)
    await harness.clock.advance(5)
    assert silent.close_codes == [RESUMABLE_CLOSE_CODE]
    assert state_of(harness.shard) is ShardState.READY
    await harness.stop()


async def test_close_interrupts_the_reconnect_backoff() -> None:
    harness = Harness(ConnectionError("down"))
    await harness.start()
    await harness.shard.close()
    assert harness.task is not None
    await asyncio.wait_for(harness.task, timeout=1)
    assert state_of(harness.shard) is ShardState.CLOSED


async def test_events_after_close_are_not_dispatched_or_counted() -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready(sequence=1))
    harness = Harness(connection)
    await harness.start()
    connection.push(gateway_message(0, {}, s=2, t="TYPING_START"))
    await harness.shard.close()
    assert harness.task is not None
    await asyncio.wait_for(harness.task, timeout=1)
    saved = await harness.store.load(0, 1)
    assert saved is not None
    assert saved.sequence == 1
    assert [event.name for event in harness.events] == ["READY"]


async def test_compressed_frames_are_inflated() -> None:
    connection = FakeConnection()
    for frame in zlib_stream_frames(HELLO, ready()):
        connection.push_binary(frame)
    harness = Harness(connection, compression=TransportCompression.ZLIB_STREAM)
    await harness.start()
    assert harness.connector.urls[0].endswith("compress=zlib-stream")
    assert state_of(harness.shard) is ShardState.READY
    await harness.stop()


async def test_late_messages_are_measured_and_warned_about(caplog: pytest.LogCaptureFixture) -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    harness = Harness(connection)
    created = datetime.fromtimestamp(harness.clock.wall() - 15, tz=UTC)
    message_id = Snowflake.from_datetime(created)
    connection.push(gateway_message(0, {"id": str(message_id)}, s=2, t="MESSAGE_CREATE"))
    with caplog.at_level(logging.WARNING, logger="shoal.gateway"):
        await harness.start()
    key = InMemoryMetrics.key(GATEWAY_EVENT_DELAY_SECONDS, {"shard": "0", "event": "MESSAGE_CREATE"})
    assert harness.metrics.observations[key][0] == pytest.approx(15, abs=0.01)
    assert "arrived 15.0s after it was created" in caplog.text
    await harness.stop()


async def test_events_replayed_by_a_resume_are_not_counted_as_late() -> None:
    store = MemorySessionStore()
    await store.save(saved_session())
    connection = FakeConnection()
    connection.push(HELLO)
    harness = Harness(connection, store=store)
    created = datetime.fromtimestamp(harness.clock.wall() - 120, tz=UTC)
    replayed = Snowflake.from_datetime(created)
    connection.push(gateway_message(0, {"id": str(replayed)}, s=6, t="MESSAGE_CREATE"))
    connection.push(gateway_message(0, None, s=7, t="RESUMED"))
    await harness.start()
    assert state_of(harness.shard) is ShardState.READY
    assert [event.name for event in harness.events] == ["MESSAGE_CREATE", "RESUMED"]
    assert harness.metrics.observations == {}
    await harness.stop()


async def test_dispatch_handler_errors_do_not_stop_the_shard(caplog: pytest.LogCaptureFixture) -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    connection.push(gateway_message(0, {}, s=2, t="TYPING_START"))
    harness = Harness(connection)

    async def explode(event: DispatchEvent) -> None:
        raise RuntimeError(event.name)

    harness.shard = Shard(
        token="token",
        shard_id=0,
        shard_count=1,
        intents=Intents.none(),
        dispatch=explode,
        connector=harness.connector,
        clock=harness.clock,
        compression=None,
    )
    with caplog.at_level(logging.ERROR, logger="shoal.gateway"):
        await harness.start()
    assert state_of(harness.shard) is ShardState.READY
    assert "dispatch handler failed for TYPING_START" in caplog.text
    await harness.stop()


async def test_commands_require_a_ready_connection() -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    harness = Harness(connection)
    presence = UpdatePresence(since=None, activities=[], status=StatusType.ONLINE, afk=False)
    with pytest.raises(ShardNotConnectedError):
        await harness.shard.update_presence(presence)
    await harness.start()
    with pytest.raises(ValueError, match="managed by the shard"):
        await harness.shard.send_command(GatewayOpcode.IDENTIFY, presence)
    await harness.shard.request_guild_members(RequestGuildMembers(guild_id=Snowflake(1), limit=0, query=""))
    assert ops(connection)[-1] == GatewayOpcode.REQUEST_GUILD_MEMBERS
    await harness.stop()


async def test_close_during_connect_stops_cleanly() -> None:
    connection = FakeConnection()
    harness = Harness(connection)
    await harness.shard.close()
    await asyncio.wait_for(harness.shard.run(), timeout=1)
    assert connection.close_codes == []
    assert harness.connector.urls == []
    assert state_of(harness.shard) is ShardState.CLOSED


def test_validates_shard_layout_and_threshold() -> None:
    async def noop(event: DispatchEvent) -> None:
        del event

    with pytest.raises(ValueError, match="outside"):
        Shard(token="t", shard_id=2, shard_count=2, intents=Intents.none(), dispatch=noop)
    with pytest.raises(ValueError, match="large_threshold"):
        Shard(token="t", shard_id=0, shard_count=1, intents=Intents.none(), dispatch=noop, large_threshold=10)


async def test_a_session_ended_for_good_is_never_saved_again() -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    harness = Harness(connection)
    await harness.start()
    await harness.stop(resumable=False)
    await harness.shard.close()
    assert await harness.store.load(0, 1) is None


@pytest.mark.parametrize(
    ("code", "next_op"),
    [(4000, GatewayOpcode.RESUME), (4009, GatewayOpcode.IDENTIFY), (1001, GatewayOpcode.RESUME)],
)
async def test_close_codes_decide_between_resume_and_identify(code: int, next_op: GatewayOpcode) -> None:
    first = FakeConnection()
    first.push(HELLO)
    first.push(ready())
    first.push_close(code)
    second = FakeConnection()
    second.push(HELLO)
    harness = Harness(first, second)
    await harness.start()
    for _ in range(3):
        await harness.clock.advance(5)
    assert ops(second)[0] == next_op
    await harness.stop()


async def test_a_resumable_invalid_session_resumes_without_waiting() -> None:
    first = FakeConnection()
    first.push(HELLO)
    first.push(ready())
    first.push(gateway_message(9, d=True))
    second = FakeConnection()
    second.push(HELLO)
    harness = Harness(first, second)
    await harness.start()
    assert ops(second) == [GatewayOpcode.RESUME]
    await harness.stop()


async def test_a_first_payload_that_is_not_hello_reconnects() -> None:
    first = FakeConnection()
    first.push(gateway_message(11))
    second = FakeConnection()
    second.push(HELLO)
    second.push(ready())
    harness = Harness(first, second)
    await harness.start()
    await harness.clock.advance(5)
    assert first.close_codes == [RESUMABLE_CLOSE_CODE]
    assert state_of(harness.shard) is ShardState.READY
    await harness.stop()


async def test_an_undecodable_payload_is_dropped(caplog: pytest.LogCaptureFixture) -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(b"{not json")
    connection.push(ready())
    harness = Harness(connection)
    with caplog.at_level(logging.ERROR, logger="shoal.gateway"):
        await harness.start()
    assert "undecodable gateway payload dropped" in caplog.text
    key = InMemoryMetrics.key(EVENTS_DROPPED, {"stage": "gateway", "event": "unknown"})
    assert harness.metrics.counters[key] == 1
    assert state_of(harness.shard) is ShardState.READY
    await harness.stop()


async def test_ending_a_session_wins_over_a_save_still_in_flight() -> None:
    class SlowStore(SessionStore):
        def __init__(self) -> None:
            self.inner = MemorySessionStore()
            self.gate = asyncio.Event()

        @override
        async def load(self, shard_id: int, shard_count: int) -> GatewaySession | None:
            return await self.inner.load(shard_id, shard_count)

        @override
        async def save(self, session: GatewaySession) -> None:
            await self.gate.wait()
            await self.inner.save(session)

        @override
        async def delete(self, shard_id: int) -> None:
            await self.inner.delete(shard_id)

    store = SlowStore()
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    harness = Harness(connection, store=store)
    await harness.start()
    closing = asyncio.create_task(harness.shard.close(resumable=False))
    await settle()
    store.gate.set()
    await asyncio.wait_for(closing, timeout=1)
    assert harness.task is not None
    await asyncio.wait_for(harness.task, timeout=1)
    assert await store.inner.load(0, 1) is None


async def test_soundboard_and_channel_info_requests_use_their_opcodes() -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    harness = Harness(connection)
    await harness.start()
    await harness.shard.request_soundboard_sounds(RequestSoundboardSounds(guild_ids=[Snowflake(2)]))
    assert sent(connection)[-1] == {"op": 31, "d": {"guild_ids": ["2"]}}
    await harness.shard.request_channel_info(
        RequestChannelInfo(guild_id=Snowflake(2), fields=[ChannelInfoField.STATUS])
    )
    assert sent(connection)[-1] == {"op": 43, "d": {"guild_id": "2", "fields": ["status"]}}
    await harness.stop()


async def test_a_rate_limited_command_is_logged_and_still_dispatched(
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    limited = {"opcode": 8, "retry_after": 27.5, "meta": {"guild_id": "2"}}
    connection.push(gateway_message(0, limited, s=2, t="RATE_LIMITED"))
    harness = Harness(connection)
    with caplog.at_level(logging.WARNING, logger="shoal.gateway"):
        await harness.start()
        await settle()
    assert "rate limited REQUEST_GUILD_MEMBERS; retry after 27.5s" in caplog.text
    assert [event.name for event in harness.events][-1] == "RATE_LIMITED"
    await harness.stop()


async def test_invalid_sessions_in_a_row_back_off() -> None:
    first = FakeConnection()
    first.push(HELLO)
    first.push(gateway_message(9, d=False))
    second = FakeConnection()
    second.push(HELLO)
    second.push(gateway_message(9, d=False))
    third = FakeConnection()
    third.push(HELLO)
    third.push(ready("s3"))
    harness = Harness(first, second, third)
    await harness.start()
    await harness.clock.advance(5)
    assert len(harness.connector.urls) == 2
    await harness.clock.advance(5)
    assert len(harness.connector.urls) == 2  # the second in a row also backs off
    await harness.clock.advance(60)
    assert len(harness.connector.urls) == 3
    assert state_of(harness.shard) is ShardState.READY
    await harness.stop()


async def test_a_close_code_ending_the_session_backs_off_when_it_repeats() -> None:
    connections: list[FakeConnection] = []
    for index in range(3):
        connection = FakeConnection()
        connection.push(HELLO)
        connection.push(ready(f"s{index}"))
        connection.push_close(4009)
        connections.append(connection)
    harness = Harness(*connections)
    await harness.start()
    await settle()
    # Closed right after READY: not a stable connection, so the shard waits before identifying again.
    assert len(harness.connector.urls) == 1
    await harness.clock.advance(60)
    assert len(harness.connector.urls) >= 2
    await harness.stop()


async def test_a_slow_store_gets_one_save_at_a_time_however_many_beats_arrive() -> None:
    class SlowStore(SessionStore):
        def __init__(self) -> None:
            self.release = asyncio.Event()
            self.saves = 0

        @override
        async def load(self, shard_id: int, shard_count: int) -> GatewaySession | None:
            return None

        @override
        async def save(self, session: GatewaySession) -> None:
            self.saves += 1
            if self.saves > 1:
                await self.release.wait()

        @override
        async def delete(self, shard_id: int) -> None:
            pass

    store = SlowStore()
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    harness = Harness(connection, store=store)
    await harness.start()
    for _ in range(3):
        connection.push(gateway_message(11))
    await settle()
    # READY saved once; the first acknowledgement's save is still running, so the others wait.
    assert store.saves == 2
    store.release.set()
    await settle()
    connection.push(gateway_message(11))
    await settle()
    assert store.saves == 3
    await harness.stop()


async def test_each_heartbeat_acknowledgement_saves_the_session() -> None:
    connection = FakeConnection()
    connection.push(HELLO)
    connection.push(ready())
    harness = Harness(connection)
    await harness.start()
    connection.push(
        gateway_message(0, {"channel_id": "1", "user_id": "2", "timestamp": 1}, s=7, t="TYPING_START")
    )
    connection.push(gateway_message(11))
    await settle()
    saved = await harness.store.load(0, 1)
    assert saved is not None
    assert saved.sequence == 7
    await harness.stop()


async def test_a_resume_closed_early_falls_back_to_the_main_gateway() -> None:
    store = MemorySessionStore()
    await store.save(saved_session())
    dropped = FakeConnection()
    dropped.push(HELLO)
    dropped.push_close(1006)
    again = FakeConnection()
    again.push(HELLO)
    again.push(gateway_message(0, None, s=6, t="RESUMED"))
    harness = Harness(dropped, again, store=store)
    await harness.start()
    await harness.clock.advance(5)
    await harness.clock.advance(5)
    assert harness.connector.urls[0].startswith("wss://gateway-us-east1-b.discord.gg/")
    assert harness.connector.urls[1].startswith("wss://gateway.example/")
    assert ops(again) == [GatewayOpcode.RESUME]
    await harness.stop()


async def test_a_connection_that_keeps_dropping_backs_off() -> None:
    first = FakeConnection()
    first.push(HELLO)
    first.push(ready())
    first.push_close(4000)
    second = FakeConnection()
    second.push(HELLO)
    second.push(gateway_message(0, None, s=2, t="RESUMED"))
    harness = Harness(first, second)
    await harness.start()
    assert len(harness.connector.urls) == 1  # dropped right after READY: not reconnected at once
    await harness.clock.advance(RECONNECT_BACKOFF_CAP)
    assert len(harness.connector.urls) == 2
    await harness.stop()
