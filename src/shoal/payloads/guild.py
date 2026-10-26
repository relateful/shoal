"""Guilds and guild members.

Discord: https://docs.discord.com/developers/resources/guild
"""

from datetime import datetime

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.api import ImageData
from shoal.payloads.base import Payload
from shoal.payloads.emoji import Emoji
from shoal.payloads.permissions import Permissions, Role, RoleColors
from shoal.payloads.sticker import Sticker
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


class WelcomeScreenChannel(Payload):
    """A channel shown on a Community guild's welcome screen.

    Discord: https://docs.discord.com/developers/resources/guild#welcome-screen-object-welcome-screen-channel-structure
    """

    channel_id: Snowflake
    description: str
    emoji_id: Snowflake | None
    """Set for a custom emoji."""
    emoji_name: str | None
    """The custom emoji's name, the unicode emoji, or `None` for no emoji."""


class WelcomeScreen(Payload):
    """What a Community guild shows new members.

    Discord: https://docs.discord.com/developers/resources/guild#welcome-screen-object
    """

    description: str | None
    welcome_channels: list[WelcomeScreenChannel]
    """Up to 5."""


class IncidentsData(Payload):
    """Safety actions in force in a guild, and recent incidents.

    Discord: https://docs.discord.com/developers/resources/guild#incidents-data-object
    """

    invites_disabled_until: datetime | None
    dms_disabled_until: datetime | None
    dm_spam_detected_at: datetime | UnsetType | None = UNSET
    raid_detected_at: datetime | UnsetType | None = UNSET


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
    welcome_screen: WelcomeScreen | UnsetType = UNSET
    nsfw_level: GuildNSFWLevel
    stickers: list[Sticker] | UnsetType = UNSET
    premium_progress_bar_enabled: bool
    safety_alerts_channel_id: Snowflake | None
    incidents_data: IncidentsData | UnsetType | None = UNSET
    """Discord's table lists it as always present; Get Guild's own example leaves it out."""


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


class GuildPreview(Payload):
    """What anyone can see of a discoverable guild.

    Discord: https://docs.discord.com/developers/resources/guild#guild-preview-object
    """

    id: Snowflake
    name: str
    icon: str | None
    splash: str | None
    discovery_splash: str | None
    emojis: list[Emoji]
    features: list[GuildFeature]
    approximate_member_count: int
    approximate_presence_count: int
    description: str | None
    stickers: list[Sticker]


class GuildWidgetSettings(Payload):
    """Whether a guild's widget is on, and the channel its invite leads to.

    Discord: https://docs.discord.com/developers/resources/guild#guild-widget-settings-object
    """

    enabled: bool
    channel_id: Snowflake | None


class WidgetChannel(Payload):
    """A voice or stage channel listed on a guild widget: a partial channel.

    Discord: https://docs.discord.com/developers/resources/guild#guild-widget-object-example-guild-widget
    """

    id: Snowflake
    name: str
    position: int


class WidgetMember(Payload):
    """An online member listed on a guild widget. `id`, `discriminator` and `avatar` are anonymized.

    Discord: https://docs.discord.com/developers/resources/guild#guild-widget-object-example-guild-widget
    """

    id: Snowflake
    username: str
    discriminator: str
    avatar: str | None
    status: str
    avatar_url: str


class GuildWidget(Payload):
    """A guild's public widget.

    Discord: https://docs.discord.com/developers/resources/guild#guild-widget-object
    """

    id: Snowflake
    name: str
    instant_invite: str | None
    channels: list[WidgetChannel]
    members: list[WidgetMember]
    """Up to 100."""
    presence_count: int


class WidgetStyle(DiscordStrEnum):
    """The look of a guild widget image.

    Discord: https://docs.discord.com/developers/resources/guild#get-guild-widget-image-widget-style-options
    """

    BANNER1 = "banner1"
    BANNER2 = "banner2"
    BANNER3 = "banner3"
    BANNER4 = "banner4"
    SHIELD = "shield"
    """Discord's default."""


class IntegrationExpireBehavior(DiscordIntEnum):
    """What happens to a subscriber when their subscription ends.

    Discord: https://docs.discord.com/developers/resources/guild#integration-object-integration-expire-behaviors
    """

    REMOVE_ROLE = 0
    KICK = 1


class IntegrationAccount(Payload):
    """The account on the other service an integration belongs to.

    Discord: https://docs.discord.com/developers/resources/guild#integration-account-object
    """

    id: str
    name: str


class IntegrationApplication(Payload):
    """The app behind a Discord integration.

    Discord: https://docs.discord.com/developers/resources/guild#integration-application-object
    """

    id: Snowflake
    name: str
    icon: str | None
    description: str
    bot: User | UnsetType = UNSET


class Integration(Payload):
    """A Twitch, YouTube, app or role subscription integration in a guild.

    The subscription fields are absent on bot integrations.

    Discord: https://docs.discord.com/developers/resources/guild#integration-object
    """

    id: Snowflake
    name: str
    type: str
    """`twitch`, `youtube`, `discord` or `guild_subscription`."""
    enabled: bool
    syncing: bool | UnsetType = UNSET
    role_id: Snowflake | UnsetType = UNSET
    """The role given to subscribers."""
    enable_emoticons: bool | UnsetType = UNSET
    expire_behavior: IntegrationExpireBehavior | UnsetType = UNSET
    expire_grace_period: int | UnsetType = UNSET
    """Days."""
    user: User | UnsetType = UNSET
    account: IntegrationAccount
    synced_at: datetime | UnsetType = UNSET
    subscriber_count: int | UnsetType = UNSET
    revoked: bool | UnsetType = UNSET
    application: IntegrationApplication | UnsetType = UNSET
    scopes: list[str] | UnsetType = UNSET
    """OAuth2 scopes the app was authorized for."""


class Ban(Payload):
    """A banned user.

    Discord: https://docs.discord.com/developers/resources/guild#ban-object
    """

    reason: str | None
    user: User


class OnboardingMode(DiscordIntEnum):
    """What counts towards the requirements for turning onboarding on.

    Discord: https://docs.discord.com/developers/resources/guild#guild-onboarding-object-onboarding-mode
    """

    ONBOARDING_DEFAULT = 0
    """Default channels only."""
    ONBOARDING_ADVANCED = 1
    """Default channels and questions."""


class PromptType(DiscordIntEnum):
    """How an onboarding question is shown.

    Discord: https://docs.discord.com/developers/resources/guild#guild-onboarding-object-prompt-types
    """

    MULTIPLE_CHOICE = 0
    DROPDOWN = 1


class PromptOption(Payload):
    """An answer to an onboarding question.

    Discord: https://docs.discord.com/developers/resources/guild#guild-onboarding-object-prompt-option-structure
    """

    id: Snowflake
    channel_ids: list[Snowflake]
    """Channels a member who picks it is added to."""
    role_ids: list[Snowflake]
    """Roles a member who picks it is given."""
    emoji: Emoji | UnsetType = UNSET
    emoji_id: Snowflake | UnsetType = UNSET
    emoji_name: str | UnsetType = UNSET
    emoji_animated: bool | UnsetType = UNSET
    title: str
    description: str | None


class OnboardingPrompt(Payload):
    """An onboarding question.

    Discord: https://docs.discord.com/developers/resources/guild#guild-onboarding-object-onboarding-prompt-structure
    """

    id: Snowflake
    type: PromptType
    options: list[PromptOption]
    title: str
    single_select: bool
    required: bool
    in_onboarding: bool
    """`False` shows it only in Channels & Roles."""


class GuildOnboarding(Payload):
    """A guild's onboarding flow.

    Discord: https://docs.discord.com/developers/resources/guild#guild-onboarding-object
    """

    guild_id: Snowflake
    prompts: list[OnboardingPrompt]
    default_channel_ids: list[Snowflake]
    """Channels every member is added to."""
    enabled: bool
    mode: OnboardingMode


class EditGuildParams(Payload):
    """JSON body of Modify Guild. Needs Manage Guild; changing `COMMUNITY` needs Administrator.

    Discord: https://docs.discord.com/developers/resources/guild#modify-guild-json-params
    """

    name: str | UnsetType = UNSET
    region: str | UnsetType | None = UNSET
    """Deprecated; set `rtc_region` on voice channels instead."""
    verification_level: VerificationLevel | UnsetType | None = UNSET
    default_message_notifications: DefaultMessageNotificationLevel | UnsetType | None = UNSET
    explicit_content_filter: ExplicitContentFilterLevel | UnsetType | None = UNSET
    afk_channel_id: Snowflake | UnsetType | None = UNSET
    afk_timeout: int | UnsetType = UNSET
    """Seconds: 60, 300, 900, 1800 or 3600."""
    icon: ImageData | UnsetType | None = UNSET
    """1024x1024; an animated GIF needs the `ANIMATED_ICON` feature."""
    splash: ImageData | UnsetType | None = UNSET
    """16:9; needs the `INVITE_SPLASH` feature."""
    discovery_splash: ImageData | UnsetType | None = UNSET
    """16:9; needs the `DISCOVERABLE` feature."""
    banner: ImageData | UnsetType | None = UNSET
    """16:9; needs the `BANNER` feature, and `ANIMATED_BANNER` for a GIF."""
    system_channel_id: Snowflake | UnsetType | None = UNSET
    system_channel_flags: SystemChannelFlags | UnsetType = UNSET
    rules_channel_id: Snowflake | UnsetType | None = UNSET
    public_updates_channel_id: Snowflake | UnsetType | None = UNSET
    preferred_locale: str | UnsetType | None = UNSET
    features: list[GuildFeature] | UnsetType = UNSET
    description: str | UnsetType | None = UNSET
    premium_progress_bar_enabled: bool | UnsetType = UNSET
    safety_alerts_channel_id: Snowflake | UnsetType | None = UNSET


class ListMembersParams(Payload):
    """Query of List Guild Members. Needs the Guild Members privileged intent.

    Discord: https://docs.discord.com/developers/resources/guild#list-guild-members-query-string-params
    """

    limit: int | UnsetType = UNSET
    """1 to 1000; Discord's default is 1."""
    after: Snowflake | UnsetType = UNSET
    """The highest user ID of the previous page."""


class SearchMembersParams(Payload):
    """Query of Search Guild Members: members whose username or nickname starts with `query`.

    Discord: https://docs.discord.com/developers/resources/guild#search-guild-members-query-string-params
    """

    query: str
    limit: int | UnsetType = UNSET
    """1 to 1000; Discord's default is 1."""


class AddMemberParams(Payload):
    """JSON body of Add Guild Member.

    Discord: https://docs.discord.com/developers/resources/guild#add-guild-member-json-params
    """

    REDACTED_FIELDS = frozenset({"access_token"})

    access_token: str
    """An OAuth2 token of the user, with the `guilds.join` scope, granted to this bot's app."""
    nick: str | UnsetType = UNSET
    """Needs Manage Nicknames."""
    roles: list[Snowflake] | UnsetType = UNSET
    """Needs Manage Roles."""
    mute: bool | UnsetType = UNSET
    """Needs Mute Members."""
    deaf: bool | UnsetType = UNSET
    """Needs Deafen Members."""


class EditMemberParams(Payload):
    """JSON body of Modify Guild Member. Each field needs its own permission (see Discord's table).

    Discord: https://docs.discord.com/developers/resources/guild#modify-guild-member-json-params
    """

    nick: str | UnsetType | None = UNSET
    roles: list[Snowflake] | UnsetType | None = UNSET
    mute: bool | UnsetType | None = UNSET
    """Fails unless the member is in a voice channel."""
    deaf: bool | UnsetType | None = UNSET
    """Fails unless the member is in a voice channel."""
    channel_id: Snowflake | UnsetType | None = UNSET
    """Move the member to this voice channel; `None` disconnects them."""
    communication_disabled_until: datetime | UnsetType | None = UNSET
    """Time the member out until then, up to 28 days ahead; `None` ends a timeout."""
    flags: GuildMemberFlags | UnsetType | None = UNSET
    """Only `bypasses_verification` can be changed."""


class EditCurrentMemberParams(Payload):
    """JSON body of Modify Current Member.

    Discord: https://docs.discord.com/developers/resources/guild#modify-current-member-json-params
    """

    nick: str | UnsetType | None = UNSET
    """Needs Change Nickname."""
    banner: ImageData | UnsetType | None = UNSET
    avatar: ImageData | UnsetType | None = UNSET
    bio: str | UnsetType | None = UNSET


class EditCurrentNickParams(Payload):
    """JSON body of the deprecated Modify Current User Nick.

    Discord: https://docs.discord.com/developers/resources/guild#modify-current-user-nick-json-params
    """

    nick: str | UnsetType | None = UNSET


class ListBansParams(Payload):
    """Query of Get Guild Bans. Bans come in ascending user ID order; `before` wins over `after`.

    Discord: https://docs.discord.com/developers/resources/guild#get-guild-bans-query-string-params
    """

    limit: int | UnsetType = UNSET
    """Up to 1000, Discord's default."""
    before: Snowflake | UnsetType = UNSET
    after: Snowflake | UnsetType = UNSET


class BanParams(Payload):
    """JSON body of Create Guild Ban.

    Discord: https://docs.discord.com/developers/resources/guild#create-guild-ban-json-params
    """

    delete_message_days: int | UnsetType = UNSET
    """Deprecated; use `delete_message_seconds`."""
    delete_message_seconds: int | UnsetType = UNSET
    """Delete the user's messages from this many seconds back, up to 604800 (7 days)."""


class BulkBanParams(Payload):
    """JSON body of Bulk Guild Ban.

    Discord: https://docs.discord.com/developers/resources/guild#bulk-guild-ban-json-params
    """

    user_ids: list[Snowflake]
    """Up to 200."""
    delete_message_seconds: int | UnsetType = UNSET
    """Up to 604800 (7 days)."""


class BulkBanResponse(Payload):
    """Who Bulk Guild Ban banned, and who it could not (or who were banned already).

    Discord: https://docs.discord.com/developers/resources/guild#bulk-guild-ban-bulk-ban-response
    """

    banned_users: list[Snowflake]
    failed_users: list[Snowflake]


class CreateRoleParams(Payload):
    """JSON body of Create Guild Role.

    Discord: https://docs.discord.com/developers/resources/guild#create-guild-role-json-params
    """

    name: str | UnsetType = UNSET
    """Up to 100 characters; Discord's default is "new role"."""
    permissions: Permissions | UnsetType = UNSET
    """Discord's default is the guild's @everyone permissions."""
    color: int | UnsetType = UNSET
    """Deprecated; use `colors`."""
    colors: RoleColors | UnsetType = UNSET
    hoist: bool | UnsetType = UNSET
    icon: ImageData | UnsetType | None = UNSET
    """Needs the `ROLE_ICONS` feature."""
    unicode_emoji: str | UnsetType | None = UNSET
    """Needs the `ROLE_ICONS` feature."""
    mentionable: bool | UnsetType = UNSET


class RolePositionParams(Payload):
    """One role's new position, in the body of Modify Guild Role Positions.

    Discord: https://docs.discord.com/developers/resources/guild#modify-guild-role-positions-json-params
    """

    id: Snowflake
    position: int | UnsetType | None = UNSET


class EditRoleParams(Payload):
    """JSON body of Modify Guild Role.

    Discord: https://docs.discord.com/developers/resources/guild#modify-guild-role-json-params
    """

    name: str | UnsetType | None = UNSET
    permissions: Permissions | UnsetType | None = UNSET
    color: int | UnsetType | None = UNSET
    """Deprecated; use `colors`."""
    colors: RoleColors | UnsetType | None = UNSET
    hoist: bool | UnsetType | None = UNSET
    icon: ImageData | UnsetType | None = UNSET
    unicode_emoji: str | UnsetType | None = UNSET
    mentionable: bool | UnsetType | None = UNSET


class GetPruneCountParams(Payload):
    """Query of Get Guild Prune Count.

    Discord: https://docs.discord.com/developers/resources/guild#get-guild-prune-count-query-string-params
    """

    days: int | UnsetType = UNSET
    """1 to 30; Discord's default is 7."""
    include_roles: list[Snowflake] | UnsetType = UNSET
    """Also count members whose roles are all among these. Sent comma-separated."""


class PruneParams(Payload):
    """JSON body of Begin Guild Prune.

    Discord: https://docs.discord.com/developers/resources/guild#begin-guild-prune-json-params
    """

    days: int | UnsetType = UNSET
    """1 to 30; Discord's default is 7."""
    compute_prune_count: bool | UnsetType = UNSET
    """`False` makes `pruned` `None`; recommended for large guilds."""
    include_roles: list[Snowflake] | UnsetType = UNSET
    reason: str | UnsetType = UNSET
    """Deprecated; pass `reason` to the method, which sends the audit log header."""


class PruneCount(Payload):
    """How many members a prune removes, or would remove.

    Discord: https://docs.discord.com/developers/resources/guild#get-guild-prune-count
    """

    pruned: int | None
    """`None` when `compute_prune_count` was false."""


class EditWidgetParams(Payload):
    """JSON body of Modify Guild Widget.

    Discord: https://docs.discord.com/developers/resources/guild#modify-guild-widget
    """

    enabled: bool | UnsetType = UNSET
    channel_id: Snowflake | UnsetType | None = UNSET


class EditWelcomeScreenParams(Payload):
    """JSON body of Modify Guild Welcome Screen.

    Discord: https://docs.discord.com/developers/resources/guild#modify-guild-welcome-screen-json-params
    """

    enabled: bool | UnsetType | None = UNSET
    welcome_channels: list[WelcomeScreenChannel] | UnsetType | None = UNSET
    description: str | UnsetType | None = UNSET


class PromptOptionParams(Payload):
    """An onboarding answer in a request; it takes the emoji as separate fields, not an object.

    Discord: https://docs.discord.com/developers/resources/guild#guild-onboarding-object-prompt-option-structure
    """

    id: Snowflake
    channel_ids: list[Snowflake]
    role_ids: list[Snowflake]
    emoji_id: Snowflake | UnsetType = UNSET
    emoji_name: str | UnsetType = UNSET
    emoji_animated: bool | UnsetType = UNSET
    title: str
    description: str | None


class OnboardingPromptParams(Payload):
    """An onboarding question in a request.

    Discord: https://docs.discord.com/developers/resources/guild#guild-onboarding-object-onboarding-prompt-structure
    """

    id: Snowflake
    type: PromptType
    options: list[PromptOptionParams]
    title: str
    single_select: bool
    required: bool
    in_onboarding: bool


class EditOnboardingParams(Payload):
    """JSON body of Modify Guild Onboarding. Needs Manage Guild and Manage Roles.

    When enabled, onboarding needs at least 7 default channels, 5 of which @everyone can send in.

    Discord: https://docs.discord.com/developers/resources/guild#modify-guild-onboarding-json-params
    """

    prompts: list[OnboardingPromptParams] | UnsetType = UNSET
    default_channel_ids: list[Snowflake] | UnsetType = UNSET
    enabled: bool | UnsetType = UNSET
    mode: OnboardingMode | UnsetType = UNSET


class EditIncidentActionsParams(Payload):
    """JSON body of Modify Guild Incident Actions. Each pause can last up to 24 hours; `None` ends it.

    Discord: https://docs.discord.com/developers/resources/guild#modify-guild-incident-actions-json-params
    """

    invites_disabled_until: datetime | UnsetType | None = UNSET
    dms_disabled_until: datetime | UnsetType | None = UNSET
