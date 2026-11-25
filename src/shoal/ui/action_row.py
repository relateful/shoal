"""Action rows: up to five buttons and overflow menus, or one select, in a `LayoutView` or a container.

    class Controls(ui.LayoutView):
        row = ui.ActionRow()

        @row.button(label="Refresh")
        async def refresh(self, interaction: Interaction, button: ui.Button) -> None:
            await interaction.response.send_message("Refreshed", ephemeral=True)

An `ActionRow` subclass can also declare its own items with `@ui.button` and `@ui.select`; there,
`self` is the row. A method decorated through a row (`@row.button`) gets as `self` the object whose
class defines it: the view, or a container subclass.

Discord: https://docs.discord.com/developers/components/reference#action-row
"""

from collections.abc import Callable, Sequence
from typing import ClassVar, Self, overload, override

from shoal.models.base import unset_if_none
from shoal.models.emoji import EmojiLike
from shoal.payloads.channel import ChannelType
from shoal.payloads.components import ACTION_ROW_MAX_BUTTONS, ButtonStyle, SelectOption
from shoal.payloads.components import ActionRow as ActionRowPayload
from shoal.ui.button import Button, ButtonCallback, button_factory
from shoal.ui.item import (
    ITEM_FACTORY,
    Decorated,
    InteractiveItem,
    Item,
    ItemView,
    bind_method,
    decorated_methods,
    lineage,
    method_owner,
)
from shoal.ui.overflow import OverflowMenu
from shoal.ui.select import BaseSelect, Select, SelectCallback, select_factory

type RowItem = Button | BaseSelect
"""What a `View` puts in its action rows."""

type LayoutRowItem = Button | BaseSelect | OverflowMenu
"""What an action row of a `LayoutView` or a container holds: overflow menus need Components V2."""

type _Pending = tuple[Callable[[], InteractiveItem], Decorated]


def row_item(item: Item) -> RowItem:
    """`item`, checked to be something an action row holds.

    Raises:
        TypeError: It is not a button or a select.
    """
    if not isinstance(item, Button | BaseSelect):
        msg = f"an action row holds buttons and selects, not {item!r}; use a LayoutView for the rest"
        raise TypeError(msg)
    return item


def layout_row_item(item: Item) -> LayoutRowItem:
    """`item`, checked to be something an `ActionRow` holds.

    Raises:
        TypeError: It is not a button, a select or an overflow menu.
    """
    if not isinstance(item, Button | BaseSelect | OverflowMenu):
        msg = f"an action row holds buttons, selects and overflow menus, not {item!r}"
        raise TypeError(msg)
    return item


class ActionRow(Item):
    """A row of up to five buttons and overflow menus, or a single select.

    Discord: https://docs.discord.com/developers/components/reference#action-row
    """

    __slots__ = ("_children", "_pending")

    __row_items__: ClassVar[list[Decorated]] = []

    @override
    def __init_subclass__(cls) -> None:
        """Collect the methods decorated with `@ui.button` and `@ui.select`, base classes first."""
        super().__init_subclass__()
        cls.__row_items__ = decorated_methods(cls)

    def __init__(self, *children: LayoutRowItem, id: int | None = None) -> None:
        """A row holding `children`, then the items a subclass declares.

        Raises:
            TypeError: A child is not a button or a select.
            ValueError: The children do not fit in one row.
        """
        super().__init__(id=id)
        self._children: list[LayoutRowItem] = []
        self._pending: list[_Pending] = [
            (getattr(method, ITEM_FACTORY), method) for method in type(self).__row_items__
        ]
        for child in children:
            self.add_item(child)

    @property
    @override
    def children(self) -> list[Item]:
        """The buttons and overflow menus, or the select, in order."""
        return list(self._children)

    def add_item(self, item: LayoutRowItem) -> Self:
        """Add a button, a select or an overflow menu.

        Raises:
            TypeError: `item` is not a button, a select or an overflow menu.
            ValueError: The row has no room for it.
        """
        item = layout_row_item(item)
        used = sum(child.width for child in self._children)
        if used + item.width > ACTION_ROW_MAX_BUTTONS:
            msg = (
                f"{self!r} has no room for {item!r}: "
                f"up to {ACTION_ROW_MAX_BUTTONS} buttons and overflow menus, or one select"
            )
            raise ValueError(msg)
        self._children.append(item)
        self.adopt(item)
        return self

    def remove_item(self, item: LayoutRowItem) -> Self:
        """Remove a button, select or overflow menu (nothing happens if it is not in the row)."""
        if item in self._children:
            self._children.remove(item)
            self.release(item)
        return self

    def clear_items(self) -> Self:
        """Remove every item."""
        for item in self._children:
            self.release(item)
        self._children.clear()
        return self

    @override
    def attach(self, view: ItemView | None) -> None:
        super().attach(view)
        if view is not None and self._pending:
            pending, self._pending = self._pending, []
            for factory, method in pending:
                item = row_item(factory())
                item.bind(bind_method(method, method_owner(method, lineage(self), view), item))
                self.add_item(item)

    @override
    def to_component(self) -> ActionRowPayload:
        """The row as Discord takes it."""
        return ActionRowPayload(
            id=unset_if_none(self.id), components=[child.to_component() for child in self._children]
        )

    def button[O](
        self,
        *,
        label: str | None = None,
        custom_id: str | None = None,
        disabled: bool = False,
        style: ButtonStyle = ButtonStyle.SECONDARY,
        emoji: EmojiLike | None = None,
        id: int | None = None,
    ) -> Callable[[ButtonCallback[O]], ButtonCallback[O]]:
        """Add a button to this row, run by the decorated method: `(self, interaction, button)`.

        Use it on a row declared in a `LayoutView` or `Container` class body. Each instance of the
        view gets its own button.
        """
        make = button_factory(
            label=label, custom_id=custom_id, disabled=disabled, style=style, emoji=emoji, row=None, id=id
        )

        def decorator(function: ButtonCallback[O]) -> ButtonCallback[O]:
            self._pending.append((make, function))
            return function

        return decorator

    @overload
    def select[O](
        self,
        *,
        cls: None = None,
        custom_id: str | None = None,
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        options: Sequence[SelectOption] = (),
        disabled: bool = False,
        id: int | None = None,
    ) -> Callable[[SelectCallback[O, Select]], SelectCallback[O, Select]]: ...
    @overload
    def select[O, S: BaseSelect](
        self,
        *,
        cls: type[S],
        custom_id: str | None = None,
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        options: Sequence[SelectOption] = (),
        channel_types: Sequence[ChannelType] = (),
        disabled: bool = False,
        id: int | None = None,
    ) -> Callable[[SelectCallback[O, S]], SelectCallback[O, S]]: ...
    def select(
        self,
        *,
        cls: type[BaseSelect] | None = None,
        custom_id: str | None = None,
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        options: Sequence[SelectOption] = (),
        channel_types: Sequence[ChannelType] = (),
        disabled: bool = False,
        id: int | None = None,
    ) -> Callable[[Decorated], Decorated]:
        """Add a select (a string select, or `cls`) to this row, run on each choice.

        The decorated method takes `(self, interaction, select)`; see `button` for where it goes.
        """
        make = select_factory(
            cls=cls,
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            options=options,
            channel_types=channel_types,
            disabled=disabled,
            row=None,
            id=id,
        )

        def decorator(function: Decorated) -> Decorated:
            self._pending.append((make, function))
            return function

        return decorator

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__} items={len(self._children)}>"
