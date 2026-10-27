from typing import Annotated, ClassVar, Literal

import msgspec
import pytest

from shoal.commands import (
    BadFlagArgumentError,
    Context,
    FlagConverter,
    MissingFlagArgumentError,
    MissingRequiredFlagError,
    TooManyArgumentsError,
    TooManyFlagsError,
    flag,
)
from shoal.core.codec import encode_json
from tests.support.client import Recorder
from tests.support.commands import bot_started, context_in, errors_of, say
from tests.support.fakes import settle
from tests.support.interactions import command as slash
from tests.support.interactions import option, payload
from tests.support.models import GENERAL


class Options(FlagConverter):
    name: str
    count: int = flag(default=1, aliases=["n"], description="How many")
    tags: list[str] = []  # noqa: RUF012 - a flag's default, copied for each parse
    size: Literal["small", "large"] | None
    point: tuple[int, int] = (0, 0)
    words: tuple[str, ...] = ()
    weights: dict[str, int] = {}  # noqa: RUF012 - a flag's default, copied for each parse


class Dashed(FlagConverter, prefix="--", delimiter=" ", case_insensitive=True):
    topic: Annotated[str, flag(positional=True)]
    loud: bool = False


async def converted[F: FlagConverter](kind: type[F], text: str) -> F:
    bot, _ = await bot_started()
    return await kind.convert(context_in(bot), text)


async def test_flags_convert_each_kind_of_annotation() -> None:
    flags = await converted(
        Options,
        'name: Ada n: 3 tags: a tags: b point: 1 2 words: x "y z" weights: a 1 weights: b 2 weights: a 3',
    )
    assert (flags.name, flags.count, flags.tags, flags.size) == ("Ada", 3, ["a", "b"], None)
    assert (flags.point, flags.words, flags.weights) == ((1, 2), ("x", "y z"), {"a": 3, "b": 2})
    assert dict(flags)["count"] == 3
    assert repr(flags).startswith("<Options name='Ada' count=3")


async def test_left_out_flags_take_their_defaults_each_their_own() -> None:
    first = await converted(Options, "name: a")
    second = await converted(Options, "name: b")
    first.tags.append("changed")
    assert second.tags == []
    assert (first.count, first.size, first.point) == (1, None, (0, 0))


async def test_a_prefix_delimiter_case_and_positional_flag() -> None:
    flags = await converted(Dashed, "release notes --LOUD yes")
    assert (flags.topic, flags.loud) == ("release notes", True)
    assert Dashed.parse_flags("--topic x") == {"topic": ["x"]}


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("count: 2", MissingRequiredFlagError),
        ("name: ", MissingFlagArgumentError),
        ("name: a name: b", TooManyFlagsError),
        ("name: a count: many", BadFlagArgumentError),
        ("name: a point: 1", MissingFlagArgumentError),
        ("name: a size: medium", BadFlagArgumentError),
    ],
)
async def test_flags_refuse_what_they_cannot_read(text: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        await converted(Options, text)


async def test_a_flag_that_overrides_keeps_the_last_value() -> None:
    class Last(FlagConverter):
        mode: str = flag(default="a", override=True)

    assert (await converted(Last, "mode: b mode: c")).mode == "c"


def test_text_before_the_first_flag_is_refused_when_extra_is_not_ignored() -> None:
    assert Options.parse_flags("hello name: a") == {"name": ["a"]}
    with pytest.raises(TooManyArgumentsError):
        Options.parse_flags("hello name: a", ignore_extra=False)


def test_flags_are_inherited_and_can_be_redeclared() -> None:
    class More(Options):
        count: int = 5
        extra: bool = True

    assert list(More.get_flags()) == ["name", "count", "tags", "size", "point", "words", "weights", "extra"]
    assert More.get_flags()["count"].default == 5
    assert Options.get_flags()["count"].default == 1
    assert not More.is_constructible()


@pytest.mark.parametrize(
    ("make", "error", "match"),
    [
        (
            lambda: type("Spaced", (FlagConverter,), {"__annotations__": {"a": str}, "a": flag(name="a b")}),
            ValueError,
            "space",
        ),
        (
            lambda: type(
                "Same", (FlagConverter,), {"__annotations__": {"a": str, "b": str}, "b": flag(name="a")}
            ),
            TypeError,
            "twice",
        ),
        (
            lambda: type(
                "Two",
                (FlagConverter,),
                {
                    "__annotations__": {"a": str, "b": str},
                    "a": flag(positional=True),
                    "b": flag(positional=True),
                },
            ),
            TypeError,
            "one flag can be positional",
        ),
        (
            lambda: type("Odd", (FlagConverter,), {"__annotations__": {"a": set[str]}}),
            TypeError,
            "cannot hold|is not something",
        ),
    ],
)
def test_flag_classes_that_cannot_be_parsed_are_refused(
    make: object, error: type[Exception], match: str
) -> None:
    assert callable(make)
    with pytest.raises(error, match=match):
        make()


async def test_a_flags_parameter_takes_the_rest_of_the_message() -> None:
    bot, transport = await bot_started()
    events = Recorder(bot, "command_error")
    seen: list[tuple[str, int, bool]] = []

    class Optional(FlagConverter):
        word: str = "none"
        times: int = 1

    @bot.command()
    async def run(ctx: Context, first: int, flags: Optional) -> None:
        del ctx
        seen.append((flags.word, flags.times, first == 0))

    @bot.command()
    async def needs(ctx: Context, *, flags: Options) -> None:
        del ctx, flags

    await say(bot, transport, "!run 0 word: hi times: 2")
    await say(bot, transport, "!run 1")
    await say(bot, transport, "!needs")
    assert seen == [("hi", 2, True), ("none", 1, False)]
    [missing] = errors_of(events)
    assert type(missing).__name__ == "MissingRequiredArgumentError"


async def test_each_flag_is_its_own_option_in_a_hybrid_command() -> None:
    bot, transport = await bot_started()
    seen: list[object] = []

    class Ban(FlagConverter):
        reason: str = flag(default="No reason", description="Why")
        days: int = 1
        tags: list[str] = []  # noqa: RUF012 - a flag's default, copied for each parse

    @bot.hybrid_command()
    async def ban(ctx: Context, *, flags: Ban) -> None:
        seen.append(("slash" if ctx.interaction else "prefix", flags.reason, flags.days, flags.tags))

    await say(bot, transport, "!ban days: 3 reason: spam")
    await bot.process_interaction(payload(slash("ban", option("days", 4, 4), option("tags", "x"))))
    await settle()
    assert seen == [("prefix", "spam", 3, []), ("slash", "No reason", 4, ["x"])]
    options = msgspec.json.decode(encode_json(ban.app_command.to_payload()))["options"]
    assert [(entry["name"], entry["type"], entry["description"]) for entry in options] == [
        ("reason", 3, "Why"),
        ("days", 4, "…"),
        ("tags", 3, "…"),
    ]


async def test_converters_class_variables_and_context_defaults() -> None:
    def shout(text: str) -> str:
        return text.upper()

    async def channel_id(ctx: Context) -> int:
        return ctx.channel.id

    class Fancy(FlagConverter):
        LIMIT: ClassVar[int] = 3
        word: str = flag(default="hi", converter=shout)
        where: int = flag(default=channel_id)
        noted: Annotated[int, "a note, not a flag"] = 2

    assert "LIMIT" not in Fancy.get_flags()
    flags = await converted(Fancy, "word: hey")
    assert (flags.word, flags.where, flags.noted) == ("HEY", GENERAL, 2)
    assert Fancy.LIMIT == 3


async def test_options_must_give_every_required_flag() -> None:
    bot, _ = await bot_started()
    with pytest.raises(MissingRequiredFlagError):
        await Options.from_options(context_in(bot), {"count": 2}, ())
    made = await Options.from_options(context_in(bot), {"name": "Ada", "tags": "x"}, {"tags"})
    assert (made.name, made.tags) == ("Ada", ["x"])
