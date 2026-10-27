"""Views: a message's components, and what happens when they are used.

A `View` lays buttons and selects out in action rows:

    class Counter(ui.View):
        def __init__(self) -> None:
            super().__init__(timeout=60)
            self.count = 0

        @ui.button(label="+1", style=ButtonStyle.PRIMARY)
        async def add(self, interaction: Interaction, button: ui.Button) -> None:
            self.count += 1
            button.label = f"+1 ({self.count})"
            await interaction.response.edit_message(view=self)

    await channel.send("Count with me", view=Counter())

A `LayoutView` is the whole message, in Components V2: text, media, sections and containers, with
buttons and selects in action rows among them. It replaces the content and embeds.

    class Welcome(ui.LayoutView):
        text = ui.TextDisplay("# Welcome!")
        row = ui.ActionRow()

        @row.button(label="Get started", style=ButtonStyle.PRIMARY)
        async def start(self, interaction: Interaction, button: ui.Button) -> None: ...

A view stops after `timeout` seconds without an interaction (the timer restarts on each one), or
when `stop()` is called. A persistent view (`timeout=None`, every item with a `custom_id` of your
choosing) keeps working after a restart once added again with `client.add_view(view)`.

Discord: https://docs.discord.com/developers/components/reference
"""

import logging
from collections.abc import Callable, Collection, Iterator, Sequence
from typing import ClassVar, Final, Self, override

from msgspec import UnsetType

from shoal.client.interaction import Interaction
from shoal.client.views import DispatchableView
from shoal.core.clock import Clock, SystemClock
from shoal.core.tasks import spawn
from shoal.payloads.components import (
    ACTION_ROW_MAX_BUTTONS,
    LEGACY_MESSAGE_MAX_ACTION_ROWS,
    MESSAGE_MAX_COMPONENTS,
    ActionRowChild,
    MessageComponent,
)
from shoal.payloads.components import ActionRow as ActionRowPayload
from shoal.payloads.interactions import ComponentInteraction, ResolvedData
from shoal.ui.action_row import ActionRow, RowItem, row_item
from shoal.ui.content import File, MediaGallery, Separator, TextDisplay
from shoal.ui.defaults import VIEW_TIMEOUT
from shoal.ui.item import (
    ITEM_FACTORY,
    Decorated,
    InteractiveItem,
    Item,
    bind_method,
    decorated_methods,
    instantiate,
    item_templates,
)
from shoal.ui.layout import Container, Section
from shoal.ui.lifetime import Lifetime

_log = logging.getLogger("shoal.ui")

MAX_ITEMS: Final = ACTION_ROW_MAX_BUTTONS * LEGACY_MESSAGE_MAX_ACTION_ROWS
"""The most items a `View` can hold: five rows of five buttons."""


class BaseView[T: Item](DispatchableView):
    """What `View` and `LayoutView` share: their items, their lifetime, and routing interactions.

    Discord: https://docs.discord.com/developers/components/reference
    """

    # Subclasses that add attributes of their own get a __dict__ by not declaring slots.
    __slots__ = ("_children", "_lifetime")

    def __init__(self, *, timeout: float | None = VIEW_TIMEOUT, clock: Clock | None = None) -> None:
        """A view that stops after `timeout` seconds without an interaction (`None`: never)."""
        self._children: list[T] = []
        self._lifetime: Lifetime = Lifetime(
            timeout,
            clock=clock or SystemClock(),
            on_timeout=lambda: spawn(self._run_timeout(), name="shoal-view-timeout"),
        )

    @property
    def children(self) -> list[T]:
        """The top-level items, in the order they were added."""
        return list(self._children)

    def walk_children(self) -> Iterator[Item]:
        """Every item, at any depth, parents before their children."""
        for child in self._children:
            yield child
            yield from child.walk()

    def find_item(self, id: int, /) -> Item | None:
        """The item with component `id`, at any depth."""
        return next((item for item in self.walk_children() if item.id == id), None)

    def remove_item(self, item: T) -> Self:
        """Remove a top-level item (nothing happens if it is not in the view)."""
        if item in self._children:
            self._children.remove(item)
            item.attach(None)
        return self

    def clear_items(self) -> Self:
        """Remove every item."""
        for item in self._children:
            item.attach(None)
        self._children.clear()
        return self

    def _append(self, item: T) -> None:
        item.attach(self)
        self._children.append(item)

    def _interactive(self) -> Iterator[InteractiveItem]:
        return (
            item
            for item in self.walk_children()
            if isinstance(item, InteractiveItem) and item.is_dispatchable()
        )

    def _validate(self) -> None:
        """Check every item, and that no custom ID or component ID is used twice.

        Raises:
            ValueError: An item is outside Discord's limits, or an ID is used twice.
        """
        for child in self._children:
            child.validate()
        custom_ids: set[str] = set()
        for item in self._interactive():
            if item.custom_id in custom_ids:
                msg = f"{item!r}: another item of the view has custom_id {item.custom_id!r}"
                raise ValueError(msg)
            custom_ids.add(item.custom_id)
        ids: set[int] = set()
        for component in self.walk_children():
            # Discord treats an id of 0 as unset.
            if component.id:
                if component.id in ids:
                    msg = f"{component!r}: another item of the view has id {component.id}"
                    raise ValueError(msg)
                ids.add(component.id)

    @property
    def timeout(self) -> float | None:
        """Seconds without an interaction before the view stops; `None` never stops."""
        return self._lifetime.timeout

    @timeout.setter
    def timeout(self, value: float | None) -> None:
        self._lifetime.timeout = value

    @override
    def is_dispatchable(self) -> bool:
        return any(True for _ in self._interactive())

    @override
    def custom_ids(self) -> Collection[str]:
        return [item.custom_id for item in self._interactive()]

    @override
    def is_persistent(self) -> bool:
        return self.timeout is None and all(item.is_persistent() for item in self._interactive())

    @override
    def is_finished(self) -> bool:
        return self._lifetime.finished

    def stop(self) -> None:
        """Stop receiving interactions; does nothing the second time."""
        self._lifetime.stop()

    @override
    def when_finished(self, callback: Callable[[], object], /) -> None:
        """Run `callback` once when it stops; now if it already has."""
        self._lifetime.when_finished(callback)

    async def wait(self) -> bool:
        """Wait until it stops; returns whether it timed out."""
        return await self._lifetime.wait()

    async def _run_timeout(self) -> None:
        try:
            await self.on_timeout()
        except Exception:  # noqa: BLE001 - logged; a timeout handler must not crash the loop
            _log.exception("view %r: on_timeout raised", self)

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Decide whether an interaction may use the view; the default allows everyone.

        Return `False` (after answering it, ideally) to ignore the interaction.
        """
        del interaction
        return True

    async def on_timeout(self) -> None:
        """Runs when the view times out; the default does nothing."""

    async def on_error(self, interaction: Interaction, error: Exception, item: InteractiveItem) -> None:
        """Runs when an item's callback raises; the default logs it."""
        del interaction
        _log.error("view %r: the callback of %r raised", self, item, exc_info=error)

    @override
    async def dispatch(self, interaction: Interaction, custom_id: str) -> bool:
        """Route an interaction to the item with `custom_id`, in its own task; whether it has one."""
        item = next((child for child in self._interactive() if child.custom_id == custom_id), None)
        if item is None or self._lifetime.finished:
            return False
        _ = spawn(self._run(interaction, item), name=f"shoal-view-{custom_id}")
        return True

    async def _run(self, interaction: Interaction, item: InteractiveItem) -> None:
        try:
            # Checked first: an interaction the view refuses changes nothing, not even its timeout.
            if not await self.interaction_check(interaction):
                return
            data = interaction.payload
            if isinstance(data, ComponentInteraction):
                values = data.data.values if not isinstance(data.data.values, UnsetType) else []
                resolved = data.data.resolved if isinstance(data.data.resolved, ResolvedData) else None
                item.refresh(interaction, values, resolved)
            self._lifetime.restart()
            await item.invoke(interaction)
        except Exception as error:  # noqa: BLE001 - handed to on_error
            await self.on_error(interaction, error, item)

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__} items={len(self._children)} timeout={self.timeout}>"


class View(BaseView[RowItem]):
    """Buttons and selects sent with a message, laid out in up to five action rows.

    Discord: https://docs.discord.com/developers/components/reference#action-row
    """

    __slots__ = ()

    __view_items__: ClassVar[list[Decorated]] = []

    @override
    def __init_subclass__(cls) -> None:
        """Collect the methods decorated with `@ui.button` and `@ui.select`, base classes first.

        A subclass that redefines one without the decorator removes its item.
        """
        super().__init_subclass__()
        cls.__view_items__ = decorated_methods(cls)

    def __init__(self, *, timeout: float | None = VIEW_TIMEOUT, clock: Clock | None = None) -> None:
        """A view that stops after `timeout` seconds without an interaction (`None`: never)."""
        super().__init__(timeout=timeout, clock=clock)
        for method in type(self).__view_items__:
            factory: Callable[[], InteractiveItem] = getattr(method, ITEM_FACTORY)
            item = factory()
            item.bind(bind_method(method, self, item))
            self.add_item(row_item(item))

    def add_item(self, item: RowItem) -> Self:
        """Add a button or select, placed in its `row` or in the first row with room.

        Raises:
            TypeError: `item` is not a button or a select (`LayoutView` takes the rest).
            ValueError: The view is full (25 items, or no row has room for this one).
        """
        item = row_item(item)
        if len(self._children) >= MAX_ITEMS:
            msg = f"a view holds at most {MAX_ITEMS} items"
            raise ValueError(msg)
        _arrange([*self._children, item])
        self._append(item)
        return self

    @override
    def to_components(self) -> list[MessageComponent]:
        """The action rows to send. Sending the view also starts its timeout."""
        self._validate()
        self._lifetime.restart()
        rows: list[MessageComponent] = []
        for row in _arrange(self._children):
            children: list[ActionRowChild] = [item.to_component() for item in row]
            rows.append(ActionRowPayload(components=children))
        return rows


type LayoutItem = ActionRow | Container | Section | TextDisplay | MediaGallery | File | Separator
"""What a `LayoutView` holds at the top level."""


class LayoutView(BaseView[LayoutItem]):
    """A whole message in Components V2: text, media, sections, containers and action rows.

    Declare its items as class attributes (each view gets its own copies), or add them with
    `add_item`. Buttons and selects go in an `ActionRow` (a button can also be a section's
    accessory); decorate their methods through the row: `@row.button(...)`.

    Discord: https://docs.discord.com/developers/components/reference
    """

    __slots__ = ()

    __layout_items__: ClassVar[list[tuple[str, Item]]] = []

    @override
    def __init_subclass__(cls) -> None:
        """Remember the items declared on the class, base classes first.

        Raises:
            TypeError: A method is decorated with `@ui.button` or `@ui.select` directly.
        """
        super().__init_subclass__()
        stray = decorated_methods(cls)
        if stray:
            msg = (
                f"{cls.__name__}.{stray[0].__name__}: a layout view's buttons and selects go in an "
                "action row; declare `row = ui.ActionRow()` and decorate with `@row.button(...)`"
            )
            raise TypeError(msg)
        cls.__layout_items__ = item_templates(cls)

    def __init__(self, *, timeout: float | None = VIEW_TIMEOUT, clock: Clock | None = None) -> None:
        """A view of the class's items that stops after `timeout` seconds without an interaction.

        Raises:
            TypeError: An item declared on the class cannot be at the top of a message.
        """
        super().__init__(timeout=timeout, clock=clock)
        for item in instantiate(self, type(self).__layout_items__):
            self.add_item(_layout_item(item))

    def add_item(self, item: LayoutItem) -> Self:
        """Add a top-level item.

        Raises:
            TypeError: `item` cannot be at the top of a message (a button or a select needs an
                action row; a thumbnail needs a section).
        """
        self._append(_layout_item(item))
        return self

    def has_components_v2(self) -> bool:
        """Whether the view needs a Components V2 message: anything but action rows does."""
        return any(item.is_v2 for item in self.walk_children())

    @override
    def to_components(self) -> list[MessageComponent]:
        """The components to send. Sending the view also starts its timeout.

        Raises:
            ValueError: An item is outside Discord's limits, or the message holds too many components.
        """
        self._validate()
        if self.has_components_v2():
            total = sum(child.count() for child in self._children)
            if total > MESSAGE_MAX_COMPONENTS:
                msg = f"{self!r}: a message holds at most {MESSAGE_MAX_COMPONENTS} components, not {total}"
                raise ValueError(msg)
        elif len(self._children) > LEGACY_MESSAGE_MAX_ACTION_ROWS:
            msg = f"{self!r}: a message of action rows only holds {LEGACY_MESSAGE_MAX_ACTION_ROWS} of them"
            raise ValueError(msg)
        self._lifetime.restart()
        return [child.to_component() for child in self._children]


def _layout_item(item: Item) -> LayoutItem:
    if not isinstance(item, ActionRow | Container | Section | TextDisplay | MediaGallery | File | Separator):
        msg = (
            f"{item!r} cannot be at the top of a message: put a button or a select in an ActionRow, "
            "and a thumbnail in a Section"
        )
        raise TypeError(msg)
    return item


def _arrange(items: Sequence[RowItem]) -> list[list[RowItem]]:
    """Lay the items out in action rows: those with a `row` there, the rest in the first with room.

    Raises:
        ValueError: An item does not fit in its row, or no row has room for it.
    """
    rows: list[list[RowItem]] = [[] for _ in range(LEGACY_MESSAGE_MAX_ACTION_ROWS)]
    widths = [0] * LEGACY_MESSAGE_MAX_ACTION_ROWS
    for item in items:
        row = item.row
        if row is None:
            continue
        if widths[row] + item.width > ACTION_ROW_MAX_BUTTONS:
            msg = f"row {row} has no room for {item!r}"
            raise ValueError(msg)
        rows[row].append(item)
        widths[row] += item.width
    for item in (item for item in items if item.row is None):
        free = next(
            (index for index, width in enumerate(widths) if width + item.width <= ACTION_ROW_MAX_BUTTONS),
            None,
        )
        if free is None:
            msg = f"no row has room for {item!r}"
            raise ValueError(msg)
        rows[free].append(item)
        widths[free] += item.width
    return [row for row in rows if row]
