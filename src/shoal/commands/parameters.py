"""A prefix command's parameters, from its callback's signature, and how each converts its text.

    async def ban(ctx, member: Member, days: Range[int, 0, 7] = 1, *, reason: str | None = None)

`member` takes one word (or quoted text), `days` one more if it converts, and `reason` the rest of
the message. `Optional[T]` (`T | None`) leaves the word for the next parameter when it does not
convert; `Greedy[T]` takes as many words as convert; `*args` takes every word left.
"""

import enum
import inspect
import types
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Final, Literal, Union, cast, get_args, get_origin

from shoal.app_commands.models import RangeSpec
from shoal.commands.converters import BUILT_IN, Converter, ConvertFunction
from shoal.commands.errors import (
    BadArgumentError,
    BadLiteralArgumentError,
    BadUnionArgumentError,
    CommandError,
    ConversionError,
    RangeError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from shoal.commands.context import Context

NO_DEFAULT: Final = inspect.Parameter.empty
"""The default of a parameter that has none."""


type ArgumentKind = Literal["word", "rest", "every_word"]
"""What a parameter takes: one word (or quoted text), the rest of the message (after `*`), or every
word left (`*args`)."""


class Greedy[T](list[T]):
    """`Greedy[int]`: as many words as convert to `int`, as a list; the first that does not is left.

    Only meaningful as an annotation.
    """

    __slots__ = ()


@dataclass(slots=True)
class Parameter:
    """One parameter of a prefix command, after the context."""

    name: str
    kind: ArgumentKind
    annotation: object
    """The annotation as written, for hybrid commands and help."""
    default: object
    converter: ConvertFunction
    optional: bool = False
    """Annotated `T | None`: a word that does not convert is left for the next parameter."""
    greedy: bool = False
    description: str | None = None
    displayed_name: str | None = None

    @property
    def required(self) -> bool:
        """Whether the command cannot run without it."""
        return self.default is NO_DEFAULT and not self.optional and self.kind != "every_word"

    @property
    def consumes_rest(self) -> bool:
        """Whether it takes the rest of the message (a keyword-only parameter, after `*`)."""
        return self.kind == "rest"

    @property
    def fallback(self) -> object:
        """What it is when left out: its default, or `None` for an optional parameter without one."""
        if self.default is not NO_DEFAULT:
            return self.default
        if self.greedy:
            return []
        return None

    def usage(self) -> str:
        """How help shows it: `<member>`, `[days=1]`, `[members...]`."""
        shown = self.displayed_name or self.name
        if self.kind == "every_word" or self.greedy:
            return f"[{shown}...]"
        if self.required:
            return f"<{shown}>"
        if self.default is not NO_DEFAULT and self.default is not None:
            return f"[{shown}={self.default}]"
        return f"[{shown}]"


def parameter_of(item: inspect.Parameter, annotation: object) -> Parameter:
    """The parameter a callback declares as `item`, with its resolved `annotation`.

    Raises:
        TypeError: The annotation is not something a command argument can be converted to.
    """
    converter, optional, greedy = converter_for(item.name, annotation)
    kind: ArgumentKind = (
        "rest"
        if item.kind is inspect.Parameter.KEYWORD_ONLY
        else "every_word"
        if item.kind is inspect.Parameter.VAR_POSITIONAL
        else "word"
    )
    return Parameter(
        name=item.name,
        kind=kind,
        annotation=annotation,
        default=item.default,
        converter=converter,
        optional=optional,
        greedy=greedy,
    )


def converter_for(name: str, annotation: object) -> tuple[ConvertFunction, bool, bool]:
    """The converter for `annotation`, whether it is optional, and whether it is greedy.

    Raises:
        TypeError: The annotation is not something a command argument can be converted to.
    """
    origin = get_origin(annotation)
    if origin is Greedy:
        [inner] = get_args(annotation)
        converter, optional, _ = converter_for(name, inner)
        if optional:
            msg = f"parameter {name!r}: Greedy[Optional[...]] is not supported; give Greedy a default instead"
            raise TypeError(msg)
        return converter, False, True
    if origin in {Union, types.UnionType}:
        members = [member for member in get_args(annotation) if member is not type(None)]
        optional = len(members) < len(get_args(annotation))
        if len(members) == 1:
            return converter_for(name, members[0])[0], optional, False
        return _union(name, [converter_for(name, member)[0] for member in members]), optional, False
    return _single(name, annotation), False, False


def _single(name: str, annotation: object) -> ConvertFunction:
    if get_origin(annotation) is Annotated:
        inner, *extras = get_args(annotation)
        spec = next((extra for extra in extras if isinstance(extra, RangeSpec)), None)
        if spec is not None:
            return _ranged(_single(name, inner), spec)
        converter = next((extra for extra in extras if _is_converter(extra)), None)
        return _custom(converter) if converter is not None else _single(name, inner)
    if get_origin(annotation) is Literal:
        return _literal(name, get_args(annotation))
    if annotation is inspect.Parameter.empty or annotation is object:
        return BUILT_IN[str]
    found = BUILT_IN.get(annotation)
    if found is not None:
        return found
    # isinstance(..., type) leaves type[Unknown]; issubclass then proves the enum.
    if isinstance(annotation, type) and issubclass(cast("type[object]", annotation), enum.Enum):
        return _enum(cast("type[enum.Enum]", annotation))  # checked just above
    if _is_converter(annotation):
        return _custom(annotation)
    msg = f"parameter {name!r}: cannot convert a command argument to {annotation!r}"
    raise TypeError(msg)


def _is_converter(value: object) -> bool:
    """A `Converter` class or instance, or a function (not a type) that takes the argument text."""
    if isinstance(value, type):
        # isinstance(..., type) leaves type[Unknown]
        return issubclass(cast("type[object]", value), Converter)
    return isinstance(value, Converter) or (callable(value) and not isinstance(value, types.GenericAlias))


def has_own_converter(annotation: object) -> bool:
    """Whether `annotation` converts with a converter of its own rather than by its type.

    That is a `Converter`, a function, or `Annotated[T, converter]`.
    """
    members = get_args(annotation) if get_origin(annotation) in {Union, types.UnionType} else (annotation,)
    for member in members:
        if get_origin(member) is Annotated:
            if any(_is_converter(extra) for extra in get_args(member)[1:]):
                return True
        elif (
            member not in BUILT_IN
            and _is_converter(member)
            # isinstance(..., type) leaves type[Unknown]
            and not (isinstance(member, type) and issubclass(cast("type[object]", member), enum.Enum))
        ):
            return True
    return False


def _as_converter(value: object) -> "Converter[object] | None":
    """`value` when it is a `Converter` instance."""
    # isinstance narrows to Converter[Unknown]
    return cast("Converter[object]", value) if isinstance(value, Converter) else None


def _custom(converter: object) -> ConvertFunction:
    """A `Converter` (class or instance) or a function taking the argument text.

    Raises:
        TypeError: `converter` is neither.
    """
    instance: object = converter
    if isinstance(converter, type):
        made = cast("type[object]", converter)  # isinstance(..., type) leaves type[Unknown]
        if not issubclass(made, Converter):
            msg = f"{made.__name__} is not a Converter"
            raise TypeError(msg)
        # Not `made()`: issubclass narrowed it to Converter[Unknown].
        instance = cast("type[object]", converter)()
    converter_instance = _as_converter(instance)
    if converter_instance is not None:

        async def convert_with(ctx: "Context", argument: str) -> object:
            try:
                return await converter_instance.convert(ctx, argument)
            except CommandError:
                raise
            except Exception as error:
                raise ConversionError(converter_instance, error) from error

        return convert_with
    if not callable(instance):
        msg = f"{instance!r} is not a converter"
        raise TypeError(msg)
    function = cast("Callable[[str], object]", instance)  # a converter function takes the text

    async def convert(ctx: "Context", argument: str) -> object:
        del ctx
        try:
            result = function(argument)
            return await result if inspect.isawaitable(result) else result
        except CommandError:
            raise
        except Exception as error:
            raise ConversionError(function, error) from error

    return convert


def _ranged(converter: ConvertFunction, spec: RangeSpec) -> ConvertFunction:
    async def convert(ctx: "Context", argument: str) -> object:
        value = await converter(ctx, argument)
        measured = len(value) if isinstance(value, str) else value
        if not isinstance(measured, int | float):
            msg = f"{value!r} cannot be compared with a range"
            raise BadArgumentError(msg)
        if (spec.minimum is not None and measured < spec.minimum) or (
            spec.maximum is not None and measured > spec.maximum
        ):
            raise RangeError(value, spec.minimum, spec.maximum)
        return value

    return convert


def _literal(name: str, values: tuple[object, ...]) -> ConvertFunction:
    async def convert(ctx: "Context", argument: str) -> object:
        del ctx
        for value in values:
            if isinstance(value, str) and value.casefold() == argument.casefold():
                return value
            if isinstance(value, bool):
                if argument.casefold() == str(value).casefold():
                    return value
            elif isinstance(value, int | float):
                try:
                    if type(value)(argument) == value:
                        return value
                except ValueError:
                    continue
        raise BadLiteralArgumentError(name, values, argument)

    return convert


def _enum(enum_class: type[enum.Enum]) -> ConvertFunction:
    """An enum member by name (any case) or by value."""
    by_name = {member.name.casefold(): member for member in enum_class}

    async def convert(ctx: "Context", argument: str) -> object:
        del ctx
        found = by_name.get(argument.casefold())
        if found is not None:
            return found
        for member in enum_class:
            if str(member.value).casefold() == argument.casefold():
                return member
        msg = f"{argument!r} is not a {enum_class.__name__}"
        raise BadArgumentError(msg)

    return convert


def _union(name: str, converters: list[ConvertFunction]) -> ConvertFunction:
    async def convert(ctx: "Context", argument: str) -> object:
        errors: list[CommandError] = []
        for converter in converters:
            try:
                return await converter(ctx, argument)
            except CommandError as error:
                errors.append(error)
        raise BadUnionArgumentError(name, errors)

    return convert
