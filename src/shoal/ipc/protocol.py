"""The IPC wire protocol: length-prefixed msgpack frames over a byte stream.

Every frame is a 4-byte big-endian length followed by that many bytes of msgpack. The first frame on a
connection is the client's `Subscribe`; the server answers `Accepted` or `Rejected`, then sends one
`EventFrame` per matching dispatch. The dispatch data inside an `EventFrame` is the raw JSON Discord
sent, carried as bytes, so forwarding never decodes or re-encodes an event.
"""

import asyncio
import struct
from typing import Final, override

import msgspec

from shoal.core.codec import PayloadDecodeError, decode_msgpack, encode_msgpack
from shoal.core.dispatch import DispatchEvent
from shoal.core.errors import ShoalError

PROTOCOL_VERSION: Final = 1
"""Bumped on incompatible wire changes; a server rejects clients speaking another version."""

_HEADER: Final = struct.Struct("!I")


class IPCError(ShoalError):
    """An IPC connection failed in a way retrying will not fix (bad token, version, oversized frame)."""


class Subscribe(msgspec.Struct, tag="subscribe", array_like=True, frozen=True):
    """Client hello: credentials and which events the client wants."""

    version: int
    token: str
    name: str
    shard_ids: list[int] | None = None
    """Only events from these shards. `None` means every shard."""
    events: list[str] | None = None
    """Only these dispatch names (for example `["INTERACTION_CREATE"]`). `None` means every event."""

    @override
    def __repr__(self) -> str:
        """Everything but the token, which must never reach a log or an error tracker."""
        return f"Subscribe(version={self.version}, name={self.name!r}, token=<redacted>)"


class Accepted(msgspec.Struct, tag="accepted", array_like=True, frozen=True):
    """The server accepted the subscription."""

    version: int


class Rejected(msgspec.Struct, tag="rejected", array_like=True, frozen=True):
    """The server refused the subscription and will close the connection."""

    reason: str


class EventFrame(msgspec.Struct, tag="event", array_like=True, frozen=True, gc=False):
    """One dispatch, with Discord's JSON carried untouched."""

    shard_id: int
    name: str
    sequence: int | None
    data: bytes

    @classmethod
    def from_event(cls, event: DispatchEvent) -> "EventFrame":
        """Wrap a dispatch for sending."""
        return cls(event.shard_id, event.name, event.sequence, bytes(event.data))

    def to_event(self) -> DispatchEvent:
        """Unwrap a received dispatch."""
        return DispatchEvent(self.shard_id, self.name, self.sequence, msgspec.Raw(self.data))

    @override
    def __repr__(self) -> str:
        """Everything but the data, which can hold interaction tokens."""
        return (
            f"EventFrame(shard_id={self.shard_id}, name={self.name!r}, sequence={self.sequence}, "
            f"data=<{len(self.data)} bytes>)"
        )


type ClientMessage = Subscribe
type ServerMessage = Accepted | Rejected | EventFrame


def encode_frame(message: ClientMessage | ServerMessage) -> bytes:
    """Serialize a message with its length prefix."""
    body = encode_msgpack(message)
    return _HEADER.pack(len(body)) + body


async def read_frame(reader: asyncio.StreamReader, max_size: int) -> bytes | None:
    """Read one frame body. Returns `None` at a clean end of stream.

    Raises:
        IPCError: The frame announces more than `max_size` bytes.
        asyncio.IncompleteReadError: The stream ended mid-frame.
    """
    try:
        header = await reader.readexactly(_HEADER.size)
    except asyncio.IncompleteReadError as error:
        if not error.partial:
            return None
        raise
    (size,) = _HEADER.unpack(header)
    if size > max_size:
        msg = f"IPC frame of {size} bytes exceeds the {max_size}-byte limit"
        raise IPCError(msg)
    return await reader.readexactly(size)


def decode_client_message(body: bytes) -> ClientMessage:
    """Decode a frame sent by a client.

    Raises:
        PayloadDecodeError: The frame is not a valid client message.
    """
    return decode_msgpack(body, Subscribe)


_SERVER_DECODER: Final[msgspec.msgpack.Decoder[ServerMessage]] = msgspec.msgpack.Decoder(
    Accepted | Rejected | EventFrame
)


def decode_server_message(body: bytes) -> ServerMessage:
    """Decode a frame sent by the server.

    Raises:
        PayloadDecodeError: The frame is not a valid server message.
    """
    try:
        return _SERVER_DECODER.decode(body)
    except msgspec.DecodeError as error:
        raise PayloadDecodeError(ServerMessage, str(error)) from error
