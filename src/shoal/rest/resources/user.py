"""Endpoints for users.

Discord: https://docs.discord.com/developers/resources/user
"""

from shoal.core.snowflake import Snowflake
from shoal.payloads.channel import Channel
from shoal.payloads.guild import GuildMember, PartialGuild
from shoal.payloads.user import (
    ApplicationRoleConnection,
    Connection,
    CreateDMParams,
    CreateGroupDMParams,
    GetCurrentUserGuildsParams,
    ModifyCurrentUserParams,
    UpdateApplicationRoleConnectionParams,
    User,
)
from shoal.rest.endpoints import (
    CREATE_DM,
    CREATE_GROUP_DM,
    DELETE_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
    GET_CURRENT_USER,
    GET_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
    GET_CURRENT_USER_CONNECTIONS,
    GET_CURRENT_USER_GUILD_MEMBER,
    GET_CURRENT_USER_GUILDS,
    GET_USER,
    LEAVE_GUILD,
    MODIFY_CURRENT_USER,
    UPDATE_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
)
from shoal.rest.requester import Requester, query_of


class UserEndpoints(Requester):
    """Endpoints for users; part of `RestClient`."""

    __slots__ = ()

    async def get_current_user(self) -> User:
        """Get the user the token belongs to (the bot, or the OAuth2 user for a bearer token).

        Discord: https://docs.discord.com/developers/resources/user#get-current-user
        """
        return await self.request(GET_CURRENT_USER.compile(), User)

    async def get_user(self, user_id: int) -> User:
        """Get any user by ID.

        Discord: https://docs.discord.com/developers/resources/user#get-user
        """
        return await self.request(GET_USER.compile(user_id=user_id), User)

    async def modify_current_user(self, params: ModifyCurrentUserParams) -> User:
        """Change the current user's username, avatar or banner.

        Discord: https://docs.discord.com/developers/resources/user#modify-current-user
        """
        return await self.request(MODIFY_CURRENT_USER.compile(), User, body=params)

    async def get_current_user_guilds(
        self, params: GetCurrentUserGuildsParams | None = None
    ) -> list[PartialGuild]:
        """List the guilds the current user is in, up to 200 per call.

        Bots using large bot sharding must pass `shard` and call once per value.

        Discord: https://docs.discord.com/developers/resources/user#get-current-user-guilds
        """
        query = query_of(params) if params is not None else None
        return await self.request(GET_CURRENT_USER_GUILDS.compile(), list[PartialGuild], query=query)

    async def get_current_user_guild_member(self, guild_id: int) -> GuildMember:
        """Get the current user's membership in a guild. Needs the `guilds.members.read` scope.

        Discord: https://docs.discord.com/developers/resources/user#get-current-user-guild-member
        """
        return await self.request(GET_CURRENT_USER_GUILD_MEMBER.compile(guild_id=guild_id), GuildMember)

    async def leave_guild(self, guild_id: int) -> None:
        """Leave a guild.

        Discord: https://docs.discord.com/developers/resources/user#leave-guild
        """
        await self.request_empty(LEAVE_GUILD.compile(guild_id=guild_id))

    async def create_dm(self, recipient_id: int) -> Channel:
        """Open (or get the existing) DM channel with a user.

        DMs should follow from something the user did; opening many quickly gets the bot rate
        limited or blocked from opening more.

        Discord: https://docs.discord.com/developers/resources/user#create-dm
        """
        return await self.request(
            CREATE_DM.compile(), Channel, body=CreateDMParams(recipient_id=Snowflake(recipient_id))
        )

    async def create_group_dm(self, params: CreateGroupDMParams) -> Channel:
        """Create a group DM with users who granted the app `gdm.join`. At most 10 can be active.

        Discord: https://docs.discord.com/developers/resources/user#create-group-dm
        """
        return await self.request(CREATE_GROUP_DM.compile(), Channel, body=params)

    async def get_current_user_connections(self) -> list[Connection]:
        """List the current user's connected accounts. Needs the `connections` scope.

        Discord: https://docs.discord.com/developers/resources/user#get-current-user-connections
        """
        return await self.request(GET_CURRENT_USER_CONNECTIONS.compile(), list[Connection])

    async def get_current_user_application_role_connection(
        self, application_id: int
    ) -> ApplicationRoleConnection:
        """Get what the app has recorded about the user for linked roles.

        Needs a bearer token with the `role_connections.write` scope for that app.

        Discord: https://docs.discord.com/developers/resources/user#get-current-user-application-role-connection
        """
        return await self.request(
            GET_CURRENT_USER_APPLICATION_ROLE_CONNECTION.compile(application_id=application_id),
            ApplicationRoleConnection,
        )

    async def update_current_user_application_role_connection(
        self, application_id: int, params: UpdateApplicationRoleConnectionParams
    ) -> ApplicationRoleConnection:
        """Record what linked roles check against for the user.

        Needs a bearer token with the `role_connections.write` scope for that app.

        Discord: https://docs.discord.com/developers/resources/user#update-current-user-application-role-connection
        """
        return await self.request(
            UPDATE_CURRENT_USER_APPLICATION_ROLE_CONNECTION.compile(application_id=application_id),
            ApplicationRoleConnection,
            body=params,
        )

    async def delete_current_user_application_role_connection(self, application_id: int) -> None:
        """Remove what the app has recorded about the user for linked roles.

        Needs a bearer token with the `role_connections.write` scope for that app.

        Discord: https://docs.discord.com/developers/resources/user#delete-current-user-application-role-connection
        """
        await self.request_empty(
            DELETE_CURRENT_USER_APPLICATION_ROLE_CONNECTION.compile(application_id=application_id)
        )
