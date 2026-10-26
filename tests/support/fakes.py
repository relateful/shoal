"""Deterministic stand-ins for time, HTTP and websockets, shared by the test suite."""

import asyncio
import zlib
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import final, override

from shoal.core.clock import Clock
from shoal.core.codec import encode_json
from shoal.gateway.connection import GatewayConnection, GatewayConnector, MessageKind, WebSocketMessage
from shoal.rest.transport import HTTPResponse, HTTPTransport


@final
class FakeClock(Clock):
    """A clock that only moves when something sleeps. `sleep` yields to the loop, then advances."""

    def __init__(self, *, monotonic: float = 1_000.0, wall: float = 1_750_000_000.0) -> None:
        self._monotonic = monotonic
        self._wall = wall
        self.sleeps: list[float] = []

    @override
    def monotonic(self) -> float:
        return self._monotonic

    @override
    def wall(self) -> float:
        return self._wall

    def advance(self, seconds: float) -> None:
        self._monotonic += seconds
        self._wall += seconds

    @override
    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        await asyncio.sleep(0)
        if seconds > 0:
            self.advance(seconds)


@final
class ManualClock(Clock):
    """A clock whose sleeps only finish when the test calls `advance`. For timing-sensitive tasks."""

    def __init__(self, *, monotonic: float = 1_000.0, wall: float = 1_750_000_000.0) -> None:
        self._monotonic = monotonic
        self._wall = wall
        self._waiters: list[tuple[float, asyncio.Future[None]]] = []

    @override
    def monotonic(self) -> float:
        return self._monotonic

    @override
    def wall(self) -> float:
        return self._wall

    @override
    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiters.append((self._monotonic + seconds, future))
        await future

    async def advance(self, seconds: float) -> None:
        self._monotonic += seconds
        self._wall += seconds
        due = [waiter for waiter in self._waiters if waiter[0] <= self._monotonic]
        self._waiters = [waiter for waiter in self._waiters if waiter[0] > self._monotonic]
        for _, future in due:
            if not future.done():
                future.set_result(None)
        await settle()


async def settle(rounds: int = 20) -> None:
    """Let every ready task run until the loop is quiet."""
    for _ in range(rounds):
        await asyncio.sleep(0)


@dataclass(frozen=True, slots=True)
class SentRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None


@final
class FakeTransport(HTTPTransport):
    """Replays queued responses (or exceptions) and records every request."""

    def __init__(self) -> None:
        self.responses: deque[HTTPResponse | OSError] = deque()
        self.requests: list[SentRequest] = []
        self.closed = False

    def queue(self, status: int, body: object = None, headers: Mapping[str, str] | None = None) -> None:
        """Queue a response; `body` is encoded as JSON unless it is already bytes."""
        payload = b"" if body is None else body if isinstance(body, bytes) else encode_json(body)
        self.responses.append(HTTPResponse(status=status, headers=dict(headers or {}), body=payload))

    def queue_error(self, error: OSError) -> None:
        self.responses.append(error)

    @override
    async def request(
        self, method: str, url: str, *, headers: Mapping[str, str], body: bytes | None
    ) -> HTTPResponse:
        self.requests.append(SentRequest(method, url, dict(headers), body))
        await asyncio.sleep(0)
        if not self.responses:
            msg = f"no response queued for {method} {url}"
            raise AssertionError(msg)
        response = self.responses.popleft()
        if isinstance(response, OSError):
            raise response
        return response

    @override
    async def close(self) -> None:
        self.closed = True


def gateway_message(op: int, d: object = None, *, s: int | None = None, t: str | None = None) -> bytes:
    """Encode one gateway payload the way Discord sends it."""
    return encode_json({"op": op, "d": d, "s": s, "t": t})


@dataclass
class FakeConnection(GatewayConnection):
    """A websocket whose incoming frames are queued by the test and whose sends are recorded."""

    incoming: asyncio.Queue[WebSocketMessage] = field(default_factory=asyncio.Queue[WebSocketMessage])
    sent: list[bytes] = field(default_factory=list[bytes])
    close_codes: list[int] = field(default_factory=list[int])
    sent_event: asyncio.Event = field(default_factory=asyncio.Event)

    def push(self, data: bytes) -> None:
        self.incoming.put_nowait(WebSocketMessage(MessageKind.TEXT, data))

    def push_binary(self, data: bytes) -> None:
        self.incoming.put_nowait(WebSocketMessage(MessageKind.BINARY, data))

    def push_close(self, code: int | None) -> None:
        self.incoming.put_nowait(WebSocketMessage(MessageKind.CLOSED, close_code=code))

    @override
    async def receive(self) -> WebSocketMessage:
        return await self.incoming.get()

    @override
    async def send(self, data: bytes) -> None:
        self.sent.append(data)
        self.sent_event.set()

    @override
    async def close(self, code: int) -> None:
        # Like a real websocket, only the first close sends a frame.
        if self.close_codes:
            return
        self.close_codes.append(code)
        self.push_close(code)


@final
class FakeConnector(GatewayConnector):
    """Hands out prepared connections in order and records the URLs requested."""

    def __init__(self, *connections: FakeConnection | OSError) -> None:
        self.connections: deque[FakeConnection | OSError] = deque(connections)
        self.urls: list[str] = []
        self.closed = False
        self.exhausted = asyncio.Event()

    @override
    async def connect(self, url: str) -> GatewayConnection:
        self.urls.append(url)
        if not self.connections:
            self.exhausted.set()
            msg = "no more connections prepared"
            raise ConnectionError(msg)
        prepared = self.connections.popleft()
        if isinstance(prepared, OSError):
            raise prepared
        return prepared

    @override
    async def close(self) -> None:
        self.closed = True


def zlib_stream_frames(*messages: bytes) -> list[bytes]:
    """Compress messages with one shared zlib context and Z_SYNC_FLUSH, like Discord's zlib-stream."""
    compressor = zlib.compressobj()
    return [compressor.compress(message) + compressor.flush(zlib.Z_SYNC_FLUSH) for message in messages]
