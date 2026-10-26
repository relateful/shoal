from datetime import UTC, datetime

from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    CreateScheduledEventParams,
    EditScheduledEventParams,
    ListScheduledEventUsersParams,
    RecurrenceRule,
    RecurrenceRuleFrequency,
    RecurrenceRuleWeekday,
    ScheduledEventEntityMetadata,
    ScheduledEventEntityType,
    ScheduledEventPrivacyLevel,
    ScheduledEventStatus,
)
from tests.support.json_payloads import MEMBER, SCHEDULED_EVENT, USER
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

EVENTS = "/guilds/2/scheduled-events"

CASES = [
    EndpointCase(
        name="list",
        call=lambda client: client.scheduled_events.list(2, with_user_count=True),
        method="GET",
        path=f"{EVENTS}?with_user_count=true",
        response=[SCHEDULED_EVENT],
    ),
    EndpointCase(
        name="create",
        call=lambda client: client.scheduled_events.create(
            2,
            CreateScheduledEventParams(
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
        response=SCHEDULED_EVENT,
        reason="community night",
    ),
    EndpointCase(
        name="get",
        call=lambda client: client.scheduled_events.get(2, 40),
        method="GET",
        path=f"{EVENTS}/40",
        response=SCHEDULED_EVENT,
    ),
    EndpointCase(
        name="start",
        call=lambda client: client.scheduled_events.edit(
            2, 40, EditScheduledEventParams(status=ScheduledEventStatus.ACTIVE, recurrence_rule=None)
        ),
        method="PATCH",
        path=f"{EVENTS}/40",
        body={"status": 2, "recurrence_rule": None},
        response=SCHEDULED_EVENT,
    ),
    EndpointCase(
        name="delete",
        call=lambda client: client.scheduled_events.delete(2, 40),
        method="DELETE",
        path=f"{EVENTS}/40",
    ),
    EndpointCase(
        name="users",
        call=lambda client: client.scheduled_events.list_users(
            2, 40, ListScheduledEventUsersParams(with_member=True, after=Snowflake(1))
        ),
        method="GET",
        path=f"{EVENTS}/40/users?with_member=true&after=1",
        response=[{"guild_scheduled_event_id": "40", "user": USER, "member": MEMBER}],
    ),
]


@endpoint_cases(CASES)
async def test_scheduled_event_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
