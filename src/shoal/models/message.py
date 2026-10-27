"""Messages: what was said, by whom, where, and what you can do with it.

    await message.reply("pong", mention_author=False)
    await message.add_reaction("\N{THUMBS UP SIGN}")
    await message.edit(content="edited")

Discord: https://docs.discord.com/developers/resources/message#message-object
"""

import logging
import re
from collections.abc import AsyncIterator, Iterable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Final, override

import msgspec
from msgspec import UNSET, UnsetType

from shoal.core.formatting import ANY_MENTION, escape_mentions
from shoal.core.snowflake import Snowflake
from shoal.models.base import MISSING, Hashable, MissingType, unset_if_none
from shoal.models.embed import Embed
from shoal.models.emoji import EmojiLike, partial_emoji
from shoal.models.sending import EmbedLike, edit
from shoal.models.state import ComponentView, State
from shoal.payloads.channel import CreateThreadFromMessageParams
from shoal.payloads.emoji import PartialEmoji
from shoal.payloads.gateway_events import MessageCreate
from shoal.payloads.message import (
    LIST_MESSAGES_MAX_LIMIT,
    AllowedMentions,
    Attachment,
    ListReactionsParams,
    MessageFlags,
    MessageReference,
    MessageType,
    ReactionCountDetails,
    ReactionType,
)
from shoal.payloads.message import Message as MessagePayload
from shoal.payloads.message import Reaction as ReactionPayload
from shoal.payloads.poll import Poll, PollCreateRequest
from shoal.payloads.sticker import StickerItem
from shoal.rest.files import File, VoiceMessage
from shoal.rest.resources.message import ReactionEmoji

if TYPE_CHECKING:
    from shoal.models.channel import MessageableChannel
    from shoal.models.guild import Guild
    from shoal.models.member import Member
    from shoal.models.messageable import MessageTarget
    from shoal.models.role import Role
    from shoal.models.thread import Thread
    from shoal.models.user import User

_log = logging.getLogger("shoal.models")

_USER_MESSAGE_TYPES: Final = frozenset(
    {
        MessageType.DEFAULT,
        MessageType.REPLY,
        MessageType.CHAT_INPUT_COMMAND,
        MessageType.CONTEXT_MENU_COMMAND,
        MessageType.THREAD_STARTER_MESSAGE,
    }
)
"""Message types a user or app sent; every other type is a system message."""


def _value[T](value: T | UnsetType) -> T | None:
    return None if isinstance(value, UnsetType) else value


class PartialMessage(Hashable):
    """A message you only know the ID and channel of; `channel.get_partial_message(id)`.

    It can do everything that does not need the message's content: reply, edit, delete, react,
    pin, and fetch the full message.

    Discord: https://docs.discord.com/developers/resources/message
    """

    __slots__ = ("_channel_id", "_guild_id", "_id", "_state")

    def __init__(
        self, state: State, channel_id: int, message_id: int, *, guild_id: int | None = None
    ) -> None:
        """Message `message_id` in channel `channel_id` (of guild `guild_id`; `None` in DMs)."""
        self._state: State = state
        self._channel_id: Snowflake = Snowflake(channel_id)
        self._id: Snowflake = Snowflake(message_id)
        self._guild_id: Snowflake | None = None if guild_id is None else Snowflake(guild_id)

    @property
    @override
    def id(self) -> Snowflake:
        return self._id

    @property
    def channel_id(self) -> Snowflake:
        """The ID of the channel it is in."""
        return self._channel_id

    @property
    def guild_id(self) -> Snowflake | None:
        """The guild it is in, or `None` in DMs."""
        return self._guild_id

    @property
    def channel(self) -> "MessageableChannel":
        """The channel it is in; a `PartialMessageable` when the channel is not cached."""
        from shoal.models.channel import resolve_channel

        return resolve_channel(self._state, self._channel_id, self._guild_id)

    @property
    def jump_url(self) -> str:
        """A link that opens the message in Discord."""
        where = int(self._guild_id) if self._guild_id is not None else "@me"
        return f"https://discord.com/channels/{where}/{int(self._channel_id)}/{int(self._id)}"

    def to_reference(self, *, fail_if_not_exists: bool = True) -> MessageReference:
        """A reference that makes a sent message a reply to this one."""
        return MessageReference(
            message_id=self._id,
            channel_id=self._channel_id,
            guild_id=unset_if_none(self._guild_id),
            fail_if_not_exists=fail_if_not_exists,
        )

    async def fetch(self) -> "Message":
        """Get the whole message from Discord.

        Discord: https://docs.discord.com/developers/resources/message#get-channel-message
        """
        data = await self._state.rest.messages.get(self._channel_id, self._id)
        return Message(self._state, data, guild_id=self._guild_id)

    async def reply(
        self,
        content: object = None,
        *,
        tts: bool = False,
        embed: EmbedLike | None = None,
        embeds: Sequence[EmbedLike] | None = None,
        file: File | None = None,
        files: Sequence[File] | None = None,
        stickers: Sequence[int | Hashable] = (),
        delete_after: float | None = None,
        allowed_mentions: AllowedMentions | None = None,
        mention_author: bool | None = None,
        view: ComponentView | None = None,
        suppress_embeds: bool = False,
        silent: bool = False,
        poll: PollCreateRequest | None = None,
        voice_message: VoiceMessage | None = None,
    ) -> "Message":
        """Reply to this message; the keywords are `send`'s.

        Discord: https://docs.discord.com/developers/resources/message#create-message
        """
        reference: MessageTarget = self
        return await self.channel.send(
            content,
            tts=tts,
            embed=embed,
            embeds=embeds,
            file=file,
            files=files,
            stickers=stickers,
            delete_after=delete_after,
            allowed_mentions=allowed_mentions,
            reference=reference,
            mention_author=mention_author,
            view=view,
            suppress_embeds=suppress_embeds,
            silent=silent,
            poll=poll,
            voice_message=voice_message,
        )

    async def edit(
        self,
        *,
        content: object = MISSING,
        embed: EmbedLike | MissingType | None = MISSING,
        embeds: Sequence[EmbedLike] | MissingType = MISSING,
        attachments: Sequence[File | Attachment] | MissingType = MISSING,
        allowed_mentions: AllowedMentions | MissingType | None = MISSING,
        view: ComponentView | MissingType | None = MISSING,
        suppress: bool | MissingType = MISSING,
        delete_after: float | None = None,
    ) -> "Message":
        """Edit the message. Leave a keyword out to keep that part; pass `None` to remove it.

        `attachments` is every attachment to keep, as `message.attachments` lists them, and new
        `File`s; `[]` removes them all. Only the bot's own messages can change content; on others
        only `suppress` (hiding link embeds) works.

        Discord: https://docs.discord.com/developers/resources/message#edit-message
        """
        changes = edit(
            content=content,
            embed=embed,
            embeds=embeds,
            attachments=attachments,
            allowed_mentions=allowed_mentions,
            view=view,
            suppress=suppress,
            flags=self._current_flags(),
        )
        channel_id, guild_id = self._channel_id, self._guild_id
        data = await self._state.rest.messages.edit(
            channel_id, self._id, changes.message_params(), files=changes.files
        )
        if changes.view is not None and changes.view.is_dispatchable():
            self._state.views.store(changes.view, message_id=self._id)
        edited = Message(self._state, data, guild_id=guild_id)
        if delete_after is not None:
            edited.delete_later(delete_after)
        return edited

    def _current_flags(self) -> MessageFlags:
        return MessageFlags.none()

    async def delete(self, *, delay: float | None = None, reason: str | None = None) -> None:
        """Delete the message, now or after `delay` seconds (a failed delayed delete is logged).

        Discord: https://docs.discord.com/developers/resources/message#delete-message
        """
        if delay is not None:
            self.delete_later(delay, reason=reason)
            return
        channel_id = self._channel_id
        await self._state.rest.messages.delete(channel_id, self._id, reason=reason)

    def delete_later(self, delay: float, *, reason: str | None = None) -> None:
        """Delete the message after `delay` seconds without waiting; a message already gone is fine."""

        async def delete() -> None:
            await self.delete(reason=reason)

        self._state.delete_later(delay, delete, name=f"shoal-delete-{int(self._id)}")

    async def pin(self, *, reason: str | None = None) -> None:
        """Pin the message.

        Discord: https://docs.discord.com/developers/resources/message#pin-message
        """
        channel_id = self._channel_id
        await self._state.rest.messages.pin(channel_id, self._id, reason=reason)

    async def unpin(self, *, reason: str | None = None) -> None:
        """Unpin the message.

        Discord: https://docs.discord.com/developers/resources/message#unpin-message
        """
        channel_id = self._channel_id
        await self._state.rest.messages.unpin(channel_id, self._id, reason=reason)

    async def publish(self) -> "Message":
        """Send an announcement channel's message to the channels that follow it.

        Discord: https://docs.discord.com/developers/resources/message#crosspost-message
        """
        channel_id, guild_id = self._channel_id, self._guild_id
        return Message(
            self._state, await self._state.rest.messages.crosspost(channel_id, self._id), guild_id=guild_id
        )

    async def add_reaction(self, emoji: EmojiLike, /) -> None:
        """React with a unicode emoji, `name:id`, or a guild or application emoji.

        Discord: https://docs.discord.com/developers/resources/message#create-reaction
        """
        channel_id = self._channel_id
        await self._state.rest.reactions.add(channel_id, self._id, _reaction(emoji))

    async def remove_reaction(self, emoji: EmojiLike, member: Hashable) -> None:
        """Remove `member`'s reaction (the bot's own, when `member` is the bot).

        Discord: https://docs.discord.com/developers/resources/message#delete-user-reaction
        """
        channel_id = self._channel_id
        if member.id == self._state.user_id:
            await self._state.rest.reactions.remove_mine(channel_id, self._id, _reaction(emoji))
        else:
            await self._state.rest.reactions.remove(channel_id, self._id, _reaction(emoji), member.id)

    async def clear_reaction(self, emoji: EmojiLike, /) -> None:
        """Remove every reaction with one emoji.

        Discord: https://docs.discord.com/developers/resources/message#delete-all-reactions-for-emoji
        """
        channel_id = self._channel_id
        await self._state.rest.reactions.clear_emoji(channel_id, self._id, _reaction(emoji))

    async def clear_reactions(self) -> None:
        """Remove every reaction.

        Discord: https://docs.discord.com/developers/resources/message#delete-all-reactions
        """
        channel_id = self._channel_id
        await self._state.rest.reactions.clear(channel_id, self._id)

    async def create_thread(
        self,
        *,
        name: str,
        auto_archive_duration: int | None = None,
        slowmode_delay: int | None = None,
        reason: str | None = None,
    ) -> "Thread":
        """Start a thread from this message.

        Discord: https://docs.discord.com/developers/resources/channel#start-thread-from-message
        """
        from shoal.models.thread import Thread

        channel_id = self._channel_id
        params = CreateThreadFromMessageParams(
            name=name,
            auto_archive_duration=UNSET if auto_archive_duration is None else auto_archive_duration,
            rate_limit_per_user=UNSET if slowmode_delay is None else slowmode_delay,
        )
        data = await self._state.rest.threads.create_from_message(channel_id, self._id, params, reason=reason)
        return Thread(self._state, data)

    @override
    def __repr__(self) -> str:
        return f"<PartialMessage id={int(self._id)}>"


class Message(PartialMessage):
    """A message, with everything Discord sent about it.

    `author` is a `Member` when the message was sent in a guild and the member is known (the
    gateway sends it with the message), otherwise a `User`.

    Discord: https://docs.discord.com/developers/resources/message#message-object
    """

    __slots__ = ("_data",)

    def __init__(self, state: State, data: MessagePayload, *, guild_id: int | None = None) -> None:
        """A message from its payload; pass `guild_id` when the payload came from REST, which omits it."""
        sent_in = data.guild_id if isinstance(data, MessageCreate) else UNSET
        super().__init__(
            state, data.channel_id, data.id, guild_id=sent_in if isinstance(sent_in, Snowflake) else guild_id
        )
        self._data: MessagePayload = data

    @override
    def _current_flags(self) -> MessageFlags:
        return self.flags

    @property
    def payload(self) -> MessagePayload:
        """The message as Discord sent it."""
        return self._data

    @property
    def guild(self) -> "Guild | None":
        """The guild it was sent in, when cached."""
        from shoal.models.guild import Guild

        return Guild.from_cache(self._state, self._guild_id) if self._guild_id is not None else None

    @property
    def author(self) -> "User | Member":
        """Who sent it: a `Member` in a guild when the member is known, else a `User`."""
        from shoal.models.member import Member
        from shoal.models.user import User

        if self._guild_id is not None and self._data.webhook_id is UNSET:
            member = self._data.member if isinstance(self._data, MessageCreate) else UNSET
            if not isinstance(member, UnsetType):
                return Member(self._state, member, self._guild_id, user=self._data.author)
            cached = Member.from_cache(self._state, self._guild_id, self._data.author.id)
            if cached is not None:
                return cached
        return User(self._state, self._data.author)

    @property
    def content(self) -> str:
        """The text. Empty without the Message Content intent, except in DMs, mentions and replies."""
        return self._data.content

    @property
    def clean_content(self) -> str:
        """The text with mentions written as names (`@Ada`, `#general`) that ping nobody."""
        return clean_mentions(self._state, self.content, guild_id=self._guild_id, mentioned=self.mentions)

    @property
    @override
    def created_at(self) -> datetime:
        """When it was sent."""
        return self._data.timestamp

    @property
    def edited_at(self) -> datetime | None:
        """When it was last edited."""
        return self._data.edited_timestamp

    @property
    def tts(self) -> bool:
        """Whether it was sent as text-to-speech."""
        return self._data.tts

    @property
    def pinned(self) -> bool:
        """Whether it is pinned."""
        return self._data.pinned

    @property
    def type(self) -> MessageType:
        """What kind of message it is (a reply, a join notice, a pin notice...)."""
        return self._data.type

    @property
    def flags(self) -> MessageFlags:
        """Its flags."""
        return self._data.flags if isinstance(self._data.flags, MessageFlags) else MessageFlags.none()

    @property
    def embeds(self) -> list[Embed]:
        """Its embeds."""
        return [Embed.from_payload(embed) for embed in self._data.embeds]

    @property
    def attachments(self) -> list[Attachment]:
        """Its files."""
        return self._data.attachments

    @property
    def reactions(self) -> "list[Reaction]":
        """Its reactions, with counts."""
        return [Reaction(self._state, self, reaction) for reaction in _value(self._data.reactions) or []]

    @property
    def stickers(self) -> list[StickerItem]:
        """Its stickers."""
        return _value(self._data.sticker_items) or []

    @property
    def mention_everyone(self) -> bool:
        """Whether it mentions @everyone or @here (and was allowed to)."""
        return self._data.mention_everyone

    @property
    def mentions(self) -> "list[User | Member]":
        """The users it mentions, as members when in a guild and cached."""
        from shoal.models.member import Member
        from shoal.models.user import User

        found: list[User | Member] = []
        for user in self._data.mentions:
            cached = Member.from_cache(self._state, self._guild_id, user.id) if self._guild_id else None
            found.append(cached if cached is not None else User(self._state, user))
        return found

    @property
    def raw_mentions(self) -> list[Snowflake]:
        """The IDs of the users it mentions."""
        return [user.id for user in self._data.mentions]

    @property
    def raw_role_mentions(self) -> list[Snowflake]:
        """The IDs of the roles it mentions."""
        return list(self._data.mention_roles)

    @property
    def role_mentions(self) -> "list[Role]":
        """The roles it mentions that are cached."""
        from shoal.models.role import Role

        roles = (Role.from_cache(self._state, role_id) for role_id in self._data.mention_roles)
        return [role for role in roles if role is not None]

    @property
    def reference(self) -> MessageReference | None:
        """The message this one replies to or forwards."""
        return _value(self._data.message_reference)

    @property
    def referenced_message(self) -> "Message | None":
        """The message this one replies to, when Discord included it."""
        replied = self._data.referenced_message
        if replied is None or isinstance(replied, UnsetType):
            return None
        return Message(self._state, replied, guild_id=self._guild_id)

    @property
    def webhook_id(self) -> Snowflake | None:
        """The webhook that sent it."""
        return _value(self._data.webhook_id)

    @property
    def application_id(self) -> Snowflake | None:
        """The application that sent it, for interaction responses and Rich Presence messages."""
        return _value(self._data.application_id)

    @property
    def poll(self) -> Poll | None:
        """Its poll."""
        return _value(self._data.poll)

    def is_system(self) -> bool:
        """Whether Discord generated it (joins, boosts, pins) rather than a user."""
        return self.type not in _USER_MESSAGE_TYPES

    @override
    def __repr__(self) -> str:
        author = self._data.author.username
        return f"<Message id={int(self.id)} channel_id={int(self.channel_id)} author={author!r}>"


class Reaction:
    """One emoji's reactions on a message.

    Discord: https://docs.discord.com/developers/resources/message#reaction-object
    """

    __slots__ = ("_data", "_message", "_state")

    def __init__(self, state: State, message: PartialMessage, data: ReactionPayload) -> None:
        """A reaction on `message` from its payload."""
        self._state: State = state
        self._message: PartialMessage = message
        self._data: ReactionPayload = data

    @property
    def message(self) -> PartialMessage:
        """The message reacted to."""
        return self._message

    @property
    def payload(self) -> ReactionPayload:
        """The reaction as Discord sent it."""
        return self._data

    @property
    def emoji(self) -> str | PartialEmoji:
        """The unicode emoji, or the custom emoji; either can be passed back to reaction methods."""
        emoji = self._data.emoji
        if emoji.id is None and emoji.name is not None:
            return emoji.name
        return PartialEmoji(id=emoji.id, name=emoji.name, animated=emoji.animated)

    def cleared(self) -> "Reaction":
        """The reaction once its last use is removed: every count 0, no longer the bot's."""
        data = msgspec.structs.replace(
            self._data,
            count=0,
            count_details=ReactionCountDetails(burst=0, normal=0),
            me=False,
            me_burst=False,
        )
        return Reaction(self._state, self._message, data)

    @property
    def count(self) -> int:
        """Reactions with this emoji, normal and super."""
        return self._data.count

    @property
    def normal_count(self) -> int:
        """Normal reactions with this emoji."""
        return self._data.count_details.normal

    @property
    def burst_count(self) -> int:
        """Super reactions with this emoji."""
        return self._data.count_details.burst

    @property
    def me(self) -> bool:
        """Whether the bot reacted with it."""
        return self._data.me

    def is_custom_emoji(self) -> bool:
        """Whether the emoji is a custom one."""
        return self._data.emoji.id is not None

    async def users(self, *, limit: int | None = 100, burst: bool = False) -> AsyncIterator["User"]:
        """The users who reacted, in ID order, 100 at a time.

        Discord: https://docs.discord.com/developers/resources/message#get-reactions
        """
        from shoal.models.user import User

        message = self._message
        state = self._state
        remaining = limit
        after: Snowflake | UnsetType = UNSET
        kind = ReactionType.BURST if burst else ReactionType.NORMAL
        while remaining is None or remaining > 0:
            size = LIST_MESSAGES_MAX_LIMIT if remaining is None else min(remaining, LIST_MESSAGES_MAX_LIMIT)
            params = ListReactionsParams(type=kind, after=after, limit=size)
            page = await state.rest.reactions.list(message.channel_id, message.id, self.emoji, params)
            for user in page:
                yield User(state, user)
            if remaining is not None:
                remaining -= len(page)
            if len(page) < size:
                return
            after = page[-1].id

    async def remove(self, user: Hashable, /) -> None:
        """Remove `user`'s reaction with this emoji.

        Discord: https://docs.discord.com/developers/resources/message#delete-user-reaction
        """
        await self._message.remove_reaction(self.emoji, user)

    async def clear(self) -> None:
        """Remove every reaction with this emoji.

        Discord: https://docs.discord.com/developers/resources/message#delete-all-reactions-for-emoji
        """
        await self._message.clear_reaction(self.emoji)

    @override
    def __repr__(self) -> str:
        return f"<Reaction emoji={self.emoji!r} count={self.count}>"


def _reaction(emoji: EmojiLike) -> ReactionEmoji:
    """`emoji` as the reaction endpoints take it; a string (unicode, or `name:id`) passes through."""
    return emoji if isinstance(emoji, str) else partial_emoji(emoji)


def clean_mentions(
    state: State,
    text: str,
    *,
    guild_id: int | None,
    mentioned: "Iterable[User | Member]" = (),
    channels: bool = True,
    nicknames: bool = True,
) -> str:
    """`text` with user, role and channel mentions written as names, and nothing in it able to ping.

    Users come from `mentioned` (a message's own mentions), then the cache; `nicknames` names members
    by their nickname. `channels` names channel mentions too. What is not known shows as
    `@deleted-user`, `@deleted-role` or `#deleted-channel`.
    """
    from shoal.models.channel import DMChannel, resolve_cached_channel
    from shoal.models.guild import Guild
    from shoal.models.role import Role
    from shoal.models.user import User

    known = {user.id: user for user in mentioned}
    guild = Guild.from_cache(state, guild_id) if guild_id is not None else None

    def named(match: re.Match[str]) -> str:
        kind, found_id = match[1], int(match[2])
        if kind in {"@", "@!"}:
            user: User | Member | None = known.get(Snowflake(found_id))
            if user is None and guild is not None:
                user = guild.get_member(found_id)
            if user is None:
                user = User.from_cache(state, found_id)
            if user is None:
                return "@deleted-user"
            return f"@{user.display_name if nicknames else user.name}"
        if kind == "@&":
            role = Role.from_cache(state, found_id)
            return "@deleted-role" if role is None else f"@{role.name}"
        if not channels:
            return match[0]
        channel = resolve_cached_channel(state, found_id)
        if channel is None:
            return "#deleted-channel"
        return match[0] if isinstance(channel, DMChannel) else f"#{channel.name}"

    return escape_mentions(ANY_MENTION.sub(named, text))
