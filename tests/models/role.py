from shoal.core.codec import decode_json, encode_json
from shoal.models.role import Role
from shoal.payloads import Permissions
from shoal.payloads import Role as RolePayload
from tests.support.models import ALICE, BOB, EVERYONE, GUILD, MODS, RED, World, role

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


async def roles() -> tuple[World, Role, Role, Role]:
    world = await World.started()
    guild = world.guild()
    everyone, mods, red = guild.get_role(EVERYONE), guild.get_role(MODS), guild.get_role(RED)
    assert everyone is not None
    assert mods is not None
    assert red is not None
    return world, everyone, mods, red


async def test_roles_read_their_payload() -> None:
    _, everyone, mods, red = await roles()
    assert everyone.is_default()
    assert everyone.mention == "@everyone"
    assert mods.mention == f"<@&{MODS}>"
    assert str(mods) == "mods"
    assert mods.permissions == Permissions(kick_members=True, ban_members=True)
    assert red.colour == red.color == 0xFF0000
    assert red.secondary_colour is None
    assert red.hoist
    assert not red.managed
    assert not red.mentionable
    assert red.icon is None
    assert red.unicode_emoji is None
    assert red.tags is None
    assert not red.is_bot_managed()
    assert not red.is_premium_subscriber()
    assert not red.is_integration()
    assert red.guild is not None
    assert red.guild_id == GUILD


async def test_roles_order_by_position_then_id() -> None:
    _, everyone, mods, red = await roles()
    assert everyone < red < mods
    assert mods >= red
    assert everyone <= red
    assert mods > everyone
    assert sorted([mods, everyone, red]) == [everyone, red, mods]


async def test_members_of_a_role_come_from_the_cache() -> None:
    _, everyone, mods, red = await roles()
    assert [member.id for member in mods.members] == [BOB]
    assert [member.id for member in red.members] == [ALICE]
    assert len(everyone.members) == 4


async def test_tags_say_what_manages_a_role() -> None:
    world = World()
    data = role(9, "boost", position=1) | {"tags": {"premium_subscriber": None}}
    booster = Role(world.state, decode_json(encode_json(data), RolePayload), GUILD)
    assert booster.is_premium_subscriber()


async def test_cached_roles_know_their_guild() -> None:
    world = await World.started()
    found = Role.from_cache(world.state, MODS)
    assert found is not None
    assert found.guild_id == GUILD
    assert Role.from_cache(world.state, 999) is None


async def test_edit_moves_the_role_separately() -> None:
    world, _, mods, _ = await roles()
    world.transport.queue(200, [role(MODS, "mods", position=1)])
    world.transport.queue(200, role(MODS, "moderators", position=1))
    edited = await mods.edit(
        name="moderators", colour=0x00FF00, icon=PNG, unicode_emoji=None, position=1, reason="r"
    )
    first, second = world.requests()[-2:]
    assert first == ("PATCH", f"/guilds/{GUILD}/roles", [{"id": str(MODS), "position": 1}])
    assert second[:2] == ("PATCH", f"/guilds/{GUILD}/roles/{MODS}")
    assert isinstance(second[2], dict)
    assert second[2]["name"] == "moderators"
    assert second[2]["color"] == 0x00FF00
    assert second[2]["unicode_emoji"] is None
    assert edited.name == "moderators"
    world.transport.queue(204)
    await mods.delete(reason="r")
    assert world.last_request()[:2] == ("DELETE", f"/guilds/{GUILD}/roles/{MODS}")
