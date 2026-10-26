from datetime import UTC, datetime, timedelta

import pytest

from shoal.models.base import Object
from shoal.models.member import Member
from shoal.payloads import GuildMember, StatusType
from tests.support.models import ALICE, BOB, BOT, GUILD, MODS, OWNER, RED, VOICE, World, decoded, member


async def alice(world: World | None = None) -> tuple[World, Member]:
    world = world or await World.started()
    found = world.guild().get_member(ALICE)
    assert found is not None
    return world, found


async def test_members_proxy_their_user_and_add_the_guilds_view() -> None:
    _, ally = await alice()
    assert (ally.name, ally.global_name, ally.nick, ally.display_name) == ("alice", "Alice", "Ally", "Ally")
    assert ally.user.display_name == "Alice"
    assert ally.guild_id == GUILD
    assert ally.guild is not None
    assert ally.mention == f"<@{ALICE}>"
    assert ally.joined_at == datetime(2024, 1, 1, tzinfo=UTC)
    assert ally.premium_since is None
    assert not ally.pending
    assert ally.raw_roles == [RED]
    assert ally.has_role(RED)
    assert ally.has_role("red")
    assert not ally.has_role(MODS)
    assert not ally.has_role("mods")


async def test_roles_are_ordered_lowest_first_from_everyone() -> None:
    world, ally = await alice()
    assert [role.name for role in ally.roles] == ["@everyone", "red"]
    assert ally.top_role is not None
    assert ally.top_role.id == RED
    assert ally.colour == ally.color == 0xFF0000
    bob = world.guild().get_member(BOB)
    assert bob is not None
    assert bob.colour == 0


async def test_guild_permissions_come_from_the_cached_roles() -> None:
    world, ally = await alice()
    assert ally.guild_permissions.send_messages
    assert not ally.guild_permissions.kick_members
    bob = world.guild().get_member(BOB)
    owner = world.guild().get_member(OWNER)
    assert bob is not None
    assert owner is not None
    assert bob.guild_permissions.kick_members
    assert owner.guild_permissions.administrator


async def test_timeouts_limit_permissions_until_they_end() -> None:
    world = await World.started()
    later = (world.state.now() + timedelta(hours=1)).isoformat()
    earlier = (world.state.now() - timedelta(hours=1)).isoformat()
    await world.dispatch(
        "GUILD_MEMBER_ADD", member(5, "timed", communication_disabled_until=later) | {"guild_id": str(GUILD)}
    )
    await world.dispatch(
        "GUILD_MEMBER_ADD", member(6, "free", communication_disabled_until=earlier) | {"guild_id": str(GUILD)}
    )
    timed, free = world.guild().get_member(5), world.guild().get_member(6)
    assert timed is not None
    assert free is not None
    assert timed.is_timed_out()
    assert not timed.guild_permissions.send_messages
    assert timed.guild_permissions.view_channel
    assert not free.is_timed_out()
    assert free.timed_out_until is None


async def test_voice_and_presence_come_from_the_cache() -> None:
    world, ally = await alice()
    assert ally.status is StatusType.IDLE
    assert ally.activities == []
    assert ally.voice is None
    bob = world.guild().get_member(BOB)
    assert bob is not None
    assert bob.voice is not None
    assert bob.voice.channel_id == VOICE
    assert bob.status is StatusType.OFFLINE


async def test_avatars_prefer_the_guild_one() -> None:
    world = World()
    data = decoded(member(ALICE, "alice", avatar="guildhash", banner="b"), GuildMember)
    ally = Member(world.state, data, GUILD)
    assert ally.guild_avatar is not None
    assert ally.display_avatar == ally.guild_avatar
    assert ally.guild_banner is not None
    assert ally.display_avatar.url.endswith(f"/guilds/{GUILD}/users/{ALICE}/avatars/guildhash.png")


async def test_a_member_needs_to_know_its_user() -> None:
    world = World()
    data = decoded({k: v for k, v in member(ALICE, "a").items() if k != "user"}, GuildMember)
    with pytest.raises(ValueError, match="needs a user"):
        Member(world.state, data, GUILD)


async def test_cached_members_without_a_user_object_use_the_cached_user() -> None:
    world = await World.started()
    assert Member.from_cache(world.state, GUILD, 999) is None
    assert Member.from_cache(world.state, 999, ALICE) is None


async def test_edit_sends_only_what_changes() -> None:
    world, ally = await alice()
    world.transport.queue(200, member(ALICE, "alice", nick=None))
    moment = datetime(2030, 1, 1, tzinfo=UTC)
    edited = await ally.edit(
        nick=None,
        roles=[Object(MODS)],
        mute=True,
        deafen=False,
        voice_channel=None,
        timed_out_until=moment,
        reason="r",
    )
    assert world.last_request() == (
        "PATCH",
        f"/guilds/{GUILD}/members/{ALICE}",
        {
            "nick": None,
            "roles": [str(MODS)],
            "mute": True,
            "deaf": False,
            "channel_id": None,
            "communication_disabled_until": "2030-01-01T00:00:00Z",
        },
    )
    assert world.transport.requests[-1].headers["X-Audit-Log-Reason"] == "r"
    assert edited.nick is None


async def test_roles_are_added_one_by_one_unless_not_atomic() -> None:
    world, ally = await alice()
    world.transport.queue(204)
    world.transport.queue(204)
    await ally.add_roles(Object(MODS), Object(99))
    assert world.requests()[-2:] == [
        ("PUT", f"/guilds/{GUILD}/members/{ALICE}/roles/{MODS}", None),
        ("PUT", f"/guilds/{GUILD}/members/{ALICE}/roles/99", None),
    ]
    world.transport.queue(200, member(ALICE, "alice"))
    await ally.add_roles(Object(MODS), Object(RED), atomic=False)
    assert world.last_request()[2] == {"roles": [str(RED), str(MODS)]}
    world.transport.queue(204)
    await ally.remove_roles(Object(RED))
    assert world.last_request()[:2] == ("DELETE", f"/guilds/{GUILD}/members/{ALICE}/roles/{RED}")
    world.transport.queue(200, member(ALICE, "alice"))
    await ally.remove_roles(Object(RED), atomic=False)
    assert world.last_request()[2] == {"roles": []}


async def test_timeout_takes_a_duration_or_a_moment() -> None:
    world, ally = await alice()
    world.transport.queue(200, member(ALICE, "alice"))
    await ally.timeout(timedelta(minutes=10))
    body = world.last_body()
    sent = datetime.fromisoformat(str(body["communication_disabled_until"]))
    assert sent - datetime.fromtimestamp(world.clock.wall(), UTC) == timedelta(minutes=10)
    world.transport.queue(200, member(ALICE, "alice"))
    await ally.timeout(None)
    assert world.last_request()[2] == {"communication_disabled_until": None}


async def test_moving_kicking_and_banning() -> None:
    world, ally = await alice()
    world.transport.queue(200, member(ALICE, "alice"))
    await ally.move_to(Object(VOICE))
    assert world.last_request()[2] == {"channel_id": str(VOICE)}
    world.transport.queue(204)
    await ally.kick(reason="bye")
    assert world.last_request()[:2] == ("DELETE", f"/guilds/{GUILD}/members/{ALICE}")
    world.transport.queue(204)
    await ally.ban()
    assert world.last_request() == ("PUT", f"/guilds/{GUILD}/bans/{ALICE}", {"delete_message_seconds": 86400})
    world.transport.queue(204)
    await ally.ban(delete_message_seconds=0)
    assert world.last_request()[2] == {"delete_message_seconds": 0}
    world.transport.queue(204)
    await ally.unban()
    assert world.last_request()[:2] == ("DELETE", f"/guilds/{GUILD}/bans/{ALICE}")


async def test_members_are_equal_per_guild() -> None:
    world, ally = await alice()
    again = world.guild().get_member(ALICE)
    other_guild = Member(world.state, ally.payload, GUILD + 1)
    assert again == ally
    assert hash(again) == hash(ally)
    assert other_guild != ally
    assert repr(ally) == f"<Member id={ALICE} name='alice' guild_id={GUILD}>"
    bot = world.guild().me
    assert bot is not None
    assert bot.id == BOT
