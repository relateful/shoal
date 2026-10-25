"""Application commands: slash, user, message and entry point commands, and their permissions.

Discord: https://docs.discord.com/developers/interactions/application-commands
"""

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.snowflake import Snowflake
from shoal.payloads.api import Localizations
from shoal.payloads.application import ApplicationIntegrationType
from shoal.payloads.base import Payload
from shoal.payloads.channel import ChannelType
from shoal.payloads.interactions import InteractionContextType
from shoal.payloads.permissions import Permissions


class ApplicationCommandType(DiscordIntEnum):
    """How a command is invoked.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-application-command-types
    """

    CHAT_INPUT = 1
    """A slash command, typed after `/`."""
    USER = 2
    """Shown when right-clicking or tapping a user."""
    MESSAGE = 3
    """Shown when right-clicking or tapping a message."""
    PRIMARY_ENTRY_POINT = 4
    """The primary way to launch an app's Activity."""


class ApplicationCommandOptionType(DiscordIntEnum):
    """What a command option holds.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-application-command-option-type
    """

    SUB_COMMAND = 1
    SUB_COMMAND_GROUP = 2
    STRING = 3
    INTEGER = 4
    """Any integer between -2^53+1 and 2^53-1."""
    BOOLEAN = 5
    USER = 6
    CHANNEL = 7
    """Any channel type, including categories."""
    ROLE = 8
    MENTIONABLE = 9
    """A user or a role."""
    NUMBER = 10
    """Any double between -2^53 and 2^53."""
    ATTACHMENT = 11


class EntryPointCommandHandlerType(DiscordIntEnum):
    """Who handles a `PRIMARY_ENTRY_POINT` command.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-entry-point-command-handler-types
    """

    APP_HANDLER = 1
    """The app handles the interaction with its interaction token."""
    DISCORD_LAUNCH_ACTIVITY = 2
    """Discord launches the Activity and sends a follow-up message itself."""


class ApplicationCommandPermissionType(DiscordIntEnum):
    """What an application command permission targets.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-permissions-object-application-command-permission-type
    """

    ROLE = 1
    USER = 2
    CHANNEL = 3


class ApplicationCommandOptionChoice(Payload):
    """One fixed value a user can pick for a `STRING`, `INTEGER` or `NUMBER` option.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-application-command-option-choice-structure
    """

    name: str
    name_localizations: Localizations | UnsetType | None = UNSET
    value: str | int | float
    """Up to 100 characters for a string; the type matches the option's."""
    name_localized: str | UnsetType = UNSET
    """The name in the requester's locale, when a list endpoint returned it instead of the
    dictionaries (https://docs.discord.com/developers/interactions/application-commands#retrieving-localized-commands)."""


class ApplicationCommandOption(Payload):
    """A parameter of a command, or a subcommand or subcommand group.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-application-command-option-structure
    """

    type: ApplicationCommandOptionType
    name: str
    name_localizations: Localizations | UnsetType | None = UNSET
    description: str
    description_localizations: Localizations | UnsetType | None = UNSET
    required: bool | UnsetType = UNSET
    """Defaults to `False`. Required options must come before optional ones."""
    choices: list[ApplicationCommandOptionChoice] | UnsetType = UNSET
    options: "list[ApplicationCommandOption] | UnsetType" = UNSET
    """The parameters of a subcommand, or the subcommands of a group."""
    channel_types: list[ChannelType] | UnsetType = UNSET
    min_value: int | float | UnsetType = UNSET
    max_value: int | float | UnsetType = UNSET
    min_length: int | UnsetType = UNSET
    max_length: int | UnsetType = UNSET
    autocomplete: bool | UnsetType = UNSET
    """Cannot be combined with `choices`."""
    file_types: list[str] | UnsetType = UNSET
    """For `ATTACHMENT` options: `image`, `video`, `audio`, or dot-prefixed extensions; at most 10."""
    name_localized: str | UnsetType = UNSET
    """See `ApplicationCommandOptionChoice.name_localized`."""
    description_localized: str | UnsetType = UNSET
    """See `ApplicationCommandOptionChoice.name_localized`."""


class ApplicationCommand(Payload):
    """A registered command.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-application-command-structure
    """

    id: Snowflake
    type: ApplicationCommandType | UnsetType = UNSET
    """Defaults to `CHAT_INPUT`."""
    application_id: Snowflake
    guild_id: Snowflake | UnsetType = UNSET
    """Set for guild commands; absent for global ones."""
    name: str
    name_localizations: Localizations | UnsetType | None = UNSET
    description: str
    """Empty for `USER` and `MESSAGE` commands."""
    description_localizations: Localizations | UnsetType | None = UNSET
    options: list[ApplicationCommandOption] | UnsetType = UNSET
    default_member_permissions: Permissions | None
    """Permissions a member needs to see the command, until a server admin overrides them."""
    dm_permission: bool | UnsetType = UNSET
    """Deprecated; use `contexts`."""
    default_permission: bool | UnsetType | None = UNSET
    """Deprecated; use `default_member_permissions`."""
    nsfw: bool | UnsetType = UNSET
    integration_types: list[ApplicationIntegrationType] | UnsetType = UNSET
    contexts: list[InteractionContextType] | UnsetType | None = UNSET
    version: Snowflake
    """Changes whenever the command changes substantially."""
    handler: EntryPointCommandHandlerType | UnsetType = UNSET
    name_localized: str | UnsetType = UNSET
    """See `ApplicationCommandOptionChoice.name_localized`."""
    description_localized: str | UnsetType = UNSET
    """See `ApplicationCommandOptionChoice.name_localized`."""


class CreateGlobalApplicationCommandParams(Payload):
    """JSON body of Create Global Application Command. A command with the same name is replaced.

    Discord: https://docs.discord.com/developers/interactions/application-commands#create-global-application-command-json-params
    """

    name: str
    name_localizations: Localizations | UnsetType | None = UNSET
    description: str | UnsetType = UNSET
    """Required for `CHAT_INPUT` and `PRIMARY_ENTRY_POINT` commands."""
    description_localizations: Localizations | UnsetType | None = UNSET
    options: list[ApplicationCommandOption] | UnsetType = UNSET
    default_member_permissions: Permissions | UnsetType | None = UNSET
    dm_permission: bool | UnsetType | None = UNSET
    """Deprecated; use `contexts`."""
    default_permission: bool | UnsetType = UNSET
    """Deprecated; use `default_member_permissions`."""
    integration_types: list[ApplicationIntegrationType] | UnsetType = UNSET
    contexts: list[InteractionContextType] | UnsetType = UNSET
    type: ApplicationCommandType | UnsetType = UNSET
    nsfw: bool | UnsetType = UNSET
    handler: EntryPointCommandHandlerType | UnsetType = UNSET


class EditGlobalApplicationCommandParams(Payload):
    """JSON body of Edit Global Application Command. Fields given replace the existing values.

    Discord: https://docs.discord.com/developers/interactions/application-commands#edit-global-application-command-json-params
    """

    name: str | UnsetType = UNSET
    name_localizations: Localizations | UnsetType | None = UNSET
    description: str | UnsetType = UNSET
    description_localizations: Localizations | UnsetType | None = UNSET
    options: list[ApplicationCommandOption] | UnsetType = UNSET
    default_member_permissions: Permissions | UnsetType | None = UNSET
    dm_permission: bool | UnsetType | None = UNSET
    """Deprecated; use `contexts`."""
    default_permission: bool | UnsetType = UNSET
    """Deprecated; use `default_member_permissions`."""
    integration_types: list[ApplicationIntegrationType] | UnsetType = UNSET
    contexts: list[InteractionContextType] | UnsetType = UNSET
    nsfw: bool | UnsetType = UNSET
    handler: EntryPointCommandHandlerType | UnsetType = UNSET


class CreateGuildApplicationCommandParams(Payload):
    """JSON body of Create Guild Application Command. A command with the same name is replaced.

    Guild commands have no `contexts` or `integration_types`: those apply to global commands only.

    Discord: https://docs.discord.com/developers/interactions/application-commands#create-guild-application-command-json-params
    """

    name: str
    name_localizations: Localizations | UnsetType | None = UNSET
    description: str | UnsetType = UNSET
    """Required for `CHAT_INPUT` commands."""
    description_localizations: Localizations | UnsetType | None = UNSET
    options: list[ApplicationCommandOption] | UnsetType = UNSET
    default_member_permissions: Permissions | UnsetType | None = UNSET
    default_permission: bool | UnsetType = UNSET
    """Deprecated; use `default_member_permissions`."""
    type: ApplicationCommandType | UnsetType = UNSET
    nsfw: bool | UnsetType = UNSET


class EditGuildApplicationCommandParams(Payload):
    """JSON body of Edit Guild Application Command. Fields given replace the existing values.

    Discord: https://docs.discord.com/developers/interactions/application-commands#edit-guild-application-command-json-params
    """

    name: str | UnsetType = UNSET
    name_localizations: Localizations | UnsetType | None = UNSET
    description: str | UnsetType = UNSET
    description_localizations: Localizations | UnsetType | None = UNSET
    options: list[ApplicationCommandOption] | UnsetType = UNSET
    default_member_permissions: Permissions | UnsetType | None = UNSET
    default_permission: bool | UnsetType = UNSET
    """Deprecated; use `default_member_permissions`."""
    nsfw: bool | UnsetType = UNSET


class BulkApplicationCommandParams(Payload):
    """One command in a Bulk Overwrite request; commands left out of the list are deleted.

    Give `id` to update a known command in place instead of matching it by name. `contexts`,
    `integration_types` and `handler` only apply to global commands.

    Discord: https://docs.discord.com/developers/interactions/application-commands#bulk-overwrite-guild-application-commands-json-params
    """

    id: Snowflake | UnsetType = UNSET
    name: str
    name_localizations: Localizations | UnsetType | None = UNSET
    description: str | UnsetType = UNSET
    """Required for `CHAT_INPUT` and `PRIMARY_ENTRY_POINT` commands."""
    description_localizations: Localizations | UnsetType | None = UNSET
    options: list[ApplicationCommandOption] | UnsetType = UNSET
    default_member_permissions: Permissions | UnsetType | None = UNSET
    dm_permission: bool | UnsetType | None = UNSET
    """Deprecated; use `contexts`."""
    default_permission: bool | UnsetType = UNSET
    """Deprecated; use `default_member_permissions`."""
    integration_types: list[ApplicationIntegrationType] | UnsetType = UNSET
    contexts: list[InteractionContextType] | UnsetType = UNSET
    type: ApplicationCommandType | UnsetType = UNSET
    nsfw: bool | UnsetType = UNSET
    handler: EntryPointCommandHandlerType | UnsetType = UNSET


class ApplicationCommandPermission(Payload):
    """Allows or denies a command for one role, user or channel.

    For every member or every channel, use `everyone_permission_id` or `all_channels_permission_id`.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-permissions-object-application-command-permissions-structure
    """

    id: Snowflake
    type: ApplicationCommandPermissionType
    permission: bool
    """`True` allows, `False` denies."""


class GuildApplicationCommandPermissions(Payload):
    """The permission overwrites of one command (or of the whole app) in one guild.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-permissions-object-guild-application-command-permissions-structure
    """

    id: Snowflake
    """The command's ID, or the application's ID when the overwrites apply to every command."""
    application_id: Snowflake
    guild_id: Snowflake
    permissions: list[ApplicationCommandPermission]
    """At most 100."""


class EditApplicationCommandPermissionsParams(Payload):
    """JSON body of Edit Application Command Permissions; replaces every existing overwrite.

    The request needs an OAuth2 bearer token of a user who can manage the guild and its roles.

    Discord: https://docs.discord.com/developers/interactions/application-commands#edit-application-command-permissions-json-params
    """

    permissions: list[ApplicationCommandPermission]


def everyone_permission_id(guild_id: int) -> Snowflake:
    """The permission target meaning every member of a guild: the guild's own ID.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-permissions-object-application-command-permissions-constants
    """
    return Snowflake(guild_id)


def all_channels_permission_id(guild_id: int) -> Snowflake:
    """The permission target meaning every channel of a guild: the guild's ID minus one.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-permissions-object-application-command-permissions-constants
    """
    return Snowflake(guild_id - 1)
