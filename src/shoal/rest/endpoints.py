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

CREATE_APPLICATION_EMOJI: Final = Route(
    HTTPMethod.POST,
    "/applications/{application_id}/emojis",
    docs="https://docs.discord.com/developers/resources/emoji#create-application-emoji",
)

CREATE_DM: Final = Route(
    HTTPMethod.POST,
    "/users/@me/channels",
    docs="https://docs.discord.com/developers/resources/user#create-dm",
)

CREATE_FOLLOWUP_MESSAGE: Final = Route(
    HTTPMethod.POST,
    "/webhooks/{application_id}/{interaction_token}",
    docs="https://docs.discord.com/developers/interactions/receiving-and-responding#create-followup-message",
    global_limit=False,
)
"""Not counted towards the global rate limit, like every interaction endpoint."""

CREATE_GLOBAL_APPLICATION_COMMAND: Final = Route(
    HTTPMethod.POST,
    "/applications/{application_id}/commands",
    docs="https://docs.discord.com/developers/interactions/application-commands#create-global-application-command",
)

CREATE_GROUP_DM: Final = Route(
    HTTPMethod.POST,
    "/users/@me/channels",
    docs="https://docs.discord.com/developers/resources/user#create-group-dm",
)

CREATE_GUILD_APPLICATION_COMMAND: Final = Route(
    HTTPMethod.POST,
    "/applications/{application_id}/guilds/{guild_id}/commands",
    docs="https://docs.discord.com/developers/interactions/application-commands#create-guild-application-command",
)

CREATE_GUILD_EMOJI: Final = Route(
    HTTPMethod.POST,
    "/guilds/{guild_id}/emojis",
    docs="https://docs.discord.com/developers/resources/emoji#create-guild-emoji",
)

CREATE_GUILD_SOUNDBOARD_SOUND: Final = Route(
    HTTPMethod.POST,
    "/guilds/{guild_id}/soundboard-sounds",
    docs="https://docs.discord.com/developers/resources/soundboard#create-guild-soundboard-sound",
)

CREATE_GUILD_STICKER: Final = Route(
    HTTPMethod.POST,
    "/guilds/{guild_id}/stickers",
    docs="https://docs.discord.com/developers/resources/sticker#create-guild-sticker",
)

CREATE_INTERACTION_RESPONSE: Final = Route(
    HTTPMethod.POST,
    "/interactions/{interaction_id}/{interaction_token}/callback",
    docs="https://docs.discord.com/developers/interactions/receiving-and-responding#create-interaction-response",
    global_limit=False,
)
"""Not counted towards the global rate limit, like every interaction endpoint."""

CREATE_MESSAGE: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/messages",
    docs="https://docs.discord.com/developers/resources/message#create-message",
)

DELETE_APPLICATION_EMOJI: Final = Route(
    HTTPMethod.DELETE,
    "/applications/{application_id}/emojis/{emoji_id}",
    docs="https://docs.discord.com/developers/resources/emoji#delete-application-emoji",
)

DELETE_CURRENT_USER_APPLICATION_ROLE_CONNECTION: Final = Route(
    HTTPMethod.DELETE,
    "/users/@me/applications/{application_id}/role-connection",
    docs="https://docs.discord.com/developers/resources/user#delete-current-user-application-role-connection",
)

DELETE_FOLLOWUP_MESSAGE: Final = Route(
    HTTPMethod.DELETE,
    "/webhooks/{application_id}/{interaction_token}/messages/{message_id}",
    docs="https://docs.discord.com/developers/interactions/receiving-and-responding#delete-followup-message",
    global_limit=False,
)
"""Not counted towards the global rate limit, like every interaction endpoint."""

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

DELETE_GUILD_EMOJI: Final = Route(
    HTTPMethod.DELETE,
    "/guilds/{guild_id}/emojis/{emoji_id}",
    docs="https://docs.discord.com/developers/resources/emoji#delete-guild-emoji",
)

DELETE_GUILD_SOUNDBOARD_SOUND: Final = Route(
    HTTPMethod.DELETE,
    "/guilds/{guild_id}/soundboard-sounds/{sound_id}",
    docs="https://docs.discord.com/developers/resources/soundboard#delete-guild-soundboard-sound",
)

DELETE_GUILD_STICKER: Final = Route(
    HTTPMethod.DELETE,
    "/guilds/{guild_id}/stickers/{sticker_id}",
    docs="https://docs.discord.com/developers/resources/sticker#delete-guild-sticker",
)

DELETE_MESSAGE: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}/messages/{message_id}",
    docs="https://docs.discord.com/developers/resources/message#delete-message",
)

DELETE_ORIGINAL_INTERACTION_RESPONSE: Final = Route(
    HTTPMethod.DELETE,
    "/webhooks/{application_id}/{interaction_token}/messages/@original",
    docs="https://docs.discord.com/developers/interactions/receiving-and-responding#delete-original-interaction-response",
    global_limit=False,
)
"""Not counted towards the global rate limit, like every interaction endpoint."""

EDIT_APPLICATION_COMMAND_PERMISSIONS: Final = Route(
    HTTPMethod.PUT,
    "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions",
    docs="https://docs.discord.com/developers/interactions/application-commands#edit-application-command-permissions",
)

EDIT_FOLLOWUP_MESSAGE: Final = Route(
    HTTPMethod.PATCH,
    "/webhooks/{application_id}/{interaction_token}/messages/{message_id}",
    docs="https://docs.discord.com/developers/interactions/receiving-and-responding#edit-followup-message",
    global_limit=False,
)
"""Not counted towards the global rate limit, like every interaction endpoint."""

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

EDIT_ORIGINAL_INTERACTION_RESPONSE: Final = Route(
    HTTPMethod.PATCH,
    "/webhooks/{application_id}/{interaction_token}/messages/@original",
    docs="https://docs.discord.com/developers/interactions/receiving-and-responding#edit-original-interaction-response",
    global_limit=False,
)
"""Not counted towards the global rate limit, like every interaction endpoint."""

GET_APPLICATION_COMMAND_PERMISSIONS: Final = Route(
    HTTPMethod.GET,
    "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions",
    docs="https://docs.discord.com/developers/interactions/application-commands#get-application-command-permissions",
)

GET_APPLICATION_EMOJI: Final = Route(
    HTTPMethod.GET,
    "/applications/{application_id}/emojis/{emoji_id}",
    docs="https://docs.discord.com/developers/resources/emoji#get-application-emoji",
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

GET_CURRENT_USER_APPLICATION_ROLE_CONNECTION: Final = Route(
    HTTPMethod.GET,
    "/users/@me/applications/{application_id}/role-connection",
    docs="https://docs.discord.com/developers/resources/user#get-current-user-application-role-connection",
)

GET_CURRENT_USER_CONNECTIONS: Final = Route(
    HTTPMethod.GET,
    "/users/@me/connections",
    docs="https://docs.discord.com/developers/resources/user#get-current-user-connections",
)

GET_CURRENT_USER_GUILDS: Final = Route(
    HTTPMethod.GET,
    "/users/@me/guilds",
    docs="https://docs.discord.com/developers/resources/user#get-current-user-guilds",
)

GET_CURRENT_USER_GUILD_MEMBER: Final = Route(
    HTTPMethod.GET,
    "/users/@me/guilds/{guild_id}/member",
    docs="https://docs.discord.com/developers/resources/user#get-current-user-guild-member",
)

GET_CURRENT_USER_VOICE_STATE: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/voice-states/@me",
    docs="https://docs.discord.com/developers/resources/voice#get-current-user-voice-state",
)

GET_FOLLOWUP_MESSAGE: Final = Route(
    HTTPMethod.GET,
    "/webhooks/{application_id}/{interaction_token}/messages/{message_id}",
    docs="https://docs.discord.com/developers/interactions/receiving-and-responding#get-followup-message",
    global_limit=False,
)
"""Not counted towards the global rate limit, like every interaction endpoint."""

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

GET_GUILD_EMOJI: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/emojis/{emoji_id}",
    docs="https://docs.discord.com/developers/resources/emoji#get-guild-emoji",
)

GET_GUILD_MEMBER: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/members/{user_id}",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-member",
)

GET_GUILD_SOUNDBOARD_SOUND: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/soundboard-sounds/{sound_id}",
    docs="https://docs.discord.com/developers/resources/soundboard#get-guild-soundboard-sound",
)

GET_GUILD_STICKER: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/stickers/{sticker_id}",
    docs="https://docs.discord.com/developers/resources/sticker#get-guild-sticker",
)

GET_ORIGINAL_INTERACTION_RESPONSE: Final = Route(
    HTTPMethod.GET,
    "/webhooks/{application_id}/{interaction_token}/messages/@original",
    docs="https://docs.discord.com/developers/interactions/receiving-and-responding#get-original-interaction-response",
    global_limit=False,
)
"""Not counted towards the global rate limit, like every interaction endpoint."""

GET_STICKER: Final = Route(
    HTTPMethod.GET,
    "/stickers/{sticker_id}",
    docs="https://docs.discord.com/developers/resources/sticker#get-sticker",
)

GET_STICKER_PACK: Final = Route(
    HTTPMethod.GET,
    "/sticker-packs/{pack_id}",
    docs="https://docs.discord.com/developers/resources/sticker#get-sticker-pack",
)

GET_USER: Final = Route(
    HTTPMethod.GET,
    "/users/{user_id}",
    docs="https://docs.discord.com/developers/resources/user#get-user",
)

GET_USER_VOICE_STATE: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/voice-states/{user_id}",
    docs="https://docs.discord.com/developers/resources/voice#get-user-voice-state",
)

LEAVE_GUILD: Final = Route(
    HTTPMethod.DELETE,
    "/users/@me/guilds/{guild_id}",
    docs="https://docs.discord.com/developers/resources/user#leave-guild",
)

LIST_APPLICATION_EMOJIS: Final = Route(
    HTTPMethod.GET,
    "/applications/{application_id}/emojis",
    docs="https://docs.discord.com/developers/resources/emoji#list-application-emojis",
)

LIST_DEFAULT_SOUNDBOARD_SOUNDS: Final = Route(
    HTTPMethod.GET,
    "/soundboard-default-sounds",
    docs="https://docs.discord.com/developers/resources/soundboard#list-default-soundboard-sounds",
)

LIST_GUILD_EMOJIS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/emojis",
    docs="https://docs.discord.com/developers/resources/emoji#list-guild-emojis",
)

LIST_GUILD_SOUNDBOARD_SOUNDS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/soundboard-sounds",
    docs="https://docs.discord.com/developers/resources/soundboard#list-guild-soundboard-sounds",
)

LIST_GUILD_STICKERS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/stickers",
    docs="https://docs.discord.com/developers/resources/sticker#list-guild-stickers",
)

LIST_STICKER_PACKS: Final = Route(
    HTTPMethod.GET,
    "/sticker-packs",
    docs="https://docs.discord.com/developers/resources/sticker#list-sticker-packs",
)

LIST_VOICE_REGIONS: Final = Route(
    HTTPMethod.GET,
    "/voice/regions",
    docs="https://docs.discord.com/developers/resources/voice#list-voice-regions",
)

MODIFY_APPLICATION_EMOJI: Final = Route(
    HTTPMethod.PATCH,
    "/applications/{application_id}/emojis/{emoji_id}",
    docs="https://docs.discord.com/developers/resources/emoji#modify-application-emoji",
)

MODIFY_CURRENT_USER: Final = Route(
    HTTPMethod.PATCH,
    "/users/@me",
    docs="https://docs.discord.com/developers/resources/user#modify-current-user",
)

MODIFY_CURRENT_USER_VOICE_STATE: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/voice-states/@me",
    docs="https://docs.discord.com/developers/resources/voice#modify-current-user-voice-state",
)

MODIFY_GUILD_EMOJI: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/emojis/{emoji_id}",
    docs="https://docs.discord.com/developers/resources/emoji#modify-guild-emoji",
)

MODIFY_GUILD_SOUNDBOARD_SOUND: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/soundboard-sounds/{sound_id}",
    docs="https://docs.discord.com/developers/resources/soundboard#modify-guild-soundboard-sound",
)

MODIFY_GUILD_STICKER: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/stickers/{sticker_id}",
    docs="https://docs.discord.com/developers/resources/sticker#modify-guild-sticker",
)

MODIFY_USER_VOICE_STATE: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/voice-states/{user_id}",
    docs="https://docs.discord.com/developers/resources/voice#modify-user-voice-state",
)

SEARCH_GUILD_MESSAGES: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/messages/search",
    docs="https://docs.discord.com/developers/resources/message#search-guild-messages",
)

SEND_SOUNDBOARD_SOUND: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/send-soundboard-sound",
    docs="https://docs.discord.com/developers/resources/soundboard#send-soundboard-sound",
)

UPDATE_CURRENT_USER_APPLICATION_ROLE_CONNECTION: Final = Route(
    HTTPMethod.PUT,
    "/users/@me/applications/{application_id}/role-connection",
    docs="https://docs.discord.com/developers/resources/user#update-current-user-application-role-connection",
)

ALL_ROUTES: Final = (
    BULK_OVERWRITE_GLOBAL_APPLICATION_COMMANDS,
    BULK_OVERWRITE_GUILD_APPLICATION_COMMANDS,
    CREATE_APPLICATION_EMOJI,
    CREATE_DM,
    CREATE_FOLLOWUP_MESSAGE,
    CREATE_GLOBAL_APPLICATION_COMMAND,
    CREATE_GROUP_DM,
    CREATE_GUILD_APPLICATION_COMMAND,
    CREATE_GUILD_EMOJI,
    CREATE_GUILD_SOUNDBOARD_SOUND,
    CREATE_GUILD_STICKER,
    CREATE_INTERACTION_RESPONSE,
    CREATE_MESSAGE,
    DELETE_APPLICATION_EMOJI,
    DELETE_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
    DELETE_FOLLOWUP_MESSAGE,
    DELETE_GLOBAL_APPLICATION_COMMAND,
    DELETE_GUILD_APPLICATION_COMMAND,
    DELETE_GUILD_EMOJI,
    DELETE_GUILD_SOUNDBOARD_SOUND,
    DELETE_GUILD_STICKER,
    DELETE_MESSAGE,
    DELETE_ORIGINAL_INTERACTION_RESPONSE,
    EDIT_APPLICATION_COMMAND_PERMISSIONS,
    EDIT_FOLLOWUP_MESSAGE,
    EDIT_GLOBAL_APPLICATION_COMMAND,
    EDIT_GUILD_APPLICATION_COMMAND,
    EDIT_ORIGINAL_INTERACTION_RESPONSE,
    GET_APPLICATION_COMMAND_PERMISSIONS,
    GET_APPLICATION_EMOJI,
    GET_CHANNEL,
    GET_CHANNEL_MESSAGE,
    GET_CURRENT_USER,
    GET_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
    GET_CURRENT_USER_CONNECTIONS,
    GET_CURRENT_USER_GUILDS,
    GET_CURRENT_USER_GUILD_MEMBER,
    GET_CURRENT_USER_VOICE_STATE,
    GET_FOLLOWUP_MESSAGE,
    GET_GATEWAY,
    GET_GATEWAY_BOT,
    GET_GLOBAL_APPLICATION_COMMAND,
    GET_GLOBAL_APPLICATION_COMMANDS,
    GET_GUILD,
    GET_GUILD_APPLICATION_COMMAND,
    GET_GUILD_APPLICATION_COMMANDS,
    GET_GUILD_APPLICATION_COMMAND_PERMISSIONS,
    GET_GUILD_EMOJI,
    GET_GUILD_MEMBER,
    GET_GUILD_SOUNDBOARD_SOUND,
    GET_GUILD_STICKER,
    GET_ORIGINAL_INTERACTION_RESPONSE,
    GET_STICKER,
    GET_STICKER_PACK,
    GET_USER,
    GET_USER_VOICE_STATE,
    LEAVE_GUILD,
    LIST_APPLICATION_EMOJIS,
    LIST_DEFAULT_SOUNDBOARD_SOUNDS,
    LIST_GUILD_EMOJIS,
    LIST_GUILD_SOUNDBOARD_SOUNDS,
    LIST_GUILD_STICKERS,
    LIST_STICKER_PACKS,
    LIST_VOICE_REGIONS,
    MODIFY_APPLICATION_EMOJI,
    MODIFY_CURRENT_USER,
    MODIFY_CURRENT_USER_VOICE_STATE,
    MODIFY_GUILD_EMOJI,
    MODIFY_GUILD_SOUNDBOARD_SOUND,
    MODIFY_GUILD_STICKER,
    MODIFY_USER_VOICE_STATE,
    SEARCH_GUILD_MESSAGES,
    SEND_SOUNDBOARD_SOUND,
    UPDATE_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
)
"""Every declared route, for the docs checker and tests."""
