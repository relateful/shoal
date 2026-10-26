from datetime import UTC, datetime

from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    CreateGuildScheduledEventParams,
    GetGuildScheduledEventUsersParams,
    ModifyGuildScheduledEventParams,
    RecurrenceRule,
    RecurrenceRuleFrequency,
    RecurrenceRuleWeekday,
    ScheduledEventEntityMetadata,
    ScheduledEventEntityType,
    ScheduledEventPrivacyLevel,
    ScheduledEventStatus,
)
from tests.support.json_payloads import MEMBER, USER
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

EVENT: dict[str, object] = {
    "id": "40",
    "guild_id": "2",
    "channel_id": None,
    "creator_id": "1",
    "name": "Meetup",
    "description": "Bring snacks",
    "scheduled_start_time": "2026-02-01T18:00:00+00:00",
    "scheduled_end_time": "2026-02-01T20:00:00+00:00",
    "privacy_level": 2,
    "status": 1,
    "entity_type": 3,
    "entity_id": None,
    "entity_metadata": {"location": "Town hall"},
    "creator": USER,
    "user_count": 12,
    "image": None,
    "recurrence_rule": {
        "start": "2026-02-01T18:00:00+00:00",
        "end": None,
        "frequency": 2,
        "interval": 1,
        "by_weekday": [6],
        "by_n_weekday": None,
        "by_month": None,
        "by_month_day": None,
        "by_year_day": None,
        "count": None,
    },
}
EVENTS = "/guilds/2/scheduled-events"

CASES = [
    EndpointCase(
        name="list",
        call=lambda client: client.list_scheduled_events_for_guild(2, with_user_count=True),
        method="GET",
        path=f"{EVENTS}?with_user_count=true",
        response=[EVENT],
    ),
    EndpointCase(
        name="create",
        call=lambda client: client.create_guild_scheduled_event(
            2,
            CreateGuildScheduledEventParams(
                entity_metadata=ScheduledEventEntityMetadata(location="Town hall"),
                name="Meetup",
                privacy_level=ScheduledEventPrivacyLevel.GUILD_ONLY,
                scheduled_start_time=datetime(2026, 2, 1, 18, tzinfo=UTC),
                scheduled_end_time=datetime(2026, 2, 1, 20, tzinfo=UTC),
                entity_type=ScheduledEventEntityType.EXTERNAL,
                recurrence_rule=RecurrenceRule(
                    start=datetime(2026, 2, 1, 18, tzinfo=UTC),
                    frequency=RecurrenceRuleFrequency.WEEKLY,
                    interval=1,
                    by_weekday=[RecurrenceRuleWeekday.SUNDAY],
                ),
            ),
            reason="community night",
        ),
        method="POST",
        path=EVENTS,
        body={
            "entity_metadata": {"location": "Town hall"},
            "name": "Meetup",
            "privacy_level": 2,
            "scheduled_start_time": "2026-02-01T18:00:00Z",
            "scheduled_end_time": "2026-02-01T20:00:00Z",
            "entity_type": 3,
            "recurrence_rule": {
                "start": "2026-02-01T18:00:00Z",
                "frequency": 2,
                "interval": 1,
                "by_weekday": [6],
            },
        },
        response=EVENT,
        reason="community night",
    ),
    EndpointCase(
        name="get",
        call=lambda client: client.get_guild_scheduled_event(2, 40),
        method="GET",
        path=f"{EVENTS}/40",
        response=EVENT,
    ),
    EndpointCase(
        name="start",
        call=lambda client: client.modify_guild_scheduled_event(
            2, 40, ModifyGuildScheduledEventParams(status=ScheduledEventStatus.ACTIVE, recurrence_rule=None)
        ),
        method="PATCH",
        path=f"{EVENTS}/40",
        body={"status": 2, "recurrence_rule": None},
        response=EVENT,
    ),
    EndpointCase(
        name="delete",
        call=lambda client: client.delete_guild_scheduled_event(2, 40),
        method="DELETE",
        path=f"{EVENTS}/40",
    ),
    EndpointCase(
        name="users",
        call=lambda client: client.get_guild_scheduled_event_users(
            2, 40, GetGuildScheduledEventUsersParams(with_member=True, after=Snowflake(1))
        ),
        method="GET",
        path=f"{EVENTS}/40/users?with_member=true&after=1",
        response=[{"guild_scheduled_event_id": "40", "user": USER, "member": MEMBER}],
    ),
]


@endpoint_cases(CASES)
async def test_scheduled_event_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
