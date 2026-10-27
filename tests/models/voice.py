import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from typing import override

import pytest

from shoal.core.codec import decode_json, encode_json
from shoal.core.ogg import OggOpusWriter
from shoal.core.snowflake import Snowflake
from shoal.models.channel import VoiceChannel
from shoal.models.state import GatewayRequiredError, State
from shoal.models.voice import AudioPlayingError, VoiceClient
from shoal.payloads import Channel, ChannelType
from shoal.payloads.gateway_events import VoiceServerUpdate
from shoal.payloads.voice import VoiceState
from shoal.payloads.voice_gateway import EncryptionMode
from shoal.voice.audio import AudioSource, OggOpusSource
from shoal.voice.crypto import TransportCipher
from shoal.voice.receive import opus
from shoal.voice.rtp import rtp_header
from tests.support.fakes import FakeTransport, ManualClock, settle
from tests.support.rest import make_client
from tests.support.voice import KEY, FakeOpus, FakeVoiceConnector, FakeVoiceGateway, FakeVoiceTransports

GUILD, CHANNEL, OTHER_CHANNEL, BOT = 10, 20, 21, 1
FRAME = bytes([0xFC, 0x01, 0x02])


def voice_state(channel_id: int | None, session_id: str = "session") -> VoiceState:
    return decode_json(
        encode_json(
            {
                "guild_id": str(GUILD),
                "channel_id": None if channel_id is None else str(channel_id),
                "user_id": str(BOT),
                "session_id": session_id,
                "deaf": False,
                "mute": False,
                "self_deaf": False,
                "self_mute": False,
                "self_video": False,
                "suppress": False,
                "request_to_speak_timestamp": None,
            }
        ),
        VoiceState,
    )


def server(endpoint: str | None = "voice.test:443", token: str = "token") -> VoiceServerUpdate:  # noqa: S107 - a test token
    return VoiceServerUpdate(token=token, guild_id=Snowflake(GUILD), endpoint=endpoint)


class Gateway:
    """Records voice state updates, and answers them like the main gateway when asked to."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, int | None, bool, bool]] = []
        self.voice: VoiceClient | None = None
        self.answer = True

    async def __call__(
        self, guild_id: int, channel_id: int | None, *, self_mute: bool, self_deaf: bool
    ) -> None:
        self.sent.append((guild_id, channel_id, self_mute, self_deaf))
        if self.answer and channel_id is not None and self.voice is not None:
            self.voice.on_voice_server(server(token=f"token-{len(self.sent)}"))
            self.voice.on_voice_state(voice_state(channel_id))


async def until(condition: Callable[[], bool]) -> None:
    """Let the loop run until `condition` holds (a handshake takes a few rounds)."""
    for _ in range(50):
        if condition():
            return
        await settle()
    msg = "the condition never held"
    raise AssertionError(msg)


class Harness:
    def __init__(self) -> None:
        self.clock = ManualClock()
        self.state = State(rest=make_client(FakeTransport()), clock=self.clock)
        self.state.identify(user_id=BOT, application_id=2)
        self.gateway = Gateway()
        self.forgotten: list[VoiceClient] = []
        self.connector = FakeVoiceConnector()
        self.transports = FakeVoiceTransports()
        self.voice = VoiceClient(
            self.state,
            GUILD,
            send_state=self.gateway,
            forget=self.forgotten.append,
            connector=self.connector,
            transports=self.transports,
        )
        self.gateway.voice = self.voice

    async def joined(self, channel_id: int = CHANNEL) -> "Harness":
        await self.voice.connect(channel_id, self_deaf=True)
        return self


async def test_joining_waits_for_both_answers_then_connects() -> None:
    harness = Harness()
    harness.gateway.answer = False
    voice = harness.voice
    joining = asyncio.ensure_future(voice.connect(CHANNEL, self_mute=True))
    await settle()
    assert harness.gateway.sent == [(GUILD, CHANNEL, True, False)]
    voice.on_voice_server(server())
    await settle()
    assert not joining.done()  # the voice state is still to come
    voice.on_voice_state(voice_state(CHANNEL, "abc"))
    await asyncio.wait_for(joining, timeout=2)
    assert voice.is_connected()
    assert (voice.guild_id, voice.channel_id) == (GUILD, CHANNEL)
    connection = voice.connection
    assert connection is not None
    assert (connection.server.session_id, connection.server.token) == ("abc", "token")
    assert voice.latency is None
    assert voice.privacy_code is None
    assert repr(voice) == "VoiceClient(guild_id=10, channel_id=20)"
    await voice.disconnect()
    assert harness.gateway.sent[-1] == (GUILD, None, True, False)
    assert harness.forgotten == [voice]
    assert voice.channel_id is None
    await voice.disconnect()  # once is enough
    assert len(harness.gateway.sent) == 2


async def test_joining_gives_up_when_discord_does_not_answer() -> None:
    harness = Harness()
    harness.gateway.answer = False
    joining = asyncio.ensure_future(harness.voice.connect(CHANNEL))
    await settle()
    await harness.clock.advance(30)
    with pytest.raises(TimeoutError):
        await joining


async def test_moving_and_a_moved_voice_server_open_a_new_connection() -> None:
    harness = await Harness().joined()
    voice = harness.voice
    first = voice.connection
    await voice.move_to(OTHER_CHANNEL)
    assert voice.channel_id == OTHER_CHANNEL
    assert harness.gateway.sent[-1] == (GUILD, OTHER_CHANNEL, False, True)
    assert voice.connection is not first
    voice.on_voice_server(server(endpoint=None))  # the voice server went away: wait for the next
    voice.on_voice_server(server(endpoint="voice-2.test:443", token="new"))
    await until(lambda: voice.connection is not None and voice.connection.server.token == "new")
    # A new token on the same voice server is a new session too: connect again with it.
    voice.on_voice_server(server(endpoint="voice-2.test:443", token="newer"))
    await until(lambda: voice.connection is not None and voice.connection.server.token == "newer")
    connection = voice.connection
    assert connection is not None
    assert connection.server.endpoint == "voice-2.test:443"
    await voice.disconnect()


async def test_being_disconnected_leaves_without_saying_so() -> None:
    harness = await Harness().joined()
    harness.voice.on_voice_state(voice_state(None))
    await settle()
    assert harness.forgotten == [harness.voice]
    assert harness.gateway.sent == [(GUILD, CHANNEL, False, True)]  # nothing more sent
    assert not harness.voice.is_connected()


async def test_a_lost_session_is_joined_again() -> None:
    harness = await Harness().joined()
    voice = harness.voice
    lost = voice.connection
    harness.connector.opened[-1].drop(4006)
    await until(lambda: not voice.is_connected())
    await until(voice.is_connected)
    assert harness.gateway.sent[-1] == (GUILD, CHANNEL, False, True)
    assert len(harness.gateway.sent) == 2
    assert voice.is_connected()
    assert voice.connection is not lost
    await voice.disconnect()


async def test_a_call_discord_ended_is_left(caplog: pytest.LogCaptureFixture) -> None:
    harness = await Harness().joined()
    with caplog.at_level(logging.INFO, logger="shoal.voice"):
        harness.connector.opened[-1].drop(4014)
        await settle()
    assert harness.forgotten == [harness.voice]
    assert "ended" in caplog.text
    assert len(harness.gateway.sent) == 1


async def test_joining_again_gives_up_after_repeated_failures(caplog: pytest.LogCaptureFixture) -> None:
    harness = await Harness().joined()
    harness.gateway.answer = False
    with caplog.at_level(logging.WARNING, logger="shoal.voice"):
        harness.connector.opened[-1].drop(4006)
        for _ in range(12):
            await settle()
            await harness.clock.advance(31)
    assert "could not be joined again" in caplog.text
    assert harness.forgotten == [harness.voice]
    assert harness.gateway.sent[-1] == (GUILD, None, False, True)


async def test_playing_pausing_and_stopping() -> None:
    harness = await Harness().joined()
    voice = harness.voice
    writer = OggOpusWriter()
    data = writer.headers() + b"".join(writer.packet(FRAME, 960) for _ in range(50))
    finished: list[BaseException | None] = []
    voice.play(OggOpusSource(data), after=finished.append)
    await settle()
    assert voice.is_playing()
    with pytest.raises(AudioPlayingError):
        voice.play(OggOpusSource(data))
    voice.pause()
    assert voice.is_paused()
    voice.resume()
    assert not voice.is_paused()
    voice.stop()
    await voice.wait_until_done()
    assert not voice.is_playing()
    assert finished == [None]
    await voice.wait_until_done()
    voice.play(OggOpusSource(writer.headers()))
    await voice.wait_until_done()
    await voice.disconnect()


async def test_listening_yields_what_others_send() -> None:
    harness = await Harness().joined()
    voice = harness.voice
    gateway, socket = harness.connector.opened[-1], harness.transports.transports[-1]
    gateway.push(5, {"speaking": 1, "ssrc": 55, "user_id": "99"}, seq=1)
    await settle()
    heard = voice.listen()
    first = asyncio.ensure_future(anext(heard))
    await settle()
    sender = TransportCipher(EncryptionMode.AEAD_AES256_GCM_RTPSIZE, KEY)
    socket.incoming.put_nowait(sender.seal(rtp_header(1, 960, 55), FRAME))
    packet = await asyncio.wait_for(first, timeout=2)
    assert (packet.user_id, packet.opus) == (99, FRAME)
    await voice.disconnect()


async def test_audio_is_what_one_user_says_decoded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opus, "_library", FakeOpus())
    harness = await Harness().joined()
    voice = harness.voice
    gateway, socket = harness.connector.opened[-1], harness.transports.transports[-1]
    gateway.push(5, {"speaking": 1, "ssrc": 55, "user_id": "99"}, seq=1)
    gateway.push(5, {"speaking": 1, "ssrc": 66, "user_id": "98"}, seq=2)
    await settle()
    heard = voice.audio(user=99)
    first = asyncio.ensure_future(anext(heard))
    await settle()
    sender = TransportCipher(EncryptionMode.AEAD_AES256_GCM_RTPSIZE, KEY)
    socket.incoming.put_nowait(sender.seal(rtp_header(1, 960, 66), bytes([0xFC, 8])))
    socket.incoming.put_nowait(sender.seal(rtp_header(1, 960, 55), bytes([0xFC, 9])))
    frame = await asyncio.wait_for(first, timeout=2)
    assert (frame.user_id, frame.pcm[0], len(frame.pcm)) == (99, 9, 960 * 4)
    await voice.disconnect()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(heard), timeout=2)


async def test_listening_waits_for_a_connection_and_ends_with_the_leave() -> None:
    harness = Harness()
    heard = asyncio.ensure_future(anext(harness.voice.listen()))
    await settle()
    assert not heard.done()
    await harness.voice.disconnect()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(heard, timeout=2)


async def test_a_voice_channel_joins_through_its_state() -> None:
    state = State(rest=make_client(FakeTransport()))
    channel = VoiceChannel(
        state, Channel(id=Snowflake(CHANNEL), type=ChannelType.GUILD_VOICE, guild_id=Snowflake(GUILD))
    )
    with pytest.raises(GatewayRequiredError, match="joining a voice channel"):
        await channel.connect()
    assert state.voice.voice_client(GUILD) is None


async def test_a_terminated_call_waits_for_the_gateway_to_say_where_it_went() -> None:
    harness = await Harness().joined()
    voice = harness.voice
    harness.connector.opened[-1].drop(4022)
    await until(lambda: not voice.is_connected())
    await settle()
    assert harness.forgotten == []
    assert len(harness.gateway.sent) == 1  # no rejoin: the gateway decides
    voice.on_voice_server(server(endpoint="voice-2.test:443", token="moved"))
    await until(voice.is_connected)
    connection = voice.connection
    assert connection is not None
    assert connection.server.token == "moved"
    assert len(harness.gateway.sent) == 1
    await voice.disconnect()


async def test_a_new_voice_server_that_fails_falls_back_to_joining_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness = await Harness().joined()
    voice = harness.voice
    refusing = FakeVoiceGateway()
    refusing.drop(4006)
    harness.connector.prepared.append(refusing)
    with caplog.at_level(logging.WARNING, logger="shoal.voice"):
        voice.on_voice_server(server(endpoint="voice-2.test:443", token="moved"))
        await until(lambda: len(harness.gateway.sent) == 2)
        await until(voice.is_connected)
    assert "new voice server" in caplog.text
    assert harness.gateway.sent[-1] == (GUILD, CHANNEL, False, True)
    await voice.disconnect()


class Broken(AudioSource):
    @override
    async def packets(self) -> AsyncGenerator[bytes]:
        yield b""  # not an Opus packet


async def test_a_playback_error_is_logged_without_after(caplog: pytest.LogCaptureFixture) -> None:
    harness = await Harness().joined()
    voice = harness.voice
    with caplog.at_level(logging.ERROR, logger="shoal.voice"):
        voice.play(Broken())
        await voice.wait_until_done()
    assert "playback in guild 10 stopped" in caplog.text
    assert "TOC byte" in caplog.text
    await voice.disconnect()


async def test_moving_takes_a_channel_or_its_id() -> None:
    harness = await Harness().joined()
    channel = VoiceChannel(
        harness.state,
        Channel(id=Snowflake(OTHER_CHANNEL), type=ChannelType.GUILD_VOICE, guild_id=Snowflake(GUILD)),
    )
    await harness.voice.move_to(channel)
    assert harness.voice.channel_id == OTHER_CHANNEL
    assert harness.gateway.sent[-1] == (GUILD, OTHER_CHANNEL, False, True)
    await harness.voice.disconnect()
