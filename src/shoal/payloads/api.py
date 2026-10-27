"""API-wide constants and types: version, base URLs, the required user agent and locales.

Discord: https://docs.discord.com/developers/reference
"""

import base64
from typing import Final

from shoal.core.enums import DiscordStrEnum

API_BASE_URL: Final = "https://discord.com/api"
"""Base URL of the HTTP API, without the version segment.

Discord: https://docs.discord.com/developers/reference
"""

API_VERSION: Final = 10
"""The HTTP and gateway API version Shoal speaks.

Discord: https://docs.discord.com/developers/reference#api-versioning
"""

ATTACHMENT_SCHEME: Final = "attachment://"
"""How an embed or a component refers to a file sent with the same message.

Discord: https://docs.discord.com/developers/reference#uploading-files
"""

AUDIT_LOG_REASON_MAX_LENGTH: Final = 512
"""The longest `X-Audit-Log-Reason` value, in characters, before URL encoding.

Discord: https://docs.discord.com/developers/resources/audit-log#audit-log-entry-object
"""

CDN_BASE_URL: Final = "https://cdn.discordapp.com"
"""Where Discord serves images (avatars, icons, emojis, stickers), without a trailing slash.

Discord: https://docs.discord.com/developers/reference#image-formatting
"""

CDN_IMAGE_MAX_SIZE: Final = 4096
"""The largest image size the CDN serves; sizes are powers of two.

Discord: https://docs.discord.com/developers/reference#image-formatting
"""

CDN_IMAGE_MIN_SIZE: Final = 16
"""The smallest image size the CDN serves; sizes are powers of two.

Discord: https://docs.discord.com/developers/reference#image-formatting
"""

DOCS_BASE_URL: Final = "https://docs.discord.com/developers/"
"""Where Discord publishes its developer documentation; every docs link in Shoal starts with this."""

OAUTH_AUTHORIZE_URL: Final = "https://discord.com/oauth2/authorize"
"""Where a user authorizes an app, or adds a bot to a guild.

Discord: https://docs.discord.com/developers/topics/oauth2#shared-resources-oauth2-urls
"""

USER_AGENT_FORMAT: Final = "DiscordBot ({url}, {version})"
"""The `User-Agent` shape Discord requires on every HTTP request.

Discord: https://docs.discord.com/developers/reference#user-agent
"""


class Locale(DiscordStrEnum):
    """A language Discord's client offers, used for localized command names and a user's locale.

    Discord: https://docs.discord.com/developers/reference#locales
    """

    BULGARIAN = "bg"
    CZECH = "cs"
    DANISH = "da"
    GERMAN = "de"
    GREEK = "el"
    ENGLISH_UK = "en-GB"
    ENGLISH_US = "en-US"
    SPANISH_LATAM = "es-419"
    SPANISH = "es-ES"
    FINNISH = "fi"
    FRENCH = "fr"
    HINDI = "hi"
    CROATIAN = "hr"
    HUNGARIAN = "hu"
    INDONESIAN = "id"
    ITALIAN = "it"
    JAPANESE = "ja"
    KOREAN = "ko"
    LITHUANIAN = "lt"
    DUTCH = "nl"
    NORWEGIAN = "no"
    POLISH = "pl"
    PORTUGUESE_BRAZIL = "pt-BR"
    ROMANIAN = "ro"
    RUSSIAN = "ru"
    SWEDISH = "sv-SE"
    THAI = "th"
    TURKISH = "tr"
    UKRAINIAN = "uk"
    VIETNAMESE = "vi"
    CHINESE_CHINA = "zh-CN"
    CHINESE_TAIWAN = "zh-TW"


type Localizations = dict[Locale, str]
"""Translations of a name or description, keyed by locale.

Discord: https://docs.discord.com/developers/interactions/application-commands#localization
"""


type ImageData = str
"""An image sent inline as a data URI, such as `data:image/png;base64,iVBOR…`. Build one with
`image_data`.

Discord: https://docs.discord.com/developers/reference#image-data
"""

_IMAGE_SIGNATURES: Final = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)
"""The leading bytes of each format image data accepts (JPG, GIF and PNG)."""


def data_uri(content_type: str, data: bytes) -> str:
    """`data` as a base64 data URI of `content_type`, the form Discord takes inline files in."""
    return f"data:{content_type};base64,{base64.b64encode(data).decode()}"


def image_data(image: bytes) -> ImageData:
    """Encode an image as the data URI Discord expects, with the content type its bytes show.

    Raises:
        ValueError: `image` is not a PNG, JPEG or GIF, the only formats Discord accepts as image data.
    """
    for signature, content_type in _IMAGE_SIGNATURES:
        if image.startswith(signature):
            return data_uri(content_type, image)
    msg = "image data must be a PNG, JPEG or GIF"
    raise ValueError(msg)


type SoundData = str
"""A sound sent inline as a data URI, such as `data:audio/ogg;base64,T2dnUw…`. Build one with
`sound_data`.

Discord: https://docs.discord.com/developers/resources/soundboard#create-guild-soundboard-sound-json-params
"""

_SOUND_SIGNATURES: Final = (
    (b"OggS", "audio/ogg"),
    (b"ID3", "audio/mpeg"),
    (b"\xff\xfb", "audio/mpeg"),
    (b"\xff\xf3", "audio/mpeg"),
    (b"\xff\xf2", "audio/mpeg"),
)
"""The leading bytes of Ogg files, and of MP3 files with an ID3 tag or starting on a frame."""


def sound_data(sound: bytes) -> SoundData:
    """Encode a sound as the data URI Discord expects, with the content type its bytes show.

    Raises:
        ValueError: `sound` is not an MP3 or Ogg file, the only formats soundboard sounds accept.
    """
    for signature, content_type in _SOUND_SIGNATURES:
        if sound.startswith(signature):
            return data_uri(content_type, sound)
    msg = "sound data must be an MP3 or Ogg file"
    raise ValueError(msg)
