import pytest

from shoal.payloads.voice_gateway import RTP_HEADER_SIZE
from shoal.voice.rtp import opus_samples, parse_rtp, rtp_header


def test_headers_carry_discords_version_and_payload_type() -> None:
    header = rtp_header(0xFFFF, 0x01020304, 42)
    assert len(header) == RTP_HEADER_SIZE
    assert header[:2] == b"\x80\x78"
    parsed = parse_rtp(header)
    assert (parsed.sequence, parsed.timestamp, parsed.ssrc, parsed.size, parsed.extension_size) == (
        0xFFFF,
        0x01020304,
        42,
        12,
        0,
    )


def test_csrcs_and_an_extension_preamble_are_part_of_the_header() -> None:
    header = bytes([0x92]) + rtp_header(1, 2, 3)[1:] + bytes(8) + b"\xbe\xde\x00\x02"
    parsed = parse_rtp(header)
    assert (parsed.size, parsed.extension_size) == (12 + 8 + 4, 8)
    with pytest.raises(ValueError, match="too short"):
        parse_rtp(header[:-2])
    with pytest.raises(ValueError, match="too short"):
        parse_rtp(b"\x80")


@pytest.mark.parametrize(
    ("packet", "samples"),
    [
        (bytes([0xF8, 0xFF, 0xFE]), 960),  # CELT 20 ms: Discord's silence frame
        (bytes([0x00 << 3]), 480),  # SILK 10 ms
        (bytes([0x03 << 3]), 2880),  # SILK 60 ms
        (bytes([(16 << 3) | 1]), 240),  # CELT 2.5 ms, two frames
        (bytes([(19 << 3) | 3, 0x83]), 2880),  # CELT 20 ms, code 3 with three frames
    ],
)
def test_a_packets_length_comes_from_its_toc(packet: bytes, samples: int) -> None:
    assert opus_samples(packet) == samples


def test_packets_without_what_their_toc_promises_are_refused() -> None:
    with pytest.raises(ValueError, match="TOC byte"):
        opus_samples(b"")
    with pytest.raises(ValueError, match="frame count"):
        opus_samples(bytes([(19 << 3) | 3]))
