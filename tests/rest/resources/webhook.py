from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    AttachmentRequest,
    CreateWebhookParams,
    EditWebhookMessageParams,
    ExecuteWebhookParams,
    ModifyWebhookParams,
    ModifyWebhookWithTokenParams,
)
from shoal.rest.files import File
from tests.support.json_payloads import MESSAGE, USER
from tests.support.multipart import FormPart
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

INCOMING: dict[str, object] = {
    "id": "223704706495545344",
    "type": 1,
    "guild_id": "199737254929760256",
    "channel_id": "199737254929760256",
    "user": USER,
    "name": "test webhook",
    "avatar": None,
    "token": "3d89bb7572e0fb30d8128367b3b1b44fecd1726de135cbe28a41f8b2f777c372",
    "application_id": None,
}
"""Discord's example, in the field table's order and with a shorter token."""
FOLLOWER: dict[str, object] = {
    "id": "752831914402115456",
    "type": 2,
    "guild_id": "56188498421443265",
    "channel_id": "561885260615255432",
    "name": "Guildy name",
    "avatar": "bb71f469c158984e265093a81b3397fb",
    "application_id": None,
    "source_guild": {
        "id": "56188498421476534",
        "name": "Guildy name",
        "icon": "bb71f469c158984e265093a81b3397fb",
    },
    "source_channel": {"id": "5618852344134324", "name": "announcements"},
}
"""Discord's example, in the field table's order."""
HOOK = "/webhooks/223704706495545344"
WITH_TOKEN = f"{HOOK}/secret-token"

CASES = [
    EndpointCase(
        name="create",
        call=lambda client: client.create_webhook(3, CreateWebhookParams(name="test webhook"), reason="ci"),
        method="POST",
        path="/channels/3/webhooks",
        body={"name": "test webhook"},
        response=INCOMING,
        reason="ci",
    ),
    EndpointCase(
        name="channel webhooks",
        call=lambda client: client.get_channel_webhooks(3),
        method="GET",
        path="/channels/3/webhooks",
        response=[INCOMING, FOLLOWER],
    ),
    EndpointCase(
        name="guild webhooks",
        call=lambda client: client.get_guild_webhooks(2),
        method="GET",
        path="/guilds/2/webhooks",
        response=[FOLLOWER],
    ),
    EndpointCase(
        name="get",
        call=lambda client: client.get_webhook(223704706495545344),
        method="GET",
        path=HOOK,
        response=INCOMING,
    ),
    EndpointCase(
        name="get with token",
        call=lambda client: client.get_webhook_with_token(223704706495545344, "secret-token"),
        method="GET",
        path=WITH_TOKEN,
        response={key: value for key, value in INCOMING.items() if key != "user"},
    ),
    EndpointCase(
        name="modify",
        call=lambda client: client.modify_webhook(
            223704706495545344, ModifyWebhookParams(avatar=None, channel_id=Snowflake(4))
        ),
        method="PATCH",
        path=HOOK,
        body={"avatar": None, "channel_id": "4"},
        response=INCOMING,
    ),
    EndpointCase(
        name="modify with token",
        call=lambda client: client.modify_webhook_with_token(
            223704706495545344, "secret-token", ModifyWebhookWithTokenParams(name="renamed")
        ),
        method="PATCH",
        path=WITH_TOKEN,
        body={"name": "renamed"},
        response=INCOMING,
    ),
    EndpointCase(
        name="delete",
        call=lambda client: client.delete_webhook(223704706495545344, reason="unused"),
        method="DELETE",
        path=HOOK,
        reason="unused",
    ),
    EndpointCase(
        name="delete with token",
        call=lambda client: client.delete_webhook_with_token(223704706495545344, "secret-token"),
        method="DELETE",
        path=WITH_TOKEN,
    ),
    EndpointCase(
        name="execute",
        call=lambda client: client.execute_webhook(
            223704706495545344, "secret-token", ExecuteWebhookParams(content="hi", username="CI")
        ),
        method="POST",
        path=WITH_TOKEN,
        body={"content": "hi", "username": "CI"},
    ),
    EndpointCase(
        name="execute and wait",
        call=lambda client: client.execute_webhook(
            223704706495545344,
            "secret-token",
            ExecuteWebhookParams(content="build log"),
            wait=True,
            thread_id=8,
            with_components=True,
            files=[File("build.log", b"ok")],
        ),
        method="POST",
        path=f"{WITH_TOKEN}?wait=true&thread_id=8&with_components=true",
        body={"content": "build log", "attachments": [{"id": 0, "filename": "build.log"}]},
        files=(FormPart("files[0]", "build.log", "application/octet-stream", b"ok"),),
        response=MESSAGE,
    ),
    EndpointCase(
        name="execute slack",
        call=lambda client: client.execute_slack_compatible_webhook(
            223704706495545344, "secret-token", {"text": "deployed"}, thread_id=8
        ),
        method="POST",
        path=f"{WITH_TOKEN}/slack?thread_id=8",
        body={"text": "deployed"},
    ),
    EndpointCase(
        name="execute github",
        call=lambda client: client.execute_github_compatible_webhook(
            223704706495545344, "secret-token", {"zen": "Keep it simple."}, wait=False
        ),
        method="POST",
        path=f"{WITH_TOKEN}/github?wait=false",
        body={"zen": "Keep it simple."},
    ),
    EndpointCase(
        name="get message",
        call=lambda client: client.get_webhook_message(223704706495545344, "secret-token", 9, thread_id=8),
        method="GET",
        path=f"{WITH_TOKEN}/messages/9?thread_id=8",
        response=MESSAGE,
    ),
    EndpointCase(
        name="edit message",
        call=lambda client: client.edit_webhook_message(
            223704706495545344, "secret-token", 9, EditWebhookMessageParams(content="fixed", embeds=None)
        ),
        method="PATCH",
        path=f"{WITH_TOKEN}/messages/9",
        body={"content": "fixed", "embeds": None},
        response=MESSAGE,
    ),
    EndpointCase(
        name="edit message keeping one attachment and adding a file",
        call=lambda client: client.edit_webhook_message(
            223704706495545344,
            "secret-token",
            9,
            EditWebhookMessageParams(attachments=[AttachmentRequest(id="77")]),
            files=[File("v2.log", b"2", description="second run")],
        ),
        method="PATCH",
        path=f"{WITH_TOKEN}/messages/9",
        body={"attachments": [{"id": "77"}, {"id": 0, "filename": "v2.log", "description": "second run"}]},
        files=(FormPart("files[0]", "v2.log", "application/octet-stream", b"2"),),
        response=MESSAGE,
    ),
    EndpointCase(
        name="delete message",
        call=lambda client: client.delete_webhook_message(223704706495545344, "secret-token", 9),
        method="DELETE",
        path=f"{WITH_TOKEN}/messages/9",
    ),
]


@endpoint_cases(CASES)
async def test_webhook_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
