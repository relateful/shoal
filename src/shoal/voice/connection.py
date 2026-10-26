"""One voice session: the voice gateway websocket, the UDP socket, encryption and DAVE.

    connection = VoiceConnection(server, user_id=bot_id)
    await connection.connect()
    await connection.speak()
    connection.send_frame(opus_packet)

The handshake follows Discord's order: Identify, Ready (the SSRC and the voice server's UDP address),
IP discovery, Select Protocol, then Session Description (the encryption key and the DAVE version).
Heartbeats acknowledge the last numbered message (voice gateway v8), so a resumed session gets what
it missed. A dropped socket or a crashed voice server is resumed; any other close ends the
connection, and `closed` says why: Discord ended it, or the session must start over from a new voice
state update.

Discord: https://docs.discord.com/developers/topics/voice-connections
"""

import asyncio
import contextlib
import logging
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Final, final

import msgspec
from cryptography.exceptions import InvalidTag

from shoal.core.backoff import backoff_delay
from shoal.core.clock import Clock, SystemClock, within
from shoal.core.codec import PayloadDecodeError, decode_json, encode_json
from shoal.core.errors import ShoalError
from shoal.core.metrics import VOICE_PACKETS_DROPPED, VOICE_RECONNECTS, Metrics, NoopMetrics
from shoal.core.snowflake import Snowflake
from shoal.core.tasks import cancel_and_wait
from shoal.gateway.connection import AiohttpGatewayConnector, GatewayConnection, GatewayConnector, MessageKind
from shoal.payloads.voice_gateway import (
    RTP_PAYLOAD_TYPE,
    VOICE_GATEWAY_VERSION,
    ClientDisconnect,
    ClientsConnect,
    EncryptionMode,
    SelectProtocol,
    SelectProtocolData,
    SessionDescription,
    Speaking,
    SpeakingFlags,
    VoiceCloseCode,
    VoiceHeartbeat,
    VoiceHeartbeatAck,
    VoiceHello,
    VoiceIdentify,
    VoiceOpcode,
    VoicePayload,
    VoiceReady,
    VoiceResume,
)
from shoal.voice.crypto import TransportCipher
from shoal.voice.dave import MAX_PROTOCOL_VERSION, Dave
from shoal.voice.defaults import (
    JOIN_TIMEOUT,
    RECEIVED_PACKETS_QUEUE_SIZE,
    RESUME_ATTEMPTS,
    RESUME_BACKOFF_CAP,
    STABLE_SESSION,
    UNANSWERED_HEARTBEATS,
)
from shoal.voice.rtp import opus_samples, rtp_header
from shoal.voice.udp import UdpTransportFactory, VoiceTransport, VoiceTransportFactory, discover

_log = logging.getLogger("shoal.voice")

_ENDED: Final = 1000
"""The close code that ends the voice session."""

_PREFERRED_MODES: Final = (
    EncryptionMode.AEAD_AES256_GCM_RTPSIZE,
    EncryptionMode.AEAD_XCHACHA20_POLY1305_RTPSIZE,
)
"""Encryption modes in the order Discord recommends them."""

_RTP_PAYLOAD_TYPE_MASK: Final = 0x7F
"""The payload type bits of an RTP header's second byte (the top bit is the marker)."""

_ZOMBIE: Final = 4000
"""The close code Shoal uses on a socket it gives up on (unanswered heartbeats, a stalled resume);
the session is resumed after it."""


@dataclass(frozen=True, slots=True)
class VoiceServer:
    """Where a voice session runs, from the main gateway's voice state and voice server updates.

    Attributes:
        guild_id: The guild of the voice channel.
        channel_id: The voice channel.
        session_id: The bot's voice state `session_id`.
        token: The voice server update's `token`.
        endpoint: The voice server update's `endpoint` (host and port, without a scheme).
    """

    guild_id: int
    channel_id: int
    session_id: str
    token: str = field(repr=False)
    endpoint: str


@dataclass(frozen=True, slots=True)
class VoicePacket:
    """One Opus packet received from someone in the call.

    Attributes:
        user_id: Who sent it.
        ssrc: The sender's SSRC.
        sequence: The RTP sequence number.
        timestamp: The RTP timestamp, in samples at 48 kHz.
        opus: The Opus packet, decrypted. Left out of the repr: it is someone's voice.
    """

    user_id: int
    ssrc: int
    sequence: int
    timestamp: int
    opus: bytes = field(repr=False)


class VoiceConnectionClosedError(ShoalError):
    """The voice connection ended.

    Args:
        code: The voice gateway's close code, or `None` when the socket dropped without one.
        reason: What happened.
    """

    def __init__(self, code: int | None, reason: str) -> None:
        """Create the error; see the class docstring for the arguments."""
        super().__init__(reason)
        self.code: int | None = code

    @property
    def ends_connection(self) -> bool:
        """Whether Discord asked not to connect again (kicked, rate limited, the call ended)."""
        return self.code is not None and VoiceCloseCode(self.code).ends_connection


def _resumable(code: int | None) -> bool:
    """Whether a closed socket's session can be resumed: dropped, crashed, or given up on by Shoal."""
    return code is None or code < 4000 or code in (VoiceCloseCode.VOICE_SERVER_CRASHED, _ZOMBIE)  # noqa: PLR2004 - Discord's codes start at 4000


@final
class VoiceConnection:
    """A voice session in one channel: connect, then send frames (and receive them, if wanted).

    Args:
        server: Where the session runs.
        user_id: The bot's user ID.
        connector: Opens the voice websocket. Defaults to aiohttp.
        transports: Opens the UDP socket. Defaults to the event loop's.
        metrics: Receives `shoal_voice_packets_dropped_total` and `shoal_voice_reconnects_total`.
        clock: Time source for heartbeats and timeouts.
        random_source: Random source for reconnect jitter.
    """

    __slots__ = (
        "_cipher",
        "_clock",
        "_closed",
        "_connector",
        "_dave",
        "_described",
        "_finishing",
        "_heartbeat",
        "_latency",
        "_listeners",
        "_metrics",
        "_owns_connector",
        "_random_source",
        "_reader",
        "_ready",
        "_receiver",
        "_resumed",
        "_seq_ack",
        "_sequence",
        "_server",
        "_ssrc",
        "_ssrc_users",
        "_supervisor",
        "_timestamp",
        "_transport",
        "_transports",
        "_unanswered",
        "_user_id",
        "_websocket",
    )

    def __init__(
        self,
        server: VoiceServer,
        *,
        user_id: int,
        connector: GatewayConnector | None = None,
        transports: VoiceTransportFactory | None = None,
        metrics: Metrics | None = None,
        clock: Clock | None = None,
        random_source: random.Random | None = None,
    ) -> None:
        """Create a connection; see the class docstring for the arguments. Call `connect`."""
        self._server: VoiceServer = server
        self._user_id: int = user_id
        self._owns_connector: bool = connector is None
        self._connector: GatewayConnector = connector or AiohttpGatewayConnector()
        self._transports: VoiceTransportFactory = transports or UdpTransportFactory()
        self._metrics: Metrics = metrics or NoopMetrics()
        self._clock: Clock = clock or SystemClock()
        self._random_source: random.Random = random_source or random.Random()  # noqa: S311 - jitter, not security
        self._websocket: GatewayConnection | None = None
        self._transport: VoiceTransport | None = None
        self._cipher: TransportCipher | None = None
        self._dave: Dave = Dave(
            user_id=user_id, channel_id=server.channel_id, send_json=self._send, send_binary=self._send_binary
        )
        self._ssrc: int = 0
        self._sequence: int = 0
        self._timestamp: int = 0
        self._seq_ack: int = -1
        """The last numbered message received, acknowledged in heartbeats and resumes."""
        self._ssrc_users: dict[int, int] = {}
        self._latency: float | None = None
        self._unanswered: int = 0
        loop = asyncio.get_running_loop()
        self._ready: asyncio.Future[VoiceReady] = loop.create_future()
        self._described: asyncio.Future[None] = loop.create_future()
        self._resumed: asyncio.Future[None] | None = None
        self._closed: asyncio.Future[VoiceConnectionClosedError | None] = loop.create_future()
        self._reader: asyncio.Task[int | None] | None = None
        self._heartbeat: asyncio.Task[None] | None = None
        self._supervisor: asyncio.Task[None] | None = None
        self._receiver: asyncio.Task[None] | None = None
        self._finishing: asyncio.Task[None] | None = None
        """Closes everything once; every caller of `close` waits for the same run."""
        self._listeners: set[asyncio.Queue[VoicePacket | None]] = set()

    @property
    def server(self) -> VoiceServer:
        """Where the session runs."""
        return self._server

    @property
    def ssrc(self) -> int:
        """The bot's SSRC in the call, once Ready."""
        return self._ssrc

    @property
    def latency(self) -> float | None:
        """The last heartbeat round trip in seconds, once measured."""
        return self._latency

    @property
    def dave(self) -> Dave:
        """The connection's end-to-end encryption state."""
        return self._dave

    @property
    def is_connected(self) -> bool:
        """Whether the session is up: described, and not closing."""
        return self._cipher is not None and self._finishing is None

    @property
    def closed(self) -> "asyncio.Future[VoiceConnectionClosedError | None]":
        """Resolves once the connection has ended and closed both sockets: `None` after `close`, else why.

        Each access is a new view of the outcome, so cancelling one wait cancels nothing else.
        """
        return asyncio.shield(self._closed)

    async def connect(self) -> None:
        """Run the handshake; return once the session can carry audio.

        Raises:
            TimeoutError: The handshake did not finish within `JOIN_TIMEOUT`.
            VoiceConnectionClosedError: The voice gateway closed the connection during it, or offers
                no encryption mode Shoal supports.
            OSError: The websocket or the UDP socket could not be opened.
        """
        try:
            await within(self._clock, JOIN_TIMEOUT, self._handshake())
        except BaseException:
            # Shielded: a cancelled connect must still close what the handshake opened.
            await asyncio.shield(self.close())
            raise
        self._supervisor = asyncio.create_task(self._supervise(), name="shoal-voice")
        self._receiver = asyncio.create_task(self._receive(), name="shoal-voice-receive")

    async def _handshake(self) -> None:
        await self._open()
        await self._send(
            VoiceOpcode.IDENTIFY,
            VoiceIdentify(
                server_id=Snowflake(self._server.guild_id),
                user_id=Snowflake(self._user_id),
                session_id=self._server.session_id,
                token=self._server.token,
                max_dave_protocol_version=MAX_PROTOCOL_VERSION,
            ),
        )
        ready = await self._ready
        self._ssrc = ready.ssrc
        self._transport = await self._transports.connect(ready.ip, ready.port)
        address, port = await discover(self._transport, ready.ssrc, self._clock)
        mode = next((mode for mode in _PREFERRED_MODES if mode in ready.modes), None)
        if mode is None:
            msg = f"the voice server offers no encryption mode Shoal supports ({ready.modes})"
            raise VoiceConnectionClosedError(None, msg)
        data = SelectProtocolData(address=address, port=port, mode=mode)
        await self._send(VoiceOpcode.SELECT_PROTOCOL, SelectProtocol(protocol="udp", data=data))
        await self._described

    async def _open(self) -> None:
        """Open a websocket (closing any previous one) and start reading it."""
        await self._drop_socket(_ZOMBIE)
        websocket = await self._connector.connect(f"wss://{self._server.endpoint}/?v={VOICE_GATEWAY_VERSION}")
        self._websocket = websocket
        self._unanswered = 0
        self._reader = asyncio.create_task(self._read(websocket), name="shoal-voice-gateway")

    async def _drop_socket(self, code: int) -> None:
        websocket, self._websocket = self._websocket, None
        if websocket is not None:
            with contextlib.suppress(OSError):
                await websocket.close(code)

    async def _resume(self) -> None:
        resumed: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._resumed = resumed
        await self._open()
        await self._send(
            VoiceOpcode.RESUME,
            VoiceResume(
                server_id=Snowflake(self._server.guild_id),
                session_id=self._server.session_id,
                token=self._server.token,
                seq_ack=self._seq_ack,
            ),
        )
        await resumed

    async def _supervise(self) -> None:
        """Resume the session each time its socket closes in a way that allows it; else end."""
        attempts = 0
        up_since: float | None = self._clock.monotonic()
        """When the session last came up; `None` while attempts to bring it back keep failing."""
        while True:
            reader = self._reader
            code = await reader if reader is not None else None
            await self._stop_heartbeat()
            if not _resumable(code):
                reason = f"the voice gateway closed the connection ({_describe(code)})"
                await self._end(VoiceConnectionClosedError(code, reason))
                return
            # A session that stayed up starts a new count; one lost again at once keeps backing off.
            if up_since is not None and self._clock.monotonic() - up_since >= STABLE_SESSION:
                attempts = 0
            up_since = None
            attempts += 1
            if attempts > RESUME_ATTEMPTS:
                await self._end(VoiceConnectionClosedError(code, "the voice session could not be resumed"))
                return
            if attempts > 1:
                delay = backoff_delay(attempts - 1, cap=RESUME_BACKOFF_CAP, random_source=self._random_source)
                await self._clock.sleep(delay)
            _log.info("voice connection to %s lost (%s); resuming", self._server.endpoint, _describe(code))
            try:
                await within(self._clock, JOIN_TIMEOUT, self._resume())
            except (OSError, TimeoutError, VoiceConnectionClosedError) as error:
                _log.warning("resuming the voice connection failed: %r", error)
                # Give the socket up: its reader then ends, and the next attempt starts.
                await self._drop_socket(_ZOMBIE)
                continue
            self._metrics.increment(VOICE_RECONNECTS, {"mode": "resume"})
            up_since = self._clock.monotonic()

    async def _read(self, websocket: GatewayConnection) -> int | None:
        """Handle the socket's messages until it closes; return its close code."""
        while True:
            message = await websocket.receive()
            if message.kind is MessageKind.CLOSED:
                code = message.close_code
                reason = f"the voice gateway closed the connection ({_describe(code)})"
                for step in (self._ready, self._described, self._resumed):
                    if step is not None and not step.done():
                        step.set_exception(VoiceConnectionClosedError(code, reason))
                        # Awaited only if the handshake gets that far: no "never retrieved" log.
                        _ = step.exception()
                return code
            try:
                if message.kind is MessageKind.BINARY:
                    await self._handle_binary(message.data)
                else:
                    await self._handle(message.data)
            except (PayloadDecodeError, msgspec.DecodeError, ValueError, OSError) as error:
                _log.warning("skipping a voice gateway message that could not be handled: %r", error)

    async def _handle(self, raw: bytes) -> None:
        payload = decode_json(raw, VoicePayload)
        if isinstance(payload.seq, int):
            self._seq_ack = payload.seq
        op = payload.op
        if op is VoiceOpcode.HELLO:
            interval = decode_json(payload.d, VoiceHello).heartbeat_interval / 1000
            await self._stop_heartbeat()
            self._heartbeat = asyncio.create_task(self._beat(interval), name="shoal-voice-heartbeat")
        elif op is VoiceOpcode.READY:
            _resolve(self._ready, decode_json(payload.d, VoiceReady))
        elif op is VoiceOpcode.SESSION_DESCRIPTION:
            description = decode_json(payload.d, SessionDescription)
            self._cipher = TransportCipher(description.mode, bytes(description.secret_key))
            await self._dave.start(description.dave_protocol_version)
            _resolve(self._described, None)
        elif op is VoiceOpcode.RESUMED and self._resumed is not None:
            _resolve(self._resumed, None)
        elif op is VoiceOpcode.HEARTBEAT_ACK:
            sent = decode_json(payload.d, VoiceHeartbeatAck).t
            self._unanswered = 0
            self._latency = max(self._clock.wall() * 1000 - sent, 0) / 1000
        elif op is VoiceOpcode.SPEAKING:
            speaking = decode_json(payload.d, Speaking)
            if isinstance(speaking.user_id, int):
                self._ssrc_users[speaking.ssrc] = int(speaking.user_id)
        elif op is VoiceOpcode.CLIENTS_CONNECT:
            self._dave.users_joined(int(user) for user in decode_json(payload.d, ClientsConnect).user_ids)
        elif op is VoiceOpcode.CLIENT_DISCONNECT:
            gone = int(decode_json(payload.d, ClientDisconnect).user_id)
            self._dave.user_left(gone)
            self._ssrc_users = {ssrc: user for ssrc, user in self._ssrc_users.items() if user != gone}
        elif op in (
            VoiceOpcode.DAVE_PREPARE_TRANSITION,
            VoiceOpcode.DAVE_EXECUTE_TRANSITION,
            VoiceOpcode.DAVE_PREPARE_EPOCH,
        ):
            await self._dave.handle(op, payload.d)

    async def _handle_binary(self, data: bytes) -> None:
        """A binary message: a sequence number, an opcode byte, then the opcode's payload."""
        if len(data) < 3:  # noqa: PLR2004 - the sequence number and the opcode
            msg = "a binary voice gateway message is too short"
            raise ValueError(msg)
        self._seq_ack = int.from_bytes(data[:2], "big")
        await self._dave.handle_binary(VoiceOpcode(data[2]), data[3:])

    async def _beat(self, interval: float) -> None:
        while True:
            await self._clock.sleep(interval)
            websocket = self._websocket
            if websocket is None:
                return
            if self._unanswered >= UNANSWERED_HEARTBEATS:
                _log.warning("voice heartbeats went unanswered; reconnecting")
                await websocket.close(_ZOMBIE)
                return
            self._unanswered += 1
            beat = VoiceHeartbeat(t=round(self._clock.wall() * 1000), seq_ack=self._seq_ack)
            with contextlib.suppress(OSError):
                await self._send(VoiceOpcode.HEARTBEAT, beat)

    async def _stop_heartbeat(self) -> None:
        heartbeat, self._heartbeat = self._heartbeat, None
        if heartbeat is not None and heartbeat is not asyncio.current_task():
            await cancel_and_wait(heartbeat)

    async def _send(self, op: VoiceOpcode, data: msgspec.Struct) -> None:
        websocket = self._websocket
        if websocket is not None:
            await websocket.send(encode_json({"op": int(op), "d": data}))

    async def _send_binary(self, op: VoiceOpcode, payload: bytes) -> None:
        websocket = self._websocket
        if websocket is not None:
            await websocket.send_binary(bytes([op]) + payload)

    async def speak(self, flags: SpeakingFlags | None = None) -> None:
        """Tell the call the bot transmits (the microphone by default); needed before any audio.

        Discord: https://docs.discord.com/developers/topics/voice-connections#speaking
        """
        speaking = flags if flags is not None else SpeakingFlags(microphone=True)
        await self._send(VoiceOpcode.SPEAKING, Speaking(speaking=speaking, delay=0, ssrc=self._ssrc))

    def send_frame(self, opus: bytes) -> None:
        """Send one Opus packet: end-to-end encrypted while DAVE is in effect, then sealed.

        Pace the calls yourself (one packet per its duration); `AudioPlayer` does.

        Raises:
            VoiceConnectionClosedError: The connection is not up.
            ValueError: `opus` is not an Opus packet (nothing is sent).
        """
        cipher, transport = self._cipher, self._transport
        if cipher is None or transport is None or self._finishing is not None:
            msg = "the voice connection is not connected"
            raise VoiceConnectionClosedError(None, msg)
        samples = opus_samples(opus)
        header = rtp_header(self._sequence, self._timestamp, self._ssrc)
        transport.send(cipher.seal(header, self._dave.encrypt(opus)))
        self._sequence = (self._sequence + 1) & 0xFFFF
        self._timestamp = (self._timestamp + samples) & 0xFFFFFFFF

    async def packets(self) -> AsyncIterator[VoicePacket]:
        """Yield the Opus packets received from the call until the connection ends.

        Each iteration gets every packet. Packets are only kept while something iterates, and an
        iteration that falls `RECEIVED_PACKETS_QUEUE_SIZE` behind loses the oldest.
        """
        if self._closed.done():
            return
        queue: asyncio.Queue[VoicePacket | None] = asyncio.Queue(RECEIVED_PACKETS_QUEUE_SIZE)
        self._listeners.add(queue)
        try:
            while (packet := await queue.get()) is not None:
                yield packet
        finally:
            self._listeners.discard(queue)

    async def _receive(self) -> None:
        transport = self._transport
        if transport is None:
            return
        while True:
            try:
                packet = await transport.receive()
            except ConnectionError:
                return
            if not self._listeners:
                continue
            received = self._open_packet(packet)
            if received is None:
                continue
            for queue in self._listeners:
                if queue.full():
                    _ = queue.get_nowait()
                    self._metrics.increment(VOICE_PACKETS_DROPPED, {"reason": "behind"})
                queue.put_nowait(received)

    def _open_packet(self, packet: bytes) -> VoicePacket | None:
        """A received packet's audio, or `None` for anything else (RTCP, a bad seal, no key yet)."""
        cipher = self._cipher
        if cipher is None or len(packet) < 2 or packet[1] & _RTP_PAYLOAD_TYPE_MASK != RTP_PAYLOAD_TYPE:  # noqa: PLR2004 - the RTP header's first two bytes
            return None
        try:
            header, payload = cipher.unseal(packet)
        except (ValueError, InvalidTag):
            self._metrics.increment(VOICE_PACKETS_DROPPED, {"reason": "unsealed"})
            return None
        user_id = self._ssrc_users.get(header.ssrc)
        opus = self._dave.decrypt(user_id, payload) if user_id is not None else None
        if user_id is None or opus is None:
            self._metrics.increment(VOICE_PACKETS_DROPPED, {"reason": "undecrypted"})
            return None
        return VoicePacket(user_id, header.ssrc, header.sequence, header.timestamp, opus)

    async def close(self) -> None:
        """End the session and close both sockets; return once they are closed. Idempotent."""
        await self._end(None)

    async def _end(self, reason: VoiceConnectionClosedError | None) -> None:
        if self._finishing is None:
            self._finishing = asyncio.create_task(self._finish(reason), name="shoal-voice-close")
        if self._finishing is not asyncio.current_task():
            await asyncio.shield(self._finishing)

    async def _finish(self, reason: VoiceConnectionClosedError | None) -> None:
        """Close everything, then resolve `closed`: whoever awaits it finds both sockets closed."""
        for task in (self._supervisor, self._receiver, self._reader):
            if task is not None:
                await cancel_and_wait(task)
        await self._stop_heartbeat()
        await self._drop_socket(_ENDED)
        transport, self._transport = self._transport, None
        if transport is not None:
            transport.close()
        if self._owns_connector:
            await self._connector.close()
        for queue in self._listeners:
            if queue.full():
                _ = queue.get_nowait()
            queue.put_nowait(None)  # ends that `packets` iteration
        _resolve(self._closed, reason)


def _resolve[T](future: "asyncio.Future[T]", value: T) -> None:
    if not future.done():
        future.set_result(value)


def _describe(code: int | None) -> str:
    if code is None:
        return "dropped"
    return f"{code} {VoiceCloseCode(code).name}" if code >= 4000 else str(code)  # noqa: PLR2004 - Discord's codes start at 4000
