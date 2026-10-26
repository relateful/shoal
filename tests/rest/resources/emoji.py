from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    CreateApplicationEmojiParams,
    CreateEmojiParams,
    EditApplicationEmojiParams,
    EditEmojiParams,
)
from tests.support.json_payloads import USER
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

EMOJI: dict[str, object] = {
    "id": "41771983429993937",
    "name": "LUL",
    "roles": ["41771983429993000"],
    "user": USER,
    "require_colons": True,
    "managed": False,
    "animated": False,
    "available": True,
}
IMAGE = "data:image/png;base64,iVBORw0KGgo="
GUILD_EMOJIS = "/guilds/2/emojis"
APPLICATION_EMOJIS = "/applications/7/emojis"

CASES = [
    EndpointCase(
        name="list guild emojis",
        call=lambda client: client.emojis.list(2),
        method="GET",
        path=GUILD_EMOJIS,
        response=[EMOJI],
    ),
    EndpointCase(
        name="get guild emoji",
        call=lambda client: client.emojis.get(2, 41771983429993937),
        method="GET",
        path=f"{GUILD_EMOJIS}/41771983429993937",
        response=EMOJI,
    ),
    EndpointCase(
        name="create guild emoji",
        call=lambda client: client.emojis.create(
            2,
            CreateEmojiParams(name="LUL", image=IMAGE, roles=[Snowflake(41771983429993000)]),
            reason="new emote",
        ),
        method="POST",
        path=GUILD_EMOJIS,
        body={"name": "LUL", "image": IMAGE, "roles": ["41771983429993000"]},
        response=EMOJI,
        reason="new emote",
    ),
    EndpointCase(
        name="modify guild emoji",
        call=lambda client: client.emojis.edit(2, 41771983429993937, EditEmojiParams(roles=None)),
        method="PATCH",
        path=f"{GUILD_EMOJIS}/41771983429993937",
        body={"roles": None},
        response=EMOJI,
    ),
    EndpointCase(
        name="delete guild emoji",
        call=lambda client: client.emojis.delete(2, 41771983429993937, reason="unused"),
        method="DELETE",
        path=f"{GUILD_EMOJIS}/41771983429993937",
        reason="unused",
    ),
    EndpointCase(
        name="list application emojis",
        call=lambda client: client.emojis.list_for_application(7),
        method="GET",
        path=APPLICATION_EMOJIS,
        response={"items": [EMOJI]},
        result=[EMOJI],
    ),
    EndpointCase(
        name="get application emoji",
        call=lambda client: client.emojis.get_for_application(7, 41771983429993937),
        method="GET",
        path=f"{APPLICATION_EMOJIS}/41771983429993937",
        response=EMOJI,
    ),
    EndpointCase(
        name="create application emoji",
        call=lambda client: client.emojis.create_for_application(
            7, CreateApplicationEmojiParams(name="LUL", image=IMAGE)
        ),
        method="POST",
        path=APPLICATION_EMOJIS,
        body={"name": "LUL", "image": IMAGE},
        response=EMOJI,
    ),
    EndpointCase(
        name="modify application emoji",
        call=lambda client: client.emojis.edit_for_application(
            7, 41771983429993937, EditApplicationEmojiParams(name="KEKW")
        ),
        method="PATCH",
        path=f"{APPLICATION_EMOJIS}/41771983429993937",
        body={"name": "KEKW"},
        response=EMOJI,
    ),
    EndpointCase(
        name="delete application emoji",
        call=lambda client: client.emojis.delete_for_application(7, 41771983429993937),
        method="DELETE",
        path=f"{APPLICATION_EMOJIS}/41771983429993937",
    ),
]


@endpoint_cases(CASES)
async def test_emoji_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
