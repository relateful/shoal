from tests.support.json_payloads import USER
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

CASES = [
    EndpointCase(
        name="get current user",
        call=lambda client: client.get_current_user(),
        method="GET",
        path="/users/@me",
        response=USER,
    ),
    EndpointCase(
        name="get user",
        call=lambda client: client.get_user(1),
        method="GET",
        path="/users/1",
        response=USER,
    ),
]


@endpoint_cases(CASES)
async def test_user_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
