from collections.abc import AsyncIterator, Iterable

from shoal.core.metrics import VOICE_FRAMES_CONCEALED, VOICE_PACKETS_DROPPED, InMemoryMetrics
from shoal.payloads.voice_gateway import SILENCE_FRAME
from shoal.voice.connection import VoicePacket
from shoal.voice.defaults import MAX_CONCEALED, REORDER_DEPTH
from shoal.voice.receive.opus import OpusDecoder
from shoal.voice.receive.stream import AudioFrame, Reorderer, decode_audio
from tests.support.voice import FakeOpus


def packet(sequence: int, *, user_id: int = 99, ssrc: int = 55, value: int | None = None) -> VoicePacket:
    opus = bytes([0xFC, sequence % 100 if value is None else value])
    return VoicePacket(user_id, ssrc, sequence % 0x10000, sequence * 960 % 0x100000000, opus)


def silence(*, ssrc: int = 55) -> VoicePacket:
    return VoicePacket(99, ssrc, 0, 0, SILENCE_FRAME)


def sequences(played: Iterable[VoicePacket | None] | None) -> list[int | None]:
    assert played is not None
    return [None if item is None else item.sequence for item in played]


def test_packets_in_order_play_at_once() -> None:
    reorderer = Reorderer()
    assert [sequences(reorderer.push(packet(n))) for n in (5, 6)] == [[5], [6]]


def test_a_late_packet_is_put_back_in_place() -> None:
    reorderer = Reorderer()
    assert sequences(reorderer.push(packet(1))) == [1]
    assert sequences(reorderer.push(packet(3))) == []
    assert sequences(reorderer.push(packet(2))) == [2, 3]


def test_a_packet_still_missing_past_the_depth_is_lost() -> None:
    reorderer = Reorderer()
    _ = reorderer.push(packet(1))
    for n in range(3, 3 + REORDER_DEPTH):
        assert sequences(reorderer.push(packet(n))) == []
    assert sequences(reorderer.push(packet(3 + REORDER_DEPTH))) == [None, *range(3, 4 + REORDER_DEPTH)]
    # Too late now: its place was played.
    assert reorderer.push(packet(2)) is None


def test_duplicates_and_old_packets_are_refused() -> None:
    reorderer = Reorderer()
    _ = reorderer.push(packet(10))
    _ = reorderer.push(packet(12))
    assert reorderer.push(packet(12)) is None
    assert reorderer.push(packet(9)) is None


def test_sequence_numbers_wrap() -> None:
    reorderer = Reorderer()
    assert sequences(reorderer.push(packet(0xFFFF))) == [0xFFFF]
    assert sequences(reorderer.push(packet(0x10001))) == []
    assert sequences(reorderer.push(packet(0x10000))) == [0, 1]


def test_a_long_jump_marks_a_bounded_gap() -> None:
    reorderer = Reorderer(depth=0)
    _ = reorderer.push(packet(1))
    played = sequences(reorderer.push(packet(30000)))
    assert played == [None] * (MAX_CONCEALED + 1) + [30000]


def test_flushing_plays_what_is_held_with_its_gaps() -> None:
    reorderer = Reorderer()
    _ = reorderer.push(packet(1))
    _ = reorderer.push(packet(3))
    _ = reorderer.push(packet(4))
    assert sequences(reorderer.flush()) == [None, 3, 4]
    assert reorderer.flush() == []
    # It starts over: the next packet plays at once, whatever its number.
    assert sequences(reorderer.push(packet(100))) == [100]


async def stream(*packets: VoicePacket) -> AsyncIterator[VoicePacket]:
    for item in packets:
        yield item


def values(frames: list[AudioFrame]) -> list[tuple[int, int, bool]]:
    return [(frame.user_id, frame.pcm[0], frame.concealed) for frame in frames]


async def decoded(
    *packets: VoicePacket, library: FakeOpus | None = None, metrics: InMemoryMetrics | None = None
) -> list[AudioFrame]:
    library = library or FakeOpus()
    return [
        frame
        async for frame in decode_audio(
            stream(*packets), decoders=lambda: OpusDecoder(library=library), metrics=metrics
        )
    ]


async def test_each_sender_is_decoded_in_order() -> None:
    frames = await decoded(
        packet(1), packet(5, user_id=7, ssrc=66), packet(3), packet(2), packet(6, user_id=7, ssrc=66)
    )
    assert values(frames) == [(99, 1, False), (7, 5, False), (99, 2, False), (99, 3, False), (7, 6, False)]


async def test_a_loss_is_concealed_and_the_last_one_rebuilt_from_the_next_packet() -> None:
    metrics = InMemoryMetrics()
    lost_two = [packet(1), *(packet(n) for n in range(4, 5 + REORDER_DEPTH))]
    frames = await decoded(*lost_two, metrics=metrics)
    assert values(frames)[:4] == [(99, 1, False), (99, 0, True), (99, 104, True), (99, 4, False)]
    # Stand-ins carry the timestamps of the packets they replace.
    assert [frame.timestamp for frame in frames[1:3]] == [2 * 960, 3 * 960]
    assert metrics.counters[InMemoryMetrics.key(VOICE_FRAMES_CONCEALED, {})] == 2


async def test_a_pause_longer_than_concealment_is_left_silent() -> None:
    frames = await decoded(packet(1), packet(3 + MAX_CONCEALED), silence())
    assert values(frames) == [(99, 1, False), (99, (3 + MAX_CONCEALED) % 100, False)]


async def test_a_late_packet_is_counted_dropped() -> None:
    metrics = InMemoryMetrics()
    frames = await decoded(*(packet(n) for n in range(1, 6 + REORDER_DEPTH)), packet(2), metrics=metrics)
    assert len(frames) == 5 + REORDER_DEPTH
    assert metrics.counters[InMemoryMetrics.key(VOICE_PACKETS_DROPPED, {"reason": "late"})] == 1


async def test_silence_ends_a_stream_and_frees_its_decoder() -> None:
    library = FakeOpus()
    frames = await decoded(packet(1), packet(3), silence(), silence(), packet(9), library=library)
    # What was held played out at the silence; the next words start a new stream.
    assert values(frames) == [(99, 1, False), (99, 103, True), (99, 3, False), (99, 9, False)]
    assert library.created == 2
    assert library.destroyed == [1, 2]


async def test_a_new_user_on_a_reused_stream_gets_a_new_decoder() -> None:
    library = FakeOpus()
    frames = await decoded(packet(1), packet(2, user_id=8), library=library)
    assert [frame.user_id for frame in frames] == [99, 8]
    assert library.created == 2


async def test_a_corrupt_packet_is_dropped_and_others_keep_coming() -> None:
    metrics = InMemoryMetrics()
    empty = VoicePacket(99, 55, 2, 1920, b"")
    frames = await decoded(packet(1), empty, packet(3), packet(1, user_id=7, ssrc=66), metrics=metrics)
    assert values(frames) == [(99, 1, False), (99, 3, False), (7, 1, False)]
    dropped = InMemoryMetrics.key(VOICE_PACKETS_DROPPED, {"reason": "undecodable"})
    assert metrics.counters[dropped] == 1


async def test_a_stream_taken_by_another_user_frees_the_old_decoder() -> None:
    library = FakeOpus()
    _ = await decoded(packet(1), packet(2, user_id=8), library=library)
    assert 1 in library.destroyed
