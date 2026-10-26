"""The base of every component in a view or modal: buttons, selects and text inputs.

Discord: https://docs.discord.com/developers/components/reference
"""

import os
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, ClassVar, Final

from shoal.client.interaction import Interaction
from shoal.payloads.components import (
    COMPONENT_CUSTOM_ID_MAX_LENGTH,
    LEGACY_MESSAGE_MAX_ACTION_ROWS,
    ActionRowChild,
    Label,
)
from shoal.payloads.interactions import ResolvedData

if TYPE_CHECKING:
    from shoal.ui.view import View

ITEM_FACTORY: Final = "__shoal_item__"
"""The attribute `@ui.button` and `@ui.select` leave on a view method: a function making its item."""


def check_length(item: object, field: str, value: str | None, maximum: int) -> None:
    """Refuse `value` when it is longer than Discord allows for `field`.

    Raises:
        ValueError: It is longer than `maximum` characters.
    """
    if value is not None and len(value) > maximum:
        msg = f"{item!r}: {field} is {len(value)} characters; Discord allows at most {maximum}"
        raise ValueError(msg)


def random_custom_id() -> str:
    """A custom ID nobody else will pick, for items that were not given one."""
    return os.urandom(16).hex()


class Item:
    """One component. Subclass it, or set `callback`, to react when it is used.

    `callback` can be overridden in a subclass (`async def callback(self, interaction)`) or assigned
    on an instance (`button.callback = handler`).

    Discord: https://docs.discord.com/developers/components/reference
    """

    # `__dict__` lets an instance's callback be replaced; the named slots keep the rest compact.
    __slots__ = ("__dict__", "_bound", "_custom_id", "_custom_id_given", "_row", "_view")

    width: ClassVar[int] = 1
    """How much of an action row the item takes (a button 1, a select the whole row)."""

    def __init__(self, *, custom_id: str | None = None, row: int | None = None) -> None:
        """An item; `custom_id` is random when not given, and `row` (0 to 4) is chosen when not given.

        Raises:
            ValueError: `row` is outside 0 to 4.
        """
        if row is not None and not 0 <= row < LEGACY_MESSAGE_MAX_ACTION_ROWS:
            msg = f"row must be from 0 to {LEGACY_MESSAGE_MAX_ACTION_ROWS - 1}, not {row}"
            raise ValueError(msg)
        self._custom_id: str = custom_id or random_custom_id()
        self._custom_id_given: bool = custom_id is not None
        self._row: int | None = row
        self._view: View | None = None
        self._bound: Callable[[Interaction], Awaitable[None]] | None = None

    @property
    def custom_id(self) -> str:
        """The ID Discord sends back when the item is used."""
        return self._custom_id

    @custom_id.setter
    def custom_id(self, value: str) -> None:
        self._custom_id = value
        self._custom_id_given = True

    @property
    def row(self) -> int | None:
        """The action row the item asked for, or `None` to be placed in the first with room."""
        return self._row

    @row.setter
    def row(self, value: int | None) -> None:
        if value is not None and not 0 <= value < LEGACY_MESSAGE_MAX_ACTION_ROWS:
            msg = f"row must be from 0 to {LEGACY_MESSAGE_MAX_ACTION_ROWS - 1}, not {value}"
            raise ValueError(msg)
        self._row = value

    @property
    def view(self) -> "View | None":
        """The view the item belongs to."""
        return self._view

    def attach(self, view: "View | None") -> None:
        """Record the view the item belongs to; `View.add_item` and `remove_item` call it."""
        self._view = view

    def to_component(self) -> ActionRowChild | Label:
        """The item as Discord takes it: a component of an action row, or a label in a modal."""
        raise NotImplementedError

    def validate(self) -> None:
        """Refuse what Discord would refuse; views and modals call it before sending.

        Raises:
            ValueError: A text is too long, or a number is out of Discord's range.
        """
        if not 1 <= len(self._custom_id) <= COMPONENT_CUSTOM_ID_MAX_LENGTH:
            msg = f"{self!r}: custom_id must be 1 to {COMPONENT_CUSTOM_ID_MAX_LENGTH} characters"
            raise ValueError(msg)

    def is_dispatchable(self) -> bool:
        """Whether the item sends interactions (a link button does not)."""
        return True

    def is_persistent(self) -> bool:
        """Whether the item's custom ID was chosen by hand, so it still matches after a restart."""
        return self._custom_id_given or not self.is_dispatchable()

    def refresh(self, interaction: Interaction, values: Sequence[str], resolved: ResolvedData | None) -> None:
        """Take the item's new state from the interaction that used it (choices, or typed text)."""
        del interaction, values, resolved

    async def callback(self, interaction: Interaction) -> None:
        """Runs when the item is used. The default does nothing; override or assign it."""
        del interaction

    def bind(self, handler: Callable[[Interaction], Awaitable[None]]) -> None:
        """Run `handler` instead of `callback` (what `@ui.button` and `@ui.select` set up)."""
        self._bound = handler

    async def invoke(self, interaction: Interaction) -> None:
        """Run the item's handler: the bound one, else `callback`."""
        if self._bound is not None:
            await self._bound(interaction)
        else:
            await self.callback(interaction)
