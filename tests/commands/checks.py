import inspect

import pytest

from shoal import commands
from shoal.commands import Context
from shoal.commands.checks import DM_PERMISSIONS, CheckDecorator, channel_permissions
from shoal.commands.errors import (
    BotMissingAnyRoleError,
    BotMissingPermissionsError,
    BotMissingRoleError,
    CheckAnyFailureError,
    MissingAnyRoleError,
    MissingPermissionsError,
    MissingRoleError,
    NoPrivateMessageError,
    NotOwnerError,
    NSFWChannelRequiredError,
    PrivateMessageOnlyError,
)
from tests.support.client import feed
from tests.support.commands import PrefixBot, bot_started, context_in
from tests.support.interactions import command as slash
from tests.support.interactions import payload
from tests.support.json_payloads import APPLICATION
from tests.support.models import (
    ALICE,
    BOB,
    BOT,
    CATEGORY,
    GENERAL,
    GUILD,
    MODS,
    OWNER,
    RED,
    THREAD,
    channel,
    user,
)


async def passes(decorator: CheckDecorator, ctx: Context) -> bool:
    result = decorator.predicate(ctx)
    return bool(await result if inspect.isawaitable(result) else result)


async def bot() -> PrefixBot:
    started, _ = await bot_started()
    return started


async def test_permission_checks_read_the_channel() -> None:
    made = await bot()
    assert await passes(commands.has_permissions(send_messages=True), context_in(made, author=BOB))
    with pytest.raises(MissingPermissionsError) as refused:
        await passes(commands.has_permissions(send_messages=True, view_channel=True), context_in(made))
    assert refused.value.missing_permissions == ["send_messages"]
    assert await passes(commands.has_permissions(send_messages=True), context_in(made, in_guild=False))
    with pytest.raises(MissingPermissionsError):
        await passes(commands.has_permissions(ban_members=True), context_in(made, in_guild=False))
    with pytest.raises(BotMissingPermissionsError):
        await passes(commands.bot_has_permissions(send_messages=True), context_in(made))
    with pytest.raises(TypeError):
        commands.has_permissions(fly=True)


async def test_guild_permission_checks_need_a_member() -> None:
    made = await bot()
    assert await passes(commands.has_guild_permissions(ban_members=True), context_in(made, author=BOB))
    with pytest.raises(MissingPermissionsError):
        await passes(commands.has_guild_permissions(ban_members=True), context_in(made))
    with pytest.raises(BotMissingPermissionsError):
        await passes(commands.bot_has_guild_permissions(ban_members=True), context_in(made))
    with pytest.raises(NoPrivateMessageError):
        await passes(commands.has_guild_permissions(ban_members=True), context_in(made, in_guild=False))


async def test_role_checks_take_ids_or_names() -> None:
    made = await bot()
    assert await passes(commands.has_role(MODS), context_in(made, author=BOB))
    assert await passes(commands.has_role("red"), context_in(made))
    with pytest.raises(MissingRoleError):
        await passes(commands.has_role("mods"), context_in(made))
    assert await passes(commands.has_any_role("mods", RED), context_in(made))
    with pytest.raises(MissingAnyRoleError):
        await passes(commands.has_any_role(MODS), context_in(made))
    with pytest.raises(BotMissingRoleError):
        await passes(commands.bot_has_role("mods"), context_in(made))
    with pytest.raises(BotMissingAnyRoleError) as refused:
        await passes(commands.bot_has_any_role("mods", MODS), context_in(made))
    assert refused.value.missing_roles == ["mods", MODS]
    update = {"guild_id": str(GUILD), "roles": [str(MODS)], "user": user(BOT, "shoalbot"), "joined_at": None}
    await feed(made, "GUILD_MEMBER_UPDATE", update | {"avatar": None, "banner": None})
    assert await passes(commands.bot_has_any_role("red", MODS), context_in(made))


async def test_place_checks() -> None:
    made = await bot()
    assert await passes(commands.guild_only(), context_in(made))
    with pytest.raises(NoPrivateMessageError):
        await passes(commands.guild_only(), context_in(made, in_guild=False))
    assert await passes(commands.dm_only(), context_in(made, in_guild=False))
    with pytest.raises(PrivateMessageOnlyError):
        await passes(commands.dm_only(), context_in(made))
    with pytest.raises(NSFWChannelRequiredError):
        await passes(commands.is_nsfw(), context_in(made))
    assert await passes(commands.is_nsfw(), context_in(made, in_guild=False))


async def test_threads_are_age_restricted_when_their_parent_is() -> None:
    made = await bot()
    with pytest.raises(NSFWChannelRequiredError):
        await passes(commands.is_nsfw(), context_in(made, channel=THREAD))
    general = channel(GENERAL, 0, "general", position=1, parent=CATEGORY, nsfw=True)
    await feed(made, "CHANNEL_UPDATE", general)
    assert await passes(commands.is_nsfw(), context_in(made, channel=THREAD))


async def test_owner_and_combined_checks() -> None:
    made, transport = await bot_started()
    transport.queue(200, APPLICATION | {"owner": user(OWNER, "owner"), "team": None})
    assert await passes(commands.is_owner(), context_in(made, author=OWNER))
    with pytest.raises(NotOwnerError):
        await passes(commands.is_owner(), context_in(made))
    either = commands.check_any(commands.is_owner(), commands.has_role("red"))
    assert await passes(either, context_in(made))
    with pytest.raises(CheckAnyFailureError) as refused:
        await passes(either, context_in(made, author=BOB))
    assert len(refused.value.errors) == 2
    assert await passes(commands.check_any(commands.check(lambda _: True)), context_in(made))


async def test_dm_permissions_cover_what_a_dm_allows() -> None:
    made = await bot()
    assert channel_permissions(context_in(made, in_guild=False), None) == DM_PERMISSIONS
    assert channel_permissions(context_in(made), None) == DM_PERMISSIONS
    guild = made.get_guild(GUILD)
    assert guild is not None
    alice = guild.get_member(ALICE)
    assert alice is not None
    assert not channel_permissions(context_in(made), alice).send_messages
    assert channel_permissions(context_in(made), alice).view_channel


async def test_decorators_apply_to_made_commands_too() -> None:
    made = await bot()

    async def hook(ctx: Context) -> None:
        del ctx

    async def run(ctx: Context) -> None:
        del ctx

    built = commands.command()(run)
    commands.cooldown(1, 5.0)(built)
    commands.max_concurrency(2)(built)
    commands.before_invoke(hook)(built)
    commands.after_invoke(hook)(built)
    commands.guild_only()(built)
    assert built.cooldown is not None
    assert built.max_concurrency is not None
    assert built.max_concurrency.number == 2
    assert len(built.checks) == 1
    assert await built.can_run(context_in(made))


async def test_slash_contexts_read_the_permissions_discord_sent() -> None:
    made, _ = await bot_started()
    interaction = await made.process_interaction(payload(slash("ping")))
    ctx = Context(made, interaction)
    assert await passes(commands.has_permissions(send_messages=True), ctx)
    with pytest.raises(MissingPermissionsError):
        await passes(commands.has_permissions(administrator=True), ctx)
    assert await passes(commands.bot_has_permissions(embed_links=True), ctx)
    with pytest.raises(BotMissingPermissionsError):
        await passes(commands.bot_has_permissions(administrator=True), ctx)
