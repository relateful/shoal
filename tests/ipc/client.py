import asyncio
import random

import pytest

from shoal.ipc.client import EventClient
from shoal.ipc.protocol import IPCError
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
