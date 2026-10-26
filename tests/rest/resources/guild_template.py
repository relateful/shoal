from shoal.payloads import CreateGuildTemplateParams, ModifyGuildTemplateParams
from tests.support.json_payloads import USER
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

TEMPLATE: dict[str, object] = {
    "code": "hgM48av5Q69A",
    "name": "Friends & Family",
    "description": None,
    "usage_count": 49605,
    "creator_id": "1",
    "creator": USER,
    "created_at": "2020-04-02T21:10:38+00:00",
    "updated_at": "2020-05-01T17:57:38+00:00",
    "source_guild_id": "678070694164299796",
    "serialized_source_guild": {
        "name": "Friends & Family",
        "roles": [{"id": 0, "name": "@everyone"}],
        "channels": [],
    },
    "is_dirty": None,
}
"""Discord's example, with a smaller snapshot."""

CASES = [
    EndpointCase(
        name="get by code",
        call=lambda client: client.get_guild_template("hgM48av5Q69A"),
        method="GET",
        path="/guilds/templates/hgM48av5Q69A",
        response=TEMPLATE,
    ),
    EndpointCase(
        name="list",
        call=lambda client: client.get_guild_templates(2),
        method="GET",
        path="/guilds/2/templates",
        response=[TEMPLATE],
    ),
    EndpointCase(
        name="create",
        call=lambda client: client.create_guild_template(
            2, CreateGuildTemplateParams(name="Friends & Family")
        ),
        method="POST",
        path="/guilds/2/templates",
        body={"name": "Friends & Family"},
        response=TEMPLATE,
    ),
    EndpointCase(
        name="sync",
        call=lambda client: client.sync_guild_template(2, "hgM48av5Q69A"),
        method="PUT",
        path="/guilds/2/templates/hgM48av5Q69A",
        response=TEMPLATE,
    ),
    EndpointCase(
        name="modify",
        call=lambda client: client.modify_guild_template(
            2, "hgM48av5Q69A", ModifyGuildTemplateParams(description=None)
        ),
        method="PATCH",
        path="/guilds/2/templates/hgM48av5Q69A",
        body={"description": None},
        response=TEMPLATE,
    ),
    EndpointCase(
        name="delete",
        call=lambda client: client.delete_guild_template(2, "hgM48av5Q69A"),
        method="DELETE",
        path="/guilds/2/templates/hgM48av5Q69A",
        response=TEMPLATE,
    ),
]


@endpoint_cases(CASES)
async def test_guild_template_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
