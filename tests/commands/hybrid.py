import logging
from typing import Annotated, override

import msgspec
import pytest

from shoal import app_commands, commands
from shoal.app_commands.parameters import NO_DESCRIPTION
from shoal.commands import Cog, Context, HybridCommand, HybridGroup
from shoal.commands.errors import BadArgumentError, CheckFailureError, HybridCommandError
from shoal.core.codec import encode_json
from shoal.models.member import Member
from shoal.payloads.permissions import Permissions
from tests.support.client import Recorder
from tests.support.commands import bot_started, say
from tests.support.fakes import settle
from tests.support.interactions import command as slash
from tests.support.interactions import payload
from tests.support.models import BOB, member, user


def option(name: str, value: object, kind: int = 3) -> dict[str, object]:
    return {"name": name, "type": kind, "value": value}


class Shout(commands.Converter[str]):
    @override
    async def convert(self, ctx: Context, argument: str) -> str:
        del ctx
        if argument == "quiet":
            msg = "too quiet"
            raise BadArgumentError(msg)
        return argument.upper()


async def test_a_hybrid_command_runs_both_ways() -> None:
    bot, transport = await bot_started()
    seen: list[tuple[str, int, str]] = []

    @bot.hybrid_command()
    @app_commands.describe(times="How many times")
    async def echo(ctx: Context, times: int, *, text: Annotated[str, Shout]) -> None:
        """Repeat something."""
        seen.append(("slash" if ctx.interaction else "prefix", times, text))

    await say(bot, transport, "!echo 2 hello there")
    await bot.process_interaction(payload(slash("echo", option("times", 3, 4), option("text", "hi"))))
    await settle()
    assert seen == [("prefix", 2, "HELLO THERE"), ("slash", 3, "HI")]
    sent_options = msgspec.json.decode(encode_json(echo.app_command.to_payload()))["options"]
    assert sent_options == [
        {"type": 4, "name": "times", "description": "How many times", "required": True},
        {"type": 3, "name": "text", "description": NO_DESCRIPTION, "required": True},
    ]
    assert echo.app_command.description == "Repeat something."
    assert bot.tree.get_command("echo") is echo.app_command


async def test_slash_errors_reach_the_command_error_event(caplog: pytest.LogCaptureFixture) -> None:
    bot, _ = await bot_started()
    events = Recorder(bot, "command_error", "command_completion")

    @commands.check(lambda ctx: ctx.author.id == BOB)
    @bot.hybrid_command()
    async def mods(ctx: Context) -> None:
        del ctx

    @bot.hybrid_command()
    async def loud(ctx: Context, text: Annotated[str, Shout]) -> None:
        del ctx, text

    @bot.hybrid_command()
    async def needs(ctx: Context, member: Member) -> None:
        del ctx, member

    await bot.process_interaction(payload(slash("mods")))
    await bot.process_interaction(payload(slash("loud", option("text", "quiet"))))
    await bot.process_interaction(payload(slash("needs", option("member", str(BOB + 1), 6))))
    await settle()
    errors = [args[1] for name, args in events.seen if name == "command_error"]
    assert [type(error) for error in errors] == [CheckFailureError, BadArgumentError, HybridCommandError]
    hybrid_error = errors[2]
    assert isinstance(hybrid_error, HybridCommandError)
    assert isinstance(hybrid_error.original, app_commands.TransformerError)
    # One log line per error: the command error path logged each, and the tree none a second time.
    assert len([record for record in caplog.records if record.levelno >= logging.ERROR]) == len(errors)


async def test_slash_members_come_from_the_resolved_data() -> None:
    bot, _ = await bot_started()
    seen: list[int] = []

    @bot.hybrid_command()
    async def greet(ctx: Context, target: Member) -> None:
        del ctx
        seen.append(target.id)

    partial = {key: value for key, value in member(BOB, "bob").items() if key != "user"}
    resolved: dict[str, object] = {"users": {str(BOB): user(BOB, "bob")}, "members": {str(BOB): partial}}
    await bot.process_interaction(payload(slash("greet", option("target", str(BOB), 6), resolved=resolved)))
    await settle()
    assert seen == [BOB]


async def test_hybrid_groups_route_subcommands_both_ways() -> None:
    bot, transport = await bot_started()
    seen: list[str] = []

    @bot.hybrid_group()
    async def tag(ctx: Context) -> None:
        del ctx

    @tag.hybrid_command()
    async def show(ctx: Context, name: str) -> None:
        seen.append(f"{'slash' if ctx.interaction else 'prefix'} {name}")

    @tag.command()
    async def legacy(ctx: Context) -> None:
        del ctx
        seen.append("legacy")

    await say(bot, transport, "!tag show faq")
    await say(bot, transport, "!tag legacy")
    sub: dict[str, object] = {"name": "show", "type": 1, "options": [option("name", "rules")]}
    await bot.process_interaction(payload(slash("tag", sub)))
    await settle()
    assert seen == ["prefix faq", "legacy", "slash rules"]
    assert [command.name for command in tag.app_command.commands] == ["show"]
    assert tag.remove_command("show") is show
    assert tag.app_command.commands == []


class Fun(Cog):
    def __init__(self) -> None:
        self.calls: list[int] = []

    @commands.hybrid_command()
    async def roll(self, ctx: Context, sides: int = 6) -> None:
        del ctx
        self.calls.append(sides)


async def test_hybrid_commands_in_cogs_are_bound_both_ways() -> None:
    bot, transport = await bot_started()
    cog = Fun()
    await bot.add_cog(cog)
    roll = bot.get_command("roll")
    assert isinstance(roll, HybridCommand)
    assert bot.tree.get_command("roll") is roll.app_command
    assert roll.app_command is not Fun.roll.app_command
    await say(bot, transport, "!roll 20")
    await bot.process_interaction(payload(slash("roll")))
    await settle()
    assert cog.calls == [20, 6]
    await bot.remove_cog("Fun")
    assert bot.tree.get_command("roll") is None


def test_star_args_cannot_be_slash_options() -> None:
    async def many(ctx: Context, *words: str) -> None:
        del ctx, words

    with pytest.raises(TypeError, match="cannot be slash options"):
        HybridCommand(many)


class Tags(Cog):
    def __init__(self) -> None:
        self.calls: list[str] = []

    @commands.hybrid_group()
    async def tag(self, ctx: Context) -> None:
        del ctx

    @tag.hybrid_command()
    async def show(self, ctx: Context, name: str) -> None:
        self.calls.append(f"{'slash' if ctx.interaction else 'prefix'} {name}")

    @tag.hybrid_group()
    async def admin(self, ctx: Context) -> None:
        del ctx

    @admin.hybrid_command()
    async def wipe(self, ctx: Context) -> None:
        del ctx
        self.calls.append("wipe")


async def test_hybrid_groups_in_cogs_get_their_own_slash_groups() -> None:
    bot, transport = await bot_started()
    first, second = Tags(), Tags()
    await bot.add_cog(first)
    copied = bot.get_command("tag")
    assert isinstance(copied, HybridGroup)
    assert copied.app_command is not Tags.tag.app_command
    assert [command.name for command in copied.app_command.commands] == ["show", "admin"]
    assert [command.name for command in Tags.tag.app_command.commands] == ["show", "admin"]
    await say(bot, transport, "!tag show faq")
    wipe: dict[str, object] = {
        "name": "admin",
        "type": 2,
        "options": [{"name": "wipe", "type": 1, "options": []}],
    }
    await bot.process_interaction(payload(slash("tag", wipe)))
    await settle()
    assert first.calls == ["prefix faq", "wipe"]
    await bot.add_cog(second, override=True)
    assert bot.get_cog("Tags") is second


def test_hybrid_groups_can_be_made_on_their_own() -> None:
    @commands.hybrid_group(invoke_without_command=True)
    async def settings(ctx: Context) -> None:
        """Settings."""
        del ctx

    assert isinstance(settings, HybridGroup)
    assert settings.app_command.name == "settings"
    assert settings.app_command.description == "Settings."


async def test_slash_side_checks_the_group_and_the_command_before_converting() -> None:
    bot, _ = await bot_started()
    events = Recorder(bot, "command_error")
    converted: list[str] = []

    class Looked(commands.Converter[str]):
        @override
        async def convert(self, ctx: Context, argument: str) -> str:
            del ctx
            converted.append(argument)
            return argument

    @bot.hybrid_group()
    @commands.check(lambda ctx: ctx.author.id == BOB)
    async def admin(ctx: Context) -> None:
        del ctx

    @admin.hybrid_command()
    async def note(ctx: Context, text: Annotated[str, Looked]) -> None:
        del ctx, text

    sub: dict[str, object] = {"name": "note", "type": 1, "options": [option("text", "hello")]}
    await bot.process_interaction(payload(slash("admin", sub)))
    await settle()
    ctx, error = events.args("command_error")
    assert isinstance(error, CheckFailureError)
    assert isinstance(ctx, Context)
    assert ctx.invoked_parents == ["admin"]
    # Refused by the group's check before the option went through its converter.
    assert converted == []


def test_slash_settings_on_a_hybrid_group_reach_its_slash_group() -> None:
    @commands.hybrid_group()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def config(ctx: Context) -> None:
        del ctx

    assert config.app_command.guild_only
    assert config.app_command.default_permissions == Permissions(manage_guild=True)


async def test_settings_made_on_the_slash_side_survive_a_copy() -> None:
    @commands.hybrid_command()
    async def ping(ctx: Context) -> None:
        del ctx

    ping.app_command.guild_only = True
    ping.app_command.guild_ids.append(5)
    copied = ping.copy()
    assert copied.app_command is not ping.app_command
    assert copied.app_command.guild_only
    assert copied.app_command.guild_ids == [5]
