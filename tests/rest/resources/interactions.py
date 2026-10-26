import pytest

from shoal.payloads import (
    DeferredMessageResponse,
    DeferredUpdateResponse,
    EditWebhookMessageParams,
    InteractionMessage,
    MessageFlags,
    MessageResponse,
    SendFollowupParams,
    UpdateMessageResponse,
)
from shoal.rest.errors import NotFoundError
from shoal.rest.files import File
from tests.support.fakes import FakeTransport
from tests.support.json_payloads import MESSAGE
from tests.support.multipart import FormPart
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases, make_client

INTERACTION_WEBHOOK = "/webhooks/7/aW50ZXJhY3Rpb24"
PNG = b"\x89PNG\r\n\x1a\n"

CASES = [
    EndpointCase(
        name="respond with a file",
        call=lambda client: client.interactions.respond(
            9,
            "aW50ZXJhY3Rpb24",
            MessageResponse(data=InteractionMessage(content="here")),
            files=[File("chart.png", PNG, content_type="image/png")],
        ),
        method="POST",
        path="/interactions/9/aW50ZXJhY3Rpb24/callback",
        body={"type": 4, "data": {"content": "here", "attachments": [{"id": 0, "filename": "chart.png"}]}},
        files=(FormPart("files[0]", "chart.png", "image/png", PNG),),
    ),
    EndpointCase(
        name="update a message adding a file",
        call=lambda client: client.interactions.respond(
            9,
            "aW50ZXJhY3Rpb24",
            UpdateMessageResponse(data=InteractionMessage(content="v2")),
            files=[File("v2.txt", b"2")],
        ),
        method="POST",
        path="/interactions/9/aW50ZXJhY3Rpb24/callback",
        body={"type": 7, "data": {"content": "v2"}},
        files=(FormPart("files[0]", "v2.txt", "application/octet-stream", b"2"),),
    ),
    EndpointCase(
        name="follow up with a file",
        call=lambda client: client.interactions.send_followup(
            7, "aW50ZXJhY3Rpb24", SendFollowupParams(content="later"), files=[File("a.txt", b"a")]
        ),
        method="POST",
        path=INTERACTION_WEBHOOK,
        body={"content": "later", "attachments": [{"id": 0, "filename": "a.txt"}]},
        files=(FormPart("files[0]", "a.txt", "application/octet-stream", b"a"),),
        response=MESSAGE,
    ),
    EndpointCase(
        name="edit original adding a file",
        call=lambda client: client.interactions.edit_original(
            7, "aW50ZXJhY3Rpb24", EditWebhookMessageParams(content="done"), files=[File("a.txt", b"a")]
        ),
        method="PATCH",
        path=f"{INTERACTION_WEBHOOK}/messages/@original",
        body={"content": "done"},
        files=(FormPart("files[0]", "a.txt", "application/octet-stream", b"a"),),
        response=MESSAGE,
    ),
    EndpointCase(
        name="edit follow-up adding a file",
        call=lambda client: client.interactions.edit_followup(
            7, "aW50ZXJhY3Rpb24", 9, EditWebhookMessageParams(), files=[File("a.txt", b"a")]
        ),
        method="PATCH",
        path=f"{INTERACTION_WEBHOOK}/messages/9",
        body={},
        files=(FormPart("files[0]", "a.txt", "application/octet-stream", b"a"),),
        response=MESSAGE,
    ),
    EndpointCase(
        name="respond",
        call=lambda client: client.interactions.respond(
            9, "aW50ZXJhY3Rpb24", MessageResponse(data=InteractionMessage(content="hi"))
        ),
        method="POST",
        path="/interactions/9/aW50ZXJhY3Rpb24/callback",
        body={"type": 4, "data": {"content": "hi"}},
    ),
    EndpointCase(
        name="respond with response",
        call=lambda client: client.interactions.respond(
            9, "aW50ZXJhY3Rpb24", DeferredMessageResponse(), with_response=True
        ),
        method="POST",
        path="/interactions/9/aW50ZXJhY3Rpb24/callback?with_response=true",
        body={"type": 5},
        response={"interaction": {"id": "9", "type": 2}},
    ),
    EndpointCase(
        name="get original",
        call=lambda client: client.interactions.get_original(7, "aW50ZXJhY3Rpb24"),
        method="GET",
        path=f"{INTERACTION_WEBHOOK}/messages/@original",
        response=MESSAGE,
    ),
    EndpointCase(
        name="edit original",
        call=lambda client: client.interactions.edit_original(
            7, "aW50ZXJhY3Rpb24", EditWebhookMessageParams(content=None)
        ),
        method="PATCH",
        path=f"{INTERACTION_WEBHOOK}/messages/@original",
        body={"content": None},
        response=MESSAGE,
    ),
    EndpointCase(
        name="delete original",
        call=lambda client: client.interactions.delete_original(7, "aW50ZXJhY3Rpb24"),
        method="DELETE",
        path=f"{INTERACTION_WEBHOOK}/messages/@original",
    ),
    EndpointCase(
        name="follow up",
        call=lambda client: client.interactions.send_followup(
            7, "aW50ZXJhY3Rpb24", SendFollowupParams(content="later")
        ),
        method="POST",
        path=INTERACTION_WEBHOOK,
        body={"content": "later"},
        response=MESSAGE,
    ),
    EndpointCase(
        name="get follow-up",
        call=lambda client: client.interactions.get_followup(7, "aW50ZXJhY3Rpb24", 9),
        method="GET",
        path=f"{INTERACTION_WEBHOOK}/messages/9",
        response=MESSAGE,
    ),
    EndpointCase(
        name="edit follow-up",
        call=lambda client: client.interactions.edit_followup(
            7, "aW50ZXJhY3Rpb24", 9, EditWebhookMessageParams(content="edited")
        ),
        method="PATCH",
        path=f"{INTERACTION_WEBHOOK}/messages/9",
        body={"content": "edited"},
        response=MESSAGE,
    ),
    EndpointCase(
        name="delete follow-up",
        call=lambda client: client.interactions.delete_followup(7, "aW50ZXJhY3Rpb24", 9),
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
        await client.interactions.get_original(7, "aW50ZXJhY3Rpb24")
    assert "aW50ZXJhY3Rpb24" not in str(caught.value)
    assert "{interaction_token}" in str(caught.value)


async def test_files_need_a_response_that_carries_a_message() -> None:
    client = make_client(FakeTransport())
    # A deferred message response has data (its flags), but Discord does not use files with it.
    deferred = DeferredMessageResponse(data=InteractionMessage(flags=MessageFlags(ephemeral=True)))
    with pytest.raises(TypeError, match="DeferredMessageResponse carries no message"):
        await client.interactions.respond(9, "aW50ZXJhY3Rpb24", deferred, files=[File("a", b"")])
    with pytest.raises(TypeError, match="DeferredUpdateResponse carries no message"):
        await client.interactions.respond(
            9, "aW50ZXJhY3Rpb24", DeferredUpdateResponse(), files=[File("a", b"")]
        )
