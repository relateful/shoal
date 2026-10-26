import msgspec

from shoal.core.codec import decode_json
from shoal.core.snowflake import Snowflake
from shoal.payloads import AuditLog, AuditLogEvent, GetGuildAuditLogParams
from tests.support.json_payloads import USER
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

AUDIT_LOG: dict[str, object] = {
    "application_commands": [],
    "audit_log_entries": [
        {
            "target_id": "3",
            "changes": [
                {"new_value": "general-chat", "old_value": "general", "key": "name"},
                {"old_value": [{"id": "5", "name": "mods"}], "key": "$remove"},
            ],
            "user_id": "1",
            "id": "90",
            "action_type": 11,
            "reason": "tidy up",
        },
        {
            "target_id": "4",
            "user_id": "1",
            "id": "91",
            "action_type": 21,
            "options": {"delete_member_days": "7", "members_removed": "12"},
        },
    ],
    "auto_moderation_rules": [],
    "guild_scheduled_events": [],
    "integrations": [
        {
            "id": "33590653072239123",
            "name": "A Name",
            "type": "twitch",
            "account": {"id": "1234567", "name": "twitchusername"},
            "application_id": "94651234501213162",
        }
    ],
    "threads": [],
    "users": [USER],
    "webhooks": [],
}

CASES = [
    EndpointCase(
        name="get audit log",
        call=lambda client: client.get_guild_audit_log(
            2,
            GetGuildAuditLogParams(action_type=AuditLogEvent.CHANNEL_UPDATE, before=Snowflake(100), limit=10),
        ),
        method="GET",
        path="/guilds/2/audit-logs?action_type=11&before=100&limit=10",
        response=AUDIT_LOG,
    ),
]


@endpoint_cases(CASES)
async def test_audit_log_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)


def test_change_values_decode_into_the_type_their_key_names() -> None:
    log = decode_json(msgspec.json.encode(AUDIT_LOG), AuditLog)
    rename, removal = log.audit_log_entries[0].changes or []
    assert isinstance(rename.new_value, msgspec.Raw)
    assert decode_json(rename.new_value, str) == "general-chat"
    assert removal.new_value is msgspec.UNSET
