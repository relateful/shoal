"""Endpoints for stickers and sticker packs.

Discord: https://docs.discord.com/developers/resources/sticker
"""

import builtins

from shoal.payloads.sticker import (
    CreateStickerParams,
    EditStickerParams,
    Sticker,
    StickerPack,
    StickerPacks,
)
from shoal.rest.endpoints import (
    CREATE_GUILD_STICKER,
    DELETE_GUILD_STICKER,
    GET_GUILD_STICKER,
    GET_STICKER,
    GET_STICKER_PACK,
    LIST_GUILD_STICKERS,
    LIST_STICKER_PACKS,
    MODIFY_GUILD_STICKER,
)
from shoal.rest.files import File
from shoal.rest.requester import Resource, form_of


class Stickers(Resource):
    """Stickers and sticker packs.

    Use it as `rest.stickers`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def get_any(self, sticker_id: int) -> Sticker:
        """Get any sticker by ID.

        Discord: https://docs.discord.com/developers/resources/sticker#get-sticker
        """
        return await self.request(GET_STICKER.compile(sticker_id=sticker_id), Sticker)

    async def list_packs(self) -> builtins.list[StickerPack]:
        """List the packs of standard stickers.

        Discord: https://docs.discord.com/developers/resources/sticker#list-sticker-packs
        """
        response = await self.request(LIST_STICKER_PACKS.compile(), StickerPacks)
        return response.sticker_packs

    async def get_pack(self, pack_id: int) -> StickerPack:
        """Get one pack of standard stickers.

        Discord: https://docs.discord.com/developers/resources/sticker#get-sticker-pack
        """
        return await self.request(GET_STICKER_PACK.compile(pack_id=pack_id), StickerPack)

    async def list(self, guild_id: int) -> builtins.list[Sticker]:
        """List a guild's stickers. `user` is set with Create or Manage Expressions.

        Discord: https://docs.discord.com/developers/resources/sticker#list-guild-stickers
        """
        return await self.request(LIST_GUILD_STICKERS.compile(guild_id=guild_id), list[Sticker])

    async def get(self, guild_id: int, sticker_id: int) -> Sticker:
        """Get one of a guild's stickers.

        Discord: https://docs.discord.com/developers/resources/sticker#get-guild-sticker
        """
        return await self.request(
            GET_GUILD_STICKER.compile(guild_id=guild_id, sticker_id=sticker_id), Sticker
        )

    async def create(
        self, guild_id: int, params: CreateStickerParams, file: File, *, reason: str | None = None
    ) -> Sticker:
        """Upload a sticker to a guild. Needs Create Expressions.

        `file` is a PNG, APNG, GIF or Lottie JSON file of at most 512 KiB and 320x320 pixels, and
        at most 5 seconds when animated. Lottie stickers need a verified or partnered guild.

        Discord: https://docs.discord.com/developers/resources/sticker#create-guild-sticker
        """
        return await self.request(
            CREATE_GUILD_STICKER.compile(guild_id=guild_id),
            Sticker,
            files={"file": file},
            form=form_of(params),
            reason=reason,
        )

    async def edit(
        self, guild_id: int, sticker_id: int, params: EditStickerParams, *, reason: str | None = None
    ) -> Sticker:
        """Change a sticker's name, description or tags.

        Needs Manage Expressions, or Create Expressions for stickers the bot created.

        Discord: https://docs.discord.com/developers/resources/sticker#modify-guild-sticker
        """
        return await self.request(
            MODIFY_GUILD_STICKER.compile(guild_id=guild_id, sticker_id=sticker_id),
            Sticker,
            body=params,
            reason=reason,
        )

    async def delete(self, guild_id: int, sticker_id: int, *, reason: str | None = None) -> None:
        """Delete a guild sticker.

        Needs Manage Expressions, or Create Expressions for stickers the bot created.

        Discord: https://docs.discord.com/developers/resources/sticker#delete-guild-sticker
        """
        await self.request_empty(
            DELETE_GUILD_STICKER.compile(guild_id=guild_id, sticker_id=sticker_id), reason=reason
        )
