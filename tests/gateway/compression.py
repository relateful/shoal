import pytest

from shoal.core.errors import MissingDependencyError
from shoal.gateway import compression
from shoal.gateway.compression import (
    ZlibStreamDecompressor,
    ZstdStreamDecompressor,
    create_decompressor,
    require_decompressor,
    zstd_available,
)
from shoal.payloads import TransportCompression
from tests.support.fakes import zlib_stream_frames


def test_zlib_stream_buffers_until_the_sync_flush() -> None:
    frames = zlib_stream_frames(b'{"op":10}', b'{"op":11}')
    decompressor = ZlibStreamDecompressor()
    first = frames[0]
    assert decompressor.feed(first[:5]) is None
    assert decompressor.feed(first[5:]) == b'{"op":10}'
    assert decompressor.feed(frames[1]) == b'{"op":11}'


def test_zstd_stream_shares_one_context_across_messages() -> None:
    zstandard = pytest.importorskip("zstandard")
    compressor = zstandard.ZstdCompressor().compressobj()
    decompressor = ZstdStreamDecompressor()
    for message in (b'{"op":10}', b'{"op":11,"d":null}'):
        frame = compressor.compress(message) + compressor.flush(zstandard.COMPRESSOBJ_FLUSH_BLOCK)
        assert decompressor.feed(frame) == message
    # The frame header alone completes nothing yet.
    header = compressor.compress(b'{"op":1}') + compressor.flush(zstandard.COMPRESSOBJ_FLUSH_BLOCK)
    assert decompressor.feed(header[:3]) is None
    assert decompressor.feed(header[3:]) == b'{"op":1}'


def test_create_decompressor() -> None:
    assert create_decompressor(None) is None
    assert isinstance(create_decompressor(TransportCompression.ZLIB_STREAM), ZlibStreamDecompressor)
    assert zstd_available()


def test_zstd_without_any_backend_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    def nothing_installed(name: str) -> None:
        del name

    monkeypatch.setattr(compression, "_import", nothing_installed)
    assert not zstd_available()
    with pytest.raises(MissingDependencyError, match=r"shoal\[zstd\]"):
        ZstdStreamDecompressor()
    with pytest.raises(MissingDependencyError, match=r"shoal\[zstd\]"):
        require_decompressor(TransportCompression.ZSTD_STREAM)
    require_decompressor(TransportCompression.ZLIB_STREAM)
    require_decompressor(None)
