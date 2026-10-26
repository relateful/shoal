from typing import override

import pytest

from shoal import app_commands, commands
from shoal.client.interaction import Interaction
from shoal.commands import Cog, Context
from shoal.commands.core import CommandRegistrationError
from shoal.commands.errors import CheckFailureError
from shoal.models.member import Member
from tests.support.client import feed
from tests.support.commands import bot_started, say, sent
from tests.support.fakes import settle
from tests.support.interactions import Json, payload
from tests.support.interactions import command as slash
from tests.support.models import BOB, GUILD, member


class Greetings(Cog, name="Greetings"):
    """Saying hello."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    @commands.command()
    async def hello(self, ctx: Context, name: str = "there") -> None:
        self.calls.append(f"hello {name}")
        await ctx.send(f"Hello {name}")

    @commands.group(invoke_without_command=True)
    async def tag(self, ctx: Context) -> None:
        del ctx
        self.calls.append("tag")

    @tag.command()
    async def show(self, ctx: Context, name: str) -> None:
        del ctx
        self.calls.append(f"show {name}")

    @app_commands.command()
    async def wave(self, interaction: Interaction) -> None:
        del interaction
        self.calls.append("wave")

    @Cog.listener()
    async def on_member_join(self, joined: Member) -> None:
        self.calls.append(f"joined {joined.name}")

    @Cog.listener("member_join")
    async def also_on_join(self, joined: Member) -> None:
        self.calls.append(f"also {joined.name}")

    @override
    async def cog_load(self) -> None:
        self.calls.append("load")

    @override
    async def cog_unload(self) -> None:
        self.calls.append("unload")

    @override
    async def cog_before_invoke(self, ctx: Context) -> None:
        del ctx
        self.calls.append("before")

    @override
    async def cog_after_invoke(self, ctx: Context) -> None:
        del ctx
        self.calls.append("after")


async def test_a_cog_adds_its_commands_slash_commands_and_listeners() -> None:
    bot, transport = await bot_started()
    cog = Greetings()
    await bot.add_cog(cog)
    assert bot.get_cog("Greetings") is cog
    assert cog.description == "Saying hello."
    assert [command.name for command in cog.get_commands()] == ["hello", "tag"]
    assert [command.name for command in cog.walk_commands()] == ["hello", "tag", "show"]
    assert [command.name for command in cog.get_app_commands()] == ["wave"]
    hello = bot.get_command("hello")
    assert hello is not None
    assert hello.cog is cog
    assert hello is not Greetings.hello
    assert hello.cog_name == "Greetings"
    await say(bot, transport, "!hello Ada", replies=1)
    await say(bot, transport, "!tag show faq")
    await say(bot, transport, "!tag")
    await bot.process_interaction(payload(slash("wave")))
    await feed(bot, "GUILD_MEMBER_ADD", member(BOB + 50, "newcomer") | {"guild_id": str(GUILD)})
    await settle()
    assert sent(transport) == ["Hello Ada"]
    assert cog.calls == [
        "load",
        "before",
        "hello Ada",
        "after",
        "before",
        "show faq",
        "after",
        "before",
        "tag",
        "after",
        "wave",
        "joined newcomer",
        "also newcomer",
    ]
    assert repr(cog) == "<Greetings name='Greetings'>"


async def test_removing_a_cog_takes_everything_back() -> None:
    bot, transport = await bot_started()
    cog = Greetings()
    await bot.add_cog(cog)
    assert await bot.remove_cog("Greetings") is cog
    assert await bot.remove_cog("Greetings") is None
    assert bot.get_command("hello") is None
    assert bot.tree.get_command("wave") is None
    await feed(bot, "GUILD_MEMBER_ADD", member(BOB + 51, "late") | {"guild_id": str(GUILD)})
    await settle()
    assert cog.calls == ["load", "unload"]
    await say(bot, transport, "!hello")
    assert sent(transport) == []


class Tags(Cog):
    tags = app_commands.Group(name="tags", description="Saved answers.")

    def __init__(self, label: str) -> None:
        self.label = label
        self.shown: list[str] = []

    @tags.command(description="Show a tag.")
    async def show(self, interaction: Interaction, name: str) -> None:
        del interaction
        self.shown.append(f"{self.label} {name}")


async def test_a_group_made_in_a_cog_body_is_one_command_with_bound_subcommands() -> None:
    bot, _ = await bot_started()
    first, second = Tags("first"), Tags("second")
    assert [command.name for command in first.get_app_commands()] == ["tags"]
    await bot.add_cog(first)
    assert first.tags is not Tags.tags
    assert [command.name for command in bot.tree.get_commands()] == ["tags"]
    option: Json = {"type": 1, "name": "show", "options": [{"type": 3, "name": "name", "value": "faq"}]}
    await bot.process_interaction(payload(slash("tags", option)))
    await settle()
    assert first.shown == ["first faq"]
    await bot.remove_cog("Tags")
    await bot.add_cog(second)
    await bot.process_interaction(payload(slash("tags", option)))
    await settle()
    assert second.shown == ["second faq"]
    assert first.shown == ["first faq"]
    assert Tags.tags.get_command("show") is not second.tags.get_command("show")


class GuildOnly(Cog):
    @app_commands.command(description="Only here.")
    @app_commands.guilds(GUILD)
    async def local(self, interaction: Interaction) -> None:
        del interaction


async def test_removing_a_cog_takes_its_guild_commands_back_too() -> None:
    bot, _ = await bot_started()
    await bot.add_cog(GuildOnly())
    assert [command.name for command in bot.tree.get_commands(guild=GUILD)] == ["local"]
    await bot.remove_cog("GuildOnly")
    assert bot.tree.get_all_commands() == []
    await bot.add_cog(GuildOnly())
    assert [command.name for command in bot.tree.get_commands(guild=GUILD)] == ["local"]


async def test_a_slash_name_clash_leaves_nothing_of_the_cog() -> None:
    bot, transport = await bot_started()

    @bot.tree.command(description="Taken.")
    async def wave(interaction: Interaction) -> None:
        del interaction

    cog = Greetings()
    with pytest.raises(ValueError, match="already registered"):
        await bot.add_cog(cog)
    assert bot.get_cog("Greetings") is None
    assert bot.get_command("hello") is None
    assert bot.tree.get_commands() == [wave]
    await feed(bot, "GUILD_MEMBER_ADD", member(BOB + 52, "nobody") | {"guild_id": str(GUILD)})
    await settle()
    assert cog.calls == ["load", "unload"]
    await say(bot, transport, "!hello")
    assert sent(transport) == []


async def test_cogs_are_added_once_unless_replaced() -> None:
    bot, _ = await bot_started()
    await bot.add_cog(Greetings())
    with pytest.raises(ValueError, match="already added"):
        await bot.add_cog(Greetings())
    replacement = Greetings()
    await bot.add_cog(replacement, override=True)
    assert bot.cogs == {"Greetings": replacement}


async def test_a_name_clash_leaves_nothing_of_the_cog() -> None:
    bot, _ = await bot_started()

    @bot.command()
    async def tag(ctx: Context) -> None:
        del ctx

    cog = Greetings()
    with pytest.raises(CommandRegistrationError):
        await bot.add_cog(cog)
    assert bot.get_command("hello") is None
    assert bot.get_cog("Greetings") is None
    assert cog.calls == ["load", "unload"]


class Guarded(Cog):
    def __init__(self) -> None:
        self.errors: list[Exception] = []
        self.slash_errors: list[Exception] = []

    @commands.command()
    async def secret(self, ctx: Context) -> None:
        del ctx

    @app_commands.command()
    async def hidden(self, interaction: Interaction) -> None:
        del interaction

    @override
    def cog_check(self, ctx: Context) -> bool:
        return ctx.author.id == BOB

    @override
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        del ctx
        self.errors.append(error)

    @override
    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == BOB

    @override
    async def cog_app_command_error(self, interaction: Interaction, error: Exception) -> None:
        del interaction
        self.slash_errors.append(error)


async def test_cog_checks_and_error_handlers_cover_both_kinds_of_command() -> None:
    bot, transport = await bot_started()
    cog = Guarded()
    await bot.add_cog(cog)
    await say(bot, transport, "!secret")
    await bot.process_interaction(payload(slash("hidden")))
    await settle()
    [error] = cog.errors
    assert isinstance(error, CheckFailureError)
    [slash_error] = cog.slash_errors
    assert isinstance(slash_error, app_commands.CheckFailureError)


def test_context_menus_cannot_live_in_a_cog() -> None:
    async def inspect(interaction: Interaction, target: Member) -> None:
        del interaction, target

    with pytest.raises(TypeError, match="context menus"):
        type("Menus", (Cog,), {"inspect": app_commands.context_menu(name="Inspect")(inspect)})


def test_listeners_need_an_event_name() -> None:
    async def handle(member: Member) -> None:
        del member

    with pytest.raises(TypeError, match="named after its event"):
        Cog.listener()(handle)


class Moderation(commands.GroupCog, group_description="Keep order"):
    def __init__(self) -> None:
        self.calls: list[str] = []

    @app_commands.command()
    async def warn(self, interaction: Interaction) -> None:
        del interaction
        self.calls.append("warn")

    @commands.hybrid_command()
    async def mute(self, ctx: Context) -> None:
        """Mute someone."""
        del ctx
        self.calls.append("mute")


async def test_a_group_cog_puts_its_slash_commands_in_one_group() -> None:
    bot, transport = await bot_started()
    with pytest.raises(RuntimeError, match="added to a bot"):
        _ = Moderation().app_command
    cog = Moderation()
    await bot.add_cog(cog)
    group = cog.app_command
    assert (group.name, group.description) == ("moderation", "Keep order")
    assert [command.name for command in bot.tree.get_commands()] == ["moderation"]
    assert sorted(command.name for command in group.commands) == ["mute", "warn"]
    await bot.process_interaction(payload(slash("moderation", {"name": "warn", "type": 1, "options": []})))
    await bot.process_interaction(payload(slash("moderation", {"name": "mute", "type": 1, "options": []})))
    await say(bot, transport, "!mute")
    await settle()
    assert cog.calls == ["warn", "mute", "mute"]
    await bot.remove_cog("Moderation")
    assert bot.tree.get_commands() == []
    assert bot.get_command("mute") is None


def test_a_group_cog_names_its_group_from_its_keywords() -> None:
    class Server(commands.GroupCog, name="Server Tools", group_name="server", group_nsfw=True):
        """Manage the server."""

    assert (Server.__cog_group_name__, Server.__cog_group_description__) == ("server", "Manage the server.")
    assert Server.__cog_group_nsfw__

    class Plain(commands.GroupCog, name="Plain Tools"):
        pass

    assert (Plain.__cog_group_name__, Plain.__cog_group_description__) == ("plain-tools", "…")
