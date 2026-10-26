import asyncio
import random

import pytest

from shoal.core.backoff import backoff_delay
from shoal.ipc.client import EventClient
from shoal.ipc.defaults import CLIENT_RECONNECT_BACKOFF_CAP, CLIENT_STABLE_CONNECTION, MAX_FRAME_SIZE
from shoal.ipc.protocol import PROTOCOL_VERSION, Accepted, EventFrame, IPCError, encode_frame, read_frame
from shoal.ipc.server import EventServer
from tests.ipc.conftest import TOKEN, client, event, wait_for_subscribers
from tests.support.fakes import FakeClock, ManualClock, settle
from tests.support.server import free_port


async def test_wrong_token_is_rejected(server: EventServer) -> None:
    receiver = client(server, token="wrong")
    with pytest.raises(IPCError, match="invalid token"):
        await asyncio.wait_for(anext(receiver.events()), timeout=5)
    assert server.subscriber_count == 0


async def test_client_reconnects_after_the_server_restarts() -> None:
    server = EventServer(token=TOKEN)
    await server.start()
    host, port = server.address
    receiver = EventClient(host, port, token=TOKEN, clock=FakeClock(), random_source=random.Random(0))
    stream = receiver.events()
    first = asyncio.ensure_future(anext(stream))
    await wait_for_subscribers(server, 1)
    await asyncio.wait_for(server.close(), timeout=5)
    restarted = EventServer(token=TOKEN, port=port)
    await restarted.start()
    await wait_for_subscribers(restarted, 1)
    await restarted.publish(event(0, "RESUMED"))
    received = await asyncio.wait_for(first, timeout=5)
    assert received.name == "RESUMED"
    await receiver.close()
    await stream.aclose()
    await asyncio.wait_for(restarted.close(), timeout=5)


async def test_only_a_subscription_that_lasted_resets_the_reconnect_backoff() -> None:
    clock = FakeClock()
    connections = 0
    lasted = asyncio.Event()
    stopping = asyncio.Event()

    async def accept_then_drop(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal connections
        connections += 1
        await read_frame(reader, MAX_FRAME_SIZE)
        writer.write(encode_frame(Accepted(PROTOCOL_VERSION)))
        if connections == 3:
            writer.write(encode_frame(EventFrame.from_event(event(0, "RESUMED"))))
            await lasted.wait()
        if connections == 4:
            stopping.set()
            await reader.read()  # held open until the client closes it
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(accept_then_drop, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    receiver = EventClient("127.0.0.1", port, token=TOKEN, clock=clock, random_source=random.Random(0))
    stream = receiver.events()
    received = await asyncio.wait_for(anext(stream), timeout=5)
    assert received.name == "RESUMED"
    following = asyncio.ensure_future(anext(stream))
    clock.advance(CLIENT_STABLE_CONNECTION)
    lasted.set()
    await asyncio.wait_for(stopping.wait(), timeout=5)
    await receiver.close()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(following, timeout=5)
    server.close()
    await server.wait_closed()
    expected = random.Random(0)
    # Dropped at once twice (the backoff grows), then after a lasting subscription (it starts over).
    assert clock.sleeps == [
        backoff_delay(attempt, cap=CLIENT_RECONNECT_BACKOFF_CAP, random_source=expected)
        for attempt in (1, 2, 1)
    ]


async def test_close_ends_an_iteration_waiting_to_reconnect() -> None:
    receiver = EventClient(
        "127.0.0.1", free_port(), token=TOKEN, clock=ManualClock(), random_source=random.Random(0)
    )
    stream = receiver.events()
    waiting = asyncio.ensure_future(anext(stream))
    for _ in range(100):
        await settle()
        await asyncio.sleep(0.01)
    assert not waiting.done()
    await receiver.close()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(waiting, timeout=5)
