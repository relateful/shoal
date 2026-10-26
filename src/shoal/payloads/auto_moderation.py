"""Auto Moderation rules. Every Auto Moderation endpoint needs Manage Guild.

Discord: https://docs.discord.com/developers/resources/auto-moderation
"""

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload


class AutoModerationTriggerType(DiscordIntEnum):
    """What a rule checks. Each type has a limit per guild: 6 keyword rules, 1 of each other type.

    Discord: https://docs.discord.com/developers/resources/auto-moderation#auto-moderation-rule-object-trigger-types
    """

    KEYWORD = 1
    SPAM = 3
    KEYWORD_PRESET = 4
    MENTION_SPAM = 5
    MEMBER_PROFILE = 6


class AutoModerationKeywordPresetType(DiscordIntEnum):
    """A word list Discord maintains.

    Discord: https://docs.discord.com/developers/resources/auto-moderation#auto-moderation-rule-object-keyword-preset-types
    """

    PROFANITY = 1
    SEXUAL_CONTENT = 2
    SLURS = 3


class AutoModerationEventType(DiscordIntEnum):
    """When a rule is checked.

    Discord: https://docs.discord.com/developers/resources/auto-moderation#auto-moderation-rule-object-event-types
    """

    MESSAGE_SEND = 1
    """A member sends or edits a message."""
    MEMBER_UPDATE = 2
    """A member edits their profile."""


class AutoModerationTriggerMetadata(Payload):
    """What a rule matches; which fields apply depends on the trigger type.

    Keywords and allow-list entries can start or end with `*` to match within words; matching is
    case-insensitive. Regex patterns are Rust-flavored.

    Discord: https://docs.discord.com/developers/resources/auto-moderation#auto-moderation-rule-object-trigger-metadata
    """

    keyword_filter: list[str] | UnsetType = UNSET
    """`KEYWORD` and `MEMBER_PROFILE`: up to 1000, each up to 60 characters."""
    regex_patterns: list[str] | UnsetType = UNSET
    """`KEYWORD` and `MEMBER_PROFILE`: up to 10, each up to 260 characters."""
    presets: list[AutoModerationKeywordPresetType] | UnsetType = UNSET
    """`KEYWORD_PRESET` only."""
    allow_list: list[str] | UnsetType = UNSET
    """Exceptions: up to 100 (or 1000 for `KEYWORD_PRESET`), each up to 60 characters."""
    mention_total_limit: int | UnsetType = UNSET
    """`MENTION_SPAM`: unique role and user mentions allowed per message, up to 50."""
    mention_raid_protection_enabled: bool | UnsetType = UNSET
    """`MENTION_SPAM` only."""


class AutoModerationActionType(DiscordIntEnum):
    """What a rule does when it matches.

    Discord: https://docs.discord.com/developers/resources/auto-moderation#auto-moderation-action-object-action-types
    """

    BLOCK_MESSAGE = 1
    SEND_ALERT_MESSAGE = 2
    """Log the content to a channel."""
    TIMEOUT = 3
    """Keyword and mention spam rules only; needs Moderate Members."""
    BLOCK_MEMBER_INTERACTION = 4


class AutoModerationActionMetadata(Payload):
    """Details of an action; which fields apply depends on the action type.

    Discord: https://docs.discord.com/developers/resources/auto-moderation#auto-moderation-action-object-action-metadata
    """

    channel_id: Snowflake | UnsetType = UNSET
    """`SEND_ALERT_MESSAGE`: where to log the content."""
    duration_seconds: int | UnsetType = UNSET
    """`TIMEOUT`: up to 2419200 (4 weeks)."""
    custom_message: str | UnsetType | None = UNSET
    """`BLOCK_MESSAGE`: shown to the member, up to 150 characters."""


class AutoModerationAction(Payload):
    """An action a rule takes.

    Discord: https://docs.discord.com/developers/resources/auto-moderation#auto-moderation-action-object
    """

    type: AutoModerationActionType
    metadata: AutoModerationActionMetadata | UnsetType = UNSET


class AutoModerationRule(Payload):
    """An Auto Moderation rule.

    Discord: https://docs.discord.com/developers/resources/auto-moderation#auto-moderation-rule-object
    """

    id: Snowflake
    guild_id: Snowflake
    name: str
    creator_id: Snowflake
    event_type: AutoModerationEventType
    trigger_type: AutoModerationTriggerType
    trigger_metadata: AutoModerationTriggerMetadata
    actions: list[AutoModerationAction]
    enabled: bool
    exempt_roles: list[Snowflake]
    """Up to 20."""
    exempt_channels: list[Snowflake]
    """Up to 50."""


class CreateAutoModerationRuleParams(Payload):
    """JSON body of Create Auto Moderation Rule.

    Discord: https://docs.discord.com/developers/resources/auto-moderation#create-auto-moderation-rule-json-params
    """

    name: str
    event_type: AutoModerationEventType
    trigger_type: AutoModerationTriggerType
    trigger_metadata: AutoModerationTriggerMetadata | UnsetType = UNSET
    actions: list[AutoModerationAction]
    enabled: bool | UnsetType = UNSET
    """Discord's default is `False`."""
    exempt_roles: list[Snowflake] | UnsetType = UNSET
    exempt_channels: list[Snowflake] | UnsetType = UNSET


class ModifyAutoModerationRuleParams(Payload):
    """JSON body of Modify Auto Moderation Rule. The trigger type cannot change.

    Discord: https://docs.discord.com/developers/resources/auto-moderation#modify-auto-moderation-rule-json-params
    """

    name: str | UnsetType = UNSET
    event_type: AutoModerationEventType | UnsetType = UNSET
    trigger_metadata: AutoModerationTriggerMetadata | UnsetType = UNSET
    actions: list[AutoModerationAction] | UnsetType = UNSET
    enabled: bool | UnsetType = UNSET
    exempt_roles: list[Snowflake] | UnsetType = UNSET
    exempt_channels: list[Snowflake] | UnsetType = UNSET
