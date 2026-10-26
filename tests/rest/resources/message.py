from shoal.payloads import CreateMessageParams
from tests.support.json_payloads import MESSAGE
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

CASES = [
    EndpointCase(
        name="get message",
        call=lambda client: client.get_channel_message(3, 9),
        method="GET",
        path="/channels/3/messages/9",
        response=MESSAGE,
    ),
    EndpointCase(
        name="create message",
        call=lambda client: client.create_message(3, CreateMessageParams(content="hi")),
        method="POST",
        path="/channels/3/messages",
        body={"content": "hi"},
        response=MESSAGE,
    ),
    EndpointCase(
        name="delete message",
        call=lambda client: client.delete_message(3, 9, reason="spam"),
        method="DELETE",
        path="/channels/3/messages/9",
        reason="spam",
    ),
]


@endpoint_cases(CASES)
async def test_message_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
