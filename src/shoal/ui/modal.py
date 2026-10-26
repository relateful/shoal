"""Modals: a popup form, shown in answer to a command or a component.

    class Feedback(ui.Modal, title="Feedback"):
        name = ui.TextInput(label="Name")
        body = ui.TextInput(label="Your feedback", style=TextInputStyle.PARAGRAPH)

        async def on_submit(self, interaction: Interaction) -> None:
            await interaction.response.send_message(f"Thanks, {self.name.value}!", ephemeral=True)

    await interaction.response.send_modal(Feedback())

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-modal
"""

import copy
import logging
from collections.abc import Callable
from typing import ClassVar, Self, override

from shoal.client.interaction import Interaction
from shoal.client.views import SubmittableModal
from shoal.core.clock import Clock, SystemClock
from shoal.core.tasks import spawn
from shoal.payloads.components import (
    SubmittedActionRow,
    SubmittedLabel,
    SubmittedTextInput,
    parse_submitted_components,
)
from shoal.payloads.interactions import (
    MODAL_MAX_COMPONENTS,
    MODAL_TITLE_MAX_LENGTH,
    ModalSubmitInteraction,
    ResolvedData,
)
from shoal.payloads.interactions import Modal as ModalPayload
from shoal.ui.item import check_length, random_custom_id
from shoal.ui.lifetime import Lifetime
from shoal.ui.text_input import TextInput

_log = logging.getLogger("shoal.ui")


class Modal(SubmittableModal):
    """A popup form of text inputs; `on_submit` runs when the user sends it.

    Give the title as a class keyword (`class Feedback(ui.Modal, title="Feedback")`) or to the
    constructor. Inputs declared on the class are copied for each modal, so each has its own values.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-modal
    """

    # A subclass's inputs are set as attributes; subclasses get a __dict__ by not declaring slots.
    __slots__ = (
        "_children",
        "_custom_id",
        "_lifetime",
        "title",
    )

    __modal_title__: ClassVar[str | None] = None
    __modal_inputs__: ClassVar[list[tuple[str, TextInput]]] = []

    @override
    def __init_subclass__(cls, *, title: str | None = None) -> None:
        """Remember the class's title and inputs, base classes first."""
        super().__init_subclass__()
        if title is not None:
            cls.__modal_title__ = title
        found: dict[str, TextInput] = {}
        for base in reversed(cls.__mro__):
            found.update(
                (name, member) for name, member in vars(base).items() if isinstance(member, TextInput)
            )
        cls.__modal_inputs__ = list(found.items())

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
        self._children: list[TextInput] = []
        self._lifetime: Lifetime = Lifetime(timeout, clock=clock or SystemClock())
        for name, template in type(self).__modal_inputs__:
            own = copy.copy(template)
            setattr(self, name, own)
            self.add_item(own)

    @property
    @override
    def custom_id(self) -> str:
        return self._custom_id

    @property
    def children(self) -> list[TextInput]:
        """The inputs, in order."""
        return list(self._children)

    def add_item(self, item: TextInput) -> Self:
        """Add an input.

        Raises:
            ValueError: The modal already holds five inputs.
        """
        if len(self._children) >= MODAL_MAX_COMPONENTS:
            msg = f"a modal holds at most {MODAL_MAX_COMPONENTS} inputs"
            raise ValueError(msg)
        self._children.append(item)
        return self

    def remove_item(self, item: TextInput) -> Self:
        """Remove an input (nothing happens if it is not in the modal)."""
        if item in self._children:
            self._children.remove(item)
        return self

    @override
    def to_modal(self) -> ModalPayload:
        """The modal to show. Showing it also starts its timeout."""
        check_length(self, "title", self.title, MODAL_TITLE_MAX_LENGTH)
        for item in self._children:
            item.validate()
        self._lifetime.restart()
        return ModalPayload(
            custom_id=self._custom_id,
            title=self.title,
            components=[item.to_component() for item in self._children],
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
        by_id = {item.custom_id: item for item in self._children}
        for component in parse_submitted_components(data.data.components):
            inputs: list[SubmittedTextInput] = []
            if isinstance(component, SubmittedLabel) and isinstance(component.component, SubmittedTextInput):
                inputs.append(component.component)
            elif isinstance(component, SubmittedActionRow):
                inputs.extend(component.components)
            for submitted in inputs:
                item = by_id.get(submitted.custom_id)
                if item is not None:
                    item.refresh(interaction, [submitted.value], resolved)
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
        return f"<{type(self).__name__} title={self.title!r} inputs={len(self._children)}>"
