"""Endpoints for channels and threads.

Discord: https://docs.discord.com/developers/resources/channel
"""

from shoal.payloads.channel import Channel
from shoal.rest.endpoints import (
    GET_CHANNEL,
)
from shoal.rest.requester import Requester


class ChannelEndpoints(Requester):
    """Endpoints for channels and threads; part of `RestClient`."""

    __slots__ = ()

    async def get_channel(self, channel_id: int) -> Channel:
        """Get a channel or thread by ID.

        Discord: https://docs.discord.com/developers/resources/channel#get-channel
        """
        return await self.request(GET_CHANNEL.compile(channel_id=channel_id), Channel)
