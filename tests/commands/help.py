from typing import override

import pytest

from shoal import commands
from shoal.commands import Bot, Cog, Context, DefaultHelpCommand, HelpCommand
from shoal.commands.help import HelpMapping, MinimalHelpCommand, Paginator
from shoal.payloads.message import MESSAGE_CONTENT_MAX_LENGTH
from tests.support.client import INTENTS
from tests.support.commands import PrefixBot, bot_started, context_in, say, sent
from tests.support.fakes import FakeTransport
from tests.support.models import BOB


class Tools(Cog):
    """Handy tools."""

    @commands.command(aliases=["c"])
    async def calc(self, ctx: Context, first: int, second: int = 1) -> None:
        """Add two numbers.

        Second defaults to one.
        """
        del ctx, first, second

    @commands.group()
    async def tag(self, ctx: Context) -> None:
        """Manage tags."""
        del ctx

    @tag.command()
    async def create(self, ctx: Context, name: str) -> None:
        """Create a tag."""
        del ctx, name


async def helped_bot() -> tuple[PrefixBot, FakeTransport]:
    bot, transport = await bot_started()
    bot.description = "A test bot."

    @bot.command(hidden=True)
    async def secret(ctx: Context) -> None:
        del ctx

    @commands.check(lambda ctx: ctx.author.id == BOB)
    @bot.command()
    async def mods(ctx: Context) -> None:
        """For mods only."""
        del ctx

    @bot.command()
    async def ping(ctx: Context) -> None:
        """Check the bot is alive."""
        del ctx

    await bot.add_cog(Tools())
    return bot, transport


async def help_for(query: str = "", *, author: int | None = None, replies: int = 1) -> str:
    bot, transport = await helped_bot()
    text = f"!help {query}".strip()
    if author is None:
        await say(bot, transport, text, replies=replies)
    else:
        await say(bot, transport, text, author=author, replies=replies)
    return "\n".join(sent(transport))


async def test_the_bot_page_lists_what_the_user_can_run() -> None:
    page = await help_for()
    assert page == (
        "```\n"
        "A test bot.\n\n"
        "Tools:\n"
        "  calc Add two numbers.\n"
        "  tag  Manage tags.\n"
        "No Category:\n"
        "  help Shows this message\n"
        "  ping Check the bot is alive.\n\n"
        "Type !help command for more info on a command.\n"
        "You can also type !help category for more info on a category.\n"
        "```"
    )
    assert "mods" in await help_for(author=BOB)


async def test_command_group_and_cog_pages() -> None:
    command_page = await help_for("calc")
    assert command_page.startswith("```\n![calc|c] <first> [second=1]\n\nAdd two numbers.")
    group_page = await help_for("tag")
    assert "!tag \n" not in group_page
    assert "Commands:\n  create Create a tag." in group_page
    sub_page = await help_for("tag create")
    assert sub_page.startswith("```\n!tag create <name>")
    cog_page = await help_for("Tools")
    assert cog_page.startswith("```\nHandy tools.\n\nCommands:\n  calc")


async def test_unknown_names_are_reported() -> None:
    assert await help_for("nothing") == 'No command called "nothing" found.'
    assert await help_for("tag nothing") == 'Command "tag" has no subcommand named nothing'
    assert await help_for("ping more") == 'Command "ping" has no subcommands.'


async def test_long_pages_are_split_to_fit_messages() -> None:
    bot, transport = await bot_started()
    for index in range(80):

        async def callback(ctx: Context) -> None:
            del ctx

        bot.add_command(commands.Command(callback, name=f"command{index:02}", help="x" * 60))
    await say(bot, transport, "!help", replies=5)
    pages = sent(transport)
    assert len(pages) > 1
    assert all(len(page) <= MESSAGE_CONTENT_MAX_LENGTH for page in pages)
    assert all(page.startswith("```\n") and page.endswith("\n```") for page in pages)


class Plain(HelpCommand):
    @override
    async def send_bot_help(self, mapping: HelpMapping) -> None:
        names = sorted(command.name for listed in mapping.values() for command in listed)
        await self.get_destination().send(f"{self.context.author.name}: {', '.join(names)}")


async def test_a_custom_help_command_uses_its_context() -> None:
    bot, transport = await bot_started()
    bot.help_command = Plain(command_name="commands")
    await say(bot, transport, "!commands", replies=1)
    assert sent(transport) == ["alice: commands"]
    ctx = context_in(bot)
    with pytest.raises(NotImplementedError):
        await bot.send_help(ctx, bot.get_command("commands"))
    bot.help_command = None
    await bot.send_help(ctx)
    assert sent(transport) == ["alice: commands"]


def test_help_context_exists_only_while_it_runs() -> None:
    with pytest.raises(RuntimeError, match="only while it runs"):
        _ = DefaultHelpCommand().context
    bot = Bot("!", intents=INTENTS, help_command=None)
    assert bot.help_command is None


def test_a_paginator_splits_lines_into_pages_that_fit() -> None:
    pages = Paginator(max_size=20)
    pages.add_line("a" * 10)
    pages.add_line("b" * 10, empty=True)
    assert pages.pages == ["```\naaaaaaaaaa\n```", "```\nbbbbbbbbbb\n\n```"]
    assert len(pages) == len("```\naaaaaaaaaa\n```") + len("```\nbbbbbbbbbb\n\n")
    assert repr(pages) == "<Paginator pages=2 max_size=20>"
    with pytest.raises(RuntimeError, match="does not fit"):
        pages.add_line("c" * 13)
    pages.close_page()
    pages.clear()
    assert pages.pages == []
    # Each line counts the separator after it, so two two-letter words fill six characters.
    plain = Paginator(prefix=None, suffix=None, max_size=6, linesep=" ")
    for word in ("ab", "cd", "ef"):
        plain.add_line(word)
    assert plain.pages == ["ab cd", "ef"]


async def test_the_minimal_help_lists_commands_inline() -> None:
    bot, transport = await helped_bot()
    bot.help_command = MinimalHelpCommand()
    await say(bot, transport, "!help", replies=1)
    await say(bot, transport, "!help Tools", replies=1)
    await say(bot, transport, "!help tag", replies=1)
    await say(bot, transport, "!help calc", replies=1)
    bot_page, cog_page, group_page, command_page = sent(transport)
    assert bot_page == (
        "A test bot.\n\n"
        "Use `!help [command]` for more info on a command.\n\n"
        "__**Tools**__\n`calc` `tag`\n"
        "__**No Category**__\n`help` `ping`"
    )
    assert cog_page == (
        "Use `!help [command]` for more info on a command.\n\n"
        "Handy tools.\n\n"
        "__**Commands**__\n`!calc` — Add two numbers.\n`!tag` — Manage tags."
    )
    assert group_page == "`!tag`\n\nManage tags.\n\n__**Commands**__\n`!tag create` — Create a tag."
    assert (
        command_page
        == "`!calc <first> [second=1]`\n**Aliases:** c\n\nAdd two numbers.\n\nSecond defaults to one."
    )
