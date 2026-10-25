"""Every HTTP endpoint Shoal calls, declared once with its Discord docs link.

Each constant is named after the docs section title in UPPER_SNAKE_CASE, and its path uses Discord's
placeholders with `.` replaced by `_` (`{channel.id}` becomes `{channel_id}`). The
`scripts/check_docs.py` checker compares every route here against the `<Route>` declarations in the
Discord docs source, so a path or method drift is caught before release.
"""

from typing import Final

from shoal.rest.route import HTTPMethod, Route

BULK_OVERWRITE_GLOBAL_APPLICATION_COMMANDS: Final = Route(
    HTTPMethod.PUT,
    "/applications/{application_id}/commands",
    docs="https://docs.discord.com/developers/interactions/application-commands#bulk-overwrite-global-application-commands",
)

BULK_OVERWRITE_GUILD_APPLICATION_COMMANDS: Final = Route(
    HTTPMethod.PUT,
    "/applications/{application_id}/guilds/{guild_id}/commands",
    docs="https://docs.discord.com/developers/interactions/application-commands#bulk-overwrite-guild-application-commands",
)

CREATE_GLOBAL_APPLICATION_COMMAND: Final = Route(
    HTTPMethod.POST,
    "/applications/{application_id}/commands",
    docs="https://docs.discord.com/developers/interactions/application-commands#create-global-application-command",
)

CREATE_GUILD_APPLICATION_COMMAND: Final = Route(
    HTTPMethod.POST,
    "/applications/{application_id}/guilds/{guild_id}/commands",
    docs="https://docs.discord.com/developers/interactions/application-commands#create-guild-application-command",
)

CREATE_MESSAGE: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/messages",
    docs="https://docs.discord.com/developers/resources/message#create-message",
)

DELETE_GLOBAL_APPLICATION_COMMAND: Final = Route(
    HTTPMethod.DELETE,
    "/applications/{application_id}/commands/{command_id}",
    docs="https://docs.discord.com/developers/interactions/application-commands#delete-global-application-command",
)

DELETE_GUILD_APPLICATION_COMMAND: Final = Route(
    HTTPMethod.DELETE,
    "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}",
    docs="https://docs.discord.com/developers/interactions/application-commands#delete-guild-application-command",
)

DELETE_MESSAGE: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}/messages/{message_id}",
    docs="https://docs.discord.com/developers/resources/message#delete-message",
)

EDIT_APPLICATION_COMMAND_PERMISSIONS: Final = Route(
    HTTPMethod.PUT,
    "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions",
    docs="https://docs.discord.com/developers/interactions/application-commands#edit-application-command-permissions",
)

EDIT_GLOBAL_APPLICATION_COMMAND: Final = Route(
    HTTPMethod.PATCH,
    "/applications/{application_id}/commands/{command_id}",
    docs="https://docs.discord.com/developers/interactions/application-commands#edit-global-application-command",
)

EDIT_GUILD_APPLICATION_COMMAND: Final = Route(
    HTTPMethod.PATCH,
    "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}",
    docs="https://docs.discord.com/developers/interactions/application-commands#edit-guild-application-command",
)

GET_APPLICATION_COMMAND_PERMISSIONS: Final = Route(
    HTTPMethod.GET,
    "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions",
    docs="https://docs.discord.com/developers/interactions/application-commands#get-application-command-permissions",
)

GET_CHANNEL: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}",
    docs="https://docs.discord.com/developers/resources/channel#get-channel",
)

GET_CHANNEL_MESSAGE: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/messages/{message_id}",
    docs="https://docs.discord.com/developers/resources/message#get-channel-message",
)

GET_CURRENT_USER: Final = Route(
    HTTPMethod.GET,
    "/users/@me",
    docs="https://docs.discord.com/developers/resources/user#get-current-user",
)

GET_GATEWAY: Final = Route(
    HTTPMethod.GET,
    "/gateway",
    docs="https://docs.discord.com/developers/events/gateway#get-gateway",
)

GET_GATEWAY_BOT: Final = Route(
    HTTPMethod.GET,
    "/gateway/bot",
    docs="https://docs.discord.com/developers/events/gateway#get-gateway-bot",
)

GET_GLOBAL_APPLICATION_COMMAND: Final = Route(
    HTTPMethod.GET,
    "/applications/{application_id}/commands/{command_id}",
    docs="https://docs.discord.com/developers/interactions/application-commands#get-global-application-command",
)

GET_GLOBAL_APPLICATION_COMMANDS: Final = Route(
    HTTPMethod.GET,
    "/applications/{application_id}/commands",
    docs="https://docs.discord.com/developers/interactions/application-commands#get-global-application-commands",
)

GET_GUILD: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}",
    docs="https://docs.discord.com/developers/resources/guild#get-guild",
)

GET_GUILD_APPLICATION_COMMAND: Final = Route(
    HTTPMethod.GET,
    "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}",
    docs="https://docs.discord.com/developers/interactions/application-commands#get-guild-application-command",
)

GET_GUILD_APPLICATION_COMMANDS: Final = Route(
    HTTPMethod.GET,
    "/applications/{application_id}/guilds/{guild_id}/commands",
    docs="https://docs.discord.com/developers/interactions/application-commands#get-guild-application-commands",
)

GET_GUILD_APPLICATION_COMMAND_PERMISSIONS: Final = Route(
    HTTPMethod.GET,
    "/applications/{application_id}/guilds/{guild_id}/commands/permissions",
    docs="https://docs.discord.com/developers/interactions/application-commands#get-guild-application-command-permissions",
)

GET_GUILD_MEMBER: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/members/{user_id}",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-member",
)

GET_USER: Final = Route(
    HTTPMethod.GET,
    "/users/{user_id}",
    docs="https://docs.discord.com/developers/resources/user#get-user",
)

SEARCH_GUILD_MESSAGES: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/messages/search",
    docs="https://docs.discord.com/developers/resources/message#search-guild-messages",
)

ALL_ROUTES: Final = (
    BULK_OVERWRITE_GLOBAL_APPLICATION_COMMANDS,
    BULK_OVERWRITE_GUILD_APPLICATION_COMMANDS,
    CREATE_GLOBAL_APPLICATION_COMMAND,
    CREATE_GUILD_APPLICATION_COMMAND,
    CREATE_MESSAGE,
    DELETE_GLOBAL_APPLICATION_COMMAND,
    DELETE_GUILD_APPLICATION_COMMAND,
    DELETE_MESSAGE,
    EDIT_APPLICATION_COMMAND_PERMISSIONS,
    EDIT_GLOBAL_APPLICATION_COMMAND,
    EDIT_GUILD_APPLICATION_COMMAND,
    GET_APPLICATION_COMMAND_PERMISSIONS,
    GET_CHANNEL,
    GET_CHANNEL_MESSAGE,
    GET_CURRENT_USER,
    GET_GATEWAY,
    GET_GATEWAY_BOT,
    GET_GLOBAL_APPLICATION_COMMAND,
    GET_GLOBAL_APPLICATION_COMMANDS,
    GET_GUILD,
    GET_GUILD_APPLICATION_COMMAND,
    GET_GUILD_APPLICATION_COMMANDS,
    GET_GUILD_APPLICATION_COMMAND_PERMISSIONS,
    GET_GUILD_MEMBER,
    GET_USER,
    SEARCH_GUILD_MESSAGES,
)
"""Every declared route, for the docs checker and tests."""
