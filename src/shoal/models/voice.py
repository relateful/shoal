"""Voice from the bot's side: joining a channel, playing audio, and listening.

    voice = await channel.connect()
    voice.play(FFmpegSource("song.mp3"))
    await voice.wait_until_done()
    await voice.disconnect()

Joining takes two answers from the main gateway (the bot's voice state, with its session, and the
voice server to connect to); the `Client` passes them to the guild's `VoiceClient`, which opens the
`shoal.voice` connection. Every new voice server answer means a new session, so the voice client
connects again whenever one arrives (a move, or Discord moving the call). When the session is lost
it joins again by itself; when Discord ends the call it leaves. One join, reconnect or rejoin runs at
a time.

Voice needs `pip install 'shoal[voice]'`; nothing here loads it until a channel is joined.

Discord: https://docs.discord.com/developers/topics/voice-connections#connecting-to-voice
"""

import abc
import asyncio
import contextlib
import logging
import random
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Protocol, final, override

from shoal.core.backoff import backoff_delay
from shoal.core.clock import within
from shoal.core.errors import ShoalError
from shoal.core.metrics import VOICE_RECONNECTS, Metrics, NoopMetrics
from shoal.core.snowflake import Snowflake
from shoal.core.tasks import spawn
from shoal.models.base import Hashable
from shoal.payloads.gateway_events import VoiceServerUpdate
from shoal.payloads.voice import VoiceState
from shoal.payloads.voice_gateway import VoiceCloseCode

if TYPE_CHECKING:
    from shoal.gateway.connection import GatewayConnector
    from shoal.models.channel import VoiceChannel
    from shoal.models.state import State
    from shoal.voice.audio import AudioPlayer, AudioSource
    from shoal.voice.connection import VoiceConnection, VoicePacket
    from shoal.voice.receive import AudioFrame
    from shoal.voice.udp import VoiceTransportFactory

_log = logging.getLogger("shoal.voice")


class AudioPlayingError(ShoalError):
    """The voice client is already playing; `stop` it first."""


class SendVoiceState(Protocol):
    """Sends the main gateway's voice state update for a guild; a `None` channel leaves voice."""

    __slots__ = ()

    async def __call__(
        self, guild_id: int, channel_id: int | None, *, self_mute: bool, self_deaf: bool
    ) -> None:
        """Send the update."""
        ...


class VoiceGateway(Protocol):
    """Joins voice channels through the main gateway: a `Client`."""

    __slots__ = ()

    async def connect_voice(
        self, guild_id: int, channel_id: int, /, *, self_mute: bool, self_deaf: bool
    ) -> "VoiceClient":
        """Join (or move to) a voice channel; the guild's voice client once audio can flow.

        Raises:
            GatewayRequiredError: There is no gateway connection for the guild.
            TimeoutError: Discord did not answer, or the voice handshake did not finish, in time.
            VoiceConnectionClosedError: The voice server refused the connection.
        """
        ...

    def voice_client(self, guild_id: int, /) -> "VoiceClient | None":
        """The guild's voice client, while the bot is in one of its voice channels."""
        ...

    async def connect_protocol(self, voice: "VoiceProtocol", /, *, self_mute: bool, self_deaf: bool) -> None:
        """Register `voice` as the guild's voice, then call its `connect`.

        Raises:
            GatewayRequiredError: There is no gateway connection for the guild.
            VoiceInUseError: The guild already has a voice client or protocol.
        """
        ...

    def voice_protocol(self, guild_id: int, /) -> "VoiceProtocol | None":
        """The guild's registered `VoiceProtocol`, if one is connected instead of a `VoiceClient`."""
        ...

    async def send_voice_state(
        self, guild_id: int, channel_id: int | None, *, self_mute: bool, self_deaf: bool
    ) -> None:
        """Send the main gateway's voice state update for a guild; a `None` channel leaves voice.

        Raises:
            GatewayRequiredError: There is no gateway connection for the guild.
        """
        ...

    def forget_voice(self, voice: "VoiceProtocol", /) -> None:
        """Stop sending `voice` the guild's voice events (`VoiceProtocol.cleanup` calls this)."""
        ...


class VoiceInUseError(ShoalError):
    """The guild already has a voice client or protocol; disconnect it first."""


class VoiceProtocol(abc.ABC):
    """Voice in one guild through something other than Shoal's own connection, such as Lavalink.

    Subclass it and pass the class to `VoiceChannel.connect(cls=...)`. Shoal registers the instance
    as the guild's voice, then calls `connect`; from then on, the bot's own voice state updates and
    the guild's voice server updates go to `on_voice_state_update` and `on_voice_server_update`,
    each in its own task (a failure is logged), so either may run first. Call `cleanup` once done,
    or the guild stays taken.

        class LavalinkPlayer(VoiceProtocol):
            session_id: str | None = None
            server: VoiceServerUpdate | None = None

            async def connect(self, *, self_mute: bool, self_deaf: bool) -> None:
                await self.change_voice_state(self.channel, self_mute=self_mute, self_deaf=self_deaf)

            async def on_voice_state_update(self, data: VoiceState) -> None:
                self.session_id = data.session_id
                await self.update_node()

            async def on_voice_server_update(self, data: VoiceServerUpdate) -> None:
                self.server = data
                await self.update_node()

            async def update_node(self) -> None:
                # The two updates come in either order; the node needs both.
                server = self.server
                if self.session_id is not None and server is not None and server.endpoint is not None:
                    await node.update_voice(self.guild_id, self.session_id, server.token, server.endpoint)

            async def disconnect(self) -> None:
                await self.change_voice_state(None)
                self.cleanup()

    Args:
        client: The client joining voice.
        channel: The voice channel being joined.

    Discord: https://docs.discord.com/developers/topics/voice-connections#retrieving-voice-server-information
    """

    __slots__ = ("channel", "client")

    def __init__(self, client: VoiceGateway, channel: "VoiceChannel") -> None:
        """Keep the client and the channel; see the class docstring for the arguments."""
        self.client: VoiceGateway = client
        self.channel: VoiceChannel = channel

    @override
    def __repr__(self) -> str:
        return f"{type(self).__name__}(guild_id={self.guild_id}, channel_id={self.channel.id})"

    @property
    def guild_id(self) -> Snowflake:
        """The guild."""
        return self.channel.guild_id

    @abc.abstractmethod
    async def connect(self, *, self_mute: bool, self_deaf: bool) -> None:
        """Join `channel`; usually through `change_voice_state`, then waiting for the two updates."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Leave voice; call `cleanup` once done."""

    @abc.abstractmethod
    async def on_voice_state_update(self, data: VoiceState) -> None:
        """The bot's own voice state changed in the guild; `data.session_id` is its voice session."""

    @abc.abstractmethod
    async def on_voice_server_update(self, data: VoiceServerUpdate) -> None:
        """Discord named the voice server to connect to (`data.endpoint`) and its `data.token`.

        `data.endpoint` is `None` when the voice server went away; another update follows.
        """

    async def change_voice_state(
        self, channel: "int | Hashable | None", *, self_mute: bool = False, self_deaf: bool = False
    ) -> None:
        """Join, move to or leave (`None`) a voice channel of the guild.

        Raises:
            GatewayRequiredError: There is no gateway connection for the guild.
        """
        channel_id = None if channel is None else channel if isinstance(channel, int) else int(channel.id)
        await self.client.send_voice_state(
            int(self.guild_id), channel_id, self_mute=self_mute, self_deaf=self_deaf
        )

    def cleanup(self) -> None:
        """Stop receiving the guild's voice events and free the guild for another voice."""
        self.client.forget_voice(self)


@final
class VoiceClient:
    """The bot's voice connection in one guild.

    Created by the `Client` (`VoiceChannel.connect`); its gateway answers arrive through it.

    Args:
        state: The models' state.
        guild_id: The guild.
        send_state: Sends the main gateway's voice state update.
        forget: Called once the voice client leaves for good.
        connector: Opens voice websockets (tests pass a fake).
        transports: Opens voice UDP sockets (tests pass a fake).
        metrics: Receives the voice metrics.
        random_source: Random source for rejoin jitter.
    """

    __slots__ = (
        "_channel_id",
        "_connected",
        "_connection",
        "_connector",
        "_endpoint",
        "_forget",
        "_guild_id",
        "_leaving",
        "_lock",
        "_metrics",
        "_player",
        "_random_source",
        "_self_deaf",
        "_self_mute",
        "_send_state",
        "_server_update",
        "_session_id",
        "_state",
        "_state_update",
        "_token",
        "_transports",
        "_watcher",
    )

    def __init__(
        self,
        state: "State",
        guild_id: int,
        *,
        send_state: SendVoiceState,
        forget: Callable[["VoiceClient"], None],
        connector: "GatewayConnector | None" = None,
        transports: "VoiceTransportFactory | None" = None,
        metrics: Metrics | None = None,
        random_source: random.Random | None = None,
    ) -> None:
        """Create the voice client; see the class docstring for the arguments."""
        self._state: State = state
        self._guild_id: int = guild_id
        self._send_state: SendVoiceState = send_state
        self._forget: Callable[[VoiceClient], None] = forget
        self._connector: GatewayConnector | None = connector
        self._transports: VoiceTransportFactory | None = transports
        self._metrics: Metrics = metrics or NoopMetrics()
        self._random_source: random.Random = random_source or random.Random()  # noqa: S311 - jitter, not security
        self._channel_id: int | None = None
        self._self_mute: bool = False
        self._self_deaf: bool = False
        self._session_id: str | None = None
        self._token: str | None = None
        self._endpoint: str | None = None
        self._connection: VoiceConnection | None = None
        self._connected: asyncio.Event = asyncio.Event()
        """Set while a connection is up (and once leaving); `listen` waits on it across reconnects."""
        self._player: AudioPlayer | None = None
        self._watcher: asyncio.Task[None] | None = None
        self._state_update: asyncio.Future[None] | None = None
        self._server_update: asyncio.Future[None] | None = None
        self._lock: asyncio.Lock = asyncio.Lock()
        """Held by a join, a reconnect or a rejoin: they would race on the session otherwise."""
        self._leaving: bool = False

    @override
    def __repr__(self) -> str:
        return f"VoiceClient(guild_id={self._guild_id}, channel_id={self._channel_id})"

    @property
    def guild_id(self) -> Snowflake:
        """The guild."""
        return Snowflake(self._guild_id)

    @property
    def channel_id(self) -> Snowflake | None:
        """The voice channel the bot is in, once joined."""
        return None if self._channel_id is None else Snowflake(self._channel_id)

    @property
    def connection(self) -> "VoiceConnection | None":
        """The voice connection carrying the audio; `None` while (re)joining."""
        return self._connection

    @property
    def latency(self) -> float | None:
        """The voice connection's heartbeat round trip, in seconds, once measured."""
        return self._connection.latency if self._connection is not None else None

    @property
    def privacy_code(self) -> str | None:
        """The call's voice privacy code: members comparing it confirm the end-to-end encryption."""
        return self._connection.dave.privacy_code if self._connection is not None else None

    def is_connected(self) -> bool:
        """Whether audio can flow now."""
        return self._connection is not None and self._connection.is_connected

    async def connect(self, channel_id: int, *, self_mute: bool = False, self_deaf: bool = False) -> None:
        """Join `channel_id` (or move there), and return once audio can flow.

        Raises:
            TimeoutError: Discord did not answer, or the voice handshake did not finish, in time.
            VoiceConnectionClosedError: The voice server refused the connection.
        """
        from shoal.voice.defaults import JOIN_TIMEOUT

        self._self_mute, self._self_deaf = self_mute, self_deaf
        await within(self._state.clock, JOIN_TIMEOUT, self._join(channel_id))

    async def _join(self, channel_id: int) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            self._state_update, self._server_update = loop.create_future(), loop.create_future()
            try:
                await self._send_state(
                    self._guild_id, channel_id, self_mute=self._self_mute, self_deaf=self._self_deaf
                )
                # Discord answers with both, in either order; the server's token changes on every join.
                await asyncio.gather(self._state_update, self._server_update)
            finally:
                self._state_update = self._server_update = None
            await self._open()

    async def _open(self) -> None:
        """Connect with the latest answers, replacing the current connection. Hold `_lock`."""
        from shoal.voice.connection import VoiceConnection, VoiceServer

        channel_id, session_id, token, endpoint = (
            self._channel_id,
            self._session_id,
            self._token,
            self._endpoint,
        )
        user_id = self._state.user_id
        if channel_id is None or session_id is None or token is None or endpoint is None or user_id is None:
            msg = "the gateway's voice answers are incomplete"
            raise ShoalError(msg)
        await self._drop_connection()
        connection = VoiceConnection(
            VoiceServer(self._guild_id, channel_id, session_id, token, endpoint),
            user_id=int(user_id),
            connector=self._connector,
            transports=self._transports,
            metrics=self._metrics,
            clock=self._state.clock,
            random_source=self._random_source,
        )
        await connection.connect()
        self._connection = connection
        self._connected.set()
        self._watcher = spawn(self._watch(connection), name=f"shoal-voice-{self._guild_id}")

    async def _drop_connection(self) -> None:
        connection, self._connection = self._connection, None
        self._connected.clear()
        if connection is not None:
            await connection.close()

    async def _watch(self, connection: "VoiceConnection") -> None:
        """Join again when the session is lost; leave when Discord ended the call."""
        ended = await connection.closed
        if ended is None or self._is_leaving() or self._connection is not connection:
            return
        self._connection = None
        self._connected.clear()
        if ended.code == VoiceCloseCode.DISCONNECTED_CALL_TERMINATED:
            # The channel is gone, or the call moved to another voice server: the main gateway says
            # which (a voice state without a channel leaves, a new voice server reconnects).
            _log.info("voice in guild %d: %s; waiting for the gateway", self._guild_id, ended)
            return
        if ended.ends_connection:
            _log.info("voice in guild %d ended: %s", self._guild_id, ended)
            await self._leave(send=False)
            return
        await self._rejoin()

    async def _rejoin(self) -> None:
        """Join the channel again with a new session, a few times; leave if it never works."""
        from shoal.voice.defaults import JOIN_TIMEOUT, REJOIN_ATTEMPTS, REJOIN_BACKOFF_CAP

        channel_id = self._channel_id
        for attempt in range(1, REJOIN_ATTEMPTS + 1):
            if self._is_leaving() or channel_id is None:
                return
            try:
                await within(self._state.clock, JOIN_TIMEOUT, self._join(channel_id))
            except (OSError, TimeoutError, ShoalError) as error:
                _log.warning("joining voice in guild %d again failed: %r", self._guild_id, error)
                delay = backoff_delay(attempt, cap=REJOIN_BACKOFF_CAP, random_source=self._random_source)
                await self._state.clock.sleep(delay)
                continue
            self._metrics.increment(VOICE_RECONNECTS, {"mode": "rejoin"})
            return
        _log.error("voice in guild %d could not be joined again; leaving", self._guild_id)
        await self._leave(send=True)

    async def _reconnect(self) -> None:
        """Connect with a voice server Discord named outside a join (a move, a new voice server)."""
        try:
            async with self._lock:
                if self._is_leaving():
                    return
                await self._open()
        except (OSError, TimeoutError, ShoalError) as error:
            _log.warning("connecting to the new voice server of guild %d failed: %r", self._guild_id, error)
            await self._rejoin()

    def _is_leaving(self) -> bool:
        # Read through a method: checkers would narrow the attribute across the awaits in between.
        return self._leaving

    def on_voice_state(self, state: VoiceState) -> None:
        """The bot's own voice state changed in this guild (the client calls this)."""
        if state.channel_id is None:
            if not self._leaving and self._channel_id is not None:
                _log.info("the bot was disconnected from voice in guild %d", self._guild_id)
                _ = spawn(self._leave(send=False), name=f"shoal-voice-leave-{self._guild_id}")
            return
        self._channel_id = int(state.channel_id)
        self._session_id = state.session_id
        if self._state_update is not None and not self._state_update.done():
            self._state_update.set_result(None)

    def on_voice_server(self, server: VoiceServerUpdate) -> None:
        """Discord named the voice server to connect to (the client calls this)."""
        if server.endpoint is None:
            # The voice server went away; the next update names a new one.
            return
        self._token, self._endpoint = server.token, server.endpoint
        if self._server_update is not None:
            if not self._server_update.done():
                self._server_update.set_result(None)
            return
        if self._channel_id is not None and not self._leaving:
            # A new token is a new session, even on the same voice server: connect again with it.
            _ = spawn(self._reconnect(), name=f"shoal-voice-reconnect-{self._guild_id}")

    async def move_to(self, channel: int | Hashable) -> None:
        """Move to another voice channel of the guild (a channel or its ID).

        Raises:
            TimeoutError: Discord did not answer, or the voice handshake did not finish, in time.
            VoiceConnectionClosedError: The voice server refused the connection.
        """
        channel_id = channel if isinstance(channel, int) else int(channel.id)
        await self.connect(channel_id, self_mute=self._self_mute, self_deaf=self._self_deaf)

    def play(
        self, source: "AudioSource", *, after: Callable[[BaseException | None], object] | None = None
    ) -> None:
        """Play `source`; `after` is called with the error that stopped it, or `None`.

        Without `after`, an error that stops playback is logged.

        Raises:
            AudioPlayingError: Something is already playing.
        """
        from shoal.voice.audio import AudioPlayer

        if self._player is not None and not self._player.done.done():
            msg = "already playing audio; stop it first"
            raise AudioPlayingError(msg)
        player = AudioPlayer(lambda: self._connection, source, clock=self._state.clock)
        self._player = player

        def finished(task: "asyncio.Task[None]") -> None:
            error = None if task.cancelled() else task.exception()
            if after is not None:
                after(error)
            elif error is not None:
                _log.error("playback in guild %d stopped", self._guild_id, exc_info=error)

        player.done.add_done_callback(finished)

    def is_playing(self) -> bool:
        """Whether audio is going out."""
        return self._player is not None and self._player.is_playing

    def is_paused(self) -> bool:
        """Whether playback is paused."""
        return self._player is not None and self._player.is_paused

    def pause(self) -> None:
        """Pause playback."""
        if self._player is not None:
            self._player.pause()

    def resume(self) -> None:
        """Continue a paused playback."""
        if self._player is not None:
            self._player.resume()

    def stop(self) -> None:
        """Stop playing."""
        if self._player is not None:
            self._player.stop()

    async def wait_until_done(self) -> None:
        """Wait until the current playback ends, if there is one; how it ended goes to `after`."""
        if self._player is not None:
            await asyncio.wait({self._player.done})

    async def listen(self) -> "AsyncIterator[VoicePacket]":
        """Yield the Opus packets others send in the call, decrypted, until the bot leaves.

        Each packet says who sent it; packets from someone whose audio stream Discord has not named
        yet are dropped. Rejoins and moves are followed: the packets of the new connection come
        through the same iteration. Packets are only kept while iterating; `shoal.core.ogg.OggOpusWriter`
        saves a user's packets as an `.ogg` file.
        """
        while not self._is_leaving():
            connection = self._connection
            if connection is None:
                await self._connected.wait()
                continue
            async for packet in connection.packets():
                yield packet
            if self._connection is connection:
                # It ended without being replaced: wait for the next connection, or the leave.
                self._connected.clear()

    async def audio(self, user: int | None = None) -> "AsyncIterator[AudioFrame]":
        """Yield what others say in the call as PCM (48 kHz stereo, 16-bit), until the bot leaves.

        Each sender's audio comes in order, with packets lost in transit concealed; a pause in
        speech yields nothing. Needs libopus (see `shoal.voice.receive.opus`).

        Args:
            user: Only this user's audio.

        Raises:
            OpusError: libopus is missing.
        """
        from shoal.voice.receive import decode_audio

        async for frame in decode_audio(self.listen(), metrics=self._metrics):
            if user is None or frame.user_id == user:
                yield frame

    async def disconnect(self) -> None:
        """Stop playing, close the connection and leave the channel."""
        await self._leave(send=True)

    async def _leave(self, *, send: bool) -> None:
        if self._leaving:
            return
        self._leaving = True
        player = self._player
        if player is not None:
            player.stop()
            await asyncio.wait({player.done})
        if self._watcher is not None and self._watcher is not asyncio.current_task():
            self._watcher.cancel()
        await self._drop_connection()
        self._connected.set()  # wakes a `listen` waiting for a connection, which then ends
        if send:
            with contextlib.suppress(ShoalError, OSError):
                await self._send_state(
                    self._guild_id, None, self_mute=self._self_mute, self_deaf=self._self_deaf
                )
        self._channel_id = None
        self._forget(self)
