"""One gateway connection: connect, identify or resume, heartbeat, dispatch, reconnect.

The shard does no event processing of its own. Every dispatch is handed to a callback with its data
still raw, so the consumer decodes only what it needs, in-process or after forwarding the bytes to
another process.

Discord: https://docs.discord.com/developers/events/gateway#connection-lifecycle
"""

import asyncio
import logging
import platform
import random
from dataclasses import dataclass
from enum import Enum, StrEnum, auto
from typing import final
from urllib.parse import urlencode, urlsplit, urlunsplit

import msgspec
from msgspec import UNSET

from shoal._version import __version__
from shoal.core.backoff import backoff_delay
from shoal.core.clock import Clock, SystemClock, sleep_unless
from shoal.core.codec import PayloadDecodeError, decode_json, encode_json
from shoal.core.dispatch import DispatchEvent, DispatchHandler
from shoal.core.errors import ShoalError
from shoal.core.metrics import (
    GATEWAY_EVENT_DELAY_SECONDS,
    GATEWAY_EVENTS,
    GATEWAY_LATENCY_SECONDS,
    GATEWAY_RECONNECTS,
    GATEWAY_SHARD_READY,
    Metrics,
    NoopMetrics,
)
from shoal.core.snowflake import Snowflake
from shoal.core.tasks import cancel_and_wait
from shoal.gateway.compression import Decompressor, create_decompressor, require_decompressor
from shoal.gateway.connection import (
    AiohttpGatewayConnector,
    GatewayConnection,
    GatewayConnector,
    MessageKind,
)
from shoal.gateway.defaults import (
    DELAY_TRACKED_EVENTS,
    EVENT_DELAY_WARNING,
    EVENT_DELAY_WARNING_COOLDOWN,
    HELLO_TIMEOUT,
    INVALID_SESSION_DELAY,
    RECONNECT_BACKOFF_CAP,
    RESUMABLE_CLOSE_CODE,
    RESUME_WINDOW,
    STABLE_CONNECTION,
)
from shoal.gateway.heartbeat import HeartbeatMonitor
from shoal.gateway.ratelimit import GatewaySendLimiter
from shoal.gateway.session import GatewaySession, SessionStore
from shoal.gateway.sharding import IdentifyLimiter, LocalIdentifyLimiter
from shoal.payloads.api import API_VERSION
from shoal.payloads.gateway import (
    DEFAULT_GATEWAY_URL,
    LARGE_THRESHOLD_RANGE,
    SESSION_ENDING_CLOSE_CODES,
    GatewayCloseCode,
    GatewayEncoding,
    GatewayOpcode,
    Intents,
    TransportCompression,
)
from shoal.payloads.gateway_events import (
    GatewayCapabilities,
    GatewayPayload,
    Hello,
    Identify,
    IdentifyConnectionProperties,
    RateLimited,
    Ready,
    RequestChannelInfo,
    RequestGuildMembers,
    RequestSoundboardSounds,
    Resume,
    UpdatePresence,
    UpdateVoiceState,
)

_log = logging.getLogger("shoal.gateway")


class _CreatedObject(msgspec.Struct, gc=False):
    """Just the ID of a dispatched object, to read its creation time from the snowflake."""

    id: Snowflake


class ShardState(StrEnum):
    """Where a shard is in its connection lifecycle.

    A shard goes `IDLE` → `CONNECTING` → `IDENTIFYING` or `RESUMING` → `READY`, back to `CONNECTING`
    on every reconnect, and ends `CLOSED`.
    """

    CLOSED = "closed"
    CONNECTING = "connecting"
    IDENTIFYING = "identifying"
    IDLE = "idle"
    READY = "ready"
    RESUMING = "resuming"


class GatewayFatalError(ShoalError):
    """Discord closed the connection with a code that reconnecting cannot fix (bad token, intents)."""

    def __init__(self, shard_id: int, code: GatewayCloseCode) -> None:
        """Report the shard and the close code."""
        super().__init__(f"shard {shard_id} closed with {code.name} ({int(code)}); not reconnecting")
        self.shard_id: int = shard_id
        self.code: GatewayCloseCode = code


class ShardNotConnectedError(ShoalError):
    """A command was sent while the shard had no open connection."""


class _Next(Enum):
    RESUME = auto()
    RESUME_REQUESTED = auto()
    """Discord asked for the reconnect; it is routine, not a failure to back off from."""
    IDENTIFY = auto()
    STOP = auto()


@dataclass(frozen=True, slots=True)
class _Closed:
    code: int | None


@final
class Shard:
    """A single gateway connection and its session.

    Args:
        token: The bot token, without the `Bot ` prefix.
        shard_id: This shard's index.
        shard_count: Total shards.
        intents: Gateway intents.
        dispatch: Receives every dispatch event, in order. Exceptions it raises are logged and do
            not stop the shard.
        connector: Opens websockets. Defaults to aiohttp.
        identify_limiter: Coordinates identifies across shards. Pass one shared limiter to every
            shard of a bot, or a cross-process implementation when shards span processes.
        session_store: Where sessions are saved so a restart can resume. `None` keeps them only in
            memory for this process.
        gateway_url: The URL from Get Gateway Bot.
        compression: Transport compression, or `None` for none.
        large_threshold: Member count above which guilds arrive without offline members (50-250).
        presence: Initial presence sent with Identify.
        capabilities: Opt-in gateway behaviours. Pass
            `GatewayCapabilities(channel_obfuscation=True)` to receive obfuscated channels before
            Discord enables them for every bot on November 16, 2026
            (https://docs.discord.com/developers/events/gateway-events#identify-gateway-capabilities).
        metrics: Receives event counts, latency, readiness, reconnects and event delivery delay.
        event_delay_warning: Log a warning when a message or interaction arrives more than this many
            seconds after it was created (measured from its snowflake). A large delay with a low
            heartbeat latency means events are queuing somewhere: usually a blocked event loop (see
            `shoal.diagnostics.LoopMonitor`), sometimes Discord. `None` disables the warning; the
            `shoal_gateway_event_delay_seconds` metric is always recorded.
        resume_window: Seconds after a disconnect during which resuming is attempted. Discord keeps a
            session resumable for a few minutes (or until its event buffer overflows); after this
            window the shard identifies a new session instead of trying a resume that will fail.
        clock: Time source.
        random_source: Random source for jitter.

    Discord: https://docs.discord.com/developers/events/gateway
    """

    __slots__ = (
        "_capabilities",
        "_clock",
        "_closing",
        "_compression",
        "_connection",
        "_connector",
        "_disconnected_at",
        "_dispatch",
        "_event_delay_warning",
        "_gateway_url",
        "_identify_limiter",
        "_intents",
        "_labels",
        "_large_threshold",
        "_last_delay_warning",
        "_limiter",
        "_metrics",
        "_monitor",
        "_owns_connector",
        "_presence",
        "_random_source",
        "_reading",
        "_resume_url",
        "_resume_window",
        "_sequence",
        "_session_id",
        "_shard_count",
        "_shard_id",
        "_state",
        "_stopped",
        "_store",
        "_store_lock",
        "_token",
    )

    def __init__(
        self,
        *,
        token: str,
        shard_id: int,
        shard_count: int,
        intents: Intents,
        dispatch: DispatchHandler,
        connector: GatewayConnector | None = None,
        identify_limiter: IdentifyLimiter | None = None,
        session_store: SessionStore | None = None,
        gateway_url: str = DEFAULT_GATEWAY_URL,
        compression: TransportCompression | None = TransportCompression.ZLIB_STREAM,
        large_threshold: int = LARGE_THRESHOLD_RANGE[-1],
        presence: UpdatePresence | None = None,
        capabilities: GatewayCapabilities | None = None,
        metrics: Metrics | None = None,
        event_delay_warning: float | None = EVENT_DELAY_WARNING,
        resume_window: float = RESUME_WINDOW,
        clock: Clock | None = None,
        random_source: random.Random | None = None,
    ) -> None:
        """Create a shard; see the class docstring for the arguments. Call `run` to connect."""
        if not 0 <= shard_id < shard_count:
            msg = f"shard_id {shard_id} is outside 0..{shard_count - 1}"
            raise ValueError(msg)
        if large_threshold not in LARGE_THRESHOLD_RANGE:
            msg = (
                f"large_threshold must be between {LARGE_THRESHOLD_RANGE[0]} and {LARGE_THRESHOLD_RANGE[-1]}"
            )
            raise ValueError(msg)
        require_decompressor(compression)
        self._token: str = token
        self._shard_id: int = shard_id
        self._shard_count: int = shard_count
        self._intents: Intents = intents
        self._dispatch: DispatchHandler = dispatch
        self._owns_connector: bool = connector is None
        self._connector: GatewayConnector = connector or AiohttpGatewayConnector()
        self._identify_limiter: IdentifyLimiter = identify_limiter or LocalIdentifyLimiter(1, clock=clock)
        self._store: SessionStore | None = session_store
        self._gateway_url: str = gateway_url
        self._compression: TransportCompression | None = compression
        self._large_threshold: int = large_threshold
        self._presence: UpdatePresence | None = presence
        self._capabilities: GatewayCapabilities | None = capabilities
        self._metrics: Metrics = metrics or NoopMetrics()
        self._labels: dict[str, str] = {"shard": str(shard_id)}
        self._event_delay_warning: float | None = event_delay_warning
        self._resume_window: float = resume_window
        self._disconnected_at: float | None = None
        self._last_delay_warning: float | None = None
        self._clock: Clock = clock or SystemClock()
        self._random_source: random.Random = random_source or random.Random()  # noqa: S311 - jitter, not security
        self._state: ShardState = ShardState.IDLE
        self._session_id: str | None = None
        self._resume_url: str | None = None
        self._sequence: int | None = None
        self._connection: GatewayConnection | None = None
        self._limiter: GatewaySendLimiter | None = None
        self._monitor: HeartbeatMonitor | None = None
        self._closing: bool = False
        self._stopped: asyncio.Event = asyncio.Event()
        self._store_lock: asyncio.Lock = asyncio.Lock()
        self._reading: bool = False
        """Whether the receive loop is waiting on the socket, i.e. has processed everything sent so far."""

    @property
    def shard_id(self) -> int:
        """This shard's index."""
        return self._shard_id

    @property
    def state(self) -> ShardState:
        """The current lifecycle state."""
        return self._state

    @property
    def latency(self) -> float | None:
        """Heartbeat round trip in seconds, once measured on the current connection."""
        return self._monitor.latency if self._monitor is not None else None

    @property
    def session(self) -> GatewaySession | None:
        """The resumable session, if one exists."""
        if self._session_id is None or self._sequence is None:
            return None
        return GatewaySession(
            shard_id=self._shard_id,
            shard_count=self._shard_count,
            session_id=self._session_id,
            sequence=self._sequence,
            resume_gateway_url=self._resume_url or self._gateway_url,
            saved_at=self._clock.wall(),
        )

    def gateway_query(self) -> str:
        """The query string every connection uses (version, encoding, compression).

        Discord: https://docs.discord.com/developers/events/gateway#connecting
        """
        params = {"v": str(API_VERSION), "encoding": GatewayEncoding.JSON.value}
        if self._compression is not None:
            params["compress"] = self._compression.value
        return urlencode(params)

    def _url(self) -> str:
        base = self._resume_url if self._session_id is not None and self._resume_url else self._gateway_url
        parts = urlsplit(base)
        return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", self.gateway_query(), ""))

    async def run(self) -> None:
        """Connect and keep the shard connected until `close` is called.

        Errors on one connection (a reset socket, a corrupt compressed stream, a failing session
        store) are logged and the shard reconnects; only a close code Discord marks as final stops it.

        Raises:
            GatewayFatalError: Discord closed with a code that reconnecting cannot fix.
        """
        if self._store is not None and self._session_id is None:
            try:
                await self._restore_session(self._store)
            except Exception:  # noqa: BLE001 - without a saved session the shard identifies, which is fine
                _log.exception("shard %d: could not load the saved session; identifying", self._shard_id)
        failures = 0
        try:
            while not self._closing:
                await self._expire_old_session()
                self._state = ShardState.CONNECTING
                try:
                    connection = await self._connector.connect(self._url())
                except OSError as error:
                    failures += 1
                    delay = backoff_delay(
                        failures, cap=RECONNECT_BACKOFF_CAP, random_source=self._random_source
                    )
                    _log.warning(
                        "shard %d: connect failed (%s); retrying in %.1fs", self._shard_id, error, delay
                    )
                    self._resume_attempt_failed()
                    await self._pause(delay)
                    continue
                outcome, ready_for = await self._serve(connection)
                self._metrics.set(GATEWAY_SHARD_READY, 0, self._labels)
                if ready_for is not None:
                    self._disconnected_at = self._clock.monotonic()
                if outcome is _Next.STOP:
                    break
                if outcome is _Next.IDENTIFY:
                    await self._forget_session()
                elif ready_for is None and outcome is _Next.RESUME:
                    self._resume_attempt_failed()
                mode = "resume" if self._session_id is not None else "identify"
                self._metrics.increment(GATEWAY_RECONNECTS, {**self._labels, "mode": mode})
                # An Invalid Session that needs a new identify has already waited 1-5 s.
                requested = outcome in {_Next.RESUME_REQUESTED, _Next.IDENTIFY}
                stable = ready_for is not None and ready_for >= STABLE_CONNECTION
                failures = 0 if requested or stable else failures + 1
                if failures:
                    await self._pause(
                        backoff_delay(failures, cap=RECONNECT_BACKOFF_CAP, random_source=self._random_source)
                    )
        finally:
            self._state = ShardState.CLOSED
            if self._owns_connector:
                await self._connector.close()

    async def close(self, *, resumable: bool = True) -> None:
        """Disconnect.

        Args:
            resumable: Keep the session alive and save it to the session store, so the next
                `Shard` for this shard ID (in this process or after a restart) resumes instead of
                identifying. Pass `False` to end the session, for example when the bot is shutting
                down for good.

        A closed shard does not run again; create a new one with the same session store.
        """
        self._closing = True
        self._stopped.set()
        connection = self._connection
        if connection is not None:
            await connection.close(RESUMABLE_CLOSE_CODE if resumable else 1000)
        # Read after the socket is closed, so the sequence covers every event that was dispatched
        # and a resume never replays one twice.
        if resumable:
            await self._persist()
        else:
            # Ended for good: a later `close()` must not save it again.
            await self._forget_session()

    async def send_command(self, opcode: GatewayOpcode, data: msgspec.Struct) -> None:
        """Send a gateway command (presence, voice state, member and soundboard requests).

        Raises:
            ValueError: `opcode` is not a command an app may send.
            ShardNotConnectedError: The shard has no open connection.
        """
        if not opcode.is_command:
            msg = f"{opcode.name} is managed by the shard and cannot be sent directly"
            raise ValueError(msg)
        connection, limiter = self._connection, self._limiter
        if connection is None or limiter is None or self._state is not ShardState.READY:
            msg = f"shard {self._shard_id} is not connected"
            raise ShardNotConnectedError(msg)
        await self._send(connection, limiter, opcode, data)

    async def update_presence(self, presence: UpdatePresence) -> None:
        """Change the bot's presence on this shard.

        Discord: https://docs.discord.com/developers/events/gateway-events#update-presence
        """
        self._presence = presence
        await self.send_command(GatewayOpcode.PRESENCE_UPDATE, presence)

    async def request_guild_members(self, request: RequestGuildMembers) -> None:
        """Ask for guild members; the answer arrives as `GUILD_MEMBERS_CHUNK` dispatches.

        Discord: https://docs.discord.com/developers/events/gateway-events#request-guild-members
        """
        await self.send_command(GatewayOpcode.REQUEST_GUILD_MEMBERS, request)

    async def update_voice_state(self, update: UpdateVoiceState) -> None:
        """Join, move or leave a voice channel.

        Discord: https://docs.discord.com/developers/events/gateway-events#update-voice-state
        """
        await self.send_command(GatewayOpcode.VOICE_STATE_UPDATE, update)

    async def request_soundboard_sounds(self, request: RequestSoundboardSounds) -> None:
        """Ask for guilds' soundboard sounds; each answer arrives as a `SOUNDBOARD_SOUNDS` dispatch.

        Every guild must be on this shard; `ShardManager.request_soundboard_sounds` splits a list
        across shards.

        Discord: https://docs.discord.com/developers/events/gateway-events#request-soundboard-sounds
        """
        await self.send_command(GatewayOpcode.REQUEST_SOUNDBOARD_SOUNDS, request)

    async def request_channel_info(self, request: RequestChannelInfo) -> None:
        """Ask for a guild's ephemeral channel data; the answer arrives as a `CHANNEL_INFO` dispatch.

        Discord: https://docs.discord.com/developers/events/gateway-events#request-channel-info
        """
        await self.send_command(GatewayOpcode.REQUEST_CHANNEL_INFO, request)

    async def _serve(self, connection: GatewayConnection) -> tuple[_Next, float | None]:
        """Run one connection. Returns what to do next and, if it became ready, for how long."""
        if self._closing:
            await connection.close(RESUMABLE_CLOSE_CODE)
            return _Next.STOP, None
        self._connection = connection
        decompressor = create_decompressor(self._compression)
        limiter = GatewaySendLimiter(self._clock)
        heartbeat: asyncio.Task[None] | None = None
        ready_at: float | None = None

        def ready_for() -> float | None:
            return None if ready_at is None else self._clock.monotonic() - ready_at

        try:
            hello = await self._hello(connection, decompressor)
            if isinstance(hello, _Next):
                return hello, None
            monitor = HeartbeatMonitor(hello.heartbeat_interval)
            self._monitor = monitor
            self._limiter = limiter
            heartbeat = asyncio.create_task(self._heartbeat(connection, monitor, limiter))
            await self._start_session(connection, limiter)
            while not self._stop_requested():
                payload = await self._receive(connection, decompressor)
                if self._stop_requested():
                    # `close` saved the session while this payload was in flight; handling it now
                    # would move the sequence past the saved one and a resume would replay it.
                    break
                if isinstance(payload, _Closed):
                    return self._after_close(payload.code), ready_for()
                outcome = await self._handle(payload, connection, monitor, limiter)
                if ready_at is None and self._state is ShardState.READY:
                    ready_at = self._clock.monotonic()
                if outcome is not None:
                    return outcome, ready_for()
            return _Next.STOP, ready_for()
        except GatewayFatalError:
            raise
        except Exception:  # noqa: BLE001 - one broken connection must never end the shard
            _log.exception("shard %d: connection failed; reconnecting", self._shard_id)
            return _Next.RESUME, ready_for()
        finally:
            self._reading = False
            if heartbeat is not None:
                await self._stop_heartbeat(heartbeat)
            self._connection = None
            self._limiter = None
            # Frees the socket on every path; a socket that is already closed ignores it.
            try:
                await connection.close(RESUMABLE_CLOSE_CODE)
            except Exception:  # noqa: BLE001 - the connection is gone either way
                _log.debug("shard %d: closing the connection failed", self._shard_id, exc_info=True)

    async def _hello(self, connection: GatewayConnection, decompressor: Decompressor | None) -> Hello | _Next:
        """Wait for Hello. Returns what to do instead when it does not arrive."""
        try:
            async with asyncio.timeout(HELLO_TIMEOUT):
                first = await self._receive(connection, decompressor)
        except TimeoutError:
            _log.warning("shard %d: no Hello within %.0fs; reconnecting", self._shard_id, HELLO_TIMEOUT)
            return _Next.RESUME
        if isinstance(first, _Closed):
            return self._after_close(first.code)
        if first.op is not GatewayOpcode.HELLO:
            _log.warning("shard %d: expected Hello, got %s; reconnecting", self._shard_id, first.op.name)
            return _Next.RESUME
        return decode_json(first.d, Hello)

    async def _stop_heartbeat(self, heartbeat: asyncio.Task[None]) -> None:
        error = await cancel_and_wait(heartbeat)
        if error is not None:
            # A send on a socket that was closing; the connection is being replaced either way.
            _log.debug("shard %d: heartbeat ended with %r", self._shard_id, error)

    async def _start_session(self, connection: GatewayConnection, limiter: GatewaySendLimiter) -> None:
        if self._session_id is not None and self._sequence is not None:
            self._state = ShardState.RESUMING
            resume = Resume(token=self._token, session_id=self._session_id, seq=self._sequence)
            await self._send(connection, limiter, GatewayOpcode.RESUME, resume)
            return
        self._state = ShardState.IDENTIFYING
        identify = Identify(
            token=self._token,
            properties=IdentifyConnectionProperties(
                os=platform.system().lower() or "unknown",
                browser=f"shoal/{__version__}",
                device=f"shoal/{__version__}",
            ),
            large_threshold=self._large_threshold,
            shard=(self._shard_id, self._shard_count),
            presence=self._presence if self._presence is not None else UNSET,
            intents=self._intents,
            capabilities=self._capabilities if self._capabilities is not None else UNSET,
        )
        async with self._identify_limiter.slot(self._shard_id):
            await self._send(connection, limiter, GatewayOpcode.IDENTIFY, identify)

    async def _handle(
        self,
        payload: GatewayPayload,
        connection: GatewayConnection,
        monitor: HeartbeatMonitor,
        limiter: GatewaySendLimiter,
    ) -> _Next | None:
        match payload.op:
            case GatewayOpcode.DISPATCH:
                await self._on_dispatch(payload)
            case GatewayOpcode.HEARTBEAT:
                # Discord asked for a beat now; it does not replace the scheduled beat's tracking.
                await self._send(connection, limiter, GatewayOpcode.HEARTBEAT, self._sequence, priority=True)
            case GatewayOpcode.HEARTBEAT_ACK:
                monitor.acknowledged(self._clock.monotonic())
                if monitor.latency is not None:
                    self._metrics.set(GATEWAY_LATENCY_SECONDS, monitor.latency, self._labels)
            case GatewayOpcode.RECONNECT:
                _log.info("shard %d: Discord asked us to reconnect", self._shard_id)
                await connection.close(RESUMABLE_CLOSE_CODE)
                return _Next.RESUME_REQUESTED
            case GatewayOpcode.INVALID_SESSION:
                resumable = decode_json(payload.d, bool)
                _log.info("shard %d: session invalidated (resumable=%s)", self._shard_id, resumable)
                await connection.close(RESUMABLE_CLOSE_CODE)
                if resumable:
                    return _Next.RESUME_REQUESTED
                await self._pause(self._random_source.uniform(*INVALID_SESSION_DELAY))
                return _Next.IDENTIFY
            case _:
                _log.debug("shard %d: ignoring opcode %s", self._shard_id, payload.op)
        return None

    async def _on_dispatch(self, payload: GatewayPayload) -> None:
        if payload.s is not None:
            self._sequence = payload.s
        name = payload.t or ""
        if name == "READY":
            ready = decode_json(payload.d, Ready)
            self._session_id = ready.session_id
            self._resume_url = ready.resume_gateway_url
            self._state = ShardState.READY
            self._metrics.set(GATEWAY_SHARD_READY, 1, self._labels)
            _log.info("shard %d: ready with %d guilds", self._shard_id, len(ready.guilds))
            await self._persist()
        elif name == "RESUMED":
            self._state = ShardState.READY
            self._metrics.set(GATEWAY_SHARD_READY, 1, self._labels)
            _log.info("shard %d: resumed", self._shard_id)
            await self._persist()
        elif name == "RATE_LIMITED":
            self._log_rate_limited(payload.d)
        self._metrics.increment(GATEWAY_EVENTS, {**self._labels, "event": name})
        if name in DELAY_TRACKED_EVENTS:
            self._track_delay(name, payload.d)
        try:
            await self._dispatch(DispatchEvent(self._shard_id, name, payload.s, payload.d))
        except Exception:  # noqa: BLE001 - a failing handler must never take the shard down
            _log.exception("shard %d: dispatch handler failed for %s", self._shard_id, name)

    def _log_rate_limited(self, data: msgspec.Raw) -> None:
        try:
            limited = decode_json(data, RateLimited)
        except PayloadDecodeError:
            _log.warning("shard %d: a gateway command was rate limited", self._shard_id)
            return
        _log.warning(
            "shard %d: Discord rate limited %s; retry after %.1fs",
            self._shard_id,
            limited.opcode.name,
            limited.retry_after,
        )

    def _track_delay(self, name: str, data: msgspec.Raw) -> None:
        try:
            created = decode_json(data, _CreatedObject).id
        except PayloadDecodeError:
            return
        delay = max(0.0, self._clock.wall() - created.timestamp_ms / 1000)
        self._metrics.observe(GATEWAY_EVENT_DELAY_SECONDS, delay, {**self._labels, "event": name})
        threshold = self._event_delay_warning
        if threshold is None or delay < threshold:
            return
        now = self._clock.monotonic()
        if (
            self._last_delay_warning is not None
            and now - self._last_delay_warning < EVENT_DELAY_WARNING_COOLDOWN
        ):
            return
        self._last_delay_warning = now
        latency = self.latency
        latency_text = f"{latency * 1000:.0f}ms" if latency is not None else "not measured yet"
        _log.warning(
            "shard %d: %s arrived %.1fs after it was created, while heartbeat latency is %s. "
            "Events are queuing before your code sees them: check for a blocked event loop "
            "(shoal.diagnostics.LoopMonitor names the blocking call), an overloaded process, or "
            "a system clock that is out of sync (enable NTP).",
            self._shard_id,
            name,
            delay,
            latency_text,
        )

    async def _heartbeat(
        self, connection: GatewayConnection, monitor: HeartbeatMonitor, limiter: GatewaySendLimiter
    ) -> None:
        await self._clock.sleep(monitor.first_delay(self._random_source.random()))
        while True:
            # Unread ACKs may be waiting while the receive loop is busy (identifying, or a slow
            # dispatch handler), so only a reader that has caught up can prove the link is dead.
            if monitor.is_zombie() and self._reading:
                _log.warning("shard %d: heartbeat not acknowledged; reconnecting", self._shard_id)
                await connection.close(RESUMABLE_CLOSE_CODE)
                return
            await self._beat(connection, monitor, limiter)
            await self._clock.sleep(monitor.interval)

    async def _beat(
        self, connection: GatewayConnection, monitor: HeartbeatMonitor, limiter: GatewaySendLimiter
    ) -> None:
        await self._send(connection, limiter, GatewayOpcode.HEARTBEAT, self._sequence, priority=True)
        monitor.sent(self._clock.monotonic())

    async def _send(
        self,
        connection: GatewayConnection,
        limiter: GatewaySendLimiter,
        opcode: GatewayOpcode,
        data: object,
        *,
        priority: bool = False,
    ) -> None:
        await limiter.acquire(priority=priority)
        await connection.send(encode_json({"op": int(opcode), "d": data}))

    async def _receive(
        self, connection: GatewayConnection, decompressor: Decompressor | None
    ) -> GatewayPayload | _Closed:
        while True:
            self._reading = True
            try:
                message = await connection.receive()
            finally:
                self._reading = False
            if message.kind is MessageKind.CLOSED:
                return _Closed(message.close_code)
            data = message.data
            if message.kind is MessageKind.BINARY and decompressor is not None:
                inflated = decompressor.feed(message.data)
                if inflated is None:
                    continue
                data = inflated
            try:
                return decode_json(data, GatewayPayload)
            except PayloadDecodeError:
                _log.exception("shard %d: undecodable gateway payload dropped", self._shard_id)

    def _after_close(self, code: int | None) -> _Next:
        if self._closing:
            return _Next.STOP
        if code is not None and GatewayCloseCode.is_gateway_code(code) and code != RESUMABLE_CLOSE_CODE:
            close_code = GatewayCloseCode(code)
            if not close_code.can_reconnect:
                raise GatewayFatalError(self._shard_id, close_code)
            _log.info("shard %d: closed with %s; reconnecting", self._shard_id, close_code.name)
            if close_code.invalidates_session:
                return _Next.IDENTIFY
        elif code in SESSION_ENDING_CLOSE_CODES:
            _log.info("shard %d: closed with %s; trying to resume", self._shard_id, code)
        return _Next.RESUME

    def _resume_attempt_failed(self) -> None:
        """A connection attempt carrying a session failed before the session was confirmed.

        Discord's guidance: when the resume URL fails for any reason (timeout, an HTTP error such as
        503 during the handshake, an early close), fall back to the main gateway URL, where resuming
        is still allowed. The session itself is kept: only Discord can reject it (Invalid Session
        starts a new one), and it expires on its own after `resume_window`.
        """
        if self._session_id is None or self._resume_url is None:
            return
        _log.warning(
            "shard %d: resume URL %s failed; resuming through the main gateway instead",
            self._shard_id,
            self._resume_url,
        )
        self._resume_url = None

    async def _restore_session(self, store: SessionStore) -> None:
        """Pick up the session saved before a restart, if it is still usable."""
        saved = await store.load(self._shard_id, self._shard_count)
        if saved is None:
            return
        if not self._trusted_resume_url(saved.resume_gateway_url):
            # The token is sent to this URL, so a file on disk must not be able to redirect it.
            _log.warning(
                "shard %d: saved resume URL is not a secure gateway URL; starting a new session",
                self._shard_id,
            )
            await store.delete(self._shard_id)
            return
        _log.info("shard %d: resuming saved session from before the restart", self._shard_id)
        self._session_id = saved.session_id
        self._sequence = saved.sequence
        self._resume_url = saved.resume_gateway_url
        age = max(0.0, self._clock.wall() - saved.saved_at)
        self._disconnected_at = self._clock.monotonic() - age

    def _trusted_resume_url(self, url: str) -> bool:
        """`wss://`, or the same scheme and host as the configured gateway (a local proxy)."""
        parts, configured = urlsplit(url), urlsplit(self._gateway_url)
        return parts.scheme == "wss" or (parts.scheme, parts.netloc) == (configured.scheme, configured.netloc)

    def _stop_requested(self) -> bool:
        """`close` was called. A method, so type checkers do not narrow the flag across awaits."""
        return self._closing

    async def _pause(self, seconds: float) -> None:
        """Sleep, but wake as soon as `close` is called."""
        await sleep_unless(self._clock, seconds, self._stopped)

    async def _expire_old_session(self) -> None:
        """Drop a session that has been disconnected longer than Discord keeps sessions resumable."""
        if self._session_id is None or self._disconnected_at is None:
            return
        if self._clock.monotonic() - self._disconnected_at > self._resume_window:
            _log.info("shard %d: disconnected too long to resume; starting a new session", self._shard_id)
            await self._forget_session()

    async def _forget_session(self) -> None:
        self._session_id = None
        self._resume_url = None
        self._sequence = None
        self._disconnected_at = None
        if self._store is None:
            return
        async with self._store_lock:
            try:
                await self._store.delete(self._shard_id)
            except Exception:  # noqa: BLE001 - a stale file only costs one failed resume
                _log.exception("shard %d: could not delete the saved session", self._shard_id)

    async def _persist(self) -> None:
        """Save the current session.

        Store calls are serialised and the session is read inside the lock, so a save never lands
        after a delete that ended the session.
        """
        if self._store is None:
            return
        async with self._store_lock:
            session = self.session
            if session is None:
                return
            try:
                await self._store.save(session)
            except Exception:  # noqa: BLE001 - the connection is fine; only a restart cannot resume
                _log.exception("shard %d: could not save the session", self._shard_id)
