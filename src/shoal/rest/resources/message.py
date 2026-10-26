"""Endpoints for messages.

Discord: https://docs.discord.com/developers/resources/message
"""

from shoal.payloads.message import (
    CreateMessageParams,
    Message,
)
from shoal.rest.endpoints import (
    CREATE_MESSAGE,
    DELETE_MESSAGE,
    GET_CHANNEL_MESSAGE,
)
from shoal.rest.requester import Requester


class MessageEndpoints(Requester):
    """Endpoints for messages; part of `RestClient`."""

    __slots__ = ()

    async def get_channel_message(self, channel_id: int, message_id: int) -> Message:
        """Get one message.

        Discord: https://docs.discord.com/developers/resources/message#get-channel-message
        """
        return await self.request(
            GET_CHANNEL_MESSAGE.compile(channel_id=channel_id, message_id=message_id), Message
        )

    async def create_message(self, channel_id: int, params: CreateMessageParams) -> Message:
        """Send a message.

        Discord: https://docs.discord.com/developers/resources/message#create-message
        """
        return await self.request(CREATE_MESSAGE.compile(channel_id=channel_id), Message, body=params)

    async def delete_message(self, channel_id: int, message_id: int, *, reason: str | None = None) -> None:
        """Delete a message.

        Discord: https://docs.discord.com/developers/resources/message#delete-message
        """
        await self.request_empty(
            DELETE_MESSAGE.compile(channel_id=channel_id, message_id=message_id), reason=reason
        )
