"""Scheduled events in guilds.

Discord: https://docs.discord.com/developers/resources/guild-scheduled-event
"""

from datetime import datetime

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.snowflake import Snowflake
from shoal.payloads.api import ImageData
from shoal.payloads.base import Payload
from shoal.payloads.guild import GuildMember
from shoal.payloads.user import User


class ScheduledEventPrivacyLevel(DiscordIntEnum):
    """Who can see a scheduled event.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-object-guild-scheduled-event-privacy-level
    """

    GUILD_ONLY = 2


class ScheduledEventEntityType(DiscordIntEnum):
    """Where a scheduled event happens.

    `STAGE_INSTANCE` and `VOICE` need a `channel_id` and no `entity_metadata`; `EXTERNAL` needs
    `entity_metadata.location`, a `scheduled_end_time` and no channel.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-object-guild-scheduled-event-entity-types
    """

    STAGE_INSTANCE = 1
    VOICE = 2
    EXTERNAL = 3


class ScheduledEventStatus(DiscordIntEnum):
    """Where a scheduled event is in its life.

    `SCHEDULED` can become `ACTIVE` or `CANCELED`, and `ACTIVE` can become `COMPLETED`; the last two
    are final.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-object-guild-scheduled-event-status
    """

    SCHEDULED = 1
    ACTIVE = 2
    COMPLETED = 3
    CANCELED = 4


class ScheduledEventEntityMetadata(Payload):
    """Extra details of an external event.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-object-guild-scheduled-event-entity-metadata
    """

    location: str | UnsetType = UNSET
    """1 to 100 characters; required for `EXTERNAL` events."""


class RecurrenceRuleFrequency(DiscordIntEnum):
    """How often a recurring event happens.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-recurrence-rule-object-guild-scheduled-event-recurrence-rule-frequency
    """

    YEARLY = 0
    MONTHLY = 1
    WEEKLY = 2
    DAILY = 3


class RecurrenceRuleWeekday(DiscordIntEnum):
    """A day of the week in a recurrence rule.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-recurrence-rule-object-guild-scheduled-event-recurrence-rule-weekday
    """

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class RecurrenceRuleMonth(DiscordIntEnum):
    """A month in a recurrence rule.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-recurrence-rule-object-guild-scheduled-event-recurrence-rule-month
    """

    JANUARY = 1
    FEBRUARY = 2
    MARCH = 3
    APRIL = 4
    MAY = 5
    JUNE = 6
    JULY = 7
    AUGUST = 8
    SEPTEMBER = 9
    OCTOBER = 10
    NOVEMBER = 11
    DECEMBER = 12


class RecurrenceRuleNWeekday(Payload):
    """A weekday in a given week of the month, such as the fourth Wednesday.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-recurrence-rule-object-guild-scheduled-event-recurrence-rule-nweekday-structure
    """

    n: int
    """The week of the month, 1 to 5."""
    day: RecurrenceRuleWeekday


class RecurrenceRule(Payload):
    """How a scheduled event repeats; a restricted form of the iCalendar RRULE.

    `end`, `count` and `by_year_day` cannot be set by apps, and Discord restricts which
    combinations work (see its "System limitations"): for example `by_weekday`, `by_n_weekday` and
    `by_month` with `by_month_day` are mutually exclusive.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-recurrence-rule-object
    """

    start: datetime
    end: datetime | UnsetType | None = UNSET
    frequency: RecurrenceRuleFrequency
    interval: int
    """Units of `frequency` between occurrences; only weekly events may use 2."""
    by_weekday: list[RecurrenceRuleWeekday] | UnsetType | None = UNSET
    by_n_weekday: list[RecurrenceRuleNWeekday] | UnsetType | None = UNSET
    by_month: list[RecurrenceRuleMonth] | UnsetType | None = UNSET
    by_month_day: list[int] | UnsetType | None = UNSET
    by_year_day: list[int] | UnsetType | None = UNSET
    count: int | UnsetType | None = UNSET


class GuildScheduledEvent(Payload):
    """A scheduled event in a guild.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-object
    """

    id: Snowflake
    guild_id: Snowflake
    channel_id: Snowflake | None
    """`None` for `EXTERNAL` events."""
    creator_id: Snowflake | UnsetType | None = UNSET
    """`None` for events created before October 25, 2021."""
    name: str
    description: str | UnsetType | None = UNSET
    scheduled_start_time: datetime
    scheduled_end_time: datetime | None
    privacy_level: ScheduledEventPrivacyLevel
    status: ScheduledEventStatus
    entity_type: ScheduledEventEntityType
    entity_id: Snowflake | None
    entity_metadata: ScheduledEventEntityMetadata | None
    creator: User | UnsetType = UNSET
    user_count: int | UnsetType = UNSET
    """Only with `with_user_count`."""
    image: str | UnsetType | None = UNSET
    """The cover image hash."""
    recurrence_rule: RecurrenceRule | None


class GuildScheduledEventUser(Payload):
    """A user who subscribed to a scheduled event.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-user-object
    """

    guild_scheduled_event_id: Snowflake
    user: User
    member: GuildMember | UnsetType = UNSET
    """Only with `with_member`, and only when the user is still in the guild."""


class CreateGuildScheduledEventParams(Payload):
    """JSON body of Create Guild Scheduled Event. A guild can have 100 scheduled or active events.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#create-guild-scheduled-event-json-params
    """

    channel_id: Snowflake | UnsetType = UNSET
    """Required unless the event is `EXTERNAL`."""
    entity_metadata: ScheduledEventEntityMetadata | UnsetType = UNSET
    """Required for `EXTERNAL` events."""
    name: str
    privacy_level: ScheduledEventPrivacyLevel
    scheduled_start_time: datetime
    scheduled_end_time: datetime | UnsetType = UNSET
    """Required for `EXTERNAL` events."""
    description: str | UnsetType = UNSET
    entity_type: ScheduledEventEntityType
    image: ImageData | UnsetType = UNSET
    recurrence_rule: RecurrenceRule | UnsetType = UNSET


class ModifyGuildScheduledEventParams(Payload):
    """JSON body of Modify Guild Scheduled Event; set `status` to start or end an event.

    Changing to `EXTERNAL` needs `channel_id=None`, `entity_metadata.location` and
    `scheduled_end_time`.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#modify-guild-scheduled-event-json-params
    """

    channel_id: Snowflake | UnsetType | None = UNSET
    entity_metadata: ScheduledEventEntityMetadata | UnsetType | None = UNSET
    name: str | UnsetType = UNSET
    privacy_level: ScheduledEventPrivacyLevel | UnsetType = UNSET
    scheduled_start_time: datetime | UnsetType = UNSET
    scheduled_end_time: datetime | UnsetType = UNSET
    description: str | UnsetType | None = UNSET
    entity_type: ScheduledEventEntityType | UnsetType = UNSET
    status: ScheduledEventStatus | UnsetType = UNSET
    image: ImageData | UnsetType = UNSET
    recurrence_rule: RecurrenceRule | UnsetType | None = UNSET


class GetGuildScheduledEventUsersParams(Payload):
    """Query of Get Guild Scheduled Event Users. Users come in ascending ID order; `before` wins.

    Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#get-guild-scheduled-event-users-query-string-params
    """

    limit: int | UnsetType = UNSET
    """Up to 100, Discord's default."""
    with_member: bool | UnsetType = UNSET
    before: Snowflake | UnsetType = UNSET
    after: Snowflake | UnsetType = UNSET
