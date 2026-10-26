"""Endpoints for the gateway URL endpoints.

Discord: https://docs.discord.com/developers/events/gateway
"""

from shoal.payloads.gateway import GatewayBot, GatewayInfo
from shoal.rest.endpoints import (
    GET_GATEWAY,
    GET_GATEWAY_BOT,
)
from shoal.rest.requester import Requester


class GatewayEndpoints(Requester):
    """Endpoints for the gateway URL endpoints; part of `RestClient`."""

    __slots__ = ()

    async def get_gateway(self) -> GatewayInfo:
        """Get the gateway URL. Needs no token.

        Discord: https://docs.discord.com/developers/events/gateway#get-gateway
        """
        return await self.request(GET_GATEWAY.compile(), GatewayInfo)

    async def get_gateway_bot(self) -> GatewayBot:
        """Get the gateway URL, recommended shard count and session start limit.

        Discord: https://docs.discord.com/developers/events/gateway#get-gateway-bot
        """
        return await self.request(GET_GATEWAY_BOT.compile(), GatewayBot)
