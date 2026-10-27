"""A scripted voice server: a voice gateway websocket and a UDP socket that answer like Discord's."""

import asyncio
import struct
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import final, override

import msgspec

from shoal.core.codec import encode_json
from shoal.gateway.connection import GatewayConnection, GatewayConnector, MessageKind, WebSocketMessage
from shoal.voice.connection import VoiceServer
from shoal.voice.udp import VoiceTransport, VoiceTransportFactory

KEY = bytes(range(32))
"""The session key the fake voice server hands out."""

SSRC = 7
"""The bot's SSRC in the fake call."""

EXTERNAL = ("203.0.113.5", 4242)
"""The address IP discovery reports."""

SERVER = VoiceServer(
    guild_id=10, channel_id=20, session_id="voice-session", token="voice-token", endpoint="voice.test:443"
)


@dataclass
class FakeVoiceGateway(GatewayConnection):
    """One voice websocket: answers Identify, Select Protocol, Resume and heartbeats."""

    modes: Sequence[str] = ("aead_aes256_gcm_rtpsize", "aead_xchacha20_poly1305_rtpsize")
    dave_version: int = 0
    acknowledge: bool = True
    resumes: bool = True
    incoming: asyncio.Queue[WebSocketMessage] = field(default_factory=asyncio.Queue[WebSocketMessage])
    sent: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    sent_binary: list[bytes] = field(default_factory=list[bytes])
    close_codes: list[int] = field(default_factory=list[int])

    def __post_init__(self) -> None:
        self.push(8, {"heartbeat_interval": 41250})

    def push(self, op: int, data: object, *, seq: int | None = None) -> None:
        message: dict[str, object] = {"op": op, "d": data}
        if seq is not None:
            message["seq"] = seq
        self.incoming.put_nowait(WebSocketMessage(MessageKind.TEXT, encode_json(message)))

    def push_binary(self, seq: int, op: int, payload: bytes) -> None:
        self.incoming.put_nowait(WebSocketMessage(MessageKind.BINARY, struct.pack(">HB", seq, op) + payload))

    def drop(self, code: int | None) -> None:
        self.incoming.put_nowait(WebSocketMessage(MessageKind.CLOSED, close_code=code))

    def ops(self) -> list[object]:
        return [message["op"] for message in self.sent]

    @override
    async def receive(self) -> WebSocketMessage:
        return await self.incoming.get()

    @override
    async def send(self, data: bytes) -> None:
        message = msgspec.json.decode(data, type=dict[str, object])
        self.sent.append(message)
        op, body = message["op"], msgspec.convert(message["d"], dict[str, object])
        if op == 0:
            self.push(
                2,
                {
                    "ssrc": SSRC,
                    "ip": "198.51.100.1",
                    "port": 50000,
                    "modes": list(self.modes),
                    "heartbeat_interval": 1,
                },
            )
        elif op == 1:
            selected = msgspec.convert(body["data"], dict[str, object])
            self.push(
                4,
                {
                    "mode": selected["mode"],
                    "secret_key": list(KEY),
                    "dave_protocol_version": self.dave_version,
                },
            )
        elif op == 7 and self.resumes:
            self.push(9, None)
        elif op == 3 and self.acknowledge:
            self.push(6, {"t": body["t"]})

    @override
    async def send_binary(self, data: bytes) -> None:
        self.sent_binary.append(data)

    @override
    async def close(self, code: int) -> None:
        if not self.close_codes:
            self.close_codes.append(code)
            self.drop(code)


@final
class FakeVoiceConnector(GatewayConnector):
    """Hands out voice gateways in order (a fresh default one when none is prepared)."""

    def __init__(self, *gateways: FakeVoiceGateway) -> None:
        self.prepared: list[FakeVoiceGateway] = list(gateways)
        self.opened: list[FakeVoiceGateway] = []
        self.urls: list[str] = []
        self.closed = False

    @override
    async def connect(self, url: str) -> GatewayConnection:
        self.urls.append(url)
        gateway = self.prepared.pop(0) if self.prepared else FakeVoiceGateway()
        self.opened.append(gateway)
        return gateway

    @override
    async def close(self) -> None:
        self.closed = True


@final
class FakeVoiceTransport(VoiceTransport):
    """A UDP socket that answers IP discovery and records every packet sent."""

    def __init__(self, *, discovers: bool = True) -> None:
        self.sent: list[bytes] = []
        self.incoming: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.closed = False
        self.discovers = discovers

    @override
    def send(self, packet: bytes) -> None:
        self.sent.append(packet)
        if self.discovers and packet[:2] == b"\x00\x01":
            address = EXTERNAL[0].encode().ljust(64, b"\0")
            answer = struct.pack(">HHI", 2, 70, SSRC) + address + struct.pack(">H", EXTERNAL[1])
            self.incoming.put_nowait(answer)

    @override
    async def receive(self) -> bytes:
        packet = await self.incoming.get()
        if packet is None:
            self.incoming.put_nowait(None)
            msg = "closed"
            raise ConnectionError(msg)
        return packet

    @override
    def close(self) -> None:
        self.closed = True
        self.incoming.put_nowait(None)

    def audio(self) -> list[bytes]:
        """The voice packets sent: everything but the IP discovery request."""
        return [packet for packet in self.sent if packet[:2] != b"\x00\x01"]


@final
class FakeVoiceTransports(VoiceTransportFactory):
    def __init__(self, *, discovers: bool = True) -> None:
        self.transports: list[FakeVoiceTransport] = []
        self.addresses: list[tuple[str, int]] = []
        self.discovers = discovers

    @override
    async def connect(self, host: str, port: int) -> VoiceTransport:
        self.addresses.append((host, port))
        transport = FakeVoiceTransport(discovers=self.discovers)
        self.transports.append(transport)
        return transport
