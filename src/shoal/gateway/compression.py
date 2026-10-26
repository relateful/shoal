"""Gateway transport compression (`zlib-stream` and `zstd-stream`).

One decompressor belongs to one connection: the stream context carries state across messages and
must be replaced, never reused, when the shard reconnects.

Discord: https://docs.discord.com/developers/events/gateway#transport-compression
"""

import importlib
import zlib
from types import ModuleType
from typing import TYPE_CHECKING, Final, Protocol, final, override

from shoal.core.errors import MissingDependencyError
from shoal.payloads.gateway import ZLIB_SUFFIX, TransportCompression

if TYPE_CHECKING:
    from collections.abc import Callable


class Decompressor(Protocol):
    """Turns websocket binary frames back into complete gateway messages."""

    __slots__ = ()

    def feed(self, data: bytes) -> bytes | None:
        """Add one frame; return the decompressed message once complete, else `None`."""
        ...


@final
class ZlibStreamDecompressor(Decompressor):
    """Buffers frames until `Z_SYNC_FLUSH`, then inflates them through one shared context.

    Discord: https://docs.discord.com/developers/events/gateway#zlib-stream
    """

    __slots__ = ("_buffer", "_inflator")

    def __init__(self) -> None:
        """Create a fresh inflate context for one connection."""
        self._inflator = zlib.decompressobj()
        self._buffer: bytearray = bytearray()

    @override
    def feed(self, data: bytes) -> bytes | None:
        self._buffer.extend(data)
        if not data.endswith(ZLIB_SUFFIX):
            return None
        message = self._inflator.decompress(self._buffer)
        self._buffer = bytearray()
        return message


class _ZstdStream(Protocol):
    __slots__ = ()

    def decompress(self, data: bytes) -> bytes: ...


_STDLIB_ZSTD: Final = "compression.zstd"
_THIRD_PARTY_ZSTD: Final = "zstandard"


def _import(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _zstd_stream() -> _ZstdStream:
    stdlib = _import(_STDLIB_ZSTD)
    if stdlib is not None:
        create_stdlib: Callable[[], _ZstdStream] = stdlib.ZstdDecompressor
        return create_stdlib()
    zstandard = _import(_THIRD_PARTY_ZSTD)
    if zstandard is None:
        feature = "zstd-stream gateway compression"
        raise MissingDependencyError(feature, "zstd")
    stream: _ZstdStream = zstandard.ZstdDecompressor().decompressobj()
    return stream


@final
class ZstdStreamDecompressor(Decompressor):
    """Feeds every frame through one zstd context that lives as long as the connection.

    Uses the standard library's `compression.zstd` on Python 3.14+, and the `zstandard` package
    (`pip install 'shoal[zstd]'`) before that.

    Discord: https://docs.discord.com/developers/events/gateway#zstd-stream
    """

    __slots__ = ("_stream",)

    def __init__(self) -> None:
        """Create a fresh zstd context for one connection.

        Raises:
            MissingDependencyError: Python is older than 3.14 and `zstandard` is not installed.
        """
        self._stream: _ZstdStream = _zstd_stream()

    @override
    def feed(self, data: bytes) -> bytes | None:
        # A frame that completes no output yields b"", which is not a message.
        return self._stream.decompress(data) or None


def create_decompressor(compression: TransportCompression | None) -> Decompressor | None:
    """Create the decompressor for a connection, or `None` when compression is off."""
    if compression is None:
        return None
    if compression is TransportCompression.ZSTD_STREAM:
        return ZstdStreamDecompressor()
    return ZlibStreamDecompressor()


def require_decompressor(compression: TransportCompression | None) -> None:
    """Fail now, not on the first connection, when `compression` cannot be decoded here.

    Raises:
        MissingDependencyError: zstd-stream was asked for but no zstd implementation is installed.
    """
    if compression is TransportCompression.ZSTD_STREAM and not zstd_available():
        feature = "zstd-stream gateway compression"
        raise MissingDependencyError(feature, "zstd")


def zstd_available() -> bool:
    """Whether zstd-stream can be used in this environment."""
    return _import(_STDLIB_ZSTD) is not None or _import(_THIRD_PARTY_ZSTD) is not None
