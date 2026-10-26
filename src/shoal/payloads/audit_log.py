"""Audit logs: who changed what in a guild.

Discord: https://docs.discord.com/developers/resources/audit-log
"""

import msgspec
from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.snowflake import Snowflake
from shoal.payloads.application_commands import ApplicationCommand
from shoal.payloads.auto_moderation import AutoModerationRule
from shoal.payloads.base import Payload
from shoal.payloads.channel import Channel
from shoal.payloads.guild import IntegrationAccount
from shoal.payloads.scheduled_event import GuildScheduledEvent
from shoal.payloads.user import User
from shoal.payloads.webhook import Webhook


class AuditLogEvent(DiscordIntEnum):
    """The kind of action an audit log entry records.

    Discord: https://docs.discord.com/developers/resources/audit-log#audit-log-entry-object-audit-log-events
    """

    GUILD_UPDATE = 1
    CHANNEL_CREATE = 10
    CHANNEL_UPDATE = 11
    CHANNEL_DELETE = 12
    CHANNEL_OVERWRITE_CREATE = 13
    CHANNEL_OVERWRITE_UPDATE = 14
    CHANNEL_OVERWRITE_DELETE = 15
    MEMBER_KICK = 20
    MEMBER_PRUNE = 21
    MEMBER_BAN_ADD = 22
    MEMBER_BAN_REMOVE = 23
    MEMBER_UPDATE = 24
    MEMBER_ROLE_UPDATE = 25
    MEMBER_MOVE = 26
    MEMBER_DISCONNECT = 27
    BOT_ADD = 28
    ROLE_CREATE = 30
    ROLE_UPDATE = 31
    ROLE_DELETE = 32
    INVITE_CREATE = 40
    INVITE_UPDATE = 41
    INVITE_DELETE = 42
    WEBHOOK_CREATE = 50
    WEBHOOK_UPDATE = 51
    WEBHOOK_DELETE = 52
    EMOJI_CREATE = 60
    EMOJI_UPDATE = 61
    EMOJI_DELETE = 62
    MESSAGE_DELETE = 72
    MESSAGE_BULK_DELETE = 73
    MESSAGE_PIN = 74
    MESSAGE_UNPIN = 75
    INTEGRATION_CREATE = 80
    INTEGRATION_UPDATE = 81
    INTEGRATION_DELETE = 82
    STAGE_INSTANCE_CREATE = 83
    STAGE_INSTANCE_UPDATE = 84
    STAGE_INSTANCE_DELETE = 85
    STICKER_CREATE = 90
    STICKER_UPDATE = 91
    STICKER_DELETE = 92
    GUILD_SCHEDULED_EVENT_CREATE = 100
    GUILD_SCHEDULED_EVENT_UPDATE = 101
    GUILD_SCHEDULED_EVENT_DELETE = 102
    THREAD_CREATE = 110
    THREAD_UPDATE = 111
    THREAD_DELETE = 112
    APPLICATION_COMMAND_PERMISSION_UPDATE = 121
    SOUNDBOARD_SOUND_CREATE = 130
    SOUNDBOARD_SOUND_UPDATE = 131
    SOUNDBOARD_SOUND_DELETE = 132
    AUTO_MODERATION_RULE_CREATE = 140
    AUTO_MODERATION_RULE_UPDATE = 141
    AUTO_MODERATION_RULE_DELETE = 142
    AUTO_MODERATION_BLOCK_MESSAGE = 143
    AUTO_MODERATION_FLAG_TO_CHANNEL = 144
    AUTO_MODERATION_USER_COMMUNICATION_DISABLED = 145
    AUTO_MODERATION_QUARANTINE_USER = 146
    CREATOR_MONETIZATION_REQUEST_CREATED = 150
    CREATOR_MONETIZATION_TERMS_ACCEPTED = 151
    ONBOARDING_PROMPT_CREATE = 163
    ONBOARDING_PROMPT_UPDATE = 164
    ONBOARDING_PROMPT_DELETE = 165
    ONBOARDING_CREATE = 166
    ONBOARDING_UPDATE = 167
    HOME_SETTINGS_CREATE = 190
    HOME_SETTINGS_UPDATE = 191
    VOICE_CHANNEL_STATUS_CREATE = 192
    VOICE_CHANNEL_STATUS_DELETE = 193


class AuditLogChange(Payload):
    """One changed field of an audit log entry.

    A missing `new_value` means the field was reset or cleared; a missing `old_value` means it was
    `None` before.

    The values have the changed field's type, so they are kept as raw JSON: decode them with
    `shoal.core.codec.decode_json` into the type that `key` names. Discord lists exceptions (role
    changes use `$add` and `$remove`, webhooks `avatar_hash`, command permissions an ID as `key`).

    Discord: https://docs.discord.com/developers/resources/audit-log#audit-log-change-object
    """

    new_value: msgspec.Raw | UnsetType = UNSET
    old_value: msgspec.Raw | UnsetType = UNSET
    key: str


class OptionalAuditEntryInfo(Payload):
    """Details some kinds of entry carry; which fields are set depends on `action_type`.

    Discord sends the counts as strings.

    Discord: https://docs.discord.com/developers/resources/audit-log#audit-log-entry-object-optional-audit-entry-info
    """

    application_id: Snowflake | UnsetType = UNSET
    auto_moderation_rule_name: str | UnsetType = UNSET
    auto_moderation_rule_trigger_type: str | UnsetType = UNSET
    channel_id: Snowflake | UnsetType = UNSET
    count: str | UnsetType = UNSET
    delete_member_days: str | UnsetType = UNSET
    id: Snowflake | UnsetType = UNSET
    members_removed: str | UnsetType = UNSET
    message_id: Snowflake | UnsetType = UNSET
    role_name: str | UnsetType = UNSET
    type: str | UnsetType = UNSET
    """`"0"` for a role overwrite, `"1"` for a member overwrite."""
    integration_type: str | UnsetType = UNSET
    status: str | UnsetType = UNSET


class AuditLogEntry(Payload):
    """One administrative action.

    Discord: https://docs.discord.com/developers/resources/audit-log#audit-log-entry-object
    """

    target_id: str | None
    """The affected entity's ID; for command permission updates, the command or app ID."""
    changes: list[AuditLogChange] | UnsetType = UNSET
    user_id: Snowflake | None
    """The user or app that acted."""
    id: Snowflake
    action_type: AuditLogEvent
    options: OptionalAuditEntryInfo | UnsetType = UNSET
    reason: str | UnsetType = UNSET


class AuditLogIntegration(Payload):
    """An integration referenced in an audit log: a partial integration.

    Discord: https://docs.discord.com/developers/resources/audit-log#audit-log-object-example-partial-integration-object
    """

    id: Snowflake
    name: str
    type: str
    account: IntegrationAccount
    application_id: Snowflake | UnsetType = UNSET


class AuditLog(Payload):
    """A page of a guild's audit log, and the objects its entries refer to.

    Discord: https://docs.discord.com/developers/resources/audit-log#audit-log-object
    """

    application_commands: list[ApplicationCommand]
    audit_log_entries: list[AuditLogEntry]
    """Newest first with `before`, oldest first with `after`."""
    auto_moderation_rules: list[AutoModerationRule]
    guild_scheduled_events: list[GuildScheduledEvent]
    integrations: list[AuditLogIntegration]
    threads: list[Channel]
    users: list[User]
    webhooks: list[Webhook]


class GetGuildAuditLogParams(Payload):
    """Query of Get Guild Audit Log.

    Without `before` or `after`, the newest entries come first; `after=0` gives the oldest.

    Discord: https://docs.discord.com/developers/resources/audit-log#get-guild-audit-log-query-string-params
    """

    user_id: Snowflake | UnsetType = UNSET
    action_type: AuditLogEvent | UnsetType = UNSET
    before: Snowflake | UnsetType = UNSET
    after: Snowflake | UnsetType = UNSET
    limit: int | UnsetType = UNSET
    """1 to 100; Discord's default is 50."""
