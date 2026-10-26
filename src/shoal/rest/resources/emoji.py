"""Endpoints for guild and application emojis.

Discord: https://docs.discord.com/developers/resources/emoji
"""

import builtins

from shoal.payloads.emoji import (
    ApplicationEmojis,
    CreateApplicationEmojiParams,
    CreateEmojiParams,
    EditApplicationEmojiParams,
    EditEmojiParams,
    Emoji,
)
from shoal.rest.endpoints import (
    CREATE_APPLICATION_EMOJI,
    CREATE_GUILD_EMOJI,
    DELETE_APPLICATION_EMOJI,
    DELETE_GUILD_EMOJI,
    GET_APPLICATION_EMOJI,
    GET_GUILD_EMOJI,
    LIST_APPLICATION_EMOJIS,
    LIST_GUILD_EMOJIS,
    MODIFY_APPLICATION_EMOJI,
    MODIFY_GUILD_EMOJI,
)
from shoal.rest.requester import Resource


class Emojis(Resource):
    """Guild emojis and application emojis.

    Use it as `rest.emojis`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def list(self, guild_id: int) -> builtins.list[Emoji]:
        """List a guild's custom emojis. `user` is set with Create or Manage Expressions.

        Discord: https://docs.discord.com/developers/resources/emoji#list-guild-emojis
        """
        return await self.request(LIST_GUILD_EMOJIS.compile(guild_id=guild_id), list[Emoji])

    async def get(self, guild_id: int, emoji_id: int) -> Emoji:
        """Get one of a guild's custom emojis.

        Discord: https://docs.discord.com/developers/resources/emoji#get-guild-emoji
        """
        return await self.request(GET_GUILD_EMOJI.compile(guild_id=guild_id, emoji_id=emoji_id), Emoji)

    async def create(self, guild_id: int, params: CreateEmojiParams, *, reason: str | None = None) -> Emoji:
        """Add a custom emoji to a guild. Needs Create Expressions.

        Discord: https://docs.discord.com/developers/resources/emoji#create-guild-emoji
        """
        return await self.request(
            CREATE_GUILD_EMOJI.compile(guild_id=guild_id), Emoji, body=params, reason=reason
        )

    async def edit(
        self, guild_id: int, emoji_id: int, params: EditEmojiParams, *, reason: str | None = None
    ) -> Emoji:
        """Rename an emoji or change who can use it.

        Needs Manage Expressions, or Create Expressions for emojis the bot created.

        Discord: https://docs.discord.com/developers/resources/emoji#modify-guild-emoji
        """
        return await self.request(
            MODIFY_GUILD_EMOJI.compile(guild_id=guild_id, emoji_id=emoji_id),
            Emoji,
            body=params,
            reason=reason,
        )

    async def delete(self, guild_id: int, emoji_id: int, *, reason: str | None = None) -> None:
        """Delete a custom emoji.

        Needs Manage Expressions, or Create Expressions for emojis the bot created.

        Discord: https://docs.discord.com/developers/resources/emoji#delete-guild-emoji
        """
        await self.request_empty(
            DELETE_GUILD_EMOJI.compile(guild_id=guild_id, emoji_id=emoji_id), reason=reason
        )

    async def list_for_application(self, application_id: int) -> builtins.list[Emoji]:
        """List the app's own emojis, which it can use in any guild.

        Discord: https://docs.discord.com/developers/resources/emoji#list-application-emojis
        """
        response = await self.request(
            LIST_APPLICATION_EMOJIS.compile(application_id=application_id), ApplicationEmojis
        )
        return response.items

    async def get_for_application(self, application_id: int, emoji_id: int) -> Emoji:
        """Get one of the app's emojis.

        Discord: https://docs.discord.com/developers/resources/emoji#get-application-emoji
        """
        return await self.request(
            GET_APPLICATION_EMOJI.compile(application_id=application_id, emoji_id=emoji_id), Emoji
        )

    async def create_for_application(
        self, application_id: int, params: CreateApplicationEmojiParams
    ) -> Emoji:
        """Add an emoji to the app.

        Discord: https://docs.discord.com/developers/resources/emoji#create-application-emoji
        """
        return await self.request(
            CREATE_APPLICATION_EMOJI.compile(application_id=application_id), Emoji, body=params
        )

    async def edit_for_application(
        self, application_id: int, emoji_id: int, params: EditApplicationEmojiParams
    ) -> Emoji:
        """Rename one of the app's emojis.

        Discord: https://docs.discord.com/developers/resources/emoji#modify-application-emoji
        """
        return await self.request(
            MODIFY_APPLICATION_EMOJI.compile(application_id=application_id, emoji_id=emoji_id),
            Emoji,
            body=params,
        )

    async def delete_for_application(self, application_id: int, emoji_id: int) -> None:
        """Delete one of the app's emojis.

        Discord: https://docs.discord.com/developers/resources/emoji#delete-application-emoji
        """
        await self.request_empty(
            DELETE_APPLICATION_EMOJI.compile(application_id=application_id, emoji_id=emoji_id)
        )
