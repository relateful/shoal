"""Every HTTP endpoint Shoal calls, declared once with its Discord docs link.

Each constant is named after the docs section title in UPPER_SNAKE_CASE, and its path uses Discord's
placeholders with `.` replaced by `_` (`{channel.id}` becomes `{channel_id}`). The
`scripts/check_docs.py` checker compares every route here against the `<Route>` declarations in the
Discord docs source, so a path or method drift is caught before release.
"""

from typing import Final

from shoal.rest.route import HTTPMethod, Route

ADD_GUILD_MEMBER: Final = Route(
    HTTPMethod.PUT,
    "/guilds/{guild_id}/members/{user_id}",
    docs="https://docs.discord.com/developers/resources/guild#add-guild-member",
)

ADD_GUILD_MEMBER_ROLE: Final = Route(
    HTTPMethod.PUT,
    "/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
    docs="https://docs.discord.com/developers/resources/guild#add-guild-member-role",
)

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

BEGIN_GUILD_PRUNE: Final = Route(
    HTTPMethod.POST,
    "/guilds/{guild_id}/prune",
    docs="https://docs.discord.com/developers/resources/guild#begin-guild-prune",
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

BULK_GUILD_BAN: Final = Route(
    HTTPMethod.POST,
    "/guilds/{guild_id}/bulk-ban",
    docs="https://docs.discord.com/developers/resources/guild#bulk-guild-ban",
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

CREATE_AUTO_MODERATION_RULE: Final = Route(
    HTTPMethod.POST,
    "/guilds/{guild_id}/auto-moderation/rules",
    docs="https://docs.discord.com/developers/resources/auto-moderation#create-auto-moderation-rule",
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

CREATE_GUILD_BAN: Final = Route(
    HTTPMethod.PUT,
    "/guilds/{guild_id}/bans/{user_id}",
    docs="https://docs.discord.com/developers/resources/guild#create-guild-ban",
)

CREATE_GUILD_CHANNEL: Final = Route(
    HTTPMethod.POST,
    "/guilds/{guild_id}/channels",
    docs="https://docs.discord.com/developers/resources/guild#create-guild-channel",
)

CREATE_GUILD_EMOJI: Final = Route(
    HTTPMethod.POST,
    "/guilds/{guild_id}/emojis",
    docs="https://docs.discord.com/developers/resources/emoji#create-guild-emoji",
)

CREATE_GUILD_ROLE: Final = Route(
    HTTPMethod.POST,
    "/guilds/{guild_id}/roles",
    docs="https://docs.discord.com/developers/resources/guild#create-guild-role",
)

CREATE_GUILD_SCHEDULED_EVENT: Final = Route(
    HTTPMethod.POST,
    "/guilds/{guild_id}/scheduled-events",
    docs="https://docs.discord.com/developers/resources/guild-scheduled-event#create-guild-scheduled-event",
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

CREATE_GUILD_TEMPLATE: Final = Route(
    HTTPMethod.POST,
    "/guilds/{guild_id}/templates",
    docs="https://docs.discord.com/developers/resources/guild-template#create-guild-template",
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

CREATE_STAGE_INSTANCE: Final = Route(
    HTTPMethod.POST,
    "/stage-instances",
    docs="https://docs.discord.com/developers/resources/stage-instance#create-stage-instance",
)

CREATE_WEBHOOK: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/webhooks",
    docs="https://docs.discord.com/developers/resources/webhook#create-webhook",
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

DELETE_AUTO_MODERATION_RULE: Final = Route(
    HTTPMethod.DELETE,
    "/guilds/{guild_id}/auto-moderation/rules/{auto_moderation_rule_id}",
    docs="https://docs.discord.com/developers/resources/auto-moderation#delete-auto-moderation-rule",
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

DELETE_GUILD_INTEGRATION: Final = Route(
    HTTPMethod.DELETE,
    "/guilds/{guild_id}/integrations/{integration_id}",
    docs="https://docs.discord.com/developers/resources/guild#delete-guild-integration",
)

DELETE_GUILD_ROLE: Final = Route(
    HTTPMethod.DELETE,
    "/guilds/{guild_id}/roles/{role_id}",
    docs="https://docs.discord.com/developers/resources/guild#delete-guild-role",
)

DELETE_GUILD_SCHEDULED_EVENT: Final = Route(
    HTTPMethod.DELETE,
    "/guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}",
    docs="https://docs.discord.com/developers/resources/guild-scheduled-event#delete-guild-scheduled-event",
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

DELETE_GUILD_TEMPLATE: Final = Route(
    HTTPMethod.DELETE,
    "/guilds/{guild_id}/templates/{template_code}",
    docs="https://docs.discord.com/developers/resources/guild-template#delete-guild-template",
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

DELETE_STAGE_INSTANCE: Final = Route(
    HTTPMethod.DELETE,
    "/stage-instances/{channel_id}",
    docs="https://docs.discord.com/developers/resources/stage-instance#delete-stage-instance",
)

DELETE_USER_REACTION: Final = Route(
    HTTPMethod.DELETE,
    "/channels/{channel_id}/messages/{message_id}/reactions/{emoji_id}/{user_id}",
    docs="https://docs.discord.com/developers/resources/message#delete-user-reaction",
)

DELETE_WEBHOOK: Final = Route(
    HTTPMethod.DELETE,
    "/webhooks/{webhook_id}",
    docs="https://docs.discord.com/developers/resources/webhook#delete-webhook",
)

DELETE_WEBHOOK_MESSAGE: Final = Route(
    HTTPMethod.DELETE,
    "/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}",
    docs="https://docs.discord.com/developers/resources/webhook#delete-webhook-message",
)

DELETE_WEBHOOK_WITH_TOKEN: Final = Route(
    HTTPMethod.DELETE,
    "/webhooks/{webhook_id}/{webhook_token}",
    docs="https://docs.discord.com/developers/resources/webhook#delete-webhook-with-token",
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

EDIT_WEBHOOK_MESSAGE: Final = Route(
    HTTPMethod.PATCH,
    "/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}",
    docs="https://docs.discord.com/developers/resources/webhook#edit-webhook-message",
)

END_POLL: Final = Route(
    HTTPMethod.POST,
    "/channels/{channel_id}/polls/{message_id}/expire",
    docs="https://docs.discord.com/developers/resources/poll#end-poll",
)

EXECUTE_GITHUB_COMPATIBLE_WEBHOOK: Final = Route(
    HTTPMethod.POST,
    "/webhooks/{webhook_id}/{webhook_token}/github",
    docs="https://docs.discord.com/developers/resources/webhook#execute-github-compatible-webhook",
)

EXECUTE_SLACK_COMPATIBLE_WEBHOOK: Final = Route(
    HTTPMethod.POST,
    "/webhooks/{webhook_id}/{webhook_token}/slack",
    docs="https://docs.discord.com/developers/resources/webhook#execute-slack-compatible-webhook",
)

EXECUTE_WEBHOOK: Final = Route(
    HTTPMethod.POST,
    "/webhooks/{webhook_id}/{webhook_token}",
    docs="https://docs.discord.com/developers/resources/webhook#execute-webhook",
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

GET_AUTO_MODERATION_RULE: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/auto-moderation/rules/{auto_moderation_rule_id}",
    docs="https://docs.discord.com/developers/resources/auto-moderation#get-auto-moderation-rule",
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

GET_CHANNEL_WEBHOOKS: Final = Route(
    HTTPMethod.GET,
    "/channels/{channel_id}/webhooks",
    docs="https://docs.discord.com/developers/resources/webhook#get-channel-webhooks",
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

GET_GUILD_AUDIT_LOG: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/audit-logs",
    docs="https://docs.discord.com/developers/resources/audit-log#get-guild-audit-log",
)

GET_GUILD_BAN: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/bans/{user_id}",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-ban",
)

GET_GUILD_BANS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/bans",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-bans",
)

GET_GUILD_CHANNELS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/channels",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-channels",
)

GET_GUILD_EMOJI: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/emojis/{emoji_id}",
    docs="https://docs.discord.com/developers/resources/emoji#get-guild-emoji",
)

GET_GUILD_INTEGRATIONS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/integrations",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-integrations",
)

GET_GUILD_INVITES: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/invites",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-invites",
)

GET_GUILD_MEMBER: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/members/{user_id}",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-member",
)

GET_GUILD_ONBOARDING: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/onboarding",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-onboarding",
)

GET_GUILD_PREVIEW: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/preview",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-preview",
)

GET_GUILD_PRUNE_COUNT: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/prune",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-prune-count",
)

GET_GUILD_ROLE: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/roles/{role_id}",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-role",
)

GET_GUILD_ROLES: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/roles",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-roles",
)

GET_GUILD_ROLE_MEMBER_COUNTS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/roles/member-counts",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-role-member-counts",
)

GET_GUILD_SCHEDULED_EVENT: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}",
    docs="https://docs.discord.com/developers/resources/guild-scheduled-event#get-guild-scheduled-event",
)

GET_GUILD_SCHEDULED_EVENT_USERS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}/users",
    docs="https://docs.discord.com/developers/resources/guild-scheduled-event#get-guild-scheduled-event-users",
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

GET_GUILD_TEMPLATE: Final = Route(
    HTTPMethod.GET,
    "/guilds/templates/{template_code}",
    docs="https://docs.discord.com/developers/resources/guild-template#get-guild-template",
)

GET_GUILD_TEMPLATES: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/templates",
    docs="https://docs.discord.com/developers/resources/guild-template#get-guild-templates",
)

GET_GUILD_VANITY_URL: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/vanity-url",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-vanity-url",
)

GET_GUILD_VOICE_REGIONS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/regions",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-voice-regions",
)

GET_GUILD_WEBHOOKS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/webhooks",
    docs="https://docs.discord.com/developers/resources/webhook#get-guild-webhooks",
)

GET_GUILD_WELCOME_SCREEN: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/welcome-screen",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-welcome-screen",
)

GET_GUILD_WIDGET: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/widget.json",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-widget",
)

GET_GUILD_WIDGET_IMAGE: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/widget.png",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-widget-image",
)

GET_GUILD_WIDGET_SETTINGS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/widget",
    docs="https://docs.discord.com/developers/resources/guild#get-guild-widget-settings",
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

GET_STAGE_INSTANCE: Final = Route(
    HTTPMethod.GET,
    "/stage-instances/{channel_id}",
    docs="https://docs.discord.com/developers/resources/stage-instance#get-stage-instance",
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

GET_WEBHOOK: Final = Route(
    HTTPMethod.GET,
    "/webhooks/{webhook_id}",
    docs="https://docs.discord.com/developers/resources/webhook#get-webhook",
)

GET_WEBHOOK_MESSAGE: Final = Route(
    HTTPMethod.GET,
    "/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}",
    docs="https://docs.discord.com/developers/resources/webhook#get-webhook-message",
)

GET_WEBHOOK_WITH_TOKEN: Final = Route(
    HTTPMethod.GET,
    "/webhooks/{webhook_id}/{webhook_token}",
    docs="https://docs.discord.com/developers/resources/webhook#get-webhook-with-token",
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

LIST_ACTIVE_GUILD_THREADS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/threads/active",
    docs="https://docs.discord.com/developers/resources/guild#list-active-guild-threads",
)

LIST_APPLICATION_EMOJIS: Final = Route(
    HTTPMethod.GET,
    "/applications/{application_id}/emojis",
    docs="https://docs.discord.com/developers/resources/emoji#list-application-emojis",
)

LIST_AUTO_MODERATION_RULES_FOR_GUILD: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/auto-moderation/rules",
    docs="https://docs.discord.com/developers/resources/auto-moderation#list-auto-moderation-rules-for-guild",
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

LIST_GUILD_MEMBERS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/members",
    docs="https://docs.discord.com/developers/resources/guild#list-guild-members",
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

LIST_SCHEDULED_EVENTS_FOR_GUILD: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/scheduled-events",
    docs="https://docs.discord.com/developers/resources/guild-scheduled-event#list-scheduled-events-for-guild",
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

MODIFY_AUTO_MODERATION_RULE: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/auto-moderation/rules/{auto_moderation_rule_id}",
    docs="https://docs.discord.com/developers/resources/auto-moderation#modify-auto-moderation-rule",
)

MODIFY_CHANNEL: Final = Route(
    HTTPMethod.PATCH,
    "/channels/{channel_id}",
    docs="https://docs.discord.com/developers/resources/channel#modify-channel",
)

MODIFY_CURRENT_MEMBER: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/members/@me",
    docs="https://docs.discord.com/developers/resources/guild#modify-current-member",
)

MODIFY_CURRENT_USER: Final = Route(
    HTTPMethod.PATCH,
    "/users/@me",
    docs="https://docs.discord.com/developers/resources/user#modify-current-user",
)

MODIFY_CURRENT_USER_NICK: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/members/@me/nick",
    docs="https://docs.discord.com/developers/resources/guild#modify-current-user-nick",
)

MODIFY_CURRENT_USER_VOICE_STATE: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/voice-states/@me",
    docs="https://docs.discord.com/developers/resources/voice#modify-current-user-voice-state",
)

MODIFY_GUILD: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}",
    docs="https://docs.discord.com/developers/resources/guild#modify-guild",
)

MODIFY_GUILD_CHANNEL_POSITIONS: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/channels",
    docs="https://docs.discord.com/developers/resources/guild#modify-guild-channel-positions",
)

MODIFY_GUILD_EMOJI: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/emojis/{emoji_id}",
    docs="https://docs.discord.com/developers/resources/emoji#modify-guild-emoji",
)

MODIFY_GUILD_INCIDENT_ACTIONS: Final = Route(
    HTTPMethod.PUT,
    "/guilds/{guild_id}/incident-actions",
    docs="https://docs.discord.com/developers/resources/guild#modify-guild-incident-actions",
)

MODIFY_GUILD_MEMBER: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/members/{user_id}",
    docs="https://docs.discord.com/developers/resources/guild#modify-guild-member",
)

MODIFY_GUILD_ONBOARDING: Final = Route(
    HTTPMethod.PUT,
    "/guilds/{guild_id}/onboarding",
    docs="https://docs.discord.com/developers/resources/guild#modify-guild-onboarding",
)

MODIFY_GUILD_ROLE: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/roles/{role_id}",
    docs="https://docs.discord.com/developers/resources/guild#modify-guild-role",
)

MODIFY_GUILD_ROLE_POSITIONS: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/roles",
    docs="https://docs.discord.com/developers/resources/guild#modify-guild-role-positions",
)

MODIFY_GUILD_SCHEDULED_EVENT: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}",
    docs="https://docs.discord.com/developers/resources/guild-scheduled-event#modify-guild-scheduled-event",
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

MODIFY_GUILD_TEMPLATE: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/templates/{template_code}",
    docs="https://docs.discord.com/developers/resources/guild-template#modify-guild-template",
)

MODIFY_GUILD_WELCOME_SCREEN: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/welcome-screen",
    docs="https://docs.discord.com/developers/resources/guild#modify-guild-welcome-screen",
)

MODIFY_GUILD_WIDGET: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/widget",
    docs="https://docs.discord.com/developers/resources/guild#modify-guild-widget",
)

MODIFY_STAGE_INSTANCE: Final = Route(
    HTTPMethod.PATCH,
    "/stage-instances/{channel_id}",
    docs="https://docs.discord.com/developers/resources/stage-instance#modify-stage-instance",
)

MODIFY_USER_VOICE_STATE: Final = Route(
    HTTPMethod.PATCH,
    "/guilds/{guild_id}/voice-states/{user_id}",
    docs="https://docs.discord.com/developers/resources/voice#modify-user-voice-state",
)

MODIFY_WEBHOOK: Final = Route(
    HTTPMethod.PATCH,
    "/webhooks/{webhook_id}",
    docs="https://docs.discord.com/developers/resources/webhook#modify-webhook",
)

MODIFY_WEBHOOK_WITH_TOKEN: Final = Route(
    HTTPMethod.PATCH,
    "/webhooks/{webhook_id}/{webhook_token}",
    docs="https://docs.discord.com/developers/resources/webhook#modify-webhook-with-token",
)

PIN_MESSAGE: Final = Route(
    HTTPMethod.PUT,
    "/channels/{channel_id}/messages/pins/{message_id}",
    docs="https://docs.discord.com/developers/resources/message#pin-message",
)

REMOVE_GUILD_BAN: Final = Route(
    HTTPMethod.DELETE,
    "/guilds/{guild_id}/bans/{user_id}",
    docs="https://docs.discord.com/developers/resources/guild#remove-guild-ban",
)

REMOVE_GUILD_MEMBER: Final = Route(
    HTTPMethod.DELETE,
    "/guilds/{guild_id}/members/{user_id}",
    docs="https://docs.discord.com/developers/resources/guild#remove-guild-member",
)

REMOVE_GUILD_MEMBER_ROLE: Final = Route(
    HTTPMethod.DELETE,
    "/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
    docs="https://docs.discord.com/developers/resources/guild#remove-guild-member-role",
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

SEARCH_GUILD_MEMBERS: Final = Route(
    HTTPMethod.GET,
    "/guilds/{guild_id}/members/search",
    docs="https://docs.discord.com/developers/resources/guild#search-guild-members",
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

SYNC_GUILD_TEMPLATE: Final = Route(
    HTTPMethod.PUT,
    "/guilds/{guild_id}/templates/{template_code}",
    docs="https://docs.discord.com/developers/resources/guild-template#sync-guild-template",
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
    ADD_GUILD_MEMBER,
    ADD_GUILD_MEMBER_ROLE,
    ADD_TARGET_USER,
    ADD_THREAD_MEMBER,
    BEGIN_GUILD_PRUNE,
    BULK_ADD_TARGET_USERS,
    BULK_DELETE_MESSAGES,
    BULK_DELETE_TARGET_USERS,
    BULK_GUILD_BAN,
    BULK_OVERWRITE_GLOBAL_APPLICATION_COMMANDS,
    BULK_OVERWRITE_GUILD_APPLICATION_COMMANDS,
    CREATE_APPLICATION_EMOJI,
    CREATE_AUTO_MODERATION_RULE,
    CREATE_CHANNEL_INVITE,
    CREATE_DM,
    CREATE_FOLLOWUP_MESSAGE,
    CREATE_GLOBAL_APPLICATION_COMMAND,
    CREATE_GROUP_DM,
    CREATE_GUILD_APPLICATION_COMMAND,
    CREATE_GUILD_BAN,
    CREATE_GUILD_CHANNEL,
    CREATE_GUILD_EMOJI,
    CREATE_GUILD_ROLE,
    CREATE_GUILD_SCHEDULED_EVENT,
    CREATE_GUILD_SOUNDBOARD_SOUND,
    CREATE_GUILD_STICKER,
    CREATE_GUILD_TEMPLATE,
    CREATE_INTERACTION_RESPONSE,
    CREATE_MESSAGE,
    CREATE_REACTION,
    CREATE_STAGE_INSTANCE,
    CREATE_WEBHOOK,
    CROSSPOST_MESSAGE,
    DELETE_ALL_REACTIONS,
    DELETE_ALL_REACTIONS_FOR_EMOJI,
    DELETE_APPLICATION_EMOJI,
    DELETE_AUTO_MODERATION_RULE,
    DELETE_CHANNEL,
    DELETE_CHANNEL_PERMISSION,
    DELETE_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
    DELETE_FOLLOWUP_MESSAGE,
    DELETE_GLOBAL_APPLICATION_COMMAND,
    DELETE_GUILD_APPLICATION_COMMAND,
    DELETE_GUILD_EMOJI,
    DELETE_GUILD_INTEGRATION,
    DELETE_GUILD_ROLE,
    DELETE_GUILD_SCHEDULED_EVENT,
    DELETE_GUILD_SOUNDBOARD_SOUND,
    DELETE_GUILD_STICKER,
    DELETE_GUILD_TEMPLATE,
    DELETE_INVITE,
    DELETE_MESSAGE,
    DELETE_ORIGINAL_INTERACTION_RESPONSE,
    DELETE_OWN_REACTION,
    DELETE_STAGE_INSTANCE,
    DELETE_USER_REACTION,
    DELETE_WEBHOOK,
    DELETE_WEBHOOK_MESSAGE,
    DELETE_WEBHOOK_WITH_TOKEN,
    EDIT_APPLICATION_COMMAND_PERMISSIONS,
    EDIT_CHANNEL_PERMISSIONS,
    EDIT_FOLLOWUP_MESSAGE,
    EDIT_GLOBAL_APPLICATION_COMMAND,
    EDIT_GUILD_APPLICATION_COMMAND,
    EDIT_MESSAGE,
    EDIT_ORIGINAL_INTERACTION_RESPONSE,
    EDIT_WEBHOOK_MESSAGE,
    END_POLL,
    EXECUTE_GITHUB_COMPATIBLE_WEBHOOK,
    EXECUTE_SLACK_COMPATIBLE_WEBHOOK,
    EXECUTE_WEBHOOK,
    FOLLOW_ANNOUNCEMENT_CHANNEL,
    GET_ANSWER_VOTERS,
    GET_APPLICATION_COMMAND_PERMISSIONS,
    GET_APPLICATION_EMOJI,
    GET_AUTO_MODERATION_RULE,
    GET_CHANNEL,
    GET_CHANNEL_INVITES,
    GET_CHANNEL_MESSAGE,
    GET_CHANNEL_MESSAGES,
    GET_CHANNEL_PINS,
    GET_CHANNEL_WEBHOOKS,
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
    GET_GUILD_AUDIT_LOG,
    GET_GUILD_BAN,
    GET_GUILD_BANS,
    GET_GUILD_CHANNELS,
    GET_GUILD_EMOJI,
    GET_GUILD_INTEGRATIONS,
    GET_GUILD_INVITES,
    GET_GUILD_MEMBER,
    GET_GUILD_ONBOARDING,
    GET_GUILD_PREVIEW,
    GET_GUILD_PRUNE_COUNT,
    GET_GUILD_ROLE,
    GET_GUILD_ROLES,
    GET_GUILD_ROLE_MEMBER_COUNTS,
    GET_GUILD_SCHEDULED_EVENT,
    GET_GUILD_SCHEDULED_EVENT_USERS,
    GET_GUILD_SOUNDBOARD_SOUND,
    GET_GUILD_STICKER,
    GET_GUILD_TEMPLATE,
    GET_GUILD_TEMPLATES,
    GET_GUILD_VANITY_URL,
    GET_GUILD_VOICE_REGIONS,
    GET_GUILD_WEBHOOKS,
    GET_GUILD_WELCOME_SCREEN,
    GET_GUILD_WIDGET,
    GET_GUILD_WIDGET_IMAGE,
    GET_GUILD_WIDGET_SETTINGS,
    GET_INVITE,
    GET_ORIGINAL_INTERACTION_RESPONSE,
    GET_REACTIONS,
    GET_STAGE_INSTANCE,
    GET_STICKER,
    GET_STICKER_PACK,
    GET_TARGET_USERS,
    GET_TARGET_USERS_JOB_STATUS,
    GET_THREAD_MEMBER,
    GET_USER,
    GET_USER_VOICE_STATE,
    GET_WEBHOOK,
    GET_WEBHOOK_MESSAGE,
    GET_WEBHOOK_WITH_TOKEN,
    GROUP_DM_ADD_RECIPIENT,
    GROUP_DM_REMOVE_RECIPIENT,
    JOIN_THREAD,
    LEAVE_GUILD,
    LEAVE_THREAD,
    LIST_ACTIVE_GUILD_THREADS,
    LIST_APPLICATION_EMOJIS,
    LIST_AUTO_MODERATION_RULES_FOR_GUILD,
    LIST_DEFAULT_SOUNDBOARD_SOUNDS,
    LIST_GUILD_EMOJIS,
    LIST_GUILD_MEMBERS,
    LIST_GUILD_SOUNDBOARD_SOUNDS,
    LIST_GUILD_STICKERS,
    LIST_JOINED_PRIVATE_ARCHIVED_THREADS,
    LIST_PRIVATE_ARCHIVED_THREADS,
    LIST_PUBLIC_ARCHIVED_THREADS,
    LIST_SCHEDULED_EVENTS_FOR_GUILD,
    LIST_STICKER_PACKS,
    LIST_THREAD_MEMBERS,
    LIST_VOICE_REGIONS,
    MODIFY_APPLICATION_EMOJI,
    MODIFY_AUTO_MODERATION_RULE,
    MODIFY_CHANNEL,
    MODIFY_CURRENT_MEMBER,
    MODIFY_CURRENT_USER,
    MODIFY_CURRENT_USER_NICK,
    MODIFY_CURRENT_USER_VOICE_STATE,
    MODIFY_GUILD,
    MODIFY_GUILD_CHANNEL_POSITIONS,
    MODIFY_GUILD_EMOJI,
    MODIFY_GUILD_INCIDENT_ACTIONS,
    MODIFY_GUILD_MEMBER,
    MODIFY_GUILD_ONBOARDING,
    MODIFY_GUILD_ROLE,
    MODIFY_GUILD_ROLE_POSITIONS,
    MODIFY_GUILD_SCHEDULED_EVENT,
    MODIFY_GUILD_SOUNDBOARD_SOUND,
    MODIFY_GUILD_STICKER,
    MODIFY_GUILD_TEMPLATE,
    MODIFY_GUILD_WELCOME_SCREEN,
    MODIFY_GUILD_WIDGET,
    MODIFY_STAGE_INSTANCE,
    MODIFY_USER_VOICE_STATE,
    MODIFY_WEBHOOK,
    MODIFY_WEBHOOK_WITH_TOKEN,
    PIN_MESSAGE,
    REMOVE_GUILD_BAN,
    REMOVE_GUILD_MEMBER,
    REMOVE_GUILD_MEMBER_ROLE,
    REMOVE_TARGET_USER,
    REMOVE_THREAD_MEMBER,
    SEARCH_GUILD_MEMBERS,
    SEARCH_GUILD_MESSAGES,
    SEND_SOUNDBOARD_SOUND,
    SET_VOICE_CHANNEL_STATUS,
    START_THREAD_FROM_MESSAGE,
    START_THREAD_IN_FORUM_OR_MEDIA_CHANNEL,
    START_THREAD_WITHOUT_MESSAGE,
    SYNC_GUILD_TEMPLATE,
    TRIGGER_TYPING_INDICATOR,
    UNPIN_MESSAGE,
    UPDATE_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
    UPDATE_TARGET_USERS,
)
"""Every declared route, for the docs checker and tests."""
