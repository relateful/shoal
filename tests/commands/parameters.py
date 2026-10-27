import enum
import inspect
from typing import Annotated, Literal, override

import pytest

from shoal import commands
from shoal.commands import (
    Author,
    Context,
    Converter,
    CurrentChannel,
    CurrentGuild,
    Greedy,
    ParameterOptions,
    Range,
    param,
)
from shoal.commands.errors import (
    BadArgumentError,
    BadBoolArgumentError,
    BadLiteralArgumentError,
    BadUnionArgumentError,
    ConversionError,
    NoPrivateMessageError,
    RangeError,
)
from shoal.commands.parameters import Parameter, converter_for, parameter_of, run_converters
from shoal.models.guild import Guild
from shoal.models.member import Member
from shoal.models.user import User
from tests.support.client import Recorder
from tests.support.commands import bot_started, context_in, errors_of, say
from tests.support.models import ALICE, GENERAL, GUILD


class Colour(enum.Enum):
    RED = "red"
    BLUE = 2


class Shout(Converter[str]):
    @override
    async def convert(self, ctx: Context, argument: str) -> str:
        del ctx
        return argument.upper()


def broken(argument: str) -> str:
    raise LookupError(argument)


async def reverse(argument: str) -> str:
    return argument[::-1]


async def convert(annotation: object, argument: str) -> object:
    bot, _ = await bot_started()
    converter, _, _ = converter_for("value", annotation)
    return await converter(context_in(bot), argument)


async def test_primitives_convert() -> None:
    assert await convert(int, "42") == 42
    assert await convert(float, "1.5") == 1.5
    assert await convert(str, "text") == "text"
    assert await convert(inspect.Parameter.empty, "plain") == "plain"
    with pytest.raises(BadArgumentError, match="not a whole number"):
        await convert(int, "4.2")


@pytest.mark.parametrize(
    ("word", "expected"), [("yes", True), ("ON", True), ("0", False), ("disable", False)]
)
async def test_booleans_read_the_usual_words(word: str, expected: bool) -> None:
    assert await convert(bool, word) is expected


async def test_other_words_are_not_booleans() -> None:
    with pytest.raises(BadBoolArgumentError):
        await convert(bool, "maybe")


async def test_literals_and_enums_match_case_insensitively() -> None:
    assert await convert(Literal["Red", "Blue"], "red") == "Red"
    assert await convert(Literal[1, 2], "2") == 2
    assert await convert(Literal[True], "true") is True
    with pytest.raises(BadLiteralArgumentError, match="must be one of 1, 2"):
        await convert(Literal[1, 2], "three")
    assert await convert(Colour, "RED") is Colour.RED
    assert await convert(Colour, "2") is Colour.BLUE
    with pytest.raises(BadArgumentError, match="not a Colour"):
        await convert(Colour, "green")


async def test_ranges_bound_numbers_and_lengths() -> None:
    assert await convert(Range[int, 1, 5], "3") == 3
    with pytest.raises(RangeError, match="outside the range 1 to 5"):
        await convert(Range[int, 1, 5], "9")
    with pytest.raises(RangeError):
        await convert(Range[str, None, 3], "long")


async def test_unions_try_each_type_in_order() -> None:
    assert await convert(int | float, "1.5") == 1.5
    with pytest.raises(BadUnionArgumentError, match="could not convert 'value'"):
        await convert(int | float, "x")


async def test_custom_converters_and_functions() -> None:
    assert await convert(Shout, "hi") == "HI"
    assert await convert(Shout(), "hi") == "HI"
    assert await convert(reverse, "abc") == "cba"
    assert await convert(Annotated[str, Shout], "hey") == "HEY"
    assert await convert(Annotated[int, "a note"], "7") == 7
    with pytest.raises(ConversionError, match="LookupError"):
        await convert(broken, "x")


def test_optional_and_greedy_parameters_are_marked() -> None:
    _, optional, greedy = converter_for("value", int | None)
    assert (optional, greedy) == (True, False)
    _, optional, greedy = converter_for("value", Greedy[int])
    assert (optional, greedy) == (False, True)
    with pytest.raises(TypeError, match="Greedy\\[Optional"):
        converter_for("value", Greedy[int | None])


def test_types_that_cannot_hold_an_argument_are_refused() -> None:
    with pytest.raises(TypeError, match="cannot convert"):
        converter_for("value", list[int])


KINDS = {
    "word": inspect.Parameter.POSITIONAL_OR_KEYWORD,
    "rest": inspect.Parameter.KEYWORD_ONLY,
    "every": inspect.Parameter.VAR_POSITIONAL,
}


def parameter(
    name: str,
    kind: Literal["word", "rest", "every"],
    annotation: object,
    default: object = inspect.Parameter.empty,
) -> Parameter:
    item = inspect.Parameter(name, KINDS[kind], annotation=annotation, default=default)
    return parameter_of(item, annotation)


def test_help_shows_each_kind_of_parameter() -> None:
    assert parameter("member", "word", int).usage() == "<member>"
    assert parameter("days", "word", int, 1).usage() == "[days=1]"
    assert parameter("reason", "word", str | None, None).usage() == "[reason]"
    assert parameter("members", "every", int).usage() == "[members...]"
    rest = parameter("reason", "rest", str)
    assert rest.consumes_rest
    assert rest.required
    assert not parameter("members", "every", int).has_default


async def test_param_defaults_are_worked_out_from_the_context() -> None:
    bot, transport = await bot_started()
    events = Recorder(bot, "command_error")
    seen: list[object] = []

    async def doubled(ctx: Context) -> int:
        return ctx.author.id * 2

    @bot.command()
    async def who(
        ctx: Context,
        person: Member | User = Author,
        twice: int = param(default=doubled, displayed_default="<twice your ID>"),
    ) -> None:
        del ctx
        seen.extend([person.id, twice])

    @bot.command()
    async def here(ctx: Context, guild: Guild = CurrentGuild, channel: object = CurrentChannel) -> None:
        del ctx
        seen.extend([guild.id, getattr(channel, "id", None)])

    await say(bot, transport, "!who")
    # A word that is not a member is left for the next parameter, and the author used.
    transport.queue(200, [])  # the member search finds nobody called "21"
    await say(bot, transport, "!who 21")
    await say(bot, transport, "!here")
    await say(bot, transport, "!here", in_guild=False)
    assert seen == [ALICE, ALICE * 2, ALICE, 21, GUILD, GENERAL]
    [error] = errors_of(events)
    assert isinstance(error, NoPrivateMessageError)
    assert who.signature == "[person=<you>] [twice=<twice your ID>]"


async def test_param_replaces_the_converter_and_describes_the_parameter() -> None:
    bot, transport = await bot_started()
    seen: list[object] = []

    def shout(text: str) -> str:
        return text.upper()

    @bot.command()
    async def loud(
        ctx: Context,
        word: str = param(converter=shout, default="hey", description="What to shout"),
        *,
        rest: Annotated[str, param(description="The rest", displayed_name="more")],
    ) -> None:
        del ctx
        seen.extend([word, rest])

    await say(bot, transport, "!loud hi there you")
    assert seen == ["HI", "there you"]
    word, rest = loud.params
    assert (word.description, rest.description) == ("What to shout", "The rest")
    assert loud.signature == "[word=hey] <more>"


def test_parameter_is_another_name_for_param() -> None:
    assert commands.parameter is param
    assert isinstance(param(description="x"), ParameterOptions)


async def test_run_converters_converts_as_an_annotation_would() -> None:
    bot, _ = await bot_started()
    ctx = context_in(bot)
    assert await run_converters(ctx, int, "42") == 42
    assert await run_converters(ctx, Literal["a", "b"], "B") == "b"
    with pytest.raises(BadArgumentError):
        await run_converters(ctx, int, "many")
    assert commands.AutoShardedBot is commands.Bot
