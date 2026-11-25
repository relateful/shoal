"""Overflow menus: a "more" button opening a menu of actions, in an action row or beside a section.

    class Ticket(ui.LayoutView):
        manage = ui.OverflowMenuGroup(label="Manage")
        summary = ui.Section("Ticket #12", accessory=ui.OverflowMenu(manage))

        @manage.action(label="Close", style=MenuActionItemStyle.DANGER)
        async def close(self, interaction: Interaction, item: ui.MenuActionItem) -> None:
            await interaction.response.send_message("Closed", ephemeral=True)

A method decorated through a group (`@group.action`) gets as `self` the object whose class defines
it: the view, or a container holding the menu. An `OverflowMenuGroup` subclass can add actions run
by its own methods from `__init__` (`self.action(label=...)(type(self).method)`); there `self` is
the group.

Overflow menus are not yet in Discord's docs: Discord is testing them in its clients, and these
classes follow the shape seen there. They need a Components V2 message, and may change before
Discord documents them. Only documented limits are checked, so none of their own are yet.

Discord: https://docs.discord.com/developers/components/reference
"""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, ClassVar, Self, override

from msgspec import UNSET

from shoal.client.interaction import Interaction
from shoal.models.base import unset_if_none
from shoal.models.emoji import EmojiLike, partial_emoji
from shoal.payloads.components import MenuActionItem as MenuActionItemPayload
from shoal.payloads.components import MenuActionItemStyle
from shoal.payloads.components import OverflowMenu as OverflowMenuPayload
from shoal.payloads.components import OverflowMenuGroup as OverflowMenuGroupPayload
from shoal.ui.item import (
    Decorated,
    InteractiveItem,
    Item,
    ItemView,
    bind_method,
    lineage,
    method_owner,
)

if TYPE_CHECKING:
    from shoal.payloads.emoji import PartialEmoji


class MenuActionItem(InteractiveItem):
    """One action of an overflow menu. A link action (`url`) sends no interaction.

    Discord: https://docs.discord.com/developers/components/reference
    """

    __slots__ = ("description", "emoji", "label", "style", "url")

    def __init__(
        self,
        *,
        label: str,
        style: MenuActionItemStyle = MenuActionItemStyle.DEFAULT,
        custom_id: str | None = None,
        url: str | None = None,
        description: str | None = None,
        emoji: EmojiLike | None = None,
        id: int | None = None,
    ) -> None:
        """An action; giving `url` makes it a link action.

        Raises:
            ValueError: Both `url` and `custom_id` were given.
        """
        if url is not None and custom_id is not None:
            msg = "a link action cannot have a custom_id"
            raise ValueError(msg)
        super().__init__(custom_id=custom_id, id=id)
        self.label: str = label
        self.style: MenuActionItemStyle = MenuActionItemStyle.LINK if url is not None else style
        self.url: str | None = url
        self.description: str | None = description
        self.emoji: PartialEmoji | None = partial_emoji(emoji) if emoji is not None else None

    @override
    def is_dispatchable(self) -> bool:
        return self.url is None

    @override
    def validate(self) -> None:
        """Refuse a link action without a URL, on top of the checks every item gets.

        Raises:
            ValueError: The style is `LINK` but there is no `url`, or the custom ID is out of range.
        """
        super().validate()
        if self.style is MenuActionItemStyle.LINK and self.url is None:
            msg = f"{self!r}: a link action needs a url"
            raise ValueError(msg)

    @override
    def to_component(self) -> MenuActionItemPayload:
        """The action as Discord takes it."""
        return MenuActionItemPayload(
            id=unset_if_none(self.id),
            custom_id=self.custom_id if self.is_dispatchable() else UNSET,
            label=self.label,
            style=self.style,
            description=unset_if_none(self.description),
            url=unset_if_none(self.url),
            emoji=unset_if_none(self.emoji),
        )

    @override
    def __repr__(self) -> str:
        return f"<MenuActionItem style={self.style.name} label={self.label!r} custom_id={self.custom_id!r}>"


type ActionCallback[O] = Callable[[O, Interaction, MenuActionItem], Awaitable[None]]
"""A method decorated with `@group.action`."""

type _Pending = tuple[Callable[[], MenuActionItem], Decorated]


class OverflowMenuGroup:
    """A run of an overflow menu's actions, under an optional heading.

    It is not a component: Discord numbers and dispatches only the menu and its actions. A subclass
    can add actions run by its own methods in `__init__`: `self.action(label=...)(type(self).method)`.

    Discord: https://docs.discord.com/developers/components/reference
    """

    __slots__ = ("_items", "_menu", "_pending", "label")

    __shoal_template__: ClassVar[bool] = True
    """Copied per instance when declared on a view, container or modal class (see `item.TEMPLATE`)."""

    def __init__(self, *items: MenuActionItem, label: str | None = None) -> None:
        """A group of `items`, under `label` when given."""
        self.label: str | None = label
        self._items: list[MenuActionItem] = []
        self._menu: OverflowMenu | None = None
        self._pending: list[_Pending] = []
        for item in items:
            self.add_item(item)

    @property
    def items(self) -> list[MenuActionItem]:
        """The actions, in order."""
        return list(self._items)

    @property
    def menu(self) -> "OverflowMenu | None":
        """The overflow menu holding the group, if any."""
        return self._menu

    def add_item(self, item: MenuActionItem) -> Self:
        """Add an action.

        Raises:
            TypeError: `item` is not a `MenuActionItem`.
        """
        item = _action(item)
        self._items.append(item)
        if self._menu is not None:
            self._menu.adopt(item)
        return self

    def remove_item(self, item: MenuActionItem) -> Self:
        """Remove an action (nothing happens if it is not in the group)."""
        if item in self._items:
            self._items.remove(item)
            if self._menu is not None:
                self._menu.release(item)
        return self

    def clear_items(self) -> Self:
        """Remove every action."""
        for item in list(self._items):
            self.remove_item(item)
        return self

    def action[O](
        self,
        *,
        label: str,
        style: MenuActionItemStyle = MenuActionItemStyle.DEFAULT,
        custom_id: str | None = None,
        description: str | None = None,
        emoji: EmojiLike | None = None,
        id: int | None = None,
    ) -> Callable[[ActionCallback[O]], ActionCallback[O]]:
        """Add an action to this group, run by the decorated method: `(self, interaction, item)`.

        Use it on a group declared in a `LayoutView`, `Container` or `Modal` class body: each
        instance gets its own copy of the group, and its action is made when the menu joins a view.
        """

        def make() -> MenuActionItem:
            return MenuActionItem(
                label=label, style=style, custom_id=custom_id, description=description, emoji=emoji, id=id
            )

        def decorator(function: ActionCallback[O]) -> ActionCallback[O]:
            self._pending.append((make, function))
            return function

        return decorator

    def join(self, menu: "OverflowMenu | None") -> None:
        """Move the group's actions into `menu` (or out of every menu); `OverflowMenu` calls it."""
        if self._menu is not None:
            for item in self._items:
                self._menu.release(item)
        self._menu = menu
        if menu is not None:
            for item in self._items:
                menu.adopt(item)

    def bind_pending(self, view: ItemView) -> None:
        """Make the actions declared with `action`, once the group's menu is in `view`."""
        menu = self._menu
        if menu is None or not self._pending:
            return
        holders: list[object] = [self, *lineage(menu)]
        # Find every owner before changing anything, so a method with no owner leaves the group as it was.
        owners = [method_owner(method, holders, view) for _, method in self._pending]
        pending, self._pending = self._pending, []
        for (factory, method), owner in zip(pending, owners, strict=True):
            item = factory()
            item.bind(bind_method(method, owner, item))
            self.add_item(item)

    def to_payload(self) -> OverflowMenuGroupPayload:
        """The group as Discord takes it."""
        return OverflowMenuGroupPayload(
            label=unset_if_none(self.label), components=[item.to_component() for item in self._items]
        )

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__} label={self.label!r} items={len(self._items)}>"


class OverflowMenu(Item):
    """A "more" button opening a menu of actions, in groups: in an action row, or beside a section.

    Discord: https://docs.discord.com/developers/components/reference
    """

    __slots__ = ("_groups",)

    is_v2: ClassVar[bool] = True

    width: ClassVar[int] = 1
    """How much of an action row the menu takes: as much as a button."""

    def __init__(self, *groups: OverflowMenuGroup, id: int | None = None) -> None:
        """A menu of `groups`, in order.

        Raises:
            TypeError: A group is not an `OverflowMenuGroup`.
            ValueError: A group already belongs to another menu.
        """
        super().__init__(id=id)
        self._groups: list[OverflowMenuGroup] = []
        for group in groups:
            self.add_group(group)

    @property
    def groups(self) -> list[OverflowMenuGroup]:
        """The groups, in order."""
        return list(self._groups)

    @property
    @override
    def children(self) -> list[Item]:
        """Every group's actions, in order."""
        return [item for group in self._groups for item in group.items]

    def add_group(self, group: OverflowMenuGroup) -> Self:
        """Add a group of actions.

        Raises:
            TypeError: `group` is not an `OverflowMenuGroup`, or an action declared on it has no owner
                in this menu's view (the menu is left as it was).
            ValueError: `group` already belongs to another menu.
        """
        group = _group(group)
        if group.menu is not None and group.menu is not self:
            msg = f"{group!r} already belongs to {group.menu!r}"
            raise ValueError(msg)
        if group.menu is self:
            return self
        self._groups.append(group)
        group.join(self)
        if self.view is not None:
            try:
                group.bind_pending(self.view)
            except TypeError:
                self.remove_group(group)
                raise
        return self

    def remove_group(self, group: OverflowMenuGroup) -> Self:
        """Remove a group (nothing happens if it is not in the menu)."""
        if group in self._groups:
            self._groups.remove(group)
            group.join(None)
        return self

    def add_action(
        self,
        *,
        label: str,
        style: MenuActionItemStyle = MenuActionItemStyle.DEFAULT,
        custom_id: str | None = None,
        url: str | None = None,
        description: str | None = None,
        emoji: EmojiLike | None = None,
        id: int | None = None,
    ) -> MenuActionItem:
        """Add an action to the last group (a new group without a label when there is none), and return it."""
        if not self._groups:
            self.add_group(OverflowMenuGroup())
        item = MenuActionItem(
            label=label,
            style=style,
            custom_id=custom_id,
            url=url,
            description=description,
            emoji=emoji,
            id=id,
        )
        self._groups[-1].add_item(item)
        return item

    @override
    def attach(self, view: ItemView | None) -> None:
        super().attach(view)
        if view is not None:
            for group in self._groups:
                group.bind_pending(view)

    @override
    def to_component(self) -> OverflowMenuPayload:
        """The menu as Discord takes it."""
        return OverflowMenuPayload(
            id=unset_if_none(self.id), groups=[group.to_payload() for group in self._groups]
        )

    @override
    def __repr__(self) -> str:
        return f"<OverflowMenu groups={len(self._groups)}>"


def _action(item: object) -> MenuActionItem:
    if not isinstance(item, MenuActionItem):
        msg = f"an overflow menu group holds menu action items, not {item!r}"
        raise TypeError(msg)
    return item


def _group(group: object) -> OverflowMenuGroup:
    if not isinstance(group, OverflowMenuGroup):
        msg = f"an overflow menu holds groups, not {group!r}"
        raise TypeError(msg)
    return group
