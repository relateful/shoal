"""Emojis.

Discord: https://docs.discord.com/developers/resources/emoji
"""

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
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
