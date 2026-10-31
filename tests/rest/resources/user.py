from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    CreateGroupDMParams,
    EditCurrentRoleConnectionParams,
    EditCurrentUserParams,
    ListGuildsParams,
)
from tests.support.json_payloads import MEMBER, USER
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

PARTIAL_GUILD: dict[str, object] = {
    "id": "80351110224678912",
    "name": "1337 Krew",
    "icon": "8342729096ea3675442027381ff50dfe",
    "banner": "bb42bdc37653b7cf58c4c8cc622e76cb",
    "owner": True,
    "permissions": "36953089",
    "features": ["COMMUNITY", "NEWS", "ANIMATED_ICON", "INVITE_SPLASH", "BANNER", "ROLE_ICONS"],
    "approximate_member_count": 3268,
    "approximate_presence_count": 784,
}
"""Discord's own example."""
DM: dict[str, object] = {"id": "4", "type": 1, "last_message_id": None, "recipients": [USER]}
CONNECTION: dict[str, object] = {
    "id": "octocat",
    "name": "octocat",
    "type": "github",
    "verified": True,
    "friend_sync": False,
    "show_activity": True,
    "two_way_link": False,
    "visibility": 1,
}
ROLE_CONNECTION: dict[str, object] = {
    "platform_name": "Example",
    "platform_username": "ada",
    "metadata": {"level": "12"},
}
ROLE_CONNECTION_PATH = "/users/@me/applications/7/role-connection"

CASES = [
    EndpointCase(
        name="get current user",
        call=lambda client: client.users.get_me(),
        method="GET",
        path="/users/@me",
        response=USER,
    ),
    EndpointCase(
        name="get user",
        call=lambda client: client.users.get(1),
        method="GET",
        path="/users/1",
        response=USER,
    ),
    EndpointCase(
        name="modify current user",
        call=lambda client: client.users.edit_me(EditCurrentUserParams(username="bot", avatar=None)),
        method="PATCH",
        path="/users/@me",
        body={"username": "bot", "avatar": None},
        response=USER,
    ),
    EndpointCase(
        name="get guilds",
        call=lambda client: client.guilds.list(),
        method="GET",
        path="/users/@me/guilds",
        response=[PARTIAL_GUILD],
    ),
    EndpointCase(
        name="get guilds of one shard",
        call=lambda client: client.guilds.list(
            ListGuildsParams(after=Snowflake(5), limit=10, shard=2, with_counts=True)
        ),
        method="GET",
        path="/users/@me/guilds?after=5&limit=10&shard=2&with_counts=true",
        response=[PARTIAL_GUILD],
    ),
    EndpointCase(
        name="get own member",
        call=lambda client: client.members.get_me(2),
        method="GET",
        path="/users/@me/guilds/2/member",
        response=MEMBER,
    ),
    EndpointCase(
        name="leave guild",
        call=lambda client: client.guilds.leave(2),
        method="DELETE",
        path="/users/@me/guilds/2",
    ),
    EndpointCase(
        name="create dm",
        call=lambda client: client.users.create_dm(1),
        method="POST",
        path="/users/@me/channels",
        body={"recipient_id": "1"},
        response=DM,
    ),
    EndpointCase(
        name="create group dm",
        call=lambda client: client.users.create_group_dm(
            CreateGroupDMParams(access_tokens=["token"], nicks={Snowflake(1): "Ada"})
        ),
        method="POST",
        path="/users/@me/channels",
        body={"access_tokens": ["token"], "nicks": {"1": "Ada"}},
        response=DM,
    ),
    EndpointCase(
        name="get connections",
        call=lambda client: client.users.list_connections(),
        method="GET",
        path="/users/@me/connections",
        response=[CONNECTION],
    ),
    EndpointCase(
        name="get role connection",
        call=lambda client: client.role_connections.get_me(7),
        method="GET",
        path=ROLE_CONNECTION_PATH,
        response=ROLE_CONNECTION,
    ),
    EndpointCase(
        name="get an empty role connection",
        call=lambda client: client.role_connections.get_me(7),
        method="GET",
        path=ROLE_CONNECTION_PATH,
        response={},
    ),
    EndpointCase(
        name="update role connection",
        call=lambda client: client.role_connections.edit_me(
            7,
            EditCurrentRoleConnectionParams(
                platform_name="Example", platform_username="ada", metadata={"level": "12"}
            ),
        ),
        method="PUT",
        path=ROLE_CONNECTION_PATH,
        body=ROLE_CONNECTION,
        response=ROLE_CONNECTION,
    ),
    EndpointCase(
        name="delete role connection",
        call=lambda client: client.role_connections.delete_me(7),
        method="DELETE",
        path=ROLE_CONNECTION_PATH,
    ),
]


@endpoint_cases(CASES)
async def test_user_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
