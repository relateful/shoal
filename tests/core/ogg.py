import pytest

from shoal.core.ogg import (
    OggError,
    OggOpusWriter,
    OggPacketReader,
    ogg_checksum,
    ogg_packets,
    ogg_pages,
    opus_pre_skip,
)


def reference_checksum(data: bytes) -> int:
    """The Ogg checksum bit by bit: polynomial 0x04C11DB7, not reflected, starting at zero."""
    crc = 0
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) if crc & 0x80000000 else crc << 1
            crc &= 0xFFFFFFFF
    return crc


def test_the_checksum_is_oggs() -> None:
    assert ogg_checksum(b"") == 0
    for data in (b"OggS", bytes(range(256)), b"\xff" * 1000):
        assert ogg_checksum(data) == reference_checksum(data)


def stream(*packets: bytes) -> bytes:
    writer = OggOpusWriter(serial=5)
    pages = writer.headers()
    for index, packet in enumerate(packets):
        pages += writer.packet(packet, 960, last=index == len(packets) - 1)
    return pages


def test_written_streams_read_back_with_valid_checksums() -> None:
    long_packet = bytes(range(256)) * 3  # spans several segments
    data = stream(b"\xfc\x01", long_packet, b"\xf8\xff\xfe")
    pages = list(ogg_pages(data))
    assert [page.granule for page in pages] == [0, 0, 960, 1920, 2880]
    packets = ogg_packets(data)
    assert packets[0].startswith(b"OpusHead")
    assert packets[1].startswith(b"OpusTags")
    assert packets[2:] == [b"\xfc\x01", long_packet, b"\xf8\xff\xfe"]
    assert opus_pre_skip(packets[0]) == 0
    # Every page's checksum is the checksum of the page with its own checksum zeroed.
    offset = 0
    for page in pages:
        size = 27 + len(page.segments) + len(page.body)
        raw = data[offset : offset + size]
        assert int.from_bytes(raw[22:26], "little") == ogg_checksum(raw[:22] + bytes(4) + raw[26:])
        offset += size


def test_a_stream_fed_in_pieces_gives_each_packet_once() -> None:
    data = stream(b"\xfc\x01", b"\xfc\x02" * 200)
    reader = OggPacketReader()
    packets: list[bytes] = []
    for start in range(0, len(data), 7):
        packets.extend(reader.feed(data[start : start + 7]))
    assert packets[2:] == [b"\xfc\x01", b"\xfc\x02" * 200]
    assert not reader.pending


def test_a_packet_continued_on_the_next_page_is_joined() -> None:
    def page(body: bytes, segments: bytes, *, continued: bool) -> bytes:
        header = b"OggS" + bytes([0, 1 if continued else 0]) + bytes(8) + bytes(12) + bytes([len(segments)])
        return header + segments + body

    first = page(b"a" * 255, b"\xff", continued=False)
    second = page(b"bc", b"\x02", continued=True)
    assert ogg_packets(first + second) == [b"a" * 255 + b"bc"]


def test_what_is_not_a_complete_ogg_stream_is_refused() -> None:
    with pytest.raises(OggError, match="not an Ogg stream"):
        ogg_packets(b"RIFF....")
    with pytest.raises(OggError, match="cut short"):
        ogg_packets(stream(b"\xfc\x01")[:-1])
    with pytest.raises(OggError, match="cut short"):
        list(ogg_pages(b"OggS"))
    with pytest.raises(OggError, match="not an Ogg Opus stream"):
        opus_pre_skip(b"OpusTags")
    with pytest.raises(OggError, match="headers before"):
        OggOpusWriter().packet(b"\xfc", 960)
    writer = OggOpusWriter()
    _ = writer.headers()
    with pytest.raises(OggError, match="more than one page"):
        writer.packet(bytes(255 * 256), 960)


def test_a_packet_larger_than_a_reader_accepts_is_refused() -> None:
    # Pages of 255 full segments, each continuing the packet before: a packet that never ends.
    page = b"OggS" + bytes([0, 1]) + bytes(8) + bytes(12) + bytes([255]) + b"\xff" * 255 + bytes(255 * 255)
    reader = OggPacketReader()
    for _ in range(258):  # 258 pages of 65,025 bytes: just under 16 MiB
        assert reader.feed(page) == []
    with pytest.raises(OggError, match="larger than this reader accepts"):
        reader.feed(page)
