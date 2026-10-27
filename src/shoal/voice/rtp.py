"""RTP headers of voice packets, and how long an Opus packet plays.

Discord: https://docs.discord.com/developers/topics/voice-connections#transport-encryption-modes-voice-packet-structure
RTP: https://www.rfc-editor.org/rfc/rfc3550#section-5.1
Opus packets: https://www.rfc-editor.org/rfc/rfc6716#section-3.1
"""

import struct
from dataclasses import dataclass
from typing import Final

from shoal.payloads.voice_gateway import (
    OPUS_SAMPLE_RATE,
    RTP_HEADER_SIZE,
    RTP_PAYLOAD_TYPE,
    RTP_VERSION_FLAGS,
)

_EXTENSION: Final = 0x10
"""The header-extension bit of the first byte."""

_FRAME_COUNT_MASK: Final = 0x3F
"""The frame count bits of a code 3 packet's second byte."""

_FRAME_SIZES: Final = (
    *(OPUS_SAMPLE_RATE // 100, OPUS_SAMPLE_RATE // 50, OPUS_SAMPLE_RATE // 25, OPUS_SAMPLE_RATE * 3 // 50)
    * 3,
    *(OPUS_SAMPLE_RATE // 100, OPUS_SAMPLE_RATE // 50) * 2,
    *(OPUS_SAMPLE_RATE // 400, OPUS_SAMPLE_RATE // 200, OPUS_SAMPLE_RATE // 100, OPUS_SAMPLE_RATE // 50) * 4,
)
"""Samples (48 kHz) per frame for each of the 32 configurations of an Opus TOC byte: SILK (10, 20, 40
and 60 ms, three bandwidths), Hybrid (10 and 20 ms, two), CELT (2.5, 5, 10 and 20 ms, four)."""


@dataclass(frozen=True, slots=True)
class RtpHeader:
    """What a received voice packet's header says.

    Attributes:
        sequence: The packet's sequence number.
        timestamp: Its timestamp, in samples at 48 kHz.
        ssrc: The sender's SSRC.
        size: Bytes of the unencrypted header (fixed part, CSRCs and the extension preamble).
        extension_size: Bytes of extension data at the start of the decrypted payload.
    """

    sequence: int
    timestamp: int
    ssrc: int
    size: int
    extension_size: int


def rtp_header(sequence: int, timestamp: int, ssrc: int) -> bytes:
    """The header of an outgoing voice packet."""
    return struct.pack(">BBHII", RTP_VERSION_FLAGS, RTP_PAYLOAD_TYPE, sequence, timestamp, ssrc)


def parse_rtp(packet: bytes) -> RtpHeader:
    """The header of a received voice packet.

    Raises:
        ValueError: The packet is shorter than its header says.
    """
    if len(packet) < RTP_HEADER_SIZE:
        msg = "a voice packet is too short"
        raise ValueError(msg)
    first, _, sequence, timestamp, ssrc = struct.unpack_from(">BBHII", packet)
    size = RTP_HEADER_SIZE + 4 * (first & 0x0F)
    extension_size = 0
    if first & _EXTENSION:
        # Only the 4-byte preamble is unencrypted; its length (in words) counts the encrypted data.
        if len(packet) < size + 4:
            msg = "a voice packet is too short"
            raise ValueError(msg)
        extension_size = 4 * int.from_bytes(packet[size + 2 : size + 4], "big")
        size += 4
    return RtpHeader(sequence, timestamp, ssrc, size, extension_size)


def opus_samples(packet: bytes) -> int:
    """How many samples (48 kHz) an Opus packet plays, from its TOC byte.

    Raises:
        ValueError: The packet is empty, or a code 3 packet lacks its frame count.
    """
    if not packet:
        msg = "an Opus packet has at least its TOC byte"
        raise ValueError(msg)
    toc = packet[0]
    per_frame = _FRAME_SIZES[toc >> 3]
    code = toc & 0x03
    if code == 0:
        return per_frame
    if code in (1, 2):
        return 2 * per_frame
    if len(packet) < 2:  # noqa: PLR2004 - the TOC byte and the frame count byte
        msg = "an Opus code 3 packet has a frame count byte"
        raise ValueError(msg)
    return (packet[1] & _FRAME_COUNT_MASK) * per_frame
