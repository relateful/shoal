"""Roles: named sets of permissions, colours and positions in a guild.

    role = guild.get_role(role_id)
    await member.add_roles(role, reason="verified")

Discord: https://docs.discord.com/developers/topics/permissions#role-object
"""

from typing import TYPE_CHECKING, Self, override

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
from shoal.models.asset import Asset
from shoal.models.base import MISSING, Hashable, MissingType, given
from shoal.models.colour import Colour
from shoal.models.state import State
from shoal.payloads.api import image_data
from shoal.payloads.guild import EditRoleParams, RolePositionParams
from shoal.payloads.permissions import Permissions, RoleFlags, RoleTags
from shoal.payloads.permissions import Role as RolePayload

if TYPE_CHECKING:
    from shoal.models.guild import Guild
    from shoal.models.member import Member


class Role(Hashable):
    """A role in a guild. Roles compare by position, as Discord orders them: `role_a > role_b`.

    Discord: https://docs.discord.com/developers/topics/permissions#role-object
    """

    __slots__ = ("_data", "_guild_id", "_state")

    def __init__(self, state: State, data: RolePayload, guild_id: int) -> None:
        """A role of guild `guild_id` from its payload."""
        self._state: State = state
        self._data: RolePayload = data
        self._guild_id: Snowflake = Snowflake(guild_id)

    @classmethod
    def from_cache(cls, state: State, role_id: int) -> Self | None:
        """The cached role with this ID, from whichever guild it belongs to."""
        entry = state.cache.roles.peek(Snowflake(role_id))
        if entry is None or entry.scope is None:
            return None
        data = state.cache.peek(state.cache.roles, Snowflake(role_id))
        return cls(state, data, entry.scope) if data is not None else None

    def sort_key(self) -> tuple[int, int]:
        """Discord's order: by position, then by ID (the older role is lower)."""
        return (self._data.position, int(self.id))

    @property
    @override
    def id(self) -> Snowflake:
        return self._data.id

    @property
    def payload(self) -> RolePayload:
        """The role as Discord sent it."""
        return self._data

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
    def name(self) -> str:
        """The role's name."""
        return self._data.name

    @property
    def colour(self) -> Colour:
        """The role's colour; 0 means no colour."""
        return Colour(self._data.colors.primary_color)

    color = colour

    @property
    def secondary_colour(self) -> Colour | None:
        """The gradient's second colour, for gradient roles."""
        color = self._data.colors.secondary_color
        return None if color is None else Colour(color)

    secondary_color = secondary_colour

    @property
    def hoist(self) -> bool:
        """Whether members with it are listed separately."""
        return self._data.hoist

    @property
    def position(self) -> int:
        """Its place in the role list; higher is more powerful. @everyone is 0."""
        return self._data.position

    @property
    def permissions(self) -> Permissions:
        """What the role grants across the guild."""
        return self._data.permissions

    @property
    def managed(self) -> bool:
        """Whether an integration (a bot, boosting, a subscription) controls it."""
        return self._data.managed

    @property
    def mentionable(self) -> bool:
        """Whether everyone can mention it."""
        return self._data.mentionable

    @property
    def flags(self) -> RoleFlags:
        """The role's flags."""
        return self._data.flags

    @property
    def tags(self) -> RoleTags | None:
        """Why the role exists (a bot, boosting, an integration, a subscription)."""
        tags = self._data.tags
        return None if isinstance(tags, UnsetType) else tags

    @property
    def icon(self) -> Asset | None:
        """The role's icon."""
        icon = self._data.icon
        return Asset.for_role_icon(self.id, icon) if isinstance(icon, str) else None

    @property
    def unicode_emoji(self) -> str | None:
        """The role's emoji, for roles with a unicode emoji instead of an icon."""
        emoji = self._data.unicode_emoji
        return emoji if isinstance(emoji, str) else None

    @property
    def mention(self) -> str:
        """`<@&id>`, or `@everyone` for the default role."""
        return "@everyone" if self.is_default() else f"<@&{int(self.id)}>"

    @property
    def members(self) -> "list[Member]":
        """The cached members who have the role (every cached member, for @everyone)."""
        from shoal.models.member import Member

        everyone = self.is_default()
        return [
            Member(self._state, data, self._guild_id)
            for data in self._state.cache.peek_scoped(self._state.cache.members, self._guild_id)
            if (everyone or self.id in data.roles) and not isinstance(data.user, UnsetType)
        ]

    def is_default(self) -> bool:
        """Whether this is @everyone, whose ID is the guild's."""
        return self.id == self._guild_id

    def is_bot_managed(self) -> bool:
        """Whether it is a bot's own role."""
        return self.tags is not None and not isinstance(self.tags.bot_id, UnsetType)

    def is_premium_subscriber(self) -> bool:
        """Whether it is the guild's Booster role."""
        return self.tags is not None and self.tags.is_premium_subscriber

    def is_integration(self) -> bool:
        """Whether an integration manages it."""
        return self.tags is not None and not isinstance(self.tags.integration_id, UnsetType)

    async def edit(
        self,
        *,
        name: str | MissingType = MISSING,
        permissions: Permissions | MissingType = MISSING,
        colour: int | MissingType = MISSING,
        color: int | MissingType = MISSING,
        hoist: bool | MissingType = MISSING,
        icon: bytes | MissingType | None = MISSING,
        unicode_emoji: str | MissingType | None = MISSING,
        mentionable: bool | MissingType = MISSING,
        position: int | MissingType = MISSING,
        reason: str | None = None,
    ) -> "Role":
        """Change the role. Leave a keyword out to keep it.

        `position` moves the role with a separate request, as Discord orders roles on their own.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild-role
        """
        rest = self._state.rest
        if not isinstance(position, MissingType):
            positions = [RolePositionParams(id=self.id, position=position)]
            await rest.roles.edit_positions(self._guild_id, positions, reason=reason)
        chosen_colour = colour if not isinstance(colour, MissingType) else color
        params = EditRoleParams(
            name=given(name),
            permissions=given(permissions),
            color=given(chosen_colour),
            hoist=given(hoist),
            icon=UNSET if isinstance(icon, MissingType) else None if icon is None else image_data(icon),
            unicode_emoji=given(unicode_emoji),
            mentionable=given(mentionable),
        )
        data = await rest.roles.edit(self._guild_id, self.id, params, reason=reason)
        return Role(self._state, data, self._guild_id)

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete the role.

        Discord: https://docs.discord.com/developers/resources/guild#delete-guild-role
        """
        await self._state.rest.roles.delete(self._guild_id, self.id, reason=reason)

    def __lt__(self, other: "Role") -> bool:
        """Lower in the role list."""
        return self.sort_key() < other.sort_key()

    def __le__(self, other: "Role") -> bool:
        """Lower in the role list, or the same role."""
        return self.sort_key() <= other.sort_key()

    def __gt__(self, other: "Role") -> bool:
        """Higher in the role list."""
        return self.sort_key() > other.sort_key()

    def __ge__(self, other: "Role") -> bool:
        """Higher in the role list, or the same role."""
        return self.sort_key() >= other.sort_key()

    @override
    def __str__(self) -> str:
        return self.name

    @override
    def __repr__(self) -> str:
        return f"<Role id={int(self.id)} name={self.name!r} position={self.position}>"
