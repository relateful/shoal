"""Ogg, the container Discord's clients record Opus voice in: reading pages and packets, and writing them.

An Ogg stream is a run of pages. Each page carries segments of up to 255 bytes; a segment shorter than
255 ends a packet, so one packet can span pages. An Opus stream starts with an `OpusHead` and an
`OpusTags` packet, then one Opus packet per audio frame.

Ogg: https://www.rfc-editor.org/rfc/rfc3533
Opus in Ogg: https://www.rfc-editor.org/rfc/rfc7845
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final, final

from shoal.core.errors import ShoalError

OPUS_HEAD: Final = b"OpusHead"
"""What the Opus identification header starts with; its pre-skip is at offset 10."""

OPUS_TAGS: Final = b"OpusTags"
"""What the Opus comment header starts with."""

_CONTINUED: Final = 0x01
"""Header type flag: the page's first packet continues one from the previous page."""

_CRC_POLYNOMIAL: Final = 0x04C11DB7
"""The Ogg checksum's polynomial (not bit-reflected, unlike zlib's CRC-32)."""

_FIRST_PAGE: Final = 0x02
"""Header type flag: the first page of a stream."""

_HEADER_SIZE: Final = 27
"""Bytes in a page header up to and including its segment count."""

_LAST_PAGE: Final = 0x04
"""Header type flag: the last page of a stream."""

_MAX_PACKET: Final = 16 * 1024 * 1024
"""The largest packet a reader reassembles (cover art in `OpusTags` can be large); a stream that
claims a bigger one is refused rather than buffered without end."""


_MAX_SEGMENTS: Final = 255
"""Segments one page can carry."""

_OPUS_HEAD_SIZE: Final = 19
"""Bytes in the fixed part of an `OpusHead`."""

_PAGE: Final = b"OggS"
"""What every page starts with."""

_SEGMENT: Final = 255
"""The largest segment; a shorter one ends its packet."""


def _crc_table() -> tuple[int, ...]:
    table: list[int] = []
    for byte in range(256):
        crc = byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ _CRC_POLYNOMIAL) if crc & 0x80000000 else (crc << 1)
        table.append(crc & 0xFFFFFFFF)
    return tuple(table)


_CRC_TABLE: Final = _crc_table()
"""The Ogg checksum by leading byte."""


class OggError(ShoalError, ValueError):
    """The bytes are not an Ogg stream, or not one this reader can follow."""


@dataclass(frozen=True, slots=True)
class OggPage:
    """One page: its granule position (samples at 48 kHz for Opus), its segment sizes and its body."""

    granule: int
    continued: bool
    segments: bytes
    body: bytes


def ogg_checksum(data: bytes) -> int:
    """The checksum of a page, computed with its own checksum field set to zero."""
    crc = 0
    for byte in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ _CRC_TABLE[(crc >> 24) ^ byte]
    return crc


def ogg_pages(data: bytes) -> Iterator[OggPage]:
    """Every page of a complete stream, walking the headers (audio bytes can spell `OggS`).

    Raises:
        OggError: A page does not start where the previous one ended, or is cut short.
    """
    offset = 0
    while offset < len(data):
        page, offset = _page_at(data, offset)
        if page is None:
            msg = "the Ogg stream is cut short"
            raise OggError(msg)
        yield page


def _page_at(data: bytes, offset: int) -> tuple[OggPage | None, int]:
    """The page at `offset` and where the next starts, or `None` when `data` ends within it.

    Raises:
        OggError: `data` has no page at `offset`.
    """
    header_end = offset + _HEADER_SIZE
    if len(data) < header_end:
        if not _PAGE.startswith(data[offset : offset + len(_PAGE)]):
            msg = "not an Ogg stream"
            raise OggError(msg)
        return None, offset
    if not data.startswith(_PAGE, offset):
        msg = "not an Ogg stream"
        raise OggError(msg)
    segments_end = header_end + data[header_end - 1]
    if len(data) < segments_end:
        return None, offset
    segments = data[header_end:segments_end]
    body_end = segments_end + sum(segments)
    if len(data) < body_end:
        return None, offset
    page = OggPage(
        granule=int.from_bytes(data[offset + 6 : offset + 14], "little", signed=True),
        continued=bool(data[offset + 5] & _CONTINUED),
        segments=segments,
        body=data[segments_end:body_end],
    )
    return page, body_end


@final
class OggPacketReader:
    """Reassembles packets from a stream fed in pieces, such as a pipe from an encoder.

    `feed` takes whatever bytes arrived and returns the packets they completed, in order.
    """

    __slots__ = ("_buffer", "_partial")

    def __init__(self) -> None:
        """Create a reader at the start of a stream."""
        self._buffer: bytearray = bytearray()
        self._partial: bytearray = bytearray()

    @property
    def pending(self) -> bool:
        """Whether bytes were fed that complete no packet yet."""
        return bool(self._buffer or self._partial)

    def feed(self, data: bytes) -> list[bytes]:
        """Add bytes of the stream; return the packets they complete.

        Raises:
            OggError: The bytes are not an Ogg stream.
        """
        self._buffer.extend(data)
        buffer = bytes(self._buffer)
        packets: list[bytes] = []
        offset = 0
        while True:
            page, after = _page_at(buffer, offset)
            if page is None:
                break
            offset = after
            if not page.continued:
                self._partial.clear()
            position = 0
            for size in page.segments:
                self._partial.extend(page.body[position : position + size])
                position += size
                if len(self._partial) > _MAX_PACKET:
                    msg = "an Ogg packet is larger than this reader accepts"
                    raise OggError(msg)
                if size < _SEGMENT:
                    packets.append(bytes(self._partial))
                    self._partial.clear()
        del self._buffer[:offset]
        return packets


def ogg_packets(data: bytes) -> list[bytes]:
    """Every packet of a complete stream.

    Raises:
        OggError: `data` is not a complete Ogg stream.
    """
    reader = OggPacketReader()
    packets = reader.feed(data)
    if reader.pending:
        msg = "the Ogg stream is cut short"
        raise OggError(msg)
    return packets


def opus_pre_skip(head: bytes) -> int:
    """The samples an Opus decoder drops at the start, from the `OpusHead` packet.

    Raises:
        OggError: `head` is not an `OpusHead`.
    """
    if not head.startswith(OPUS_HEAD) or len(head) < _OPUS_HEAD_SIZE:
        msg = "not an Ogg Opus stream"
        raise OggError(msg)
    return int.from_bytes(head[10:12], "little")


@final
class OggOpusWriter:
    """Writes Opus packets as an Ogg Opus stream: one packet per page, stereo, 48 kHz.

    Args:
        serial: The stream's serial number.
    """

    __slots__ = ("_granule", "_sequence", "_serial", "_started")

    def __init__(self, serial: int = 1) -> None:
        """Create a writer; see the class docstring for the arguments."""
        self._serial: int = serial
        self._sequence: int = 0
        self._granule: int = 0
        self._started: bool = False

    def headers(self) -> bytes:
        """The `OpusHead` and `OpusTags` pages every stream starts with."""
        head = (
            OPUS_HEAD + bytes([1, 2]) + (0).to_bytes(2, "little") + (48_000).to_bytes(4, "little") + bytes(3)
        )
        vendor = b"shoal"
        tags = OPUS_TAGS + len(vendor).to_bytes(4, "little") + vendor + (0).to_bytes(4, "little")
        self._started = True
        return self._page(head, 0, first=True) + self._page(tags, 0)

    def packet(self, packet: bytes, samples: int, *, last: bool = False) -> bytes:
        """The page carrying one Opus packet of `samples` samples (48 kHz).

        Raises:
            OggError: `headers` was not written first, or the packet needs more than one page.
        """
        if not self._started:
            msg = "write the headers before the first packet"
            raise OggError(msg)
        self._granule += samples
        return self._page(packet, self._granule, last=last)

    def _page(self, packet: bytes, granule: int, *, first: bool = False, last: bool = False) -> bytes:
        full, rest = divmod(len(packet), _SEGMENT)
        segments = bytes([_SEGMENT] * full + [rest])
        if len(segments) > _MAX_SEGMENTS:
            msg = "a packet this large needs more than one page"
            raise OggError(msg)
        kind = (_FIRST_PAGE if first else 0) | (_LAST_PAGE if last else 0)
        header = (
            _PAGE
            + bytes([0, kind])
            + granule.to_bytes(8, "little", signed=True)
            + self._serial.to_bytes(4, "little")
            + self._sequence.to_bytes(4, "little")
        )
        self._sequence += 1
        unsigned = header + bytes(4) + bytes([len(segments)]) + segments + packet
        checksum = ogg_checksum(unsigned).to_bytes(4, "little")
        return header + checksum + bytes([len(segments)]) + segments + packet
