from datetime import timedelta

import pytest

from shoal.core.snowflake import Snowflake
from shoal.models.base import Object
from shoal.models.channel import (
    CategoryChannel,
    DMChannel,
    ForumChannel,
    GroupChannel,
    GuildChannel,
    MediaChannel,
    PartialMessageable,
    StageChannel,
    TextChannel,
    VoiceChannel,
    channel_from_payload,
    resolve_channel,
)
from shoal.models.overwrite import PermissionOverwrite
from shoal.models.thread import Thread
from shoal.payloads import Channel, ChannelType, Permissions, VideoQualityMode
from tests.support.json_payloads import INVITE
from tests.support.models import (
    ALICE,
    ANNOUNCEMENTS,
    BOB,
    CATEGORY,
    FORUM,
    GENERAL,
    GUILD,
    MODS,
    OWNER,
    RED,
    ROW_VIEW,
    STAGE,
    THREAD,
    VOICE,
    World,
    channel,
    decoded,
    message,
    user,
)


def payload(data: object) -> Channel:
    return decoded(data, Channel)


async def get[T](world: World, channel_id: int, kind: type[T]) -> T:
    found = world.guild().get_channel_or_thread(channel_id)
    assert isinstance(found, kind)
    return found


@pytest.mark.parametrize(
    ("kind", "model"),
    [
        (0, TextChannel),
        (5, TextChannel),
        (2, VoiceChannel),
        (13, StageChannel),
        (4, CategoryChannel),
        (15, ForumChannel),
        (16, MediaChannel),
        (11, Thread),
        (12, Thread),
        (10, Thread),
        (1, DMChannel),
        (3, GroupChannel),
        (14, GuildChannel),
        (99, GuildChannel),
    ],
)
def test_payloads_become_the_model_of_their_type(kind: int, model: type) -> None:
    built = channel_from_payload(World().state, payload(channel(1, kind, "c")))
    assert type(built) is model


async def test_messages_in_uncached_channels_get_a_partial_messageable() -> None:
    world = await World.started()
    assert isinstance(resolve_channel(world.state, GENERAL, GUILD), TextChannel)
    assert isinstance(resolve_channel(world.state, THREAD, GUILD), Thread)
    partial = resolve_channel(world.state, 999, GUILD)
    assert isinstance(partial, PartialMessageable)
    assert partial.guild_id == GUILD
    assert partial.jump_url == f"https://discord.com/channels/{GUILD}/999"
    # A category cannot hold messages, so it is never a message's channel.
    assert isinstance(resolve_channel(world.state, CATEGORY, GUILD), PartialMessageable)


async def test_guild_channels_share_their_basics() -> None:
    world = await World.started()
    general = await get(world, GENERAL, TextChannel)
    assert (general.name, str(general), general.position) == ("general", "general", 1)
    assert general.type is ChannelType.GUILD_TEXT
    assert general.guild is not None
    assert general.category is not None
    assert general.category.id == CATEGORY
    assert general.mention == f"<#{GENERAL}>"
    assert general.jump_url == f"https://discord.com/channels/{GUILD}/{GENERAL}"
    assert not general.nsfw
    assert not general.is_nsfw()
    assert not general.is_obfuscated
    assert general.topic is None
    assert not general.is_news()
    assert (await get(world, ANNOUNCEMENTS, TextChannel)).is_news()
    assert general.overwrites_for(Object(MODS)) is not None
    assert general.overwrites_for(Object(RED)) is None
    assert [thread.id for thread in general.threads] == [THREAD]
    assert general.slowmode_delay == 0
    assert general.last_message is None
    assert repr(general) == f"<TextChannel id={GENERAL} name='general'>"


async def test_obfuscated_channels_have_an_empty_name() -> None:
    world = World()
    hidden = channel_from_payload(world.state, payload(channel(1, 0, "secret") | {"flags": 1 << 17}))
    assert isinstance(hidden, TextChannel)
    assert hidden.is_obfuscated
    assert hidden.name == ""


async def test_permissions_for_members_and_roles_apply_the_overwrites() -> None:
    world = await World.started()
    general = await get(world, GENERAL, TextChannel)
    guild = world.guild()
    alice, bob, owner = guild.get_member(ALICE), guild.get_member(BOB), guild.get_member(OWNER)
    assert alice is not None
    assert bob is not None
    assert owner is not None
    assert not general.permissions_for(alice).send_messages
    assert general.permissions_for(bob).send_messages
    assert general.permissions_for(owner) == Permissions.all()
    everyone, mods = guild.default_role, guild.get_role(MODS)
    assert everyone is not None
    assert mods is not None
    assert not general.permissions_for(everyone).send_messages
    assert general.permissions_for(mods).send_messages
    assert general.permissions_for(mods).kick_members


async def test_set_permissions_writes_or_removes_an_overwrite() -> None:
    world = await World.started()
    general = await get(world, GENERAL, TextChannel)
    mods = world.guild().get_role(MODS)
    alice = world.guild().get_member(ALICE)
    assert mods is not None
    assert alice is not None
    world.transport.queue(204)
    await general.set_permissions(mods, allow=Permissions(send_messages=True), reason="r")
    assert world.last_request() == (
        "PUT",
        f"/channels/{GENERAL}/permissions/{MODS}",
        {"allow": str(1 << 11), "type": 0},
    )
    world.transport.queue(204)
    await general.set_permissions(alice, deny=Permissions(view_channel=True))
    assert world.last_request()[2] == {"deny": str(1 << 10), "type": 1}
    world.transport.queue(204)
    await general.set_permissions(alice)
    assert world.last_request()[:2] == ("DELETE", f"/channels/{GENERAL}/permissions/{ALICE}")
    world.transport.queue(204)
    await general.set_permissions(mods, overwrite=PermissionOverwrite(send_messages=True, view_channel=False))
    assert world.last_request()[2] == {"allow": str(1 << 11), "deny": str(1 << 10), "type": 0}
    with pytest.raises(TypeError, match="not both"):
        await general.set_permissions(mods, overwrite=PermissionOverwrite(), allow=Permissions.none())


async def test_edit_delete_and_invites() -> None:
    world = await World.started()
    general = await get(world, GENERAL, TextChannel)
    world.transport.queue(200, channel(GENERAL, 0, "renamed"))
    edited = await general.edit(name="renamed", topic=None, slowmode_delay=10, category=None)
    assert isinstance(edited, TextChannel)
    assert edited.name == "renamed"
    assert world.last_request()[2] == {
        "name": "renamed",
        "topic": None,
        "rate_limit_per_user": 10,
        "parent_id": None,
    }
    world.transport.queue(200, INVITE)
    await general.create_invite()
    assert world.last_request()[2] == {"max_age": 0, "max_uses": 0, "temporary": False, "unique": True}
    world.transport.queue(200, [])
    assert await general.invites() == []
    world.transport.queue(200, channel(GENERAL, 0, "renamed"))
    await general.delete(reason="r")
    assert world.last_request()[:2] == ("DELETE", f"/channels/{GENERAL}")


async def test_threads_are_started_from_a_message_or_on_their_own() -> None:
    world = await World.started()
    general = await get(world, GENERAL, TextChannel)
    thread = channel(90, 12, "t", parent=GENERAL)
    world.transport.queue(200, thread)
    created = await general.create_thread(name="t")
    assert world.last_request() == (
        "POST",
        f"/channels/{GENERAL}/threads",
        {"name": "t", "type": 12, "invitable": True},
    )
    assert created.is_private()
    world.transport.queue(200, thread)
    await general.create_thread(name="t", message=Object(5), auto_archive_duration=60)
    assert world.last_request() == (
        "POST",
        f"/channels/{GENERAL}/messages/5/threads",
        {"name": "t", "auto_archive_duration": 60},
    )


async def test_bulk_deletion_and_purge() -> None:
    world = await World.started()
    general = await get(world, GENERAL, TextChannel)
    world.transport.queue(204)
    await general.delete_messages([Object(1)])
    assert world.last_request()[:2] == ("DELETE", f"/channels/{GENERAL}/messages/1")
    world.transport.queue(204)
    await general.delete_messages([Object(1), Object(2)])
    assert world.last_request() == (
        "POST",
        f"/channels/{GENERAL}/messages/bulk-delete",
        {"messages": ["1", "2"]},
    )
    await general.delete_messages([])
    recent = Snowflake.from_datetime(world.state.now() - timedelta(days=1))
    old = Snowflake.from_datetime(world.state.now() - timedelta(days=30))
    world.transport.queue(200, [message(recent + 2), message(recent + 1), message(old)])
    world.transport.queue(204)
    world.transport.queue(204)
    deleted = await general.purge(limit=3, check=lambda found: found.id != recent + 1)
    assert [found.id for found in deleted] == [old, recent + 2]
    assert world.requests()[-2:] == [
        ("DELETE", f"/channels/{GENERAL}/messages/{old}", None),
        ("DELETE", f"/channels/{GENERAL}/messages/{recent + 2}", None),
    ]


async def test_webhooks_of_a_channel() -> None:
    world = await World.started()
    general = await get(world, GENERAL, TextChannel)
    world.transport.queue(200, [])
    assert await general.webhooks() == []
    hook = {
        "id": "5",
        "type": 1,
        "channel_id": str(GENERAL),
        "name": "w",
        "avatar": None,
        "application_id": None,
    }
    world.transport.queue(200, hook)
    assert (await general.create_webhook(name="w")).name == "w"


async def test_voice_channels_know_who_is_in_them() -> None:
    world = await World.started()
    voice = await get(world, VOICE, VoiceChannel)
    assert (voice.bitrate, voice.user_limit, voice.rtc_region) == (96000, 5, None)
    assert voice.video_quality_mode is VideoQualityMode.AUTO
    assert list(voice.voice_states) == [BOB]
    assert [member.id for member in voice.members] == [BOB]


async def test_stages_know_their_live_instance() -> None:
    world = await World.started()
    stage = await get(world, STAGE, StageChannel)
    assert stage.instance is not None
    assert stage.instance.topic == "Town hall"
    assert stage.topic is None
    instance = {
        "id": "51",
        "guild_id": str(GUILD),
        "channel_id": str(STAGE),
        "topic": "Q&A",
        "privacy_level": 2,
        "discoverable_disabled": False,
        "guild_scheduled_event_id": None,
    }
    world.transport.queue(200, instance)
    await stage.create_instance(topic="Q&A")
    assert world.last_request() == ("POST", "/stage-instances", {"channel_id": str(STAGE), "topic": "Q&A"})
    world.transport.queue(200, instance)
    assert (await stage.fetch_instance()).topic == "Q&A"


async def test_categories_list_their_channels_in_order() -> None:
    world = await World.started()
    category = await get(world, CATEGORY, CategoryChannel)
    assert [found.id for found in category.channels] == [GENERAL, ANNOUNCEMENTS]
    assert [found.id for found in category.text_channels] == [GENERAL, ANNOUNCEMENTS]
    assert category.voice_channels == category.stage_channels == category.forums == []


async def test_forum_posts_are_a_thread_and_a_message() -> None:
    world = await World.started()
    forum = await get(world, FORUM, ForumChannel)
    assert forum.available_tags == []
    assert forum.get_tag(1) is None
    assert forum.threads == []
    assert forum.topic is None
    post = channel(92, 11, "question", parent=FORUM) | {"message": message(93, channel_id=92)}
    world.transport.queue(200, post)
    created = await forum.create_thread(
        name="question", content="How?", applied_tags=[Object(7)], view=ROW_VIEW
    )
    method, path, _ = world.last_request()
    assert (method, path) == ("POST", f"/channels/{FORUM}/threads")
    body = world.last_body()
    button = {"type": 2, "style": 1, "custom_id": "ok", "label": "OK"}
    assert body["message"] == {"content": "How?", "components": [{"type": 1, "components": [button]}]}
    assert body["applied_tags"] == ["7"]
    assert created.thread.id == 92
    assert created.message.id == 93
    assert world.views.stored == [(ROW_VIEW, 93)]


async def test_dms_and_group_dms() -> None:
    world = World()
    dm = channel_from_payload(
        world.state, payload({"id": "60", "type": 1, "recipients": [user(ALICE, "alice")]})
    )
    assert isinstance(dm, DMChannel)
    assert dm.recipient is not None
    assert dm.recipient.id == ALICE
    assert dm.type is ChannelType.DM
    assert dm.jump_url == "https://discord.com/channels/@me/60"
    group = channel_from_payload(
        world.state,
        payload(
            {"id": "61", "type": 3, "name": "pals", "owner_id": "1", "recipients": [user(ALICE, "alice")]}
        ),
    )
    assert isinstance(group, GroupChannel)
    assert (group.name, group.owner_id) == ("pals", 1)
    assert [found.id for found in group.recipients] == [ALICE]
    assert repr(group) == "<GroupChannel id=61 name='pals'>"
    world.transport.queue(200, message(9, channel_id=60))
    sent = await dm.send("hi")
    assert world.last_request() == ("POST", "/channels/60/messages", {"content": "hi"})
    assert sent.guild_id is None


async def test_partial_messages_from_a_channel() -> None:
    world = await World.started()
    general = await get(world, GENERAL, TextChannel)
    partial = general.get_partial_message(5)
    assert (partial.id, partial.channel_id, partial.guild_id) == (5, GENERAL, GUILD)
    unknown = PartialMessageable(world.state, 999)
    assert unknown.get_partial_message(6).guild_id is None
