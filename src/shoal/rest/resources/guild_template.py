"""Endpoints for guild templates.

Discord: https://docs.discord.com/developers/resources/guild-template
"""

import builtins

from shoal.payloads.guild_template import CreateTemplateParams, EditTemplateParams, GuildTemplate
from shoal.rest.endpoints import (
    CREATE_GUILD_TEMPLATE,
    DELETE_GUILD_TEMPLATE,
    GET_GUILD_TEMPLATE,
    GET_GUILD_TEMPLATES,
    MODIFY_GUILD_TEMPLATE,
    SYNC_GUILD_TEMPLATE,
)
from shoal.rest.requester import Resource


class Templates(Resource):
    """Guild templates.

    Use it as `rest.templates`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def get(self, template_code: str) -> GuildTemplate:
        """Get a template by its code.

        Discord: https://docs.discord.com/developers/resources/guild-template#get-guild-template
        """
        return await self.request(GET_GUILD_TEMPLATE.compile(template_code=template_code), GuildTemplate)

    async def list(self, guild_id: int) -> builtins.list[GuildTemplate]:
        """List a guild's templates.

        Discord: https://docs.discord.com/developers/resources/guild-template#get-guild-templates
        """
        return await self.request(GET_GUILD_TEMPLATES.compile(guild_id=guild_id), list[GuildTemplate])

    async def create(self, guild_id: int, params: CreateTemplateParams) -> GuildTemplate:
        """Create a template from the guild.

        Discord: https://docs.discord.com/developers/resources/guild-template#create-guild-template
        """
        return await self.request(
            CREATE_GUILD_TEMPLATE.compile(guild_id=guild_id), GuildTemplate, body=params
        )

    async def sync(self, guild_id: int, template_code: str) -> GuildTemplate:
        """Update a template to the guild as it is now.

        Discord: https://docs.discord.com/developers/resources/guild-template#sync-guild-template
        """
        return await self.request(
            SYNC_GUILD_TEMPLATE.compile(guild_id=guild_id, template_code=template_code), GuildTemplate
        )

    async def edit(self, guild_id: int, template_code: str, params: EditTemplateParams) -> GuildTemplate:
        """Rename a template or change its description.

        Discord: https://docs.discord.com/developers/resources/guild-template#modify-guild-template
        """
        return await self.request(
            MODIFY_GUILD_TEMPLATE.compile(guild_id=guild_id, template_code=template_code),
            GuildTemplate,
            body=params,
        )

    async def delete(self, guild_id: int, template_code: str) -> GuildTemplate:
        """Delete a template; returns it.

        Discord: https://docs.discord.com/developers/resources/guild-template#delete-guild-template
        """
        return await self.request(
            DELETE_GUILD_TEMPLATE.compile(guild_id=guild_id, template_code=template_code), GuildTemplate
        )
