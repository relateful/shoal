"""Transformers: an option converted by code of your own, after the checks pass.

    class ItemTransformer(app_commands.Transformer[Item]):
        async def transform(self, interaction: Interaction, value: object) -> Item:
            return await shop.find(str(value))

        async def autocomplete(self, interaction: Interaction, value: str | int | float) -> list[Choice[str]]:
            return [Choice(name=item.name, value=item.id) for item in await shop.search(str(value))]

    @tree.command()
    async def buy(interaction: Interaction, item: app_commands.Transform[Item, ItemTransformer]) -> None: ...

The option is a string unless `type` says otherwise; `transform` gets the value as a parameter of
that type would (a `Member` for a user option), and its result is what the callback receives.

Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-application-command-option-structure
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated, cast, get_args, get_origin

from shoal.app_commands.models import AnyChoice
from shoal.client.interaction import Interaction
from shoal.payloads.application_commands import ApplicationCommandOptionType
from shoal.payloads.channel import ChannelType

__all__ = ["Transform", "Transformer", "transformer_of"]


class Transformer[T](ABC):
    """Converts an option's value into what the callback asks for; override `transform`.

    Override the properties to shape the option Discord shows: its `type`, `channel_types`,
    `min_value` and `max_value` (lengths, for a string), and fixed `choices`. Override
    `autocomplete` to suggest values as the user types.
    """

    __slots__ = ()

    @property
    def type(self) -> ApplicationCommandOptionType:
        """The option's type; a string by default."""
        return ApplicationCommandOptionType.STRING

    @property
    def channel_types(self) -> list[ChannelType]:
        """For a channel option, the kinds of channel it offers; empty means every kind."""
        return []

    @property
    def min_value(self) -> int | float | None:
        """The smallest value (for a string, length) the option takes."""
        return None

    @property
    def max_value(self) -> int | float | None:
        """The largest value (for a string, length) the option takes."""
        return None

    @property
    def choices(self) -> Sequence[AnyChoice]:
        """Fixed values the user picks from; none by default."""
        return ()

    @abstractmethod
    async def transform(self, interaction: Interaction, value: object) -> T:
        """What the callback receives for `value` (converted as for an option of `type`).

        Raise an `AppCommandError` to refuse it; anything else raised becomes a `TransformerError`.
        """

    async def autocomplete(self, interaction: Interaction, value: str | float) -> Sequence[AnyChoice]:
        """Suggestions for what the user typed so far; a transformer that overrides this offers them."""
        del interaction, value
        return ()

    def has_autocomplete(self) -> bool:
        """Whether this transformer suggests values (its class overrides `autocomplete`)."""
        defining = next(cls for cls in type(self).__mro__ if "autocomplete" in vars(cls))
        return defining is not Transformer


if TYPE_CHECKING:
    # To a type checker `Transform[Item, ItemTransformer]` is `Annotated[Item, ItemTransformer]`: an
    # `Item`. Imported under the name, rather than assigned, so mypy treats it as the special form too.
    from typing import Annotated as Transform
else:

    class Transform:
        """`Transform[T, SomeTransformer]`: an option the transformer turns into a `T`."""

        __slots__ = ()

        def __class_getitem__(cls, parameters: tuple[type, object]) -> object:
            kind, transformer = parameters
            made = transformer() if isinstance(transformer, type) else transformer
            if not isinstance(made, Transformer):
                msg = f"Transform takes a Transformer (class or instance), not {transformer!r}"
                raise TypeError(msg)
            return Annotated[kind, made]


def transformer_of(annotation: object) -> "Transformer[object] | None":
    """The transformer an annotation names: a `Transformer` class or instance, alone or in `Annotated`."""
    candidates = get_args(annotation)[1:] if get_origin(annotation) is Annotated else (annotation,)
    for candidate in candidates:
        # isinstance(..., type) leaves type[Unknown]
        if isinstance(candidate, type) and issubclass(cast("type[object]", candidate), Transformer):
            # Any transformer returns an object, whatever it promises.
            return cast("type[Transformer[object]]", candidate)()
        if isinstance(candidate, Transformer):
            return cast("Transformer[object]", candidate)  # isinstance narrows to Transformer[Unknown]
    return None
