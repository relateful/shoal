"""Emojis.

Discord: https://docs.discord.com/developers/resources/emoji
"""

from typing import Final

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
from shoal.payloads.api import ImageData, data_uri
from shoal.payloads.base import Payload
from shoal.payloads.user import User

APPLICATION_MAX_EMOJIS: Final = 2000
"""How many emojis an application can own.

Discord: https://docs.discord.com/developers/resources/emoji#emoji-object-applicationowned-emoji
"""

EMOJI_MAX_SIZE: Final = 256 * 1024
"""The largest emoji image, in bytes, still or animated.

Discord: https://docs.discord.com/developers/resources/emoji#create-application-emoji
"""


def emoji_data(image: bytes) -> ImageData:
    """Encode an emoji image as the data URI Discord expects, with the content type its bytes show.

    Emojis take JPEG, PNG, GIF, WebP and AVIF, more formats than other image data.

    Raises:
        ValueError: `image` is none of those formats, or larger than `EMOJI_MAX_SIZE`.

    Discord: https://docs.discord.com/developers/resources/emoji#emoji-object-emoji-formats
    """
    if len(image) > EMOJI_MAX_SIZE:
        msg = f"an emoji image is at most {EMOJI_MAX_SIZE // 1024} KiB, not {len(image) / 1024:.0f} KiB"
        raise ValueError(msg)
    content_type = emoji_content_type(image)
    if content_type is None:
        msg = "an emoji image must be a JPEG, PNG, GIF, WebP or AVIF"
        raise ValueError(msg)
    return data_uri(content_type, image)


def emoji_content_type(image: bytes) -> str | None:
    """The content type of an emoji image, read from its first bytes; `None` for other formats."""
    if image.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if image.startswith(b"RIFF") and image[8:12] == b"WEBP":
        return "image/webp"
    if image[4:8] == b"ftyp" and image[8:12] in {b"avif", b"avis"}:
        return "image/avif"
    return None


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
