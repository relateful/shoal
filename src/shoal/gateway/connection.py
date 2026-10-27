"""The websocket underneath a shard, behind a protocol so shards can be tested without a network.

Discord: https://docs.discord.com/developers/events/gateway#connecting
"""

import asyncio
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol, final, override

import aiohttp

from shoal.gateway.defaults import CONNECT_TIMEOUT


class MessageKind(Enum):
    """What a websocket frame carried."""

    TEXT = auto()
    BINARY = auto()
    CLOSED = auto()


@dataclass(frozen=True, slots=True)
class WebSocketMessage:
    """One received frame. `close_code` is set for `CLOSED` (None when the socket dropped)."""

    kind: MessageKind
    data: bytes = b""
    close_code: int | None = None


class GatewayConnection(Protocol):
    """An open websocket to the gateway."""

    __slots__ = ()

    async def receive(self) -> WebSocketMessage:
        """Wait for the next frame. Returns a `CLOSED` message once the socket is gone."""
        ...

    async def send(self, data: bytes) -> None:
        """Send a text frame containing UTF-8 JSON."""
        ...

    async def send_binary(self, data: bytes) -> None:
        """Send a binary frame (the voice gateway's DAVE messages)."""
        ...

    async def close(self, code: int) -> None:
        """Close the socket with `code`. 1000/1001 end the session; anything else keeps it resumable."""
        ...


class GatewayConnector(Protocol):
    """Opens gateway connections."""

    __slots__ = ()

    async def connect(self, url: str) -> GatewayConnection:
        """Open a websocket to `url`. Raises `OSError` when the connection cannot be made."""
        ...

    async def close(self) -> None:
        """Release shared resources (the HTTP session)."""
        ...


@final
class _AiohttpConnection(GatewayConnection):
    __slots__ = ("_socket",)

    def __init__(self, socket: aiohttp.ClientWebSocketResponse) -> None:
        self._socket: aiohttp.ClientWebSocketResponse = socket

    @override
    async def receive(self) -> WebSocketMessage:
        message = await self._socket.receive()
        if message.type is aiohttp.WSMsgType.TEXT:
            text: str = message.data
            return WebSocketMessage(MessageKind.TEXT, text.encode())
        if message.type is aiohttp.WSMsgType.BINARY:
            data: bytes = message.data
            return WebSocketMessage(MessageKind.BINARY, data)
        return WebSocketMessage(MessageKind.CLOSED, close_code=self._socket.close_code)

    @override
    async def send(self, data: bytes) -> None:
        await self._socket.send_str(data.decode())

    @override
    async def send_binary(self, data: bytes) -> None:
        await self._socket.send_bytes(data)

    @override
    async def close(self, code: int) -> None:
        await self._socket.close(code=code)


@final
class AiohttpGatewayConnector(GatewayConnector):
    """Opens gateway websockets with aiohttp, sharing one HTTP session between shards."""

    __slots__ = ("_session", "_timeout")

    def __init__(self, *, connect_timeout: float = CONNECT_TIMEOUT) -> None:
        """Create the connector; the session opens lazily."""
        self._timeout: float = connect_timeout
        self._session: aiohttp.ClientSession | None = None

    @override
    async def connect(self, url: str) -> GatewayConnection:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        try:
            async with asyncio.timeout(self._timeout):
                socket = await self._session.ws_connect(url, autoclose=False, max_msg_size=0)
        except (aiohttp.ClientError, TimeoutError) as error:
            msg = f"could not connect to the gateway: {type(error).__name__}: {error}"
            raise ConnectionError(msg) from error
        return _AiohttpConnection(socket)

    @override
    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
