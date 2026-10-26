from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    AddLobbyMemberParams,
    BulkEditLobbyMemberParams,
    CreateLobbyParams,
    CreateOrJoinLobbyParams,
    EditLobbyParams,
    ListLobbyMessagesParams,
    LobbyMemberFlags,
    LobbyMemberParams,
    SendLobbyMessageParams,
)
from tests.support.json_payloads import CHANNEL, USER
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

MEMBER: dict[str, object] = {
    "id": "41771983429993000",
    "metadata": None,
    "flags": 1,
    "additional_name": "Twindly Shimmerleaf",
}
LOBBY: dict[str, object] = {
    "id": "96008815106887111",
    "application_id": "41771983429993937",
    "metadata": {"topic": "we need more redstone"},
    "members": [MEMBER],
}
"""Discord's example."""
MESSAGE: dict[str, object] = {
    "id": "50",
    "type": 0,
    "content": "gg",
    "lobby_id": "96008815106887111",
    "channel_id": "96008815106887111",
    "author": USER,
    "lobby_member": {"additional_name": "Twindly Shimmerleaf"},
    "metadata": None,
    "flags": 0,
    "application_id": "41771983429993937",
}
L = "/lobbies/96008815106887111"

CASES = [
    EndpointCase(
        name="create",
        call=lambda client: client.lobbies.create(
            CreateLobbyParams(
                members=[
                    LobbyMemberParams(
                        id=Snowflake(41771983429993000), flags=LobbyMemberFlags(can_link_lobby=True)
                    )
                ],
                idle_timeout_seconds=300,
            )
        ),
        method="POST",
        path="/lobbies",
        body={"members": [{"id": "41771983429993000", "flags": 1}], "idle_timeout_seconds": 300},
        response=LOBBY,
    ),
    EndpointCase(
        name="create or join",
        call=lambda client: client.lobbies.create_or_join(
            CreateOrJoinLobbyParams(secret="party-1", member_metadata={"team": "red"})
        ),
        method="PUT",
        path="/lobbies",
        body={"secret": "party-1", "member_metadata": {"team": "red"}},
        response=LOBBY,
    ),
    EndpointCase(
        name="get",
        call=lambda client: client.lobbies.get(96008815106887111),
        method="GET",
        path=L,
        response={**LOBBY, "linked_channel": CHANNEL},
    ),
    EndpointCase(
        name="modify",
        call=lambda client: client.lobbies.edit(96008815106887111, EditLobbyParams(metadata=None)),
        method="PATCH",
        path=L,
        body={"metadata": None},
        response=LOBBY,
    ),
    EndpointCase(
        name="delete",
        call=lambda client: client.lobbies.delete(96008815106887111),
        method="DELETE",
        path=L,
    ),
    EndpointCase(
        name="add member",
        call=lambda client: client.lobbies.add_member(
            96008815106887111, 41771983429993000, AddLobbyMemberParams(additional_name=None)
        ),
        method="PUT",
        path=f"{L}/members/41771983429993000",
        body={"additional_name": None},
        response=MEMBER,
    ),
    EndpointCase(
        name="bulk update members",
        call=lambda client: client.lobbies.bulk_edit_members(
            96008815106887111,
            [
                BulkEditLobbyMemberParams(id=Snowflake(41771983429993000), metadata={"team": "blue"}),
                BulkEditLobbyMemberParams(id=Snowflake(2), remove_member=True),
            ],
        ),
        method="POST",
        path=f"{L}/members/bulk",
        body=[{"id": "41771983429993000", "metadata": {"team": "blue"}}, {"id": "2", "remove_member": True}],
        response=[MEMBER],
    ),
    EndpointCase(
        name="remove member",
        call=lambda client: client.lobbies.remove_member(96008815106887111, 41771983429993000),
        method="DELETE",
        path=f"{L}/members/41771983429993000",
    ),
    EndpointCase(
        name="leave",
        call=lambda client: client.lobbies.leave(96008815106887111),
        method="DELETE",
        path=f"{L}/members/@me",
    ),
    EndpointCase(
        name="link channel",
        call=lambda client: client.lobbies.link_channel(96008815106887111, 3),
        method="PATCH",
        path=f"{L}/channel-linking",
        body={"channel_id": "3"},
        response={**LOBBY, "linked_channel": CHANNEL},
    ),
    EndpointCase(
        name="unlink channel",
        call=lambda client: client.lobbies.unlink_channel(96008815106887111),
        method="PATCH",
        path=f"{L}/channel-linking",
        body={},
        response=LOBBY,
    ),
    EndpointCase(
        name="send message",
        call=lambda client: client.lobbies.send_message(
            96008815106887111, SendLobbyMessageParams(content="gg")
        ),
        method="POST",
        path=f"{L}/messages",
        body={"content": "gg"},
        response=MESSAGE,
    ),
    EndpointCase(
        name="get messages",
        call=lambda client: client.lobbies.list_messages(
            96008815106887111, ListLobbyMessagesParams(limit=200)
        ),
        method="GET",
        path=f"{L}/messages?limit=200",
        response=[MESSAGE],
    ),
    EndpointCase(
        name="moderation metadata",
        call=lambda client: client.lobbies.edit_message_moderation(
            96008815106887111, 50, {"verdict": "hidden"}
        ),
        method="PUT",
        path=f"{L}/messages/50/moderation-metadata",
        body={"verdict": "hidden"},
    ),
    EndpointCase(
        name="invite for self",
        call=lambda client: client.lobbies.create_my_invite(96008815106887111),
        method="POST",
        path=f"{L}/members/@me/invites",
        response={"code": "abc"},
    ),
    EndpointCase(
        name="invite for user",
        call=lambda client: client.lobbies.create_invite(96008815106887111, 2),
        method="POST",
        path=f"{L}/members/2/invites",
        response={"code": "abc"},
    ),
]


@endpoint_cases(CASES)
async def test_lobby_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
