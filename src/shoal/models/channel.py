"""Channels: text, voice, stage, category, forum and media channels in guilds, and DMs.

    channel = guild.get_channel(channel_id)
    if isinstance(channel, TextChannel) and channel.permissions_for(guild.me).send_messages:
        await channel.send("hello")

Discord: https://docs.discord.com/developers/resources/channel#channel-object
"""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, NamedTuple, Self, override

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
from shoal.models.base import MISSING, Hashable, MissingType, given, unset_if_none
from shoal.models.messageable import Before, Messageable
from shoal.models.permissions import channel_permissions, guild_permissions
from shoal.models.sending import EmbedLike, outgoing
from shoal.models.state import ComponentView, State
from shoal.payloads.channel import (
    Channel,
    ChannelType,
    CreateThreadParams,
    EditChannelPermissionsParams,
    EditGuildChannelParams,
    ForumTag,
    Overwrite,
    OverwriteType,
    VideoQualityMode,
)
from shoal.payloads.forum import CreatePostParams, ForumThreadMessageParams
from shoal.payloads.invite import CreateInviteParams, Invite, InviteWithMetadata
from shoal.payloads.message import BULK_DELETE_MAX_AGE, BULK_DELETE_MAX_MESSAGES, AllowedMentions
from shoal.payloads.permissions import Permissions
from shoal.payloads.stage_instance import CreateStageInstanceParams, StageInstance
from shoal.payloads.voice import VoiceState
from shoal.payloads.webhook import CreateWebhookParams, Webhook
from shoal.rest.files import File

if TYPE_CHECKING:
    from shoal.models.guild import Guild
    from shoal.models.member import Member
    from shoal.models.message import Message, PartialMessage
    from shoal.models.role import Role
    from shoal.models.thread import Thread
    from shoal.models.user import User
    from shoal.models.voice import VoiceClient


def _value[T](value: T | UnsetType) -> T | None:
    return None if isinstance(value, UnsetType) else value


class GuildChannel(Hashable):
    """What every channel in a guild shares: name, position, category and permission overwrites.

    Also used, as is, for channel types newer than this version of Shoal.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object
    """

    __slots__ = ("_data", "_state")

    def __init__(self, state: State, data: Channel) -> None:
        """A guild channel from its payload."""
        self._state: State = state
        self._data: Channel = data

    @property
    @override
    def id(self) -> Snowflake:
        return self._data.id

    @property
    def payload(self) -> Channel:
        """The channel as Discord sent it."""
        return self._data

    @property
    def type(self) -> ChannelType:
        """The channel's type."""
        return self._data.type

    @property
    def name(self) -> str:
        """The channel's name; empty for a channel whose details Discord hid (`is_obfuscated`)."""
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
    def position(self) -> int:
        """Its place in the channel list."""
        return _value(self._data.position) or 0

    @property
    def category_id(self) -> Snowflake | None:
        """The category it is in."""
        parent = self._data.parent_id
        return parent if isinstance(parent, Snowflake) else None

    @property
    def category(self) -> "CategoryChannel | None":
        """The category it is in, when cached."""
        category = resolve_cached_channel(self._state, self.category_id) if self.category_id else None
        return category if isinstance(category, CategoryChannel) else None

    @property
    def overwrites(self) -> list[Overwrite]:
        """Its permission overwrites."""
        return _value(self._data.permission_overwrites) or []

    def overwrites_for(self, target: Hashable) -> Overwrite | None:
        """The overwrite for a role or member, if there is one."""
        return next((overwrite for overwrite in self.overwrites if overwrite.id == target.id), None)

    @property
    def nsfw(self) -> bool:
        """Whether it is age-restricted."""
        return self._data.nsfw is True

    def is_nsfw(self) -> bool:
        """Whether it is age-restricted."""
        return self.nsfw

    @property
    def is_obfuscated(self) -> bool:
        """Whether Discord hid its details because the bot cannot view it."""
        return self._data.is_obfuscated

    @property
    def mention(self) -> str:
        """`<#id>`, which Discord renders as a link to the channel."""
        return f"<#{int(self.id)}>"

    @property
    def jump_url(self) -> str:
        """A link that opens the channel in Discord."""
        return f"https://discord.com/channels/{int(self.guild_id)}/{int(self.id)}"

    def permissions_for(self, target: "Member | Role") -> Permissions:
        """What a member (or everyone with a role) can do in this channel, from the cache.

        Discord: https://docs.discord.com/developers/topics/permissions#permission-overwrites
        """
        from shoal.models.member import Member

        if isinstance(target, Member):
            return channel_permissions(
                target.guild_permissions,
                guild_id=self.guild_id,
                user_id=target.id,
                member_roles=target.raw_roles,
                overwrites=self.overwrites,
                channel_type=self.type,
                timed_out=target.is_timed_out(),
            )
        guild = self._state.cache.peek(self._state.cache.guilds, self.guild_id)
        everyone = self._state.cache.peek(self._state.cache.roles, self.guild_id)
        permissions: dict[int, Permissions] = {self.guild_id: everyone.permissions} if everyone else {}
        permissions[target.id] = target.permissions
        base = guild_permissions(
            guild_id=self.guild_id,
            owner_id=guild.owner_id if guild is not None else 0,
            user_id=0,
            role_permissions=permissions,
            member_roles=[] if target.is_default() else [target.id],
        )
        roles = [] if target.is_default() else [target.id]
        return channel_permissions(
            base,
            guild_id=self.guild_id,
            user_id=0,
            member_roles=roles,
            overwrites=self.overwrites,
            channel_type=self.type,
        )

    async def set_permissions(
        self,
        target: "Member | Role | User",
        *,
        allow: Permissions | None = None,
        deny: Permissions | None = None,
        reason: str | None = None,
    ) -> None:
        """Set the overwrite for a role or member; with neither `allow` nor `deny`, remove it.

        Discord: https://docs.discord.com/developers/resources/channel#edit-channel-permissions
        """
        from shoal.models.role import Role

        if allow is None and deny is None:
            await self._state.rest.channels.delete_permissions(self.id, target.id, reason=reason)
            return
        kind = OverwriteType.ROLE if isinstance(target, Role) else OverwriteType.MEMBER
        params = EditChannelPermissionsParams(allow=unset_if_none(allow), deny=unset_if_none(deny), type=kind)
        await self._state.rest.channels.edit_permissions(self.id, target.id, params, reason=reason)

    async def edit(
        self,
        *,
        name: str | MissingType = MISSING,
        position: int | MissingType = MISSING,
        topic: str | MissingType | None = MISSING,
        nsfw: bool | MissingType = MISSING,
        slowmode_delay: int | MissingType = MISSING,
        bitrate: int | MissingType = MISSING,
        user_limit: int | MissingType = MISSING,
        category: Hashable | MissingType | None = MISSING,
        rtc_region: str | MissingType | None = MISSING,
        video_quality_mode: VideoQualityMode | MissingType = MISSING,
        default_auto_archive_duration: int | MissingType = MISSING,
        reason: str | None = None,
    ) -> Self:
        """Change the channel. Leave a keyword out to keep it.

        Discord refuses settings that do not apply to this channel's type.

        Discord: https://docs.discord.com/developers/resources/channel#modify-channel
        """
        params = EditGuildChannelParams(
            name=given(name),
            position=given(position),
            topic=given(topic),
            nsfw=given(nsfw),
            rate_limit_per_user=given(slowmode_delay),
            bitrate=given(bitrate),
            user_limit=given(user_limit),
            parent_id=UNSET
            if isinstance(category, MissingType)
            else None
            if category is None
            else category.id,
            rtc_region=given(rtc_region),
            video_quality_mode=given(video_quality_mode),
            default_auto_archive_duration=given(default_auto_archive_duration),
        )
        data = await self._state.rest.channels.edit(self.id, params, reason=reason)
        return type(self)(self._state, data)

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete the channel.

        Discord: https://docs.discord.com/developers/resources/channel#delete/close-channel
        """
        await self._state.rest.channels.delete(self.id, reason=reason)

    async def create_invite(
        self,
        *,
        max_age: int = 0,
        max_uses: int = 0,
        temporary: bool = False,
        unique: bool = True,
        reason: str | None = None,
    ) -> Invite:
        """Create an invite to the channel.

        The defaults never expire and create a new invite each time.

        Discord: https://docs.discord.com/developers/resources/channel#create-channel-invite
        """
        params = CreateInviteParams(max_age=max_age, max_uses=max_uses, temporary=temporary, unique=unique)
        return await self._state.rest.invites.create(self.id, params, reason=reason)

    async def invites(self) -> list[InviteWithMetadata]:
        """The channel's invites.

        Discord: https://docs.discord.com/developers/resources/channel#get-channel-invites
        """
        return await self._state.rest.invites.list_for_channel(self.id)

    @override
    def __str__(self) -> str:
        return self.name

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__} id={int(self.id)} name={self.name!r}>"


class _GuildMessageable(GuildChannel, Messageable):
    """A guild channel messages can be sent in."""

    __slots__ = ()

    @property
    @override
    def _messageable_state(self) -> State:
        return self._state

    @override
    async def _messageable_channel(self) -> tuple[Snowflake, Snowflake | None]:
        return self.id, self.guild_id

    def get_partial_message(self, message_id: int, /) -> "PartialMessage":
        """A message you only know the ID of: reply to it, edit, delete or react without fetching it."""
        from shoal.models.message import PartialMessage

        return PartialMessage(self._state, self.id, message_id, guild_id=self.guild_id)

    @property
    def slowmode_delay(self) -> int:
        """Seconds members must wait between messages; 0 when off."""
        return _value(self._data.rate_limit_per_user) or 0

    @property
    def last_message_id(self) -> Snowflake | None:
        """The latest message's ID, which may have been deleted since."""
        last = self._data.last_message_id
        return last if isinstance(last, Snowflake) else None

    @property
    def last_message(self) -> "Message | None":
        """The latest message, when cached."""
        from shoal.models.message import Message

        last = self.last_message_id
        data = self._state.cache.peek(self._state.cache.messages, last) if last is not None else None
        return Message(self._state, data, guild_id=self.guild_id) if data is not None else None

    async def delete_messages(self, messages: Sequence[Hashable], *, reason: str | None = None) -> None:
        """Delete messages at once: up to 100, none older than two weeks.

        Discord: https://docs.discord.com/developers/resources/message#bulk-delete-messages
        """
        ids = [message.id for message in messages]
        if len(ids) == 1:
            await self._state.rest.messages.delete(self.id, ids[0], reason=reason)
        elif ids:
            await self._state.rest.messages.bulk_delete(self.id, ids, reason=reason)

    async def purge(
        self,
        *,
        limit: int | None = 100,
        check: "Callable[[Message], bool] | None" = None,
        before: Before | None = None,
        after: Before | None = None,
        reason: str | None = None,
    ) -> "list[Message]":
        """Delete recent messages that pass `check`, 100 at a time, and return them.

        Messages older than two weeks cannot be bulk deleted; they are deleted one by one.

        Discord: https://docs.discord.com/developers/resources/message#bulk-delete-messages
        """
        too_old = Snowflake.from_datetime(self._state.now() - BULK_DELETE_MAX_AGE)
        deleted: list[Message] = []
        batch: list[Message] = []
        async for message in self.history(limit=limit, before=before, after=after):
            if check is not None and not check(message):
                continue
            if message.id < too_old:
                await message.delete(reason=reason)
                deleted.append(message)
                continue
            batch.append(message)
            if len(batch) == BULK_DELETE_MAX_MESSAGES:
                await self.delete_messages(batch, reason=reason)
                deleted.extend(batch)
                batch = []
        await self.delete_messages(batch, reason=reason)
        deleted.extend(batch)
        return deleted

    async def webhooks(self) -> list[Webhook]:
        """The channel's webhooks.

        Discord: https://docs.discord.com/developers/resources/webhook#get-channel-webhooks
        """
        return await self._state.rest.webhooks.list_for_channel(self.id)

    async def create_webhook(self, *, name: str, reason: str | None = None) -> Webhook:
        """Create a webhook that posts in this channel.

        Discord: https://docs.discord.com/developers/resources/webhook#create-webhook
        """
        return await self._state.rest.webhooks.create(self.id, CreateWebhookParams(name=name), reason=reason)


class TextChannel(_GuildMessageable):
    """A text or announcement channel.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object
    """

    __slots__ = ()

    @property
    def topic(self) -> str | None:
        """The channel topic."""
        topic = self._data.topic
        return topic if isinstance(topic, str) else None

    def is_news(self) -> bool:
        """Whether it is an announcement channel, whose messages can be published to followers."""
        return self.type is ChannelType.GUILD_ANNOUNCEMENT

    @property
    def threads(self) -> "list[Thread]":
        """The cached active threads started in this channel."""
        return [thread for thread in guild_threads(self._state, self.guild_id) if thread.parent_id == self.id]

    async def create_thread(
        self,
        *,
        name: str,
        message: Hashable | None = None,
        auto_archive_duration: int | None = None,
        type: ChannelType | None = None,  # noqa: A002 - the thread's channel type, as Discord names it
        invitable: bool = True,
        slowmode_delay: int | None = None,
        reason: str | None = None,
    ) -> "Thread":
        """Start a thread from `message`, or a thread of its own.

        A thread of its own is private unless `type` says otherwise, as is Discord's
        current default.

        Discord: https://docs.discord.com/developers/resources/channel#start-thread-without-message
        """
        from shoal.models.message import PartialMessage
        from shoal.models.thread import Thread

        if message is not None:
            starter = PartialMessage(self._state, self.id, message.id, guild_id=self.guild_id)
            return await starter.create_thread(
                name=name,
                auto_archive_duration=auto_archive_duration,
                slowmode_delay=slowmode_delay,
                reason=reason,
            )
        params = CreateThreadParams(
            name=name,
            auto_archive_duration=UNSET if auto_archive_duration is None else auto_archive_duration,
            type=ChannelType.PRIVATE_THREAD if type is None else type,
            invitable=invitable,
            rate_limit_per_user=UNSET if slowmode_delay is None else slowmode_delay,
        )
        return Thread(self._state, await self._state.rest.threads.create(self.id, params, reason=reason))


class VoiceChannel(_GuildMessageable):
    """A voice channel, which also has its own text chat.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object
    """

    __slots__ = ()

    @property
    def bitrate(self) -> int:
        """The audio bitrate, in bits per second."""
        return _value(self._data.bitrate) or 64_000

    @property
    def user_limit(self) -> int:
        """How many users can join; 0 is unlimited."""
        return _value(self._data.user_limit) or 0

    @property
    def rtc_region(self) -> str | None:
        """The voice region; `None` lets Discord choose."""
        region = self._data.rtc_region
        return region if isinstance(region, str) else None

    @property
    def video_quality_mode(self) -> VideoQualityMode:
        """The camera video quality."""
        return _value(self._data.video_quality_mode) or VideoQualityMode.AUTO

    @property
    def voice_states(self) -> dict[Snowflake, VoiceState]:
        """The cached voice states of everyone in the channel, by user ID."""
        states = self._state.cache.peek_scoped(self._state.cache.voice_states, self.guild_id)
        return {state.user_id: state for state in states if state.channel_id == self.id}

    @property
    def members(self) -> "list[Member]":
        """The cached members in the channel."""
        from shoal.models.member import Member

        found = (Member.from_cache(self._state, self.guild_id, user_id) for user_id in self.voice_states)
        return [member for member in found if member is not None]

    async def connect(self, *, self_mute: bool = False, self_deaf: bool = False) -> "VoiceClient":
        """Join the channel (or move the bot here), and return the guild's voice client.

        Needs `pip install 'shoal[voice]'` and a `Client` running the guild's shard.

        Raises:
            GatewayRequiredError: There is no gateway connection for the guild.
            TimeoutError: Discord did not answer, or the voice handshake did not finish, in time.
            VoiceConnectionClosedError: The voice server refused the connection.

        Discord: https://docs.discord.com/developers/topics/voice-connections#connecting-to-voice
        """
        return await self._state.voice.connect_voice(
            self.guild_id, self.id, self_mute=self_mute, self_deaf=self_deaf
        )


class StageChannel(VoiceChannel):
    """A stage channel, where speakers talk to an audience.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object
    """

    __slots__ = ()

    @property
    def topic(self) -> str | None:
        """The channel topic."""
        topic = self._data.topic
        return topic if isinstance(topic, str) else None

    @property
    def instance(self) -> StageInstance | None:
        """The live stage, when the channel is live and cached."""
        stages = self._state.cache.peek_scoped(self._state.cache.stage_instances, self.guild_id)
        return next((stage for stage in stages if stage.channel_id == self.id), None)

    async def create_instance(self, *, topic: str, reason: str | None = None) -> StageInstance:
        """Make the stage live.

        Discord: https://docs.discord.com/developers/resources/stage-instance#create-stage-instance
        """
        params = CreateStageInstanceParams(channel_id=self.id, topic=topic)
        return await self._state.rest.stage_instances.create(params, reason=reason)

    async def fetch_instance(self) -> StageInstance:
        """Get the live stage from Discord.

        Raises:
            NotFoundError: The stage is not live.

        Discord: https://docs.discord.com/developers/resources/stage-instance#get-stage-instance
        """
        return await self._state.rest.stage_instances.get(self.id)


class CategoryChannel(GuildChannel):
    """A category that groups channels.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object
    """

    __slots__ = ()

    @property
    def channels(self) -> list[GuildChannel]:
        """The cached channels in the category, in channel list order."""
        found = [
            channel
            for channel in guild_channels(self._state, self.guild_id)
            if channel.category_id == self.id
        ]
        return sorted(found, key=lambda channel: (channel.position, int(channel.id)))

    @property
    def text_channels(self) -> list[TextChannel]:
        """The category's text and announcement channels."""
        return [channel for channel in self.channels if isinstance(channel, TextChannel)]

    @property
    def voice_channels(self) -> list[VoiceChannel]:
        """The category's voice channels (not stages)."""
        return [channel for channel in self.channels if type(channel) is VoiceChannel]

    @property
    def stage_channels(self) -> list[StageChannel]:
        """The category's stage channels."""
        return [channel for channel in self.channels if isinstance(channel, StageChannel)]

    @property
    def forums(self) -> "list[ForumChannel]":
        """The category's forum and media channels."""
        return [channel for channel in self.channels if isinstance(channel, ForumChannel)]


class ThreadWithMessage(NamedTuple):
    """A new forum post: the thread and its first message."""

    thread: "Thread"
    message: "Message"


class ForumChannel(GuildChannel):
    """A forum channel, where every post is a thread.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object
    """

    __slots__ = ()

    @property
    def topic(self) -> str | None:
        """The guidelines shown at the top."""
        topic = self._data.topic
        return topic if isinstance(topic, str) else None

    @property
    def available_tags(self) -> list[ForumTag]:
        """The tags posts can have."""
        return _value(self._data.available_tags) or []

    def get_tag(self, tag_id: int, /) -> ForumTag | None:
        """The tag with this ID."""
        return next((tag for tag in self.available_tags if tag.id == tag_id), None)

    @property
    def threads(self) -> "list[Thread]":
        """The cached active posts."""
        return [thread for thread in guild_threads(self._state, self.guild_id) if thread.parent_id == self.id]

    async def create_thread(
        self,
        *,
        name: str,
        content: object = None,
        embed: EmbedLike | None = None,
        embeds: Sequence[EmbedLike] | None = None,
        file: File | None = None,
        files: Sequence[File] | None = None,
        allowed_mentions: AllowedMentions | None = None,
        view: ComponentView | None = None,
        applied_tags: Sequence[ForumTag | Hashable] = (),
        auto_archive_duration: int | None = None,
        slowmode_delay: int | None = None,
        reason: str | None = None,
    ) -> ThreadWithMessage:
        """Create a post: a thread and its first message.

        Discord: https://docs.discord.com/developers/resources/channel#start-thread-in-forum-or-media-channel
        """
        from shoal.models.message import Message
        from shoal.models.thread import Thread

        message = outgoing(
            content,
            embed=embed,
            embeds=embeds,
            file=file,
            files=files,
            allowed_mentions=allowed_mentions,
            view=view,
        )
        params = CreatePostParams(
            name=name,
            auto_archive_duration=UNSET if auto_archive_duration is None else auto_archive_duration,
            rate_limit_per_user=UNSET if slowmode_delay is None else slowmode_delay,
            message=ForumThreadMessageParams(
                content=message.content,
                embeds=message.embeds,
                allowed_mentions=message.allowed_mentions,
                components=message.components,
                flags=message.flags,
            ),
            applied_tags=[Snowflake(tag.id) for tag in applied_tags] if applied_tags else UNSET,
        )
        data = await self._state.rest.threads.create_post(self.id, params, files=message.files, reason=reason)
        sent = Message(self._state, data.message, guild_id=self.guild_id)
        if view is not None and view.is_dispatchable():
            self._state.views.store(view, message_id=sent.id)
        return ThreadWithMessage(Thread(self._state, data), sent)


class MediaChannel(ForumChannel):
    """A media channel: a forum whose posts lead with images and videos.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object
    """

    __slots__ = ()


class DMChannel(Hashable, Messageable):
    """A direct message channel with one user.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object
    """

    __slots__ = ("_data", "_state")

    def __init__(self, state: State, data: Channel) -> None:
        """A DM channel from its payload."""
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
        return self.id, None

    def get_partial_message(self, message_id: int, /) -> "PartialMessage":
        """A message you only know the ID of: reply to it, edit, delete or react without fetching it."""
        from shoal.models.message import PartialMessage

        return PartialMessage(self._state, self.id, message_id, guild_id=None)

    @property
    def type(self) -> ChannelType:
        """`ChannelType.DM`."""
        return self._data.type

    @property
    def recipient(self) -> "User | None":
        """The other user, when Discord included them."""
        from shoal.models.user import User

        recipients = _value(self._data.recipients) or []
        return User(self._state, recipients[0]) if recipients else None

    @property
    def jump_url(self) -> str:
        """A link that opens the DM in Discord."""
        return f"https://discord.com/channels/@me/{int(self.id)}"

    @override
    def __repr__(self) -> str:
        return f"<DMChannel id={int(self.id)}>"


class GroupChannel(DMChannel):
    """A group DM.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object
    """

    __slots__ = ()

    @property
    def name(self) -> str | None:
        """The group's name."""
        name = self._data.name
        return name if isinstance(name, str) else None

    @property
    def recipients(self) -> "list[User]":
        """Everyone in the group but the bot."""
        from shoal.models.user import User

        return [User(self._state, user) for user in _value(self._data.recipients) or []]

    @property
    def owner_id(self) -> Snowflake | None:
        """Who created the group."""
        return _value(self._data.owner_id)

    @override
    def __repr__(self) -> str:
        return f"<GroupChannel id={int(self.id)} name={self.name!r}>"


class PartialMessageable(Hashable, Messageable):
    """A channel known only by ID: messages can be sent and read, nothing else is known.

    `Message.channel` is one when the channel is not cached.
    """

    __slots__ = ("_guild_id", "_id", "_state")

    def __init__(self, state: State, channel_id: int, guild_id: int | None = None) -> None:
        """A channel with this ID, in guild `guild_id` (`None` for DMs)."""
        self._state: State = state
        self._id: Snowflake = Snowflake(channel_id)
        self._guild_id: Snowflake | None = None if guild_id is None else Snowflake(guild_id)

    @property
    @override
    def id(self) -> Snowflake:
        return self._id

    @property
    def guild_id(self) -> Snowflake | None:
        """The guild's ID, if known."""
        return self._guild_id

    def get_partial_message(self, message_id: int, /) -> "PartialMessage":
        """A message you only know the ID of: reply to it, edit, delete or react without fetching it."""
        from shoal.models.message import PartialMessage

        return PartialMessage(self._state, self.id, message_id, guild_id=self._guild_id)

    @property
    @override
    def _messageable_state(self) -> State:
        return self._state

    @override
    async def _messageable_channel(self) -> tuple[Snowflake, Snowflake | None]:
        return self._id, self._guild_id

    @property
    def jump_url(self) -> str:
        """A link that opens the channel in Discord."""
        where = int(self._guild_id) if self._guild_id is not None else "@me"
        return f"https://discord.com/channels/{where}/{int(self._id)}"

    @override
    def __repr__(self) -> str:
        return f"<PartialMessageable id={int(self._id)}>"


type AnyGuildChannel = (
    TextChannel | VoiceChannel | StageChannel | CategoryChannel | ForumChannel | GuildChannel
)
"""Any channel of a guild (threads aside)."""
type MessageableChannel = (
    TextChannel | VoiceChannel | StageChannel | Thread | DMChannel | GroupChannel | PartialMessageable
)
"""Any channel a message can be in."""

_GUILD_KINDS: dict[ChannelType, type[GuildChannel]] = {
    ChannelType.GUILD_ANNOUNCEMENT: TextChannel,
    ChannelType.GUILD_CATEGORY: CategoryChannel,
    ChannelType.GUILD_FORUM: ForumChannel,
    ChannelType.GUILD_MEDIA: MediaChannel,
    ChannelType.GUILD_STAGE_VOICE: StageChannel,
    ChannelType.GUILD_TEXT: TextChannel,
    ChannelType.GUILD_VOICE: VoiceChannel,
}


def channel_from_payload(state: State, data: Channel) -> "AnyGuildChannel | Thread | DMChannel":
    """The model for a channel payload, by its type; unknown guild types become `GuildChannel`."""
    from shoal.models.thread import Thread

    if data.type.is_thread:
        return Thread(state, data)
    if data.type is ChannelType.DM:
        return DMChannel(state, data)
    if data.type is ChannelType.GROUP_DM:
        return GroupChannel(state, data)
    return _GUILD_KINDS.get(data.type, GuildChannel)(state, data)


def resolve_cached_channel(state: State, channel_id: int) -> "AnyGuildChannel | Thread | DMChannel | None":
    """The cached channel, thread or DM channel with this ID."""
    data = state.cache.peek(state.cache.channels, Snowflake(channel_id))
    return channel_from_payload(state, data) if data is not None else None


def resolve_channel(state: State, channel_id: int, guild_id: int | None) -> MessageableChannel:
    """The cached channel a message is in, or a `PartialMessageable` when it is not cached."""
    from shoal.models.thread import Thread

    channel = resolve_cached_channel(state, channel_id)
    if isinstance(channel, TextChannel | VoiceChannel | Thread | DMChannel):
        return channel
    return PartialMessageable(state, channel_id, guild_id)


def guild_channels(state: State, guild_id: int) -> list[AnyGuildChannel]:
    """Every cached channel of a guild, threads aside, in no particular order."""
    found: list[AnyGuildChannel] = []
    for data in state.cache.peek_scoped(state.cache.channels, Snowflake(guild_id)):
        channel = channel_from_payload(state, data)
        if isinstance(channel, GuildChannel):
            found.append(channel)
    return found


def guild_threads(state: State, guild_id: int) -> "list[Thread]":
    """Every cached active thread of a guild."""
    from shoal.models.thread import Thread

    channels = state.cache.peek_scoped(state.cache.channels, Snowflake(guild_id))
    return [Thread(state, data) for data in channels if data.type.is_thread]
