"""The base of every component in a view or modal, and of the interactive ones.

Discord: https://docs.discord.com/developers/components/reference
"""

import copy
import os
from collections.abc import Awaitable, Callable, Iterator, Sequence
from typing import ClassVar, Final, Protocol, cast, override

from shoal.client.interaction import Interaction
from shoal.payloads.components import (
    COMPONENT_CUSTOM_ID_MAX_LENGTH,
    LEGACY_MESSAGE_MAX_ACTION_ROWS,
    Component,
    SubmittedCheckbox,
    SubmittedLabelChild,
    SubmittedRadioGroup,
    SubmittedTextInput,
)
from shoal.payloads.interactions import ResolvedData

ITEM_FACTORY: Final = "__shoal_item__"
"""The attribute `@ui.button` and `@ui.select` leave on a method: a function making its item."""

type ItemFactory = Callable[[], "InteractiveItem"]
type Decorated = Callable[..., Awaitable[None]]
"""A method decorated with `@ui.button` or `@ui.select`, called as `(owner, interaction, item)`."""


def check_length(item: object, field: str, value: str | None, maximum: int) -> None:
    """Refuse `value` when it is longer than Discord allows for `field`.

    Raises:
        ValueError: It is longer than `maximum` characters.
    """
    if value is not None and len(value) > maximum:
        msg = f"{item!r}: {field} is {len(value)} characters; Discord allows at most {maximum}"
        raise ValueError(msg)


def check_count(item: object, field: str, count: int, low: int, high: int) -> None:
    """Refuse a number of things outside what Discord allows for `field`.

    Raises:
        ValueError: `count` is outside `low` to `high`.
    """
    if not low <= count <= high:
        msg = f"{item!r}: needs {low} to {high} {field}, not {count}"
        raise ValueError(msg)


def random_custom_id() -> str:
    """A custom ID nobody else will pick, for items that were not given one."""
    return os.urandom(16).hex()


class ItemView(Protocol):
    """The view an item belongs to, as the item sees it: a `ui.View` or a `ui.LayoutView`."""

    __slots__ = ()

    def stop(self) -> None:
        """Stop receiving interactions."""
        ...

    def is_finished(self) -> bool:
        """Whether the view stopped or timed out."""
        ...

    def walk_children(self) -> Iterator["Item"]:
        """Every item of the view, at any depth."""
        ...

    def find_item(self, id: int, /) -> "Item | None":
        """The item with component `id`, at any depth."""
        ...


class Item:
    """One component: a button, a select, a text display, a container.

    `id` is Discord's optional component identifier: unique within the message or modal, and sent
    back in interactions. Left unset, Discord numbers the components itself.

    Discord: https://docs.discord.com/developers/components/reference#anatomy-of-a-component
    """

    # `__dict__` lets an instance's callback be replaced; the named slots keep the rest compact.
    __slots__ = ("__dict__", "_id", "_parent", "_view")

    is_v2: ClassVar[bool] = False
    """Whether the item needs a Components V2 message (`MessageFlags.is_components_v2`)."""

    def __init__(self, *, id: int | None = None) -> None:
        """An item with Discord's component `id` (unset: Discord numbers it)."""
        self._id: int | None = id
        self._parent: Item | None = None
        self._view: ItemView | None = None

    @property
    def id(self) -> int | None:
        """The component's identifier, unique within its message or modal."""
        return self._id

    @id.setter
    def id(self, value: int | None) -> None:
        self._id = value

    @property
    def view(self) -> ItemView | None:
        """The view the item belongs to."""
        return self._view

    @property
    def parent(self) -> "Item | None":
        """The item holding this one (an action row, a section, a container or a label), if any."""
        return self._parent

    @property
    def children(self) -> list["Item"]:
        """The items this one holds directly; none for most items."""
        return []

    def walk(self) -> Iterator["Item"]:
        """Every item held by this one, at any depth, parents before their children."""
        for child in self.children:
            yield child
            yield from child.walk()

    def adopt(self, child: "Item") -> None:
        """Make this item `child`'s parent, in this item's view; containers call it when adding."""
        child._parent = self  # noqa: SLF001 - parent and child are both items
        child.attach(self._view)

    def release(self, child: "Item") -> None:
        """Undo `adopt`; containers call it when removing."""
        child._parent = None  # noqa: SLF001 - parent and child are both items
        child.attach(None)

    def attach(self, view: ItemView | None) -> None:
        """Record the view the item (and everything it holds) belongs to."""
        self._view = view
        for child in self.children:
            child.attach(view)

    def to_component(self) -> Component:
        """The item as Discord takes it."""
        raise NotImplementedError

    def validate(self) -> None:
        """Refuse what Discord would refuse, here and in every item held; called before sending.

        Raises:
            ValueError: A text is too long, a number is out of Discord's range, or a count is wrong.
        """
        if self._id is not None and self._id < 0:
            msg = f"{self!r}: id must not be negative, not {self._id}"
            raise ValueError(msg)
        for child in self.children:
            child.validate()

    def count(self) -> int:
        """How many components the item is, with everything it holds (Discord limits the total)."""
        return 1 + sum(child.count() for child in self.children)


class InteractiveItem(Item):
    """An item the user acts on: a button, a select, or a modal input.

    `callback` can be overridden in a subclass (`async def callback(self, interaction)`) or assigned
    on an instance (`button.callback = handler`).

    Discord: https://docs.discord.com/developers/components/reference#anatomy-of-a-component-custom-id
    """

    __slots__ = ("_bound", "_custom_id", "_custom_id_given", "_row")

    width: ClassVar[int] = 1
    """How much of an action row the item takes (a button 1, a select the whole row)."""

    def __init__(
        self, *, custom_id: str | None = None, row: int | None = None, id: int | None = None
    ) -> None:
        """An item; `custom_id` is random when not given.

        `row` (0 to 4) places it in a `View`'s action rows; it is chosen when not given.

        Raises:
            ValueError: `row` is outside 0 to 4.
        """
        super().__init__(id=id)
        _check_row(row)
        self._custom_id: str = custom_id or random_custom_id()
        self._custom_id_given: bool = custom_id is not None
        self._row: int | None = row
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
        """The action row of a `View` the item asked for, or `None` to be placed in the first with room."""
        return self._row

    @row.setter
    def row(self, value: int | None) -> None:
        _check_row(value)
        self._row = value

    @override
    def validate(self) -> None:
        """Refuse what Discord would refuse; views and modals call it before sending.

        Raises:
            ValueError: The custom ID, a text or a number is outside Discord's limits.
        """
        super().validate()
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


def _check_row(row: int | None) -> None:
    if row is not None and not 0 <= row < LEGACY_MESSAGE_MAX_ACTION_ROWS:
        msg = f"row must be from 0 to {LEGACY_MESSAGE_MAX_ACTION_ROWS - 1}, not {row}"
        raise ValueError(msg)


def submitted_values(submitted: SubmittedLabelChild) -> list[str]:
    """What a modal input sent, as the strings a component interaction would carry."""
    match submitted:
        case SubmittedTextInput() | SubmittedRadioGroup():
            return [] if submitted.value is None else [submitted.value]
        case SubmittedCheckbox():
            return ["true"] if submitted.value else []
        case _:
            return [str(value) for value in submitted.values]


def bind_method(
    method: Decorated, owner: object, item: InteractiveItem
) -> Callable[[Interaction], Awaitable[None]]:
    """`method`, called as `(owner, interaction, item)`."""

    async def handler(interaction: Interaction) -> None:
        await method(owner, interaction, item)

    return handler


def decorated_methods(cls: type) -> list[Decorated]:
    """The methods of `cls` decorated with `@ui.button` or `@ui.select`, base classes first.

    A subclass that redefines one without the decorator removes its item.
    """
    found: dict[str, Decorated] = {}
    for base in reversed(cls.__mro__):
        for name, member in vars(base).items():
            if callable(member) and hasattr(member, ITEM_FACTORY):
                found[name] = cast("Decorated", member)  # only the item decorators set ITEM_FACTORY
            elif name in found:
                del found[name]
    return list(found.values())


def item_templates(cls: type) -> list[tuple[str, Item]]:
    """The items declared as class attributes of `cls`, base classes first, by attribute name."""
    found: dict[str, Item] = {}
    for base in reversed(cls.__mro__):
        found.update((name, member) for name, member in vars(base).items() if isinstance(member, Item))
    return list(found.items())


def instantiate(owner: object, templates: Sequence[tuple[str, Item]]) -> list[Item]:
    """Copy class-declared items for one instance, set them as its attributes, return the top-level ones.

    One copy is shared by every attribute naming the same item, so an action row declared on its own
    and inside a container is the same object in the instance too.
    """
    memo: dict[int, object] = {}
    top: list[Item] = []
    for name, template in templates:
        own = copy.deepcopy(template, memo)
        setattr(owner, name, own)
        if template.parent is None:
            top.append(own)
    return top
