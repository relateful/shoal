"""Endpoints for application commands and their permissions.

Discord: https://docs.discord.com/developers/interactions/application-commands
"""

from collections.abc import Sequence

from shoal.payloads.application_commands import (
    ApplicationCommand,
    CreateGlobalCommandParams,
    CreateGuildCommandParams,
    EditCommandPermissionsParams,
    EditGlobalCommandParams,
    EditGuildCommandParams,
    GuildApplicationCommandPermissions,
    OverwriteCommandParams,
)
from shoal.rest.endpoints import (
    BULK_OVERWRITE_GLOBAL_APPLICATION_COMMANDS,
    BULK_OVERWRITE_GUILD_APPLICATION_COMMANDS,
    CREATE_GLOBAL_APPLICATION_COMMAND,
    CREATE_GUILD_APPLICATION_COMMAND,
    DELETE_GLOBAL_APPLICATION_COMMAND,
    DELETE_GUILD_APPLICATION_COMMAND,
    EDIT_APPLICATION_COMMAND_PERMISSIONS,
    EDIT_GLOBAL_APPLICATION_COMMAND,
    EDIT_GUILD_APPLICATION_COMMAND,
    GET_APPLICATION_COMMAND_PERMISSIONS,
    GET_GLOBAL_APPLICATION_COMMAND,
    GET_GLOBAL_APPLICATION_COMMANDS,
    GET_GUILD_APPLICATION_COMMAND,
    GET_GUILD_APPLICATION_COMMAND_PERMISSIONS,
    GET_GUILD_APPLICATION_COMMANDS,
)
from shoal.rest.requester import Resource


class Commands(Resource):
    """Application commands, global and per guild, and their permissions.

    Use it as `rest.commands`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def list_global(
        self, application_id: int, *, with_localizations: bool = False
    ) -> list[ApplicationCommand]:
        """Get the app's global commands.

        Without `with_localizations`, Discord sends each name and description in the requester's
        locale (`name_localized`) instead of the full dictionaries.

        Discord: https://docs.discord.com/developers/interactions/application-commands#get-global-application-commands
        """
        return await self.request(
            GET_GLOBAL_APPLICATION_COMMANDS.compile(application_id=application_id),
            list[ApplicationCommand],
            query={"with_localizations": with_localizations},
        )

    async def create_global(
        self, application_id: int, params: CreateGlobalCommandParams
    ) -> ApplicationCommand:
        """Create a global command, replacing one with the same name.

        Discord: https://docs.discord.com/developers/interactions/application-commands#create-global-application-command
        """
        return await self.request(
            CREATE_GLOBAL_APPLICATION_COMMAND.compile(application_id=application_id),
            ApplicationCommand,
            body=params,
        )

    async def get_global(self, application_id: int, command_id: int) -> ApplicationCommand:
        """Get one global command.

        Discord: https://docs.discord.com/developers/interactions/application-commands#get-global-application-command
        """
        return await self.request(
            GET_GLOBAL_APPLICATION_COMMAND.compile(application_id=application_id, command_id=command_id),
            ApplicationCommand,
        )

    async def edit_global(
        self, application_id: int, command_id: int, params: EditGlobalCommandParams
    ) -> ApplicationCommand:
        """Edit a global command; the fields given replace the existing values.

        Discord: https://docs.discord.com/developers/interactions/application-commands#edit-global-application-command
        """
        return await self.request(
            EDIT_GLOBAL_APPLICATION_COMMAND.compile(application_id=application_id, command_id=command_id),
            ApplicationCommand,
            body=params,
        )

    async def delete_global(self, application_id: int, command_id: int) -> None:
        """Delete a global command.

        Discord: https://docs.discord.com/developers/interactions/application-commands#delete-global-application-command
        """
        await self.request_empty(
            DELETE_GLOBAL_APPLICATION_COMMAND.compile(application_id=application_id, command_id=command_id)
        )

    async def overwrite_global(
        self, application_id: int, commands: Sequence[OverwriteCommandParams]
    ) -> list[ApplicationCommand]:
        """Replace every global command (slash, user and message) with `commands`.

        Commands not in the list are deleted; an empty list deletes them all.

        Discord: https://docs.discord.com/developers/interactions/application-commands#bulk-overwrite-global-application-commands
        """
        return await self.request(
            BULK_OVERWRITE_GLOBAL_APPLICATION_COMMANDS.compile(application_id=application_id),
            list[ApplicationCommand],
            body=list(commands),
        )

    async def list_guild(
        self, application_id: int, guild_id: int, *, with_localizations: bool = False
    ) -> list[ApplicationCommand]:
        """Get the app's commands in one guild.

        Discord: https://docs.discord.com/developers/interactions/application-commands#get-guild-application-commands
        """
        return await self.request(
            GET_GUILD_APPLICATION_COMMANDS.compile(application_id=application_id, guild_id=guild_id),
            list[ApplicationCommand],
            query={"with_localizations": with_localizations},
        )

    async def create_guild(
        self, application_id: int, guild_id: int, params: CreateGuildCommandParams
    ) -> ApplicationCommand:
        """Create a guild command, available immediately, replacing one with the same name.

        Discord: https://docs.discord.com/developers/interactions/application-commands#create-guild-application-command
        """
        return await self.request(
            CREATE_GUILD_APPLICATION_COMMAND.compile(application_id=application_id, guild_id=guild_id),
            ApplicationCommand,
            body=params,
        )

    async def get_guild(self, application_id: int, guild_id: int, command_id: int) -> ApplicationCommand:
        """Get one guild command.

        Discord: https://docs.discord.com/developers/interactions/application-commands#get-guild-application-command
        """
        return await self.request(
            GET_GUILD_APPLICATION_COMMAND.compile(
                application_id=application_id, guild_id=guild_id, command_id=command_id
            ),
            ApplicationCommand,
        )

    async def edit_guild(
        self, application_id: int, guild_id: int, command_id: int, params: EditGuildCommandParams
    ) -> ApplicationCommand:
        """Edit a guild command; the fields given replace the existing values.

        Discord: https://docs.discord.com/developers/interactions/application-commands#edit-guild-application-command
        """
        return await self.request(
            EDIT_GUILD_APPLICATION_COMMAND.compile(
                application_id=application_id, guild_id=guild_id, command_id=command_id
            ),
            ApplicationCommand,
            body=params,
        )

    async def delete_guild(self, application_id: int, guild_id: int, command_id: int) -> None:
        """Delete a guild command.

        Discord: https://docs.discord.com/developers/interactions/application-commands#delete-guild-application-command
        """
        await self.request_empty(
            DELETE_GUILD_APPLICATION_COMMAND.compile(
                application_id=application_id, guild_id=guild_id, command_id=command_id
            )
        )

    async def overwrite_guild(
        self, application_id: int, guild_id: int, commands: Sequence[OverwriteCommandParams]
    ) -> list[ApplicationCommand]:
        """Replace every command of the app in one guild with `commands`.

        Discord: https://docs.discord.com/developers/interactions/application-commands#bulk-overwrite-guild-application-commands
        """
        return await self.request(
            BULK_OVERWRITE_GUILD_APPLICATION_COMMANDS.compile(
                application_id=application_id, guild_id=guild_id
            ),
            list[ApplicationCommand],
            body=list(commands),
        )

    async def list_permissions(
        self, application_id: int, guild_id: int
    ) -> list[GuildApplicationCommandPermissions]:
        """Get the permission overwrites of every command of the app in one guild.

        Discord: https://docs.discord.com/developers/interactions/application-commands#get-guild-application-command-permissions
        """
        return await self.request(
            GET_GUILD_APPLICATION_COMMAND_PERMISSIONS.compile(
                application_id=application_id, guild_id=guild_id
            ),
            list[GuildApplicationCommandPermissions],
        )

    async def get_permissions(
        self, application_id: int, guild_id: int, command_id: int
    ) -> GuildApplicationCommandPermissions:
        """Get the permission overwrites of one command in one guild.

        Discord: https://docs.discord.com/developers/interactions/application-commands#get-application-command-permissions
        """
        return await self.request(
            GET_APPLICATION_COMMAND_PERMISSIONS.compile(
                application_id=application_id, guild_id=guild_id, command_id=command_id
            ),
            GuildApplicationCommandPermissions,
        )

    async def edit_permissions(
        self,
        application_id: int,
        guild_id: int,
        command_id: int,
        params: EditCommandPermissionsParams,
    ) -> GuildApplicationCommandPermissions:
        """Replace the permission overwrites of one command in one guild.

        Needs a client built with `Token.bearer` for a user who can manage the guild and its roles; a
        bot token is rejected.

        Discord: https://docs.discord.com/developers/interactions/application-commands#edit-application-command-permissions
        """
        return await self.request(
            EDIT_APPLICATION_COMMAND_PERMISSIONS.compile(
                application_id=application_id, guild_id=guild_id, command_id=command_id
            ),
            GuildApplicationCommandPermissions,
            body=params,
        )
