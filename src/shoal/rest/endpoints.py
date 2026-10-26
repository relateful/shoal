"""Every HTTP endpoint Shoal calls, declared once with its Discord docs link.

Each constant is named after the docs section title in UPPER_SNAKE_CASE, and its path uses Discord's
placeholders with `.` replaced by `_` (`{channel.id}` becomes `{channel_id}`). The
`scripts/check_docs.py` checker compares every route here against the `<Route>` declarations in the
Discord docs source, so a path or method drift is caught before release.
"""

from typing import Final

from shoal.rest.route import HTTPMethod, Route

ADD_TARGET_USER: Final = Route(
    HTTPMethod.PUT,
    "/invites/{invite_code}/target-users/{user_id}",
    docs="https://docs.discord.com/developers/resources/invite#add-target-user",
)

ADD_THREAD_MEMBER: Final = Route(
    HTTPMethod.PUT,
    "/channels/{channel_id}/thread-members/{user_id}",
    docs="https://docs.discord.com/developers/resources/channel#add-thread-member",
)

BULK_ADD_TARGET_USERS: Final = Route(
    HTTPMethod.POST,
    "/invites/{invite_code}/target-users/bulk-add",
    docs="https://docs.discord.com/developers/resources/invite#bulk-add-target-users",
)

BULK_DELETE_MESSAGES: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/messages/bulk-delete",
    docs="https://docs.discord.com/developers/resources/message#bulk-delete-messages",
)

BULK_DELETE_TARGET_USERS: Final = Route(
    HTTPMethod.POST,
    "/invites/{invite_code}/target-users/bulk-delete",
    docs="https://docs.discord.com/developers/resources/invite#bulk-delete-target-users",
)

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

CREATE_CHANNEL_INVITE: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/invites",
    docs="https://docs.discord.com/developers/resources/channel#create-channel-invite",
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

CREATE_REACTION: Final = Route(
    HTTPMethod.PUT,
    "/channels/{channel_id}/messages/{message_id}/reactions/{emoji_id}/@me",
    docs="https://docs.discord.com/developers/resources/message#create-reaction",
)

CROSSPOST_MESSAGE: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/messages/{message_id}/crosspost",
    docs="https://docs.discord.com/developers/resources/message#crosspost-message",
)

DELETE_ALL_REACTIONS: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}/messages/{message_id}/reactions",
    docs="https://docs.discord.com/developers/resources/message#delete-all-reactions",
)

DELETE_ALL_REACTIONS_FOR_EMOJI: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}/messages/{message_id}/reactions/{emoji_id}",
    docs="https://docs.discord.com/developers/resources/message#delete-all-reactions-for-emoji",
)

DELETE_APPLICATION_EMOJI: Final = Route(
    HTTPMethod.DELETE,
    "/applications/{application_id}/emojis/{emoji_id}",
    docs="https://docs.discord.com/developers/resources/emoji#delete-application-emoji",
)

DELETE_CHANNEL: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}",
    docs="https://docs.discord.com/developers/resources/channel#delete/close-channel",
)

DELETE_CHANNEL_PERMISSION: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}/permissions/{overwrite_id}",
    docs="https://docs.discord.com/developers/resources/channel#delete-channel-permission",
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

DELETE_INVITE: Final = Route(
    HTTPMethod.DELETE,
    "/invites/{invite_code}",
    docs="https://docs.discord.com/developers/resources/invite#delete-invite",
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

DELETE_OWN_REACTION: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}/messages/{message_id}/reactions/{emoji_id}/@me",
    docs="https://docs.discord.com/developers/resources/message#delete-own-reaction",
)

DELETE_USER_REACTION: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}/messages/{message_id}/reactions/{emoji_id}/{user_id}",
    docs="https://docs.discord.com/developers/resources/message#delete-user-reaction",
)

EDIT_APPLICATION_COMMAND_PERMISSIONS: Final = Route(
    HTTPMethod.PUT,
    "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions",
    docs="https://docs.discord.com/developers/interactions/application-commands#edit-application-command-permissions",
)

EDIT_CHANNEL_PERMISSIONS: Final = Route(
    HTTPMethod.PUT,
    "/channels/{channel_id}/permissions/{overwrite_id}",
    docs="https://docs.discord.com/developers/resources/channel#edit-channel-permissions",
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

EDIT_MESSAGE: Final = Route(
    HTTPMethod.PATCH,
    "/channels/{channel_id}/messages/{message_id}",
    docs="https://docs.discord.com/developers/resources/message#edit-message",
)

EDIT_ORIGINAL_INTERACTION_RESPONSE: Final = Route(
    HTTPMethod.PATCH,
    "/webhooks/{application_id}/{interaction_token}/messages/@original",
    docs="https://docs.discord.com/developers/interactions/receiving-and-responding#edit-original-interaction-response",
    global_limit=False,
)
"""Not counted towards the global rate limit, like every interaction endpoint."""

END_POLL: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/polls/{message_id}/expire",
    docs="https://docs.discord.com/developers/resources/poll#end-poll",
)

FOLLOW_ANNOUNCEMENT_CHANNEL: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/followers",
    docs="https://docs.discord.com/developers/resources/channel#follow-announcement-channel",
)

GET_ANSWER_VOTERS: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/polls/{message_id}/answers/{answer_id}",
    docs="https://docs.discord.com/developers/resources/poll#get-answer-voters",
)

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

GET_CHANNEL_INVITES: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/invites",
    docs="https://docs.discord.com/developers/resources/channel#get-channel-invites",
)

GET_CHANNEL_MESSAGE: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/messages/{message_id}",
    docs="https://docs.discord.com/developers/resources/message#get-channel-message",
)

GET_CHANNEL_MESSAGES: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/messages",
    docs="https://docs.discord.com/developers/resources/message#get-channel-messages",
)

GET_CHANNEL_PINS: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/messages/pins",
    docs="https://docs.discord.com/developers/resources/message#get-channel-pins",
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

GET_INVITE: Final = Route(
    HTTPMethod.GET,
    "/invites/{invite_code}",
    docs="https://docs.discord.com/developers/resources/invite#get-invite",
)

GET_ORIGINAL_INTERACTION_RESPONSE: Final = Route(
    HTTPMethod.GET,
    "/webhooks/{application_id}/{interaction_token}/messages/@original",
    docs="https://docs.discord.com/developers/interactions/receiving-and-responding#get-original-interaction-response",
    global_limit=False,
)
"""Not counted towards the global rate limit, like every interaction endpoint."""

GET_REACTIONS: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/messages/{message_id}/reactions/{emoji_id}",
    docs="https://docs.discord.com/developers/resources/message#get-reactions",
)

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

GET_TARGET_USERS: Final = Route(
    HTTPMethod.GET,
    "/invites/{invite_code}/target-users",
    docs="https://docs.discord.com/developers/resources/invite#get-target-users",
)

GET_TARGET_USERS_JOB_STATUS: Final = Route(
    HTTPMethod.GET,
    "/invites/{invite_code}/target-users/job-status",
    docs="https://docs.discord.com/developers/resources/invite#get-target-users-job-status",
)

GET_THREAD_MEMBER: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/thread-members/{user_id}",
    docs="https://docs.discord.com/developers/resources/channel#get-thread-member",
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

GROUP_DM_ADD_RECIPIENT: Final = Route(
    HTTPMethod.PUT,
    "/channels/{channel_id}/recipients/{user_id}",
    docs="https://docs.discord.com/developers/resources/channel#group-dm-add-recipient",
)

GROUP_DM_REMOVE_RECIPIENT: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}/recipients/{user_id}",
    docs="https://docs.discord.com/developers/resources/channel#group-dm-remove-recipient",
)

JOIN_THREAD: Final = Route(
    HTTPMethod.PUT,
    "/channels/{channel_id}/thread-members/@me",
    docs="https://docs.discord.com/developers/resources/channel#join-thread",
)

LEAVE_GUILD: Final = Route(
    HTTPMethod.DELETE,
    "/users/@me/guilds/{guild_id}",
    docs="https://docs.discord.com/developers/resources/user#leave-guild",
)

LEAVE_THREAD: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}/thread-members/@me",
    docs="https://docs.discord.com/developers/resources/channel#leave-thread",
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

LIST_JOINED_PRIVATE_ARCHIVED_THREADS: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/users/@me/threads/archived/private",
    docs="https://docs.discord.com/developers/resources/channel#list-joined-private-archived-threads",
)

LIST_PRIVATE_ARCHIVED_THREADS: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/threads/archived/private",
    docs="https://docs.discord.com/developers/resources/channel#list-private-archived-threads",
)

LIST_PUBLIC_ARCHIVED_THREADS: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/threads/archived/public",
    docs="https://docs.discord.com/developers/resources/channel#list-public-archived-threads",
)

LIST_STICKER_PACKS: Final = Route(
    HTTPMethod.GET,
    "/sticker-packs",
    docs="https://docs.discord.com/developers/resources/sticker#list-sticker-packs",
)

LIST_THREAD_MEMBERS: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/thread-members",
    docs="https://docs.discord.com/developers/resources/channel#list-thread-members",
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

MODIFY_CHANNEL: Final = Route(
    HTTPMethod.PATCH,
    "/channels/{channel_id}",
    docs="https://docs.discord.com/developers/resources/channel#modify-channel",
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

PIN_MESSAGE: Final = Route(
    HTTPMethod.PUT,
    "/channels/{channel_id}/messages/pins/{message_id}",
    docs="https://docs.discord.com/developers/resources/message#pin-message",
)

REMOVE_TARGET_USER: Final = Route(
    HTTPMethod.DELETE,
    "/invites/{invite_code}/target-users/{user_id}",
    docs="https://docs.discord.com/developers/resources/invite#remove-target-user",
)

REMOVE_THREAD_MEMBER: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}/thread-members/{user_id}",
    docs="https://docs.discord.com/developers/resources/channel#remove-thread-member",
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

SET_VOICE_CHANNEL_STATUS: Final = Route(
    HTTPMethod.PUT,
    "/channels/{channel_id}/voice-status",
    docs="https://docs.discord.com/developers/resources/channel#set-voice-channel-status",
)

START_THREAD_FROM_MESSAGE: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/messages/{message_id}/threads",
    docs="https://docs.discord.com/developers/resources/channel#start-thread-from-message",
)

START_THREAD_IN_FORUM_OR_MEDIA_CHANNEL: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/threads",
    docs="https://docs.discord.com/developers/resources/channel#start-thread-in-forum-or-media-channel",
)

START_THREAD_WITHOUT_MESSAGE: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/threads",
    docs="https://docs.discord.com/developers/resources/channel#start-thread-without-message",
)

TRIGGER_TYPING_INDICATOR: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/typing",
    docs="https://docs.discord.com/developers/resources/channel#trigger-typing-indicator",
)

UNPIN_MESSAGE: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}/messages/pins/{message_id}",
    docs="https://docs.discord.com/developers/resources/message#unpin-message",
)

UPDATE_CURRENT_USER_APPLICATION_ROLE_CONNECTION: Final = Route(
    HTTPMethod.PUT,
    "/users/@me/applications/{application_id}/role-connection",
    docs="https://docs.discord.com/developers/resources/user#update-current-user-application-role-connection",
)

UPDATE_TARGET_USERS: Final = Route(
    HTTPMethod.PUT,
    "/invites/{invite_code}/target-users",
    docs="https://docs.discord.com/developers/resources/invite#update-target-users",
)

ALL_ROUTES: Final = (
    ADD_TARGET_USER,
    ADD_THREAD_MEMBER,
    BULK_ADD_TARGET_USERS,
    BULK_DELETE_MESSAGES,
    BULK_DELETE_TARGET_USERS,
    BULK_OVERWRITE_GLOBAL_APPLICATION_COMMANDS,
    BULK_OVERWRITE_GUILD_APPLICATION_COMMANDS,
    CREATE_APPLICATION_EMOJI,
    CREATE_CHANNEL_INVITE,
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
    CREATE_REACTION,
    CROSSPOST_MESSAGE,
    DELETE_ALL_REACTIONS,
    DELETE_ALL_REACTIONS_FOR_EMOJI,
    DELETE_APPLICATION_EMOJI,
    DELETE_CHANNEL,
    DELETE_CHANNEL_PERMISSION,
    DELETE_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
    DELETE_FOLLOWUP_MESSAGE,
    DELETE_GLOBAL_APPLICATION_COMMAND,
    DELETE_GUILD_APPLICATION_COMMAND,
    DELETE_GUILD_EMOJI,
    DELETE_GUILD_SOUNDBOARD_SOUND,
    DELETE_GUILD_STICKER,
    DELETE_INVITE,
    DELETE_MESSAGE,
    DELETE_ORIGINAL_INTERACTION_RESPONSE,
    DELETE_OWN_REACTION,
    DELETE_USER_REACTION,
    EDIT_APPLICATION_COMMAND_PERMISSIONS,
    EDIT_CHANNEL_PERMISSIONS,
    EDIT_FOLLOWUP_MESSAGE,
    EDIT_GLOBAL_APPLICATION_COMMAND,
    EDIT_GUILD_APPLICATION_COMMAND,
    EDIT_MESSAGE,
    EDIT_ORIGINAL_INTERACTION_RESPONSE,
    END_POLL,
    FOLLOW_ANNOUNCEMENT_CHANNEL,
    GET_ANSWER_VOTERS,
    GET_APPLICATION_COMMAND_PERMISSIONS,
    GET_APPLICATION_EMOJI,
    GET_CHANNEL,
    GET_CHANNEL_INVITES,
    GET_CHANNEL_MESSAGE,
    GET_CHANNEL_MESSAGES,
    GET_CHANNEL_PINS,
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
    GET_INVITE,
    GET_ORIGINAL_INTERACTION_RESPONSE,
    GET_REACTIONS,
    GET_STICKER,
    GET_STICKER_PACK,
    GET_TARGET_USERS,
    GET_TARGET_USERS_JOB_STATUS,
    GET_THREAD_MEMBER,
    GET_USER,
    GET_USER_VOICE_STATE,
    GROUP_DM_ADD_RECIPIENT,
    GROUP_DM_REMOVE_RECIPIENT,
    JOIN_THREAD,
    LEAVE_GUILD,
    LEAVE_THREAD,
    LIST_APPLICATION_EMOJIS,
    LIST_DEFAULT_SOUNDBOARD_SOUNDS,
    LIST_GUILD_EMOJIS,
    LIST_GUILD_SOUNDBOARD_SOUNDS,
    LIST_GUILD_STICKERS,
    LIST_JOINED_PRIVATE_ARCHIVED_THREADS,
    LIST_PRIVATE_ARCHIVED_THREADS,
    LIST_PUBLIC_ARCHIVED_THREADS,
    LIST_STICKER_PACKS,
    LIST_THREAD_MEMBERS,
    LIST_VOICE_REGIONS,
    MODIFY_APPLICATION_EMOJI,
    MODIFY_CHANNEL,
    MODIFY_CURRENT_USER,
    MODIFY_CURRENT_USER_VOICE_STATE,
    MODIFY_GUILD_EMOJI,
    MODIFY_GUILD_SOUNDBOARD_SOUND,
    MODIFY_GUILD_STICKER,
    MODIFY_USER_VOICE_STATE,
    PIN_MESSAGE,
    REMOVE_TARGET_USER,
    REMOVE_THREAD_MEMBER,
    SEARCH_GUILD_MESSAGES,
    SEND_SOUNDBOARD_SOUND,
    SET_VOICE_CHANNEL_STATUS,
    START_THREAD_FROM_MESSAGE,
    START_THREAD_IN_FORUM_OR_MEDIA_CHANNEL,
    START_THREAD_WITHOUT_MESSAGE,
    TRIGGER_TYPING_INDICATOR,
    UNPIN_MESSAGE,
    UPDATE_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
    UPDATE_TARGET_USERS,
)
"""Every declared route, for the docs checker and tests."""
