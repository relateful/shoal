"""The voice gateway: opcodes, close codes, the payloads of a voice websocket, and the UDP constants.

A voice connection has its own websocket (version 8) and a UDP socket for the audio. DAVE, the
end-to-end encryption every voice channel requires, adds opcodes 21 to 31; some of them are binary.

Discord: https://docs.discord.com/developers/topics/voice-connections
"""

from typing import Final

import msgspec
from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload

IP_DISCOVERY_LENGTH: Final = 70
"""The length field of an IP discovery packet: its size without the type and length fields.

Discord: https://docs.discord.com/developers/topics/voice-connections#ip-discovery
"""

OPUS_CHANNELS: Final = 2
"""Channels of the Opus audio Discord expects: stereo.

Discord: https://docs.discord.com/developers/topics/voice-connections#transport-encryption-and-sending-voice
"""

OPUS_SAMPLE_RATE: Final = 48_000
"""Samples per second of the Opus audio Discord expects; RTP timestamps count at this rate.

Discord: https://docs.discord.com/developers/topics/voice-connections#transport-encryption-and-sending-voice
"""

RTP_HEADER_SIZE: Final = 12
"""Bytes in a voice packet's RTP header: version and flags, payload type, sequence, timestamp, SSRC.

Discord: https://docs.discord.com/developers/topics/voice-connections#transport-encryption-modes-voice-packet-structure
"""

RTP_PAYLOAD_TYPE: Final = 0x78
"""The payload type byte of a voice packet's RTP header.

Discord: https://docs.discord.com/developers/topics/voice-connections#transport-encryption-modes-voice-packet-structure
"""

RTP_VERSION_FLAGS: Final = 0x80
"""The first byte of a voice packet's RTP header: version 2, no padding, extension or CSRCs.

Discord: https://docs.discord.com/developers/topics/voice-connections#transport-encryption-modes-voice-packet-structure
"""

SILENCE_FRAME: Final = b"\xf8\xff\xfe"
"""An Opus frame of silence.

Discord: https://docs.discord.com/developers/topics/voice-connections#voice-data-interpolation
"""

SILENCE_FRAMES_AFTER_AUDIO: Final = 5
"""Frames of silence to send when audio stops, so the next audio is not interpolated with the last.

Discord: https://docs.discord.com/developers/topics/voice-connections#voice-data-interpolation
"""

VOICE_GATEWAY_VERSION: Final = 8
"""The voice gateway version Shoal speaks: it re-sends missed messages on resume.

Discord: https://docs.discord.com/developers/topics/voice-connections#voice-gateway-versioning-gateway-versions
"""


class VoiceOpcode(DiscordIntEnum):
    """The `op` of a voice gateway message.

    Discord: https://docs.discord.com/developers/topics/opcodes-and-status-codes#voice-voice-opcodes
    """

    IDENTIFY = 0
    SELECT_PROTOCOL = 1
    READY = 2
    HEARTBEAT = 3
    SESSION_DESCRIPTION = 4
    SPEAKING = 5
    HEARTBEAT_ACK = 6
    RESUME = 7
    HELLO = 8
    RESUMED = 9
    CLIENTS_CONNECT = 11
    CLIENT_DISCONNECT = 13
    DAVE_PREPARE_TRANSITION = 21
    DAVE_EXECUTE_TRANSITION = 22
    DAVE_TRANSITION_READY = 23
    DAVE_PREPARE_EPOCH = 24
    DAVE_MLS_EXTERNAL_SENDER = 25
    DAVE_MLS_KEY_PACKAGE = 26
    DAVE_MLS_PROPOSALS = 27
    DAVE_MLS_COMMIT_WELCOME = 28
    DAVE_MLS_ANNOUNCE_COMMIT_TRANSITION = 29
    DAVE_MLS_WELCOME = 30
    DAVE_MLS_INVALID_COMMIT_WELCOME = 31


class VoiceCloseCode(DiscordIntEnum):
    """Why the voice gateway closed a connection.

    Discord: https://docs.discord.com/developers/topics/opcodes-and-status-codes#voice-voice-close-event-codes
    """

    UNKNOWN_OPCODE = 4001
    FAILED_TO_DECODE_PAYLOAD = 4002
    NOT_AUTHENTICATED = 4003
    AUTHENTICATION_FAILED = 4004
    ALREADY_AUTHENTICATED = 4005
    SESSION_NO_LONGER_VALID = 4006
    SESSION_TIMEOUT = 4009
    SERVER_NOT_FOUND = 4011
    UNKNOWN_PROTOCOL = 4012
    DISCONNECTED = 4014
    VOICE_SERVER_CRASHED = 4015
    UNKNOWN_ENCRYPTION_MODE = 4016
    DAVE_PROTOCOL_REQUIRED = 4017
    BAD_REQUEST = 4020
    DISCONNECTED_RATE_LIMITED = 4021
    DISCONNECTED_CALL_TERMINATED = 4022

    @property
    def ends_connection(self) -> bool:
        """Whether Discord says not to reconnect: the bot was disconnected or the call ended."""
        return self in _ENDS_CONNECTION


_ENDS_CONNECTION: Final = frozenset(
    {
        VoiceCloseCode.AUTHENTICATION_FAILED,
        VoiceCloseCode.DISCONNECTED,
        VoiceCloseCode.DISCONNECTED_RATE_LIMITED,
        VoiceCloseCode.DISCONNECTED_CALL_TERMINATED,
    }
)


class EncryptionMode(DiscordStrEnum):
    """How voice packets are encrypted between the bot and Discord's voice server.

    Discord offers `aead_xchacha20_poly1305_rtpsize` on every server and `aead_aes256_gcm_rtpsize`
    where the hardware allows; the second is preferred.

    Discord: https://docs.discord.com/developers/topics/voice-connections#transport-encryption-modes
    """

    AEAD_AES256_GCM_RTPSIZE = "aead_aes256_gcm_rtpsize"
    AEAD_XCHACHA20_POLY1305_RTPSIZE = "aead_xchacha20_poly1305_rtpsize"


class SpeakingFlags(BaseFlags):
    """How the bot transmits audio.

    Discord: https://docs.discord.com/developers/topics/voice-connections#speaking
    """

    __slots__ = ()

    microphone = flag(0)
    soundshare = flag(1)
    priority = flag(2)


class VoicePayload(Payload):
    """One voice gateway message: an opcode, its data, and (from the server) a sequence number.

    Discord: https://docs.discord.com/developers/topics/voice-connections#buffered-resume
    """

    op: VoiceOpcode
    d: msgspec.Raw = msgspec.Raw(b"null")
    seq: int | UnsetType = UNSET


class VoiceIdentify(Payload):
    """Opcode 0: start a voice session.

    Discord: https://docs.discord.com/developers/topics/voice-connections#establishing-a-voice-websocket-connection-example-voice-identify-payload
    """

    REDACTED_FIELDS = frozenset({"token"})

    server_id: Snowflake
    user_id: Snowflake
    session_id: str
    token: str
    max_dave_protocol_version: int


class SelectProtocolData(Payload):
    """Where the bot receives voice, and the encryption it chose.

    Discord: https://docs.discord.com/developers/topics/voice-connections#establishing-a-voice-udp-connection-example-select-protocol-payload
    """

    address: str
    port: int
    mode: EncryptionMode


class SelectProtocol(Payload):
    """Opcode 1: tell the voice server the bot's UDP address and encryption mode.

    Discord: https://docs.discord.com/developers/topics/voice-connections#establishing-a-voice-udp-connection-example-select-protocol-payload
    """

    protocol: str
    data: SelectProtocolData


class VoiceReady(Payload):
    """Opcode 2: the bot's SSRC, the voice server's UDP address, and the encryption modes it offers.

    Its `heartbeat_interval` is erroneous and not read: the interval comes from `VoiceHello`.

    Discord: https://docs.discord.com/developers/topics/voice-connections#establishing-a-voice-websocket-connection-example-voice-ready-payload
    """

    ssrc: int
    ip: str
    port: int
    modes: list[EncryptionMode]


class VoiceHeartbeat(Payload):
    """Opcode 3: a heartbeat, acknowledging the last numbered message received.

    Discord: https://docs.discord.com/developers/topics/voice-connections#heartbeating-example-heartbeat-payload-since-v8
    """

    t: int
    seq_ack: int


class SessionDescription(Payload):
    """Opcode 4: the transport encryption key, and the DAVE protocol version the call starts with.

    Discord: https://docs.discord.com/developers/topics/voice-connections#transport-encryption-modes-example-session-description-payload
    """

    REDACTED_FIELDS = frozenset({"secret_key"})

    mode: EncryptionMode
    secret_key: list[int]
    dave_protocol_version: int = 0


class Speaking(Payload):
    """Opcode 5: a user's speaking mode and SSRC; the bot sends its own before any audio.

    Discord: https://docs.discord.com/developers/topics/voice-connections#speaking-example-speaking-payload
    """

    speaking: SpeakingFlags
    ssrc: int
    delay: int | UnsetType = UNSET
    user_id: Snowflake | UnsetType = UNSET
    """Set by the server: whose SSRC this is."""


class VoiceHeartbeatAck(Payload):
    """Opcode 6: the server received a heartbeat.

    Discord: https://docs.discord.com/developers/topics/voice-connections#heartbeating-example-heartbeat-ack-payload-since-v8
    """

    t: int


class VoiceResume(Payload):
    """Opcode 7: resume a voice session on a new websocket.

    Discord: https://docs.discord.com/developers/topics/voice-connections#resuming-voice-connection-example-resume-connection-payload-since-v8
    """

    REDACTED_FIELDS = frozenset({"token"})

    server_id: Snowflake
    session_id: str
    token: str
    seq_ack: int


class VoiceHello(Payload):
    """Opcode 8: how often to heartbeat, in milliseconds.

    Discord: https://docs.discord.com/developers/topics/voice-connections#heartbeating-example-hello-payload
    """

    heartbeat_interval: float


class ClientsConnect(Payload):
    """Opcode 11: users who joined the call.

    Discord: https://docs.discord.com/developers/topics/opcodes-and-status-codes#voice-voice-opcodes
    """

    user_ids: list[Snowflake]


class ClientDisconnect(Payload):
    """Opcode 13: a user who left the call.

    Discord: https://docs.discord.com/developers/topics/opcodes-and-status-codes#voice-voice-opcodes
    """

    user_id: Snowflake


class DavePrepareTransition(Payload):
    """Opcode 21: a change of DAVE protocol version (a downgrade to 0 included) is coming.

    Discord: https://docs.discord.com/developers/topics/voice-connections#downgrade
    """

    protocol_version: int
    transition_id: int


class DaveExecuteTransition(Payload):
    """Opcode 22: the announced transition happens now.

    Discord: https://docs.discord.com/developers/topics/voice-connections#protocol-transitions
    """

    transition_id: int


class DaveTransitionReady(Payload):
    """Opcode 23: the bot is ready for the announced transition.

    Discord: https://docs.discord.com/developers/topics/voice-connections#protocol-transitions
    """

    transition_id: int


class DavePrepareEpoch(Payload):
    """Opcode 24: a protocol version change or a new MLS group is coming; epoch 1 is a new group.

    Discord: https://docs.discord.com/developers/topics/voice-connections#protocol-version-change-upgrade
    """

    protocol_version: int
    epoch: int
    transition_id: int | UnsetType = UNSET


class DaveMlsInvalidCommitWelcome(Payload):
    """Opcode 31: the commit or welcome of a transition could not be processed; re-add the bot.

    Discord: https://docs.discord.com/developers/topics/voice-connections#invalid-group
    """

    transition_id: int
