"""Endpoints for guilds and their members.

Discord: https://docs.discord.com/developers/resources/guild
"""

from shoal.payloads.guild import Guild, GuildMember
from shoal.rest.endpoints import (
    GET_GUILD,
    GET_GUILD_MEMBER,
)
from shoal.rest.requester import Requester


class GuildEndpoints(Requester):
    """Endpoints for guilds and their members; part of `RestClient`."""

    __slots__ = ()

    async def get_guild(self, guild_id: int, *, with_counts: bool = False) -> Guild:
        """Get a guild, optionally with approximate member and presence counts.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild
        """
        return await self.request(
            GET_GUILD.compile(guild_id=guild_id), Guild, query={"with_counts": with_counts}
        )

    async def get_guild_member(self, guild_id: int, user_id: int) -> GuildMember:
        """Get one member of a guild.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-member
        """
        return await self.request(GET_GUILD_MEMBER.compile(guild_id=guild_id, user_id=user_id), GuildMember)
