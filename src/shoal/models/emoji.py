"""Custom emojis: a guild's own, or the application's, usable in messages, reactions and components.

    emoji = client.get_emoji(emoji_id)
    await message.add_reaction(emoji)
    await channel.send(f"Nice {emoji}")

Anything that takes an emoji takes an `EmojiLike`: a unicode emoji, a guild or application emoji,
or a `PartialEmoji`.

Discord: https://docs.discord.com/developers/resources/emoji#emoji-object
"""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Self, override

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
from shoal.models.asset import Asset
from shoal.models.base import MISSING, Hashable, MissingType, given
from shoal.models.state import State
from shoal.payloads.emoji import EditApplicationEmojiParams, EditEmojiParams, PartialEmoji
from shoal.payloads.emoji import Emoji as EmojiPayload

if TYPE_CHECKING:
    from shoal.models.guild import Guild
    from shoal.models.role import Role
    from shoal.models.user import User


class Emoji(Hashable):
    """A guild's custom emoji. `str(emoji)` is the text that shows it in a message.

    Discord: https://docs.discord.com/developers/resources/emoji#emoji-object
    """

    __slots__ = ("_data", "_guild_id", "_id", "_state")

    def __init__(self, state: State, data: EmojiPayload, guild_id: int) -> None:
        """A custom emoji of guild `guild_id` from its payload.

        Raises:
            ValueError: The payload is a unicode emoji, which has no ID.
        """
        if data.id is None:
            msg = "a unicode emoji is not a custom emoji; send it as a string"
            raise ValueError(msg)
        self._state: State = state
        self._data: EmojiPayload = data
        self._id: Snowflake = data.id
        self._guild_id: Snowflake = Snowflake(guild_id)

    @classmethod
    def from_cache(cls, state: State, emoji_id: int) -> Self | None:
        """The cached custom emoji with this ID, from whichever guild it belongs to."""
        entry = state.cache.emojis.peek(Snowflake(emoji_id))
        if entry is None or entry.scope is None:
            return None
        data = state.cache.peek(state.cache.emojis, Snowflake(emoji_id))
        return cls(state, data, entry.scope) if data is not None else None

    @property
    @override
    def id(self) -> Snowflake:
        return self._id

    @property
    def payload(self) -> EmojiPayload:
        """The emoji as Discord sent it; reaction methods take it too."""
        return self._data

    @property
    def name(self) -> str:
        """The emoji's name, without colons."""
        return self._data.name or ""

    @property
    def animated(self) -> bool:
        """Whether it is animated."""
        return self._data.animated is True

    @property
    def managed(self) -> bool:
        """Whether an integration (such as Twitch) controls it."""
        return self._data.managed is True

    @property
    def available(self) -> bool:
        """`False` after the guild lost the Boosts the emoji needed."""
        return self._data.available is not False

    @property
    def require_colons(self) -> bool:
        """Whether it must be wrapped in colons to be used."""
        return self._data.require_colons is not False

    @property
    def guild_id(self) -> Snowflake:
        """The guild's ID."""
        return self._guild_id

    @property
    def guild(self) -> "Guild | None":
        """The guild, when cached."""
        from shoal.models.guild import Guild

        return Guild.from_cache(self._state, self._guild_id)

    @property
    def roles(self) -> "list[Role]":
        """The cached roles allowed to use it; empty means everyone."""
        from shoal.models.role import Role

        ids = self._data.roles if not isinstance(self._data.roles, UnsetType) else []
        found = (Role.from_cache(self._state, role_id) for role_id in ids)
        return [role for role in found if role is not None]

    @property
    def user(self) -> "User | None":
        """Who uploaded it, when Discord said (it needs Manage Expressions)."""
        from shoal.models.user import User

        uploader = self._data.user
        return None if isinstance(uploader, UnsetType) else User(self._state, uploader)

    @property
    def url(self) -> str:
        """The emoji's image."""
        return Asset.for_emoji(self._id, animated=self.animated).url

    async def edit(
        self,
        *,
        name: str | MissingType = MISSING,
        roles: Iterable[Hashable] | MissingType | None = MISSING,
        reason: str | None = None,
    ) -> "Emoji":
        """Rename the emoji or limit it to roles (`None` or an empty list: everyone).

        Discord: https://docs.discord.com/developers/resources/emoji#modify-guild-emoji
        """
        params = EditEmojiParams(
            name=given(name),
            roles=UNSET
            if isinstance(roles, MissingType)
            else None
            if roles is None
            else [role.id for role in roles],
        )
        data = await self._state.rest.emojis.edit(self._guild_id, self._id, params, reason=reason)
        return Emoji(self._state, data, self._guild_id)

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete the emoji.

        Discord: https://docs.discord.com/developers/resources/emoji#delete-guild-emoji
        """
        await self._state.rest.emojis.delete(self._guild_id, self._id, reason=reason)

    @override
    def __str__(self) -> str:
        prefix = "a" if self.animated else ""
        return f"<{prefix}:{self.name}:{int(self._id)}>"

    @override
    def __repr__(self) -> str:
        return f"<Emoji id={int(self._id)} name={self.name!r} animated={self.animated}>"


class AppEmoji(Hashable):
    """An emoji the application owns, usable in every guild without Use External Emojis.

    `str(emoji)` is the text that shows it in a message. Look them up by name through
    `client.app_emojis`.

    Discord: https://docs.discord.com/developers/resources/emoji#emoji-object-applicationowned-emoji
    """

    __slots__ = ("_application_id", "_data", "_id", "_state")

    def __init__(self, state: State, data: EmojiPayload, application_id: int) -> None:
        """An emoji of application `application_id` from its payload.

        Raises:
            ValueError: The payload has no ID or no name, so it is not an application emoji.
        """
        if data.id is None or data.name is None:
            msg = "an application emoji has an ID and a name"
            raise ValueError(msg)
        self._state: State = state
        self._data: EmojiPayload = data
        self._id: Snowflake = data.id
        self._application_id: Snowflake = Snowflake(application_id)

    @property
    @override
    def id(self) -> Snowflake:
        return self._id

    @property
    def application_id(self) -> Snowflake:
        """The ID of the application that owns it."""
        return self._application_id

    @property
    def payload(self) -> EmojiPayload:
        """The emoji as Discord sent it."""
        return self._data

    @property
    def name(self) -> str:
        """The emoji's name, without colons."""
        return self._data.name or ""

    @property
    def animated(self) -> bool:
        """Whether it is animated."""
        return self._data.animated is True

    @property
    def url(self) -> str:
        """The emoji's image."""
        return Asset.for_emoji(self._id, animated=self.animated).url

    async def edit(self, *, name: str) -> "AppEmoji":
        """Rename the emoji.

        Discord: https://docs.discord.com/developers/resources/emoji#modify-application-emoji
        """
        params = EditApplicationEmojiParams(name=name)
        data = await self._state.rest.emojis.edit_for_application(self._application_id, self._id, params)
        return AppEmoji(self._state, data, self._application_id)

    async def delete(self) -> None:
        """Delete the emoji.

        Discord: https://docs.discord.com/developers/resources/emoji#delete-application-emoji
        """
        await self._state.rest.emojis.delete_for_application(self._application_id, self._id)

    @override
    def __str__(self) -> str:
        prefix = "a" if self.animated else ""
        return f"<{prefix}:{self.name}:{int(self._id)}>"

    @override
    def __repr__(self) -> str:
        return f"<AppEmoji id={int(self._id)} name={self.name!r} animated={self.animated}>"


type EmojiLike = str | Emoji | AppEmoji | PartialEmoji
"""An emoji to show or react with: a unicode emoji, a guild or application emoji, or a partial one."""


def partial_emoji(emoji: EmojiLike) -> PartialEmoji:
    """`emoji` as components and reactions take it."""
    if isinstance(emoji, str):
        return PartialEmoji(name=emoji)
    if isinstance(emoji, Emoji | AppEmoji):
        return PartialEmoji(id=emoji.id, name=emoji.name, animated=emoji.animated)
    return emoji
