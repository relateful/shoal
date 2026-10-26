import asyncio

import msgspec
import pytest

from shoal.core.codec import PayloadDecodeError
from shoal.core.dispatch import DispatchEvent
from shoal.ipc.protocol import (
    PROTOCOL_VERSION,
    Accepted,
    EventFrame,
    IPCError,
    Rejected,
    ServerMessage,
    Subscribe,
    decode_client_message,
    decode_server_message,
    encode_frame,
    read_frame,
)


def reader_with(data: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


async def test_frames_round_trip_every_message() -> None:
    event = DispatchEvent(3, "MESSAGE_CREATE", 9, msgspec.Raw(b'{"id":"1"}'))
    messages: list[ServerMessage] = [Accepted(PROTOCOL_VERSION), Rejected("no"), EventFrame.from_event(event)]
    reader = reader_with(b"".join(encode_frame(message) for message in messages))
    decoded = [decode_server_message(await read_frame(reader, 1024) or b"") for _ in messages]
    assert decoded == messages
    frame = decoded[2]
    assert isinstance(frame, EventFrame)
    assert frame.to_event() == event
    assert await read_frame(reader, 1024) is None


async def test_client_hello_round_trips() -> None:
    hello = Subscribe(PROTOCOL_VERSION, "secret", "worker", [0, 1], ["READY"])
    reader = reader_with(encode_frame(hello))
    body = await read_frame(reader, 1024)
    assert body is not None
    assert decode_client_message(body) == hello


def test_the_hello_repr_hides_the_token() -> None:
    hello = Subscribe(PROTOCOL_VERSION, "secret", "worker")
    assert "secret" not in repr(hello)
    assert "worker" in repr(hello)


async def test_oversized_and_truncated_frames_fail() -> None:
    with pytest.raises(IPCError, match="exceeds"):
        await read_frame(reader_with(encode_frame(Rejected("x" * 100))), 10)
    with pytest.raises(asyncio.IncompleteReadError):
        await read_frame(reader_with(encode_frame(Rejected("x"))[:-1]), 1024)


def test_garbage_is_a_decode_error() -> None:
    with pytest.raises(PayloadDecodeError):
        decode_server_message(b"\xc1")
    with pytest.raises(PayloadDecodeError):
        decode_client_message(msgspec.msgpack.encode(["accepted", 1]))


def test_an_event_frame_repr_leaves_out_the_data() -> None:
    frame = EventFrame(0, "INTERACTION_CREATE", 1, b'{"token":"secret"}')
    assert "secret" not in repr(frame)
    assert "18 bytes" in repr(frame)
