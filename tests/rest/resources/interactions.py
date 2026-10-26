import pytest

from shoal.payloads import (
    CreateFollowupMessageParams,
    DeferredMessageResponse,
    EditWebhookMessageParams,
    InteractionMessage,
    MessageResponse,
)
from shoal.rest.errors import NotFoundError
from tests.support.fakes import FakeTransport
from tests.support.json_payloads import MESSAGE
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases, make_client

INTERACTION_WEBHOOK = "/webhooks/7/aW50ZXJhY3Rpb24"

CASES = [
    EndpointCase(
        name="respond",
        call=lambda client: client.create_interaction_response(
            9, "aW50ZXJhY3Rpb24", MessageResponse(data=InteractionMessage(content="hi"))
        ),
        method="POST",
        path="/interactions/9/aW50ZXJhY3Rpb24/callback",
        body={"type": 4, "data": {"content": "hi"}},
    ),
    EndpointCase(
        name="respond with response",
        call=lambda client: client.create_interaction_response(
            9, "aW50ZXJhY3Rpb24", DeferredMessageResponse(), with_response=True
        ),
        method="POST",
        path="/interactions/9/aW50ZXJhY3Rpb24/callback?with_response=true",
        body={"type": 5},
        response={"interaction": {"id": "9", "type": 2}},
    ),
    EndpointCase(
        name="get original",
        call=lambda client: client.get_original_interaction_response(7, "aW50ZXJhY3Rpb24"),
        method="GET",
        path=f"{INTERACTION_WEBHOOK}/messages/@original",
        response=MESSAGE,
    ),
    EndpointCase(
        name="edit original",
        call=lambda client: client.edit_original_interaction_response(
            7, "aW50ZXJhY3Rpb24", EditWebhookMessageParams(content=None)
        ),
        method="PATCH",
        path=f"{INTERACTION_WEBHOOK}/messages/@original",
        body={"content": None},
        response=MESSAGE,
    ),
    EndpointCase(
        name="delete original",
        call=lambda client: client.delete_original_interaction_response(7, "aW50ZXJhY3Rpb24"),
        method="DELETE",
        path=f"{INTERACTION_WEBHOOK}/messages/@original",
    ),
    EndpointCase(
        name="follow up",
        call=lambda client: client.create_followup_message(
            7, "aW50ZXJhY3Rpb24", CreateFollowupMessageParams(content="later")
        ),
        method="POST",
        path=INTERACTION_WEBHOOK,
        body={"content": "later"},
        response=MESSAGE,
    ),
    EndpointCase(
        name="get follow-up",
        call=lambda client: client.get_followup_message(7, "aW50ZXJhY3Rpb24", 9),
        method="GET",
        path=f"{INTERACTION_WEBHOOK}/messages/9",
        response=MESSAGE,
    ),
    EndpointCase(
        name="edit follow-up",
        call=lambda client: client.edit_followup_message(
            7, "aW50ZXJhY3Rpb24", 9, EditWebhookMessageParams(content="edited")
        ),
        method="PATCH",
        path=f"{INTERACTION_WEBHOOK}/messages/9",
        body={"content": "edited"},
        response=MESSAGE,
    ),
    EndpointCase(
        name="delete follow-up",
        call=lambda client: client.delete_followup_message(7, "aW50ZXJhY3Rpb24", 9),
        method="DELETE",
        path=f"{INTERACTION_WEBHOOK}/messages/9",
    ),
]


@endpoint_cases(CASES)
async def test_interaction_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)


async def test_interaction_tokens_stay_out_of_errors() -> None:
    transport = FakeTransport()
    transport.queue(404, {"message": "Unknown Webhook", "code": 10015})
    client = make_client(transport)
    with pytest.raises(NotFoundError) as caught:
        await client.get_original_interaction_response(7, "aW50ZXJhY3Rpb24")
    assert "aW50ZXJhY3Rpb24" not in str(caught.value)
    assert "{interaction_token}" in str(caught.value)
