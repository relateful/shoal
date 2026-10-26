from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

CASES = [
    EndpointCase(
        name="get gateway",
        call=lambda client: client.gateway.get(),
        method="GET",
        path="/gateway",
        response={"url": "wss://gateway.discord.gg"},
    ),
    EndpointCase(
        name="get gateway bot",
        call=lambda client: client.gateway.get_bot(),
        method="GET",
        path="/gateway/bot",
        response={
            "url": "wss://gateway.discord.gg",
            "shards": 9,
            "session_start_limit": {
                "total": 1000,
                "remaining": 999,
                "reset_after": 14400000,
                "max_concurrency": 1,
            },
        },
    ),
]


@endpoint_cases(CASES)
async def test_gateway_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
