import msgspec
import pytest

from shoal.core.codec import (
    PayloadDecodeError,
    decode_json,
    decode_msgpack,
    encode_json,
    encode_msgpack,
    json_decoder,
)
from shoal.core.snowflake import Snowflake
from shoal.payloads import ChannelType, MessageFlags, Permissions, User


class Holder(msgspec.Struct):
    id: Snowflake
    permissions: Permissions
    flags: MessageFlags
    channel_type: ChannelType


def test_json_round_trip_uses_discord_wire_formats() -> None:
    raw = b'{"id":"80351110224678912","permissions":"2048","flags":4,"channel_type":77}'
    holder = decode_json(raw, Holder)
    assert holder.id == 80351110224678912
    assert holder.permissions.send_messages
    assert holder.flags.suppress_embeds
    assert holder.channel_type == 77
    assert encode_json(holder) == raw


def test_msgpack_stores_snowflakes_and_flags_as_integers() -> None:
    holder = Holder(Snowflake(1), Permissions(8), MessageFlags(4), ChannelType.DM)
    data = encode_msgpack(holder)
    assert msgspec.msgpack.decode(data) == {"id": 1, "permissions": 8, "flags": 4, "channel_type": 1}
    assert decode_msgpack(data, Holder) == holder


@pytest.mark.parametrize(
    "raw",
    [
        b'{"id":true,"permissions":"1","flags":0,"channel_type":0}',
        b'{"id":"1","permissions":[],"flags":0,"channel_type":0}',
        b"{",
    ],
)
def test_bad_input_raises_payload_decode_error(raw: bytes) -> None:
    with pytest.raises(PayloadDecodeError):
        decode_json(raw, Holder)
    with pytest.raises(PayloadDecodeError):
        decode_msgpack(b"\xc1", Holder)


def test_unsupported_types_are_reported() -> None:
    class Custom:
        pass

    with pytest.raises(TypeError, match="cannot encode"):
        encode_json(Custom())
    with pytest.raises(TypeError, match="cannot encode"):
        encode_msgpack(Custom())


def test_decoders_are_cached() -> None:
    assert json_decoder(User) is json_decoder(User)
