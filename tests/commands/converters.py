from datetime import UTC, datetime

import pytest

from shoal.commands import Context
from shoal.commands.converters import (
    BUILT_IN,
    ColorConverter,
    ColourConverter,
    EmojiConverter,
    GameConverter,
    GuildChannelConverter,
    GuildConverter,
    GuildStickerConverter,
    MemberConverter,
    ObjectConverter,
    PartialEmojiConverter,
    PartialMessageConverter,
    RoleConverter,
    ScheduledEventConverter,
    SoundboardSoundConverter,
    TextChannelConverter,
    Timestamp,
    VoiceChannelConverter,
    channel_converter,
    clean_content,
    to_colour,
    to_invite,
    to_object,
    to_partial_emoji,
    to_scheduled_event,
    to_soundboard_sound,
    to_sticker,
    to_timestamp,
)
from shoal.commands.errors import (
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
from shoal.payloads import MessageCreate, PartialEmoji
from tests.support.client import feed
from tests.support.commands import PrefixBot, bot_started, context_in
from tests.support.fakes import FakeTransport
from tests.support.json_payloads import GUILD_SOUND, GUILD_STICKER, INVITE, SCHEDULED_EVENT
from tests.support.models import GUILD, channel, decoded, member, message, role, user

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
    with pytest.raises(PartialEmojiConversionFailureError):
        to_partial_emoji("dance")
    guild = await BUILT_IN[Guild](ctx, "Shoal Test")
    assert isinstance(guild, Guild)
    with pytest.raises(GuildNotFoundError):
        await BUILT_IN[Guild](ctx, str(CAROL))
    assert to_object(f"<@&{STAFF}>") == Object(STAFF)
    assert to_object(str(CAROL)).id == CAROL
    with pytest.raises(ObjectNotFoundError, match="ID or mention 'carol' not found"):
        to_object("carol")


async def test_clean_content_writes_mentions_as_names_that_ping_nobody() -> None:
    _, _, ctx = await world()
    text = f"<@{CAROL}> <@!{DAVE}> <@&{STAFF}> <#{NEWS}> @everyone **hi**"
    plain = await clean_content().convert(ctx, text)
    assert plain == f"@Caz @deleted-user @staff <#{NEWS}> @\u200beveryone **hi**"
    named = await clean_content(fix_channel_mentions=True, use_nicknames=False).convert(ctx, text)
    assert named == "@carol @deleted-user @staff #news-feed @\u200beveryone **hi**"
    assert (
        await clean_content(escape_markdown=True).convert(ctx, "**hi** @here")
        == r"\*\*hi\*\* @" + "\u200bhere"
    )
    assert await clean_content(remove_markdown=True).convert(ctx, "**hi**") == "hi"
    gone = await clean_content(fix_channel_mentions=True).convert(ctx, f"<#{DAVE}> <@&{DAVE}>")
    assert gone == "#deleted-channel @deleted-role"


async def test_a_message_cleans_its_own_content() -> None:
    bot, _, _ = await world()
    data = message(
        9, content=f"hi <@{DAVE}> and <@{CAROL}>", mentions=[user(DAVE, "dave", global_name="Dave")]
    )
    data["guild_id"] = str(GUILD)
    sent = Message(bot.state, decoded(data, MessageCreate))
    assert sent.clean_content == "hi @Dave and @Caz"


STICKER_ID = 723456789012345678
EVENT_ID = 823456789012345678
SOUND_ID = 923456789012345678


async def guild_things() -> tuple[PrefixBot, FakeTransport, Context]:
    bot, transport, ctx = await world()
    sticker = GUILD_STICKER | {"id": str(STICKER_ID), "guild_id": str(GUILD)}
    await feed(bot, "GUILD_STICKERS_UPDATE", {"guild_id": str(GUILD), "stickers": [sticker]})
    event = SCHEDULED_EVENT | {"id": str(EVENT_ID), "guild_id": str(GUILD)}
    await feed(bot, "GUILD_SCHEDULED_EVENT_CREATE", event)
    sound = GUILD_SOUND | {"sound_id": str(SOUND_ID), "guild_id": str(GUILD)}
    await feed(bot, "GUILD_SOUNDBOARD_SOUND_CREATE", sound)
    return bot, transport, ctx


@pytest.mark.parametrize(
    ("argument", "colour"),
    [
        ("#5865F2", 0x5865F2),
        ("0x5865f2", 0x5865F2),
        ("5865F2", 0x5865F2),
        ("#abc", 0xAABBCC),
        ("rgb(88, 101, 242)", 0x5865F2),
        ("rgb(100%, 0%, 50%)", 0xFF0080),
    ],
)
def test_colours_in_every_written_form(argument: str, colour: int) -> None:
    assert to_colour(argument) == colour


@pytest.mark.parametrize("argument", ["blurple", "#12345", "rgb(256, 0, 0)", "rgb(1.5, 0, 0)", "rgb(1, 2)"])
def test_what_is_not_a_colour_is_refused(argument: str) -> None:
    with pytest.raises(BadColourArgumentError):
        to_colour(argument)


async def test_guild_stickers_events_and_sounds_by_id_or_name() -> None:
    _, _, ctx = await guild_things()
    for argument in (str(STICKER_ID), "party"):
        assert to_sticker(ctx, argument).id == STICKER_ID
    link = f"https://discord.com/events/{GUILD}0000000000000/{EVENT_ID}"
    for argument in (str(EVENT_ID), "Meetup", link):
        assert to_scheduled_event(ctx, argument).id == EVENT_ID
    for argument in (str(SOUND_ID), "Yay"):
        assert to_soundboard_sound(ctx, argument).sound_id == SOUND_ID
    with pytest.raises(GuildStickerNotFoundError):
        to_sticker(ctx, "nope")
    with pytest.raises(ScheduledEventNotFoundError):
        to_scheduled_event(ctx, "nope")
    with pytest.raises(SoundboardSoundNotFoundError):
        to_soundboard_sound(ctx, "nope")
    dm = context_in(ctx.bot, in_guild=False)
    with pytest.raises(GuildStickerNotFoundError):
        to_sticker(dm, "party")


async def test_invites_are_fetched_by_link_or_code() -> None:
    _, transport, ctx = await world()
    transport.queue(200, INVITE)
    invite = await to_invite(ctx, "https://discord.gg/0vCdhLbwjZZTWZLD")
    assert invite.code == "0vCdhLbwjZZTWZLD"
    assert transport.requests[-1].url.split("?")[0].endswith("/invites/0vCdhLbwjZZTWZLD")
    transport.queue(404, {"code": 10006, "message": "Unknown Invite"})
    with pytest.raises(BadInviteArgumentError):
        await to_invite(ctx, "gone")


def test_timestamps_become_utc_moments() -> None:
    assert to_timestamp("<t:1618953630:R>") == datetime(2021, 4, 20, 21, 20, 30, tzinfo=UTC)
    with pytest.raises(BadTimestampArgumentError):
        to_timestamp("yesterday")
    with pytest.raises(BadTimestampArgumentError):
        to_timestamp("<t:99999999999999999999>")


async def test_converter_classes_convert_as_their_annotations_do() -> None:
    _, _, ctx = await guild_things()
    assert (await MemberConverter().convert(ctx, str(CAROL))).id == CAROL
    assert (await RoleConverter().convert(ctx, "staff")).id == STAFF
    assert (await TextChannelConverter().convert(ctx, "news-feed")).id == NEWS
    assert (await VoiceChannelConverter().convert(ctx, "chat")).id == CHAT
    assert (await GuildChannelConverter().convert(ctx, "chat")).id == CHAT
    assert (await EmojiConverter().convert(ctx, "party")).id == EMOJI_ID
    assert (await PartialEmojiConverter().convert(ctx, f"<:x:{EMOJI_ID}>")).id == EMOJI_ID
    assert (await ObjectConverter().convert(ctx, str(CAROL))).id == CAROL
    assert await ColourConverter().convert(ctx, "#000001") == 1
    assert ColorConverter is ColourConverter
    assert (await GuildStickerConverter().convert(ctx, "party")).id == STICKER_ID
    assert (await ScheduledEventConverter().convert(ctx, "Meetup")).id == EVENT_ID
    assert (await SoundboardSoundConverter().convert(ctx, "Yay")).sound_id == SOUND_ID
    assert (await GameConverter().convert(ctx, "chess")).name == "chess"
    assert (await Timestamp().convert(ctx, "<t:0>")).year == 1970
    assert (await GuildConverter().convert(ctx, "Shoal Test")).id == GUILD
    assert (await PartialMessageConverter().convert(ctx, f"{NEWS}-{CAROL}")).id == CAROL
