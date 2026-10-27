"""DAVE: the end-to-end encryption of every voice call, on top of Discord's protocol library.

The voice gateway runs the protocol: it announces protocol versions and MLS group changes, and the
members answer with key packages, commits and welcomes. `Dave` follows those messages and keeps an
MLS session (`davey`, a binding of the protocol's reference implementation), whose per-sender keys
encrypt each Opus frame the bot sends and decrypt those it receives. Transitions are acknowledged
(opcode 23) once prepared, and take effect when the gateway executes them (opcode 22).

Discord: https://docs.discord.com/developers/topics/voice-connections#end-to-end-encryption-dave-protocol
DAVE: https://daveprotocol.com
"""

import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Final, final

import msgspec

from shoal.core.errors import MissingDependencyError
from shoal.payloads.voice_gateway import (
    SILENCE_FRAME,
    DaveExecuteTransition,
    DaveMlsInvalidCommitWelcome,
    DavePrepareEpoch,
    DavePrepareTransition,
    DaveTransitionReady,
    VoiceOpcode,
)

try:
    import davey
except ImportError as error:  # pragma: no cover - exercised only without the extra installed
    _FEATURE = "Voice"
    raise MissingDependencyError(_FEATURE, "voice") from error

_log = logging.getLogger("shoal.voice")

MAX_PROTOCOL_VERSION: Final = davey.DAVE_PROTOCOL_VERSION
"""The highest DAVE protocol version Shoal speaks, sent in the voice Identify."""

_DOWNGRADE_PASSTHROUGH: Final = 120
"""Seconds unencrypted frames are still accepted after a downgrade to protocol 0 is announced."""

_OPERATIONS: Final = (davey.ProposalsOperationType.append, davey.ProposalsOperationType.revoke)
"""Opcode 27's operation byte: append (0) or revoke (1) the proposals."""

_PASSTHROUGH: Final = 10
"""Seconds unencrypted frames are still accepted after the call stops or starts encrypting."""

type SendJson = Callable[[VoiceOpcode, msgspec.Struct], Awaitable[None]]
type SendBinary = Callable[[VoiceOpcode, bytes], Awaitable[None]]


@final
class Dave:
    """One voice connection's DAVE state.

    Args:
        user_id: The bot's user ID.
        channel_id: The voice channel's ID (the MLS group ID).
        send_json: Sends a JSON opcode to the voice gateway.
        send_binary: Sends a binary opcode to the voice gateway.
    """

    __slots__ = (
        "_channel_id",
        "_downgraded",
        "_external_sender",
        "_members",
        "_pending",
        "_reinitializing",
        "_send_binary",
        "_send_json",
        "_session",
        "_user_id",
        "_version",
    )

    def __init__(
        self, *, user_id: int, channel_id: int, send_json: SendJson, send_binary: SendBinary
    ) -> None:
        """Create the state; `start` begins the protocol once the session is described."""
        self._user_id: int = user_id
        self._channel_id: int = channel_id
        self._send_json: SendJson = send_json
        self._send_binary: SendBinary = send_binary
        self._session: davey.DaveSession | None = None
        self._version: int = 0
        self._pending: tuple[int, int] | None = None
        """The announced transition: its ID and the protocol version it moves to."""
        self._downgraded: bool = False
        self._reinitializing: bool = False
        self._external_sender: bytes | None = None
        self._members: set[int] = set()
        """Users in the call besides the bot (opcodes 11 and 13): who proposals may add."""

    @property
    def protocol_version(self) -> int:
        """The DAVE protocol version in effect; 0 while the call is not end-to-end encrypted."""
        return self._version

    @property
    def ready(self) -> bool:
        """Whether frames are end-to-end encrypted now."""
        return self._version > 0 and self._session is not None and self._session.ready

    @property
    def privacy_code(self) -> str | None:
        """The call's voice privacy code, which members can compare to check the encryption."""
        return self._session.voice_privacy_code if self._session is not None else None

    async def start(self, protocol_version: int) -> None:
        """Begin with the version Session Description gives (0: not encrypted yet)."""
        self._version = protocol_version
        await self._reinit()

    def users_joined(self, user_ids: Iterable[int]) -> None:
        """Opcode 11: users joined the call."""
        self._members.update(user_ids)

    def user_left(self, user_id: int) -> None:
        """Opcode 13: a user left the call."""
        self._members.discard(user_id)

    async def handle(self, opcode: VoiceOpcode, data: msgspec.Raw) -> None:
        """Follow a JSON DAVE opcode (21, 22 or 24)."""
        if opcode is VoiceOpcode.DAVE_PREPARE_TRANSITION:
            transition = msgspec.json.decode(data, type=DavePrepareTransition)
            await self._prepare_transition(transition.transition_id, transition.protocol_version)
        elif opcode is VoiceOpcode.DAVE_EXECUTE_TRANSITION:
            self._execute_transition(msgspec.json.decode(data, type=DaveExecuteTransition).transition_id)
        elif opcode is VoiceOpcode.DAVE_PREPARE_EPOCH:
            epoch = msgspec.json.decode(data, type=DavePrepareEpoch)
            if epoch.epoch == 1:  # a new group: everyone starts over with a key package
                self._version = epoch.protocol_version
                await self._reinit()

    async def handle_binary(self, opcode: VoiceOpcode, payload: bytes) -> None:
        """Follow a binary DAVE opcode (25, 27, 29 or 30); `payload` follows the opcode byte."""
        if opcode is VoiceOpcode.DAVE_MLS_EXTERNAL_SENDER:
            self._external_sender = payload
            if self._session is not None:
                self._session.set_external_sender(payload)
        elif opcode is VoiceOpcode.DAVE_MLS_PROPOSALS:
            await self._proposals(payload)
        elif opcode in (VoiceOpcode.DAVE_MLS_ANNOUNCE_COMMIT_TRANSITION, VoiceOpcode.DAVE_MLS_WELCOME):
            await self._commit_or_welcome(opcode, payload)

    def encrypt(self, frame: bytes) -> bytes:
        """An Opus frame to send: end-to-end encrypted while the call is (silence never is)."""
        if not self.ready or frame == SILENCE_FRAME or self._session is None:
            return frame
        return self._session.encrypt_opus(frame)

    def decrypt(self, user_id: int, frame: bytes) -> bytes | None:
        """A received Opus frame, decrypted; `None` when it cannot be (it is dropped).

        Unencrypted frames pass while the call is not encrypted, and for a while around a
        transition (passthrough).
        """
        session = self._session
        if frame == SILENCE_FRAME:
            return frame
        if session is None or not session.ready:
            return frame if self._version == 0 else None
        if self._version == 0 and not session.can_passthrough(user_id):
            return frame
        try:
            return session.decrypt(user_id, davey.MediaType.audio, frame)
        except ValueError:
            return frame if session.can_passthrough(user_id) else None

    async def _reinit(self) -> None:
        if self._version > 0:
            if self._session is None:
                self._session = davey.DaveSession(self._version, self._user_id, self._channel_id)
            else:
                self._session.reinit(self._version, self._user_id, self._channel_id)
            if self._external_sender is not None:
                self._session.set_external_sender(self._external_sender)
            await self._send_binary(
                VoiceOpcode.DAVE_MLS_KEY_PACKAGE, self._session.get_serialized_key_package()
            )
        elif self._session is not None:
            self._session.reset()
            self._session.set_passthrough_mode(passthrough_mode=True, transition_expiry=_PASSTHROUGH)

    async def _prepare_transition(self, transition_id: int, protocol_version: int) -> None:
        self._pending = (transition_id, protocol_version)
        if transition_id == 0:
            self._execute_transition(0)
            return
        if protocol_version == 0 and self._session is not None:
            self._session.set_passthrough_mode(
                passthrough_mode=True, transition_expiry=_DOWNGRADE_PASSTHROUGH
            )
        await self._send_json(
            VoiceOpcode.DAVE_TRANSITION_READY, DaveTransitionReady(transition_id=transition_id)
        )

    def _execute_transition(self, transition_id: int) -> None:
        pending, self._pending = self._pending, None
        if pending is None or pending[0] != transition_id:
            return
        previous, self._version = self._version, pending[1]
        if previous != self._version and self._version == 0:
            self._downgraded = True
        elif transition_id > 0 and self._downgraded:
            self._downgraded = False
            if self._session is not None:
                self._session.set_passthrough_mode(passthrough_mode=True, transition_expiry=_PASSTHROUGH)
        self._reinitializing = False
        _log.debug("DAVE transition %d executed: protocol version %d", transition_id, self._version)

    async def _proposals(self, payload: bytes) -> None:
        if self._session is None or not payload or payload[0] >= len(_OPERATIONS):
            return
        members = [self._user_id, *self._members]
        try:
            answer = self._session.process_proposals(_OPERATIONS[payload[0]], payload[1:], members)
        except ValueError:
            _log.exception("could not process DAVE proposals")
            return
        if answer is not None:
            await self._send_binary(
                VoiceOpcode.DAVE_MLS_COMMIT_WELCOME, answer.commit + (answer.welcome or b"")
            )

    async def _commit_or_welcome(self, opcode: VoiceOpcode, payload: bytes) -> None:
        if self._session is None or len(payload) < 2:  # noqa: PLR2004 - the transition ID
            return
        transition_id = int.from_bytes(payload[:2], "big")
        try:
            if opcode is VoiceOpcode.DAVE_MLS_WELCOME:
                self._session.process_welcome(payload[2:])
            else:
                self._session.process_commit(payload[2:])
        except ValueError:
            _log.warning(
                "DAVE %s for transition %d could not be processed; asking to be re-added",
                opcode.name,
                transition_id,
            )
            await self._recover(transition_id)
            return
        if transition_id == 0:
            self._reinitializing = False
            return
        self._pending = (transition_id, self._version)
        await self._send_json(
            VoiceOpcode.DAVE_TRANSITION_READY, DaveTransitionReady(transition_id=transition_id)
        )

    async def _recover(self, transition_id: int) -> None:
        """Report an unusable commit or welcome and start over with a new key package."""
        if self._reinitializing:
            return
        self._reinitializing = True
        await self._send_json(
            VoiceOpcode.DAVE_MLS_INVALID_COMMIT_WELCOME,
            DaveMlsInvalidCommitWelcome(transition_id=transition_id),
        )
        await self._reinit()
