"""The UDP socket that carries voice packets, and IP discovery.

IP discovery sends the voice server one packet with the bot's SSRC; the answer says the address and
port the server sees the bot at, which the bot then tells the voice gateway (Select Protocol).

Discord: https://docs.discord.com/developers/topics/voice-connections#ip-discovery
"""

import asyncio
import contextlib
import struct
from typing import Final, Protocol, final, override

from shoal.core.clock import Clock, within
from shoal.payloads.voice_gateway import IP_DISCOVERY_LENGTH
from shoal.voice.defaults import IP_DISCOVERY_TIMEOUT, RECEIVED_PACKETS_QUEUE_SIZE

_REQUEST: Final = 1
"""IP discovery packet type: a request."""

_RESPONSE: Final = 2
"""IP discovery packet type: the server's answer."""

_DISCOVERY_SIZE: Final = 4 + IP_DISCOVERY_LENGTH
"""Bytes in an IP discovery packet: type, length, then `IP_DISCOVERY_LENGTH` bytes."""


class VoiceTransport(Protocol):
    """A datagram socket to one voice server, behind a protocol so connections can be tested."""

    __slots__ = ()

    def send(self, packet: bytes) -> None:
        """Send one packet; a full socket buffer drops it, as UDP does."""
        ...

    async def receive(self) -> bytes:
        """The next packet received.

        Raises:
            ConnectionError: The socket was closed.
        """
        ...

    def close(self) -> None:
        """Close the socket; a waiting `receive` raises."""
        ...


class VoiceTransportFactory(Protocol):
    """Opens voice sockets."""

    __slots__ = ()

    async def connect(self, host: str, port: int) -> VoiceTransport:
        """A socket sending to `host:port`.

        Raises:
            OSError: The socket could not be opened.
        """
        ...


@final
class _Datagrams(asyncio.DatagramProtocol):
    """Queues received packets; the oldest is dropped when the reader falls behind."""

    __slots__ = ("packets",)

    def __init__(self) -> None:
        self.packets: asyncio.Queue[bytes | None] = asyncio.Queue(RECEIVED_PACKETS_QUEUE_SIZE)

    @override
    def datagram_received(self, data: bytes, addr: tuple[str | int, ...]) -> None:
        if self.packets.full():
            # Audio is only worth having on time: drop the oldest rather than fall further behind.
            with contextlib.suppress(asyncio.QueueEmpty):
                _ = self.packets.get_nowait()
        self.packets.put_nowait(data)

    @override
    def connection_lost(self, exc: Exception | None) -> None:
        if self.packets.full():
            _ = self.packets.get_nowait()  # the close must get through
        self.packets.put_nowait(None)


@final
class _UdpTransport(VoiceTransport):
    __slots__ = ("_protocol", "_transport")

    def __init__(self, transport: asyncio.DatagramTransport, protocol: _Datagrams) -> None:
        self._transport: asyncio.DatagramTransport = transport
        self._protocol: _Datagrams = protocol

    @override
    def send(self, packet: bytes) -> None:
        self._transport.sendto(packet)

    @override
    async def receive(self) -> bytes:
        packet = await self._protocol.packets.get()
        if packet is None:
            self._protocol.packets.put_nowait(None)  # every later `receive` sees the close too
            msg = "the voice socket is closed"
            raise ConnectionError(msg)
        return packet

    @override
    def close(self) -> None:
        self._transport.close()


@final
class UdpTransportFactory(VoiceTransportFactory):
    """Opens real UDP sockets."""

    __slots__ = ()

    @override
    async def connect(self, host: str, port: int) -> VoiceTransport:
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(_Datagrams, remote_addr=(host, port))
        return _UdpTransport(transport, protocol)


def discovery_request(ssrc: int) -> bytes:
    """The IP discovery request for `ssrc`."""
    return struct.pack(">HHI", _REQUEST, IP_DISCOVERY_LENGTH, ssrc) + bytes(IP_DISCOVERY_LENGTH - 4)


def parse_discovery(packet: bytes) -> tuple[str, int]:
    """The address and port an IP discovery answer reports.

    Raises:
        ValueError: The packet is not an IP discovery answer.
    """
    if len(packet) < _DISCOVERY_SIZE:
        msg = "not an IP discovery answer"
        raise ValueError(msg)
    kind, length = struct.unpack_from(">HH", packet)
    if kind != _RESPONSE or length != IP_DISCOVERY_LENGTH:
        msg = "not an IP discovery answer"
        raise ValueError(msg)
    address = packet[8:72].split(b"\0", 1)[0].decode("ascii")
    (port,) = struct.unpack_from(">H", packet, 72)
    return address, port


async def discover(transport: VoiceTransport, ssrc: int, clock: Clock) -> tuple[str, int]:
    """Ask the voice server which address and port it sees this socket at.

    Packets that are not the answer (audio that arrives early) are skipped.

    Raises:
        TimeoutError: No answer came within `IP_DISCOVERY_TIMEOUT`.
        ConnectionError: The socket was closed.
    """
    transport.send(discovery_request(ssrc))

    async def answer() -> tuple[str, int]:
        while True:
            with contextlib.suppress(ValueError):
                return parse_discovery(await transport.receive())

    return await within(clock, IP_DISCOVERY_TIMEOUT, answer())
