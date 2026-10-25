"""The gateway side of IPC: streams dispatch events to worker processes.

    server = EventServer(token=secret, port=7700)
    await server.start()
    shards = ShardManager(..., dispatch=server.publish)

Each subscriber gets its own bounded queue and writer task. A subscriber that falls behind by
`queue_size` events is disconnected (and counted in `shoal_ipc_disconnects_total{reason="slow"}`)
instead of growing the gateway process's memory; it reconnects and continues.
"""

import asyncio
import contextlib
import hmac
import logging
from dataclasses import dataclass, field
from ssl import SSLContext
from typing import Final, final

from shoal.core.codec import PayloadDecodeError
from shoal.core.dispatch import DispatchEvent
from shoal.core.metrics import IPC_DISCONNECTS, IPC_EVENTS_SENT, IPC_SUBSCRIBERS, Metrics, NoopMetrics
from shoal.ipc.defaults import (
    HANDSHAKE_MAX_FRAME_SIZE,
    HANDSHAKE_TIMEOUT,
    MAX_FRAME_SIZE,
    SUBSCRIBER_QUEUE_SIZE,
)
from shoal.ipc.protocol import (
    PROTOCOL_VERSION,
    Accepted,
    EventFrame,
    IPCError,
    Rejected,
    Subscribe,
    decode_client_message,
    encode_frame,
    read_frame,
)

_log = logging.getLogger("shoal.ipc.server")

_DISCARD_CHUNK: Final = 64 * 1024
"""Bytes read at a time from a subscriber that sends anything after its handshake."""

_LOGGED_NAME_LENGTH: Final = 100
"""How much of a rejected client's self-chosen name is logged."""


@dataclass(eq=False, slots=True)
class _Subscriber:
    name: str
    shard_ids: frozenset[int] | None
    events: frozenset[str] | None
    writer: asyncio.StreamWriter
    queue: asyncio.Queue[bytes]
    task: asyncio.Task[None] | None = field(default=None)

    def wants(self, event: DispatchEvent) -> bool:
        return (self.shard_ids is None or event.shard_id in self.shard_ids) and (
            self.events is None or event.name in self.events
        )


@final
class EventServer:
    """Accepts worker connections and forwards every published dispatch to the matching ones.

    Args:
        token: Shared secret workers must present. Required; there is no default.
        host: Interface to listen on. Keep the default loopback unless the port is firewalled; across
            hosts, pass `ssl` so the token and events are encrypted.
        port: TCP port; 0 picks a free one (see `address`).
        queue_size: Events buffered per subscriber before it is disconnected as too slow.
        max_frame_size: Largest frame accepted from a client.
        metrics: Receives subscriber counts, events sent and disconnects.
        ssl: TLS context for the listening socket.
    """

    __slots__ = (
        "_connections",
        "_host",
        "_max_frame",
        "_metrics",
        "_port",
        "_queue_size",
        "_server",
        "_ssl",
        "_subscribers",
        "_token",
    )

    def __init__(
        self,
        *,
        token: str,
        host: str = "127.0.0.1",
        port: int = 0,
        queue_size: int = SUBSCRIBER_QUEUE_SIZE,
        max_frame_size: int = MAX_FRAME_SIZE,
        metrics: Metrics | None = None,
        ssl: SSLContext | None = None,
    ) -> None:
        """Create a server; call `start` to listen."""
        if not token:
            msg = "an IPC token is required"
            raise ValueError(msg)
        self._token: bytes = token.encode()
        self._host: str = host
        self._port: int = port
        self._queue_size: int = queue_size
        self._max_frame: int = max_frame_size
        self._metrics: Metrics = metrics or NoopMetrics()
        self._server: asyncio.Server | None = None
        self._subscribers: set[_Subscriber] = set()
        self._connections: set[asyncio.StreamWriter] = set()
        self._ssl: SSLContext | None = ssl

    @property
    def address(self) -> tuple[str, int]:
        """The host and port the server listens on.

        Raises:
            RuntimeError: The server has not been started.
        """
        if self._server is None or not self._server.sockets:
            msg = "the EventServer is not listening"
            raise RuntimeError(msg)
        host, port = self._server.sockets[0].getsockname()[:2]
        return str(host), int(port)

    @property
    def subscriber_count(self) -> int:
        """Connected, authenticated subscribers."""
        return len(self._subscribers)

    async def start(self) -> None:
        """Start listening. Idempotent."""
        if self._server is None:
            self._server = await asyncio.start_server(self._accept, self._host, self._port, ssl=self._ssl)
            _log.info("IPC server listening on %s:%d", *self.address)

    async def close(self) -> None:
        """Stop listening and disconnect every connection, including ones still authenticating.

        Connections are aborted, not closed gracefully: a subscriber that stopped reading would
        otherwise keep its socket open while the server waits to flush to it, and
        `Server.wait_closed` waits for every open connection.
        """
        server, self._server = self._server, None
        if server is not None:
            server.close()
        for subscriber in list(self._subscribers):
            self._drop(subscriber, "closed")
        connections = list(self._connections)
        self._connections.clear()
        for writer in connections:
            writer.transport.abort()
        if server is not None:
            await server.wait_closed()

    async def publish(self, event: DispatchEvent) -> None:
        """Queue `event` for every subscriber that wants it. Never waits on a subscriber.

        Usable directly as a shard's `dispatch` handler.
        """
        frame: bytes | None = None
        for subscriber in list(self._subscribers):
            if not subscriber.wants(event):
                continue
            if frame is None:
                frame = encode_frame(EventFrame.from_event(event))
            try:
                subscriber.queue.put_nowait(frame)
            except asyncio.QueueFull:
                _log.warning(
                    "IPC subscriber %r fell %d events behind; disconnecting it",
                    subscriber.name,
                    self._queue_size,
                )
                self._drop(subscriber, "slow")
                continue
            self._metrics.increment(IPC_EVENTS_SENT)

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._connections.add(writer)
        try:
            async with asyncio.timeout(HANDSHAKE_TIMEOUT):
                body = await read_frame(reader, min(self._max_frame, HANDSHAKE_MAX_FRAME_SIZE))
            if body is None:
                self._close(writer)
                return
            hello = decode_client_message(body)
        except (TimeoutError, IPCError, PayloadDecodeError, asyncio.IncompleteReadError, OSError):
            self._metrics.increment(IPC_DISCONNECTS, {"reason": "rejected"})
            self._close(writer)
            return
        reason = self._reject_reason(hello)
        if reason is not None:
            _log.warning("IPC subscriber %r rejected: %s", hello.name[:_LOGGED_NAME_LENGTH], reason)
            self._metrics.increment(IPC_DISCONNECTS, {"reason": "rejected"})
            writer.write(encode_frame(Rejected(reason)))
            with contextlib.suppress(OSError):
                await writer.drain()
            self._close(writer)
            return
        if self._server is None:
            # `close` ran while this hello was being read.
            self._abort(writer)
            return
        subscriber = _Subscriber(
            name=hello.name,
            shard_ids=frozenset(hello.shard_ids) if hello.shard_ids is not None else None,
            events=frozenset(hello.events) if hello.events is not None else None,
            writer=writer,
            queue=asyncio.Queue(self._queue_size),
        )
        writer.write(encode_frame(Accepted(PROTOCOL_VERSION)))
        self._subscribers.add(subscriber)
        self._metrics.set(IPC_SUBSCRIBERS, len(self._subscribers))
        _log.info("IPC subscriber %r connected", hello.name)
        subscriber.task = asyncio.create_task(self._pump(subscriber, reader), name=f"shoal-ipc-{hello.name}")

    def _reject_reason(self, hello: Subscribe) -> str | None:
        if not hmac.compare_digest(hello.token.encode(), self._token):
            return "invalid token"
        if hello.version != PROTOCOL_VERSION:
            return f"protocol version {hello.version} is not supported (server speaks {PROTOCOL_VERSION})"
        return None

    async def _pump(self, subscriber: _Subscriber, reader: asyncio.StreamReader) -> None:
        closed = asyncio.create_task(_until_closed(reader))
        frame: asyncio.Task[bytes] | None = None
        try:
            while True:
                frame = asyncio.create_task(subscriber.queue.get())
                done, _ = await asyncio.wait({frame, closed}, return_when=asyncio.FIRST_COMPLETED)
                if closed in done:
                    self._drop(subscriber, "closed")
                    return
                subscriber.writer.write(frame.result())
                await subscriber.writer.drain()
        except OSError:
            self._drop(subscriber, "error")
        except Exception:  # noqa: BLE001 - one subscriber's failure must never reach the others
            _log.exception("IPC subscriber %r failed", subscriber.name)
            self._drop(subscriber, "error")
        finally:
            closed.cancel()
            if frame is not None:
                frame.cancel()

    def _drop(self, subscriber: _Subscriber, reason: str) -> None:
        """Forget a subscriber and close its socket without waiting, so no caller ever blocks on it."""
        if subscriber not in self._subscribers:
            return
        self._subscribers.discard(subscriber)
        self._metrics.set(IPC_SUBSCRIBERS, len(self._subscribers))
        self._metrics.increment(IPC_DISCONNECTS, {"reason": reason})
        if subscriber.task is not None and subscriber.task is not asyncio.current_task():
            subscriber.task.cancel()
        # Whatever is still queued for it is discarded anyway; a graceful close would wait to flush.
        self._abort(subscriber.writer)
        _log.info("IPC subscriber %r disconnected (%s)", subscriber.name, reason)

    def _close(self, writer: asyncio.StreamWriter) -> None:
        self._connections.discard(writer)
        writer.close()

    def _abort(self, writer: asyncio.StreamWriter) -> None:
        self._connections.discard(writer)
        writer.transport.abort()


async def _until_closed(reader: asyncio.StreamReader) -> None:
    """Return once the peer closes. Subscribers send nothing after the handshake; data is discarded."""
    with contextlib.suppress(OSError):
        while await reader.read(_DISCARD_CHUNK):
            pass
