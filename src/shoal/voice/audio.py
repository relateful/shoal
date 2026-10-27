"""What a voice connection plays: Opus packets from a file or an encoder, paced in real time.

    player = AudioPlayer(lambda: connection, OggOpusSource(data))
    await player.done

An `AudioSource` yields Opus packets (48 kHz; Discord expects stereo). `OggOpusSource` reads Ogg Opus,
what Discord's own clients record; `FFmpegSource` encodes anything `ffmpeg` reads, streaming as it
encodes, so a long file or a stream starts at once. Shoal needs no audio library for either: the
packets go out as encoded.

Discord: https://docs.discord.com/developers/topics/voice-connections#transport-encryption-and-sending-voice
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator, Callable, Sequence
from pathlib import Path
from typing import Final, Protocol, final, override

from shoal.core.clock import Clock, SystemClock
from shoal.core.errors import ShoalError
from shoal.core.ogg import OPUS_HEAD, OPUS_TAGS, OggPacketReader, ogg_packets
from shoal.payloads.voice_gateway import (
    OPUS_CHANNELS,
    OPUS_SAMPLE_RATE,
    SILENCE_FRAME,
    SILENCE_FRAMES_AFTER_AUDIO,
    SpeakingFlags,
)
from shoal.voice.connection import VoiceConnection, VoiceConnectionClosedError
from shoal.voice.defaults import PLAYBACK_MAX_LAG
from shoal.voice.rtp import opus_samples

_log = logging.getLogger("shoal.voice")

_READ_SIZE: Final = 64 * 1024
"""Bytes read from the encoder at a time."""

_SILENCE_SAMPLES: Final = OPUS_SAMPLE_RATE // 50
"""Samples one silence frame stands for: 20 ms."""


class AudioSource(Protocol):
    """Opus packets to play, in order."""

    __slots__ = ()

    def packets(self) -> AsyncGenerator[bytes]:
        """Yield the packets; closing the iteration releases whatever produces them."""
        ...


def _audio(packets: Sequence[bytes]) -> list[bytes]:
    """The audio packets of an Ogg Opus stream: everything after its two header packets."""
    return [packet for packet in packets if not packet.startswith((OPUS_HEAD, OPUS_TAGS))]


@final
class OggOpusSource(AudioSource):
    """Plays an Ogg Opus file held in memory.

    Args:
        data: The file's bytes.

    Raises:
        OggError: `data` is not a complete Ogg stream.
    """

    __slots__ = ("_packets",)

    def __init__(self, data: bytes) -> None:
        """Read the packets; see the class docstring for the arguments."""
        self._packets: list[bytes] = _audio(ogg_packets(data))

    @classmethod
    async def from_path(cls, path: str | Path) -> "OggOpusSource":
        """Read a file in a worker thread, so the event loop never waits on the disk.

        Raises:
            OSError: The file could not be read.
            OggError: It is not a complete Ogg stream.
        """
        return cls(await asyncio.to_thread(Path(path).read_bytes))

    @override
    async def packets(self) -> AsyncGenerator[bytes]:
        for packet in self._packets:
            yield packet


class AudioSourceError(ShoalError):
    """A source could not produce its audio, such as `ffmpeg` failing on its input."""


@final
class FFmpegSource(AudioSource):
    """Plays anything `ffmpeg` reads, encoded to Opus as it plays.

    Args:
        source: What `ffmpeg` reads: a path or a URL. Anything `ffmpeg` can open is opened (local
            files, internal addresses), so never pass a user's input unchecked: allow-list what a
            user may play, or restrict the protocols (`before_options=["-protocol_whitelist",
            "https,tls,tcp"]`).
        executable: The `ffmpeg` program.
        before_options: Arguments before `-i` (`["-ss", "30"]` starts 30 seconds in).
        options: Arguments after it, before the output (`["-af", "volume=0.5"]`).
        bitrate: The Opus bitrate, in kbit/s.

    The process gets no shell: `source` and the options are passed as they are.
    """

    __slots__ = ("_arguments", "_executable")

    def __init__(
        self,
        source: str,
        *,
        executable: str = "ffmpeg",
        before_options: Sequence[str] = (),
        options: Sequence[str] = (),
        bitrate: int = 128,
    ) -> None:
        """Prepare the command; see the class docstring for the arguments."""
        self._executable: str = executable
        self._arguments: list[str] = [
            "-hide_banner",
            "-loglevel",
            "error",
            *before_options,
            "-i",
            source,
            "-vn",
            *options,
            "-c:a",
            "libopus",
            "-ar",
            str(OPUS_SAMPLE_RATE),
            "-ac",
            str(OPUS_CHANNELS),
            "-b:a",
            f"{bitrate}k",
            "-frame_duration",
            "20",
            "-f",
            "ogg",
            "pipe:1",
        ]

    @override
    async def packets(self) -> AsyncGenerator[bytes]:
        """Yield the packets as `ffmpeg` encodes them.

        Raises:
            FileNotFoundError: `executable` is not installed.
            AudioSourceError: `ffmpeg` failed (an input it cannot read, say); the message is what it
                printed.
        """
        process = await asyncio.create_subprocess_exec(
            self._executable,
            *self._arguments,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        reader = OggPacketReader()
        finished = False
        try:
            stdout = process.stdout
            while stdout is not None and (chunk := await stdout.read(_READ_SIZE)):
                for packet in _audio(reader.feed(chunk)):
                    yield packet
            finished = True
        finally:
            if process.returncode is None and not finished:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
            # `-loglevel error` keeps what it prints short, so reading it after the audio is safe.
            errors = await process.stderr.read() if process.stderr is not None else b""
            code = await process.wait()
        if code != 0:
            printed = errors.decode(errors="replace").strip().splitlines()
            msg = f"ffmpeg exited with {code}: {printed[-1] if printed else 'no output'}"
            raise AudioSourceError(msg)


@final
class AudioPlayer:
    """Plays a source on a voice connection, one packet per its duration, until it ends or is stopped.

    Args:
        connection: The connection to send on now; `None` while it reconnects (the audio of that
            time is skipped, so playback keeps its pace).
        source: What to play.
        clock: Time source for pacing.

    Playing starts at once; `done` resolves when it ends (with the error that ended it, if any). A
    connection opened while playing (a rejoin, a move) is told the bot is speaking before its first
    packet, as Discord requires.
    """

    __slots__ = ("_clock", "_connection", "_paused", "_resumed", "_source", "_spoken", "_task")

    def __init__(
        self,
        connection: Callable[[], VoiceConnection | None],
        source: AudioSource,
        *,
        clock: Clock | None = None,
    ) -> None:
        """Start playing; see the class docstring for the arguments."""
        self._connection: Callable[[], VoiceConnection | None] = connection
        self._source: AudioSource = source
        self._clock: Clock = clock or SystemClock()
        self._paused: bool = False
        self._resumed: asyncio.Event = asyncio.Event()
        self._resumed.set()
        self._spoken: VoiceConnection | None = None
        """The connection last told the bot is speaking."""
        self._task: asyncio.Task[None] = asyncio.create_task(self._play(), name="shoal-voice-player")

    @property
    def done(self) -> "asyncio.Task[None]":
        """The playback: it ends when the source does, or when `stop` is called."""
        return self._task

    @property
    def is_playing(self) -> bool:
        """Whether audio is going out: started, not paused, not finished."""
        return not self._task.done() and not self._paused

    @property
    def is_paused(self) -> bool:
        """Whether playback is paused."""
        return self._paused and not self._task.done()

    def pause(self) -> None:
        """Pause after the current packet; silence is sent so the next audio is not blended in."""
        self._paused = True
        self._resumed.clear()

    def resume(self) -> None:
        """Continue a paused playback."""
        self._paused = False
        self._resumed.set()

    def stop(self) -> None:
        """Stop playing and release the source; `done` ends once it has."""
        self._task.cancel()

    async def _play(self) -> None:
        started = self._clock.monotonic()
        played = 0
        try:
            async with contextlib.aclosing(self._source.packets()) as packets:
                async for packet in packets:
                    if self._paused:
                        await self._silence()
                        await self._resumed.wait()
                        started, played = self._clock.monotonic(), 0
                    await self._send(packet)
                    played += opus_samples(packet)
                    due = started + played / OPUS_SAMPLE_RATE
                    behind = self._clock.monotonic() - due
                    if behind > PLAYBACK_MAX_LAG:
                        # The loop stalled: start the schedule over rather than send a burst.
                        started, played = self._clock.monotonic(), 0
                        continue
                    await self._clock.sleep(-behind)
        finally:
            with contextlib.suppress(VoiceConnectionClosedError, OSError):
                await self._closing_silence()

    async def _silence(self) -> None:
        """Five frames of silence, paced, so audio after a pause is not blended with what came before."""
        for _ in range(SILENCE_FRAMES_AFTER_AUDIO):
            await self._send(SILENCE_FRAME)
            await self._clock.sleep(_SILENCE_SAMPLES / OPUS_SAMPLE_RATE)

    async def _closing_silence(self) -> None:
        """Five frames of silence at once (nothing follows), then the bot stops speaking."""
        connection = self._connection()
        if connection is None or not connection.is_connected or self._spoken is not connection:
            return
        for _ in range(SILENCE_FRAMES_AFTER_AUDIO):
            connection.send_frame(SILENCE_FRAME)
        await connection.speak(SpeakingFlags(0))

    async def _send(self, packet: bytes) -> None:
        connection = self._connection()
        if connection is None or not connection.is_connected:
            return
        if self._spoken is not connection:
            await connection.speak(SpeakingFlags(microphone=True))
            self._spoken = connection
        connection.send_frame(packet)
