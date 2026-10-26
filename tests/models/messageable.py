import asyncio
from datetime import UTC, datetime

import pytest

from shoal.core.snowflake import Snowflake
from shoal.models import messageable
from shoal.models.base import Object
from shoal.models.channel import TextChannel
from shoal.models.embed import Embed
from shoal.payloads import AllowedMentions
from shoal.rest.files import File
from tests.support.models import GENERAL, GUILD, LINK_VIEW, ROW_VIEW, World, message


async def general(world: World) -> TextChannel:
    found = world.guild().get_channel(GENERAL)
    assert isinstance(found, TextChannel)
    return found


async def test_send_takes_discord_py_keywords() -> None:
    world = await World.started()
    channel = await general(world)
    world.transport.queue(200, message(9))
    sent = await channel.send(
        "hi",
        embed=Embed(title="t"),
        stickers=[Object(3), 4],
        allowed_mentions=AllowedMentions(users=[Snowflake(1)]),
        mention_author=True,
        reference=channel.get_partial_message(5),
        silent=True,
    )
    assert sent.guild_id == GUILD
    _, path, body = world.last_request()
    assert path == f"/channels/{GENERAL}/messages"
    assert body == {
        "content": "hi",
        "embeds": [{"title": "t"}],
        "allowed_mentions": {"users": ["1"], "replied_user": True},
        "message_reference": {
            "message_id": "5",
            "channel_id": str(GENERAL),
            "guild_id": str(GUILD),
            "fail_if_not_exists": True,
        },
        "sticker_ids": ["3", "4"],
        "flags": 1 << 12,
    }


async def test_send_with_files_and_a_view() -> None:
    world = await World.started()
    channel = await general(world)
    world.transport.queue(200, message(9))
    await channel.send(file=File("a.txt", b"a"), view=ROW_VIEW)
    assert world.transport.requests[-1].headers["Content-Type"].startswith("multipart/form-data")
    assert world.views.stored == [(ROW_VIEW, 9)]
    world.transport.queue(200, message(10))
    await channel.send("link", view=LINK_VIEW)
    assert len(world.views.stored) == 1  # a view with nothing to dispatch is not kept


async def test_delete_after_deletes_the_sent_message() -> None:
    world = await World.started()
    channel = await general(world)
    world.transport.queue(200, message(9))
    world.transport.queue(204)
    await channel.send("bye", delete_after=0)
    for _ in range(5):
        await asyncio.sleep(0)
    assert world.last_request()[:2] == ("DELETE", f"/channels/{GENERAL}/messages/9")


async def test_fetch_message() -> None:
    world = await World.started()
    channel = await general(world)
    world.transport.queue(200, message(9))
    fetched = await channel.fetch_message(9)
    assert fetched.guild_id == GUILD
    assert world.last_request()[:2] == ("GET", f"/channels/{GENERAL}/messages/9")


async def test_history_pages_backwards_until_the_limit() -> None:
    world = await World.started()
    channel = await general(world)
    world.transport.queue(200, [message(index) for index in range(300, 200, -1)])
    world.transport.queue(200, [message(index) for index in range(200, 150, -1)])
    found = [item.id async for item in channel.history(limit=150)]
    assert found == list(range(300, 150, -1))
    assert [request[1] for request in world.requests()] == [
        f"/channels/{GENERAL}/messages?limit=100",
        f"/channels/{GENERAL}/messages?before=201&limit=50",
    ]


async def test_history_stops_at_the_start_of_the_channel() -> None:
    world = await World.started()
    channel = await general(world)
    world.transport.queue(200, [message(3), message(2)])
    assert [item.id async for item in channel.history(limit=None)] == [3, 2]


async def test_history_after_a_point_goes_forwards() -> None:
    world = await World.started()
    channel = await general(world)
    world.transport.queue(200, [message(index) for index in range(110, 10, -1)])
    world.transport.queue(200, [message(111)])
    found = [item.id async for item in channel.history(limit=None, after=Object(10))]
    assert found == list(range(11, 112))
    assert world.requests()[-1][1] == f"/channels/{GENERAL}/messages?after=110&limit=100"


async def test_history_between_two_points() -> None:
    world = await World.started()
    channel = await general(world)
    world.transport.queue(200, [message(25), message(21), message(12)])
    found = [item.id async for item in channel.history(after=10, before=22)]
    assert found == [21, 12]
    world.transport.queue(200, [message(25), message(21), message(12)])
    found = [item.id async for item in channel.history(after=10, before=22, oldest_first=True)]
    assert found == [12, 21]


async def test_history_around_a_point() -> None:
    world = await World.started()
    channel = await general(world)
    world.transport.queue(200, [message(6), message(5), message(4)])
    moment = datetime(2024, 1, 1, tzinfo=UTC)
    found = [item.id async for item in channel.history(around=moment, limit=3)]
    assert found == [6, 5, 4]
    assert (
        world.last_request()[1]
        == f"/channels/{GENERAL}/messages?around={Snowflake.from_datetime(moment)}&limit=3"
    )
    with pytest.raises(ValueError, match="around"):
        _ = [item async for item in channel.history(around=5, before=6)]
    with pytest.raises(ValueError, match="at most"):
        _ = [item async for item in channel.history(around=5, limit=None)]


async def test_pins_page_until_there_are_no_more() -> None:
    world = await World.started()
    channel = await general(world)
    first = {"items": [{"pinned_at": "2024-02-01T00:00:00+00:00", "message": message(9)}], "has_more": True}
    second = {"items": [{"pinned_at": "2024-01-01T00:00:00+00:00", "message": message(8)}], "has_more": False}
    world.transport.queue(200, first)
    world.transport.queue(200, second)
    assert [pinned.id for pinned in await channel.pins()] == [9, 8]
    assert (
        world.requests()[-1][1]
        == f"/channels/{GENERAL}/messages/pins?before=2024-02-01T00%3A00%3A00%2B00%3A00"
    )


async def test_typing_keeps_the_indicator_on_until_the_block_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    world = await World.started()
    channel = await general(world)
    monkeypatch.setattr(messageable, "TYPING_REFRESH", 0.01)
    for _ in range(20):
        world.transport.queue(204)
    async with channel.typing():
        await asyncio.sleep(0.05)
    count = len(world.requests())
    assert count >= 2
    await asyncio.sleep(0.05)
    assert len(world.requests()) == count
    assert world.requests()[0][:2] == ("POST", f"/channels/{GENERAL}/typing")
