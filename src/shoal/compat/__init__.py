"""Familiar names for bots moving to Shoal: `import shoal.compat as discord`.

    import shoal.compat as discord
    from shoal.compat import app_commands, commands

    try:
        await member.send("hi")
    except discord.Forbidden: ...

The models, payloads and helpers bots name most, under the names they are used to: the same
objects as in Shoal (`discord.Member` is `shoal.Member`, `discord.Forbidden` is `ForbiddenError`,
`discord.Status` is `StatusType`). `commands`, `app_commands`, `tasks`, `ui` and `utils` are here too. New
code reads better with Shoal's own names.

A name is here only when Shoal's object is the same Discord object. The `Raw*Event` names are
Shoal's gateway event payloads, so their fields carry Discord's names (`MessageDelete.id`, not
`message_id`); `FFmpegPCMAudio` is `FFmpegSource`, whose options are lists of arguments.
"""

import importlib
from typing import TYPE_CHECKING, Final

from shoal import tasks, ui
from shoal.app_commands.errors import (
    MissingApplicationIDError as MissingApplicationID,
)

if TYPE_CHECKING:
    from shoal.voice import AudioSource
    from shoal.voice import FFmpegSource as FFmpegPCMAudio

from shoal.client import (
    Client,
    Interaction,
    InteractionResponse,
)
from shoal.client import (
    Client as AutoShardedClient,
)
from shoal.client import (
    ClientError as ClientException,
)
from shoal.client import (
    InteractionRespondedError as InteractionResponded,
)
from shoal.compat import app_commands, commands, utils
from shoal.compat.utils import (
    MISSING,
    as_chunks,
    escape_markdown,
    escape_mentions,
    find,
    format_dt,
    get,
    maybe_coroutine,
    oauth_url,
    remove_markdown,
    snowflake_time,
    time_snowflake,
    utcnow,
)
from shoal.core.codec import (
    PayloadDecodeError as InvalidData,
)
from shoal.core.errors import (
    ShoalError as DiscordException,
)
from shoal.core.snowflake import (
    Snowflake,
)
from shoal.gateway import (
    GatewayFatalError as ConnectionClosed,
)
from shoal.gateway import (
    PrivilegedIntentsRequiredError as PrivilegedIntentsRequired,
)
from shoal.models.activity import (
    CustomActivity,
    Game,
    Streaming,
)
from shoal.models.asset import (
    Asset,
)
from shoal.models.base import (
    Hashable,
    Object,
)
from shoal.models.channel import (
    CategoryChannel,
    DMChannel,
    ForumChannel,
    GroupChannel,
    GuildChannel,
    PartialMessageable,
    StageChannel,
    TextChannel,
    VoiceChannel,
)
from shoal.models.colour import Color, Colour
from shoal.models.embed import (
    Embed,
)
from shoal.models.emoji import (
    Emoji,
)
from shoal.models.guild import (
    Guild,
)
from shoal.models.member import (
    Member,
)
from shoal.models.message import (
    Message,
    PartialMessage,
    Reaction,
)
from shoal.models.messageable import (
    Messageable,
    Typing,
)
from shoal.models.role import (
    Role,
)
from shoal.models.thread import (
    Thread,
)
from shoal.models.user import (
    ClientUser,
    User,
)
from shoal.models.voice import (
    VoiceClient,
)
from shoal.payloads import (
    SKU,
    ActionRow,
    Activity,
    ActivityType,
    AllowedMentions,
    ApplicationFlags,
    Attachment,
    AttachmentFlags,
    AuditLogEntry,
    Button,
    ButtonStyle,
    ChannelFlags,
    ChannelType,
    CheckboxGroupOption,
    ClientStatus,
    Component,
    ComponentType,
    Container,
    EmbedFlags,
    Entitlement,
    EntitlementOwnerType,
    EntitlementType,
    FileComponent,
    ForumLayoutType,
    ForumTag,
    GuildPreview,
    Integration,
    IntegrationAccount,
    IntegrationApplication,
    Intents,
    InteractionCallbackResponse,
    InteractionMessage,
    InteractionType,
    Invite,
    InviteType,
    Locale,
    MediaGalleryItem,
    MessageFlags,
    MessageInteraction,
    MessageInteractionMetadata,
    MessageReference,
    MessageReferenceType,
    MessageSnapshot,
    MessageType,
    MFALevel,
    OnboardingMode,
    OnboardingPrompt,
    PartialEmoji,
    Permissions,
    Poll,
    PollAnswer,
    PollLayoutType,
    PollMedia,
    RadioGroupOption,
    ReactionType,
    RoleFlags,
    RoleTags,
    SelectDefaultValue,
    SelectDefaultValueType,
    SelectOption,
    SeparatorSpacing,
    SKUFlags,
    SKUType,
    SoundboardSound,
    StageInstance,
    StatusDisplayType,
    Sticker,
    StickerFormatType,
    StickerItem,
    StickerPack,
    StickerType,
    Subscription,
    SubscriptionStatus,
    SystemChannelFlags,
    Team,
    TeamMember,
    TeamMemberRole,
    TextDisplay,
    TextInput,
    ThreadMember,
    UnfurledMediaItem,
    UserFlags,
    VerificationLevel,
    VideoQualityMode,
    VoiceChannelEffectAnimationType,
    VoiceState,
    WebhookType,
    WelcomeScreen,
    WidgetChannel,
    WidgetMember,
)
from shoal.payloads import (
    Application as AppInfo,
)
from shoal.payloads import (
    ApplicationCommandOptionType as AppCommandOptionType,
)
from shoal.payloads import (
    ApplicationCommandPermissionType as AppCommandPermissionType,
)
from shoal.payloads import (
    ApplicationCommandType as AppCommandType,
)
from shoal.payloads import (
    ApplicationIntegrationTypeConfiguration as IntegrationTypeConfig,
)
from shoal.payloads import (
    AuditLogEvent as AuditLogAction,
)
from shoal.payloads import (
    AutoModerationAction as AutoModRuleAction,
)
from shoal.payloads import (
    AutoModerationActionExecution as AutoModAction,
)
from shoal.payloads import (
    AutoModerationActionType as AutoModRuleActionType,
)
from shoal.payloads import (
    AutoModerationEventType as AutoModRuleEventType,
)
from shoal.payloads import (
    AutoModerationRule as AutoModRule,
)
from shoal.payloads import (
    AutoModerationTriggerMetadata as AutoModTrigger,
)
from shoal.payloads import (
    AutoModerationTriggerType as AutoModRuleTriggerType,
)
from shoal.payloads import (
    Ban as BanEntry,
)
from shoal.payloads import (
    Checkbox as CheckboxComponent,
)
from shoal.payloads import (
    CheckboxGroup as CheckboxGroupComponent,
)
from shoal.payloads import (
    DefaultMessageNotificationLevel as NotificationLevel,
)
from shoal.payloads import (
    ExplicitContentFilterLevel as ContentFilter,
)
from shoal.payloads import (
    FileUpload as FileUploadComponent,
)
from shoal.payloads import (
    GuildApplicationCommandPermissions as RawAppCommandPermissionsUpdateEvent,
)
from shoal.payloads import (
    GuildInviteFlags as InviteFlags,
)
from shoal.payloads import (
    GuildMemberFlags as MemberFlags,
)
from shoal.payloads import (
    GuildMemberRemove as RawMemberRemoveEvent,
)
from shoal.payloads import (
    GuildNSFWLevel as NSFWLevel,
)
from shoal.payloads import (
    GuildOnboarding as Onboarding,
)
from shoal.payloads import (
    GuildScheduledEvent as ScheduledEvent,
)
from shoal.payloads import (
    GuildTemplate as Template,
)
from shoal.payloads import (
    GuildWidget as Widget,
)
from shoal.payloads import (
    InstallParams as AppInstallParams,
)
from shoal.payloads import (
    IntegrationDelete as RawIntegrationDeleteEvent,
)
from shoal.payloads import (
    IntegrationExpireBehavior as ExpireBehavior,
)
from shoal.payloads import (
    IntegrationExpireBehavior as ExpireBehaviour,
)
from shoal.payloads import (
    InteractionCallbackType as InteractionResponseType,
)
from shoal.payloads import (
    InviteGuild as PartialInviteGuild,
)
from shoal.payloads import (
    InviteTargetType as InviteTarget,
)
from shoal.payloads import (
    Label as LabelComponent,
)
from shoal.payloads import (
    MediaGallery as MediaGalleryComponent,
)
from shoal.payloads import (
    MembershipState as TeamMembershipState,
)
from shoal.payloads import (
    MessageCall as CallMessage,
)
from shoal.payloads import (
    MessageDelete as RawMessageDeleteEvent,
)
from shoal.payloads import (
    MessageDeleteBulk as RawBulkMessageDeleteEvent,
)
from shoal.payloads import (
    MessagePollVoteAdd as RawPollVoteActionEvent,
)
from shoal.payloads import (
    MessageReactionRemoveAll as RawReactionClearEvent,
)
from shoal.payloads import (
    MessageReactionRemoveEmoji as RawReactionClearEmojiEvent,
)
from shoal.payloads import (
    MessageUpdate as RawMessageUpdateEvent,
)
from shoal.payloads import (
    PartialApplication as PartialAppInfo,
)
from shoal.payloads import (
    PresenceUpdate as RawPresenceUpdateEvent,
)
from shoal.payloads import (
    PromptOption as OnboardingPromptOption,
)
from shoal.payloads import (
    PromptType as OnboardingPromptType,
)
from shoal.payloads import (
    RadioGroup as RadioGroupComponent,
)
from shoal.payloads import (
    RoleSubscriptionData as RoleSubscriptionInfo,
)
from shoal.payloads import (
    ScheduledEventEntityType as EntityType,
)
from shoal.payloads import (
    ScheduledEventPrivacyLevel as PrivacyLevel,
)
from shoal.payloads import (
    ScheduledEventStatus as EventStatus,
)
from shoal.payloads import (
    Section as SectionComponent,
)
from shoal.payloads import (
    Separator as SeparatorComponent,
)
from shoal.payloads import (
    SessionStartLimit as SessionStartLimits,
)
from shoal.payloads import (
    SortOrderType as ForumOrderType,
)
from shoal.payloads import (
    SoundboardSound as BaseSoundboardSound,
)
from shoal.payloads import (
    SoundboardSound as SoundboardDefaultSound,
)
from shoal.payloads import (
    SpeakingFlags as SpeakingState,
)
from shoal.payloads import (
    StatusType as Status,
)
from shoal.payloads import (
    Sticker as GuildSticker,
)
from shoal.payloads import (
    TextInputStyle as TextStyle,
)
from shoal.payloads import (
    ThreadMembersUpdate as RawThreadMembersUpdate,
)
from shoal.payloads import (
    Thumbnail as ThumbnailComponent,
)
from shoal.payloads import (
    TypingStart as RawTypingEvent,
)
from shoal.payloads import (
    UserFlags as PublicUserFlags,
)
from shoal.payloads import (
    UserPrimaryGuild as PrimaryGuild,
)
from shoal.payloads import (
    VoiceChannelEffectSend as VoiceChannelEffect,
)
from shoal.payloads import (
    WebhookSourceChannel as PartialWebhookChannel,
)
from shoal.payloads import (
    WebhookSourceGuild as PartialWebhookGuild,
)
from shoal.payloads import (
    WelcomeScreenChannel as WelcomeChannel,
)
from shoal.rest.errors import (
    ForbiddenError as Forbidden,
)
from shoal.rest.errors import (
    HTTPError as HTTPException,
)
from shoal.rest.errors import (
    NotFoundError as NotFound,
)
from shoal.rest.errors import (
    RateLimitedError as RateLimited,
)
from shoal.rest.errors import (
    ServerError as DiscordServerError,
)
from shoal.rest.errors import (
    UnauthorizedError as LoginFailure,
)
from shoal.rest.files import (
    File,
)

__all__ = [
    "MISSING",
    "SKU",
    "ActionRow",
    "Activity",
    "ActivityType",
    "AllowedMentions",
    "AppCommandOptionType",
    "AppCommandPermissionType",
    "AppCommandType",
    "AppInfo",
    "AppInstallParams",
    "ApplicationFlags",
    "Asset",
    "Attachment",
    "AttachmentFlags",
    "AudioSource",
    "AuditLogAction",
    "AuditLogEntry",
    "AutoModAction",
    "AutoModRule",
    "AutoModRuleAction",
    "AutoModRuleActionType",
    "AutoModRuleEventType",
    "AutoModRuleTriggerType",
    "AutoModTrigger",
    "AutoShardedClient",
    "BanEntry",
    "BaseSoundboardSound",
    "Button",
    "ButtonStyle",
    "CallMessage",
    "CategoryChannel",
    "ChannelFlags",
    "ChannelType",
    "CheckboxComponent",
    "CheckboxGroupComponent",
    "CheckboxGroupOption",
    "Client",
    "ClientException",
    "ClientStatus",
    "ClientUser",
    "Color",
    "Colour",
    "Component",
    "ComponentType",
    "ConnectionClosed",
    "Container",
    "ContentFilter",
    "CustomActivity",
    "DMChannel",
    "DiscordException",
    "DiscordServerError",
    "Embed",
    "EmbedFlags",
    "Emoji",
    "Entitlement",
    "EntitlementOwnerType",
    "EntitlementType",
    "EntityType",
    "EventStatus",
    "ExpireBehavior",
    "ExpireBehaviour",
    "FFmpegPCMAudio",
    "File",
    "FileComponent",
    "FileUploadComponent",
    "Forbidden",
    "ForumChannel",
    "ForumLayoutType",
    "ForumOrderType",
    "ForumTag",
    "Game",
    "GroupChannel",
    "Guild",
    "GuildChannel",
    "GuildPreview",
    "GuildSticker",
    "HTTPException",
    "Hashable",
    "Integration",
    "IntegrationAccount",
    "IntegrationApplication",
    "IntegrationTypeConfig",
    "Intents",
    "Interaction",
    "InteractionCallbackResponse",
    "InteractionMessage",
    "InteractionResponded",
    "InteractionResponse",
    "InteractionResponseType",
    "InteractionType",
    "InvalidData",
    "Invite",
    "InviteFlags",
    "InviteTarget",
    "InviteType",
    "LabelComponent",
    "Locale",
    "LoginFailure",
    "MFALevel",
    "MediaGalleryComponent",
    "MediaGalleryItem",
    "Member",
    "MemberFlags",
    "Message",
    "MessageFlags",
    "MessageInteraction",
    "MessageInteractionMetadata",
    "MessageReference",
    "MessageReferenceType",
    "MessageSnapshot",
    "MessageType",
    "Messageable",
    "MissingApplicationID",
    "NSFWLevel",
    "NotFound",
    "NotificationLevel",
    "Object",
    "Onboarding",
    "OnboardingMode",
    "OnboardingPrompt",
    "OnboardingPromptOption",
    "OnboardingPromptType",
    "PartialAppInfo",
    "PartialEmoji",
    "PartialInviteGuild",
    "PartialMessage",
    "PartialMessageable",
    "PartialWebhookChannel",
    "PartialWebhookGuild",
    "Permissions",
    "Poll",
    "PollAnswer",
    "PollLayoutType",
    "PollMedia",
    "PrimaryGuild",
    "PrivacyLevel",
    "PrivilegedIntentsRequired",
    "PublicUserFlags",
    "RadioGroupComponent",
    "RadioGroupOption",
    "RateLimited",
    "RawAppCommandPermissionsUpdateEvent",
    "RawBulkMessageDeleteEvent",
    "RawIntegrationDeleteEvent",
    "RawMemberRemoveEvent",
    "RawMessageDeleteEvent",
    "RawMessageUpdateEvent",
    "RawPollVoteActionEvent",
    "RawPresenceUpdateEvent",
    "RawReactionClearEmojiEvent",
    "RawReactionClearEvent",
    "RawThreadMembersUpdate",
    "RawTypingEvent",
    "Reaction",
    "ReactionType",
    "Role",
    "RoleFlags",
    "RoleSubscriptionInfo",
    "RoleTags",
    "SKUFlags",
    "SKUType",
    "ScheduledEvent",
    "SectionComponent",
    "SelectDefaultValue",
    "SelectDefaultValueType",
    "SelectOption",
    "SeparatorComponent",
    "SeparatorSpacing",
    "SessionStartLimits",
    "Snowflake",
    "SoundboardDefaultSound",
    "SoundboardSound",
    "SpeakingState",
    "StageChannel",
    "StageInstance",
    "Status",
    "StatusDisplayType",
    "Sticker",
    "StickerFormatType",
    "StickerItem",
    "StickerPack",
    "StickerType",
    "Streaming",
    "Subscription",
    "SubscriptionStatus",
    "SystemChannelFlags",
    "Team",
    "TeamMember",
    "TeamMemberRole",
    "TeamMembershipState",
    "Template",
    "TextChannel",
    "TextDisplay",
    "TextInput",
    "TextStyle",
    "Thread",
    "ThreadMember",
    "ThumbnailComponent",
    "Typing",
    "UnfurledMediaItem",
    "User",
    "UserFlags",
    "VerificationLevel",
    "VideoQualityMode",
    "VoiceChannel",
    "VoiceChannelEffect",
    "VoiceChannelEffectAnimationType",
    "VoiceClient",
    "VoiceState",
    "WebhookType",
    "WelcomeChannel",
    "WelcomeScreen",
    "Widget",
    "WidgetChannel",
    "WidgetMember",
    "app_commands",
    "as_chunks",
    "commands",
    "escape_markdown",
    "escape_mentions",
    "find",
    "format_dt",
    "get",
    "maybe_coroutine",
    "oauth_url",
    "remove_markdown",
    "snowflake_time",
    "tasks",
    "time_snowflake",
    "ui",
    "utcnow",
    "utils",
]


# Voice loads its optional dependencies (davey, cryptography) when imported, so its names load on
# first use: `import shoal.compat as discord` stays as light as before.
_VOICE: Final[dict[str, str]] = {
    "AudioSource": "AudioSource",
    "FFmpegPCMAudio": "FFmpegSource",
}


def __getattr__(name: str) -> object:
    """Load a voice name on first use (PEP 562)."""
    source = _VOICE.get(name)
    if source is None:
        msg = f"module 'shoal.compat' has no attribute {name!r}"
        raise AttributeError(msg)
    value: object = getattr(importlib.import_module("shoal.voice"), source)
    globals()[name] = value
    return value
