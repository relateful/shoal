"""Turning a command's text arguments into what its parameters ask for.

    @bot.command()
    async def ban(ctx, member: Member, days: Range[int, 0, 7] = 1, *, reason: str | None = None): ...

Members, users, roles, channels and threads are found by mention, by ID, then by name, from the
cache first and from Discord when they are not cached. Custom conversions subclass `Converter`:

    class Lowercase(commands.Converter[str]):
        async def convert(self, ctx, argument):
            return argument.lower()
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Final

from shoal.commands.errors import (
    BadArgumentError,
    BadBoolArgumentError,
    ChannelNotFoundError,
    ChannelNotReadableError,
    EmojiNotFoundError,
    GuildNotFoundError,
    MemberNotFoundError,
    MessageNotFoundError,
    RoleNotFoundError,
    ThreadNotFoundError,
    UserNotFoundError,
)
from shoal.core.snowflake import Snowflake
from shoal.models.base import Object
from shoal.models.channel import (
    CategoryChannel,
    DMChannel,
    ForumChannel,
    GuildChannel,
    MediaChannel,
    StageChannel,
    TextChannel,
    VoiceChannel,
)
from shoal.models.emoji import Emoji
from shoal.models.guild import Guild
from shoal.models.member import Member
from shoal.models.message import Message, PartialMessage
from shoal.models.role import Role
from shoal.models.thread import Thread
from shoal.models.user import User
from shoal.payloads.emoji import PartialEmoji
from shoal.payloads.guild import SearchMembersParams
from shoal.rest.errors import ForbiddenError, NotFoundError

if TYPE_CHECKING:
    from shoal.commands.context import Context

type ConvertFunction = Callable[["Context", str], Awaitable[object]]
"""Converts one argument for a context."""

_ID: Final = re.compile(r"^([0-9]{15,20})$")
_USER_MENTION: Final = re.compile(r"^<@!?([0-9]{15,20})>$")
_ROLE_MENTION: Final = re.compile(r"^<@&([0-9]{15,20})>$")
_CHANNEL_MENTION: Final = re.compile(r"^<#([0-9]{15,20})>$")
_CUSTOM_EMOJI: Final = re.compile(r"^<(a?):([A-Za-z0-9_]{1,32}):([0-9]{15,20})>$")
_MESSAGE_LINK: Final = re.compile(
    r"^https?://(?:(?:ptb|canary|www)\.)?discord(?:app)?\.com/channels/"
    r"(?P<guild>[0-9]{15,20}|@me)/(?P<channel>[0-9]{15,20})/(?P<message>[0-9]{15,20})/?$"
)
_CHANNEL_MESSAGE: Final = re.compile(r"^(?P<channel>[0-9]{15,20})-(?P<message>[0-9]{15,20})$")
_TRUE: Final = frozenset({"yes", "y", "true", "t", "1", "enable", "on"})
_FALSE: Final = frozenset({"no", "n", "false", "f", "0", "disable", "off"})


class Converter[T](ABC):
    """A conversion of its own: subclass it and annotate a parameter with the class (or an instance)."""

    __slots__ = ()

    @abstractmethod
    async def convert(self, ctx: "Context", argument: str) -> T:
        """`argument` as the parameter wants it.

        Raises:
            BadArgumentError: The argument cannot be converted.
        """


def _id_in(pattern: re.Pattern[str], argument: str) -> Snowflake | None:
    match = pattern.match(argument) or _ID.match(argument)
    return Snowflake(match.group(1)) if match is not None else None


def to_bool(argument: str) -> bool:
    """`yes`/`no`, `true`/`false`, `on`/`off`, `enable`/`disable`, `1`/`0` and their first letters.

    Raises:
        BadBoolArgumentError: The argument is none of those.
    """
    lowered = argument.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise BadBoolArgumentError(argument)


async def to_member(ctx: "Context", argument: str) -> Member:
    """A member of the context's guild, by mention, ID, `name#0000`, username, global or nickname.

    Raises:
        MemberNotFoundError: No member matches, or the command is used outside a guild.
    """
    guild = ctx.guild
    if guild is None:
        raise MemberNotFoundError(argument)
    member_id = _id_in(_USER_MENTION, argument)
    if member_id is not None:
        found = guild.get_member(member_id)
        if found is not None:
            return found
        try:
            return await guild.fetch_member(member_id)
        except NotFoundError:
            raise MemberNotFoundError(argument) from None
    named = guild.get_member_named(argument)
    if named is not None:
        return named
    query = argument.split("#", 1)[0]
    matches = await ctx.state.rest.members.search(guild.id, SearchMembersParams(query=query, limit=100))
    for data in matches:
        member = Member(ctx.state, data, guild.id)
        if argument in {member.name, member.global_name, member.nick, str(member)}:
            return member
    raise MemberNotFoundError(argument)


async def to_user(ctx: "Context", argument: str) -> User:
    """A user by mention, ID, `name#0000`, username or global name (cached users only for names).

    Raises:
        UserNotFoundError: No user matches.
    """
    user_id = _id_in(_USER_MENTION, argument)
    if user_id is not None:
        cached = ctx.bot.get_user(user_id)
        if cached is not None:
            return cached
        try:
            return await ctx.bot.fetch_user(user_id)
        except NotFoundError:
            raise UserNotFoundError(argument) from None
    for user in ctx.bot.users:
        if argument in {user.name, str(user)} or (
            user.global_name is not None and user.global_name == argument
        ):
            return user
    raise UserNotFoundError(argument)


async def to_role(ctx: "Context", argument: str) -> Role:
    """A role of the context's guild, by mention, ID or name.

    Raises:
        RoleNotFoundError: No role matches, or the command is used outside a guild.
    """
    guild = ctx.guild
    if guild is None:
        raise RoleNotFoundError(argument)
    role_id = _id_in(_ROLE_MENTION, argument)
    found = guild.get_role(role_id) if role_id is not None else None
    if found is None:
        found = next((role for role in guild.roles if role.name == argument), None)
    if found is None:
        raise RoleNotFoundError(argument)
    return found


def channel_converter[T](kind: type[T]) -> ConvertFunction:
    """A converter to channels of class `kind`, by mention, ID or name in the context's guild."""

    async def convert(ctx: "Context", argument: str) -> T:
        channel_id = _id_in(_CHANNEL_MENTION, argument)
        guild = ctx.guild
        candidates: list[object] = []
        if channel_id is not None:
            found = (
                guild.get_channel_or_thread(channel_id)
                if guild is not None
                else ctx.bot.get_channel(channel_id)
            )
            candidates = [found] if found is not None else []
        elif guild is not None:
            candidates = [channel for channel in guild.channels if channel.name == argument]
            candidates.extend(thread for thread in guild.threads if thread.name == argument)
        for candidate in candidates:
            if isinstance(candidate, kind):
                return candidate
        if kind is Thread:
            raise ThreadNotFoundError(argument)
        raise ChannelNotFoundError(argument)

    return convert


async def to_message(ctx: "Context", argument: str) -> Message:
    """A message by link, by `channel-message` IDs, or by ID in the context's channel.

    Raises:
        MessageNotFoundError: The message does not exist.
        ChannelNotReadableError: The bot cannot read the message's channel.
    """
    partial = to_partial_message(ctx, argument)
    try:
        return await partial.fetch()
    except NotFoundError:
        raise MessageNotFoundError(argument) from None
    except ForbiddenError:
        channel = f"<#{partial.channel_id}>"
        raise ChannelNotReadableError(channel) from None


def to_partial_message(ctx: "Context", argument: str) -> PartialMessage:
    """A message reference by link, `channel-message` IDs, or ID in the context's channel, unfetched.

    Raises:
        MessageNotFoundError: The argument names no message.
    """
    link = _MESSAGE_LINK.match(argument) or _CHANNEL_MESSAGE.match(argument)
    if link is not None:
        guild = link.groupdict().get("guild")
        guild_id = None if guild in {None, "@me"} else int(guild or 0)
        return PartialMessage(
            ctx.state, int(link.group("channel")), int(link.group("message")), guild_id=guild_id
        )
    message_id = _id_in(_ID, argument)
    if message_id is None:
        raise MessageNotFoundError(argument)
    guild_id = ctx.guild.id if ctx.guild is not None else None
    return PartialMessage(ctx.state, ctx.channel.id, message_id, guild_id=guild_id)


async def to_emoji(ctx: "Context", argument: str) -> Emoji:
    """A guild's custom emoji by its text (`<:name:id>`), ID or name; the context's guild first.

    Raises:
        EmojiNotFoundError: No cached emoji matches.
    """
    custom = _CUSTOM_EMOJI.match(argument)
    emoji_id = Snowflake(custom.group(3)) if custom is not None else _id_in(_ID, argument)
    if emoji_id is not None:
        found = ctx.bot.get_emoji(emoji_id)
        if found is not None:
            return found
    elif ctx.guild is not None:
        named = next((emoji for emoji in ctx.guild.emojis if emoji.name == argument), None)
        if named is not None:
            return named
    raise EmojiNotFoundError(argument)


def to_partial_emoji(argument: str) -> PartialEmoji:
    """A custom emoji from its text (`<:name:id>` or `<a:name:id>`), which need not be cached.

    Raises:
        EmojiNotFoundError: The argument is not a custom emoji's text.
    """
    custom = _CUSTOM_EMOJI.match(argument)
    if custom is None:
        raise EmojiNotFoundError(argument)
    animated, name, emoji_id = custom.groups()
    return PartialEmoji(id=Snowflake(emoji_id), name=name, animated=bool(animated))


async def to_guild(ctx: "Context", argument: str) -> Guild:
    """A cached guild by ID or name.

    Raises:
        GuildNotFoundError: No cached guild matches.
    """
    guild_id = _id_in(_ID, argument)
    if guild_id is not None:
        found = ctx.bot.get_guild(guild_id)
        if found is not None:
            return found
    named = next((guild for guild in ctx.bot.guilds if guild.name == argument), None)
    if named is None:
        raise GuildNotFoundError(argument)
    return named


def to_object(argument: str) -> Object:
    """Anything with an ID, from a mention or an ID.

    Raises:
        BadArgumentError: The argument holds no ID.
    """
    match = _USER_MENTION.match(argument) or _ROLE_MENTION.match(argument) or _CHANNEL_MENTION.match(argument)
    match = match or _ID.match(argument)
    if match is None:
        msg = f"{argument!r} is not an ID or a mention"
        raise BadArgumentError(msg)
    return Object(int(match.group(1)))


def _sync(function: Callable[[str], object]) -> ConvertFunction:
    async def convert(ctx: "Context", argument: str) -> object:
        del ctx
        return function(argument)

    return convert


def _with_context(function: Callable[["Context", str], object]) -> ConvertFunction:
    async def convert(ctx: "Context", argument: str) -> object:
        return function(ctx, argument)

    return convert


def _primitive(kind: Callable[[str], object], label: str) -> ConvertFunction:
    async def convert(ctx: "Context", argument: str) -> object:
        del ctx
        try:
            return kind(argument)
        except ValueError:
            msg = f"{argument!r} is not {label}"
            raise BadArgumentError(msg) from None

    return convert


async def _identity(ctx: "Context", argument: str) -> str:
    del ctx
    return argument


BUILT_IN: Final[dict[object, ConvertFunction]] = {
    str: _identity,
    int: _primitive(int, "a whole number"),
    float: _primitive(float, "a number"),
    bool: _sync(to_bool),
    Member: to_member,
    User: to_user,
    Role: to_role,
    Message: to_message,
    PartialMessage: _with_context(to_partial_message),
    Emoji: to_emoji,
    PartialEmoji: _sync(to_partial_emoji),
    Guild: to_guild,
    Object: _sync(to_object),
    GuildChannel: channel_converter(GuildChannel),
    TextChannel: channel_converter(TextChannel),
    VoiceChannel: channel_converter(VoiceChannel),
    StageChannel: channel_converter(StageChannel),
    CategoryChannel: channel_converter(CategoryChannel),
    ForumChannel: channel_converter(ForumChannel),
    MediaChannel: channel_converter(MediaChannel),
    Thread: channel_converter(Thread),
    DMChannel: channel_converter(DMChannel),
}
"""The converter for each type a parameter can be annotated with directly."""
