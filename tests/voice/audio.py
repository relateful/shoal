import asyncio
import sys
from pathlib import Path

import pytest

from shoal.core.ogg import OggError, OggOpusWriter
from shoal.payloads.voice_gateway import SILENCE_FRAME, EncryptionMode
from shoal.voice.audio import AudioPlayer, AudioSourceError, FFmpegSource, OggOpusSource
from shoal.voice.connection import VoiceConnection
from shoal.voice.crypto import TransportCipher
from tests.support.fakes import FakeClock, ManualClock, settle
from tests.support.voice import KEY, SERVER, FakeVoiceConnector, FakeVoiceTransports

FRAME = bytes([0xFC, 0x01, 0x02])


def ogg(*packets: bytes) -> bytes:
    writer = OggOpusWriter()
    data = writer.headers()
    for packet in packets:
        data += writer.packet(packet, 960)
    return data


async def connection(
    clock: FakeClock | ManualClock,
) -> tuple[VoiceConnection, FakeVoiceConnector, FakeVoiceTransports]:
    connector, transports = FakeVoiceConnector(), FakeVoiceTransports()
    voice = VoiceConnection(SERVER, user_id=1, connector=connector, transports=transports, clock=clock)
    await voice.connect()
    return voice, connector, transports


def frames(transports: FakeVoiceTransports) -> list[bytes]:
    opener = TransportCipher(EncryptionMode.AEAD_AES256_GCM_RTPSIZE, KEY)
    return [opener.unseal(packet)[1] for packet in transports.transports[0].audio()]


def playing(player: AudioPlayer) -> bool:
    """Read through a function: checkers narrow a property across the calls in between."""
    return player.is_playing


async def run_until(clock: ManualClock, done: "asyncio.Future[None]", *, step: float = 0.021) -> None:
    """Move the clock a little at a time until the playback ends."""
    for _ in range(1000):
        if done.done():
            return
        await clock.advance(step)
    msg = "the playback never ended"
    raise AssertionError(msg)


async def test_an_ogg_file_plays_in_real_time_then_falls_silent(tmp_path: Path) -> None:
    clock = ManualClock()
    voice, connector, transports = await connection(clock)
    path = tmp_path / "song.ogg"
    path.write_bytes(ogg(FRAME, FRAME, FRAME))
    started = clock.monotonic()
    player = AudioPlayer(lambda: voice, await OggOpusSource.from_path(path), clock=clock)
    await settle()
    assert frames(transports) == [FRAME]  # the next waits for its time
    await run_until(clock, player.done)
    assert frames(transports) == [FRAME] * 3 + [SILENCE_FRAME] * 5
    speaking = [message["d"] for message in connector.opened[0].sent if message["op"] == 5]
    assert [entry["speaking"] for entry in speaking if isinstance(entry, dict)] == [1, 0]
    # Three packets of 20 ms, each waited out; the closing silence goes out at once.
    assert 0.06 <= clock.monotonic() - started < 0.1
    assert not player.is_playing
    await voice.close()


async def test_playback_pauses_resumes_and_stops() -> None:
    clock = ManualClock()
    voice, _, transports = await connection(clock)
    player = AudioPlayer(lambda: voice, OggOpusSource(ogg(*[FRAME] * 100)), clock=clock)
    await settle()
    assert playing(player)
    player.pause()
    assert player.is_paused
    assert not playing(player)
    for _ in range(10):
        await clock.advance(0.021)
    sent = len(frames(transports))
    await clock.advance(1)
    assert len(frames(transports)) == sent  # nothing while paused
    assert frames(transports)[-1] == SILENCE_FRAME
    player.resume()
    await clock.advance(0.021)
    assert len(frames(transports)) > sent
    player.stop()
    await asyncio.wait({player.done})
    assert player.done.done()
    await voice.close()


async def test_audio_is_skipped_while_the_connection_is_away() -> None:
    clock = FakeClock()
    player = AudioPlayer(lambda: None, OggOpusSource(ogg(FRAME, FRAME)), clock=clock)
    await player.done
    assert [round(seconds, 3) for seconds in clock.sleeps] == [0.02, 0.02]  # still paced


def test_only_ogg_is_read() -> None:
    with pytest.raises(OggError):
        OggOpusSource(b"ID3 an mp3")


async def test_ffmpeg_output_is_streamed_as_it_encodes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    real = asyncio.create_subprocess_exec
    encoded = ogg(FRAME, FRAME)

    async def stand_in(
        program: str, *arguments: str, stdin: int, stdout: int, stderr: int
    ) -> asyncio.subprocess.Process:
        calls.append((program, *arguments))
        script = f"import sys; sys.stdout.buffer.write({encoded!r})"
        return await real(sys.executable, "-c", script, stdin=stdin, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", stand_in)
    source = FFmpegSource("song.mp3", before_options=["-ss", "30"], options=["-af", "volume=0.5"], bitrate=96)
    packets = [packet async for packet in source.packets()]
    assert packets == [FRAME, FRAME]
    program, *arguments = calls[0]
    assert program == "ffmpeg"
    assert arguments[arguments.index("-i") + 1] == "song.mp3"
    assert arguments.index("-ss") < arguments.index("-i") < arguments.index("-af")
    assert "96k" in arguments
    assert arguments[-3:] == ["-f", "ogg", "pipe:1"]


async def test_a_missing_ffmpeg_is_reported() -> None:
    source = FFmpegSource("song.mp3", executable="shoal-test-no-such-ffmpeg")
    with pytest.raises(FileNotFoundError):
        async for _ in source.packets():
            pass


async def test_a_new_connection_is_told_the_bot_speaks_before_its_audio() -> None:
    clock = ManualClock()
    first, first_connector, _ = await connection(clock)
    second, second_connector, second_transports = await connection(clock)
    current = [first]
    player = AudioPlayer(lambda: current[0], OggOpusSource(ogg(*[FRAME] * 100)), clock=clock)
    await settle()
    current[0] = second  # a rejoin or a move
    await clock.advance(0.021)
    assert [message["op"] for message in second_connector.opened[0].sent if message["op"] == 5] == [5]
    assert frames(second_transports) == [FRAME]
    assert any(message["op"] == 5 for message in first_connector.opened[0].sent)
    player.stop()
    await asyncio.wait({player.done})
    await first.close()
    await second.close()


async def test_a_stalled_loop_restarts_the_schedule_instead_of_bursting() -> None:
    clock = ManualClock()
    voice, _, transports = await connection(clock)
    player = AudioPlayer(lambda: voice, OggOpusSource(ogg(*[FRAME] * 100)), clock=clock)
    await settle()
    await clock.advance(1)  # fifty packets late
    # The late packet, then the next at once as the schedule starts over; the third waits its turn.
    assert len(frames(transports)) == 3
    player.stop()
    await asyncio.wait({player.done})
    await voice.close()


def scripted_ffmpeg(monkeypatch: pytest.MonkeyPatch, script: str) -> list[asyncio.subprocess.Process]:
    """Make `ffmpeg` a Python process running `script`; returns the processes started."""
    started: list[asyncio.subprocess.Process] = []
    real = asyncio.create_subprocess_exec

    async def stand_in(
        program: str, *arguments: str, stdin: int, stdout: int, stderr: int
    ) -> asyncio.subprocess.Process:
        del program, arguments
        process = await real(sys.executable, "-c", script, stdin=stdin, stdout=stdout, stderr=stderr)
        started.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", stand_in)
    return started


async def test_ffmpeg_failing_says_what_it_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    script = "import sys; print('song.mp3: Invalid data found', file=sys.stderr); sys.exit(1)"
    _ = scripted_ffmpeg(monkeypatch, script)
    with pytest.raises(AudioSourceError, match=r"ffmpeg exited with 1: song.mp3: Invalid data found"):
        async for _ in FFmpegSource("song.mp3").packets():
            pass


async def test_ffmpeg_is_stopped_when_playback_stops_early(monkeypatch: pytest.MonkeyPatch) -> None:
    encoded = ogg(FRAME)
    script = f"import sys, time; sys.stdout.buffer.write({encoded!r}); sys.stdout.flush(); time.sleep(60)"
    started = scripted_ffmpeg(monkeypatch, script)
    packets = FFmpegSource("song.mp3").packets()
    assert await anext(packets) == FRAME
    await packets.aclose()  # no error: stopping is not a failure
    assert started[0].returncode is not None
