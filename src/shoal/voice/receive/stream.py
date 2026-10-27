"""Received packets to audio: per-sender ordering, loss concealment and decoding.

UDP delivers packets late, twice, or not at all. Each sender's stream (one SSRC) holds up to
`REORDER_DEPTH` packets to put late ones back in order; a packet still missing once more than that
have arrived after it is lost, and is concealed (rebuilt from the next packet's error correction
data when the sender sent it). A packet older than what was already played is dropped.

Discord ends what someone says with silence frames. The first one ends the stream: what is held is
played out and its decoder freed, so a call of many speakers keeps state only for who is talking.
"""

from collections.abc import AsyncIterable, AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Final, final

from shoal.core.metrics import VOICE_FRAMES_CONCEALED, VOICE_PACKETS_DROPPED, Metrics, NoopMetrics
from shoal.payloads.voice_gateway import SILENCE_FRAME
from shoal.voice.connection import VoicePacket
from shoal.voice.defaults import MAX_CONCEALED, REORDER_DEPTH
from shoal.voice.receive.opus import CHANNELS, SAMPLE_WIDTH, OpusDecoder, OpusError

_SEQUENCES: Final = 0x10000
"""RTP sequence numbers wrap at 16 bits."""

_HALF: Final = _SEQUENCES // 2
"""A sequence number more than this behind another counts as after it, wrapped."""

_TIMESTAMPS: Final = 0x100000000
"""RTP timestamps wrap at 32 bits."""

_PCM_BYTES_PER_SAMPLE: Final = CHANNELS * SAMPLE_WIDTH
"""Bytes of decoded PCM per sample (both channels)."""


@dataclass(frozen=True, slots=True)
class AudioFrame:
    """One packet's audio from someone in the call.

    Attributes:
        user_id: Who said it.
        ssrc: Their audio stream.
        timestamp: The RTP timestamp, in samples at 48 kHz.
        pcm: 48 kHz stereo PCM, signed 16-bit little-endian, interleaved. Left out of the repr.
        concealed: Stands in for a lost packet, rebuilt or concealed by the decoder.
    """

    user_id: int
    ssrc: int
    timestamp: int
    pcm: bytes = field(repr=False)
    concealed: bool = False


@final
class Reorderer:
    """Puts one stream's packets back in sequence order; `None` marks a lost packet.

    Args:
        depth: Packets held for a late one before it is taken for lost.
    """

    __slots__ = ("_depth", "_expected", "_held")

    def __init__(self, depth: int = REORDER_DEPTH) -> None:
        """Create an empty reorderer."""
        self._depth: int = depth
        self._expected: int | None = None
        self._held: dict[int, VoicePacket] = {}

    def push(self, packet: VoicePacket) -> list[VoicePacket | None] | None:
        """Take a packet; what can be played now, in order. `None` when it came too late."""
        if self._expected is None:
            self._expected = packet.sequence
        ahead = (packet.sequence - self._expected) % _SEQUENCES
        if ahead >= _HALF or packet.sequence in self._held:
            return None
        self._held[packet.sequence] = packet
        return self._play(self._depth)

    def flush(self) -> list[VoicePacket | None]:
        """Everything held, in order, with the gaps between marked lost; the reorderer starts over."""
        played = self._play(0)
        self._expected = None
        return played

    def _play(self, depth: int) -> list[VoicePacket | None]:
        """Play what is in order, skipping a gap once more than `depth` packets wait behind it.

        A gap is marked by one `None` per lost packet, up to `MAX_CONCEALED + 1`: anything longer
        is a pause, and a sequence jump of thousands costs no more than a short one.
        """
        played: list[VoicePacket | None] = []
        expected = self._expected
        while self._held and expected is not None:
            next_packet = self._held.pop(expected, None)
            if next_packet is not None:
                played.append(next_packet)
                expected = (expected + 1) % _SEQUENCES
                continue
            if len(self._held) <= depth:
                break
            gap = min((sequence - expected) % _SEQUENCES for sequence in self._held)
            played += [None] * min(gap, MAX_CONCEALED + 1)
            expected = (expected + gap) % _SEQUENCES
        self._expected = expected
        return played


@final
class _Stream:
    __slots__ = ("decoder", "reorderer", "user_id")

    def __init__(self, user_id: int, decoder: OpusDecoder) -> None:
        self.user_id: int = user_id
        self.decoder: OpusDecoder = decoder
        self.reorderer: Reorderer = Reorderer()


async def decode_audio(
    packets: AsyncIterable[VoicePacket],
    *,
    decoders: Callable[[], OpusDecoder] = OpusDecoder,
    metrics: Metrics | None = None,
) -> AsyncIterator[AudioFrame]:
    """Decode received packets (`VoiceClient.listen`, `VoiceConnection.packets`) to audio.

    Frames come out per sender in order; different senders' frames interleave as they arrive.

    Args:
        packets: The received packets.
        decoders: Makes one decoder per stream; tests pass a fake.
        metrics: Receives `shoal_voice_frames_concealed_total` and late packets as dropped (`late`).

    Raises:
        OpusError: libopus is missing.
    """
    metrics = metrics or NoopMetrics()
    streams: dict[int, _Stream] = {}
    try:
        async for packet in packets:
            stream = streams.get(packet.ssrc)
            if packet.opus == SILENCE_FRAME:
                if stream is not None:
                    del streams[packet.ssrc]
                    for frame in _play(stream, stream.reorderer.flush(), metrics):
                        yield frame
                    stream.decoder.close()
                continue
            if stream is None or stream.user_id != packet.user_id:
                if stream is not None:
                    stream.decoder.close()  # the stream now carries someone else
                stream = streams[packet.ssrc] = _Stream(packet.user_id, decoders())
            played = stream.reorderer.push(packet)
            if played is None:
                metrics.increment(VOICE_PACKETS_DROPPED, {"reason": "late"})
                continue
            for frame in _play(stream, played, metrics):
                yield frame
        for stream in list(streams.values()):
            for frame in _play(stream, stream.reorderer.flush(), metrics):
                yield frame
    finally:
        for stream in streams.values():
            stream.decoder.close()


def _play(stream: _Stream, played: list[VoicePacket | None], metrics: Metrics) -> list[AudioFrame]:
    frames: list[AudioFrame] = []
    lost = 0
    for packet in played:
        if packet is None:
            lost += 1
            continue
        try:
            if lost:
                frames += _conceal(stream, packet, lost, metrics)
            pcm = stream.decoder.decode(packet.opus)
        except (OpusError, ValueError):
            # One sender's corrupt packet (or one without a TOC byte) is dropped, not everyone's audio.
            metrics.increment(VOICE_PACKETS_DROPPED, {"reason": "undecodable"})
            continue
        finally:
            lost = 0
        frames.append(AudioFrame(stream.user_id, packet.ssrc, packet.timestamp, pcm))
    return frames


def _conceal(stream: _Stream, after: VoicePacket, lost: int, metrics: Metrics) -> list[AudioFrame]:
    """Stand-ins for the `lost` packets before `after`; a long gap is a pause, not a loss."""
    if lost > MAX_CONCEALED:
        return []
    frames: list[AudioFrame] = []
    for gap in range(lost, 0, -1):
        # Only the packet just before `after` can be rebuilt from `after`'s error correction data.
        pcm = stream.decoder.conceal(after.opus if gap == 1 else None)
        timestamp = (after.timestamp - gap * len(pcm) // _PCM_BYTES_PER_SAMPLE) % _TIMESTAMPS
        frames.append(AudioFrame(stream.user_id, after.ssrc, timestamp, pcm, concealed=True))
        metrics.increment(VOICE_FRAMES_CONCEALED)
    return frames
