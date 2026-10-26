"""The endpoints `RestClient` is assembled from, one class per Discord resource.

Use them through `RestClient`; they are separate only to keep each resource's methods together.

Discord: https://docs.discord.com/developers/reference#http-api
"""

from shoal.rest.resources.application_commands import ApplicationCommandEndpoints
from shoal.rest.resources.channel import ChannelEndpoints
from shoal.rest.resources.gateway import GatewayEndpoints
from shoal.rest.resources.guild import GuildEndpoints
from shoal.rest.resources.interactions import InteractionEndpoints
from shoal.rest.resources.message import MessageEndpoints
from shoal.rest.resources.user import UserEndpoints

__all__ = [
    "ApplicationCommandEndpoints",
    "ChannelEndpoints",
    "GatewayEndpoints",
    "GuildEndpoints",
    "InteractionEndpoints",
    "MessageEndpoints",
    "UserEndpoints",
]
