from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    AutoModerationAction,
    AutoModerationActionMetadata,
    AutoModerationActionType,
    AutoModerationEventType,
    AutoModerationTriggerMetadata,
    AutoModerationTriggerType,
    CreateAutoModerationRuleParams,
    EditAutoModerationRuleParams,
)
from tests.support.json_payloads import AUTOMOD_RULE
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

RULES = "/guilds/613425648685547541/auto-moderation/rules"

CASES = [
    EndpointCase(
        name="list",
        call=lambda client: client.automod.list(613425648685547541),
        method="GET",
        path=RULES,
        response=[AUTOMOD_RULE],
    ),
    EndpointCase(
        name="get",
        call=lambda client: client.automod.get(613425648685547541, 969707018069872670),
        method="GET",
        path=f"{RULES}/969707018069872670",
        response=AUTOMOD_RULE,
    ),
    EndpointCase(
        name="create",
        call=lambda client: client.automod.create(
            613425648685547541,
            CreateAutoModerationRuleParams(
                name="No invites",
                event_type=AutoModerationEventType.MESSAGE_SEND,
                trigger_type=AutoModerationTriggerType.KEYWORD,
                trigger_metadata=AutoModerationTriggerMetadata(keyword_filter=["discord.gg*"]),
                actions=[
                    AutoModerationAction(type=AutoModerationActionType.BLOCK_MESSAGE),
                    AutoModerationAction(
                        type=AutoModerationActionType.SEND_ALERT_MESSAGE,
                        metadata=AutoModerationActionMetadata(channel_id=Snowflake(123456789123456789)),
                    ),
                ],
                enabled=True,
            ),
            reason="spam wave",
        ),
        method="POST",
        path=RULES,
        body={
            "name": "No invites",
            "event_type": 1,
            "trigger_type": 1,
            "trigger_metadata": {"keyword_filter": ["discord.gg*"]},
            "actions": [{"type": 1}, {"type": 2, "metadata": {"channel_id": "123456789123456789"}}],
            "enabled": True,
        },
        response=AUTOMOD_RULE,
        reason="spam wave",
    ),
    EndpointCase(
        name="modify",
        call=lambda client: client.automod.edit(
            613425648685547541, 969707018069872670, EditAutoModerationRuleParams(enabled=False)
        ),
        method="PATCH",
        path=f"{RULES}/969707018069872670",
        body={"enabled": False},
        response=AUTOMOD_RULE,
    ),
    EndpointCase(
        name="delete",
        call=lambda client: client.automod.delete(613425648685547541, 969707018069872670),
        method="DELETE",
        path=f"{RULES}/969707018069872670",
    ),
]


@endpoint_cases(CASES)
async def test_auto_moderation_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
