"""What everything you can send messages to shares: channels, threads, users and members.

    await channel.send("hello", embed=embed)
    async for message in channel.history(limit=200):
        ...
    async with channel.typing():
        await slow_work()

Discord: https://docs.discord.com/developers/resources/message
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from types import TracebackType
from typing import TYPE_CHECKING, Self, final

from msgspec import UNSET

from shoal.core.snowflake import Snowflake
from shoal.models.base import Hashable
from shoal.models.defaults import TYPING_REFRESH
from shoal.models.sending import EmbedLike, outgoing
from shoal.models.state import ComponentView, State
from shoal.payloads.message import (
    LIST_MESSAGES_MAX_LIMIT,
    AllowedMentions,
    ListMessagesParams,
    ListPinsParams,
    MessageReference,
)
from shoal.payloads.poll import PollCreateRequest
from shoal.rest.files import File

if TYPE_CHECKING:
    from shoal.models.message import Message, PartialMessage

type MessageTarget = Message | PartialMessage | MessageReference
"""What `reference=` accepts: a message to reply to, or a reference you built."""
type Before = int | datetime | Hashable
"""A point in a channel's history: a message, a message ID, or a time."""


def _cursor(point: int | datetime | Hashable) -> Snowflake:
    if isinstance(point, Hashable):
        return point.id
    if isinstance(point, datetime):
        return Snowflake.from_datetime(point)
    return Snowflake(point)


class Messageable:
    """Something messages can be sent to. Subclasses say which channel that is.

    Discord: https://docs.discord.com/developers/resources/message#create-message
    """

    __slots__ = ()

    @property
    def _messageable_state(self) -> State:
        raise NotImplementedError

    async def _messageable_channel(self) -> tuple[Snowflake, Snowflake | None]:
        """The channel to send to and its guild; a user opens a DM first."""
        raise NotImplementedError

    async def send(
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
        reference: MessageTarget | None = None,
        mention_author: bool | None = None,
        view: ComponentView | None = None,
        suppress_embeds: bool = False,
        silent: bool = False,
        poll: PollCreateRequest | None = None,
    ) -> "Message":
        """Send a message.

        `reference` makes it a reply; `mention_author=False` replies without pinging. `view`'s
        components are sent and, when it has callbacks, its interactions are routed to it.
        `delete_after` deletes the message after that many seconds.

        Raises:
            TypeError: Both `embed` and `embeds`, or both `file` and `files`, were given.
            HTTPError: Discord refused the message.

        Discord: https://docs.discord.com/developers/resources/message#create-message
        """
        from shoal.models.message import Message, PartialMessage

        state = self._messageable_state
        channel_id, guild_id = await self._messageable_channel()
        if mention_author is not None:
            base = allowed_mentions or AllowedMentions()
            allowed_mentions = AllowedMentions(
                parse=base.parse, roles=base.roles, users=base.users, replied_user=mention_author
            )
        message = outgoing(
            content,
            tts=tts,
            embed=embed,
            embeds=embeds,
            file=file,
            files=files,
            allowed_mentions=allowed_mentions,
            view=view,
            suppress_embeds=suppress_embeds,
            silent=silent,
            poll=poll,
        )
        reply: MessageReference | None = None
        if isinstance(reference, Message | PartialMessage):
            reply = reference.to_reference()
        elif reference is not None:
            reply = reference
        sticker_ids = [sticker.id if isinstance(sticker, Hashable) else sticker for sticker in stickers]
        params = message.message_params(reference=reply, sticker_ids=sticker_ids)
        sent = Message(
            state,
            await state.rest.messages.create(channel_id, params, files=message.files),
            guild_id=guild_id,
        )
        if view is not None and view.is_dispatchable():
            state.views.store(view, message_id=sent.id)
        if delete_after is not None:
            sent.delete_later(delete_after)
        return sent

    async def fetch_message(self, message_id: int, /) -> "Message":
        """Get one message from Discord.

        Raises:
            NotFoundError: There is no such message in this channel.

        Discord: https://docs.discord.com/developers/resources/message#get-channel-message
        """
        from shoal.models.message import Message

        channel_id, guild_id = await self._messageable_channel()
        data = await self._messageable_state.rest.messages.get(channel_id, message_id)
        return Message(self._messageable_state, data, guild_id=guild_id)

    async def history(
        self,
        *,
        limit: int | None = 100,
        before: Before | None = None,
        after: Before | None = None,
        around: Before | None = None,
        oldest_first: bool | None = None,
    ) -> AsyncIterator["Message"]:
        """Iterate over the channel's messages, newest first (oldest first with `after`).

        `limit=None` reads the whole history, a page of 100 at a time. `around` returns up to 100
        messages around a point and cannot be combined with `before` or `after`.

        Raises:
            ValueError: `around` was combined with `before` or `after`, or with a limit over 100.

        Discord: https://docs.discord.com/developers/resources/message#get-channel-messages
        """
        from shoal.models.message import Message

        if around is not None and (before is not None or after is not None):
            msg = "around cannot be combined with before or after"
            raise ValueError(msg)
        if around is not None and (limit is None or limit > LIST_MESSAGES_MAX_LIMIT):
            msg = f"around returns at most {LIST_MESSAGES_MAX_LIMIT} messages"
            raise ValueError(msg)
        state = self._messageable_state
        channel_id, guild_id = await self._messageable_channel()
        ascending = oldest_first if oldest_first is not None else (after is not None and before is None)
        remaining = limit
        lower = _cursor(after) if after is not None else None
        upper = _cursor(before) if before is not None else None
        if around is not None:
            page = await state.rest.messages.list(
                channel_id, ListMessagesParams(around=_cursor(around), limit=limit or LIST_MESSAGES_MAX_LIMIT)
            )
            for data in sorted(page, key=lambda item: item.id, reverse=not ascending):
                yield Message(state, data, guild_id=guild_id)
            return
        while remaining is None or remaining > 0:
            size = LIST_MESSAGES_MAX_LIMIT if remaining is None else min(remaining, LIST_MESSAGES_MAX_LIMIT)
            if ascending:
                params = ListMessagesParams(after=lower if lower is not None else Snowflake(0), limit=size)
            else:
                params = ListMessagesParams(before=upper if upper is not None else UNSET, limit=size)
            received = await state.rest.messages.list(channel_id, params)
            # Only one bound goes to Discord; the other is checked here, and crossing it ends the walk.
            page = [
                data
                for data in received
                if (lower is None or data.id > lower) and (upper is None or data.id < upper)
            ]
            page.sort(key=lambda item: item.id, reverse=not ascending)
            for data in page:
                yield Message(state, data, guild_id=guild_id)
            if remaining is not None:
                remaining -= len(page)
            if len(received) < size or len(page) < len(received):
                return
            if ascending:
                lower = page[-1].id
            else:
                upper = page[-1].id

    async def pins(self) -> list["Message"]:
        """The channel's pinned messages, newest first.

        Discord: https://docs.discord.com/developers/resources/message#get-channel-pins
        """
        from shoal.models.message import Message

        state = self._messageable_state
        channel_id, guild_id = await self._messageable_channel()
        pinned: list[Message] = []
        before: datetime | None = None
        while True:
            params = ListPinsParams(before=before) if before is not None else None
            page = await state.rest.messages.list_pins(channel_id, params)
            pinned.extend(Message(state, item.message, guild_id=guild_id) for item in page.items)
            if not page.has_more or not page.items:
                return pinned
            before = page.items[-1].pinned_at

    async def trigger_typing(self) -> None:
        """Show the bot typing for about 10 seconds, or until it sends a message.

        Discord: https://docs.discord.com/developers/resources/channel#trigger-typing-indicator
        """
        channel_id, _ = await self._messageable_channel()
        await self._messageable_state.rest.channels.typing(channel_id)

    def typing(self) -> "Typing":
        """`async with channel.typing():` shows the bot typing until the block ends."""
        return Typing(self)


@final
class Typing:
    """Keeps the typing indicator on while the `async with` block runs.

    Discord: https://docs.discord.com/developers/resources/channel#trigger-typing-indicator
    """

    __slots__ = ("_target", "_task")

    def __init__(self, target: Messageable) -> None:
        """Typing in `target`; use `Messageable.typing()`."""
        self._target: Messageable = target
        self._task: asyncio.Task[None] | None = None

    async def _keep_typing(self) -> None:
        while True:
            await asyncio.sleep(TYPING_REFRESH)
            await self._target.trigger_typing()

    async def __aenter__(self) -> Self:
        await self._target.trigger_typing()
        self._task = asyncio.create_task(self._keep_typing(), name="shoal-typing")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
