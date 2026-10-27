"""Flags: named arguments in any order, `!ban member: @Ada reason: spam days: 7`.

    class BanFlags(commands.FlagConverter):
        member: Member
        reason: str = "No reason"
        days: int = commands.flag(default=1, aliases=["d"], description="Days of messages to delete")

    @bot.command()
    async def ban(ctx, *, flags: BanFlags) -> None:
        await flags.member.ban(reason=flags.reason, delete_message_seconds=flags.days * 86_400)

Each flag is `name: value` by default; a class sets `prefix` (`--`) and `delimiter` (` `, `=`) as
keywords, and `case_insensitive`. A flags parameter takes the rest of the message. The annotation
sets how many values a flag takes: one, a list (`list[str]`, given again and again), the words of a
tuple (`tuple[int, int]`), or pairs for a dict. In a hybrid command each flag is its own option.
"""

import copy
import inspect
import re
import types
import typing
from collections.abc import Awaitable, Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import (
    TYPE_CHECKING,
    Annotated,
    ClassVar,
    Literal,
    Self,
    Union,
    cast,
    dataclass_transform,
    get_args,
    get_origin,
    overload,
)

from shoal.commands.errors import (
    BadFlagArgumentError,
    CommandError,
    MissingFlagArgumentError,
    MissingRequiredFlagError,
    TooManyArgumentsError,
    TooManyFlagsError,
)
from shoal.commands.parameters import NO_DEFAULT, converter_for
from shoal.commands.view import StringView

if TYPE_CHECKING:
    from shoal.commands.context import Context


@dataclass(frozen=True, slots=True)
class Flag:
    """One flag of a `FlagConverter`: its name and aliases, and how its values convert.

    `max_args` is how many times it can be given (negative: any number); `override` keeps the last
    values given instead of refusing extra ones. `positional` takes the text before the first flag.
    """

    name: str = ""
    aliases: tuple[str, ...] = ()
    attribute: str = ""
    """The attribute of the converter holding its value."""
    annotation: object = NO_DEFAULT
    default: object = NO_DEFAULT
    """A value, or a callable (or coroutine function) given the context."""
    max_args: int = 0
    """0 until chosen from the annotation."""
    override: bool | None = None
    """`None` until chosen from the annotation."""
    description: str | None = None
    positional: bool = False
    cast_to_dict: bool = False

    @property
    def required(self) -> bool:
        """Whether the flag must be given: it has no default."""
        return self.default is NO_DEFAULT


@overload
def flag[T](
    *,
    default: Callable[["Context"], Awaitable[T]],
    name: str | None = None,
    aliases: Sequence[str] = (),
    max_args: int | None = None,
    override: bool | None = None,
    converter: object = NO_DEFAULT,
    description: str | None = None,
    positional: bool = False,
) -> T: ...
@overload
def flag[T](
    *,
    default: Callable[["Context"], T],
    name: str | None = None,
    aliases: Sequence[str] = (),
    max_args: int | None = None,
    override: bool | None = None,
    converter: object = NO_DEFAULT,
    description: str | None = None,
    positional: bool = False,
) -> T: ...
@overload
def flag[T](
    *,
    default: T,
    name: str | None = None,
    aliases: Sequence[str] = (),
    max_args: int | None = None,
    override: bool | None = None,
    converter: object = NO_DEFAULT,
    description: str | None = None,
    positional: bool = False,
) -> T: ...
@overload
def flag(
    *,
    name: str | None = None,
    aliases: Sequence[str] = (),
    max_args: int | None = None,
    override: bool | None = None,
    converter: object = NO_DEFAULT,
    description: str | None = None,
    positional: bool = False,
) -> Flag: ...
def flag(
    *,
    default: object = NO_DEFAULT,
    name: str | None = None,
    aliases: Sequence[str] = (),
    max_args: int | None = None,
    override: bool | None = None,
    converter: object = NO_DEFAULT,
    description: str | None = None,
    positional: bool = False,
) -> object:
    """Details of a flag its annotation cannot give; pass the result as the attribute's value.

    `name` is how it is written (the attribute's name by default) and `aliases` other ways to write
    it. `default` is a value or a callable given the context. `max_args` and `override` change how
    repeated values are taken; `converter` replaces the annotation's conversion. `description`
    describes it as a hybrid command's option. `positional` makes it take the text before the first
    flag (one flag at most). Without a default, annotate with `Annotated[T, flag(...)]` instead, which
    type checkers accept.
    """
    return Flag(
        name=name or "",
        aliases=tuple(aliases),
        annotation=converter,
        default=default,
        max_args=max_args or 0,
        override=override,
        description=description,
        positional=positional,
    )


@dataclass_transform(kw_only_default=True, field_specifiers=(flag,))
class FlagConverter:
    """A command parameter of named flags, declared as annotated class attributes.

    Set `prefix`, `delimiter` (`:` by default) and `case_insensitive` as class keywords. An instance
    holds each flag's value as an attribute, and iterates as `(name, value)` pairs.
    """

    # Each subclass's flags are attributes it declares; they live in the instance's __dict__.
    __slots__ = ("__dict__",)

    __commands_flags__: ClassVar[dict[str, Flag]] = {}
    """The flags by name, casefolded when case-insensitive."""
    __commands_flag_aliases__: ClassVar[dict[str, str]] = {}
    """Each alias's flag name, casefolded when case-insensitive."""
    __commands_flag_pattern__: ClassVar[re.Pattern[str]] = re.compile(r"(?!)")
    __commands_flag_positional__: ClassVar[Flag | None] = None
    __commands_flag_prefix__: ClassVar[str] = ""
    __commands_flag_delimiter__: ClassVar[str] = ":"
    __commands_flag_case_insensitive__: ClassVar[bool] = False

    @typing.override
    def __init_subclass__(
        cls, *, prefix: str | None = None, delimiter: str | None = None, case_insensitive: bool | None = None
    ) -> None:
        """Read the class's flags from its annotations; a base class's flags are inherited.

        Raises:
            TypeError: Two flags (or aliases) share a name, two flags are positional, or an
                annotation is not one a flag can hold.
            ValueError: A flag name is empty, or has a space, a backslash, the prefix or the delimiter.
        """
        super().__init_subclass__()
        if prefix is not None:
            cls.__commands_flag_prefix__ = prefix
        if delimiter is not None:
            cls.__commands_flag_delimiter__ = delimiter
        if case_insensitive is not None:
            cls.__commands_flag_case_insensitive__ = case_insensitive
        insensitive = cls.__commands_flag_case_insensitive__
        flags = {found.attribute: found for found in cls.__commands_flags__.values()}
        hints = typing.get_type_hints(cls, include_extras=True)
        for attribute in inspect.get_annotations(cls):
            if get_origin(hints[attribute]) is ClassVar:
                continue
            value = vars(cls).get(attribute, NO_DEFAULT)
            if attribute in vars(cls):
                # The class holds the defaults in its flags; instances hold the values.
                delattr(cls, attribute)
            flags[attribute] = _declared(attribute, hints[attribute], value)
        _check(
            flags.values(),
            cls.__commands_flag_prefix__,
            cls.__commands_flag_delimiter__,
            insensitive=insensitive,
        )
        cls.__commands_flags__ = {_key(found.name, insensitive): found for found in flags.values()}
        cls.__commands_flag_aliases__ = {
            _key(alias, insensitive): _key(found.name, insensitive)
            for found in flags.values()
            for alias in found.aliases
        }
        cls.__commands_flag_positional__ = next((found for found in flags.values() if found.positional), None)
        written = sorted(
            (re.escape(name) for found in flags.values() for name in (found.name, *found.aliases)),
            key=len,
            reverse=True,
        )
        cls.__commands_flag_pattern__ = re.compile(
            f"{re.escape(cls.__commands_flag_prefix__)}(?P<flag>{'|'.join(written) or '(?!)'})"
            f"{re.escape(cls.__commands_flag_delimiter__)}",
            re.IGNORECASE if insensitive else 0,
        )

    @classmethod
    def get_flags(cls) -> dict[str, Flag]:
        """The flags, by name."""
        return {found.name: found for found in cls.__commands_flags__.values()}

    @classmethod
    def is_constructible(cls) -> bool:
        """Whether every flag has a default, so the converter can be made without any being given."""
        return all(not found.required for found in cls.__commands_flags__.values())

    @classmethod
    async def default_for(cls, ctx: "Context") -> Self:
        """The converter with every flag at its default (all must have one)."""
        made = cls.__new__(cls)
        for found in cls.__commands_flags__.values():
            setattr(made, found.attribute, await _default(found, ctx))
        return made

    @classmethod
    def parse_flags(cls, argument: str, *, ignore_extra: bool = True) -> dict[str, list[str]]:
        """The texts given for each flag, by name (casefolded when case-insensitive), unconverted.

        Raises:
            MissingFlagArgumentError: A flag was given without a value.
            TooManyArgumentsError: Text before the first flag, without a positional flag to take it,
                and `ignore_extra` is off.
        """
        insensitive = cls.__commands_flag_case_insensitive__
        values: dict[str, list[str]] = {}
        matches = list(cls.__commands_flag_pattern__.finditer(argument))
        before = argument[: matches[0].start() if matches else len(argument)].strip()
        positional = cls.__commands_flag_positional__
        if positional is not None and before:
            values[_key(positional.name, insensitive)] = [before]
        elif before and not ignore_extra:
            raise TooManyArgumentsError(before)
        for index, match in enumerate(matches):
            written = _key(match["flag"], insensitive)
            key = cls.__commands_flag_aliases__.get(written, written)
            end = matches[index + 1].start() if index + 1 < len(matches) else len(argument)
            value = argument[match.end() : end].strip()
            if not value:
                raise MissingFlagArgumentError(cls.__commands_flags__[key])
            values.setdefault(key, []).append(value)
        return values

    @classmethod
    async def convert(cls, ctx: "Context", argument: str) -> Self:
        """The converter with each flag's value converted from `argument`.

        Raises:
            FlagError: A flag is missing, given too often, given empty, or does not convert.
            TooManyArgumentsError: Text that is no flag was given, and the command does not ignore extra.
        """
        ignore_extra = ctx.command.ignore_extra if ctx.command is not None else True
        given = cls.parse_flags(argument, ignore_extra=ignore_extra)
        made = cls.__new__(cls)
        for key, found in cls.__commands_flags__.items():
            texts = given.get(key)
            if texts is None:
                if found.required:
                    raise MissingRequiredFlagError(found)
                setattr(made, found.attribute, await _default(found, ctx))
            else:
                setattr(made, found.attribute, await _values(ctx, found, texts))
        return made

    @classmethod
    async def from_options(cls, ctx: "Context", options: Mapping[str, object], text: Collection[str]) -> Self:
        """The converter from a slash command's options, one per flag, by flag name.

        Options in `text` are text to convert as a prefix command would; the rest Discord already
        converted. A flag left out takes its default.

        Raises:
            FlagError: A required flag was left out, or a text option does not convert.
        """
        made = cls.__new__(cls)
        for found in cls.__commands_flags__.values():
            if found.name not in options:
                if found.required:
                    raise MissingRequiredFlagError(found)
                value: object = await _default(found, ctx)
            else:
                value = options[found.name]
                if found.name in text and isinstance(value, str):
                    value = await _values(ctx, found, [value])
            setattr(made, found.attribute, value)
        return made

    def __iter__(self) -> Iterator[tuple[str, object]]:
        """Each flag's name and value."""
        for found in type(self).__commands_flags__.values():
            yield found.name, getattr(self, found.attribute)

    @typing.override
    def __repr__(self) -> str:
        shown = " ".join(f"{name}={value!r}" for name, value in self)
        return f"<{type(self).__name__} {shown}>"


def _key(name: str, insensitive: bool) -> str:  # noqa: FBT001 - the class's setting, passed on
    return name.casefold() if insensitive else name


def _declared(attribute: str, annotation: object, value: object) -> Flag:
    """The flag an attribute declares, with what its annotation implies filled in.

    Raises:
        TypeError: The annotation is not one a flag can hold.
    """
    details = value if isinstance(value, Flag) else Flag(default=value)
    if get_origin(annotation) is Annotated:
        inner, *extras = get_args(annotation)
        found = next((extra for extra in extras if isinstance(extra, Flag)), None)
        if found is not None:
            details = found if found.default is not NO_DEFAULT else replace(found, default=details.default)
            annotation = inner
    if details.annotation is not NO_DEFAULT:
        annotation = details.annotation
    default, max_args, override, cast_to_dict = details.default, details.max_args, details.override, False
    origin = get_origin(annotation)
    if origin in {list, dict}:
        # Given again and again; a dict's values are its pairs, the last given for a key winning.
        max_args = max_args or -1
        cast_to_dict = origin is dict
        override = cast_to_dict if override is None else override
    elif origin in {Union, types.UnionType} and type(None) in get_args(annotation):
        default = None if default is NO_DEFAULT else default
    elif origin not in {None, Union, types.UnionType, tuple, Literal, Annotated}:
        msg = f"flag {attribute!r}: {annotation!r} is not something a flag can hold"
        raise TypeError(msg)
    return replace(
        details,
        name=details.name or attribute,
        attribute=attribute,
        annotation=annotation,
        default=default,
        max_args=max_args or 1,
        override=bool(override),
        cast_to_dict=cast_to_dict,
    )


def _check(flags: typing.Iterable[Flag], prefix: str, delimiter: str, *, insensitive: bool) -> None:
    """Refuse names that cannot be parsed apart, and more than one positional flag.

    Raises:
        TypeError: Two flags (or aliases) share a name, or two flags are positional.
        ValueError: A name is empty, or has a space, a backslash, the prefix or the delimiter.
    """
    forbidden = {*prefix, *delimiter, "\\"}
    seen: set[str] = set()
    positional: list[str] = []
    for found in flags:
        if found.positional:
            positional.append(found.name)
        for name in (found.name, *found.aliases):
            if not name or any(character.isspace() or character in forbidden for character in name):
                msg = f"flag name {name!r} needs a character, and no space, backslash, prefix or delimiter"
                raise ValueError(msg)
            if _key(name, insensitive) in seen:
                msg = f"flag name or alias {name!r} is used twice"
                raise TypeError(msg)
            seen.add(_key(name, insensitive))
    if len(positional) > 1:
        msg = f"only one flag can be positional, not {positional}"
        raise TypeError(msg)


async def _default(found: Flag, ctx: "Context") -> object:
    """The flag's default for `ctx`; a list, dict or set default is copied, so no two share it."""
    if callable(found.default):
        value = found.default(ctx)
        return await value if inspect.isawaitable(value) else value
    # By exact type, which keeps it an object (isinstance would leave list[Unknown]).
    if type(found.default) in {list, dict, set}:
        return copy.copy(found.default)
    return found.default


async def _values(ctx: "Context", found: Flag, texts: list[str]) -> object:
    """A given flag's value: one converted text, or a list (or dict) of them.

    Raises:
        TooManyFlagsError: It was given more often than it takes, without `override`.
    """
    if 0 < found.max_args < len(texts):
        if not found.override:
            raise TooManyFlagsError(found, texts)
        texts = texts[-found.max_args :]
    if found.max_args == 1:
        return await _convert_one(ctx, found, texts[0])
    converted = [await _convert_one(ctx, found, text) for text in texts]
    if found.cast_to_dict:
        # A dict flag's values are (key, value) tuples, from its two types.
        return dict(cast("list[tuple[object, object]]", converted))
    return converted


async def _convert_one(ctx: "Context", found: Flag, text: str) -> object:
    """One value of `found`: a converted text, or the converted words of a tuple or a dict pair."""
    annotation = found.annotation
    origin = get_origin(annotation)
    if origin is list:
        [annotation] = get_args(annotation)
        origin = get_origin(annotation)
    kinds: tuple[object, ...] = get_args(annotation) if origin in {dict, tuple} else ()
    if origin is tuple and len(kinds) == 2 and kinds[1] is Ellipsis:  # noqa: PLR2004 - tuple[T, ...]
        return tuple([await _converted(ctx, found, kinds[0], word) for word in _words(text)])
    if origin in {dict, tuple}:
        words = _words(text)
        if len(words) != len(kinds):
            raise MissingFlagArgumentError(found)
        return tuple(
            [await _converted(ctx, found, kind, word) for kind, word in zip(kinds, words, strict=True)]
        )
    return await _converted(ctx, found, annotation, text)


async def _converted(ctx: "Context", found: Flag, annotation: object, text: str) -> object:
    convert = converter_for(found.name, annotation)[0]
    try:
        return await convert(ctx, text)
    except CommandError as error:
        raise BadFlagArgumentError(found, text, error) from error


def _words(text: str) -> list[str]:
    """The words of `text`, quotes keeping words together as in command arguments."""
    view = StringView(text)
    words: list[str] = []
    while True:
        view.skip_ws()
        word = view.get_quoted_word()
        if word is None:
            return words
        words.append(word)
