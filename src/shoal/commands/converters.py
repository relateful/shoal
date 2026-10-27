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
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, override

from shoal.commands.errors import (
    BadArgumentError,
    BadBoolArgumentError,
    BadColourArgumentError,
    BadInviteArgumentError,
    BadTimestampArgumentError,
    ChannelNotFoundError,
    ChannelNotReadableError,
    EmojiNotFoundError,
    GuildNotFoundError,
    GuildStickerNotFoundError,
    MemberNotFoundError,
    MessageNotFoundError,
    ObjectNotFoundError,
    PartialEmojiConversionFailureError,
    RoleNotFoundError,
    ScheduledEventNotFoundError,
    SoundboardSoundNotFoundError,
    ThreadNotFoundError,
    UserNotFoundError,
)
from shoal.core.formatting import (
    CHANNEL_MENTION,
    CUSTOM_EMOJI,
    ROLE_MENTION,
    TIMESTAMP,
    USER_MENTION,
    escape_markdown,
    escape_mentions,
    remove_markdown,
)
from shoal.core.snowflake import Snowflake
from shoal.models.activity import Game
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
from shoal.models.message import Message, PartialMessage, clean_mentions
from shoal.models.role import Role
from shoal.models.thread import Thread
from shoal.models.user import User
from shoal.payloads.emoji import PartialEmoji
from shoal.payloads.gateway_events import BotActivity
from shoal.payloads.guild import SearchMembersParams
from shoal.payloads.invite import Invite
from shoal.payloads.scheduled_event import GuildScheduledEvent
from shoal.payloads.soundboard import SoundboardSound
from shoal.payloads.sticker import Sticker
from shoal.rest.errors import ForbiddenError, NotFoundError

if TYPE_CHECKING:
    from shoal.commands.context import Context

type ConvertFunction = Callable[["Context", str], Awaitable[object]]
"""Converts one argument for a context."""

_ID: Final = re.compile(r"([0-9]{15,20})")
_MESSAGE_LINK: Final = re.compile(
    r"^https?://(?:(?:ptb|canary|www)\.)?discord(?:app)?\.com/channels/"
    r"(?P<guild>[0-9]{15,20}|@me)/(?P<channel>[0-9]{15,20})/(?P<message>[0-9]{15,20})/?$"
)
_CHANNEL_MESSAGE: Final = re.compile(r"^(?P<channel>[0-9]{15,20})-(?P<message>[0-9]{15,20})$")
_INVITE: Final = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord(?:app)?\.com/invite|discord\.gg)/(?P<code>[A-Za-z0-9-]+)/?"
)
_EVENT_LINK: Final = re.compile(
    r"https?://(?:(?:ptb|canary|www)\.)?discord(?:app)?\.com/events/[0-9]{15,20}/(?P<event>[0-9]{15,20})/?"
)
_HEX_COLOUR: Final = re.compile(r"(?:0x|#)?(?P<hex>[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})")
_RGB_COLOUR: Final = re.compile(
    r"rgb\(\s*(?P<r>[0-9.]+%?)\s*,\s*(?P<g>[0-9.]+%?)\s*,\s*(?P<b>[0-9.]+%?)\s*\)"
)
_COLOUR_MAX: Final = 255
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


class clean_content(Converter[str]):  # noqa: N801 - the converter's name as every bot writes it
    """The argument with mentions written as names that ping nobody, as `Message.clean_content`.

        async def say(ctx, *, text: commands.clean_content) -> None: ...
        async def say(ctx, *, text: Annotated[str, commands.clean_content(escape_markdown=True)]): ...

    `fix_channel_mentions` names channel mentions too, `use_nicknames` names members by their
    nickname, and `escape_markdown` (or `remove_markdown`) makes formatting show as typed (or go).
    """

    __slots__ = ("escape_markdown", "fix_channel_mentions", "remove_markdown", "use_nicknames")

    def __init__(
        self,
        *,
        fix_channel_mentions: bool = False,
        use_nicknames: bool = True,
        escape_markdown: bool = False,
        remove_markdown: bool = False,
    ) -> None:
        """A converter cleaning as the keywords say."""
        self.fix_channel_mentions: bool = fix_channel_mentions
        self.use_nicknames: bool = use_nicknames
        self.escape_markdown: bool = escape_markdown
        self.remove_markdown: bool = remove_markdown

    @override
    async def convert(self, ctx: "Context", argument: str) -> str:
        cleaned = clean_mentions(
            ctx.state,
            argument,
            guild_id=ctx.guild.id if ctx.guild is not None else None,
            mentioned=ctx.message.mentions if ctx.message is not None else (),
            channels=self.fix_channel_mentions,
            nicknames=self.use_nicknames,
        )
        if self.escape_markdown:
            return escape_mentions(escape_markdown(cleaned))
        if self.remove_markdown:
            return escape_mentions(remove_markdown(cleaned))
        return cleaned


def _id_in(pattern: re.Pattern[str], argument: str) -> Snowflake | None:
    """The ID in `argument` when it is all of `pattern` (a mention) or a bare ID."""
    match = pattern.fullmatch(argument) or _ID.fullmatch(argument)
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
    member_id = _id_in(USER_MENTION, argument)
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
    user_id = _id_in(USER_MENTION, argument)
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
    role_id = _id_in(ROLE_MENTION, argument)
    found = guild.get_role(role_id) if role_id is not None else None
    if found is None:
        found = next((role for role in guild.roles if role.name == argument), None)
    if found is None:
        raise RoleNotFoundError(argument)
    return found


def channel_converter[T](kind: type[T]) -> Callable[["Context", str], Awaitable[T]]:
    """A converter to channels of class `kind`, by mention, ID or name in the context's guild."""

    async def convert(ctx: "Context", argument: str) -> T:
        channel_id = _id_in(CHANNEL_MENTION, argument)
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
    custom = CUSTOM_EMOJI.fullmatch(argument)
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
        PartialEmojiConversionFailureError: The argument is not a custom emoji's text.
    """
    custom = CUSTOM_EMOJI.fullmatch(argument)
    if custom is None:
        raise PartialEmojiConversionFailureError(argument)
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
        ObjectNotFoundError: The argument holds no ID.
    """
    match = USER_MENTION.fullmatch(argument) or ROLE_MENTION.fullmatch(argument)
    match = match or CHANNEL_MENTION.fullmatch(argument) or _ID.fullmatch(argument)
    if match is None:
        raise ObjectNotFoundError(argument)
    return Object(int(match.group(1)))


def to_colour(argument: str) -> int:
    """A colour as an RGB integer: `#RRGGBB`, `0xRRGGBB`, `RRGGBB`, `#RGB` or `rgb(r, g, b)`.

    `rgb` takes 0 to 255 for each, or percentages.

    Raises:
        BadColourArgumentError: The argument is none of those.
    """
    hex_match = _HEX_COLOUR.fullmatch(argument.strip())
    if hex_match is not None:
        digits = hex_match["hex"]
        return int(digits if len(digits) == 6 else "".join(digit * 2 for digit in digits), 16)  # noqa: PLR2004 - RRGGBB
    rgb = _RGB_COLOUR.fullmatch(argument.strip())
    if rgb is None:
        raise BadColourArgumentError(argument)
    value = 0
    for part in (rgb["r"], rgb["g"], rgb["b"]):
        level = float(part[:-1]) * _COLOUR_MAX / 100 if part.endswith("%") else float(part)
        if not 0 <= level <= _COLOUR_MAX or (not part.endswith("%") and not level.is_integer()):
            raise BadColourArgumentError(argument)
        value = (value << 8) | round(level)
    return value


async def to_invite(ctx: "Context", argument: str) -> Invite:
    """An invite by link (`discord.gg/code`) or code, fetched from Discord.

    Raises:
        BadInviteArgumentError: There is no such invite, or it expired.
    """
    link = _INVITE.fullmatch(argument)
    code = link["code"] if link is not None else argument
    try:
        return await ctx.state.rest.invites.get(code)
    except NotFoundError:
        raise BadInviteArgumentError(argument) from None


def to_sticker(ctx: "Context", argument: str) -> Sticker:
    """A sticker of the context's guild, by ID or name, from the cache.

    Raises:
        GuildStickerNotFoundError: No sticker matches, or the command is used outside a guild.
    """
    guild = ctx.guild
    if guild is not None:
        sticker_id = _id_in(_ID, argument)
        found = (
            guild.get_sticker(sticker_id)
            if sticker_id is not None
            else next((sticker for sticker in guild.stickers if sticker.name == argument), None)
        )
        if found is not None:
            return found
    raise GuildStickerNotFoundError(argument)


def to_scheduled_event(ctx: "Context", argument: str) -> GuildScheduledEvent:
    """A scheduled event of the context's guild, by link, ID or name, from the cache.

    Raises:
        ScheduledEventNotFoundError: No event matches, or the command is used outside a guild.
    """
    guild = ctx.guild
    if guild is not None:
        link = _EVENT_LINK.fullmatch(argument)
        event_id = Snowflake(link["event"]) if link is not None else _id_in(_ID, argument)
        found = (
            guild.get_scheduled_event(event_id)
            if event_id is not None
            else next((event for event in guild.scheduled_events if event.name == argument), None)
        )
        if found is not None:
            return found
    raise ScheduledEventNotFoundError(argument)


def to_soundboard_sound(ctx: "Context", argument: str) -> SoundboardSound:
    """A soundboard sound of the context's guild, by ID or name, from the cache.

    Raises:
        SoundboardSoundNotFoundError: No sound matches, or the command is used outside a guild.
    """
    guild = ctx.guild
    if guild is not None:
        sound_id = _id_in(_ID, argument)
        found = (
            guild.get_soundboard_sound(sound_id)
            if sound_id is not None
            else next((sound for sound in guild.soundboard_sounds if sound.name == argument), None)
        )
        if found is not None:
            return found
    raise SoundboardSoundNotFoundError(argument)


def to_timestamp(argument: str) -> datetime:
    """The moment a timestamp (`<t:1618953630>`, any style) shows, in UTC.

    Raises:
        BadTimestampArgumentError: The argument is not a timestamp.
    """
    match = TIMESTAMP.fullmatch(argument)
    if match is None:
        raise BadTimestampArgumentError(argument)
    try:
        return datetime.fromtimestamp(int(match[1]), tz=UTC)
    except (OverflowError, OSError, ValueError):
        raise BadTimestampArgumentError(argument) from None


def _sync[T](function: Callable[[str], T]) -> Callable[["Context", str], Awaitable[T]]:
    """`function` of the argument alone, as a converter."""

    async def convert(ctx: "Context", argument: str) -> T:
        del ctx
        return function(argument)

    return convert


def _with_context[T](function: Callable[["Context", str], T]) -> Callable[["Context", str], Awaitable[T]]:
    """A synchronous `function` of the context and the argument, as a converter."""

    async def convert(ctx: "Context", argument: str) -> T:
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


class _Using[T](Converter[T]):
    """A converter class over one of the conversion functions above."""

    __slots__ = ()

    @abstractmethod
    def _conversion(self) -> Callable[["Context", str], Awaitable[T]]:
        """The function that converts."""

    @override
    async def convert(self, ctx: "Context", argument: str) -> T:
        return await self._conversion()(ctx, argument)


class MemberConverter(_Using[Member]):
    """A member: what a `Member` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[Member]]:
        return to_member


class UserConverter(_Using[User]):
    """A user: what a `User` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[User]]:
        return to_user


class RoleConverter(_Using[Role]):
    """A role of the guild: what a `Role` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[Role]]:
        return to_role


class MessageConverter(_Using[Message]):
    """A message, fetched: what a `Message` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[Message]]:
        return to_message


class PartialMessageConverter(_Using[PartialMessage]):
    """A message reference, not fetched: what a `PartialMessage` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[PartialMessage]]:
        return _with_context(to_partial_message)


class GuildChannelConverter(_Using[GuildChannel]):
    """Any channel of the guild: what a `GuildChannel` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[GuildChannel]]:
        return channel_converter(GuildChannel)


class TextChannelConverter(_Using[TextChannel]):
    """A text channel: what a `TextChannel` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[TextChannel]]:
        return channel_converter(TextChannel)


class VoiceChannelConverter(_Using[VoiceChannel]):
    """A voice channel: what a `VoiceChannel` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[VoiceChannel]]:
        return channel_converter(VoiceChannel)


class StageChannelConverter(_Using[StageChannel]):
    """A stage channel: what a `StageChannel` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[StageChannel]]:
        return channel_converter(StageChannel)


class CategoryChannelConverter(_Using[CategoryChannel]):
    """A category: what a `CategoryChannel` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[CategoryChannel]]:
        return channel_converter(CategoryChannel)


class ForumChannelConverter(_Using[ForumChannel]):
    """A forum channel: what a `ForumChannel` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[ForumChannel]]:
        return channel_converter(ForumChannel)


class ThreadConverter(_Using[Thread]):
    """A thread: what a `Thread` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[Thread]]:
        return channel_converter(Thread)


class GuildConverter(_Using[Guild]):
    """A cached guild: what a `Guild` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[Guild]]:
        return to_guild


class EmojiConverter(_Using[Emoji]):
    """A cached custom emoji: what an `Emoji` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[Emoji]]:
        return to_emoji


class PartialEmojiConverter(_Using[PartialEmoji]):
    """A custom emoji's text: what a `PartialEmoji` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[PartialEmoji]]:
        return _sync(to_partial_emoji)


class ObjectConverter(_Using[Object]):
    """Anything with an ID: what an `Object` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[Object]]:
        return _sync(to_object)


class ColourConverter(_Using[int]):
    """A colour, as an RGB integer (`#5865F2`, `0x5865F2`, `rgb(88, 101, 242)`)."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[int]]:
        return _sync(to_colour)


ColorConverter = ColourConverter
"""The same as `ColourConverter`."""


class InviteConverter(_Using[Invite]):
    """An invite, fetched from Discord: what an `Invite` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[Invite]]:
        return to_invite


class GuildStickerConverter(_Using[Sticker]):
    """A sticker of the guild: what a `Sticker` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[Sticker]]:
        return _with_context(to_sticker)


class ScheduledEventConverter(_Using[GuildScheduledEvent]):
    """A scheduled event of the guild: what a `GuildScheduledEvent` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[GuildScheduledEvent]]:
        return _with_context(to_scheduled_event)


class SoundboardSoundConverter(_Using[SoundboardSound]):
    """A soundboard sound of the guild: what a `SoundboardSound` annotation converts to."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[SoundboardSound]]:
        return _with_context(to_soundboard_sound)


class GameConverter(_Using[BotActivity]):
    """A "Playing ..." activity for `bot.change_presence`, named by the argument."""

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[BotActivity]]:
        return _sync(Game)


class Timestamp(_Using[datetime]):
    """The moment a timestamp (`<t:1618953630:R>`) shows, in UTC.

    Clients send no timezone with it: it is the moment the timestamp names.
    """

    __slots__ = ()

    @override
    def _conversion(self) -> Callable[["Context", str], Awaitable[datetime]]:
        return _sync(to_timestamp)


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
    Invite: to_invite,
    Sticker: _with_context(to_sticker),
    GuildScheduledEvent: _with_context(to_scheduled_event),
    SoundboardSound: _with_context(to_soundboard_sound),
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
