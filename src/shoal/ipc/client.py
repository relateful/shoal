"""The worker side of IPC: receives dispatch events from a gateway process.

    async with EventClient("127.0.0.1", 7700, token=secret, events=["INTERACTION_CREATE"]) as client:
        async for event in client:
            interaction = event.decode(Interaction)

A server listening on a Unix socket is reached with
`EventClient.unix("/run/bot/events.sock", token=secret)`. The client reconnects by itself with
backoff when the connection drops. Events published while it was disconnected are not replayed.
"""

import asyncio
import contextlib
import logging
import random
import sys
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from ssl import SSLContext
from types import TracebackType
from typing import Final, Self, final

from shoal.core.backoff import backoff_delay
from shoal.core.clock import Clock, SystemClock, sleep_unless
from shoal.core.codec import PayloadDecodeError
from shoal.core.dispatch import DispatchEvent
from shoal.core.tasks import cancel_and_wait
from shoal.ipc.defaults import (
    CLIENT_CONNECT_TIMEOUT,
    CLIENT_RECONNECT_BACKOFF_CAP,
    CLIENT_STABLE_CONNECTION,
    HANDSHAKE_TIMEOUT,
    MAX_FRAME_SIZE,
)
from shoal.ipc.protocol import (
    PROTOCOL_VERSION,
    Accepted,
    EventFrame,
    IPCError,
    Rejected,
    Subscribe,
    decode_server_message,
    encode_frame,
    read_frame,
)

_log = logging.getLogger("shoal.ipc.client")

_UNIX_SOCKETS: Final = sys.platform != "win32"
"""Whether this platform has Unix sockets (a name, so both platforms' type checks reach every line)."""


@final
class EventClient:
    """Subscribes to an `EventServer` and yields its events.

    Args:
        host: The gateway process's IPC host.
        port: Its IPC port.
        token: The shared secret.
        name: How this worker appears in the server's logs.
        shard_ids: Only receive events from these shards. `None` means all.
        events: Only receive these dispatch names. `None` means all.
        max_frame_size: Largest frame accepted from the server.
        ssl: TLS context, when the server listens with TLS.
        clock: Time source.
        random_source: Random source for reconnect jitter.
    """

    __slots__ = (
        "_clock",
        "_closing",
        "_events",
        "_host",
        "_max_frame",
        "_name",
        "_path",
        "_port",
        "_random_source",
        "_shard_ids",
        "_ssl",
        "_stopped",
        "_token",
        "_writer",
    )

    def __init__(
        self,
        host: str,
        port: int,
        *,
        token: str,
        name: str = "worker",
        shard_ids: Sequence[int] | None = None,
        events: Sequence[str] | None = None,
        max_frame_size: int = MAX_FRAME_SIZE,
        ssl: SSLContext | None = None,
        clock: Clock | None = None,
        random_source: random.Random | None = None,
    ) -> None:
        """Create a client; iterate it to connect and receive events."""
        self._host: str = host
        self._port: int = port
        self._token: str = token
        self._name: str = name
        self._shard_ids: list[int] | None = list(shard_ids) if shard_ids is not None else None
        self._events: list[str] | None = list(events) if events is not None else None
        self._max_frame: int = max_frame_size
        self._clock: Clock = clock or SystemClock()
        self._random_source: random.Random = random_source or random.Random()  # noqa: S311 - jitter, not security
        self._writer: asyncio.StreamWriter | None = None
        self._path: str | None = None
        self._ssl: SSLContext | None = ssl
        self._closing: bool = False
        self._stopped: asyncio.Event = asyncio.Event()

    @classmethod
    def unix(
        cls,
        path: str,
        *,
        token: str,
        name: str = "worker",
        shard_ids: Sequence[int] | None = None,
        events: Sequence[str] | None = None,
        max_frame_size: int = MAX_FRAME_SIZE,
        clock: Clock | None = None,
        random_source: random.Random | None = None,
    ) -> Self:
        """A client of a server listening on the Unix socket at `path`; the other arguments are as above.

        Raises:
            ValueError: Called on Windows, which has no Unix sockets.
        """
        if not _UNIX_SOCKETS:
            msg = "Unix sockets are not available on Windows; connect to a host and port"
            raise ValueError(msg)
        client = cls(
            path,
            0,
            token=token,
            name=name,
            shard_ids=shard_ids,
            events=events,
            max_frame_size=max_frame_size,
            clock=clock,
            random_source=random_source,
        )
        client._path = path
        return client

    @property
    def _target(self) -> str:
        return self._path if self._path is not None else f"{self._host}:{self._port}"

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    def __aiter__(self) -> AsyncIterator[DispatchEvent]:
        return self.events()

    @property
    def closed(self) -> bool:
        """Whether `close` has been called."""
        return self._closing

    def _stopping(self) -> bool:
        return self._closing

    async def close(self) -> None:
        """Stop receiving; an active iteration ends, including one waiting to reconnect."""
        self._closing = True
        self._stopped.set()
        if self._writer is not None:
            self._writer.close()

    async def events(self) -> AsyncGenerator[DispatchEvent]:
        """Connect (and reconnect) and yield events until `close` is called.

        Iterate one `events()` at a time per client; create a client per stream to receive several.

        Raises:
            IPCError: The server rejected the subscription (wrong token or protocol version), or
                sent a frame larger than `max_frame_size`.
        """
        failures = 0
        while not self._stopping():
            try:
                connection = await self._connect()
            except OSError as error:
                failures += 1
                delay = backoff_delay(
                    failures, cap=CLIENT_RECONNECT_BACKOFF_CAP, random_source=self._random_source
                )
                _log.warning("IPC connect to %s failed (%s); retrying in %.1fs", self._target, error, delay)
                await sleep_unless(self._clock, delay, self._stopped)
                continue
            if connection is None:
                break
            reader, writer = connection
            self._writer = writer
            subscribed_at: float | None = None
            try:
                await self._handshake(reader, writer)
                subscribed_at = self._clock.monotonic()
                async with contextlib.aclosing(self._receive(reader)) as received:
                    async for event in received:
                        yield event
            except (OSError, asyncio.IncompleteReadError, PayloadDecodeError) as error:
                if self._stopping():
                    break
                stable = (
                    subscribed_at is not None
                    and self._clock.monotonic() - subscribed_at >= CLIENT_STABLE_CONNECTION
                )
                failures = 1 if stable else failures + 1
                delay = backoff_delay(
                    failures, cap=CLIENT_RECONNECT_BACKOFF_CAP, random_source=self._random_source
                )
                _log.warning("IPC connection lost (%r); reconnecting in %.1fs", error, delay)
                await sleep_unless(self._clock, delay, self._stopped)
            finally:
                writer.close()
                self._writer = None

    async def _connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter] | None:
        """Open a connection, or return `None` once `close` is called while waiting for it.

        Raises:
            OSError: The connection failed or did not open within `CLIENT_CONNECT_TIMEOUT`.
        """
        opening = asyncio.ensure_future(asyncio.wait_for(self._open(), CLIENT_CONNECT_TIMEOUT))
        stopped = asyncio.ensure_future(self._stopped.wait())
        try:
            await asyncio.wait({opening, stopped}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stopped.cancel()
        if opening.done():
            reader, writer = opening.result()
            if not self._stopping():
                return reader, writer
            writer.close()
            return None
        await cancel_and_wait(opening)
        return None

    async def _open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if self._path is not None and sys.platform != "win32":
            return await asyncio.open_unix_connection(self._path)
        return await asyncio.open_connection(self._host, self._port, ssl=self._ssl)

    async def _handshake(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        hello = Subscribe(PROTOCOL_VERSION, self._token, self._name, self._shard_ids, self._events)
        writer.write(encode_frame(hello))
        await writer.drain()
        async with asyncio.timeout(HANDSHAKE_TIMEOUT):
            body = await read_frame(reader, self._max_frame)
        if body is None:
            msg = "the IPC server closed the connection during the handshake"
            raise ConnectionError(msg)
        answer = decode_server_message(body)
        if isinstance(answer, Rejected):
            msg = f"the IPC server rejected this client: {answer.reason}"
            raise IPCError(msg)
        if not isinstance(answer, Accepted):
            msg = "the IPC server sent an event before accepting the subscription"
            raise ConnectionError(msg)
        _log.info("IPC subscribed to %s as %r", self._target, self._name)

    async def _receive(self, reader: asyncio.StreamReader) -> AsyncGenerator[DispatchEvent]:
        while True:
            body = await read_frame(reader, self._max_frame)
            if body is None:
                msg = "the IPC server closed the connection"
                raise ConnectionError(msg)
            message = decode_server_message(body)
            if isinstance(message, EventFrame):
                yield message.to_event()
