"""Endpoints for users.

Discord: https://docs.discord.com/developers/resources/user
"""

from shoal.core.snowflake import Snowflake
from shoal.payloads.channel import Channel
from shoal.payloads.user import (
    Connection,
    CreateDMParams,
    CreateGroupDMParams,
    EditCurrentUserParams,
    User,
)
from shoal.rest.endpoints import (
    CREATE_DM,
    CREATE_GROUP_DM,
    GET_CURRENT_USER,
    GET_CURRENT_USER_CONNECTIONS,
    GET_USER,
    MODIFY_CURRENT_USER,
)
from shoal.rest.requester import Resource


class Users(Resource):
    """Users, the current user, and DMs.

    Use it as `rest.users`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def get_me(self) -> User:
        """Get the user the token belongs to (the bot, or the OAuth2 user for a bearer token).

        Discord: https://docs.discord.com/developers/resources/user#get-current-user
        """
        return await self.request(GET_CURRENT_USER.compile(), User)

    async def get(self, user_id: int) -> User:
        """Get any user by ID.

        Discord: https://docs.discord.com/developers/resources/user#get-user
        """
        return await self.request(GET_USER.compile(user_id=user_id), User)

    async def edit_me(self, params: EditCurrentUserParams) -> User:
        """Change the current user's username, avatar or banner.

        Discord: https://docs.discord.com/developers/resources/user#modify-current-user
        """
        return await self.request(MODIFY_CURRENT_USER.compile(), User, body=params)

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

    async def list_connections(self) -> list[Connection]:
        """List the current user's connected accounts. Needs the `connections` scope.

        Discord: https://docs.discord.com/developers/resources/user#get-current-user-connections
        """
        return await self.request(GET_CURRENT_USER_CONNECTIONS.compile(), list[Connection])
