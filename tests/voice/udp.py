import asyncio
import struct
from collections.abc import Callable
from typing import override

import pytest

from shoal.voice.defaults import RECEIVED_PACKETS_QUEUE_SIZE
from shoal.voice.udp import UdpTransportFactory, discover, discovery_request, parse_discovery
from tests.support.fakes import FakeClock, ManualClock, settle
from tests.support.voice import EXTERNAL, SSRC, FakeVoiceTransport


def answer(address: str, port: int) -> bytes:
    return struct.pack(">HHI", 2, 70, SSRC) + address.encode().ljust(64, b"\0") + struct.pack(">H", port)


def test_the_request_and_answer_have_discords_layout() -> None:
    request = discovery_request(SSRC)
    assert len(request) == 74
    assert request[:8] == b"\x00\x01\x00\x46\x00\x00\x00\x07"
    assert parse_discovery(answer("203.0.113.5", 4242)) == ("203.0.113.5", 4242)
    with pytest.raises(ValueError, match="not an IP discovery answer"):
        parse_discovery(request)
    with pytest.raises(ValueError, match="not an IP discovery answer"):
        parse_discovery(b"short")


async def test_discovery_skips_other_packets_and_gives_up_in_time() -> None:
    transport = FakeVoiceTransport()
    transport.incoming.put_nowait(b"\x80\x78early audio")
    assert await discover(transport, SSRC, FakeClock()) == EXTERNAL

    clock = ManualClock()
    waiting = asyncio.ensure_future(discover(FakeVoiceTransport(discovers=False), SSRC, clock))
    await settle()  # until the timeout's sleep is waiting on the clock
    await clock.advance(5)
    with pytest.raises(TimeoutError):
        await waiting


async def test_a_real_socket_carries_packets_both_ways() -> None:
    loop = asyncio.get_running_loop()
    received: asyncio.Queue[tuple[bytes, tuple[str, int]]] = asyncio.Queue()

    class Echo(asyncio.DatagramProtocol):
        def __init__(self) -> None:
            self.transport: asyncio.DatagramTransport | None = None

        @override
        def connection_made(self, transport: asyncio.BaseTransport) -> None:
            assert isinstance(transport, asyncio.DatagramTransport)
            self.transport = transport

        @override
        def datagram_received(self, data: bytes, addr: tuple[object, int]) -> None:
            received.put_nowait((data, (str(addr[0]), addr[1])))
            assert self.transport is not None
            self.transport.sendto(answer(str(addr[0]), addr[1]), addr)

    server, _ = await loop.create_datagram_endpoint(Echo, local_addr=("127.0.0.1", 0))
    host, port = server.get_extra_info("sockname")[:2]
    socket = await UdpTransportFactory().connect(host, port)
    try:
        address, local_port = await discover(socket, SSRC, FakeClock())
        assert address == "127.0.0.1"
        assert local_port > 0
        data, _ = await asyncio.wait_for(received.get(), timeout=2)
        assert data == discovery_request(SSRC)
    finally:
        socket.close()
        server.close()
    with pytest.raises(ConnectionError, match="closed"):
        await asyncio.wait_for(socket.receive(), timeout=2)
    with pytest.raises(ConnectionError, match="closed"):
        await asyncio.wait_for(socket.receive(), timeout=2)


async def test_a_full_queue_drops_the_oldest_and_still_takes_the_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()
    real = loop.create_datagram_endpoint
    protocols: list[asyncio.DatagramProtocol] = []

    async def recording(
        factory: Callable[[], asyncio.DatagramProtocol], *, remote_addr: tuple[str, int]
    ) -> tuple[asyncio.DatagramTransport, asyncio.DatagramProtocol]:
        transport, protocol = await real(factory, remote_addr=remote_addr)
        protocols.append(protocol)
        return transport, protocol

    monkeypatch.setattr(loop, "create_datagram_endpoint", recording)
    socket = await UdpTransportFactory().connect("127.0.0.1", 9)
    protocol = protocols[0]
    for index in range(RECEIVED_PACKETS_QUEUE_SIZE + 2):
        protocol.datagram_received(index.to_bytes(2), ("127.0.0.1", 9))
    socket.close()
    protocol.connection_lost(None)  # with the queue still full
    # The oldest three made room: two for the newest packets, one for the close.
    received = [await socket.receive() for _ in range(RECEIVED_PACKETS_QUEUE_SIZE - 1)]
    assert received[0] == (3).to_bytes(2)
    assert received[-1] == (RECEIVED_PACKETS_QUEUE_SIZE + 1).to_bytes(2)
    with pytest.raises(ConnectionError, match="closed"):
        await socket.receive()
