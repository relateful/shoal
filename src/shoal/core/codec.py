"""The one place Shoal turns bytes into typed objects and back.

Everything goes through msgspec with Shoal's hooks, which teach it two Discord conventions:

- Snowflakes arrive as decimal strings and become `Snowflake`. They are written back as strings in
  JSON (what Discord expects) and as integers in msgpack (smaller cache snapshots).
- Bitfields arrive as integers, or as strings for permissions, and become `BaseFlags` subclasses.

Decoders are cached per type, because building one is far more expensive than using it.
"""

from typing import Final, cast

import msgspec

from shoal.core.errors import ShoalError
from shoal.core.flags import BaseFlags
from shoal.core.snowflake import Snowflake


class PayloadDecodeError(ShoalError):
    """Bytes from Discord (or a cache snapshot) did not match the expected type."""

    def __init__(self, target: object, reason: str) -> None:
        """Describe which type failed to decode and why."""
        super().__init__(f"could not decode {target!r}: {reason}")
        self.target: object = target
        self.reason: str = reason


def _dec_hook(target: type, value: object) -> object:
    if issubclass(target, Snowflake):
        if isinstance(value, str | int) and not isinstance(value, bool):
            return target(value)
        msg = f"expected a snowflake string, got {type(value).__name__}"
        raise TypeError(msg)
    if issubclass(target, BaseFlags):
        if isinstance(value, str | int) and not isinstance(value, bool):
            return target(value)
        msg = f"expected a {target.__name__} bitfield, got {type(value).__name__}"
        raise TypeError(msg)
    msg = f"Shoal has no decoder for {target!r}"
    raise NotImplementedError(msg)


def _json_enc_hook(value: object) -> object:
    if isinstance(value, Snowflake):
        return str(int(value))
    if isinstance(value, BaseFlags):
        return str(int(value)) if value.WIRE_AS_STRING else int(value)
    msg = f"Shoal cannot encode {type(value).__name__} to JSON"
    raise TypeError(msg)


def _msgpack_enc_hook(value: object) -> object:
    if isinstance(value, Snowflake | BaseFlags):
        return int(value)
    msg = f"Shoal cannot encode {type(value).__name__} to msgpack"
    raise TypeError(msg)


_JSON_ENCODER: Final = msgspec.json.Encoder(enc_hook=_json_enc_hook)
_MSGPACK_ENCODER: Final = msgspec.msgpack.Encoder(enc_hook=_msgpack_enc_hook)
_json_decoders: dict[object, msgspec.json.Decoder[object]] = {}
"""One decoder per target type; bounded by the number of types in the program."""
_msgpack_decoders: dict[object, msgspec.msgpack.Decoder[object]] = {}


def json_decoder[T](target: type[T]) -> msgspec.json.Decoder[T]:
    """Return the cached JSON decoder for `target`."""
    cached = _json_decoders.get(target)
    if cached is not None:
        return cast(
            "msgspec.json.Decoder[T]", cached
        )  # each cached decoder was built for exactly this target
    decoder = msgspec.json.Decoder(target, dec_hook=_dec_hook)
    _json_decoders[target] = cast(
        "msgspec.json.Decoder[object]", decoder
    )  # the cache holds decoders of many targets
    return decoder


def msgpack_decoder[T](target: type[T]) -> msgspec.msgpack.Decoder[T]:
    """Return the cached msgpack decoder for `target`."""
    cached = _msgpack_decoders.get(target)
    if cached is not None:
        return cast(
            "msgspec.msgpack.Decoder[T]", cached
        )  # each cached decoder was built for exactly this target
    decoder = msgspec.msgpack.Decoder(target, dec_hook=_dec_hook)
    _msgpack_decoders[target] = cast(
        "msgspec.msgpack.Decoder[object]", decoder
    )  # the cache holds decoders of many targets
    return decoder


def decode_json[T](data: bytes | bytearray | memoryview | str, target: type[T]) -> T:
    """Decode Discord JSON into `target`.

    Raises:
        PayloadDecodeError: The JSON is malformed or does not match `target`.
    """
    try:
        return json_decoder(target).decode(data)
    except msgspec.DecodeError as error:
        raise PayloadDecodeError(target, str(error)) from error


def decode_msgpack[T](data: bytes | bytearray | memoryview, target: type[T]) -> T:
    """Decode a Shoal msgpack blob (cache snapshots, session files) into `target`.

    Raises:
        PayloadDecodeError: The data is malformed or does not match `target`.
    """
    try:
        return msgpack_decoder(target).decode(data)
    except msgspec.DecodeError as error:
        raise PayloadDecodeError(target, str(error)) from error


def encode_json(value: object) -> bytes:
    """Encode a payload as Discord expects it (snowflakes and permissions as strings).

    Raises:
        TypeError: `value` contains a type Shoal cannot encode.
    """
    return _JSON_ENCODER.encode(value)


def encode_msgpack(value: object) -> bytes:
    """Encode a value compactly for Shoal's own storage.

    Raises:
        TypeError: `value` contains a type Shoal cannot encode.
    """
    return _MSGPACK_ENCODER.encode(value)
