"""Threads: conversations branched off a channel, including forum and media posts.

    thread = await message.create_thread(name="Discussion")
    await thread.send("Let's talk here.")
    await thread.edit(archived=True)

Discord: https://docs.discord.com/developers/topics/threads
"""

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, override

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
from shoal.models.base import MISSING, Hashable, MissingType, given
from shoal.models.messageable import Messageable
from shoal.models.permissions import thread_permissions
from shoal.models.state import State
from shoal.payloads.channel import Channel, ChannelType, EditThreadParams, ThreadMember
from shoal.payloads.permissions import Permissions

if TYPE_CHECKING:
    from shoal.models.channel import ForumChannel, TextChannel
    from shoal.models.guild import Guild
    from shoal.models.member import Member
    from shoal.models.message import PartialMessage
    from shoal.models.role import Role


class Thread(Hashable, Messageable):
    """A thread, or a post in a forum or media channel.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object
    """

    __slots__ = ("_data", "_state")

    def __init__(self, state: State, data: Channel) -> None:
        """A thread from its payload."""
        self._state: State = state
        self._data: Channel = data

    @property
    @override
    def id(self) -> Snowflake:
        return self._data.id

    @property
    @override
    def _messageable_state(self) -> State:
        return self._state

    @override
    async def _messageable_channel(self) -> tuple[Snowflake, Snowflake | None]:
        return self.id, self.guild_id

    @property
    def payload(self) -> Channel:
        """The thread as Discord sent it."""
        return self._data

    def get_partial_message(self, message_id: int, /) -> "PartialMessage":
        """A message you only know the ID of: reply to it, edit, delete or react without fetching it."""
        from shoal.models.message import PartialMessage

        return PartialMessage(self._state, self.id, message_id, guild_id=self.guild_id)

    @property
    def type(self) -> ChannelType:
        """Public, private, or announcement thread."""
        return self._data.type

    @property
    def name(self) -> str:
        """The thread's name; empty for a thread whose details Discord hid."""
        return self._data.visible_name or ""

    @property
    def guild_id(self) -> Snowflake:
        """The guild's ID."""
        guild_id = self._data.guild_id
        return guild_id if isinstance(guild_id, Snowflake) else Snowflake(0)

    @property
    def guild(self) -> "Guild | None":
        """The guild, when cached."""
        from shoal.models.guild import Guild

        return Guild.from_cache(self._state, self.guild_id)

    @property
    def parent_id(self) -> Snowflake | None:
        """The channel the thread was started in."""
        parent = self._data.parent_id
        return parent if isinstance(parent, Snowflake) else None

    @property
    def parent(self) -> "TextChannel | ForumChannel | None":
        """The channel the thread was started in, when cached."""
        from shoal.models.channel import ForumChannel, TextChannel, resolve_cached_channel

        parent = resolve_cached_channel(self._state, self.parent_id) if self.parent_id else None
        return parent if isinstance(parent, TextChannel | ForumChannel) else None

    @property
    def owner_id(self) -> Snowflake | None:
        """Who started the thread."""
        owner = self._data.owner_id
        return owner if isinstance(owner, Snowflake) else None

    @property
    def owner(self) -> "Member | None":
        """Who started the thread, when cached."""
        from shoal.models.member import Member

        return Member.from_cache(self._state, self.guild_id, self.owner_id) if self.owner_id else None

    @property
    def archived(self) -> bool:
        """Whether it is archived (closed to new messages until unarchived)."""
        metadata = self._data.thread_metadata
        return not isinstance(metadata, UnsetType) and metadata.archived

    @property
    def locked(self) -> bool:
        """Whether only moderators can unarchive it."""
        metadata = self._data.thread_metadata
        return not isinstance(metadata, UnsetType) and metadata.locked

    @property
    def invitable(self) -> bool:
        """Whether non-moderators can add others to a private thread."""
        metadata = self._data.thread_metadata
        return isinstance(metadata, UnsetType) or metadata.invitable is not False

    @property
    def archive_timestamp(self) -> datetime | None:
        """When it was last archived or unarchived."""
        metadata = self._data.thread_metadata
        return None if isinstance(metadata, UnsetType) else metadata.archive_timestamp

    @property
    def auto_archive_duration(self) -> int:
        """Minutes of inactivity before it archives itself."""
        metadata = self._data.thread_metadata
        return 1440 if isinstance(metadata, UnsetType) else metadata.auto_archive_duration

    @property
    def slowmode_delay(self) -> int:
        """Seconds members must wait between messages."""
        delay = self._data.rate_limit_per_user
        return delay if isinstance(delay, int) else 0

    @property
    def message_count(self) -> int:
        """Messages in the thread, not counting the first one or deleted ones."""
        count = self._data.message_count
        return count if isinstance(count, int) else 0

    @property
    def member_count(self) -> int:
        """Members in the thread, counted up to 50."""
        count = self._data.member_count
        return count if isinstance(count, int) else 0

    @property
    def applied_tags(self) -> list[Snowflake]:
        """The IDs of the forum tags on a post."""
        tags = self._data.applied_tags
        return list(tags) if isinstance(tags, list) else []

    @property
    def me(self) -> ThreadMember | None:
        """The bot's membership, when it has joined."""
        member = self._data.member
        return None if isinstance(member, UnsetType) else member

    @property
    def mention(self) -> str:
        """`<#id>`."""
        return f"<#{int(self.id)}>"

    @property
    def jump_url(self) -> str:
        """A link that opens the thread in Discord."""
        return f"https://discord.com/channels/{int(self.guild_id)}/{int(self.id)}"

    def is_private(self) -> bool:
        """Whether only invited members (and moderators) can see it."""
        return self.type is ChannelType.PRIVATE_THREAD

    def is_news(self) -> bool:
        """Whether it was started in an announcement channel."""
        return self.type is ChannelType.ANNOUNCEMENT_THREAD

    def permissions_for(self, target: "Member | Role") -> Permissions:
        """What a member can do in the thread.

        That is the parent channel's permissions, where sending needs Send Messages in Threads; nothing
        when the parent is not cached.

        Discord: https://docs.discord.com/developers/topics/permissions#inherited-permissions-threads
        """
        parent = self.parent
        if parent is None:
            return Permissions.none()
        return thread_permissions(parent.permissions_for(target))

    async def join(self) -> None:
        """Join the thread.

        Discord: https://docs.discord.com/developers/resources/channel#join-thread
        """
        await self._state.rest.threads.join(self.id)

    async def leave(self) -> None:
        """Leave the thread.

        Discord: https://docs.discord.com/developers/resources/channel#leave-thread
        """
        await self._state.rest.threads.leave(self.id)

    async def add_user(self, user: Hashable, /) -> None:
        """Add a member to the thread.

        Discord: https://docs.discord.com/developers/resources/channel#add-thread-member
        """
        await self._state.rest.threads.add_member(self.id, user.id)

    async def remove_user(self, user: Hashable, /) -> None:
        """Remove a member from the thread.

        Discord: https://docs.discord.com/developers/resources/channel#remove-thread-member
        """
        await self._state.rest.threads.remove_member(self.id, user.id)

    async def edit(
        self,
        *,
        name: str | MissingType = MISSING,
        archived: bool | MissingType = MISSING,
        locked: bool | MissingType = MISSING,
        invitable: bool | MissingType = MISSING,
        slowmode_delay: int | MissingType = MISSING,
        auto_archive_duration: int | MissingType = MISSING,
        applied_tags: Sequence[Hashable] | MissingType = MISSING,
        reason: str | None = None,
    ) -> "Thread":
        """Change the thread. Leave a keyword out to keep it.

        Discord: https://docs.discord.com/developers/resources/channel#modify-channel-json-params-thread
        """
        params = EditThreadParams(
            name=given(name),
            archived=given(archived),
            locked=given(locked),
            invitable=given(invitable),
            rate_limit_per_user=given(slowmode_delay),
            auto_archive_duration=given(auto_archive_duration),
            applied_tags=UNSET if isinstance(applied_tags, MissingType) else [tag.id for tag in applied_tags],
        )
        return Thread(self._state, await self._state.rest.channels.edit(self.id, params, reason=reason))

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete the thread.

        Discord: https://docs.discord.com/developers/resources/channel#delete/close-channel
        """
        await self._state.rest.channels.delete(self.id, reason=reason)

    @override
    def __str__(self) -> str:
        return self.name

    @override
    def __repr__(self) -> str:
        parent = None if self.parent_id is None else int(self.parent_id)
        return f"<Thread id={int(self.id)} name={self.name!r} parent_id={parent}>"
