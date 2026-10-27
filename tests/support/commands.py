"""A started `Bot` with the prefix `!`, and a way to send it messages through the gateway.

bot, transport = await bot_started()
await say(bot, transport, "!ping", replies=1)
assert sent(transport) == ["Pong"]
"""

import itertools
from collections.abc import Callable, Iterator, Sequence
from typing import overload

import msgspec

from shoal.commands.bot import Bot, Prefix
from shoal.commands.context import Context
from shoal.commands.view import StringView
from shoal.models.message import Message
from shoal.payloads import Intents, MessageCreate
from shoal.rest.client import RestClient, Token
from tests.support.client import Recorder, feed, started
from tests.support.fakes import FakeTransport, settle
from tests.support.models import ALICE, BOT, GENERAL, GUILD, Json, decoded, message, user

_IDS: Iterator[int] = itertools.count(5000)


class PrefixBot(Bot):
    """A bot whose prefix tests can choose (`!` by default), built the way `started` builds clients."""

    prefix: Prefix = "!"

    def __init__(self, *, intents: Intents, rest: Callable[[Token], RestClient]) -> None:
        super().__init__(type(self).prefix, intents=intents, rest=rest)


@overload
async def bot_started() -> tuple[PrefixBot, FakeTransport]: ...
@overload
async def bot_started[B: PrefixBot](kind: type[B]) -> tuple[B, FakeTransport]: ...
async def bot_started(kind: type[PrefixBot] = PrefixBot) -> tuple[PrefixBot, FakeTransport]:
    """A bot that logged in, received `READY` and the test guild, as `started` does for clients."""
    return await started(kind)


async def say(
    bot: Bot,
    transport: FakeTransport,
    content: str,
    *,
    author: int = ALICE,
    channel: int = GENERAL,
    in_guild: bool = True,
    from_bot: bool = False,
    replies: int = 0,
    attachments: Sequence[Json] = (),
) -> int:
    """Send `content` (with `attachments`) as a message, queueing `replies` answers to what the bot
    sends; the message's ID."""
    for _ in range(replies):
        transport.queue(200, message(next(_IDS), channel_id=channel, author=user(BOT, "shoalbot")))
    message_id = next(_IDS)
    who = user(author, "alice" if author == ALICE else f"user{author}") | ({"bot": True} if from_bot else {})
    data = message(message_id, channel_id=channel, author=who, content=content, attachments=list(attachments))
    if in_guild:
        data["guild_id"] = str(GUILD)
    await feed(bot, "MESSAGE_CREATE", data)
    await settle(60)
    return message_id


def errors_of(events: Recorder) -> list[Exception]:
    """The errors `on_command_error` received, in order, from a recorder of `command_error`."""
    return [
        args[1] for name, args in events.seen if name == "command_error" and isinstance(args[1], Exception)
    ]


def sent(transport: FakeTransport) -> list[str]:
    """The content of every message the bot sent, in order."""
    contents: list[str] = []
    for request in transport.requests:
        if request.method == "POST" and request.url.endswith("/messages") and request.body is not None:
            content = msgspec.json.decode(request.body, type=dict[str, object]).get("content")
            if isinstance(content, str):
                contents.append(content)
    return contents


DM_CHANNEL = 990
"""A DM channel's ID: messages outside the guild are sent there."""


def message_in(
    bot: Bot, content: str = "", *, author: int = ALICE, channel: int | None = None, in_guild: bool = True
) -> Message:
    """A message model as the gateway would deliver it; in #general, or in a DM outside the guild."""
    who = user(author, "alice" if author == ALICE else f"user{author}")
    where = channel if channel is not None else GENERAL if in_guild else DM_CHANNEL
    data = message(next(_IDS), channel_id=where, author=who, content=content)
    if in_guild:
        data["guild_id"] = str(GUILD)
    return Message(bot.state, decoded(data, MessageCreate))


def context_in(
    bot: Bot, content: str = "", *, author: int = ALICE, channel: int | None = None, in_guild: bool = True
) -> Context:
    """A context for a message, as `Bot.get_context` would build before finding the command."""
    sent = message_in(bot, content, author=author, channel=channel, in_guild=in_guild)
    return Context(bot, sent, view=StringView(content))
