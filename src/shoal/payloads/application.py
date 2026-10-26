"""Applications: where an app can be installed, and where and how its interactions happen.

Discord: https://docs.discord.com/developers/resources/application

Not yet modeled: `Application.guild` (a partial guild). Decoding ignores it until it is added.
"""

from datetime import datetime

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.api import ImageData, Localizations
from shoal.payloads.base import Payload
from shoal.payloads.permissions import Permissions
from shoal.payloads.user import User


class ApplicationIntegrationType(DiscordIntEnum):
    """Where an app is installed: to a server, or to a user's account.

    Discord: https://docs.discord.com/developers/resources/application#application-object-application-integration-types
    """

    GUILD_INSTALL = 0
    USER_INSTALL = 1


class InteractionContextType(DiscordIntEnum):
    """Where an interaction can be used, or where it happened.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-interaction-context-types
    """

    GUILD = 0
    BOT_DM = 1
    PRIVATE_CHANNEL = 2


class InteractionType(DiscordIntEnum):
    """What the user did.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-interaction-type
    """

    PING = 1
    """Discord checking an HTTP interactions endpoint; answer with `PongResponse`."""
    APPLICATION_COMMAND = 2
    MESSAGE_COMPONENT = 3
    APPLICATION_COMMAND_AUTOCOMPLETE = 4
    MODAL_SUBMIT = 5


class ApplicationFlags(BaseFlags):
    """Public flags of an app.

    Discord: https://docs.discord.com/developers/resources/application#application-object-application-flags
    """

    __slots__ = ()

    application_auto_moderation_rule_create_badge = flag(6)
    gateway_presence = flag(12)
    """The Presence intent, for apps in 100 or more guilds."""
    gateway_presence_limited = flag(13)
    gateway_guild_members = flag(14)
    """The Guild Members intent, for apps in 100 or more guilds."""
    gateway_guild_members_limited = flag(15)
    verification_pending_guild_limit = flag(16)
    embedded = flag(17)
    gateway_message_content = flag(18)
    """The Message Content intent, for apps in 100 or more guilds."""
    gateway_message_content_limited = flag(19)
    application_command_badge = flag(23)


class ApplicationEventWebhookStatus(DiscordIntEnum):
    """Whether an app receives webhook events.

    Discord: https://docs.discord.com/developers/resources/application#application-object-application-event-webhook-status
    """

    DISABLED = 1
    ENABLED = 2
    DISABLED_BY_DISCORD = 3
    """Usually after a period of inactivity."""


class InstallParams(Payload):
    """The scopes and bot permissions of an app's in-app authorization link.

    Discord: https://docs.discord.com/developers/resources/application#install-params-object
    """

    scopes: list[str]
    """OAuth2 scopes."""
    permissions: Permissions


class ApplicationIntegrationTypeConfiguration(Payload):
    """The default install settings for one installation context.

    Discord: https://docs.discord.com/developers/resources/application#application-object-application-integration-type-configuration-object
    """

    oauth2_install_params: InstallParams | UnsetType = UNSET


class MembershipState(DiscordIntEnum):
    """Whether a team member has accepted their invitation.

    Discord: https://docs.discord.com/developers/topics/teams#data-models-membership-state-enum
    """

    INVITED = 1
    ACCEPTED = 2


class TeamMemberRole(DiscordStrEnum):
    """A team member's role. The owner has no role here: see `Team.owner_user_id`.

    Discord: https://docs.discord.com/developers/topics/teams#team-member-roles-team-member-role-types
    """

    ADMIN = "admin"
    DEVELOPER = "developer"
    READ_ONLY = "read_only"


class TeamMember(Payload):
    """A member of a developer team.

    Discord: https://docs.discord.com/developers/topics/teams#data-models-team-member-object
    """

    membership_state: MembershipState
    team_id: Snowflake
    user: User
    role: TeamMemberRole


class Team(Payload):
    """A developer team that owns apps.

    Discord: https://docs.discord.com/developers/topics/teams#data-models-team-object
    """

    icon: str | None
    id: Snowflake
    members: list[TeamMember]
    name: str
    owner_user_id: Snowflake


class Application(Payload):
    """A Discord app.

    Discord: https://docs.discord.com/developers/resources/application#application-object
    """

    id: Snowflake
    name: str
    icon: str | None
    description: str
    rpc_origins: list[str] | UnsetType = UNSET
    bot_public: bool
    """When `False`, only the owner can add the app to guilds."""
    bot_require_code_grant: bool
    bot: User | UnsetType = UNSET
    """A partial user."""
    terms_of_service_url: str | UnsetType = UNSET
    privacy_policy_url: str | UnsetType = UNSET
    owner: User | UnsetType = UNSET
    """A partial user."""
    verify_key: str
    """The hex public key that signs HTTP interactions."""
    team: Team | None
    guild_id: Snowflake | UnsetType = UNSET
    primary_sku_id: Snowflake | UnsetType = UNSET
    slug: str | UnsetType = UNSET
    cover_image: str | UnsetType = UNSET
    flags: ApplicationFlags | UnsetType = UNSET
    """Legacy flags, which stop at 31 bits; `flags_new` has them all."""
    flags_new: str | UnsetType = UNSET
    """Every flag bit, as a string; `ApplicationFlags(int(flags_new))` reads it."""
    approximate_guild_count: int | UnsetType = UNSET
    approximate_user_install_count: int | UnsetType = UNSET
    approximate_user_authorization_count: int | UnsetType = UNSET
    redirect_uris: list[str] | UnsetType = UNSET
    interactions_endpoint_url: str | UnsetType | None = UNSET
    role_connections_verification_url: str | UnsetType | None = UNSET
    event_webhooks_url: str | UnsetType | None = UNSET
    event_webhooks_status: ApplicationEventWebhookStatus | UnsetType = UNSET
    event_webhooks_types: list[str] | UnsetType = UNSET
    tags: list[str] | UnsetType = UNSET
    """Up to 5."""
    install_params: InstallParams | UnsetType = UNSET
    integration_types_config: (
        dict[ApplicationIntegrationType, ApplicationIntegrationTypeConfiguration] | UnsetType
    ) = UNSET
    custom_install_url: str | UnsetType = UNSET


class PartialApplication(Payload):
    """The app in Get Current Authorization Information: a partial application.

    Discord does not list which fields it carries; these follow the documented example.

    Discord: https://docs.discord.com/developers/topics/oauth2#get-current-authorization-information-example-authorization-information
    """

    id: Snowflake
    name: str
    icon: str | UnsetType | None = UNSET
    description: str | UnsetType = UNSET
    bot_public: bool | UnsetType = UNSET
    bot_require_code_grant: bool | UnsetType = UNSET
    verify_key: str | UnsetType = UNSET


class AuthorizationInformation(Payload):
    """What a bearer token was authorized for.

    Discord: https://docs.discord.com/developers/topics/oauth2#get-current-authorization-information-response-structure
    """

    application: PartialApplication
    scopes: list[str]
    expires: datetime
    """When the access token expires."""
    user: User | UnsetType = UNSET
    """Only with the `identify` scope."""


class EditCurrentApplicationParams(Payload):
    """JSON body of Edit Current Application.

    Discord: https://docs.discord.com/developers/resources/application#edit-current-application-json-params
    """

    custom_install_url: str | UnsetType = UNSET
    description: str | UnsetType = UNSET
    role_connections_verification_url: str | UnsetType = UNSET
    install_params: InstallParams | UnsetType = UNSET
    integration_types_config: (
        dict[ApplicationIntegrationType, ApplicationIntegrationTypeConfiguration] | UnsetType
    ) = UNSET
    flags: ApplicationFlags | UnsetType = UNSET
    """Only the three `_limited` intent flags can be changed."""
    icon: ImageData | UnsetType | None = UNSET
    cover_image: ImageData | UnsetType | None = UNSET
    interactions_endpoint_url: str | UnsetType = UNSET
    """Discord checks the URL answers its signed PING first."""
    tags: list[str] | UnsetType = UNSET
    """Up to 5, each up to 20 characters."""
    event_webhooks_url: str | UnsetType = UNSET
    event_webhooks_status: ApplicationEventWebhookStatus | UnsetType = UNSET
    """`DISABLED` or `ENABLED`."""
    event_webhooks_types: list[str] | UnsetType = UNSET


class ActivityLocationKind(DiscordStrEnum):
    """Where an Activity instance runs.

    Discord: https://docs.discord.com/developers/resources/application#get-application-activity-instance-activity-location-kind-enum
    """

    GUILD_CHANNEL = "gc"
    PRIVATE_CHANNEL = "pc"
    """A DM or group DM."""


class ActivityLocation(Payload):
    """The channel an Activity instance runs in.

    Discord: https://docs.discord.com/developers/resources/application#get-application-activity-instance-activity-location-object
    """

    id: str
    kind: ActivityLocationKind
    channel_id: Snowflake
    guild_id: Snowflake | UnsetType | None = UNSET


class ActivityInstance(Payload):
    """A running Activity and who is in it.

    Discord: https://docs.discord.com/developers/resources/application#get-application-activity-instance-activity-instance-object
    """

    application_id: Snowflake
    instance_id: str
    launch_id: Snowflake
    location: ActivityLocation
    users: list[Snowflake]


class ApplicationRoleConnectionMetadataType(DiscordIntEnum):
    """How a guild's linked-role requirement compares with a user's metadata value.

    Discord: https://docs.discord.com/developers/resources/application-role-connection-metadata#application-role-connection-metadata-object-application-role-connection-metadata-type
    """

    INTEGER_LESS_THAN_OR_EQUAL = 1
    INTEGER_GREATER_THAN_OR_EQUAL = 2
    INTEGER_EQUAL = 3
    INTEGER_NOT_EQUAL = 4
    DATETIME_LESS_THAN_OR_EQUAL = 5
    """The user's value is an ISO 8601 date; the guild's is a number of days before today."""
    DATETIME_GREATER_THAN_OR_EQUAL = 6
    """The user's value is an ISO 8601 date; the guild's is a number of days before today."""
    BOOLEAN_EQUAL = 7
    BOOLEAN_NOT_EQUAL = 8


class ApplicationRoleConnectionMetadata(Payload):
    """A value an app records for each user, which linked roles can require. An app can have 5.

    Discord: https://docs.discord.com/developers/resources/application-role-connection-metadata#application-role-connection-metadata-object
    """

    type: ApplicationRoleConnectionMetadataType
    key: str
    """1 to 50 characters of `a-z`, `0-9` and `_`."""
    name: str
    """1 to 100 characters."""
    name_localizations: Localizations | UnsetType = UNSET
    description: str
    """1 to 200 characters."""
    description_localizations: Localizations | UnsetType = UNSET
