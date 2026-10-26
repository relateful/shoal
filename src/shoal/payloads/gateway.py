"""Gateway protocol data: opcodes, close codes, intents, compression and Get Gateway (Bot).

Discord: https://docs.discord.com/developers/events/gateway
"""

from typing import Final, Self

from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.flags import BaseFlags, flag
from shoal.payloads.base import Payload

DEFAULT_GATEWAY_URL: Final = "wss://gateway.discord.gg"
"""The gateway URL Get Gateway returns. Used when no URL is supplied, and as the fallback when a
resume URL fails.

Discord: https://docs.discord.com/developers/events/gateway#get-gateway
"""

GATEWAY_CLOSE_CODES: Final = range(4000, 5000)
"""The range Discord uses for gateway close codes; anything else is a websocket or transport code.

Discord: https://docs.discord.com/developers/topics/opcodes-and-status-codes#gateway-gateway-close-event-codes
"""


GATEWAY_SEND_LIMIT: Final = 120
"""Gateway events a connection may send per window; exceeding it disconnects the shard.

Discord: https://docs.discord.com/developers/events/gateway#rate-limiting
"""

GATEWAY_SEND_WINDOW: Final = 60.0
"""The send window, in seconds.

Discord: https://docs.discord.com/developers/events/gateway#rate-limiting
"""

GUILDS_PER_SHARD: Final = 2500
"""The most guilds one shard may serve.

Discord: https://docs.discord.com/developers/events/gateway#sharding
"""

IDENTIFY_WINDOW: Final = 5.0
"""Seconds each `max_concurrency` bucket must wait between identifies.

Discord: https://docs.discord.com/developers/events/gateway#session-start-limit-object
"""

LARGE_THRESHOLD_RANGE: Final = range(50, 251)
"""Valid values for Identify's `large_threshold`.

Discord: https://docs.discord.com/developers/events/gateway-events#identify-identify-structure
"""

SESSION_ENDING_CLOSE_CODES: Final = frozenset({1000, 1001})
"""Websocket close codes that make Discord invalidate the session when the client sends them.

Discord: https://docs.discord.com/developers/events/gateway#initiating-a-disconnect
"""

ZLIB_SUFFIX: Final = b"\x00\x00\xff\xff"
"""The `Z_SYNC_FLUSH` marker that ends every complete zlib-stream message.

Discord: https://docs.discord.com/developers/events/gateway#zlib-stream
"""


class Intents(BaseFlags):
    """Which gateway events a session subscribes to.

    `Intents.default()` is every non-privileged intent.

    Discord: https://docs.discord.com/developers/events/gateway#list-of-intents
    """

    __slots__ = ()

    guilds = flag(0)
    guild_members = flag(1)
    guild_moderation = flag(2)
    guild_expressions = flag(3)
    guild_integrations = flag(4)
    guild_webhooks = flag(5)
    guild_invites = flag(6)
    guild_voice_states = flag(7)
    guild_presences = flag(8)
    guild_messages = flag(9)
    guild_message_reactions = flag(10)
    guild_message_typing = flag(11)
    direct_messages = flag(12)
    direct_message_reactions = flag(13)
    direct_message_typing = flag(14)
    message_content = flag(15)
    guild_scheduled_events = flag(16)
    auto_moderation_configuration = flag(20)
    auto_moderation_execution = flag(21)
    guild_message_polls = flag(24)
    direct_message_polls = flag(25)

    @classmethod
    def privileged(cls) -> Self:
        """The intents that must be enabled in the Developer Portal.

        Discord: https://docs.discord.com/developers/events/gateway#privileged-intents
        """
        return cls(guild_members=True, guild_presences=True, message_content=True)

    @classmethod
    def default(cls) -> Self:
        """Every intent except the privileged ones."""
        return cls.all().without(cls.privileged())

    @property
    def is_privileged(self) -> bool:
        """Whether any privileged intent is enabled."""
        return int(self) & int(type(self).privileged()) != 0


class TransportCompression(DiscordStrEnum):
    """The `compress` query parameter of the gateway URL.

    Discord: https://docs.discord.com/developers/events/gateway#transport-compression
    """

    ZLIB_STREAM = "zlib-stream"
    ZSTD_STREAM = "zstd-stream"


class GatewayEncoding(DiscordStrEnum):
    """The `encoding` query parameter of the gateway URL.

    Discord: https://docs.discord.com/developers/events/gateway#encoding-and-compression
    """

    ETF = "etf"
    JSON = "json"


class SessionStartLimit(Payload):
    """How many sessions the bot may still start, and how fast.

    Discord: https://docs.discord.com/developers/events/gateway#session-start-limit-object
    """

    total: int
    remaining: int
    reset_after: int
    max_concurrency: int


class GatewayInfo(Payload):
    """Response of Get Gateway.

    Discord: https://docs.discord.com/developers/events/gateway#get-gateway
    """

    url: str


class GatewayBot(Payload):
    """Response of Get Gateway Bot: URL, recommended shard count and session start limit.

    Discord: https://docs.discord.com/developers/events/gateway#get-gateway-bot
    """

    url: str
    shards: int
    session_start_limit: SessionStartLimit


class GatewayOpcode(DiscordIntEnum):
    """The `op` field of a gateway payload.

    Discord: https://docs.discord.com/developers/topics/opcodes-and-status-codes#gateway-gateway-opcodes
    """

    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    PRESENCE_UPDATE = 3
    VOICE_STATE_UPDATE = 4
    RESUME = 6
    RECONNECT = 7
    REQUEST_GUILD_MEMBERS = 8
    INVALID_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11
    REQUEST_SOUNDBOARD_SOUNDS = 31
    REQUEST_CHANNEL_INFO = 43

    @property
    def is_command(self) -> bool:
        """Whether an app sends this opcode by choice (presence, voice, member and channel requests).

        Heartbeat, Identify and Resume are part of the connection lifecycle and sent by the shard.
        """
        return self in _COMMAND_OPCODES


class GatewayCloseCode(DiscordIntEnum):
    """Why Discord closed a gateway connection.

    Discord: https://docs.discord.com/developers/topics/opcodes-and-status-codes#gateway-gateway-close-event-codes
    """

    UNKNOWN_ERROR = 4000
    UNKNOWN_OPCODE = 4001
    DECODE_ERROR = 4002
    NOT_AUTHENTICATED = 4003
    AUTHENTICATION_FAILED = 4004
    ALREADY_AUTHENTICATED = 4005
    INVALID_SEQ = 4007
    RATE_LIMITED = 4008
    SESSION_TIMED_OUT = 4009
    INVALID_SHARD = 4010
    SHARDING_REQUIRED = 4011
    INVALID_API_VERSION = 4012
    INVALID_INTENTS = 4013
    DISALLOWED_INTENTS = 4014

    @staticmethod
    def is_gateway_code(code: int) -> bool:
        """Whether `code` is in `GATEWAY_CLOSE_CODES`, the range Discord uses for gateway close codes."""
        return code in GATEWAY_CLOSE_CODES

    @property
    def can_reconnect(self) -> bool:
        """The "Reconnect" column of Discord's table: whether reconnecting can ever succeed.

        Unknown 4xxx codes are treated as reconnectable, matching Discord's advice for unknown errors.
        """
        return self not in _FATAL_CLOSE_CODES

    @property
    def invalidates_session(self) -> bool:
        """Whether the session cannot be resumed after this close and a fresh Identify is required."""
        return self in _NEW_SESSION_CLOSE_CODES


_FATAL_CLOSE_CODES: Final = frozenset(
    {
        GatewayCloseCode.AUTHENTICATION_FAILED,
        GatewayCloseCode.INVALID_SHARD,
        GatewayCloseCode.SHARDING_REQUIRED,
        GatewayCloseCode.INVALID_API_VERSION,
        GatewayCloseCode.INVALID_INTENTS,
        GatewayCloseCode.DISALLOWED_INTENTS,
    }
)
_NEW_SESSION_CLOSE_CODES: Final = frozenset(
    {
        GatewayCloseCode.NOT_AUTHENTICATED,
        GatewayCloseCode.INVALID_SEQ,
        GatewayCloseCode.SESSION_TIMED_OUT,
    }
)


_COMMAND_OPCODES: Final = frozenset(
    {
        GatewayOpcode.PRESENCE_UPDATE,
        GatewayOpcode.VOICE_STATE_UPDATE,
        GatewayOpcode.REQUEST_GUILD_MEMBERS,
        GatewayOpcode.REQUEST_SOUNDBOARD_SOUNDS,
        GatewayOpcode.REQUEST_CHANNEL_INFO,
    }
)
