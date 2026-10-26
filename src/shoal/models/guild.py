"""Guilds: a server, with lookups over what the cache holds.

    guild = client.get_guild(guild_id)
    member = guild.get_member(user_id) or await guild.fetch_member(user_id)
    for channel in guild.text_channels:
        ...

The `get_*` methods and list properties read the cache synchronously and never call Discord; the
`fetch_*` methods always call Discord.

Discord: https://docs.discord.com/developers/resources/guild#guild-object
"""

from collections.abc import AsyncIterator, Iterable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Final, Self, override

from msgspec import UNSET, UnsetType

from shoal.cache.guild import CachedGuild
from shoal.core.snowflake import Snowflake
from shoal.models.asset import Asset
from shoal.models.base import MISSING, Hashable, MissingType, given, unset_if_none
from shoal.models.defaults import DEFAULT_BAN_MESSAGE_SECONDS
from shoal.models.state import State
from shoal.payloads.api import image_data
from shoal.payloads.channel import ChannelType, CreateChannelParams, PartialOverwrite
from shoal.payloads.emoji import CreateEmojiParams
from shoal.payloads.gateway_events import MEMBER_QUERY_MAX_RESULTS
from shoal.payloads.guild import (
    LIST_BANS_MAX_LIMIT,
    LIST_MEMBERS_MAX_LIMIT,
    Ban,
    BanParams,
    CreateRoleParams,
    EditGuildParams,
    GetPruneCountParams,
    GuildFeature,
    ListBansParams,
    ListMembersParams,
    MFALevel,
    PremiumTier,
    PruneParams,
    VerificationLevel,
)
from shoal.payloads.guild import (
    Guild as GuildPayload,
)
from shoal.payloads.invite import GuildInvite
from shoal.payloads.permissions import Permissions
from shoal.payloads.scheduled_event import GuildScheduledEvent
from shoal.payloads.soundboard import SoundboardSound
from shoal.payloads.stage_instance import StageInstance
from shoal.payloads.sticker import Sticker
from shoal.payloads.webhook import Webhook

LEGACY_DISCRIMINATOR_LENGTH: Final = 4
"""Digits in a discriminator from before the new username system."""

if TYPE_CHECKING:
    from shoal.models.channel import (
        AnyGuildChannel,
        CategoryChannel,
        ForumChannel,
        StageChannel,
        TextChannel,
        VoiceChannel,
    )
    from shoal.models.emoji import Emoji
    from shoal.models.member import Member
    from shoal.models.role import Role
    from shoal.models.thread import Thread


class Guild(Hashable):
    """A guild (server).

    Discord: https://docs.discord.com/developers/resources/guild#guild-object
    """

    __slots__ = ("_data", "_state")

    def __init__(self, state: State, data: GuildPayload) -> None:
        """A guild from its payload (a REST answer, or a cached guild)."""
        self._state: State = state
        self._data: GuildPayload = data

    @classmethod
    def from_cache(cls, state: State, guild_id: int) -> Self | None:
        """The cached guild with this ID."""
        data = state.cache.peek(state.cache.guilds, Snowflake(guild_id))
        return cls(state, data) if data is not None else None

    @property
    @override
    def id(self) -> Snowflake:
        return self._data.id

    @property
    def payload(self) -> GuildPayload:
        """The guild as Discord sent it (cached guilds have no roles, emojis or stickers in it)."""
        return self._data

    @property
    def name(self) -> str:
        """The guild's name."""
        return self._data.name

    @property
    def description(self) -> str | None:
        """The description shown in discovery and invites."""
        return self._data.description

    @property
    def icon(self) -> Asset | None:
        """The guild's icon."""
        return Asset.for_guild_icon(self.id, self._data.icon) if self._data.icon else None

    @property
    def banner(self) -> Asset | None:
        """The guild's banner."""
        return Asset.for_banner(self.id, self._data.banner) if self._data.banner else None

    @property
    def splash(self) -> Asset | None:
        """The invite splash image."""
        return Asset.for_guild_splash(self.id, self._data.splash) if self._data.splash else None

    @property
    def discovery_splash(self) -> Asset | None:
        """The discovery splash image."""
        splash = self._data.discovery_splash
        return Asset.for_discovery_splash(self.id, splash) if splash else None

    @property
    def owner_id(self) -> Snowflake:
        """Who owns the guild."""
        return self._data.owner_id

    @property
    def owner(self) -> "Member | None":
        """The owner, when cached."""
        return self.get_member(self.owner_id)

    @property
    def features(self) -> list[GuildFeature]:
        """What the guild has enabled (community, discovery, vanity URL...)."""
        return list(self._data.features)

    @property
    def premium_tier(self) -> PremiumTier:
        """The Boost level."""
        return self._data.premium_tier

    @property
    def premium_subscription_count(self) -> int:
        """How many Boosts the guild has."""
        count = self._data.premium_subscription_count
        return count if isinstance(count, int) else 0

    @property
    def preferred_locale(self) -> str:
        """The guild's language, as a Discord locale."""
        return self._data.preferred_locale

    @property
    def verification_level(self) -> VerificationLevel:
        """What members must have verified before they can talk."""
        return self._data.verification_level

    @property
    def mfa_level(self) -> MFALevel:
        """Whether moderators need two-factor authentication."""
        return self._data.mfa_level

    @property
    def vanity_url_code(self) -> str | None:
        """The vanity invite code, for guilds that have one."""
        return self._data.vanity_url_code

    @property
    def afk_timeout(self) -> int:
        """Seconds of silence before a member is moved to the AFK channel."""
        return self._data.afk_timeout

    @property
    def member_count(self) -> int | None:
        """How many members the guild has; known for guilds the bot received from the gateway."""
        if isinstance(self._data, CachedGuild) and isinstance(self._data.member_count, int):
            return self._data.member_count
        approximate = self._data.approximate_member_count
        return approximate if isinstance(approximate, int) else None

    @property
    def large(self) -> bool:
        """Whether Discord considers the guild large (it then sends fewer members at startup)."""
        return isinstance(self._data, CachedGuild) and self._data.large is True

    @property
    def joined_at(self) -> datetime | None:
        """When the bot joined."""
        if isinstance(self._data, CachedGuild) and isinstance(self._data.joined_at, datetime):
            return self._data.joined_at
        return None

    async def chunk(self, *, presences: bool = False) -> "list[Member]":
        """Fetch every member over the gateway and return them, caching them as they arrive.

        Members cached earlier who are not in the list (they left while the bot was not told) are
        dropped from the cache. Needs the Server Members intent, and a connected client. Concurrent
        calls share one request. With `presences`, their presences come too (Presence intent).

        Raises:
            GatewayRequiredError: The guild's shard is not connected here.
            MemberRequestRateLimitedError: Discord refused the request for now.
            TimeoutError: The members did not all arrive in time.

        Discord: https://docs.discord.com/developers/events/gateway-events#request-guild-members
        """
        from shoal.models.member import Member

        found = await self._state.member_requests.request_members(
            self.id, query="", limit=0, user_ids=None, presences=presences
        )
        return [Member(self._state, data, self.id) for data in found if not isinstance(data.user, UnsetType)]

    async def query_members(
        self,
        query: str | None = None,
        *,
        limit: int = 5,
        user_ids: Sequence[int] | None = None,
        presences: bool = False,
    ) -> "list[Member]":
        """Members whose username starts with `query`, or the members `user_ids` names, over the gateway.

        Discord returns at most 100; `limit` (default 5) applies to `query`.

        Raises:
            ValueError: Neither or both of `query` and `user_ids`, an empty `query`, or no `user_ids`.
            GatewayRequiredError: The guild's shard is not connected here.
            MemberRequestRateLimitedError: Discord refused the request for now.
            TimeoutError: The answer did not arrive in time.

        Discord: https://docs.discord.com/developers/events/gateway-events#request-guild-members
        """
        from shoal.models.member import Member

        if (query is None) == (user_ids is None):
            msg = "pass either query or user_ids"
            raise ValueError(msg)
        if query == "":
            msg = "an empty query asks for every member: use guild.chunk()"
            raise ValueError(msg)
        if user_ids is not None and not user_ids:
            msg = "user_ids needs at least one ID"
            raise ValueError(msg)
        found = await self._state.member_requests.request_members(
            self.id,
            query=query,
            limit=min(MEMBER_QUERY_MAX_RESULTS, limit or 5),
            user_ids=None if user_ids is None else list(user_ids),
            presences=presences,
        )
        return [Member(self._state, data, self.id) for data in found if not isinstance(data.user, UnsetType)]

    @property
    def members(self) -> "list[Member]":
        """Every cached member. Complete only with the Guild Members intent and after chunking."""
        from shoal.models.member import Member

        members = self._state.cache.peek_scoped(self._state.cache.members, self.id)
        return [
            Member(self._state, data, self.id) for data in members if not isinstance(data.user, UnsetType)
        ]

    def get_member(self, user_id: int, /) -> "Member | None":
        """The cached member with this ID."""
        from shoal.models.member import Member

        return Member.from_cache(self._state, self.id, user_id)

    def get_member_named(self, name: str, /) -> "Member | None":
        """A cached member by name.

        `name#discriminator` (or `name#0`) matches the username and discriminator exactly; anything
        else matches a nickname, a global name or a username, in that order of preference.
        """
        members = self.members
        username, _, discriminator = name.rpartition("#")
        legacy = len(discriminator) == LEGACY_DISCRIMINATOR_LENGTH and discriminator.isdigit()
        if username and (discriminator == "0" or legacy):
            for member in members:
                if member.name == username and member.discriminator == discriminator:
                    return member
            return None
        for member in members:
            if member.nick == name:
                return member
        for member in members:
            if member.global_name == name:
                return member
        for member in members:
            if member.name == name:
                return member
        return None

    @property
    def me(self) -> "Member | None":
        """The bot's own member, when cached."""
        user_id = self._state.user_id
        return self.get_member(user_id) if user_id is not None else None

    async def fetch_member(self, user_id: int, /) -> "Member":
        """Get a member from Discord.

        Raises:
            NotFoundError: They are not in the guild.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-member
        """
        from shoal.models.member import Member

        return Member(self._state, await self._state.rest.members.get(self.id, user_id), self.id)

    async def fetch_members(
        self, *, limit: int | None = 1000, after: int | None = None
    ) -> "AsyncIterator[Member]":
        """Iterate over every member from Discord, in ID order, a page of 1,000 at a time.

        Needs the Guild Members intent enabled for the application.

        Discord: https://docs.discord.com/developers/resources/guild#list-guild-members
        """
        from shoal.models.member import Member

        remaining = limit
        cursor = Snowflake(after or 0)
        while remaining is None or remaining > 0:
            size = LIST_MEMBERS_MAX_LIMIT if remaining is None else min(remaining, LIST_MEMBERS_MAX_LIMIT)
            page = await self._state.rest.members.list(self.id, ListMembersParams(limit=size, after=cursor))
            for data in page:
                yield Member(self._state, data, self.id)
            if remaining is not None:
                remaining -= len(page)
            if len(page) < size:
                return
            last = page[-1].user
            if isinstance(last, UnsetType):
                return
            cursor = last.id

    @property
    def roles(self) -> "list[Role]":
        """The cached roles, lowest first, starting with @everyone."""
        from shoal.models.role import Role

        roles = [
            Role(self._state, data, self.id)
            for data in self._state.cache.peek_scoped(self._state.cache.roles, self.id)
        ]
        return sorted(roles, key=Role.sort_key)

    def get_role(self, role_id: int, /) -> "Role | None":
        """The cached role with this ID, if it is one of this guild's."""
        from shoal.models.role import Role

        role = Role.from_cache(self._state, role_id)
        return role if role is not None and role.guild_id == self.id else None

    @property
    def default_role(self) -> "Role | None":
        """@everyone, whose ID is the guild's."""
        return self.get_role(self.id)

    @property
    def premium_subscriber_role(self) -> "Role | None":
        """The role Boosters get."""
        return next((role for role in self.roles if role.is_premium_subscriber()), None)

    async def fetch_roles(self) -> "list[Role]":
        """Get the roles from Discord.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-roles
        """
        from shoal.models.role import Role

        roles = [Role(self._state, data, self.id) for data in await self._state.rest.roles.list(self.id)]
        return sorted(roles, key=Role.sort_key)

    async def create_role(
        self,
        *,
        name: str | MissingType = MISSING,
        permissions: Permissions | MissingType = MISSING,
        colour: int | MissingType = MISSING,
        color: int | MissingType = MISSING,
        hoist: bool = False,
        mentionable: bool = False,
        reason: str | None = None,
    ) -> "Role":
        """Create a role; Discord names it "new role" when `name` is left out.

        Discord: https://docs.discord.com/developers/resources/guild#create-guild-role
        """
        from shoal.models.role import Role

        chosen = colour if not isinstance(colour, MissingType) else color
        params = CreateRoleParams(
            name=given(name),
            permissions=given(permissions),
            color=given(chosen),
            hoist=hoist,
            mentionable=mentionable,
        )
        return Role(self._state, await self._state.rest.roles.create(self.id, params, reason=reason), self.id)

    @property
    def channels(self) -> "list[AnyGuildChannel]":
        """The cached channels (threads aside), in channel list order."""
        from shoal.models.channel import guild_channels

        return sorted(
            guild_channels(self._state, self.id), key=lambda channel: (channel.position, int(channel.id))
        )

    @property
    def text_channels(self) -> "list[TextChannel]":
        """The cached text and announcement channels."""
        from shoal.models.channel import TextChannel

        return [channel for channel in self.channels if isinstance(channel, TextChannel)]

    @property
    def voice_channels(self) -> "list[VoiceChannel]":
        """The cached voice channels (not stages)."""
        from shoal.models.channel import VoiceChannel

        return [channel for channel in self.channels if type(channel) is VoiceChannel]

    @property
    def stage_channels(self) -> "list[StageChannel]":
        """The cached stage channels."""
        from shoal.models.channel import StageChannel

        return [channel for channel in self.channels if isinstance(channel, StageChannel)]

    @property
    def categories(self) -> "list[CategoryChannel]":
        """The cached categories."""
        from shoal.models.channel import CategoryChannel

        return [channel for channel in self.channels if isinstance(channel, CategoryChannel)]

    @property
    def forums(self) -> "list[ForumChannel]":
        """The cached forum and media channels."""
        from shoal.models.channel import ForumChannel

        return [channel for channel in self.channels if isinstance(channel, ForumChannel)]

    @property
    def threads(self) -> "list[Thread]":
        """The cached active threads."""
        from shoal.models.channel import guild_threads

        return guild_threads(self._state, self.id)

    def get_channel(self, channel_id: int, /) -> "AnyGuildChannel | None":
        """The cached channel with this ID (threads aside)."""
        from shoal.models.channel import GuildChannel, resolve_cached_channel

        channel = resolve_cached_channel(self._state, channel_id)
        return channel if isinstance(channel, GuildChannel) and channel.guild_id == self.id else None

    def get_thread(self, thread_id: int, /) -> "Thread | None":
        """The cached active thread with this ID."""
        from shoal.models.channel import resolve_cached_channel
        from shoal.models.thread import Thread

        thread = resolve_cached_channel(self._state, thread_id)
        return thread if isinstance(thread, Thread) and thread.guild_id == self.id else None

    def get_channel_or_thread(self, channel_id: int, /) -> "AnyGuildChannel | Thread | None":
        """The cached channel or thread with this ID."""
        return self.get_channel(channel_id) or self.get_thread(channel_id)

    @property
    def system_channel(self) -> "TextChannel | None":
        """Where Discord posts join and boost messages."""
        return self._text_channel(self._data.system_channel_id)

    @property
    def rules_channel(self) -> "TextChannel | None":
        """The community rules channel."""
        return self._text_channel(self._data.rules_channel_id)

    @property
    def public_updates_channel(self) -> "TextChannel | None":
        """Where Discord posts notices for community moderators."""
        return self._text_channel(self._data.public_updates_channel_id)

    @property
    def afk_channel(self) -> "VoiceChannel | None":
        """Where idle members are moved."""
        from shoal.models.channel import VoiceChannel

        channel = self.get_channel(self._data.afk_channel_id) if self._data.afk_channel_id else None
        return channel if isinstance(channel, VoiceChannel) else None

    def _text_channel(self, channel_id: Snowflake | None) -> "TextChannel | None":
        from shoal.models.channel import TextChannel

        channel = self.get_channel(channel_id) if channel_id is not None else None
        return channel if isinstance(channel, TextChannel) else None

    async def fetch_channels(self) -> "list[AnyGuildChannel | Thread]":
        """Get the channels from Discord (the ones the bot can view).

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-channels
        """
        from shoal.models.channel import GuildChannel, channel_from_payload
        from shoal.models.thread import Thread

        found: list[AnyGuildChannel | Thread] = []
        for data in await self._state.rest.channels.list(self.id):
            channel = channel_from_payload(self._state, data)
            if isinstance(channel, GuildChannel | Thread):
                found.append(channel)
        return found

    async def _create_channel[T](self, kind: type[T], params: CreateChannelParams, reason: str | None) -> T:
        from shoal.models.channel import channel_from_payload

        data = await self._state.rest.channels.create(self.id, params, reason=reason)
        channel = channel_from_payload(self._state, data)
        if not isinstance(channel, kind):
            msg = f"Discord created a {data.type!r} channel, not a {kind.__name__}"
            raise TypeError(msg)
        return channel

    async def create_text_channel(
        self,
        name: str,
        *,
        category: Hashable | None = None,
        position: int | None = None,
        topic: str | None = None,
        nsfw: bool | None = None,
        slowmode_delay: int | None = None,
        overwrites: Sequence[PartialOverwrite] = (),
        reason: str | None = None,
    ) -> "TextChannel":
        """Create a text channel.

        Discord: https://docs.discord.com/developers/resources/guild#create-guild-channel
        """
        from shoal.models.channel import TextChannel

        params = CreateChannelParams(
            name=name,
            type=ChannelType.GUILD_TEXT,
            parent_id=_id_or_unset(category),
            position=unset_if_none(position),
            permission_overwrites=list(overwrites) if overwrites else UNSET,
            topic=unset_if_none(topic),
            nsfw=unset_if_none(nsfw),
            rate_limit_per_user=unset_if_none(slowmode_delay),
        )
        return await self._create_channel(TextChannel, params, reason)

    async def create_voice_channel(
        self,
        name: str,
        *,
        category: Hashable | None = None,
        position: int | None = None,
        bitrate: int | None = None,
        user_limit: int | None = None,
        rtc_region: str | None = None,
        overwrites: Sequence[PartialOverwrite] = (),
        reason: str | None = None,
    ) -> "VoiceChannel":
        """Create a voice channel.

        Discord: https://docs.discord.com/developers/resources/guild#create-guild-channel
        """
        from shoal.models.channel import VoiceChannel

        params = CreateChannelParams(
            name=name,
            type=ChannelType.GUILD_VOICE,
            parent_id=_id_or_unset(category),
            position=unset_if_none(position),
            permission_overwrites=list(overwrites) if overwrites else UNSET,
            bitrate=unset_if_none(bitrate),
            user_limit=unset_if_none(user_limit),
            rtc_region=unset_if_none(rtc_region),
        )
        return await self._create_channel(VoiceChannel, params, reason)

    async def create_category(
        self,
        name: str,
        *,
        position: int | None = None,
        overwrites: Sequence[PartialOverwrite] = (),
        reason: str | None = None,
    ) -> "CategoryChannel":
        """Create a category.

        Discord: https://docs.discord.com/developers/resources/guild#create-guild-channel
        """
        from shoal.models.channel import CategoryChannel

        params = CreateChannelParams(
            name=name,
            type=ChannelType.GUILD_CATEGORY,
            position=unset_if_none(position),
            permission_overwrites=list(overwrites) if overwrites else UNSET,
        )
        return await self._create_channel(CategoryChannel, params, reason)

    @property
    def emojis(self) -> "list[Emoji]":
        """The cached custom emojis."""
        from shoal.models.emoji import Emoji

        return [
            Emoji(self._state, data, self.id)
            for data in self._state.cache.peek_scoped(self._state.cache.emojis, self.id)
        ]

    def get_emoji(self, emoji_id: int, /) -> "Emoji | None":
        """The cached custom emoji with this ID."""
        from shoal.models.emoji import Emoji

        emoji = Emoji.from_cache(self._state, emoji_id)
        return emoji if emoji is not None and emoji.guild_id == self.id else None

    async def create_custom_emoji(
        self, *, name: str, image: bytes, roles: Iterable[Hashable] = (), reason: str | None = None
    ) -> "Emoji":
        """Upload a custom emoji (PNG, JPEG or GIF, up to 256 KiB).

        Discord: https://docs.discord.com/developers/resources/emoji#create-guild-emoji
        """
        from shoal.models.emoji import Emoji

        params = CreateEmojiParams(name=name, image=image_data(image), roles=[role.id for role in roles])
        return Emoji(
            self._state, await self._state.rest.emojis.create(self.id, params, reason=reason), self.id
        )

    @property
    def stickers(self) -> list[Sticker]:
        """The cached stickers."""
        return self._state.cache.peek_scoped(self._state.cache.stickers, self.id)

    def get_sticker(self, sticker_id: int, /) -> Sticker | None:
        """The cached sticker with this ID."""
        return next((sticker for sticker in self.stickers if sticker.id == sticker_id), None)

    @property
    def scheduled_events(self) -> list[GuildScheduledEvent]:
        """The cached scheduled events."""
        return self._state.cache.peek_scoped(self._state.cache.scheduled_events, self.id)

    def get_scheduled_event(self, event_id: int, /) -> GuildScheduledEvent | None:
        """The cached scheduled event with this ID."""
        return next((event for event in self.scheduled_events if event.id == event_id), None)

    @property
    def stage_instances(self) -> list[StageInstance]:
        """The cached live stages."""
        return self._state.cache.peek_scoped(self._state.cache.stage_instances, self.id)

    def get_stage_instance(self, stage_instance_id: int, /) -> StageInstance | None:
        """The cached live stage with this ID (the stage instance's, not the channel's)."""
        return next((stage for stage in self.stage_instances if stage.id == stage_instance_id), None)

    @property
    def soundboard_sounds(self) -> list[SoundboardSound]:
        """The cached soundboard sounds."""
        return self._state.cache.peek_scoped(self._state.cache.soundboard_sounds, self.id)

    def get_soundboard_sound(self, sound_id: int, /) -> SoundboardSound | None:
        """The cached soundboard sound with this ID."""
        return next((sound for sound in self.soundboard_sounds if sound.sound_id == sound_id), None)

    async def ban(
        self,
        user: Hashable,
        *,
        delete_message_seconds: int = DEFAULT_BAN_MESSAGE_SECONDS,
        reason: str | None = None,
    ) -> None:
        """Ban a user, who need not be a member.

        Their messages from the last `delete_message_seconds` are deleted: one day by default.

        Discord: https://docs.discord.com/developers/resources/guild#create-guild-ban
        """
        params = BanParams(delete_message_seconds=delete_message_seconds)
        await self._state.rest.members.ban(self.id, user.id, params, reason=reason)

    async def unban(self, user: Hashable, *, reason: str | None = None) -> None:
        """Lift a user's ban.

        Discord: https://docs.discord.com/developers/resources/guild#remove-guild-ban
        """
        await self._state.rest.members.unban(self.id, user.id, reason=reason)

    async def kick(self, user: Hashable, *, reason: str | None = None) -> None:
        """Remove a member from the guild.

        Discord: https://docs.discord.com/developers/resources/guild#remove-guild-member
        """
        await self._state.rest.members.kick(self.id, user.id, reason=reason)

    async def fetch_ban(self, user: Hashable) -> Ban:
        """Get one ban.

        Raises:
            NotFoundError: The user is not banned.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-ban
        """
        return await self._state.rest.members.get_ban(self.id, user.id)

    async def bans(self, *, limit: int | None = 1000) -> AsyncIterator[Ban]:
        """Iterate over the bans, a page of 1,000 at a time.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-bans
        """
        remaining = limit
        after: Snowflake | UnsetType = UNSET
        while remaining is None or remaining > 0:
            size = LIST_BANS_MAX_LIMIT if remaining is None else min(remaining, LIST_BANS_MAX_LIMIT)
            page = await self._state.rest.members.list_bans(self.id, ListBansParams(limit=size, after=after))
            for ban in page:
                yield ban
            if remaining is not None:
                remaining -= len(page)
            if len(page) < size:
                return
            after = page[-1].user.id

    async def estimate_pruned_members(self, *, days: int, roles: Iterable[Hashable] = ()) -> int:
        """How many members a prune would remove.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-prune-count
        """
        params = GetPruneCountParams(days=days, include_roles=[role.id for role in roles] or UNSET)
        return (await self._state.rest.guilds.get_prune_count(self.id, params)).pruned or 0

    async def prune_members(
        self,
        *,
        days: int,
        roles: Iterable[Hashable] = (),
        compute_prune_count: bool = True,
        reason: str | None = None,
    ) -> int | None:
        """Remove members inactive for `days` (and without roles, unless listed in `roles`).

        Discord: https://docs.discord.com/developers/resources/guild#begin-guild-prune
        """
        params = PruneParams(
            days=days,
            include_roles=[role.id for role in roles] or UNSET,
            compute_prune_count=compute_prune_count,
        )
        return (await self._state.rest.guilds.prune(self.id, params, reason=reason)).pruned

    async def invites(self) -> list[GuildInvite]:
        """Every invite to the guild.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-invites
        """
        return await self._state.rest.invites.list(self.id)

    async def webhooks(self) -> list[Webhook]:
        """Every webhook in the guild.

        Discord: https://docs.discord.com/developers/resources/webhook#get-guild-webhooks
        """
        return await self._state.rest.webhooks.list(self.id)

    async def edit(
        self,
        *,
        name: str | MissingType = MISSING,
        description: str | MissingType | None = MISSING,
        icon: bytes | MissingType | None = MISSING,
        banner: bytes | MissingType | None = MISSING,
        verification_level: VerificationLevel | MissingType = MISSING,
        system_channel: Hashable | MissingType | None = MISSING,
        rules_channel: Hashable | MissingType | None = MISSING,
        preferred_locale: str | MissingType = MISSING,
        reason: str | None = None,
    ) -> "Guild":
        """Change the guild's settings. Leave a keyword out to keep it.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild
        """

        def channel(value: Hashable | MissingType | None) -> Snowflake | UnsetType | None:
            return UNSET if isinstance(value, MissingType) else None if value is None else value.id

        def image(value: bytes | MissingType | None) -> str | UnsetType | None:
            return UNSET if isinstance(value, MissingType) else None if value is None else image_data(value)

        params = EditGuildParams(
            name=given(name),
            description=given(description),
            icon=image(icon),
            banner=image(banner),
            verification_level=given(verification_level),
            system_channel_id=channel(system_channel),
            rules_channel_id=channel(rules_channel),
            preferred_locale=given(preferred_locale),
        )
        return Guild(self._state, await self._state.rest.guilds.edit(self.id, params, reason=reason))

    async def leave(self) -> None:
        """Make the bot leave the guild.

        Discord: https://docs.discord.com/developers/resources/user#leave-guild
        """
        await self._state.rest.guilds.leave(self.id)

    @override
    def __str__(self) -> str:
        return self.name

    @override
    def __repr__(self) -> str:
        return f"<Guild id={int(self.id)} name={self.name!r}>"


def _id_or_unset(value: Hashable | None) -> Snowflake | UnsetType:
    return UNSET if value is None else value.id
