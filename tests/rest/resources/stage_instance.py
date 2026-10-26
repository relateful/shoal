from shoal.core.snowflake import Snowflake
from shoal.payloads import CreateStageInstanceParams, EditStageInstanceParams
from tests.support.json_payloads import STAGE_INSTANCE
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

CASES = [
    EndpointCase(
        name="create",
        call=lambda client: client.stage_instances.create(
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
        response=STAGE_INSTANCE,
        reason="town hall",
    ),
    EndpointCase(
        name="get",
        call=lambda client: client.stage_instances.get(733488538393510049),
        method="GET",
        path="/stage-instances/733488538393510049",
        response=STAGE_INSTANCE,
    ),
    EndpointCase(
        name="modify",
        call=lambda client: client.stage_instances.edit(
            733488538393510049, EditStageInstanceParams(topic="Q&A")
        ),
        method="PATCH",
        path="/stage-instances/733488538393510049",
        body={"topic": "Q&A"},
        response=STAGE_INSTANCE,
    ),
    EndpointCase(
        name="delete",
        call=lambda client: client.stage_instances.delete(733488538393510049),
        method="DELETE",
        path="/stage-instances/733488538393510049",
    ),
]


@endpoint_cases(CASES)
async def test_stage_instance_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
