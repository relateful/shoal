from datetime import UTC, datetime

from shoal.core.codec import decode_json, encode_json
from shoal.models.base import Object
from shoal.models.channel import TextChannel
from shoal.models.thread import Thread
from shoal.payloads import Channel, ChannelType, Permissions
from tests.support.models import ALICE, BOB, GENERAL, GUILD, THREAD, World, channel


async def thread(world: World) -> Thread:
    found = world.guild().get_thread(THREAD)
    assert found is not None
    return found


async def test_threads_read_their_payload() -> None:
    world = await World.started()
    found = await thread(world)
    assert (found.name, str(found), found.type) == ("a thread", "a thread", ChannelType.PUBLIC_THREAD)
    assert found.guild_id == GUILD
    assert found.guild is not None
    assert found.parent_id == GENERAL
    assert isinstance(found.parent, TextChannel)
    assert found.owner_id == ALICE
    assert found.owner is not None
    assert not found.archived
    assert not found.locked
    assert found.invitable
    assert found.archive_timestamp == datetime(2024, 1, 1, tzinfo=UTC)
    assert found.auto_archive_duration == 60
    assert (found.slowmode_delay, found.message_count, found.member_count) == (0, 3, 2)
    assert found.applied_tags == []
    assert found.me is None
    assert not found.is_private()
    assert not found.is_news()
    assert found.mention == f"<#{THREAD}>"
    assert found.jump_url == f"https://discord.com/channels/{GUILD}/{THREAD}"
    assert repr(found) == f"<Thread id={THREAD} name='a thread' parent_id={GENERAL}>"


async def test_a_bare_thread_payload_has_safe_defaults() -> None:
    world = await World.started()
    bare = Thread(world.state, decode_json(encode_json({"id": "1", "type": 12}), Channel))
    assert bare.archive_timestamp is None
    assert bare.auto_archive_duration == 1440
    assert bare.parent is None
    assert bare.owner is None
    bob = world.guild().get_member(BOB)
    assert bob is not None
    assert bare.permissions_for(bob) == Permissions.none()


async def test_permissions_come_from_the_parent_with_thread_sending() -> None:
    world = await World.started()
    found = await thread(world)
    bob = world.guild().get_member(BOB)
    assert bob is not None
    # Bob may send in the parent, but sending in a thread needs Send Messages in Threads.
    assert not found.permissions_for(bob).send_messages
    assert found.permissions_for(bob).view_channel


async def test_membership_and_edits() -> None:
    world = await World.started()
    found = await thread(world)
    for _ in range(4):
        world.transport.queue(204)
    await found.join()
    await found.leave()
    await found.add_user(Object(BOB))
    await found.remove_user(Object(BOB))
    assert [request[:2] for request in world.requests()] == [
        ("PUT", f"/channels/{THREAD}/thread-members/@me"),
        ("DELETE", f"/channels/{THREAD}/thread-members/@me"),
        ("PUT", f"/channels/{THREAD}/thread-members/{BOB}"),
        ("DELETE", f"/channels/{THREAD}/thread-members/{BOB}"),
    ]
    world.transport.queue(200, channel(THREAD, 11, "renamed", parent=GENERAL))
    edited = await found.edit(name="renamed", archived=True, applied_tags=[Object(3)])
    assert world.last_request()[2] == {"name": "renamed", "archived": True, "applied_tags": ["3"]}
    assert edited.name == "renamed"
    world.transport.queue(200, channel(THREAD, 11, "renamed", parent=GENERAL))
    await found.delete()
    assert world.last_request()[:2] == ("DELETE", f"/channels/{THREAD}")
