import asyncio
import struct

import pytest

from shoal.core.metrics import IPC_DISCONNECTS, IPC_SUBSCRIBERS, InMemoryMetrics
from shoal.ipc.protocol import Subscribe, encode_frame
from shoal.ipc.server import EventServer
from tests.ipc.conftest import TOKEN, client, event, wait_for_subscribers


async def test_events_flow_from_publisher_to_client(server: EventServer) -> None:
    receiver = client(server)
    stream = receiver.events()
    first = asyncio.ensure_future(anext(stream))
    await wait_for_subscribers(server, 1)
    await server.publish(event(0, "READY"))
    assert await asyncio.wait_for(first, timeout=5) == event(0, "READY")
    await receiver.close()
    await stream.aclose()


async def test_subscribers_only_get_what_they_asked_for(server: EventServer) -> None:
    receiver = client(server, shard_ids=[1], events=["MESSAGE_CREATE"])
    stream = receiver.events()
    first = asyncio.ensure_future(anext(stream))
    await wait_for_subscribers(server, 1)
    await server.publish(event(0, "MESSAGE_CREATE", 1))
    await server.publish(event(1, "TYPING_START", 2))
    await server.publish(event(1, "MESSAGE_CREATE", 3))
    received = await asyncio.wait_for(first, timeout=5)
    assert received.sequence == 3
    await receiver.close()
    await stream.aclose()


async def test_wrong_protocol_version_is_rejected(server: EventServer) -> None:
    host, port = server.address
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(encode_frame(Subscribe(999, TOKEN, "old")))
    await writer.drain()
    answer = await asyncio.wait_for(reader.read(), timeout=5)
    assert b"not supported" in answer
    writer.close()


async def test_slow_subscribers_are_disconnected_not_buffered_forever() -> None:
    metrics = InMemoryMetrics()
    server = EventServer(token=TOKEN, queue_size=2, metrics=metrics)
    await server.start()
    host, port = server.address
    _, writer = await asyncio.open_connection(host, port)
    writer.write(encode_frame(Subscribe(1, TOKEN, "slow")))
    await writer.drain()
    await wait_for_subscribers(server, 1)
    for sequence in range(4):
        await server.publish(event(0, "X", sequence))
    assert server.subscriber_count == 0
    assert metrics.counters[InMemoryMetrics.key(IPC_DISCONNECTS, {"reason": "slow"})] == 1
    assert metrics.gauges[InMemoryMetrics.key(IPC_SUBSCRIBERS)] == 0
    writer.close()
    await asyncio.wait_for(server.close(), timeout=5)


async def test_close_does_not_wait_for_clients_still_authenticating(server: EventServer) -> None:
    host, port = server.address
    _, writer = await asyncio.open_connection(host, port)
    await asyncio.sleep(0.05)
    await asyncio.wait_for(server.close(), timeout=5)
    writer.close()


def test_server_requires_a_token_and_a_start() -> None:
    with pytest.raises(ValueError, match="token"):
        EventServer(token="")
    with pytest.raises(RuntimeError, match="not listening"):
        _ = EventServer(token=TOKEN).address


async def test_an_oversized_hello_is_rejected_before_it_is_read() -> None:
    metrics = InMemoryMetrics()
    server = EventServer(token=TOKEN, metrics=metrics)
    await server.start()
    host, port = server.address
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(struct.pack("!I", 1024 * 1024))
    await writer.drain()
    assert await asyncio.wait_for(reader.read(), timeout=5) == b""
    assert metrics.counters[InMemoryMetrics.key(IPC_DISCONNECTS, {"reason": "rejected"})] == 1
    writer.close()
    await asyncio.wait_for(server.close(), timeout=5)


async def test_data_a_subscriber_sends_after_the_handshake_is_ignored(server: EventServer) -> None:
    host, port = server.address
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(encode_frame(Subscribe(1, TOKEN, "chatty")))
    await writer.drain()
    await wait_for_subscribers(server, 1)
    writer.write(b"unexpected" * 10_000)
    await writer.drain()
    await server.publish(event(0, "READY"))
    received = await asyncio.wait_for(reader.read(4096), timeout=5)
    assert received
    assert server.subscriber_count == 1
    writer.close()
    await wait_for_subscribers(server, 0)
