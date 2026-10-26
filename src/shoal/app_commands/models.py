"""Choices, ranges and the namespace of filled-in options.

    @tree.command()
    @app_commands.choices(colour=[Choice(name="Red", value="red"), Choice(name="Blue", value="blue")])
    async def paint(interaction: Interaction, colour: Choice[str], size: Range[int, 1, 10]) -> None: ...

Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-application-command-option-structure
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, override

from shoal.payloads.application_commands import ApplicationCommandOptionChoice

__all__ = ["AnyChoice", "Choice", "Namespace", "Range", "RangeSpec"]


@dataclass(frozen=True, slots=True)
class Choice[T: (str, int, float)]:
    """One fixed value of an option, shown to the user as `name`.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-application-command-option-choice-structure
    """

    name: str
    value: T

    def to_payload(self) -> ApplicationCommandOptionChoice:
        """The choice as Discord takes it."""
        return ApplicationCommandOptionChoice(name=self.name, value=self.value)


type AnyChoice = Choice[str] | Choice[int] | Choice[float]
"""A choice of any of the three kinds an option can offer."""


@dataclass(frozen=True, slots=True)
class RangeSpec:
    """The bounds a `Range[...]` annotation records: values for numbers, length for strings."""

    minimum: int | float | None
    maximum: int | float | None


if TYPE_CHECKING:
    # To a type checker `Range[int, 1, 10]` is `Annotated[int, 1, 10]`: an `int`. Imported under
    # the name, rather than assigned, so mypy treats it as the special form too.
    from typing import Annotated as Range
else:

    class Range:
        """`Range[int, 1, 10]`, `Range[float, 0.0, None]`, `Range[str, 1, 100]` (a length range).

        Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-application-command-option-structure
        """

        __slots__ = ()

        def __class_getitem__(cls, parameters: tuple[type, int | float | None, int | float | None]) -> object:
            kind, minimum, maximum = parameters
            if kind not in {int, float, str}:
                msg = f"Range takes int, float or str, not {kind!r}"
                raise TypeError(msg)
            if minimum is None and maximum is None:
                msg = "Range needs a minimum, a maximum or both"
                raise TypeError(msg)
            return Annotated[kind, RangeSpec(minimum, maximum)]


class Namespace:
    """The options of the command being run, by name: `interaction.namespace.member`.

    Options the user left out read as `None`. Values are converted as for the command's
    parameters (members, roles, channels), so checks and autocomplete see what the callback will.
    """

    __slots__ = ("__dict__",)

    def __init__(self, values: dict[str, object] | None = None) -> None:
        """A namespace holding `values`."""
        self.__dict__.update(values or {})

    def __getattr__(self, name: str) -> object:
        """An option the user left out: `None`."""
        if name.startswith("__"):
            raise AttributeError(name)
        return None

    def __contains__(self, name: str) -> bool:
        """Whether the user filled in option `name`."""
        return name in self.__dict__

    @override
    def __repr__(self) -> str:
        filled = " ".join(f"{name}={value!r}" for name, value in self.__dict__.items())
        return f"<Namespace {filled}>"
