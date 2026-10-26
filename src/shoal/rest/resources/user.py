"""Endpoints for users.

Discord: https://docs.discord.com/developers/resources/user
"""

from shoal.payloads.user import User
from shoal.rest.endpoints import (
    GET_CURRENT_USER,
    GET_USER,
)
from shoal.rest.requester import Requester


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
