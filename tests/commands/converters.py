import pytest

from shoal.commands import Context
from shoal.commands.converters import BUILT_IN, channel_converter, to_object, to_partial_emoji
from shoal.commands.errors import (
    BadArgumentError,
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
from shoal.models.channel import TextChannel, VoiceChannel
from shoal.models.emoji import Emoji
from shoal.models.guild import Guild
from shoal.models.member import Member
from shoal.models.message import Message, PartialMessage
from shoal.models.role import Role
from shoal.models.thread import Thread
from shoal.models.user import User
from shoal.payloads import PartialEmoji
from tests.support.client import feed
from tests.support.commands import PrefixBot, bot_started, context_in
from tests.support.fakes import FakeTransport
from tests.support.models import GUILD, channel, member, message, role, user

CAROL = 123456789012345678
"""A member with an ID as long as a real one, so mentions and IDs parse."""
DAVE = 223456789012345678
"""A user who is not a member and not cached."""
STAFF = 323456789012345678
NEWS = 423456789012345678
CHAT = 523456789012345679
EMOJI_ID = 623456789012345678


async def world() -> tuple[PrefixBot, FakeTransport, Context]:
    bot, transport = await bot_started()
    await feed(
        bot,
        "GUILD_MEMBER_ADD",
        member(CAROL, "carol", nick="Caz", global_name="Carol") | {"guild_id": str(GUILD)},
    )
    await feed(bot, "GUILD_ROLE_CREATE", {"guild_id": str(GUILD), "role": role(STAFF, "staff", position=3)})
    await feed(bot, "CHANNEL_CREATE", channel(NEWS, 0, "news-feed"))
    await feed(bot, "CHANNEL_CREATE", channel(CHAT, 2, "chat"))
    emojis = [{"id": str(EMOJI_ID), "name": "party", "animated": False}]
    await feed(bot, "GUILD_EMOJIS_UPDATE", {"guild_id": str(GUILD), "emojis": emojis})
    return bot, transport, context_in(bot)


async def test_members_are_found_by_mention_id_and_names() -> None:
    _, transport, ctx = await world()
    to_member = BUILT_IN[Member]
    for argument in (f"<@{CAROL}>", f"<@!{CAROL}>", str(CAROL), "carol", "Caz", "Carol"):
        found = await to_member(ctx, argument)
        assert isinstance(found, Member)
        assert found.id == CAROL
    transport.queue(200, member(DAVE, "dave"))
    fetched = await to_member(ctx, str(DAVE))
    assert isinstance(fetched, Member)
    transport.queue(200, [member(DAVE + 1, "erin")])
    searched = await to_member(ctx, "erin")
    assert isinstance(searched, Member)
    assert searched.name == "erin"
    transport.queue(200, [])
    with pytest.raises(MemberNotFoundError, match="'nobody'"):
        await to_member(ctx, "nobody")
    transport.queue(404, {"message": "Unknown Member", "code": 10007})
    with pytest.raises(MemberNotFoundError):
        await to_member(ctx, str(DAVE + 5))


async def test_members_need_a_guild() -> None:
    bot, _ = await bot_started()
    with pytest.raises(MemberNotFoundError):
        await BUILT_IN[Member](context_in(bot, in_guild=False), "carol")


async def test_users_are_found_cached_or_fetched() -> None:
    _, transport, ctx = await world()
    to_user = BUILT_IN[User]
    found = await to_user(ctx, f"<@{CAROL}>")
    assert isinstance(found, User)
    assert found.id == CAROL
    named = await to_user(ctx, "Carol")
    assert isinstance(named, User)
    transport.queue(200, user(DAVE, "dave"))
    fetched = await to_user(ctx, str(DAVE))
    assert isinstance(fetched, User)
    assert fetched.name == "dave"
    transport.queue(404, {"message": "Unknown User", "code": 10013})
    with pytest.raises(UserNotFoundError):
        await to_user(ctx, str(DAVE + 1))
    with pytest.raises(UserNotFoundError):
        await to_user(ctx, "nobody")


async def test_roles_channels_and_threads() -> None:
    _, _, ctx = await world()
    for argument in (f"<@&{STAFF}>", str(STAFF), "staff"):
        found = await BUILT_IN[Role](ctx, argument)
        assert isinstance(found, Role)
        assert found.id == STAFF
    with pytest.raises(RoleNotFoundError):
        await BUILT_IN[Role](ctx, "admins")
    text = await BUILT_IN[TextChannel](ctx, f"<#{NEWS}>")
    assert isinstance(text, TextChannel)
    assert (await BUILT_IN[TextChannel](ctx, "news-feed")) == text
    with pytest.raises(ChannelNotFoundError):
        await BUILT_IN[TextChannel](ctx, str(CHAT))
    voice = await BUILT_IN[VoiceChannel](ctx, "chat")
    assert isinstance(voice, VoiceChannel)
    thread = await BUILT_IN[Thread](ctx, "a thread")
    assert isinstance(thread, Thread)
    with pytest.raises(ThreadNotFoundError):
        await BUILT_IN[Thread](ctx, "news-feed")


async def test_channels_outside_a_guild_are_found_by_id_only() -> None:
    bot, _, _ = await world()
    dm_ctx = context_in(bot, in_guild=False)
    found = await channel_converter(TextChannel)(dm_ctx, str(NEWS))
    assert isinstance(found, TextChannel)
    with pytest.raises(ChannelNotFoundError):
        await channel_converter(TextChannel)(dm_ctx, "news-feed")


async def test_messages_by_link_ids_or_id_in_the_channel() -> None:
    _, transport, ctx = await world()
    link = f"https://discord.com/channels/{STAFF}/{NEWS}/{NEWS + 9}"
    partial = await BUILT_IN[PartialMessage](ctx, link)
    assert isinstance(partial, PartialMessage)
    assert (partial.channel_id, partial.id) == (NEWS, NEWS + 9)
    in_dms = await BUILT_IN[PartialMessage](ctx, f"https://discord.com/channels/@me/{NEWS}/{NEWS + 9}")
    assert isinstance(in_dms, PartialMessage)
    pair = await BUILT_IN[PartialMessage](ctx, f"{NEWS}-{NEWS + 9}")
    assert isinstance(pair, PartialMessage)
    transport.queue(200, message(NEWS + 9, channel_id=NEWS))
    fetched = await BUILT_IN[Message](ctx, str(NEWS + 9))
    assert isinstance(fetched, Message)
    transport.queue(404, {"message": "Unknown Message", "code": 10008})
    with pytest.raises(MessageNotFoundError):
        await BUILT_IN[Message](ctx, str(NEWS + 8))
    transport.queue(403, {"message": "Missing Access", "code": 50001})
    with pytest.raises(ChannelNotReadableError, match=f"<#{NEWS}>"):
        await BUILT_IN[Message](ctx, f"{NEWS}-{NEWS + 7}")
    with pytest.raises(MessageNotFoundError):
        await BUILT_IN[PartialMessage](ctx, "not a message")


async def test_emojis_guilds_and_objects() -> None:
    _, _, ctx = await world()
    for argument in (f"<:party:{EMOJI_ID}>", str(EMOJI_ID), "party"):
        found = await BUILT_IN[Emoji](ctx, argument)
        assert isinstance(found, Emoji)
    with pytest.raises(EmojiNotFoundError):
        await BUILT_IN[Emoji](ctx, "missing")
    assert to_partial_emoji(f"<a:dance:{EMOJI_ID}>") == PartialEmoji(
        id=Snowflake(EMOJI_ID), name="dance", animated=True
    )
    with pytest.raises(EmojiNotFoundError):
        to_partial_emoji("dance")
    guild = await BUILT_IN[Guild](ctx, "Shoal Test")
    assert isinstance(guild, Guild)
    with pytest.raises(GuildNotFoundError):
        await BUILT_IN[Guild](ctx, str(CAROL))
    assert to_object(f"<@&{STAFF}>") == Object(STAFF)
    assert to_object(str(CAROL)).id == CAROL
    with pytest.raises(BadArgumentError, match="not an ID"):
        to_object("carol")
