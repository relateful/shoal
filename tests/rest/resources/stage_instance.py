from shoal.core.snowflake import Snowflake
from shoal.payloads import CreateStageInstanceParams, ModifyStageInstanceParams
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

STAGE: dict[str, object] = {
    "id": "840647391636226060",
    "guild_id": "197038439483310086",
    "channel_id": "733488538393510049",
    "topic": "Testing Testing, 123",
    "privacy_level": 1,
    "discoverable_disabled": False,
    "guild_scheduled_event_id": "947656305244532806",
}
"""Discord's example."""

CASES = [
    EndpointCase(
        name="create",
        call=lambda client: client.create_stage_instance(
            CreateStageInstanceParams(
                channel_id=Snowflake(733488538393510049),
                topic="Testing Testing, 123",
                send_start_notification=True,
            ),
            reason="town hall",
        ),
        method="POST",
        path="/stage-instances",
        body={
            "channel_id": "733488538393510049",
            "topic": "Testing Testing, 123",
            "send_start_notification": True,
        },
        response=STAGE,
        reason="town hall",
    ),
    EndpointCase(
        name="get",
        call=lambda client: client.get_stage_instance(733488538393510049),
        method="GET",
        path="/stage-instances/733488538393510049",
        response=STAGE,
    ),
    EndpointCase(
        name="modify",
        call=lambda client: client.modify_stage_instance(
            733488538393510049, ModifyStageInstanceParams(topic="Q&A")
        ),
        method="PATCH",
        path="/stage-instances/733488538393510049",
        body={"topic": "Q&A"},
        response=STAGE,
    ),
    EndpointCase(
        name="delete",
        call=lambda client: client.delete_stage_instance(733488538393510049),
        method="DELETE",
        path="/stage-instances/733488538393510049",
    ),
]


@endpoint_cases(CASES)
async def test_stage_instance_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
