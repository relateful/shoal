from tests.support.json_payloads import GUILD, MEMBER
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

CASES = [
    EndpointCase(
        name="get guild",
        call=lambda client: client.get_guild(2),
        method="GET",
        path="/guilds/2?with_counts=false",
        response=GUILD,
    ),
    EndpointCase(
        name="get guild with counts",
        call=lambda client: client.get_guild(2, with_counts=True),
        method="GET",
        path="/guilds/2?with_counts=true",
        response=GUILD,
    ),
    EndpointCase(
        name="get guild member",
        call=lambda client: client.get_guild_member(2, 1),
        method="GET",
        path="/guilds/2/members/1",
        response=MEMBER,
    ),
]


@endpoint_cases(CASES)
async def test_guild_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
