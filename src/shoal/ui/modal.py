"""Modals: a popup form, shown in answer to a command or a component.

    class Feedback(ui.Modal, title="Feedback"):
        name = ui.TextInput(label="Name")
        body = ui.TextInput(label="Your feedback", style=TextInputStyle.PARAGRAPH)
        topic = ui.Label("Topic", ui.Select(options=[...]))

        async def on_submit(self, interaction: Interaction) -> None:
            await interaction.response.send_message(f"Thanks, {self.name.value}!", ephemeral=True)

    await interaction.response.send_modal(Feedback())

A modal holds up to five labels and text displays. A text input added directly is shown under its
own `label`; any other input goes in a `ui.Label`.

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-modal
"""

import logging
from collections.abc import Callable, Iterator
from typing import ClassVar, Self, override

from shoal.client.interaction import Interaction
from shoal.client.views import SubmittableModal
from shoal.core.clock import Clock, SystemClock
from shoal.core.tasks import spawn
from shoal.models.base import unset_if_none
from shoal.payloads.components import Label as LabelPayload
from shoal.payloads.components import (
    ModalComponent,
    SubmittedActionRow,
    SubmittedLabel,
    parse_submitted_components,
)
from shoal.payloads.interactions import (
    MODAL_MAX_COMPONENTS,
    MODAL_TITLE_MAX_LENGTH,
    ModalSubmitInteraction,
    ResolvedData,
)
from shoal.payloads.interactions import Modal as ModalPayload
from shoal.ui.content import TextDisplay
from shoal.ui.item import (
    InteractiveItem,
    Item,
    check_length,
    instantiate,
    item_templates,
    random_custom_id,
    submitted_values,
)
from shoal.ui.label import Label
from shoal.ui.lifetime import Lifetime
from shoal.ui.text_input import TextInput

_log = logging.getLogger("shoal.ui")

type ModalItem = Label | TextDisplay | TextInput
"""What a modal holds at the top level; a text input is shown under its own label."""


class Modal(SubmittableModal):
    """A popup form; `on_submit` runs when the user sends it.

    Give the title as a class keyword (`class Feedback(ui.Modal, title="Feedback")`) or to the
    constructor. Items declared on the class are copied for each modal, so each has its own values.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-modal
    """

    # A subclass's items are set as attributes; subclasses get a __dict__ by not declaring slots.
    __slots__ = (
        "_children",
        "_custom_id",
        "_lifetime",
        "title",
    )

    __modal_title__: ClassVar[str | None] = None
    __modal_items__: ClassVar[list[tuple[str, Item]]] = []

    @override
    def __init_subclass__(cls, *, title: str | None = None) -> None:
        """Remember the class's title and items, base classes first."""
        super().__init_subclass__()
        if title is not None:
            cls.__modal_title__ = title
        cls.__modal_items__ = item_templates(cls)

    def __init__(
        self,
        *,
        title: str | None = None,
        timeout: float | None = None,
        custom_id: str | None = None,
        clock: Clock | None = None,
    ) -> None:
        """A modal titled `title` (up to 45 characters; the class keyword when not given).

        Raises:
            TypeError: Neither the class nor the constructor gave a title.
        """
        chosen = title or type(self).__modal_title__
        if chosen is None:
            msg = f"{type(self).__name__} needs a title: Modal(title=...) or class keyword title=..."
            raise TypeError(msg)
        self.title: str = chosen
        self._custom_id: str = custom_id or random_custom_id()
        self._children: list[ModalItem] = []
        self._lifetime: Lifetime = Lifetime(timeout, clock=clock or SystemClock())
        for item in instantiate(self, type(self).__modal_items__):
            self.add_item(_modal_item(item))

    @property
    @override
    def custom_id(self) -> str:
        return self._custom_id

    @property
    def children(self) -> list[ModalItem]:
        """The top-level items, in order."""
        return list(self._children)

    def walk_children(self) -> Iterator[Item]:
        """Every item, at any depth, labels before their inputs."""
        for child in self._children:
            yield child
            yield from child.walk()

    def find_item(self, id: int, /) -> Item | None:
        """The item with component `id`, at any depth."""
        return next((item for item in self.walk_children() if item.id == id), None)

    def add_item(self, item: ModalItem) -> Self:
        """Add a label, a text display, or a text input (shown under its own label).

        Raises:
            TypeError: `item` cannot be at the top of a modal (put inputs in a `ui.Label`).
            ValueError: The modal already holds five items.
        """
        item = _modal_item(item)
        if len(self._children) >= MODAL_MAX_COMPONENTS:
            msg = f"a modal holds at most {MODAL_MAX_COMPONENTS} items"
            raise ValueError(msg)
        self._children.append(item)
        return self

    def remove_item(self, item: ModalItem) -> Self:
        """Remove an item (nothing happens if it is not in the modal)."""
        if item in self._children:
            self._children.remove(item)
        return self

    @override
    def to_modal(self) -> ModalPayload:
        """The modal to show. Showing it also starts its timeout.

        Raises:
            ValueError: An item is outside Discord's limits, or a custom ID is used twice.
        """
        check_length(self, "title", self.title, MODAL_TITLE_MAX_LENGTH)
        for child in self._children:
            child.validate()
        seen: set[str] = set()
        for item in self.walk_children():
            if isinstance(item, InteractiveItem):
                if item.custom_id in seen:
                    msg = f"{item!r}: another input of the modal has custom_id {item.custom_id!r}"
                    raise ValueError(msg)
                seen.add(item.custom_id)
        self._lifetime.restart()
        return ModalPayload(
            custom_id=self._custom_id,
            title=self.title,
            components=[_modal_component(item) for item in self._children],
        )

    @override
    def is_finished(self) -> bool:
        return self._lifetime.finished

    @override
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

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Decide whether a submission is accepted; the default accepts it."""
        del interaction
        return True

    async def on_submit(self, interaction: Interaction) -> None:
        """Runs when the modal is submitted; the inputs hold the values. Answer the interaction here."""
        del interaction

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        """Runs when `on_submit` raises; the default logs it."""
        del interaction
        _log.error("modal %r: on_submit raised", self, exc_info=error)

    @override
    async def dispatch(self, interaction: Interaction) -> None:
        """Fill the inputs from the submission, then run `on_submit` in its own task."""
        data = interaction.payload
        if not isinstance(data, ModalSubmitInteraction):
            return
        resolved = data.data.resolved if isinstance(data.data.resolved, ResolvedData) else None
        by_id = {item.custom_id: item for item in self.walk_children() if isinstance(item, InteractiveItem)}
        for component in parse_submitted_components(data.data.components):
            if isinstance(component, SubmittedLabel):
                submitted = [component.component]
            elif isinstance(component, SubmittedActionRow):
                submitted = list(component.components)
            else:
                continue
            for value in submitted:
                item = by_id.get(value.custom_id)
                if item is not None:
                    item.refresh(interaction, submitted_values(value), resolved)
        _ = spawn(self._submit(interaction), name=f"shoal-modal-{self._custom_id}")

    async def _submit(self, interaction: Interaction) -> None:
        try:
            if await self.interaction_check(interaction):
                await self.on_submit(interaction)
        except Exception as error:  # noqa: BLE001 - handed to on_error
            await self.on_error(interaction, error)
        finally:
            self.stop()

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__} title={self.title!r} items={len(self._children)}>"


def _modal_item(item: Item) -> ModalItem:
    if not isinstance(item, Label | TextDisplay | TextInput):
        msg = f"a modal holds labels, text displays and text inputs, not {item!r}; put inputs in a ui.Label"
        raise TypeError(msg)
    return item


def _modal_component(item: ModalItem) -> ModalComponent:
    """`item` as Discord takes it in a modal: a text input in a label of its own.

    Raises:
        ValueError: A text input added directly has no label.
    """
    if not isinstance(item, TextInput):
        return item.to_component()
    if item.label is None:
        msg = f"{item!r}: a text input added to a modal directly needs a label (or put it in a ui.Label)"
        raise ValueError(msg)
    return LabelPayload(
        label=item.label, description=unset_if_none(item.description), component=item.to_component()
    )
