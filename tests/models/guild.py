from datetime import UTC, datetime

import pytest

from shoal.models.base import Object
from shoal.models.channel import CategoryChannel, ForumChannel, StageChannel, TextChannel, VoiceChannel
from shoal.models.guild import Guild
from shoal.models.overwrite import PermissionOverwrite
from shoal.payloads import Guild as GuildPayload
from shoal.payloads import GuildFeature, Permissions, PremiumTier, VerificationLevel
from tests.support.models import (
    ALICE,
    ANNOUNCEMENTS,
    BOB,
    BOT,
    CATEGORY,
    EMOJI,
    EVERYONE,
    FORUM,
    GENERAL,
    GUILD,
    MODS,
    OWNER,
    RED,
    STAGE,
    THREAD,
    VOICE,
    World,
    channel,
    decoded,
    guild_create,
    member,
    role,
    user,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


async def test_guild_attributes_read_the_cached_guild() -> None:
    world = await World.started()
    guild = world.guild()
    assert (guild.id, guild.name, str(guild)) == (GUILD, "Shoal Test", "Shoal Test")
    assert guild.owner_id == OWNER
    assert guild.owner is not None
    assert guild.owner.id == OWNER
    assert guild.member_count == 4
    assert not guild.large
    assert guild.joined_at == datetime(2024, 1, 1, tzinfo=UTC)
    assert guild.features == [GuildFeature.COMMUNITY]
    assert guild.premium_tier is PremiumTier.TIER_1
    assert guild.premium_subscription_count == 0
    assert guild.verification_level is VerificationLevel.LOW
    assert guild.preferred_locale == "en-US"
    assert guild.afk_timeout == 300
    assert guild.description is None
    assert guild.vanity_url_code is None
    assert guild.icon is not None
    assert guild.icon.is_animated()
    assert guild.banner is guild.splash is guild.discovery_splash is None
    assert repr(guild) == f"<Guild id={GUILD} name='Shoal Test'>"


async def test_a_guild_from_rest_has_no_gateway_only_fields() -> None:
    world = World()
    data = {k: v for k, v in guild_create().items() if k not in {"joined_at", "large", "member_count"}}
    guild = Guild(world.state, decoded(data | {"approximate_member_count": 9}, GuildPayload))
    assert guild.member_count == 9
    assert guild.joined_at is None
    assert not guild.large
    assert Guild.from_cache(world.state, GUILD) is None


async def test_members_are_looked_up_by_id_and_name() -> None:
    world = await World.started()
    guild = world.guild()
    assert sorted(member.id for member in guild.members) == [BOT, OWNER, ALICE, BOB]
    assert guild.get_member(999) is None
    assert guild.me is not None
    assert guild.me.id == BOT


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Ally", ALICE),
        ("Alice", ALICE),
        ("alice", ALICE),
        ("alice#0", ALICE),
        ("bob", BOB),
        ("alice#1234", None),
        ("nobody", None),
    ],
)
async def test_members_are_found_by_name(query: str, expected: int | None) -> None:
    world = await World.started()
    found = world.guild().get_member_named(query)
    assert (found.id if found else None) == expected


async def test_a_nickname_wins_over_another_members_username() -> None:
    world = await World.started()
    await world.dispatch("GUILD_MEMBER_ADD", member(8, "Ally") | {"guild_id": str(GUILD)})
    found = world.guild().get_member_named("Ally")
    assert found is not None
    assert found.id == ALICE


async def test_legacy_discriminators_match_exactly() -> None:
    world = await World.started()
    legacy = member(9, "old") | {"user": user(9, "old") | {"discriminator": "1234"}}
    await world.dispatch("GUILD_MEMBER_ADD", legacy | {"guild_id": str(GUILD)})
    found = world.guild().get_member_named("old#1234")
    assert found is not None
    assert found.id == 9
    assert world.guild().get_member_named("old#4321") is None


async def test_roles_channels_and_threads() -> None:
    world = await World.started()
    guild = world.guild()
    assert [role.id for role in guild.roles] == [EVERYONE, RED, MODS]
    assert guild.default_role is not None
    assert guild.default_role.is_default()
    assert guild.get_role(999) is None
    await world.dispatch("GUILD_ROLE_CREATE", {"guild_id": "777", "role": role(778, "elsewhere", position=1)})
    assert guild.get_role(778) is None
    assert guild.get_role(RED) is not None
    assert guild.premium_subscriber_role is None
    assert [channel.id for channel in guild.channels] == [
        CATEGORY,
        GENERAL,
        ANNOUNCEMENTS,
        VOICE,
        STAGE,
        FORUM,
    ]
    assert [channel.id for channel in guild.text_channels] == [GENERAL, ANNOUNCEMENTS]
    assert [channel.id for channel in guild.voice_channels] == [VOICE]
    assert [channel.id for channel in guild.stage_channels] == [STAGE]
    assert [channel.id for channel in guild.categories] == [CATEGORY]
    assert [channel.id for channel in guild.forums] == [FORUM]
    assert isinstance(guild.get_channel(GENERAL), TextChannel)
    assert guild.get_channel(THREAD) is None
    assert guild.get_thread(THREAD) is not None
    assert guild.get_thread(GENERAL) is None
    assert guild.get_channel_or_thread(THREAD) is not None
    assert [thread.id for thread in guild.threads] == [THREAD]
    assert guild.system_channel is not None
    assert guild.system_channel.id == GENERAL
    assert guild.rules_channel is guild.public_updates_channel is None
    assert guild.afk_channel is not None
    assert guild.afk_channel.id == VOICE


async def test_a_channel_of_another_guild_is_not_this_guilds() -> None:
    world = await World.started()
    await world.dispatch("CHANNEL_CREATE", channel(70, 0, "elsewhere") | {"guild_id": "99"})
    assert world.guild().get_channel(70) is None


async def test_expressions_events_and_stages_come_from_the_cache() -> None:
    world = await World.started()
    guild = world.guild()
    assert [emoji.id for emoji in guild.emojis] == [EMOJI]
    assert guild.get_emoji(EMOJI) is not None
    assert guild.get_emoji(999) is None
    assert guild.stickers == []
    assert guild.get_sticker(1) is None
    assert guild.scheduled_events == []
    assert guild.get_scheduled_event(1) is None
    assert [stage.id for stage in guild.stage_instances] == [50]
    assert guild.get_stage_instance(50) is not None
    assert guild.soundboard_sounds == []
    assert guild.get_soundboard_sound(1) is None


async def test_fetch_member_and_members_page_through_discord() -> None:
    world = await World.started()
    guild = world.guild()
    world.transport.queue(200, member(ALICE, "alice"))
    assert (await guild.fetch_member(ALICE)).id == ALICE
    world.transport.queue(200, [member(index, f"m{index}") for index in range(1, 1001)])
    world.transport.queue(200, [member(2000, "last")])
    fetched = [found.id async for found in guild.fetch_members(limit=None)]
    assert len(fetched) == 1001
    assert world.requests()[-2:] == [
        ("GET", f"/guilds/{GUILD}/members?limit=1000&after=0", None),
        ("GET", f"/guilds/{GUILD}/members?limit=1000&after=1000", None),
    ]
    world.transport.queue(200, [member(1, "a"), member(2, "b")])
    assert [found.id async for found in guild.fetch_members(limit=2)] == [1, 2]


async def test_bans_page_through_discord() -> None:
    world = await World.started()
    guild = world.guild()
    world.transport.queue(
        200, [{"reason": None, "user": user(1, "a")}, {"reason": "spam", "user": user(2, "b")}]
    )
    assert [ban.user.id async for ban in guild.bans(limit=2)] == [1, 2]
    world.transport.queue(200, {"reason": "spam", "user": user(2, "b")})
    assert (await guild.fetch_ban(Object(2))).reason == "spam"


async def test_moderation_calls() -> None:
    world = await World.started()
    guild = world.guild()
    world.transport.queue(204)
    await guild.ban(Object(5), reason="r")
    assert world.last_request() == ("PUT", f"/guilds/{GUILD}/bans/5", {"delete_message_seconds": 86400})
    world.transport.queue(204)
    await guild.unban(Object(5))
    world.transport.queue(204)
    await guild.kick(Object(5))
    assert world.last_request()[:2] == ("DELETE", f"/guilds/{GUILD}/members/5")
    world.transport.queue(200, {"pruned": 3})
    assert await guild.estimate_pruned_members(days=7, roles=[Object(MODS)]) == 3
    assert world.last_request()[:2] == ("GET", f"/guilds/{GUILD}/prune?days=7&include_roles={MODS}")
    world.transport.queue(200, {"pruned": None})
    assert await guild.prune_members(days=7, compute_prune_count=False) is None


async def test_creating_channels_roles_and_emojis() -> None:
    world = await World.started()
    guild = world.guild()
    world.transport.queue(200, channel(80, 0, "new", parent=CATEGORY))
    text = await guild.create_text_channel("new", category=Object(CATEGORY), topic="t", slowmode_delay=5)
    assert isinstance(text, TextChannel)
    assert world.last_request() == (
        "POST",
        f"/guilds/{GUILD}/channels",
        {"name": "new", "type": 0, "topic": "t", "rate_limit_per_user": 5, "parent_id": str(CATEGORY)},
    )
    world.transport.queue(200, channel(84, 0, "staff"))
    mods = guild.get_role(MODS)
    assert mods is not None
    await guild.create_text_channel(
        "staff",
        overwrites={mods: PermissionOverwrite(read_messages=True), Object(ALICE): PermissionOverwrite()},
    )
    assert world.last_request()[2] == {
        "name": "staff",
        "type": 0,
        "permission_overwrites": [
            {"id": str(MODS), "type": 0, "allow": str(1 << 10), "deny": "0"},
            {"id": str(ALICE), "type": 1, "allow": "0", "deny": "0"},
        ],
    }
    world.transport.queue(200, channel(81, 2, "vc"))
    assert isinstance(await guild.create_voice_channel("vc", bitrate=64000), VoiceChannel)
    world.transport.queue(200, channel(82, 4, "cat"))
    assert isinstance(await guild.create_category("cat", position=3), CategoryChannel)
    world.transport.queue(200, channel(83, 2, "wrong"))
    with pytest.raises(TypeError, match="not a TextChannel"):
        await guild.create_text_channel("wrong")
    world.transport.queue(200, role(90, "new role", position=1))
    created = await guild.create_role(name="new role", colour=0x123456, hoist=True)
    assert created.id == 90
    assert world.last_request()[2] == {
        "name": "new role",
        "color": 0x123456,
        "hoist": True,
        "mentionable": False,
    }
    world.transport.queue(200, {"id": "91", "name": "e"})
    emoji = await guild.create_custom_emoji(name="e", image=PNG, roles=[Object(MODS)])
    assert emoji.id == 91


async def test_fetch_permissions_asks_discord_for_a_member_or_role() -> None:
    world = await World.started()
    guild = world.guild()
    bob, red = guild.get_member(BOB), guild.get_role(RED)
    assert bob is not None
    assert red is not None
    world.transport.queue(200, {"permissions": "8"})
    assert await guild.fetch_permissions(bob) == Permissions(8)
    assert world.last_request()[:2] == ("GET", f"/guilds/{GUILD}/permissions/member/{BOB}")
    world.transport.queue(200, {"permissions": "1024"})
    assert await guild.fetch_permissions(red) == Permissions(1024)
    assert world.last_request()[:2] == ("GET", f"/guilds/{GUILD}/permissions/role/{RED}")


async def test_fetching_roles_and_channels() -> None:
    world = await World.started()
    guild = world.guild()
    world.transport.queue(200, [role(MODS, "mods", position=2), role(EVERYONE, "@everyone", position=0)])
    assert [found.id for found in await guild.fetch_roles()] == [EVERYONE, MODS]
    world.transport.queue(200, [channel(STAGE, 13, "Stage"), channel(FORUM, 15, "help")])
    fetched = await guild.fetch_channels()
    assert isinstance(fetched[0], StageChannel)
    assert isinstance(fetched[1], ForumChannel)


async def test_editing_and_leaving() -> None:
    world = await World.started()
    guild = world.guild()
    world.transport.queue(200, guild_create() | {"name": "Renamed"})
    edited = await guild.edit(
        name="Renamed", icon=PNG, banner=None, system_channel=None, rules_channel=Object(GENERAL)
    )
    body = world.last_body()
    assert body["name"] == "Renamed"
    assert body["banner"] is None
    assert body["system_channel_id"] is None
    assert body["rules_channel_id"] == str(GENERAL)
    assert str(body["icon"]).startswith("data:image/png")
    assert edited.name == "Renamed"
    world.transport.queue(204)
    await guild.leave()
    assert world.last_request()[:2] == ("DELETE", f"/users/@me/guilds/{GUILD}")
    world.transport.queue(200, [])
    assert await guild.invites() == []
    world.transport.queue(200, [])
    assert await guild.webhooks() == []
