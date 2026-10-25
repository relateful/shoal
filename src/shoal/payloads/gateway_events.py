"""Gateway payloads sent and received over the websocket.

Discord: https://docs.discord.com/developers/events/gateway-events

Dispatch event bodies that are plain resources (`CHANNEL_CREATE` is a `Channel`) reuse the resource
type; only events with their own shape are declared here. Not yet modeled: stage instances, scheduled
events and soundboard sounds inside `GUILD_CREATE`, and the events of resources Shoal does not model
yet; `docs/coverage.md` lists them.
"""

from datetime import datetime
from typing import Final, override

import msgspec
from msgspec import UNSET, Raw, UnsetType

from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload
from shoal.payloads.channel import Channel, ChannelType, ThreadMember
from shoal.payloads.emoji import Emoji
from shoal.payloads.gateway import GatewayOpcode, Intents
from shoal.payloads.guild import Guild, GuildMember, GuildMemberFlags, UnavailableGuild
from shoal.payloads.message import Message, ReactionType
from shoal.payloads.permissions import Role
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

    token: str
    session_id: str
    seq: int

    @override
    def __repr__(self) -> str:
        """Everything but the token, which must never reach a log or an error tracker."""
        return f"Resume(session_id={self.session_id!r}, seq={self.seq}, token=<redacted>)"


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
    """`GUILD_ROLE_CREATE` dispatch. `GUILD_ROLE_UPDATE` has the same shape.

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-role-create
    """

    guild_id: Snowflake
    role: Role


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


class ThreadMembersUpdate(Payload):
    """`THREAD_MEMBERS_UPDATE` dispatch.

    Discord: https://docs.discord.com/developers/events/gateway-events#thread-members-update
    """

    id: Snowflake
    guild_id: Snowflake
    member_count: int
    added_members: list[ThreadMember] | UnsetType = UNSET
    removed_member_ids: list[Snowflake] | UnsetType = UNSET
