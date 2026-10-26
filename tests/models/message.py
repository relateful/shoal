import asyncio
from datetime import UTC, datetime

from shoal.core.snowflake import Snowflake
from shoal.models.base import Object
from shoal.models.channel import PartialMessageable, TextChannel
from shoal.models.embed import Embed
from shoal.models.member import Member
from shoal.models.message import Message, PartialMessage
from shoal.models.sending import edit
from shoal.models.user import User
from shoal.payloads import AttachmentRequest, MessageCreate, MessageFlags, MessageType
from shoal.payloads import Message as MessagePayload
from shoal.rest.files import File
from tests.support.models import (
    ALICE,
    BOB,
    BOT,
    GENERAL,
    GUILD,
    MODS,
    ROW_VIEW,
    THREAD,
    World,
    decoded,
    message,
    user,
)

REACTION: dict[str, object] = {
    "count": 1,
    "count_details": {"burst": 0, "normal": 1},
    "me": False,
    "me_burst": False,
    "emoji": {"id": None, "name": "x"},
    "burst_colors": [],
}


def from_gateway(data: object) -> MessageCreate:
    return decoded(data, MessageCreate)


def from_rest(data: object) -> MessagePayload:
    return decoded(data, MessagePayload)


async def test_a_gateway_message_knows_its_guild_and_author_as_a_member() -> None:
    world = await World.started()
    found = Message(world.state, from_gateway(message(5) | {"guild_id": str(GUILD)}))
    assert found.guild_id == GUILD
    assert found.guild is not None
    assert isinstance(found.channel, TextChannel)
    assert isinstance(found.author, Member)
    assert found.author.display_name == "Ally"
    assert found.content == "hello"
    assert found.created_at == datetime(2024, 1, 1, tzinfo=UTC)
    assert found.edited_at is None
    assert found.jump_url == f"https://discord.com/channels/{GUILD}/{GENERAL}/5"
    assert repr(found) == f"<Message id=5 channel_id={GENERAL} author='alice'>"


async def test_the_member_sent_with_a_message_is_used_first() -> None:
    world = await World.started()
    with_member = message(5) | {
        "guild_id": str(GUILD),
        "member": {
            "roles": [str(MODS)],
            "joined_at": None,
            "deaf": False,
            "mute": False,
            "flags": 0,
            "nick": "Sent",
        },
    }
    found = Message(world.state, from_gateway(with_member))
    assert isinstance(found.author, Member)
    assert found.author.display_name == "Sent"


async def test_authors_outside_a_guild_or_unknown_are_users() -> None:
    world = await World.started()
    in_dm = Message(world.state, from_rest(message(5, channel_id=60)))
    assert in_dm.guild_id is None
    assert in_dm.guild is None
    assert isinstance(in_dm.author, User)
    assert isinstance(in_dm.channel, PartialMessageable)
    assert in_dm.jump_url == "https://discord.com/channels/@me/60/5"
    stranger = Message(world.state, from_rest(message(6, author=user(77, "stranger"))), guild_id=GUILD)
    assert isinstance(stranger.author, User)
    webhook = Message(world.state, from_gateway(message(7) | {"guild_id": str(GUILD), "webhook_id": "9"}))
    assert isinstance(webhook.author, User)
    assert webhook.webhook_id == 9


async def test_mentions_resolve_through_the_cache() -> None:
    world = await World.started()
    data = message(5, mentions=[user(BOB, "bob"), user(88, "ghost")], mention_roles=[str(MODS), "999"])
    found = Message(world.state, from_rest(data), guild_id=GUILD)
    assert [type(mentioned) for mentioned in found.mentions] == [Member, User]
    assert found.raw_mentions == [BOB, 88]
    assert found.raw_role_mentions == [MODS, 999]
    assert [role.id for role in found.role_mentions] == [MODS]
    assert not found.mention_everyone


async def test_message_contents() -> None:
    world = await World.started()
    data = message(
        5,
        embeds=[{"title": "t"}],
        reactions=[REACTION],
        flags=int(MessageFlags(suppress_embeds=True)),
        referenced_message=message(4),
        message_reference={"message_id": "4"},
        application_id="7",
        type=19,
    )
    found = Message(world.state, from_rest(data), guild_id=GUILD)
    assert [embed.title for embed in found.embeds] == ["t"]
    assert isinstance(found.embeds[0], Embed)
    assert len(found.reactions) == 1
    assert found.flags.suppress_embeds
    assert found.referenced_message is not None
    assert found.referenced_message.id == 4
    assert found.reference is not None
    assert found.application_id == 7
    assert found.type is MessageType.REPLY
    assert not found.is_system()
    assert found.attachments == []
    assert found.stickers == []
    assert found.poll is None
    assert not found.tts
    assert not found.pinned
    plain = Message(world.state, from_rest(message(6)))
    assert plain.flags == MessageFlags.none()
    assert plain.reactions == []
    assert plain.referenced_message is None
    join = Message(world.state, from_rest(message(7, type=7)))
    assert join.is_system()


async def test_reply_references_the_message() -> None:
    world = await World.started()
    found = Message(world.state, from_gateway(message(5) | {"guild_id": str(GUILD)}))
    world.transport.queue(200, message(6))
    await found.reply("pong", mention_author=False, view=ROW_VIEW)
    _, path, _ = world.last_request()
    assert path == f"/channels/{GENERAL}/messages"
    body = world.last_body()
    assert body["content"] == "pong"
    assert body["message_reference"] == {
        "message_id": "5",
        "channel_id": str(GENERAL),
        "guild_id": str(GUILD),
        "fail_if_not_exists": True,
    }
    assert body["allowed_mentions"] == {"replied_user": False}
    assert world.views.stored == [(ROW_VIEW, 6)]


async def test_edit_keeps_the_flags_it_must_repeat() -> None:
    world = await World.started()
    flags = MessageFlags(suppress_notifications=True)
    found = Message(world.state, from_rest(message(5, flags=int(flags))), guild_id=GUILD)
    world.transport.queue(200, message(5, content="edited"))
    edited = await found.edit(content="edited", suppress=True, view=ROW_VIEW)
    assert world.last_request()[:2] == ("PATCH", f"/channels/{GENERAL}/messages/5")
    body = world.last_body()
    assert body["flags"] == int(flags.with_flags(suppress_embeds=True))
    assert edited.content == "edited"
    assert world.views.stored == [(ROW_VIEW, 5)]


async def test_edit_attachments_are_the_ones_to_keep() -> None:
    world = await World.started()
    kept: dict[str, object] = {
        "id": "70",
        "filename": "a.png",
        "size": 1,
        "url": "https://cdn.example/a.png",
        "proxy_url": "https://media.example/a.png",
    }
    found = Message(
        world.state, from_rest(message(5, attachments=[kept, kept | {"id": "71"}])), guild_id=GUILD
    )
    world.transport.queue(200, message(5))
    await found.edit(attachments=found.attachments[:1])
    assert world.last_body()["attachments"] == [{"id": "70"}]
    world.transport.queue(200, message(5))
    await found.edit(attachments=[])
    assert world.last_body()["attachments"] == []
    world.transport.queue(200, message(5))
    await found.edit(content="left alone")
    assert "attachments" not in world.last_body()
    changes = edit(attachments=[found.attachments[0], File("b.txt", b"b")])
    assert changes.attachments == [AttachmentRequest(id=found.attachments[0].id)]
    assert [file.filename for file in changes.files] == ["b.txt"]


async def test_delete_now_or_later() -> None:
    world = await World.started()
    found = Message(world.state, from_rest(message(5)), guild_id=GUILD)
    world.transport.queue(204)
    await found.delete(reason="r")
    assert world.last_request()[:2] == ("DELETE", f"/channels/{GENERAL}/messages/5")
    world.transport.queue(404, {"code": 10008, "message": "Unknown Message"})
    await found.delete(delay=0)
    for _ in range(5):
        await asyncio.sleep(0)
    assert len(world.requests()) == 2  # the failed delayed delete was swallowed


async def test_pins_reactions_and_publishing() -> None:
    world = await World.started()
    found = Message(world.state, from_rest(message(5)), guild_id=GUILD)
    for _ in range(7):
        world.transport.queue(204)
    await found.pin()
    await found.unpin()
    await found.add_reaction("\N{FIRE}")
    await found.remove_reaction("\N{FIRE}", Object(BOT))
    await found.remove_reaction("\N{FIRE}", Object(ALICE))
    await found.clear_reaction("\N{FIRE}")
    await found.clear_reactions()
    base = f"/channels/{GENERAL}/messages/5"
    fire = "%F0%9F%94%A5"
    assert [request[:2] for request in world.requests()] == [
        ("PUT", f"/channels/{GENERAL}/messages/pins/5"),
        ("DELETE", f"/channels/{GENERAL}/messages/pins/5"),
        ("PUT", f"{base}/reactions/{fire}/@me"),
        ("DELETE", f"{base}/reactions/{fire}/@me"),
        ("DELETE", f"{base}/reactions/{fire}/{ALICE}"),
        ("DELETE", f"{base}/reactions/{fire}"),
        ("DELETE", f"{base}/reactions"),
    ]
    world.transport.queue(200, message(5))
    assert (await found.publish()).id == 5


async def test_a_thread_can_start_from_a_message() -> None:
    world = await World.started()
    found = Message(world.state, from_rest(message(5)), guild_id=GUILD)
    world.transport.queue(200, {"id": "90", "type": 11, "guild_id": str(GUILD), "parent_id": str(GENERAL)})
    created = await found.create_thread(name="t", slowmode_delay=5)
    assert world.last_request() == (
        "POST",
        f"{f'/channels/{GENERAL}'}/messages/5/threads",
        {"name": "t", "rate_limit_per_user": 5},
    )
    assert created.id == 90


async def test_partial_messages_fetch_the_rest() -> None:
    world = await World.started()
    partial = PartialMessage(world.state, THREAD, 5, guild_id=GUILD)
    assert partial.channel.id == THREAD
    assert partial.to_reference(fail_if_not_exists=False).fail_if_not_exists is False
    world.transport.queue(200, message(5, channel_id=THREAD))
    fetched = await partial.fetch()
    assert fetched.guild_id == GUILD
    assert world.last_request()[:2] == ("GET", f"/channels/{THREAD}/messages/5")
    assert repr(partial) == "<PartialMessage id=5>"
    assert partial.id == Snowflake(5)
