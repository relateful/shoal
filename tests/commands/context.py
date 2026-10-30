import msgspec
import pytest

from shoal.commands import Context, command
from shoal.models.member import Member
from shoal.models.message import Message
from shoal.payloads import MessageFlags
from shoal.rest.files import VoiceMessage
from tests.support.commands import PrefixBot, bot_started, context_in
from tests.support.fakes import FakeTransport, SentRequest, settle
from tests.support.interactions import command as slash
from tests.support.interactions import common, payload
from tests.support.models import ALICE, APPLICATION, BOT, GENERAL, GUILD, message, user
from tests.support.multipart import parse_form


def body(request: SentRequest) -> dict[str, object]:
    assert request.body is not None
    return msgspec.json.decode(request.body, type=dict[str, object])


async def slash_context() -> tuple[PrefixBot, FakeTransport, Context]:
    bot, transport = await bot_started()
    interaction = await bot.process_interaction(payload(slash("ping")))
    return bot, transport, Context(bot, interaction, prefix="/")


async def test_a_message_context_knows_where_and_who() -> None:
    bot, _ = await bot_started()
    ctx = context_in(bot, "!ping")
    assert isinstance(ctx.message, Message)
    assert ctx.interaction is None
    assert isinstance(ctx.author, Member)
    assert ctx.author.id == ALICE
    assert ctx.guild is not None
    assert ctx.guild.id == GUILD
    assert ctx.channel.id == GENERAL
    me = ctx.me
    assert me is not None
    assert me.id == BOT
    assert ctx.state is bot.state
    assert not ctx.valid
    assert ctx.voice_client is None  # not in a voice channel
    assert ctx.voice_protocol is None
    dm = context_in(bot, in_guild=False)
    assert dm.guild is None
    assert dm.me is bot.user
    assert dm.voice_client is None
    assert dm.voice_protocol is None


async def test_send_and_reply_post_to_the_channel() -> None:
    bot, transport = await bot_started()
    ctx = context_in(bot, "!ping")
    transport.queue(200, message(1, author=user(BOT, "shoalbot")))
    transport.queue(200, message(2, author=user(BOT, "shoalbot")))
    sent = await ctx.send("hello", ephemeral=True)
    assert isinstance(sent, Message)
    await ctx.reply("there", mention_author=False)
    first, second = (body(request) for request in transport.requests[-2:])
    assert first == {"content": "hello"}
    assert second["content"] == "there"
    assert isinstance(second["message_reference"], dict)
    assert second["allowed_mentions"] == {"replied_user": False}


async def test_a_slash_context_answers_then_follows_up() -> None:
    _, transport, ctx = await slash_context()
    assert ctx.message is None
    assert ctx.interaction is not None
    assert ctx.author.id == ALICE
    transport.queue(204)
    transport.queue(200, message(10, author=user(BOT, "shoalbot")))
    first = await ctx.send("answer", ephemeral=True)
    assert first.id == 10
    callback, original = transport.requests[-2:]
    assert callback.url.endswith("/callback")
    assert body(callback) == {"type": 4, "data": {"content": "answer", "flags": 64}}
    assert original.url.endswith("/messages/@original")
    transport.queue(200, message(11, author=user(BOT, "shoalbot")))
    transport.queue(204)
    followup = await ctx.reply("more", delete_after=0)
    assert followup.id == 11
    assert transport.requests[-1].url.endswith(f"/webhooks/{APPLICATION}/interaction-token")
    await settle()
    assert transport.requests[-1].method == "DELETE"


async def test_defer_and_typing() -> None:
    bot, transport = await bot_started()
    ctx = context_in(bot)
    count = len(transport.requests)
    await ctx.defer()
    assert len(transport.requests) == count  # a prefix command has no deadline to defer
    transport.queue(204)
    async with ctx.typing():
        await settle()
    assert transport.requests[-1].url.endswith(f"/channels/{GENERAL}/typing")
    _, slash_transport, slashed = await slash_context()
    slash_transport.queue(204)
    async with slashed.typing(ephemeral=True):
        pass
    assert body(slash_transport.requests[-1]) == {"type": 5, "data": {"flags": 64}}
    await slashed.defer()
    assert len([request for request in slash_transport.requests if request.url.endswith("/callback")]) == 1


async def test_the_clean_prefix_shows_mentions_as_names() -> None:
    bot, _ = await bot_started()
    ctx = context_in(bot)
    assert ctx.clean_prefix == ""
    ctx.prefix = f"<@!{BOT}> "
    assert ctx.clean_prefix == "@shoalbot "
    ctx.prefix = "!"
    assert ctx.clean_prefix == "!"


async def test_invoke_runs_another_commands_callback() -> None:
    bot, _ = await bot_started()
    seen: list[int] = []

    @command()
    async def add(ctx: Context, first: int, second: int) -> None:
        del ctx
        seen.append(first + second)

    ctx = context_in(bot)
    await ctx.invoke(add, 2, second=3)
    assert seen == [5]
    ctx.command = add
    assert repr(ctx) == f"<Context command='add' author={ALICE}>"


async def test_an_interaction_without_a_channel_has_no_context() -> None:
    bot, _ = await bot_started()
    data = common() | {"type": 2, "data": {"id": "20", "name": "ping", "type": 1}}
    del data["channel_id"]
    interaction = await bot.process_interaction(payload(data))
    with pytest.raises(ValueError, match="without a channel"):
        Context(bot, interaction)


def form_json(request: SentRequest) -> dict[str, object]:
    assert request.body is not None
    parts = parse_form(request.body, request.headers["Content-Type"])
    assert [part.content_type for part in parts[1:]] == ["audio/ogg"]
    return msgspec.json.decode(parts[0].data, type=dict[str, object])


async def test_a_voice_message_goes_out_from_a_prefix_and_a_slash_command() -> None:
    voice = VoiceMessage(b"OggS", 1.5, b"\x80")
    bot, transport = await bot_started()
    ctx = context_in(bot, "!ping")
    transport.queue(200, message(1, author=user(BOT, "shoalbot")))
    await ctx.reply(voice_message=voice, silent=True)
    sent = form_json(transport.requests[-1])
    assert sent["flags"] == int(MessageFlags(is_voice_message=True, suppress_notifications=True))
    assert sent["attachments"] == [
        {"id": 0, "filename": "voice-message.ogg", "duration_secs": 1.5, "waveform": "gA=="}
    ]
    assert isinstance(sent["message_reference"], dict)
    _, transport, slash_ctx = await slash_context()
    transport.queue(204)
    transport.queue(200, message(10, author=user(BOT, "shoalbot")))
    await slash_ctx.send(voice_message=voice)
    answered = form_json(transport.requests[-2])
    assert answered["data"] == {
        "flags": int(MessageFlags(is_voice_message=True)),
        "attachments": [{"id": 0, "filename": "voice-message.ogg", "duration_secs": 1.5, "waveform": "gA=="}],
    }
