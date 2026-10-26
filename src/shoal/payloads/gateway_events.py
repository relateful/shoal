"""Gateway payloads sent and received over the websocket.

Discord: https://docs.discord.com/developers/events/gateway-events

Dispatch event bodies that are plain resources (`CHANNEL_CREATE` is a `Channel`) reuse the resource
type; only events with their own shape are declared here. `DISPATCH_PAYLOADS` maps every dispatch
Discord documents to the type its data decodes into.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Final, override

import msgspec
from msgspec import UNSET, Raw, UnsetType

from shoal.core.codec import decode_json
from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.application_commands import GuildApplicationCommandPermissions
from shoal.payloads.audit_log import AuditLogEntry
from shoal.payloads.auto_moderation import (
    AutoModerationAction,
    AutoModerationRule,
    AutoModerationTriggerType,
)
from shoal.payloads.base import Payload
from shoal.payloads.channel import Channel, ChannelType, ThreadMember
from shoal.payloads.emoji import Emoji
from shoal.payloads.gateway import GatewayOpcode, Intents
from shoal.payloads.guild import Guild, GuildMember, GuildMemberFlags, Integration, UnavailableGuild
from shoal.payloads.invite import InviteTargetType
from shoal.payloads.message import Message, ReactionType
from shoal.payloads.monetization import Entitlement, Subscription
from shoal.payloads.permissions import Role
from shoal.payloads.scheduled_event import GuildScheduledEvent
from shoal.payloads.soundboard import SoundboardSound
from shoal.payloads.stage_instance import StageInstance
from shoal.payloads.sticker import Sticker
from shoal.payloads.user import AvatarDecorationData, Collectibles, User
from shoal.payloads.voice import VoiceState


class GatewayPayload(Payload):
    """The envelope of every gateway message. `d` stays raw until a handler knows its type.

    Discord: https://docs.discord.com/developers/events/gateway-events#payload-structure
    """

    op: GatewayOpcode
    d: Raw = Raw(b"null")
    s: int | None = None
    t: str | None = None


class GatewayCapabilities(BaseFlags):
    """Opt-in gateway behaviours sent with Identify.

    Discord: https://docs.discord.com/developers/events/gateway-events#identify-gateway-capabilities
    """

    __slots__ = ()

    channel_obfuscation = flag(15)


class IdentifyConnectionProperties(Payload):
    """Client properties sent with Identify.

    Discord: https://docs.discord.com/developers/events/gateway-events#identify-identify-connection-properties
    """

    os: str
    browser: str
    device: str


class ActivityType(DiscordIntEnum):
    """The kind of activity shown in a presence.

    Discord: https://docs.discord.com/developers/events/gateway-events#activity-object-activity-types
    """

    PLAYING = 0
    STREAMING = 1
    LISTENING = 2
    WATCHING = 3
    CUSTOM = 4
    COMPETING = 5


class StatusDisplayType(DiscordIntEnum):
    """Which activity field a user's status line shows.

    Discord: https://docs.discord.com/developers/events/gateway-events#activity-object-status-display-types
    """

    NAME = 0
    STATE = 1
    DETAILS = 2


class ActivityFlags(BaseFlags):
    """What an activity's payload includes.

    Discord: https://docs.discord.com/developers/events/gateway-events#activity-object-activity-flags
    """

    __slots__ = ()

    instance = flag(0)
    join = flag(1)
    spectate = flag(2)
    join_request = flag(3)
    sync = flag(4)
    play = flag(5)
    party_privacy_friends = flag(6)
    party_privacy_voice_channel = flag(7)
    embedded = flag(8)


class ActivityTimestamps(Payload):
    """Start and end of an activity, in Unix milliseconds.

    Discord: https://docs.discord.com/developers/events/gateway-events#activity-object-activity-timestamps
    """

    start: int | UnsetType = UNSET
    end: int | UnsetType = UNSET


class ActivityEmoji(Payload):
    """The emoji of a custom status.

    Discord: https://docs.discord.com/developers/events/gateway-events#activity-object-activity-emoji
    """

    name: str
    id: Snowflake | UnsetType = UNSET
    animated: bool | UnsetType = UNSET


class ActivityParty(Payload):
    """The party a player is in.

    Discord: https://docs.discord.com/developers/events/gateway-events#activity-object-activity-party
    """

    id: str | UnsetType = UNSET
    size: tuple[int, int] | UnsetType = UNSET


class ActivityAssets(Payload):
    """Images and hover texts of a Rich Presence.

    Discord: https://docs.discord.com/developers/events/gateway-events#activity-object-activity-assets
    """

    large_image: str | UnsetType = UNSET
    large_text: str | UnsetType = UNSET
    large_url: str | UnsetType = UNSET
    small_image: str | UnsetType = UNSET
    small_text: str | UnsetType = UNSET
    small_url: str | UnsetType = UNSET
    invite_cover_image: str | UnsetType = UNSET


class ActivitySecrets(Payload):
    """Secrets for joining and spectating.

    Discord: https://docs.discord.com/developers/events/gateway-events#activity-object-activity-secrets
    """

    join: str | UnsetType = UNSET
    spectate: str | UnsetType = UNSET
    match: str | UnsetType = UNSET


class Activity(Payload):
    """An activity as received in a presence.

    Over the gateway `buttons` holds only the button labels; bots never see the URLs.

    Discord: https://docs.discord.com/developers/events/gateway-events#activity-object
    """

    name: str
    type: ActivityType
    url: str | UnsetType | None = UNSET
    created_at: int
    timestamps: ActivityTimestamps | UnsetType = UNSET
    application_id: Snowflake | UnsetType = UNSET
    status_display_type: StatusDisplayType | UnsetType | None = UNSET
    details: str | UnsetType | None = UNSET
    details_url: str | UnsetType | None = UNSET
    state: str | UnsetType | None = UNSET
    state_url: str | UnsetType | None = UNSET
    emoji: ActivityEmoji | UnsetType | None = UNSET
    party: ActivityParty | UnsetType = UNSET
    assets: ActivityAssets | UnsetType = UNSET
    secrets: ActivitySecrets | UnsetType = UNSET
    instance: bool | UnsetType = UNSET
    flags: ActivityFlags | UnsetType = UNSET
    buttons: list[str] | UnsetType = UNSET


class BotActivity(Payload):
    """An activity a bot sends. Bots may only set `name`, `type`, `url` and `state`.

    Discord: https://docs.discord.com/developers/events/gateway-events#activity-object
    """

    name: str
    type: ActivityType
    url: str | UnsetType | None = UNSET
    state: str | UnsetType | None = UNSET


class StatusType(DiscordStrEnum):
    """Online status.

    Discord: https://docs.discord.com/developers/events/gateway-events#update-presence-status-types
    """

    DND = "dnd"
    IDLE = "idle"
    INVISIBLE = "invisible"
    OFFLINE = "offline"
    ONLINE = "online"


class UpdatePresence(Payload):
    """Opcode 3 body, and the `presence` field of Identify.

    Discord: https://docs.discord.com/developers/events/gateway-events#update-presence
    """

    since: int | None
    activities: list[BotActivity]
    status: StatusType
    afk: bool


class Identify(Payload):
    """Opcode 2 body: start a new session.

    Discord: https://docs.discord.com/developers/events/gateway-events#identify
    """

    REDACTED_FIELDS = frozenset({"token"})

    token: str
    properties: IdentifyConnectionProperties
    compress: bool | UnsetType = UNSET
    large_threshold: int | UnsetType = UNSET
    shard: tuple[int, int] | UnsetType = UNSET
    presence: UpdatePresence | UnsetType = UNSET
    intents: Intents
    capabilities: GatewayCapabilities | UnsetType = UNSET

    @override
    def __repr__(self) -> str:
        """Everything but the token, which must never reach a log or an error tracker."""
        return f"Identify(shard={self.shard!r}, intents={self.intents!r}, token=<redacted>)"


class Resume(Payload):
    """Opcode 6 body: replay missed events on an existing session.

    Discord: https://docs.discord.com/developers/events/gateway-events#resume
    """

    REDACTED_FIELDS = frozenset({"token"})

    token: str
    session_id: str
    seq: int

    @override
    def __repr__(self) -> str:
        """Everything but the token, which must never reach a log or an error tracker."""
        return f"Resume(session_id={self.session_id!r}, seq={self.seq}, token=<redacted>)"


MEMBER_QUERY_MAX_RESULTS: Final = 100
"""Members a Request Guild Members by `query` or `user_ids` returns at most.

Discord: https://docs.discord.com/developers/events/gateway-events#request-guild-members
"""


class RequestGuildMembers(Payload):
    """Opcode 8 body: ask for members of a guild (answered by `GUILD_MEMBERS_CHUNK`).

    Discord: https://docs.discord.com/developers/events/gateway-events#request-guild-members
    """

    guild_id: Snowflake
    query: str | UnsetType = UNSET
    limit: int
    presences: bool | UnsetType = UNSET
    user_ids: list[Snowflake] | UnsetType = UNSET
    nonce: str | UnsetType = UNSET


class RequestSoundboardSounds(Payload):
    """Opcode 31 body: ask for the soundboard sounds of guilds (answered by `SOUNDBOARD_SOUNDS`).

    Discord: https://docs.discord.com/developers/events/gateway-events#request-soundboard-sounds
    """

    guild_ids: list[Snowflake]


class ChannelInfoField(DiscordStrEnum):
    """Ephemeral channel data that Request Channel Info can ask for.

    Discord: https://docs.discord.com/developers/events/gateway-events#request-channel-info
    """

    STATUS = "status"
    VOICE_START_TIME = "voice_start_time"


class RequestChannelInfo(Payload):
    """Opcode 43 body: ask for ephemeral data of a guild's channels (answered by `CHANNEL_INFO`).

    Discord: https://docs.discord.com/developers/events/gateway-events#request-channel-info
    """

    guild_id: Snowflake
    fields: list[ChannelInfoField]


class UpdateVoiceState(Payload):
    """Opcode 4 body: join, move or leave a voice channel.

    Discord: https://docs.discord.com/developers/events/gateway-events#update-voice-state
    """

    guild_id: Snowflake
    channel_id: Snowflake | None
    self_mute: bool
    self_deaf: bool


class Hello(Payload):
    """Opcode 10 body: how often to heartbeat.

    Discord: https://docs.discord.com/developers/events/gateway-events#hello
    """

    heartbeat_interval: int


class ReadyApplication(Payload):
    """The partial application inside Ready.

    Discord: https://docs.discord.com/developers/events/gateway-events#ready-ready-event-fields
    """

    id: Snowflake
    flags: int


class Ready(Payload):
    """`READY` dispatch: the session exists and these guilds will follow as `GUILD_CREATE`.

    Discord: https://docs.discord.com/developers/events/gateway-events#ready
    """

    v: int
    user: User
    guilds: list[UnavailableGuild]
    session_id: str
    resume_gateway_url: str
    shard: tuple[int, int] | UnsetType = UNSET
    application: ReadyApplication


class ClientStatus(Payload):
    """A user's status on each platform; a platform is absent when the user is not active on it.

    Discord: https://docs.discord.com/developers/events/gateway-events#client-status-object
    """

    desktop: StatusType | UnsetType = UNSET
    mobile: StatusType | UnsetType = UNSET
    web: StatusType | UnsetType = UNSET
    vr: StatusType | UnsetType = UNSET


class PresenceUser(Payload):
    """The user inside a presence. Only `id` is guaranteed; other fields arrive when they changed.

    Discord: https://docs.discord.com/developers/events/gateway-events#presence-update
    """

    id: Snowflake
    username: str | UnsetType = UNSET
    global_name: str | UnsetType | None = UNSET
    avatar: str | UnsetType | None = UNSET


class Presence(Payload):
    """A user's presence, as included in `GUILD_CREATE` (without `guild_id`).

    Discord: https://docs.discord.com/developers/events/gateway-events#presence-update-presence-update-event-fields
    """

    user: PresenceUser
    status: StatusType
    activities: list[Activity]
    client_status: ClientStatus


GUILD_CREATE_MEMBER_LIMIT: Final = 75_000
"""Above this many members, `GUILD_CREATE` lists only the bot and members in voice channels.

Discord: https://docs.discord.com/developers/events/gateway-events#guild-create
"""


class GuildCreate(Guild):
    """`GUILD_CREATE` dispatch for an available guild: the guild plus its full startup state.

    An unavailable guild is sent as an `UnavailableGuild` instead; check `unavailable` on the raw data
    before choosing which type to decode.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-create
    """

    joined_at: datetime
    large: bool
    unavailable: bool | UnsetType = UNSET
    member_count: int
    members: list[GuildMember]
    channels: list[Channel]
    threads: list[Channel]
    voice_states: list[VoiceState] = msgspec.field(default_factory=list[VoiceState])
    presences: list[Presence] = msgspec.field(default_factory=list[Presence])
    stage_instances: list[StageInstance] = msgspec.field(default_factory=list[StageInstance])
    guild_scheduled_events: list[GuildScheduledEvent] = msgspec.field(
        default_factory=list[GuildScheduledEvent]
    )
    soundboard_sounds: list[SoundboardSound] = msgspec.field(default_factory=list[SoundboardSound])


class GuildDelete(Payload):
    """`GUILD_DELETE` dispatch. `unavailable` is set for outages; absent means the bot was removed.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-delete
    """

    id: Snowflake
    unavailable: bool | UnsetType = UNSET


class GuildMembersChunk(Payload):
    """`GUILD_MEMBERS_CHUNK` dispatch: one page of an opcode 8 answer.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-members-chunk
    """

    guild_id: Snowflake
    members: list[GuildMember]
    chunk_index: int
    chunk_count: int
    not_found: list[Snowflake] | UnsetType = UNSET
    presences: list[Presence] | UnsetType = UNSET
    nonce: str | UnsetType = UNSET


class GuildRoleCreate(Payload):
    """`GUILD_ROLE_CREATE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-role-create
    """

    guild_id: Snowflake
    role: Role


class GuildRoleUpdate(GuildRoleCreate):
    """`GUILD_ROLE_UPDATE` dispatch: the role's new state.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-role-update
    """


class GuildRoleDelete(Payload):
    """`GUILD_ROLE_DELETE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-role-delete
    """

    guild_id: Snowflake
    role_id: Snowflake


class GuildMemberAdd(GuildMember):
    """`GUILD_MEMBER_ADD` dispatch: the member plus the guild it joined.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-member-add
    """

    guild_id: Snowflake


class GuildMemberRemove(Payload):
    """`GUILD_MEMBER_REMOVE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-member-remove
    """

    guild_id: Snowflake
    user: User


class MessageCreate(Message):
    """`MESSAGE_CREATE` dispatch: the message plus where it was sent and its author's membership.

    Discord: https://docs.discord.com/developers/events/gateway-events#message-create
    """

    guild_id: Snowflake | UnsetType = UNSET
    member: GuildMember | UnsetType = UNSET
    channel_type: ChannelType | UnsetType = UNSET


class MessageDelete(Payload):
    """`MESSAGE_DELETE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#message-delete
    """

    id: Snowflake
    channel_id: Snowflake
    guild_id: Snowflake | UnsetType = UNSET


class PresenceUpdate(Presence):
    """`PRESENCE_UPDATE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#presence-update
    """

    guild_id: Snowflake


class GuildMemberUpdate(Payload):
    """`GUILD_MEMBER_UPDATE` dispatch: the member's current state, sent whole.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-member-update
    """

    guild_id: Snowflake
    roles: list[Snowflake]
    user: User
    nick: str | UnsetType | None = UNSET
    avatar: str | None
    banner: str | None
    joined_at: datetime | None
    premium_since: datetime | UnsetType | None = UNSET
    deaf: bool | UnsetType = UNSET
    mute: bool | UnsetType = UNSET
    pending: bool | UnsetType = UNSET
    communication_disabled_until: datetime | UnsetType | None = UNSET
    flags: GuildMemberFlags | UnsetType = UNSET
    avatar_decoration_data: AvatarDecorationData | UnsetType | None = UNSET
    collectibles: Collectibles | UnsetType | None = UNSET


class GuildEmojisUpdate(Payload):
    """`GUILD_EMOJIS_UPDATE` dispatch: the guild's complete emoji list.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-emojis-update
    """

    guild_id: Snowflake
    emojis: list[Emoji]


class MessageUpdate(MessageCreate):
    """`MESSAGE_UPDATE` dispatch: the full updated message with `MESSAGE_CREATE`'s extra fields.

    Discord: https://docs.discord.com/developers/events/gateway-events#message-update
    """


class MessageDeleteBulk(Payload):
    """`MESSAGE_DELETE_BULK` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#message-delete-bulk
    """

    ids: list[Snowflake]
    channel_id: Snowflake
    guild_id: Snowflake | UnsetType = UNSET


class MessageReactionAdd(Payload):
    """`MESSAGE_REACTION_ADD` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#message-reaction-add
    """

    user_id: Snowflake
    channel_id: Snowflake
    message_id: Snowflake
    guild_id: Snowflake | UnsetType = UNSET
    member: GuildMember | UnsetType = UNSET
    emoji: Emoji
    message_author_id: Snowflake | UnsetType = UNSET
    burst: bool
    burst_colors: list[str] | UnsetType = UNSET
    type: ReactionType


class MessageReactionRemove(Payload):
    """`MESSAGE_REACTION_REMOVE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#message-reaction-remove
    """

    user_id: Snowflake
    channel_id: Snowflake
    message_id: Snowflake
    guild_id: Snowflake | UnsetType = UNSET
    emoji: Emoji
    burst: bool
    type: ReactionType


class MessageReactionRemoveAll(Payload):
    """`MESSAGE_REACTION_REMOVE_ALL` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#message-reaction-remove-all
    """

    channel_id: Snowflake
    message_id: Snowflake
    guild_id: Snowflake | UnsetType = UNSET


class MessageReactionRemoveEmoji(Payload):
    """`MESSAGE_REACTION_REMOVE_EMOJI` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#message-reaction-remove-emoji
    """

    channel_id: Snowflake
    guild_id: Snowflake | UnsetType = UNSET
    message_id: Snowflake
    emoji: Emoji


class ChannelPinsUpdate(Payload):
    """`CHANNEL_PINS_UPDATE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#channel-pins-update
    """

    guild_id: Snowflake | UnsetType = UNSET
    channel_id: Snowflake
    last_pin_timestamp: datetime | UnsetType | None = UNSET


class ThreadListSync(Payload):
    """`THREAD_LIST_SYNC` dispatch: the active threads of some (or all) channels after gaining access.

    Discord: https://docs.discord.com/developers/events/gateway-events#thread-list-sync
    """

    guild_id: Snowflake
    channel_ids: list[Snowflake] | UnsetType = UNSET
    threads: list[Channel]
    members: list[ThreadMember]


class AddedThreadMember(ThreadMember):
    """A thread member in `THREAD_MEMBERS_UPDATE`, with the user's guild member and presence.

    Discord: https://docs.discord.com/developers/events/gateway-events#thread-members-update
    """

    presence: Presence | UnsetType | None = UNSET


class ThreadMembersUpdate(Payload):
    """`THREAD_MEMBERS_UPDATE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#thread-members-update
    """

    id: Snowflake
    guild_id: Snowflake
    member_count: int
    """Approximate, capped at 50."""
    added_members: list[AddedThreadMember] | UnsetType = UNSET
    removed_member_ids: list[Snowflake] | UnsetType = UNSET


class ThreadCreate(Channel):
    """`THREAD_CREATE` dispatch: the thread, plus whether it is new.

    It is also sent when the bot is added to an existing private thread; `member` is then set.

    Discord: https://docs.discord.com/developers/events/gateway-events#thread-create
    """

    newly_created: bool | UnsetType = UNSET


class ThreadMemberUpdate(ThreadMember):
    """`THREAD_MEMBER_UPDATE` dispatch: the bot's own thread membership changed.

    Discord: https://docs.discord.com/developers/events/gateway-events#thread-member-update
    """

    guild_id: Snowflake


class AutoModerationActionExecution(Payload):
    """`AUTO_MODERATION_ACTION_EXECUTION` dispatch: a rule matched and one of its actions ran.

    `content` and `matched_content` are empty without the `message_content` intent.

    Discord: https://docs.discord.com/developers/events/gateway-events#auto-moderation-action-execution
    """

    guild_id: Snowflake
    action: AutoModerationAction
    rule_id: Snowflake
    rule_trigger_type: AutoModerationTriggerType
    user_id: Snowflake
    channel_id: Snowflake | UnsetType = UNSET
    message_id: Snowflake | UnsetType = UNSET
    """Absent when the message was blocked or the content was not part of a message."""
    alert_system_message_id: Snowflake | UnsetType = UNSET
    """Only for a `SEND_ALERT_MESSAGE` action."""
    content: str
    matched_keyword: str | None
    matched_content: str | None


class ChannelInfoChannel(Payload):
    """One channel's ephemeral data in `CHANNEL_INFO`.

    Discord: https://docs.discord.com/developers/events/gateway-events#channel-info-channel-info-channel-structure
    """

    id: Snowflake
    status: str | UnsetType | None = UNSET
    """The voice channel status."""
    voice_start_time: int | UnsetType | None = UNSET
    """Unix time in seconds when the voice session started."""


class ChannelInfo(Payload):
    """`CHANNEL_INFO` dispatch, the answer to `RequestChannelInfo`.

    Discord: https://docs.discord.com/developers/events/gateway-events#channel-info
    """

    guild_id: Snowflake
    channels: list[ChannelInfoChannel]


class VoiceChannelStatusUpdate(Payload):
    """`VOICE_CHANNEL_STATUS_UPDATE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#voice-channel-status-update
    """

    id: Snowflake
    guild_id: Snowflake
    status: str | None


class VoiceChannelStartTimeUpdate(Payload):
    """`VOICE_CHANNEL_START_TIME_UPDATE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#voice-channel-start-time-update
    """

    id: Snowflake
    guild_id: Snowflake
    voice_start_time: int | UnsetType | None = UNSET
    """Unix time in seconds when the voice session started."""


class GuildAuditLogEntryCreate(AuditLogEntry):
    """`GUILD_AUDIT_LOG_ENTRY_CREATE` dispatch: the entry plus its guild.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-audit-log-entry-create
    """

    guild_id: Snowflake


class GuildBanAdd(Payload):
    """`GUILD_BAN_ADD` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-ban-add
    """

    guild_id: Snowflake
    user: User


class GuildBanRemove(Payload):
    """`GUILD_BAN_REMOVE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-ban-remove
    """

    guild_id: Snowflake
    user: User


class GuildStickersUpdate(Payload):
    """`GUILD_STICKERS_UPDATE` dispatch: the guild's complete sticker list.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-stickers-update
    """

    guild_id: Snowflake
    stickers: list[Sticker]


class GuildIntegrationsUpdate(Payload):
    """`GUILD_INTEGRATIONS_UPDATE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-integrations-update
    """

    guild_id: Snowflake


class GuildScheduledEventUserAdd(Payload):
    """`GUILD_SCHEDULED_EVENT_USER_ADD` dispatch: a user subscribed to an event.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-scheduled-event-user-add
    """

    guild_scheduled_event_id: Snowflake
    user_id: Snowflake
    guild_id: Snowflake


class GuildScheduledEventUserRemove(Payload):
    """`GUILD_SCHEDULED_EVENT_USER_REMOVE` dispatch: a user unsubscribed from an event.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-scheduled-event-user-remove
    """

    guild_scheduled_event_id: Snowflake
    user_id: Snowflake
    guild_id: Snowflake


class GuildSoundboardSoundDelete(Payload):
    """`GUILD_SOUNDBOARD_SOUND_DELETE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-soundboard-sound-delete
    """

    sound_id: Snowflake
    guild_id: Snowflake


class GuildSoundboardSoundsUpdate(Payload):
    """`GUILD_SOUNDBOARD_SOUNDS_UPDATE` dispatch: several of the guild's sounds changed.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-soundboard-sounds-update
    """

    soundboard_sounds: list[SoundboardSound]
    guild_id: Snowflake


class SoundboardSounds(Payload):
    """`SOUNDBOARD_SOUNDS` dispatch: a guild's complete sound list, the answer to `RequestSoundboardSounds`.

    Discord: https://docs.discord.com/developers/events/gateway-events#soundboard-sounds
    """

    soundboard_sounds: list[SoundboardSound]
    guild_id: Snowflake


class IntegrationCreate(Integration):
    """`INTEGRATION_CREATE` dispatch: the integration (without `user`) plus its guild.

    Discord: https://docs.discord.com/developers/events/gateway-events#integration-create
    """

    guild_id: Snowflake


class IntegrationUpdate(IntegrationCreate):
    """`INTEGRATION_UPDATE` dispatch: the integration (without `user`) plus its guild.

    Discord: https://docs.discord.com/developers/events/gateway-events#integration-update
    """


class IntegrationDelete(Payload):
    """`INTEGRATION_DELETE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#integration-delete
    """

    id: Snowflake
    guild_id: Snowflake
    application_id: Snowflake | UnsetType = UNSET
    """The bot or OAuth2 application, for a Discord integration."""


class InviteCreate(Payload):
    """`INVITE_CREATE` dispatch.

    `target_application` (a partial application) is not modeled yet, as on `Invite`.

    Discord: https://docs.discord.com/developers/events/gateway-events#invite-create
    """

    REDACTED_FIELDS = frozenset({"code"})

    channel_id: Snowflake
    code: str
    created_at: datetime
    guild_id: Snowflake | UnsetType = UNSET
    inviter: User | UnsetType = UNSET
    max_age: int
    """Seconds."""
    max_uses: int
    target_type: InviteTargetType | UnsetType = UNSET
    target_user: User | UnsetType = UNSET
    temporary: bool
    uses: int
    """Always 0."""
    expires_at: datetime | None
    role_ids: list[Snowflake] | UnsetType = UNSET


class InviteDelete(Payload):
    """`INVITE_DELETE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#invite-delete
    """

    REDACTED_FIELDS = frozenset({"code"})

    channel_id: Snowflake
    guild_id: Snowflake | UnsetType = UNSET
    code: str


class TypingStart(Payload):
    """`TYPING_START` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#typing-start
    """

    channel_id: Snowflake
    guild_id: Snowflake | UnsetType = UNSET
    user_id: Snowflake
    timestamp: int
    """Unix time in seconds."""
    member: GuildMember | UnsetType = UNSET


class VoiceChannelEffectAnimationType(DiscordIntEnum):
    """How a voice channel effect is animated.

    Discord: https://docs.discord.com/developers/events/gateway-events#voice-channel-effect-send-animation-types
    """

    PREMIUM = 0
    """A fun animation, sent by a Nitro subscriber."""
    BASIC = 1


class VoiceChannelEffectSend(Payload):
    """`VOICE_CHANNEL_EFFECT_SEND` dispatch: an emoji or soundboard effect in the bot's voice channel.

    Discord: https://docs.discord.com/developers/events/gateway-events#voice-channel-effect-send
    """

    channel_id: Snowflake
    guild_id: Snowflake
    user_id: Snowflake
    emoji: Emoji | UnsetType | None = UNSET
    animation_type: VoiceChannelEffectAnimationType | UnsetType | None = UNSET
    animation_id: int | UnsetType = UNSET
    sound_id: Snowflake | UnsetType = UNSET
    """Discord documents a snowflake or an integer; both decode to a `Snowflake`."""
    sound_volume: float | UnsetType = UNSET
    """From 0 to 1."""


class VoiceServerUpdate(Payload):
    """`VOICE_SERVER_UPDATE` dispatch: where to connect for voice, and the token to connect with.

    A `None` endpoint means the voice server went away: disconnect, and wait for the next update.

    Discord: https://docs.discord.com/developers/events/gateway-events#voice-server-update
    """

    REDACTED_FIELDS = frozenset({"token"})

    token: str
    guild_id: Snowflake
    endpoint: str | None


class WebhooksUpdate(Payload):
    """`WEBHOOKS_UPDATE` dispatch: a webhook of the channel was created, updated or deleted.

    Discord: https://docs.discord.com/developers/events/gateway-events#webhooks-update
    """

    guild_id: Snowflake
    channel_id: Snowflake


class MessagePollVoteAdd(Payload):
    """`MESSAGE_POLL_VOTE_ADD` dispatch: one per answer chosen.

    Discord: https://docs.discord.com/developers/events/gateway-events#message-poll-vote-add
    """

    user_id: Snowflake
    channel_id: Snowflake
    message_id: Snowflake
    guild_id: Snowflake | UnsetType = UNSET
    answer_id: int


class MessagePollVoteRemove(Payload):
    """`MESSAGE_POLL_VOTE_REMOVE` dispatch: one per answer withdrawn.

    Discord: https://docs.discord.com/developers/events/gateway-events#message-poll-vote-remove
    """

    user_id: Snowflake
    channel_id: Snowflake
    message_id: Snowflake
    guild_id: Snowflake | UnsetType = UNSET
    answer_id: int


class RequestGuildMembersRateLimitMetadata(Payload):
    """`RateLimited.meta` when the limited command was Request Guild Members.

    Discord: https://docs.discord.com/developers/events/gateway-events#rate-limited-request-guild-member-rate-limit-metadata-structure
    """

    guild_id: Snowflake
    nonce: str | UnsetType = UNSET


class RateLimited(Payload):
    """`RATE_LIMITED` dispatch: a gateway command was refused until `retry_after` has passed.

    `meta` depends on the opcode, so it stays raw; `guild_members_metadata` reads the one kind
    Discord documents.

    Discord: https://docs.discord.com/developers/events/gateway-events#rate-limited
    """

    opcode: GatewayOpcode
    retry_after: float
    """Seconds."""
    meta: Raw

    def guild_members_metadata(self) -> RequestGuildMembersRateLimitMetadata | None:
        """The metadata of a limited Request Guild Members, or `None` for another opcode.

        Raises:
            PayloadDecodeError: The opcode is Request Guild Members but `meta` does not match.
        """
        if self.opcode is not GatewayOpcode.REQUEST_GUILD_MEMBERS:
            return None
        return decode_json(self.meta, RequestGuildMembersRateLimitMetadata)


DISPATCH_PAYLOADS: Final[Mapping[str, type[Payload]]] = {
    "APPLICATION_COMMAND_PERMISSIONS_UPDATE": GuildApplicationCommandPermissions,
    "AUTO_MODERATION_ACTION_EXECUTION": AutoModerationActionExecution,
    "AUTO_MODERATION_RULE_CREATE": AutoModerationRule,
    "AUTO_MODERATION_RULE_DELETE": AutoModerationRule,
    "AUTO_MODERATION_RULE_UPDATE": AutoModerationRule,
    "CHANNEL_CREATE": Channel,
    "CHANNEL_DELETE": Channel,
    "CHANNEL_INFO": ChannelInfo,
    "CHANNEL_PINS_UPDATE": ChannelPinsUpdate,
    "CHANNEL_UPDATE": Channel,
    "ENTITLEMENT_CREATE": Entitlement,
    "ENTITLEMENT_DELETE": Entitlement,
    "ENTITLEMENT_UPDATE": Entitlement,
    "GUILD_AUDIT_LOG_ENTRY_CREATE": GuildAuditLogEntryCreate,
    "GUILD_BAN_ADD": GuildBanAdd,
    "GUILD_BAN_REMOVE": GuildBanRemove,
    "GUILD_CREATE": GuildCreate,
    "GUILD_DELETE": GuildDelete,
    "GUILD_EMOJIS_UPDATE": GuildEmojisUpdate,
    "GUILD_INTEGRATIONS_UPDATE": GuildIntegrationsUpdate,
    "GUILD_MEMBERS_CHUNK": GuildMembersChunk,
    "GUILD_MEMBER_ADD": GuildMemberAdd,
    "GUILD_MEMBER_REMOVE": GuildMemberRemove,
    "GUILD_MEMBER_UPDATE": GuildMemberUpdate,
    "GUILD_ROLE_CREATE": GuildRoleCreate,
    "GUILD_ROLE_DELETE": GuildRoleDelete,
    "GUILD_ROLE_UPDATE": GuildRoleUpdate,
    "GUILD_SCHEDULED_EVENT_CREATE": GuildScheduledEvent,
    "GUILD_SCHEDULED_EVENT_DELETE": GuildScheduledEvent,
    "GUILD_SCHEDULED_EVENT_UPDATE": GuildScheduledEvent,
    "GUILD_SCHEDULED_EVENT_USER_ADD": GuildScheduledEventUserAdd,
    "GUILD_SCHEDULED_EVENT_USER_REMOVE": GuildScheduledEventUserRemove,
    "GUILD_SOUNDBOARD_SOUNDS_UPDATE": GuildSoundboardSoundsUpdate,
    "GUILD_SOUNDBOARD_SOUND_CREATE": SoundboardSound,
    "GUILD_SOUNDBOARD_SOUND_DELETE": GuildSoundboardSoundDelete,
    "GUILD_SOUNDBOARD_SOUND_UPDATE": SoundboardSound,
    "GUILD_STICKERS_UPDATE": GuildStickersUpdate,
    "GUILD_UPDATE": Guild,
    "INTEGRATION_CREATE": IntegrationCreate,
    "INTEGRATION_DELETE": IntegrationDelete,
    "INTEGRATION_UPDATE": IntegrationUpdate,
    "INVITE_CREATE": InviteCreate,
    "INVITE_DELETE": InviteDelete,
    "MESSAGE_CREATE": MessageCreate,
    "MESSAGE_DELETE": MessageDelete,
    "MESSAGE_DELETE_BULK": MessageDeleteBulk,
    "MESSAGE_POLL_VOTE_ADD": MessagePollVoteAdd,
    "MESSAGE_POLL_VOTE_REMOVE": MessagePollVoteRemove,
    "MESSAGE_REACTION_ADD": MessageReactionAdd,
    "MESSAGE_REACTION_REMOVE": MessageReactionRemove,
    "MESSAGE_REACTION_REMOVE_ALL": MessageReactionRemoveAll,
    "MESSAGE_REACTION_REMOVE_EMOJI": MessageReactionRemoveEmoji,
    "MESSAGE_UPDATE": MessageUpdate,
    "PRESENCE_UPDATE": PresenceUpdate,
    "RATE_LIMITED": RateLimited,
    "READY": Ready,
    "SOUNDBOARD_SOUNDS": SoundboardSounds,
    "STAGE_INSTANCE_CREATE": StageInstance,
    "STAGE_INSTANCE_DELETE": StageInstance,
    "STAGE_INSTANCE_UPDATE": StageInstance,
    "SUBSCRIPTION_CREATE": Subscription,
    "SUBSCRIPTION_DELETE": Subscription,
    "SUBSCRIPTION_UPDATE": Subscription,
    "THREAD_CREATE": ThreadCreate,
    "THREAD_DELETE": Channel,
    "THREAD_LIST_SYNC": ThreadListSync,
    "THREAD_MEMBERS_UPDATE": ThreadMembersUpdate,
    "THREAD_MEMBER_UPDATE": ThreadMemberUpdate,
    "THREAD_UPDATE": Channel,
    "TYPING_START": TypingStart,
    "USER_UPDATE": User,
    "VOICE_CHANNEL_EFFECT_SEND": VoiceChannelEffectSend,
    "VOICE_CHANNEL_START_TIME_UPDATE": VoiceChannelStartTimeUpdate,
    "VOICE_CHANNEL_STATUS_UPDATE": VoiceChannelStatusUpdate,
    "VOICE_SERVER_UPDATE": VoiceServerUpdate,
    "VOICE_STATE_UPDATE": VoiceState,
    "WEBHOOKS_UPDATE": WebhooksUpdate,
}
"""The type each documented dispatch decodes into, for `DispatchEvent.decode`.

Not listed: `RESUMED`, which carries no data, and `INTERACTION_CREATE`, whose type depends on the
interaction's `type` and is decoded by `parse_interaction`. A `GUILD_CREATE` for a guild in an outage
is an `UnavailableGuild`; `GuildCreate` documents how to tell.

Discord: https://docs.discord.com/developers/events/gateway-events#receive-events
"""
