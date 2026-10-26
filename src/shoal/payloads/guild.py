"""Guilds and guild members.

Discord: https://docs.discord.com/developers/resources/guild

Not yet modeled: `Guild.welcome_screen`, `Guild.stickers`, `Guild.incidents_data`, guild previews,
widgets, bans, integrations and onboarding. Decoding ignores those keys until they are added.
"""

from datetime import datetime

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload
from shoal.payloads.emoji import Emoji
from shoal.payloads.permissions import Permissions, Role
from shoal.payloads.user import AvatarDecorationData, Collectibles, User


class VerificationLevel(DiscordIntEnum):
    """What a member must do before talking in the guild.

    Discord: https://docs.discord.com/developers/resources/guild#guild-object-verification-level
    """

    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    VERY_HIGH = 4


class DefaultMessageNotificationLevel(DiscordIntEnum):
    """Default notification setting for new members.

    Discord: https://docs.discord.com/developers/resources/guild#guild-object-default-message-notification-level
    """

    ALL_MESSAGES = 0
    ONLY_MENTIONS = 1


class ExplicitContentFilterLevel(DiscordIntEnum):
    """Whose media is scanned for explicit content.

    Discord: https://docs.discord.com/developers/resources/guild#guild-object-explicit-content-filter-level
    """

    DISABLED = 0
    MEMBERS_WITHOUT_ROLES = 1
    ALL_MEMBERS = 2


class MFALevel(DiscordIntEnum):
    """Whether moderation actions require 2FA.

    Discord: https://docs.discord.com/developers/resources/guild#guild-object-mfa-level
    """

    NONE = 0
    ELEVATED = 1


class PremiumTier(DiscordIntEnum):
    """Server Boost level.

    Discord: https://docs.discord.com/developers/resources/guild#guild-object-premium-tier
    """

    NONE = 0
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3


class GuildNSFWLevel(DiscordIntEnum):
    """Guild age-restriction level.

    Discord: https://docs.discord.com/developers/resources/guild#guild-object-guild-nsfw-level
    """

    DEFAULT = 0
    EXPLICIT = 1
    SAFE = 2
    AGE_RESTRICTED = 3


class SystemChannelFlags(BaseFlags):
    """Which notices the system channel suppresses.

    Discord: https://docs.discord.com/developers/resources/guild#guild-object-system-channel-flags
    """

    __slots__ = ()

    suppress_join_notifications = flag(0)
    suppress_premium_subscriptions = flag(1)
    suppress_guild_reminder_notifications = flag(2)
    suppress_join_notification_replies = flag(3)
    suppress_role_subscription_purchase_notifications = flag(4)
    suppress_role_subscription_purchase_notification_replies = flag(5)


class GuildFeature(DiscordStrEnum):
    """A feature a guild has unlocked or enabled.

    Discord: https://docs.discord.com/developers/resources/guild#guild-object-guild-features
    """

    ANIMATED_BANNER = "ANIMATED_BANNER"
    ANIMATED_ICON = "ANIMATED_ICON"
    APPLICATION_COMMAND_PERMISSIONS_V2 = "APPLICATION_COMMAND_PERMISSIONS_V2"
    AUTO_MODERATION = "AUTO_MODERATION"
    BANNER = "BANNER"
    COMMUNITY = "COMMUNITY"
    CREATOR_MONETIZABLE_PROVISIONAL = "CREATOR_MONETIZABLE_PROVISIONAL"
    CREATOR_STORE_PAGE = "CREATOR_STORE_PAGE"
    DEVELOPER_SUPPORT_SERVER = "DEVELOPER_SUPPORT_SERVER"
    DISCOVERABLE = "DISCOVERABLE"
    ENHANCED_ROLE_COLORS = "ENHANCED_ROLE_COLORS"
    FEATURABLE = "FEATURABLE"
    GUESTS_ENABLED = "GUESTS_ENABLED"
    GUILD_TAGS = "GUILD_TAGS"
    INVITES_DISABLED = "INVITES_DISABLED"
    INVITE_SPLASH = "INVITE_SPLASH"
    MEMBER_VERIFICATION_GATE_ENABLED = "MEMBER_VERIFICATION_GATE_ENABLED"
    MORE_SOUNDBOARD = "MORE_SOUNDBOARD"
    MORE_STICKERS = "MORE_STICKERS"
    NEWS = "NEWS"
    PARTNERED = "PARTNERED"
    PREVIEW_ENABLED = "PREVIEW_ENABLED"
    PRUNE_REQUIRES_ADMIN = "PRUNE_REQUIRES_ADMIN"
    RAID_ALERTS_DISABLED = "RAID_ALERTS_DISABLED"
    ROLE_ICONS = "ROLE_ICONS"
    ROLE_SUBSCRIPTIONS_AVAILABLE_FOR_PURCHASE = "ROLE_SUBSCRIPTIONS_AVAILABLE_FOR_PURCHASE"
    ROLE_SUBSCRIPTIONS_ENABLED = "ROLE_SUBSCRIPTIONS_ENABLED"
    SOUNDBOARD = "SOUNDBOARD"
    TICKETED_EVENTS_ENABLED = "TICKETED_EVENTS_ENABLED"
    VANITY_URL = "VANITY_URL"
    VERIFIED = "VERIFIED"
    VIP_REGIONS = "VIP_REGIONS"
    WELCOME_SCREEN_ENABLED = "WELCOME_SCREEN_ENABLED"


class GuildMemberFlags(BaseFlags):
    """Flags on a guild member.

    Discord: https://docs.discord.com/developers/resources/guild#guild-member-object-guild-member-flags
    """

    __slots__ = ()

    did_rejoin = flag(0)
    completed_onboarding = flag(1)
    bypasses_verification = flag(2)
    started_onboarding = flag(3)
    is_guest = flag(4)
    started_home_actions = flag(5)
    completed_home_actions = flag(6)
    automod_quarantined_username = flag(7)
    dm_settings_upsell_acknowledged = flag(9)
    automod_quarantined_guild_tag = flag(10)


class Guild(Payload):
    """A guild (server).

    Discord: https://docs.discord.com/developers/resources/guild#guild-object
    """

    id: Snowflake
    name: str
    icon: str | None
    icon_hash: str | UnsetType | None = UNSET
    splash: str | None
    discovery_splash: str | None
    owner: bool | UnsetType = UNSET
    owner_id: Snowflake
    permissions: Permissions | UnsetType = UNSET
    region: str | UnsetType | None = UNSET
    afk_channel_id: Snowflake | None
    afk_timeout: int
    widget_enabled: bool | UnsetType = UNSET
    widget_channel_id: Snowflake | UnsetType | None = UNSET
    verification_level: VerificationLevel
    default_message_notifications: DefaultMessageNotificationLevel
    explicit_content_filter: ExplicitContentFilterLevel
    roles: list[Role]
    emojis: list[Emoji]
    features: list[GuildFeature]
    mfa_level: MFALevel
    application_id: Snowflake | None
    system_channel_id: Snowflake | None
    system_channel_flags: SystemChannelFlags
    rules_channel_id: Snowflake | None
    max_presences: int | UnsetType | None = UNSET
    max_members: int | UnsetType = UNSET
    vanity_url_code: str | None
    description: str | None
    banner: str | None
    premium_tier: PremiumTier
    premium_subscription_count: int | UnsetType = UNSET
    preferred_locale: str
    public_updates_channel_id: Snowflake | None
    max_video_channel_users: int | UnsetType = UNSET
    max_stage_video_channel_users: int | UnsetType = UNSET
    approximate_member_count: int | UnsetType = UNSET
    approximate_presence_count: int | UnsetType = UNSET
    nsfw_level: GuildNSFWLevel
    premium_progress_bar_enabled: bool
    safety_alerts_channel_id: Snowflake | None


class PartialGuild(Payload):
    """A guild the current user is in, as Get Current User Guilds lists it.

    Discord does not give this object a field table; its fields follow the documented example.

    Discord: https://docs.discord.com/developers/resources/user#get-current-user-guilds-example-partial-guild
    """

    id: Snowflake
    name: str
    icon: str | None
    banner: str | None
    owner: bool
    """Whether the current user owns the guild."""
    permissions: Permissions
    """The current user's permissions in the guild."""
    features: list[GuildFeature]
    approximate_member_count: int | UnsetType = UNSET
    """Only with `with_counts`."""
    approximate_presence_count: int | UnsetType = UNSET
    """Only with `with_counts`."""


class UnavailableGuild(Payload):
    """A guild Discord has not sent yet (startup) or cannot serve (outage).

    Discord: https://docs.discord.com/developers/resources/guild#unavailable-guild-object
    """

    id: Snowflake
    unavailable: bool | UnsetType = UNSET


class GuildMember(Payload):
    """A user's membership in a guild.

    `user` is absent in `MESSAGE_CREATE` and `MESSAGE_UPDATE` member objects, which belong to the
    message author.

    Discord: https://docs.discord.com/developers/resources/guild#guild-member-object
    """

    user: User | UnsetType = UNSET
    nick: str | UnsetType | None = UNSET
    avatar: str | UnsetType | None = UNSET
    banner: str | UnsetType | None = UNSET
    roles: list[Snowflake]
    joined_at: datetime | None
    premium_since: datetime | UnsetType | None = UNSET
    deaf: bool
    mute: bool
    flags: GuildMemberFlags
    pending: bool | UnsetType = UNSET
    permissions: Permissions | UnsetType = UNSET
    communication_disabled_until: datetime | UnsetType | None = UNSET
    avatar_decoration_data: AvatarDecorationData | UnsetType | None = UNSET
    collectibles: Collectibles | UnsetType | None = UNSET


class PartialMember(Payload):
    """A guild member without `user`, `deaf` and `mute`, as interactions resolve them.

    The member's user is in the same resolved data, under the same ID.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-resolved-data-structure
    """

    nick: str | UnsetType | None = UNSET
    avatar: str | UnsetType | None = UNSET
    banner: str | UnsetType | None = UNSET
    roles: list[Snowflake]
    joined_at: datetime | None
    premium_since: datetime | UnsetType | None = UNSET
    flags: GuildMemberFlags
    pending: bool | UnsetType = UNSET
    permissions: Permissions | UnsetType = UNSET
    communication_disabled_until: datetime | UnsetType | None = UNSET
    avatar_decoration_data: AvatarDecorationData | UnsetType | None = UNSET
    collectibles: Collectibles | UnsetType | None = UNSET
