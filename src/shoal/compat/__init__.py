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
"""

import importlib
from typing import TYPE_CHECKING, Final

from shoal import tasks, ui
from shoal.app_commands.errors import (
    MissingApplicationIDError as MissingApplicationID,
)

if TYPE_CHECKING:
    from shoal.voice import AudioSource

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
    ApplicationCommandType as AppCommandType,
)
from shoal.payloads import (
    AuditLogEvent as AuditLogAction,
)
from shoal.payloads import (
    AutoModerationRule as AutoModRule,
)
from shoal.payloads import (
    Ban as BanEntry,
)
from shoal.payloads import (
    DefaultMessageNotificationLevel as NotificationLevel,
)
from shoal.payloads import (
    ExplicitContentFilterLevel as ContentFilter,
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
    InviteTargetType as InviteTarget,
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
    StatusType as Status,
)
from shoal.payloads import (
    Sticker as GuildSticker,
)
from shoal.payloads import (
    TextInputStyle as TextStyle,
)
from shoal.payloads import (
    UserPrimaryGuild as PrimaryGuild,
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
    "AppCommandType",
    "AppInfo",
    "ApplicationFlags",
    "Asset",
    "Attachment",
    "AttachmentFlags",
    "AudioSource",
    "AuditLogAction",
    "AuditLogEntry",
    "AutoModRule",
    "AutoShardedClient",
    "BanEntry",
    "Button",
    "ButtonStyle",
    "CategoryChannel",
    "ChannelFlags",
    "ChannelType",
    "CheckboxGroupOption",
    "Client",
    "ClientException",
    "ClientStatus",
    "ClientUser",
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
    "File",
    "FileComponent",
    "Forbidden",
    "ForumChannel",
    "ForumLayoutType",
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
    "Intents",
    "Interaction",
    "InteractionCallbackResponse",
    "InteractionMessage",
    "InteractionResponded",
    "InteractionResponse",
    "InteractionType",
    "InvalidData",
    "Invite",
    "InviteTarget",
    "InviteType",
    "Locale",
    "LoginFailure",
    "MFALevel",
    "MediaGalleryItem",
    "Member",
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
    "PartialEmoji",
    "PartialMessage",
    "PartialMessageable",
    "Permissions",
    "Poll",
    "PollAnswer",
    "PollLayoutType",
    "PollMedia",
    "PrimaryGuild",
    "PrivacyLevel",
    "PrivilegedIntentsRequired",
    "RadioGroupOption",
    "RateLimited",
    "Reaction",
    "ReactionType",
    "Role",
    "RoleFlags",
    "RoleTags",
    "SKUFlags",
    "SKUType",
    "ScheduledEvent",
    "SelectDefaultValue",
    "SelectDefaultValueType",
    "SelectOption",
    "SeparatorSpacing",
    "Snowflake",
    "SoundboardSound",
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
    "Template",
    "TextChannel",
    "TextDisplay",
    "TextInput",
    "TextStyle",
    "Thread",
    "ThreadMember",
    "Typing",
    "UnfurledMediaItem",
    "User",
    "UserFlags",
    "VerificationLevel",
    "VideoQualityMode",
    "VoiceChannel",
    "VoiceChannelEffectAnimationType",
    "VoiceClient",
    "VoiceState",
    "WebhookType",
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
