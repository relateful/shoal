import pytest

from shoal import app_commands
from shoal.app_commands.checks import Cooldown, by_channel, by_guild, by_user
from shoal.app_commands.errors import (
    BotMissingPermissionsError,
    CommandOnCooldownError,
    MissingAnyRoleError,
    MissingPermissionsError,
    MissingRoleError,
    NoPrivateMessageError,
)
from shoal.app_commands.tree import CommandTree
from shoal.client.client import Client
from shoal.client.interaction import Interaction
from tests.support.client import started
from tests.support.fakes import settle
from tests.support.interactions import command, payload
from tests.support.models import ALICE, GENERAL, GUILD, MODS, RED, member

type Json = dict[str, object]


def with_roles(*roles: int) -> Json:
    """A command used by Alice holding `roles`."""
    data = command("guarded")
    data["member"] = member(ALICE, "alice", roles=list(roles)) | {"permissions": "2048"}
    return data


async def run(client: Client, tree: CommandTree, data: Json) -> list[Exception]:
    """Use `guarded` with `data`; the errors the tree received."""
    errors: list[Exception] = []

    @tree.error
    async def record(interaction: Interaction, error: Exception) -> None:
        del interaction
        errors.append(error)

    await client.process_interaction(payload(data))
    await settle()
    return errors


async def guarded(interaction: Interaction) -> None:
    del interaction


async def test_has_permissions_reads_the_users_channel_permissions() -> None:
    client, _ = await started()
    tree = CommandTree(client)
    tree.add_command(
        app_commands.checks.has_permissions(send_messages=True, manage_messages=True)(
            app_commands.command()(guarded)
        )
    )
    [error] = await run(client, tree, command("guarded"))
    assert isinstance(error, MissingPermissionsError)
    assert error.missing_permissions == ["manage_messages"]


async def test_bot_has_permissions_reads_the_apps_permissions() -> None:
    client, _ = await started()
    tree = CommandTree(client)
    tree.add_command(
        app_commands.checks.bot_has_permissions(administrator=True)(app_commands.command()(guarded))
    )
    [error] = await run(client, tree, command("guarded"))
    assert isinstance(error, BotMissingPermissionsError)
    assert error.missing_permissions == ["administrator"]


def test_permission_names_are_checked_up_front() -> None:
    with pytest.raises(TypeError):
        app_commands.checks.has_permissions(fly=True)


async def test_role_checks_accept_ids_and_names() -> None:
    client, _ = await started()
    tree = CommandTree(client)
    tree.add_command(app_commands.checks.has_role("mods")(app_commands.command()(guarded)))
    assert await run(client, tree, with_roles(MODS)) == []
    [error] = await run(client, tree, with_roles(RED))
    assert isinstance(error, MissingRoleError)
    assert error.missing_role == "mods"

    tree.remove_command("guarded")
    tree.add_command(app_commands.checks.has_any_role(MODS, "red")(app_commands.command()(guarded)))
    assert await run(client, tree, with_roles(RED)) == []
    [error] = await run(client, tree, with_roles())
    assert isinstance(error, MissingAnyRoleError)
    assert error.missing_roles == [MODS, "red"]


async def test_role_checks_refuse_outside_guilds() -> None:
    client, _ = await started()
    tree = CommandTree(client)
    tree.add_command(app_commands.checks.has_role(MODS)(app_commands.command()(guarded)))
    [error] = await run(client, tree, command("guarded", in_guild=False))
    assert isinstance(error, NoPrivateMessageError)


async def test_cooldown_refuses_until_the_window_passes() -> None:
    client, _ = await started()
    interaction = await client.process_interaction(payload(command("x")))
    now = [0.0]
    cooldown = Cooldown(2, 10.0, clock=lambda: now[0])
    assert cooldown.retry_after(interaction) == 0.0
    now[0] = 4.0
    assert cooldown.retry_after(interaction) == 0.0
    assert cooldown.retry_after(interaction) == 6.0
    now[0] = 10.5
    assert cooldown.retry_after(interaction) == 0.0


async def test_cooldowns_count_per_key() -> None:
    client, _ = await started()
    in_guild = await client.process_interaction(payload(command("x")))
    in_dm = await client.process_interaction(payload(command("x", in_guild=False)))
    assert by_user(in_guild) == ALICE
    assert by_guild(in_guild) == GUILD
    assert by_guild(in_dm) == ALICE
    assert by_channel(in_guild) == GENERAL


def test_a_cooldown_needs_a_positive_rate_and_window() -> None:
    with pytest.raises(ValueError, match="rate >= 1"):
        Cooldown(0, 1.0)
    with pytest.raises(ValueError, match="per > 0"):
        Cooldown(1, 0.0)


async def test_the_cooldown_decorator_refuses_a_second_use() -> None:
    client, _ = await started()
    tree = CommandTree(client)
    tree.add_command(app_commands.checks.cooldown(1, 60.0)(app_commands.command()(guarded)))
    assert await run(client, tree, command("guarded")) == []
    [error] = await run(client, tree, command("guarded"))
    assert isinstance(error, CommandOnCooldownError)
    assert 59.0 < error.retry_after <= 60.0


async def test_a_full_cooldown_forgets_expired_keys() -> None:
    client, _ = await started()
    now = [0.0]
    cooldown = Cooldown(1, 1.0, key=lambda interaction: interaction.id, clock=lambda: now[0])
    for index in range(1024):
        cooldown.retry_after(await client.process_interaction(payload(command("x", interaction_id=index))))
    now[0] = 5.0
    latest = await client.process_interaction(payload(command("x", interaction_id=5000)))
    assert cooldown.retry_after(latest) == 0.0
    assert cooldown.tracked == 1
