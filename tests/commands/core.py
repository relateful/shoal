import asyncio
from typing import cast

import pytest

from shoal.commands import (
    BucketType,
    Command,
    Context,
    Greedy,
    Group,
    MaxConcurrency,
    command,
    cooldown,
    group,
    max_concurrency,
)
from shoal.commands.core import CommandCallback, CommandRegistrationError
from shoal.commands.errors import (
    BadArgumentError,
    CheckFailureError,
    CommandInvokeError,
    CommandOnCooldownError,
    DisabledCommandError,
    MaxConcurrencyReachedError,
    MissingRequiredArgumentError,
    TooManyArgumentsError,
)
from tests.support.client import Recorder
from tests.support.commands import bot_started, context_in, say
from tests.support.fakes import settle
from tests.support.models import ALICE, BOB, GUILD

NO_NUMBERS: Greedy[int] = Greedy()
"""No numbers: the default of a greedy parameter that may match none."""


async def errors_of(events: Recorder) -> list[Exception]:
    return [
        args[1] for name, args in events.seen if name == "command_error" and isinstance(args[1], Exception)
    ]


async def test_words_quotes_optional_greedy_and_the_rest() -> None:
    bot, transport = await bot_started()
    seen: list[object] = []

    @bot.command()
    async def tag(
        ctx: Context, count: int | None, numbers: Greedy[int] = NO_NUMBERS, name: str = "", *, body: str = ""
    ) -> None:
        del ctx
        seen.append((count, numbers, name, body))

    await say(bot, transport, '!tag "my tag"  hello  world ')
    await say(bot, transport, "!tag 3 1 2 x the rest")
    await say(bot, transport, "!tag 7 y")
    assert seen == [(None, [], "my tag", "hello  world"), (3, [1, 2], "x", "the rest"), (7, [], "y", "")]


async def test_star_args_take_every_word_and_raw_rest_keeps_spaces() -> None:
    bot, transport = await bot_started()
    seen: list[object] = []

    @bot.command()
    async def total(ctx: Context, *numbers: int) -> None:
        del ctx
        seen.append(sum(numbers))

    @bot.command(rest_is_raw=True)
    async def echo(ctx: Context, *, text: str) -> None:
        del ctx
        seen.append(text)

    await say(bot, transport, "!total 1 2 3")
    await say(bot, transport, "!echo   spaced ")
    assert seen == [6, "spaced "]


async def test_argument_errors_reach_the_error_event() -> None:
    bot, transport = await bot_started()
    events = Recorder(bot, "command_error")

    @bot.command(ignore_extra=False)
    async def add(ctx: Context, first: int, second: int) -> None:
        del ctx, first, second

    @bot.command()
    async def greedy(ctx: Context, numbers: Greedy[int]) -> None:
        del ctx, numbers

    await say(bot, transport, "!add 1")
    await say(bot, transport, "!add 1 x")
    await say(bot, transport, "!add 1 2 3")
    await say(bot, transport, "!greedy x")
    first, second, third, fourth = await errors_of(events)
    assert isinstance(first, MissingRequiredArgumentError)
    assert first.parameter.name == "second"
    assert isinstance(second, BadArgumentError)
    assert isinstance(third, TooManyArgumentsError)
    assert third.extra == "3"
    assert isinstance(fourth, MissingRequiredArgumentError)


async def test_callback_errors_are_wrapped_and_handled_by_the_command() -> None:
    bot, transport = await bot_started()
    handled: list[Exception] = []

    @bot.command()
    async def fail(ctx: Context) -> None:
        del ctx
        msg = "no"
        raise ValueError(msg)

    @fail.error
    async def on_fail(ctx: Context, error: Exception) -> None:
        del ctx
        handled.append(error)

    await say(bot, transport, "!fail")
    [error] = handled
    assert isinstance(error, CommandInvokeError)
    assert isinstance(error.original, ValueError)
    assert fail.error_handler is on_fail


async def test_groups_run_their_subcommands() -> None:
    bot, transport = await bot_started()
    order: list[str] = []

    @bot.group()
    async def tag(ctx: Context) -> None:
        order.append(f"tag sub={ctx.invoked_subcommand.name if ctx.invoked_subcommand else None}")

    @tag.command()
    async def create(ctx: Context, name: str) -> None:
        order.append(f"create {name} via {ctx.invoked_parents}")

    @bot.group(invoke_without_command=True, case_insensitive=True)
    async def settings(ctx: Context) -> None:
        order.append(f"settings passed={ctx.subcommand_passed}")

    @settings.group()
    async def roles(ctx: Context) -> None:
        del ctx
        order.append("roles")

    @roles.command(name="list")
    async def list_roles(ctx: Context) -> None:
        del ctx
        order.append("list")

    await say(bot, transport, "!tag create one")
    await say(bot, transport, "!tag")
    await say(bot, transport, "!settings")
    await say(bot, transport, "!settings ROLES list")
    await say(bot, transport, "!settings other")
    assert order == [
        "tag sub=create",
        "create one via ['tag']",
        "tag sub=None",
        "settings passed=None",
        "roles",
        "list",
        "settings passed=other",
    ]
    assert bot.get_command("settings roles list") is list_roles
    assert list_roles.qualified_name == "settings roles list"
    assert list_roles.root_parent is settings
    assert [found.name for found in settings.walk_commands()] == ["roles", "list"]
    assert settings.remove_command("roles") is roles
    assert settings.get_command("roles") is None
    assert bot.get_command("ping missing") is None
    assert bot.get_command("tag create extra") is None


async def test_checks_disabled_commands_and_hooks() -> None:
    bot, transport = await bot_started()
    events = Recorder(bot, "command_error")
    order: list[str] = []

    @bot.command()
    async def guarded(ctx: Context) -> None:
        del ctx
        order.append("run")

    guarded.add_check(lambda ctx: ctx.author.id == ALICE)

    @guarded.before_invoke
    async def before(ctx: Context) -> None:
        del ctx
        order.append("before")

    @guarded.after_invoke
    async def after(ctx: Context) -> None:
        del ctx
        order.append("after")

    await say(bot, transport, "!guarded")
    await say(bot, transport, "!guarded", author=BOB)
    guarded.enabled = False
    await say(bot, transport, "!guarded")
    assert order == ["before", "run", "after"]
    refused, disabled = await errors_of(events)
    assert isinstance(refused, CheckFailureError)
    assert isinstance(disabled, DisabledCommandError)


async def test_cooldowns_refuse_until_reset() -> None:
    bot, transport = await bot_started()
    events = Recorder(bot, "command_error")
    ran: list[int] = []

    @cooldown(1, 60.0, BucketType.USER)
    @bot.command()
    async def slow(ctx: Context) -> None:
        ran.append(ctx.author.id)

    await say(bot, transport, "!slow")
    await say(bot, transport, "!slow")
    await say(bot, transport, "!slow", author=BOB)
    [error] = await errors_of(events)
    assert isinstance(error, CommandOnCooldownError)
    ctx = context_in(bot)
    assert slow.retry_after(ctx) > 0
    slow.reset_cooldown(ctx)
    assert slow.retry_after(ctx) == 0.0
    assert ran == [ALICE, BOB]


async def test_asking_a_command_how_long_to_wait_keeps_the_uses() -> None:
    bot, transport = await bot_started()
    events = Recorder(bot, "command_error")

    @cooldown(2, 60.0, BucketType.USER)
    @bot.command()
    async def twice(ctx: Context) -> None:
        del ctx

    await say(bot, transport, "!twice")
    ctx = context_in(bot)
    assert twice.retry_after(ctx) == 0.0
    await say(bot, transport, "!twice")
    await say(bot, transport, "!twice")
    [error] = await errors_of(events)
    assert isinstance(error, CommandOnCooldownError)


async def test_max_concurrency_refuses_or_queues() -> None:
    bot, transport = await bot_started()
    events = Recorder(bot, "command_error")
    release = asyncio.Event()
    running: list[str] = []

    @max_concurrency(1, BucketType.DEFAULT)
    @bot.command()
    async def once(ctx: Context) -> None:
        del ctx
        running.append("once")
        await release.wait()

    first = asyncio.create_task(say(bot, transport, "!once"))
    await settle()
    await say(bot, transport, "!once")
    release.set()
    await first
    [error] = await errors_of(events)
    assert isinstance(error, MaxConcurrencyReachedError)
    assert running == ["once"]


async def test_a_waiting_concurrency_limit_queues_and_forgets_idle_keys() -> None:
    bot, _ = await bot_started()
    limit = MaxConcurrency(1, BucketType.CHANNEL, wait=True)
    ctx = context_in(bot)
    key = await limit.acquire(ctx)
    waiting = asyncio.create_task(limit.acquire(ctx))
    await settle()
    assert not waiting.done()
    limit.release(key)
    second = await waiting
    limit.release(second)
    limit.release(second)
    with pytest.raises(ValueError, match="at least 1"):
        max_concurrency(0)


async def test_bucket_keys() -> None:
    bot, _ = await bot_started()
    in_guild = context_in(bot)
    in_dm = context_in(bot, in_guild=False)
    assert BucketType.DEFAULT.key(in_guild) == 0
    assert BucketType.USER.key(in_guild) == ALICE
    assert BucketType.GUILD.key(in_guild) == GUILD
    assert BucketType.GUILD.key(in_dm) == ("user", ALICE)
    assert BucketType.CHANNEL.key(in_guild) == in_guild.channel.id
    assert BucketType.MEMBER.key(in_dm) == (None, ALICE)
    assert BucketType.CATEGORY.key(in_guild) == 40
    assert BucketType.ROLE.key(in_dm) == ("channel", in_dm.channel.id)


def test_commands_describe_themselves() -> None:
    async def ban(ctx: Context, member: int, days: int = 1, *, reason: str | None = None) -> None:
        """Ban someone.

        More detail here.
        """
        del ctx, member, days, reason

    made = command(aliases=["b"], brief="Ban")(ban)
    assert made.help == "Ban someone.\n\nMore detail here."
    assert made.short_doc == "Ban"
    assert made.signature == "<member> [days=1] [reason]"
    assert command(usage="<who>")(ban).signature == "<who>"
    assert command()(ban).short_doc == "Ban someone."
    assert repr(made) == "<Command name='ban'>"
    copied = made.copy()
    copied.aliases.append("c")
    assert made.aliases == ["b"]


def test_callbacks_are_checked_when_made() -> None:
    def blocking(ctx: Context) -> None:
        del ctx

    async def nothing() -> None:
        pass

    async def kwargs(ctx: Context, **options: str) -> None:
        del ctx, options

    async def positional(ctx: Context, value: str, /) -> None:
        del ctx, value

    async def two_rests(ctx: Context, *, one: str, two: str) -> None:
        del ctx, one, two

    async def after_star(ctx: Context, *words: str, reason: str) -> None:
        del ctx, words, reason

    async def defaulted_after_star(ctx: Context, *words: str, reason: str = "none") -> None:
        del ctx, words, reason

    with pytest.raises(TypeError, match="must be async"):
        Command(cast("CommandCallback", blocking))  # a sync callback, to prove it is refused
    for callback, match in (
        (nothing, "take the context"),
        (kwargs, "cannot hold"),
        (positional, "positional-only"),
        (two_rests, "only one keyword-only"),
        (after_star, r"reason after \*words needs a default"),
    ):
        with pytest.raises(TypeError, match=match):
            Command(callback)
    assert Command(defaulted_after_star).params[-1].name == "reason"


def test_groups_hold_unique_names() -> None:
    @group()
    async def parent(ctx: Context) -> None:
        del ctx

    @parent.command(aliases=["c"])
    async def child(ctx: Context) -> None:
        del ctx

    with pytest.raises(CommandRegistrationError):
        parent.add_command(Command(child.callback, name="c"))
    assert isinstance(parent, Group)
    assert parent.commands == [child]
    assert parent.copy().commands[0] is not child
