import importlib
import logging
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

from shoal.commands import Bot, Context, command, when_mentioned, when_mentioned_or
from shoal.commands.core import CommandRegistrationError
from shoal.commands.errors import (
    CommandNotFoundError,
    ExtensionAlreadyLoadedError,
    ExtensionFailedError,
    ExtensionNotFoundError,
    ExtensionNotLoadedError,
    NoEntryPointError,
)
from shoal.core.metrics import InMemoryMetrics
from shoal.models.message import Message
from tests.support.calls import call_unchecked
from tests.support.client import INTENTS, Recorder
from tests.support.commands import PrefixBot, bot_started, say, sent
from tests.support.json_payloads import APPLICATION
from tests.support.models import ALICE, BOT, user


async def test_a_command_runs_from_a_message() -> None:
    bot, transport = await bot_started()

    @bot.command()
    async def ping(ctx: Context) -> None:
        await ctx.send("Pong")

    await say(bot, transport, "!ping", replies=1)
    assert sent(transport) == ["Pong"]


async def test_messages_without_the_prefix_or_from_bots_are_ignored() -> None:
    bot, transport = await bot_started()
    ran: list[str] = []

    @bot.command()
    async def ping(ctx: Context) -> None:
        ran.append(ctx.author.name)

    await say(bot, transport, "ping")
    await say(bot, transport, "!ping", author=999, from_bot=True)
    await say(bot, transport, "!ping")
    assert ran == ["alice"]


async def test_prefixes_can_be_several_or_computed() -> None:
    class Several(PrefixBot):
        prefix = ("?", "!!")

    bot, transport = await bot_started(Several)
    ran: list[str | None] = []

    @bot.command()
    async def ping(ctx: Context) -> None:
        ran.append(ctx.prefix)

    await say(bot, transport, "?ping")
    await say(bot, transport, "!!ping")
    await say(bot, transport, "!ping")
    assert ran == ["?", "!!"]


async def test_mentioning_the_bot_can_be_the_prefix() -> None:
    class Mentioned(PrefixBot):
        prefix = staticmethod(when_mentioned_or("$"))

    bot, transport = await bot_started(Mentioned)
    seen: list[str] = []

    @bot.command()
    async def ping(ctx: Context) -> None:
        seen.append(ctx.clean_prefix)

    await say(bot, transport, f"<@{BOT}> ping")
    await say(bot, transport, "$ping")
    assert seen == ["@shoalbot ", "$"]


async def test_when_mentioned_is_empty_before_login() -> None:
    bot = Bot("!", intents=INTENTS)
    assert call_unchecked(when_mentioned, bot, object()) == []


async def test_async_prefix_functions_are_awaited() -> None:
    async def prefix(bot: Bot, message: Message) -> str:
        del bot, message
        return ">"

    class Computed(PrefixBot):
        pass

    Computed.prefix = prefix
    bot, transport = await bot_started(Computed)
    ran: list[bool] = []

    @bot.command()
    async def ping(ctx: Context) -> None:
        del ctx
        ran.append(True)

    await say(bot, transport, ">ping")
    assert ran == [True]


async def test_names_can_ignore_case_and_spaces_after_the_prefix() -> None:
    bot, transport = await bot_started()
    bot.case_insensitive = True
    bot.strip_after_prefix = True
    ran: list[str | None] = []

    @bot.command(aliases=["Hi"])
    async def hello(ctx: Context) -> None:
        ran.append(ctx.invoked_with)

    await say(bot, transport, "! HELLO")
    await say(bot, transport, "!hi")
    assert ran == ["HELLO", "hi"]


async def test_unknown_commands_reach_the_error_event() -> None:
    bot, transport = await bot_started()
    events = Recorder(bot, "command_error")
    await say(bot, transport, "!nothing")
    _, error = events.args("command_error")
    assert isinstance(error, CommandNotFoundError)
    assert error.name == "nothing"


async def test_unhandled_errors_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    bot, transport = await bot_started()

    @bot.command()
    async def broken(ctx: Context) -> None:
        del ctx
        msg = "boom"
        raise RuntimeError(msg)

    with caplog.at_level(logging.ERROR, logger="shoal.commands"):
        await say(bot, transport, "!broken")
    assert "command 'broken' raised" in caplog.text


async def test_command_events_mark_the_start_and_the_end() -> None:
    bot, transport = await bot_started()
    events = Recorder(bot, "command", "command_completion")

    @bot.command()
    async def quiet(ctx: Context) -> None:
        del ctx

    await say(bot, transport, "!quiet")
    assert events.names() == ["command", "command_completion"]


async def test_replacing_on_message_turns_commands_off_unless_it_processes_them() -> None:
    bot, transport = await bot_started()
    ran: list[str] = []

    @bot.command()
    async def ping(ctx: Context) -> None:
        del ctx
        ran.append("ping")

    @bot.event
    async def on_message(message: Message) -> None:
        if message.content.endswith("please"):
            await bot.process_commands(message)

    await say(bot, transport, "!ping")
    await say(bot, transport, "!ping please")
    assert ran == ["ping"]


def test_names_and_aliases_cannot_be_taken_twice() -> None:
    bot = Bot("!", intents=INTENTS)

    async def ping(ctx: Context) -> None:
        del ctx

    bot.add_command(command(aliases=["p"])(ping))
    with pytest.raises(CommandRegistrationError, match="'ping'"):
        bot.add_command(command()(ping))
    with pytest.raises(CommandRegistrationError, match="alias 'p'"):
        bot.add_command(command(name="other", aliases=["p"])(ping))
    assert [found.name for found in bot.commands] == ["help", "ping"]
    removed = bot.remove_command("p")
    assert removed is not None
    assert bot.get_command("ping") is None
    assert bot.remove_command("ping") is None


async def test_global_checks_and_hooks_apply_to_every_command() -> None:
    bot, transport = await bot_started()
    order: list[str] = []

    @bot.check
    def only_alice(ctx: Context) -> bool:
        return ctx.author.id == ALICE

    @bot.before_invoke
    async def before(ctx: Context) -> None:
        del ctx
        order.append("before")

    @bot.after_invoke
    async def after(ctx: Context) -> None:
        del ctx
        order.append("after")

    @bot.command()
    async def run(ctx: Context) -> None:
        del ctx
        order.append("run")

    await say(bot, transport, "!run")
    await say(bot, transport, "!run", author=BOT + 100)
    assert order == ["before", "run", "after"]
    bot.remove_check(only_alice)
    assert bot.checks == []


async def test_owners_come_from_the_application_or_the_arguments() -> None:
    bot, transport = await bot_started()
    owner = user(ALICE, "alice")
    transport.queue(200, APPLICATION | {"owner": owner, "team": None})
    alice = bot.get_user(ALICE)
    assert alice is not None
    assert await bot.is_owner(alice)
    assert await bot.is_owner(alice)
    assert len([request for request in transport.requests if request.url.endswith("/applications/@me")]) == 2
    named = Bot("!", intents=INTENTS, owner_ids=[1, 2])
    assert named.owner_ids == {1, 2}
    with pytest.raises(TypeError, match="not both"):
        Bot("!", intents=INTENTS, owner_id=1, owner_ids=[2])


def test_the_help_command_can_be_turned_off() -> None:
    bot = Bot("!", intents=INTENTS, help_command=None)
    assert bot.get_command("help") is None
    assert repr(bot) == "<Bot commands=0 cogs=0>"


def write_extension(folder: Path, name: str, body: str) -> None:
    (folder / f"{name}.py").write_text(textwrap.dedent(body), encoding="utf-8")


GREETER = """
    from shoal import commands

    class Greeter(commands.Cog):
        @commands.command()
        async def greet(self, ctx):
            await ctx.send("{reply}")

    @commands.command()
    async def wave(ctx):
        await ctx.send("wave")

    async def on_member_join(member):
        pass

    async def setup(bot):
        await bot.add_cog(Greeter())
        bot.add_command(wave)
        bot.add_listener(on_member_join)

    async def teardown(bot):
        bot.torn_down = True
"""


@pytest.fixture
def extensions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    yield tmp_path
    for name in [key for key in sys.modules if key.startswith("shoal_test_ext")]:
        del sys.modules[name]


async def test_an_extension_adds_and_removes_its_commands(extensions: Path) -> None:
    write_extension(extensions, "shoal_test_ext_greeter", GREETER.replace("{reply}", "hi"))
    bot, transport = await bot_started()
    await bot.load_extension("shoal_test_ext_greeter")
    assert list(bot.extensions) == ["shoal_test_ext_greeter"]
    await say(bot, transport, "!greet", replies=1)
    await say(bot, transport, "!wave", replies=1)
    assert sent(transport) == ["hi", "wave"]
    with pytest.raises(ExtensionAlreadyLoadedError):
        await bot.load_extension("shoal_test_ext_greeter")
    await bot.unload_extension("shoal_test_ext_greeter")
    assert bot.get_command("greet") is None
    assert bot.get_command("wave") is None
    assert bot.get_cog("Greeter") is None
    assert "shoal_test_ext_greeter" not in sys.modules
    assert vars(bot).get("torn_down") is True
    with pytest.raises(ExtensionNotLoadedError):
        await bot.unload_extension("shoal_test_ext_greeter")


async def test_a_reload_picks_up_changes_and_restores_on_failure(extensions: Path) -> None:
    write_extension(extensions, "shoal_test_ext_reload", GREETER.replace("{reply}", "first"))
    bot, transport = await bot_started()
    await bot.load_extension("shoal_test_ext_reload")
    write_extension(extensions, "shoal_test_ext_reload", GREETER.replace("{reply}", "second"))
    importlib.invalidate_caches()
    await bot.reload_extension("shoal_test_ext_reload")
    await say(bot, transport, "!greet", replies=1)
    write_extension(extensions, "shoal_test_ext_reload", "raise RuntimeError('broken')\n")
    importlib.invalidate_caches()
    with pytest.raises(ExtensionFailedError, match="broken"):
        await bot.reload_extension("shoal_test_ext_reload")
    await say(bot, transport, "!greet", replies=1)
    assert sent(transport) == ["second", "second"]
    with pytest.raises(ExtensionNotLoadedError):
        await bot.reload_extension("shoal_test_ext_missing")


SLASHER = """
    from shoal import app_commands

    @app_commands.command(description="Pong.")
    async def ping(interaction):
        pass

    tags = app_commands.Group(name="tags", description="Tags.")

    @tags.command(description="Show one.")
    async def show(interaction, name: str):
        pass

    async def setup(bot):
        bot.tree.add_command(ping)
        bot.tree.add_command(tags, guild=5)
"""


async def test_unloading_an_extension_takes_its_slash_commands_from_every_scope(extensions: Path) -> None:
    write_extension(extensions, "shoal_test_ext_slasher", SLASHER)
    bot, _ = await bot_started()
    await bot.load_extension("shoal_test_ext_slasher")
    assert [command.name for command in bot.tree.get_all_commands()] == ["ping", "tags"]
    importlib.invalidate_caches()
    await bot.reload_extension("shoal_test_ext_slasher")
    assert [command.name for command in bot.tree.get_all_commands()] == ["ping", "tags"]
    await bot.unload_extension("shoal_test_ext_slasher")
    assert bot.tree.get_all_commands() == []


async def test_broken_extensions_leave_nothing_behind(extensions: Path) -> None:
    bot, _ = await bot_started()
    with pytest.raises(ExtensionNotFoundError):
        await bot.load_extension("shoal_test_ext_nowhere")
    with pytest.raises(ExtensionNotFoundError):
        await bot.load_extension("..nowhere")
    write_extension(extensions, "shoal_test_ext_nosetup", "VALUE = 1\n")
    with pytest.raises(NoEntryPointError):
        await bot.load_extension("shoal_test_ext_nosetup")
    assert "shoal_test_ext_nosetup" not in sys.modules
    write_extension(extensions, "shoal_test_ext_import", "import shoal_test_ext_not_a_module\n")
    with pytest.raises(ExtensionFailedError):
        await bot.load_extension("shoal_test_ext_import")
    failing = GREETER.replace("{reply}", "x").replace(
        "bot.add_listener(on_member_join)", "raise ValueError('setup failed')"
    )
    write_extension(extensions, "shoal_test_ext_setup", failing)
    with pytest.raises(ExtensionFailedError, match="setup failed"):
        await bot.load_extension("shoal_test_ext_setup")
    assert bot.get_command("greet") is None
    assert bot.get_command("wave") is None
    assert bot.extensions == {}


async def test_a_failing_teardown_is_logged(extensions: Path, caplog: pytest.LogCaptureFixture) -> None:
    body = """
        async def setup(bot):
            pass

        async def teardown(bot):
            raise RuntimeError("teardown failed")
    """
    write_extension(extensions, "shoal_test_ext_teardown", body)
    bot, _ = await bot_started()
    await bot.load_extension("shoal_test_ext_teardown")
    with caplog.at_level(logging.ERROR, logger="shoal.commands"):
        await bot.unload_extension("shoal_test_ext_teardown")
    assert "teardown of extension shoal_test_ext_teardown raised" in caplog.text


async def test_a_bot_takes_the_clients_options() -> None:
    metrics = InMemoryMetrics()
    bot = Bot("!", intents=INTENTS, metrics=metrics, large_threshold=100, compression=None)
    await bot.close()
