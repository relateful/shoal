"""Custom emojis: a guild's own (or the application's) images usable in messages and reactions.

    emoji = client.get_emoji(emoji_id)
    await message.add_reaction(emoji)
    await channel.send(f"Nice {emoji}")

Discord: https://docs.discord.com/developers/resources/emoji#emoji-object
"""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Self, override

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
from shoal.models.asset import Asset
from shoal.models.base import MISSING, Hashable, MissingType
from shoal.models.state import State
from shoal.payloads.emoji import EditEmojiParams
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
            name=UNSET if isinstance(name, MissingType) else name,
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
