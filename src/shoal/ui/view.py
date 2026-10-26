"""Views: a message's buttons and selects, and what happens when they are used.

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

A view stops after `timeout` seconds without an interaction (the timer restarts on each one), or
when `stop()` is called. A persistent view (`timeout=None`, every item with a `custom_id` of your
choosing) keeps working after a restart once added again with `client.add_view(view)`.

Discord: https://docs.discord.com/developers/components/reference#action-row
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Collection, Sequence
from typing import ClassVar, Self, cast, override

from msgspec import UnsetType

from shoal.client.interaction import Interaction
from shoal.client.views import DispatchableView
from shoal.core.tasks import spawn
from shoal.payloads.components import (
    ACTION_ROW_MAX_BUTTONS,
    LEGACY_MESSAGE_MAX_ACTION_ROWS,
    ActionRow,
    ActionRowChild,
    Label,
    MessageComponent,
)
from shoal.payloads.interactions import ComponentInteraction, ResolvedData
from shoal.ui.defaults import VIEW_TIMEOUT
from shoal.ui.item import ITEM_FACTORY, Item

_log = logging.getLogger("shoal.ui")

MAX_ITEMS = ACTION_ROW_MAX_BUTTONS * LEGACY_MESSAGE_MAX_ACTION_ROWS
"""The most items a view can hold: five rows of five buttons."""

type _Factory = Callable[[], Item]
type _Decorated = Callable[..., Awaitable[None]]


class View(DispatchableView):
    """A set of buttons and selects sent with a message.

    Discord: https://docs.discord.com/developers/components/reference#action-row
    """

    # Subclasses usually add their own attributes; the protocol base already gives instances a __dict__.
    __slots__ = ("_children", "_finished", "_timed_out", "_timeout", "_timer", "_waiter")

    __view_items__: ClassVar[list[_Decorated]] = []

    @override
    def __init_subclass__(cls) -> None:
        """Collect the methods decorated with `@ui.button` and `@ui.select`, base classes first."""
        super().__init_subclass__()
        found: dict[str, _Decorated] = {}
        for base in reversed(cls.__mro__):
            found.update(
                (name, cast("_Decorated", member))
                for name, member in vars(base).items()
                if callable(member) and hasattr(member, ITEM_FACTORY)
            )
        cls.__view_items__ = list(found.values())

    def __init__(self, *, timeout: float | None = VIEW_TIMEOUT) -> None:
        """A view that stops after `timeout` seconds without an interaction (`None`: never)."""
        self._timeout: float | None = timeout
        self._children: list[Item] = []
        self._finished: bool = False
        self._timed_out: bool = False
        self._timer: asyncio.TimerHandle | None = None
        self._waiter: asyncio.Future[bool] | None = None
        for method in type(self).__view_items__:
            factory: _Factory = getattr(method, ITEM_FACTORY)
            item = factory()
            item.bind(_bind(method, self, item))
            self.add_item(item)

    @property
    def children(self) -> list[Item]:
        """The items, in the order they were added."""
        return list(self._children)

    def add_item(self, item: Item) -> Self:
        """Add an item, placed in its `row` or in the first row with room.

        Raises:
            ValueError: The view is full (25 items, or no row has room for this one).
        """
        if len(self._children) >= MAX_ITEMS:
            msg = f"a view holds at most {MAX_ITEMS} items"
            raise ValueError(msg)
        _arrange([*self._children, item])
        item.attach(self)
        self._children.append(item)
        return self

    def remove_item(self, item: Item) -> Self:
        """Remove an item (nothing happens if it is not in the view)."""
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

    @override
    def to_components(self) -> list[MessageComponent]:
        """The action rows to send. Sending the view also starts its timeout.

        Raises:
            TypeError: An item belongs in a modal (a text input), not in a message.
        """
        self._start_timer()
        rows: list[MessageComponent] = []
        for row in _arrange(self._children):
            children: list[ActionRowChild] = []
            for item in row:
                component = item.to_component()
                if isinstance(component, Label):
                    msg = f"{item!r} belongs in a modal, not in a message's view"
                    raise TypeError(msg)
                children.append(component)
            rows.append(ActionRow(components=children))
        return rows

    @property
    def timeout(self) -> float | None:
        """Seconds without an interaction before the view stops; `None` never stops."""
        return self._timeout

    @timeout.setter
    def timeout(self, value: float | None) -> None:
        self._timeout = value
        if self._timer is not None:
            self._start_timer()

    @override
    def is_dispatchable(self) -> bool:
        return any(item.is_dispatchable() for item in self._children)

    @override
    def custom_ids(self) -> Collection[str]:
        return [item.custom_id for item in self._children if item.is_dispatchable()]

    @override
    def is_persistent(self) -> bool:
        return self._timeout is None and all(item.is_persistent() for item in self._children)

    @override
    def is_finished(self) -> bool:
        return self._finished

    def stop(self) -> None:
        """Stop the view: it no longer receives interactions, and `wait()` returns."""
        if self._finished:
            return
        self._finished = True
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._waiter is not None and not self._waiter.done():
            self._waiter.set_result(self._timed_out)

    async def wait(self) -> bool:
        """Wait until the view stops; returns whether it timed out."""
        if self._finished:
            return self._timed_out
        if self._waiter is None:
            self._waiter = asyncio.get_running_loop().create_future()
        return await self._waiter

    def _start_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._timeout is None or self._finished:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # Rendered outside a loop (a test, a script); the timer starts on the first use.
        self._timer = loop.call_later(self._timeout, self._expire)

    def _expire(self) -> None:
        self._timer = None
        if self._finished:
            return
        self._timed_out = True
        self.stop()
        _ = spawn(self._run_timeout(), name="shoal-view-timeout")

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

    async def on_error(self, interaction: Interaction, error: Exception, item: Item) -> None:
        """Runs when an item's callback raises; the default logs it."""
        del interaction
        _log.error("view %r: the callback of %r raised", self, item, exc_info=error)

    @override
    async def dispatch(self, interaction: Interaction, custom_id: str) -> None:
        """Route an interaction to the item with `custom_id`, in its own task."""
        item = next((child for child in self._children if child.custom_id == custom_id), None)
        if item is None or self._finished:
            return
        data = interaction.payload
        if isinstance(data, ComponentInteraction):
            values = data.data.values if not isinstance(data.data.values, UnsetType) else []
            resolved = data.data.resolved if isinstance(data.data.resolved, ResolvedData) else None
            item.refresh(interaction, values, resolved)
        self._start_timer()
        _ = spawn(self._run(interaction, item), name=f"shoal-view-{custom_id}")

    async def _run(self, interaction: Interaction, item: Item) -> None:
        try:
            if not await self.interaction_check(interaction):
                return
            await item.invoke(interaction)
        except Exception as error:  # noqa: BLE001 - handed to on_error
            await self.on_error(interaction, error, item)

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__} items={len(self._children)} timeout={self._timeout}>"


def _bind(method: _Decorated, view: View, item: Item) -> Callable[[Interaction], Awaitable[None]]:
    """The decorated method, called as `(view, interaction, item)`."""

    async def handler(interaction: Interaction) -> None:
        await method(view, interaction, item)

    return handler


def _arrange(items: Sequence[Item]) -> list[list[Item]]:
    """Lay the items out in action rows: those with a `row` there, the rest in the first with room.

    Raises:
        ValueError: An item does not fit in its row, or no row has room for it.
    """
    rows: list[list[Item]] = [[] for _ in range(LEGACY_MESSAGE_MAX_ACTION_ROWS)]
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
