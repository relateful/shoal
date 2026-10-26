"""Stickers and sticker packs.

Discord: https://docs.discord.com/developers/resources/sticker
"""

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload
from shoal.payloads.user import User


class StickerType(DiscordIntEnum):
    """Where a sticker comes from.

    Discord: https://docs.discord.com/developers/resources/sticker#sticker-object-sticker-types
    """

    STANDARD = 1
    """An official sticker in a pack."""
    GUILD = 2
    """Uploaded to a guild for its members."""


class StickerFormatType(DiscordIntEnum):
    """A sticker's image format.

    Discord: https://docs.discord.com/developers/resources/sticker#sticker-object-sticker-format-types
    """

    PNG = 1
    APNG = 2
    LOTTIE = 3
    GIF = 4


class Sticker(Payload):
    """A sticker that can be sent in messages.

    Discord: https://docs.discord.com/developers/resources/sticker#sticker-object
    """

    id: Snowflake
    pack_id: Snowflake | UnsetType = UNSET
    """For standard stickers, the pack it is from."""
    name: str
    description: str | None
    tags: str
    """Autocomplete tags, up to 200 characters; standard stickers use a comma-separated list."""
    type: StickerType
    format_type: StickerFormatType
    available: bool | UnsetType = UNSET
    """For guild stickers; `False` after the guild loses the Boosts it needed."""
    guild_id: Snowflake | UnsetType = UNSET
    user: User | UnsetType = UNSET
    """Who uploaded a guild sticker; needs Create or Manage Expressions."""
    sort_value: int | UnsetType = UNSET
    """A standard sticker's position in its pack."""


class StickerItem(Payload):
    """The least needed to render a sticker, as messages carry it.

    Discord: https://docs.discord.com/developers/resources/sticker#sticker-item-object
    """

    id: Snowflake
    name: str
    format_type: StickerFormatType


class StickerPack(Payload):
    """A pack of standard stickers.

    Discord: https://docs.discord.com/developers/resources/sticker#sticker-pack-object
    """

    id: Snowflake
    stickers: list[Sticker]
    name: str
    sku_id: Snowflake
    cover_sticker_id: Snowflake | UnsetType = UNSET
    """The sticker shown as the pack's icon."""
    description: str
    banner_asset_id: Snowflake | UnsetType = UNSET


class StickerPacks(Payload):
    """The response of List Sticker Packs.

    Discord: https://docs.discord.com/developers/resources/sticker#list-sticker-packs-response-structure
    """

    sticker_packs: list[StickerPack]


class CreateStickerParams(Payload):
    """Form fields of Create Guild Sticker; the sticker file is passed separately.

    Discord: https://docs.discord.com/developers/resources/sticker#create-guild-sticker-form-params
    """

    name: str
    """2 to 30 characters."""
    description: str
    """Empty, or 2 to 100 characters."""
    tags: str
    """Autocomplete tags, up to 200 characters. Discord's client uses the name of an emoji."""


class EditStickerParams(Payload):
    """JSON body of Modify Guild Sticker.

    Discord: https://docs.discord.com/developers/resources/sticker#modify-guild-sticker-json-params
    """

    name: str | UnsetType = UNSET
    """2 to 30 characters."""
    description: str | UnsetType | None = UNSET
    """2 to 100 characters."""
    tags: str | UnsetType = UNSET
    """Up to 200 characters."""
