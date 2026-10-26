from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    ApplicationCommandPermission,
    ApplicationCommandPermissionType,
    BulkApplicationCommandParams,
    CreateGlobalApplicationCommandParams,
    CreateGuildApplicationCommandParams,
    EditApplicationCommandPermissionsParams,
    EditGlobalApplicationCommandParams,
    EditGuildApplicationCommandParams,
)
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

COMMAND: dict[str, object] = {
    "id": "5",
    "application_id": "7",
    "name": "ping",
    "description": "Check the bot",
    "default_member_permissions": None,
    "version": "1",
}
PERMISSIONS: dict[str, object] = {
    "id": "5",
    "application_id": "7",
    "guild_id": "2",
    "permissions": [{"id": "2", "type": 1, "permission": True}],
}
GLOBAL_COMMANDS = "/applications/7/commands"
GUILD_COMMANDS = "/applications/7/guilds/2/commands"

CASES = [
    EndpointCase(
        name="get global",
        call=lambda client: client.get_global_application_commands(7),
        method="GET",
        path=f"{GLOBAL_COMMANDS}?with_localizations=false",
        response=[COMMAND],
    ),
    EndpointCase(
        name="create global",
        call=lambda client: client.create_global_application_command(
            7, CreateGlobalApplicationCommandParams(name="ping", description="Check the bot")
        ),
        method="POST",
        path=GLOBAL_COMMANDS,
        body={"name": "ping", "description": "Check the bot"},
        response=COMMAND,
    ),
    EndpointCase(
        name="get one global",
        call=lambda client: client.get_global_application_command(7, 5),
        method="GET",
        path=f"{GLOBAL_COMMANDS}/5",
        response=COMMAND,
    ),
    EndpointCase(
        name="edit global",
        call=lambda client: client.edit_global_application_command(
            7, 5, EditGlobalApplicationCommandParams(nsfw=True)
        ),
        method="PATCH",
        path=f"{GLOBAL_COMMANDS}/5",
        body={"nsfw": True},
        response=COMMAND,
    ),
    EndpointCase(
        name="delete global",
        call=lambda client: client.delete_global_application_command(7, 5),
        method="DELETE",
        path=f"{GLOBAL_COMMANDS}/5",
    ),
    EndpointCase(
        name="bulk global",
        call=lambda client: client.bulk_overwrite_global_application_commands(7, []),
        method="PUT",
        path=GLOBAL_COMMANDS,
        body=[],
        response=[],
    ),
    EndpointCase(
        name="get guild",
        call=lambda client: client.get_guild_application_commands(7, 2, with_localizations=True),
        method="GET",
        path=f"{GUILD_COMMANDS}?with_localizations=true",
        response=[COMMAND],
    ),
    EndpointCase(
        name="create guild",
        call=lambda client: client.create_guild_application_command(
            7, 2, CreateGuildApplicationCommandParams(name="ping", description="Check the bot")
        ),
        method="POST",
        path=GUILD_COMMANDS,
        body={"name": "ping", "description": "Check the bot"},
        response=COMMAND,
    ),
    EndpointCase(
        name="get one guild",
        call=lambda client: client.get_guild_application_command(7, 2, 5),
        method="GET",
        path=f"{GUILD_COMMANDS}/5",
        response=COMMAND,
    ),
    EndpointCase(
        name="edit guild",
        call=lambda client: client.edit_guild_application_command(
            7, 2, 5, EditGuildApplicationCommandParams(name="pong")
        ),
        method="PATCH",
        path=f"{GUILD_COMMANDS}/5",
        body={"name": "pong"},
        response=COMMAND,
    ),
    EndpointCase(
        name="delete guild",
        call=lambda client: client.delete_guild_application_command(7, 2, 5),
        method="DELETE",
        path=f"{GUILD_COMMANDS}/5",
    ),
    EndpointCase(
        name="bulk guild",
        call=lambda client: client.bulk_overwrite_guild_application_commands(
            7, 2, [BulkApplicationCommandParams(name="ping", description="Check the bot")]
        ),
        method="PUT",
        path=GUILD_COMMANDS,
        body=[{"name": "ping", "description": "Check the bot"}],
        response=[COMMAND],
    ),
    EndpointCase(
        name="guild permissions",
        call=lambda client: client.get_guild_application_command_permissions(7, 2),
        method="GET",
        path=f"{GUILD_COMMANDS}/permissions",
        response=[PERMISSIONS],
    ),
    EndpointCase(
        name="command permissions",
        call=lambda client: client.get_application_command_permissions(7, 2, 5),
        method="GET",
        path=f"{GUILD_COMMANDS}/5/permissions",
        response=PERMISSIONS,
    ),
    EndpointCase(
        name="edit permissions",
        call=lambda client: client.edit_application_command_permissions(
            7,
            2,
            5,
            EditApplicationCommandPermissionsParams(
                permissions=[
                    ApplicationCommandPermission(
                        id=Snowflake(2), type=ApplicationCommandPermissionType.ROLE, permission=True
                    )
                ]
            ),
        ),
        method="PUT",
        path=f"{GUILD_COMMANDS}/5/permissions",
        body={"permissions": [{"id": "2", "type": 1, "permission": True}]},
        response=PERMISSIONS,
    ),
]


@endpoint_cases(CASES)
async def test_application_command_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
