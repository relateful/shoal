"""Emojis.

Discord: https://docs.discord.com/developers/resources/emoji
"""

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
from shoal.payloads.api import ImageData
from shoal.payloads.base import Payload
from shoal.payloads.user import User


class Emoji(Payload):
    """A custom or unicode emoji.

    `id` is `None` for unicode emoji. `name` can be `None` only for reaction emoji whose custom emoji
    was deleted.

    Discord: https://docs.discord.com/developers/resources/emoji#emoji-object
    """

    id: Snowflake | None
    name: str | None
    roles: list[Snowflake] | UnsetType = UNSET
    user: User | UnsetType = UNSET
    require_colons: bool | UnsetType = UNSET
    managed: bool | UnsetType = UNSET
    animated: bool | UnsetType = UNSET
    available: bool | UnsetType = UNSET


class PartialEmoji(Payload):
    """An emoji shown on a button or select option: a custom emoji's `id`, or a unicode emoji's `name`.

    Discord: https://docs.discord.com/developers/components/reference#button-button-structure
    """

    id: Snowflake | UnsetType | None = UNSET
    """Set for custom emoji."""
    name: str | UnsetType | None = UNSET
    """The emoji itself for unicode emoji; the name for custom emoji."""
    animated: bool | UnsetType = UNSET


class ApplicationEmojis(Payload):
    """The response of List Application Emojis.

    Discord: https://docs.discord.com/developers/resources/emoji#list-application-emojis
    """

    items: list[Emoji]


class CreateEmojiParams(Payload):
    """JSON body of Create Guild Emoji. The image may be at most 256 KiB.

    Discord: https://docs.discord.com/developers/resources/emoji#create-guild-emoji-json-params
    """

    name: str
    image: ImageData
    """The 128x128 emoji image."""
    roles: list[Snowflake]
    """Roles allowed to use the emoji; an empty list lets everyone use it."""


class EditEmojiParams(Payload):
    """JSON body of Modify Guild Emoji.

    Discord: https://docs.discord.com/developers/resources/emoji#modify-guild-emoji-json-params
    """

    name: str | UnsetType = UNSET
    roles: list[Snowflake] | UnsetType | None = UNSET
    """Roles allowed to use the emoji."""


class CreateApplicationEmojiParams(Payload):
    """JSON body of Create Application Emoji. The image may be at most 256 KiB.

    Discord: https://docs.discord.com/developers/resources/emoji#create-application-emoji-json-params
    """

    name: str
    image: ImageData
    """The 128x128 emoji image."""


class EditApplicationEmojiParams(Payload):
    """JSON body of Modify Application Emoji.

    Discord: https://docs.discord.com/developers/resources/emoji#modify-application-emoji-json-params
    """

    name: str
