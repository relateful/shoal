from tests.support.json_payloads import CHANNEL
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

CASES = [
    EndpointCase(
        name="get channel",
        call=lambda client: client.get_channel(3),
        method="GET",
        path="/channels/3",
        response=CHANNEL,
    ),
]


@endpoint_cases(CASES)
async def test_channel_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
