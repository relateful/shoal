"""Invites to guilds and group DMs.

Discord: https://docs.discord.com/developers/resources/invite

Not yet modeled: `Invite.target_application` (partial application) and the deprecated stage
instance object. Decoding ignores those keys until they are added.
"""

from datetime import datetime

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload
from shoal.payloads.channel import Channel
from shoal.payloads.guild import GuildFeature, GuildNSFWLevel, VerificationLevel
from shoal.payloads.permissions import RoleColors
from shoal.payloads.scheduled_event import GuildScheduledEvent
from shoal.payloads.user import User


class InviteType(DiscordIntEnum):
    """What an invite is for.

    Discord: https://docs.discord.com/developers/resources/invite#invite-object-invite-types
    """

    GUILD = 0
    GROUP_DM = 1
    FRIEND = 2


class InviteTargetType(DiscordIntEnum):
    """What a voice channel invite opens.

    Discord: https://docs.discord.com/developers/resources/invite#invite-object-invite-target-types
    """

    STREAM = 1
    EMBEDDED_APPLICATION = 2


class GuildInviteFlags(BaseFlags):
    """Flags on a guild invite.

    Discord: https://docs.discord.com/developers/resources/invite#invite-object-guild-invite-flags
    """

    __slots__ = ()

    is_guest_invite = flag(0)
    """A guest invite for a voice channel."""


class InviteGuild(Payload):
    """The partial guild an invite carries.

    Discord does not give this object a field table; its fields follow the documented example.

    Discord: https://docs.discord.com/developers/resources/invite#invite-object-example-invite-object
    """

    id: Snowflake
    name: str
    splash: str | UnsetType | None = UNSET
    banner: str | UnsetType | None = UNSET
    description: str | UnsetType | None = UNSET
    icon: str | UnsetType | None = UNSET
    features: list[GuildFeature] | UnsetType = UNSET
    verification_level: VerificationLevel | UnsetType = UNSET
    vanity_url_code: str | UnsetType | None = UNSET
    nsfw_level: GuildNSFWLevel | UnsetType = UNSET
    premium_subscription_count: int | UnsetType = UNSET


class InviteRole(Payload):
    """A role an invite gives the users who accept it: a partial role.

    Discord: https://docs.discord.com/developers/resources/invite#invite-object-invite-structure
    """

    id: Snowflake
    name: str
    position: int
    color: int
    colors: RoleColors
    icon: str | UnsetType | None = UNSET
    unicode_emoji: str | UnsetType | None = UNSET


class Invite(Payload):
    """A code that adds a user to a guild or group DM.

    Discord: https://docs.discord.com/developers/resources/invite#invite-object
    """

    type: InviteType
    code: str
    guild: InviteGuild | UnsetType = UNSET
    channel: Channel | None
    """A partial channel."""
    inviter: User | UnsetType = UNSET
    target_type: InviteTargetType | UnsetType = UNSET
    target_user: User | UnsetType = UNSET
    """The user whose stream a stream invite shows."""
    approximate_presence_count: int | UnsetType = UNSET
    """Only from Get Invite with `with_counts`."""
    approximate_member_count: int | UnsetType = UNSET
    """Only from Get Invite with `with_counts`."""
    expires_at: datetime | None
    guild_scheduled_event: GuildScheduledEvent | UnsetType = UNSET
    """Only when asked for with `guild_scheduled_event_id`."""
    flags: GuildInviteFlags | UnsetType = UNSET
    roles: list[InviteRole] | UnsetType = UNSET
    """Roles given to the users who accept it."""


class InviteWithMetadata(Invite):
    """An invite with its usage, as the guild and channel invite lists return it.

    Discord: https://docs.discord.com/developers/resources/invite#invite-metadata-object
    """

    uses: int
    max_uses: int
    max_age: int
    """Seconds until it expires; 0 for never."""
    temporary: bool
    """Whether it grants temporary membership."""
    created_at: datetime


class GuildInvite(Invite):
    """An invite from Get Guild Invites: the metadata is only there with Manage Guild.

    Discord: https://docs.discord.com/developers/resources/guild#get-guild-invites
    """

    uses: int | UnsetType = UNSET
    max_uses: int | UnsetType = UNSET
    max_age: int | UnsetType = UNSET
    temporary: bool | UnsetType = UNSET
    created_at: datetime | UnsetType = UNSET


class VanityURL(Payload):
    """A guild's vanity invite and how often it was used: a partial invite.

    Discord: https://docs.discord.com/developers/resources/guild#get-guild-vanity-url-example-partial-invite-object
    """

    code: str | None
    """`None` when the guild has no vanity URL set."""
    uses: int


class CreateInviteParams(Payload):
    """JSON body of Create Channel Invite. Every field is optional, but the body is always sent.

    Discord: https://docs.discord.com/developers/resources/channel#create-channel-invite-jsonform-params
    """

    max_age: int | UnsetType = UNSET
    """Seconds until it expires, 0 for never, at most 604800; Discord's default is 86400."""
    max_uses: int | UnsetType = UNSET
    """0 for unlimited, at most 100; Discord's default is 0."""
    temporary: bool | UnsetType = UNSET
    """Grant temporary membership only."""
    unique: bool | UnsetType = UNSET
    """Always create a new invite rather than reuse a similar one."""
    target_type: InviteTargetType | UnsetType = UNSET
    target_user_id: Snowflake | UnsetType = UNSET
    """Required with `STREAM`: the streaming user."""
    target_application_id: Snowflake | UnsetType = UNSET
    """Required with `EMBEDDED_APPLICATION`: an app with the `EMBEDDED` flag."""
    target_user_ids: list[Snowflake] | UnsetType = UNSET
    """The only users who can see and accept the invite; at most 1000."""
    role_ids: list[Snowflake] | UnsetType = UNSET
    """Roles given to the users who accept; needs Manage Roles."""


class GetInviteParams(Payload):
    """Query of Get Invite.

    Discord: https://docs.discord.com/developers/resources/invite#get-invite-query-string-params
    """

    with_counts: bool | UnsetType = UNSET
    guild_scheduled_event_id: Snowflake | UnsetType = UNSET


class TargetUserIDs(Payload):
    """JSON body of Bulk-Add Target Users and Bulk-Delete Target Users.

    Discord: https://docs.discord.com/developers/resources/invite#bulk-add-target-users-json-params
    """

    user_ids: list[Snowflake]
    """At most 1000."""


class TargetUsersJobStatusCode(DiscordIntEnum):
    """Where the processing of an invite's target user list stands.

    Discord: https://docs.discord.com/developers/resources/invite#get-target-users-job-status-status-codes
    """

    UNSPECIFIED = 0
    PROCESSING = 1
    COMPLETED = 2
    FAILED = 3
    """See `error_message`."""


class TargetUsersJobStatus(Payload):
    """The progress of processing an invite's target user list.

    Discord does not give this object a field table; its fields follow the documented example.

    Discord: https://docs.discord.com/developers/resources/invite#get-target-users-job-status-example-response
    """

    status: TargetUsersJobStatusCode
    total_users: int
    processed_users: int
    created_at: datetime
    completed_at: datetime | UnsetType | None = UNSET
    """Optional here: Discord documents this object only by example, so a running job may leave it out."""
    error_message: str | UnsetType | None = UNSET
