"""Guild members: a user, their roles, nickname and timeout in one guild.

    member = guild.get_member(user_id)
    if member and member.guild_permissions.kick_members:
        await member.timeout(timedelta(minutes=10), reason="spam")

Discord: https://docs.discord.com/developers/resources/guild#guild-member-object
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Self, override

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
from shoal.models.asset import Asset
from shoal.models.base import MISSING, Hashable, MissingType, Object, given
from shoal.models.colour import Colour
from shoal.models.defaults import DEFAULT_BAN_MESSAGE_SECONDS
from shoal.models.messageable import Messageable
from shoal.models.permissions import guild_permissions
from shoal.models.state import State
from shoal.models.user import BaseUser, User
from shoal.payloads.gateway_events import Activity, Presence, StatusType
from shoal.payloads.guild import BanParams, EditMemberParams, GuildMember, GuildMemberFlags, PartialMember
from shoal.payloads.permissions import Permissions
from shoal.payloads.user import User as UserPayload
from shoal.payloads.voice import VoiceState

if TYPE_CHECKING:
    from collections.abc import Iterable

    from shoal.models.guild import Guild
    from shoal.models.role import Role


def _timed_out(until: datetime | None, now: datetime) -> bool:
    return until is not None and until > now


class Member(BaseUser, Messageable):
    """A user in a guild. It has every `User` attribute, plus the guild's view of them.

    `send` opens a DM with the user. Role, presence and voice lookups read the cache and return
    nothing (not an error) when it does not hold them.

    Discord: https://docs.discord.com/developers/resources/guild#guild-member-object
    """

    __slots__ = ("_data", "_guild_id", "_presence", "_state", "_user")

    def __init__(
        self, state: State, data: GuildMember, guild_id: int, *, user: UserPayload | None = None
    ) -> None:
        """A member from their payload; `user` is needed when the payload has none (message authors).

        Raises:
            ValueError: Neither the payload nor `user` says who the member is.
        """
        if isinstance(data.user, UserPayload):
            user = data.user
        if user is None:
            msg = "a member needs a user: the payload has none and no user was given"
            raise ValueError(msg)
        self._state: State = state
        self._data: GuildMember = data
        self._guild_id: Snowflake = Snowflake(guild_id)
        self._user: UserPayload = user
        # Read now, so a member is a snapshot: `on_presence_update`'s `before` keeps the old status.
        entry = state.cache.presences.peek((self._guild_id, user.id))
        self._presence: Presence | None = entry.value if entry is not None else None

    @classmethod
    def from_partial(cls, state: State, data: PartialMember, guild_id: int, *, user: UserPayload) -> Self:
        """A member from an interaction's resolved data, which leaves out `deaf` and `mute`.

        Those read as `False`; every other field is kept.
        """
        full = GuildMember(
            user=user,
            nick=data.nick,
            avatar=data.avatar,
            banner=data.banner,
            roles=data.roles,
            joined_at=data.joined_at,
            premium_since=data.premium_since,
            deaf=False,
            mute=False,
            flags=data.flags,
            pending=data.pending,
            permissions=data.permissions,
            communication_disabled_until=data.communication_disabled_until,
            avatar_decoration_data=data.avatar_decoration_data,
            collectibles=data.collectibles,
        )
        return cls(state, full, guild_id)

    @classmethod
    def from_cache(cls, state: State, guild_id: int, user_id: int) -> Self | None:
        """The cached member, if the cache holds them."""
        data = state.cache.peek(state.cache.members, (Snowflake(guild_id), Snowflake(user_id)))
        if data is None:
            return None
        if isinstance(data.user, UnsetType):
            user = state.cache.peek(state.cache.users, Snowflake(user_id))
            return cls(state, data, guild_id, user=user) if user is not None else None
        return cls(state, data, guild_id)

    @property
    @override
    def _user_data(self) -> UserPayload:
        return self._user

    @property
    @override
    def _messageable_state(self) -> State:
        return self._state

    @override
    async def _messageable_channel(self) -> tuple[Snowflake, Snowflake | None]:
        return (await self.user.create_dm()).id, None

    @property
    def payload(self) -> GuildMember:
        """The member as Discord sent them."""
        return self._data

    @property
    def user(self) -> User:
        """The user, outside the guild."""
        return User(self._state, self._user)

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
    def nick(self) -> str | None:
        """The member's nickname in this guild."""
        nick = self._data.nick
        return nick if isinstance(nick, str) else None

    @property
    @override
    def display_name(self) -> str:
        """The name Discord shows in this guild: the nickname, the global name, or the username."""
        return self.nick or super().display_name

    @property
    def guild_avatar(self) -> Asset | None:
        """The avatar the member set for this guild only."""
        avatar = self._data.avatar
        return Asset.for_member_avatar(self._guild_id, self.id, avatar) if isinstance(avatar, str) else None

    @property
    @override
    def display_avatar(self) -> Asset:
        """The avatar Discord shows in this guild: the guild avatar, the user's, or the default."""
        return self.guild_avatar or super().display_avatar

    @property
    def guild_banner(self) -> Asset | None:
        """The banner the member set for this guild only."""
        banner = self._data.banner
        return Asset.for_member_banner(self._guild_id, self.id, banner) if isinstance(banner, str) else None

    @property
    def joined_at(self) -> datetime | None:
        """When they joined; `None` for guest members of voice channels."""
        return self._data.joined_at

    @property
    def premium_since(self) -> datetime | None:
        """When they started boosting the guild."""
        since = self._data.premium_since
        return since if isinstance(since, datetime) else None

    @property
    def pending(self) -> bool:
        """Whether they have not passed Membership Screening yet."""
        return self._data.pending is True

    @property
    def flags(self) -> GuildMemberFlags:
        """The member's flags."""
        return self._data.flags

    @property
    def timed_out_until(self) -> datetime | None:
        """When their timeout ends, while they are timed out."""
        until = self._data.communication_disabled_until
        until = until if isinstance(until, datetime) else None
        return until if _timed_out(until, self._state.now()) else None

    def is_timed_out(self) -> bool:
        """Whether they are timed out right now."""
        return self.timed_out_until is not None

    def has_role(self, role: int | str, /) -> bool:
        """Whether they have `role`, given by ID or by name."""
        if isinstance(role, int):
            return role in self._data.roles
        return any(found.name == role for found in self.roles)

    @property
    def raw_roles(self) -> list[Snowflake]:
        """The IDs of their roles, without @everyone."""
        return list(self._data.roles)

    @property
    def roles(self) -> "list[Role]":
        """Their cached roles, lowest first, starting with @everyone."""
        from shoal.models.role import Role

        found = [Role.from_cache(self._state, role_id) for role_id in (self._guild_id, *self._data.roles)]
        return sorted((role for role in found if role is not None), key=Role.sort_key)

    @property
    def top_role(self) -> "Role | None":
        """Their highest cached role."""
        roles = self.roles
        return roles[-1] if roles else None

    @property
    def colour(self) -> Colour:
        """The colour of their name: their highest coloured role's, or 0."""
        for role in reversed(self.roles):
            if role.colour:
                return role.colour
        return Colour.default()

    color = colour

    @property
    def guild_permissions(self) -> Permissions:
        """Their permissions across the guild, from the cached guild and roles.

        Ignores channel overwrites; use `channel.permissions_for(member)` for one channel. Without
        the guild in the cache, only what their cached roles grant is counted.
        """
        guild = self._state.cache.peek(self._state.cache.guilds, self._guild_id)
        role_ids: Iterable[Snowflake] = (self._guild_id, *self._data.roles)
        roles = {
            role_id: role
            for role_id in role_ids
            if (role := self._state.cache.peek(self._state.cache.roles, role_id))
        }
        return guild_permissions(
            guild_id=self._guild_id,
            owner_id=guild.owner_id if guild is not None else 0,
            user_id=self.id,
            role_permissions={role_id: role.permissions for role_id, role in roles.items()},
            member_roles=self._data.roles,
            timed_out=self.is_timed_out(),
        )

    @property
    def voice(self) -> VoiceState | None:
        """Their voice state, while they are in one of the guild's voice channels."""
        return self._state.cache.peek(self._state.cache.voice_states, (self._guild_id, self.id))

    @property
    def status(self) -> StatusType:
        """Their status when this object was made; `OFFLINE` when unknown (needs Guild Presences)."""
        presence = self._presence
        return presence.status if presence is not None else StatusType.OFFLINE

    @property
    def activities(self) -> list[Activity]:
        """What they are doing, from their presence."""
        presence = self._presence
        return list(presence.activities) if presence is not None else []

    async def edit(
        self,
        *,
        nick: str | MissingType | None = MISSING,
        roles: "Iterable[Hashable] | MissingType" = MISSING,
        mute: bool | MissingType = MISSING,
        deafen: bool | MissingType = MISSING,
        voice_channel: Hashable | MissingType | None = MISSING,
        timed_out_until: datetime | MissingType | None = MISSING,
        reason: str | None = None,
    ) -> "Member":
        """Change the member. Leave a keyword out to keep it.

        `None` clears a nickname, disconnects from voice, or ends a timeout.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild-member
        """
        params = EditMemberParams(
            nick=given(nick),
            roles=UNSET if isinstance(roles, MissingType) else [role.id for role in roles],
            mute=given(mute),
            deaf=given(deafen),
            channel_id=(
                UNSET
                if isinstance(voice_channel, MissingType)
                else None
                if voice_channel is None
                else voice_channel.id
            ),
            communication_disabled_until=UNSET
            if isinstance(timed_out_until, MissingType)
            else timed_out_until,
        )
        data = await self._state.rest.members.edit(self._guild_id, self.id, params, reason=reason)
        return Member(self._state, data, self._guild_id, user=self._user)

    async def add_roles(self, *roles: Hashable, reason: str | None = None, atomic: bool = True) -> None:
        """Give the member roles.

        With `atomic` (the default) each role is added on its own, so roles changed elsewhere at the
        same time are kept; without it, the cached role list plus these is written in one request.

        Discord: https://docs.discord.com/developers/resources/guild#add-guild-member-role
        """
        if not atomic:
            wanted = [*self._data.roles, *(role.id for role in roles if role.id not in self._data.roles)]
            await self.edit(roles=[Object(role_id) for role_id in wanted], reason=reason)
            return
        for role in roles:
            await self._state.rest.members.add_role(self._guild_id, self.id, role.id, reason=reason)

    async def remove_roles(self, *roles: Hashable, reason: str | None = None, atomic: bool = True) -> None:
        """Take roles from the member; `atomic` works as in `add_roles`.

        Discord: https://docs.discord.com/developers/resources/guild#remove-guild-member-role
        """
        if not atomic:
            removed = {role.id for role in roles}
            await self.edit(
                roles=[Object(role_id) for role_id in self._data.roles if role_id not in removed],
                reason=reason,
            )
            return
        for role in roles:
            await self._state.rest.members.remove_role(self._guild_id, self.id, role.id, reason=reason)

    async def timeout(self, until: timedelta | datetime | None, /, *, reason: str | None = None) -> "Member":
        """Time the member out for a duration or until a moment (up to 28 days); `None` ends it.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild-member
        """
        moment = self._state.now() + until if isinstance(until, timedelta) else until
        return await self.edit(timed_out_until=moment, reason=reason)

    async def move_to(self, channel: Hashable | None, *, reason: str | None = None) -> "Member":
        """Move the member to another voice channel, or disconnect them with `None`.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild-member
        """
        return await self.edit(voice_channel=channel, reason=reason)

    async def kick(self, *, reason: str | None = None) -> None:
        """Remove the member from the guild; they can rejoin with an invite.

        Discord: https://docs.discord.com/developers/resources/guild#remove-guild-member
        """
        await self._state.rest.members.kick(self._guild_id, self.id, reason=reason)

    async def ban(
        self, *, delete_message_seconds: int = DEFAULT_BAN_MESSAGE_SECONDS, reason: str | None = None
    ) -> None:
        """Ban the member.

        Their messages from the last `delete_message_seconds` (up to 7 days) are deleted: one day by
        default.

        Discord: https://docs.discord.com/developers/resources/guild#create-guild-ban
        """
        params = BanParams(delete_message_seconds=delete_message_seconds)
        await self._state.rest.members.ban(self._guild_id, self.id, params, reason=reason)

    async def unban(self, *, reason: str | None = None) -> None:
        """Lift the member's ban.

        Discord: https://docs.discord.com/developers/resources/guild#remove-guild-ban
        """
        await self._state.rest.members.unban(self._guild_id, self.id, reason=reason)

    @override
    def __eq__(self, other: object) -> bool:
        # A member equals the same user's member object in the same guild.
        return isinstance(other, Member) and other.id == self.id and other.guild_id == self._guild_id

    @override
    def __hash__(self) -> int:
        return hash(("Member", int(self._guild_id), int(self.id)))

    @override
    def __repr__(self) -> str:
        return f"<Member id={int(self.id)} name={self.name!r} guild_id={int(self._guild_id)}>"
