"""Routing component and modal interactions to the views and modals that sent them.

`shoal.ui.View` and `shoal.ui.Modal` implement the protocols here; the client keeps a `ViewStore`
and hands it every component and modal interaction. A view sent with a message is matched by
custom ID on that message; a persistent view (no timeout, every item with a fixed custom ID) added
with `Client.add_view` matches its custom IDs on any message, across restarts.

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding
"""

import logging
from collections.abc import Collection
from typing import TYPE_CHECKING, Protocol, final, override, runtime_checkable

from shoal.models.state import ComponentView, ViewRegistry
from shoal.payloads.interactions import Modal

if TYPE_CHECKING:
    from shoal.client.interaction import Interaction

_log = logging.getLogger("shoal.client")


@runtime_checkable
class DispatchableView(ComponentView, Protocol):
    """A view the store can route interactions to: `ui.View`."""

    def custom_ids(self) -> Collection[str]:
        """The custom IDs of the view's interactive components."""
        ...

    def is_persistent(self) -> bool:
        """Whether the view outlives its message: no timeout, and every custom ID chosen by hand."""
        ...

    def is_finished(self) -> bool:
        """Whether the view stopped or timed out, so it no longer receives interactions."""
        ...

    async def dispatch(self, interaction: "Interaction", custom_id: str) -> None:
        """Run the callback of the component with `custom_id`."""
        ...


@runtime_checkable
class SubmittableModal(Protocol):
    """A modal the store can route its submission to: `ui.Modal`."""

    @property
    def custom_id(self) -> str:
        """The modal's custom ID."""
        ...

    def to_modal(self) -> Modal:
        """The modal as Discord shows it."""
        ...

    def is_finished(self) -> bool:
        """Whether the modal stopped or timed out."""
        ...

    async def dispatch(self, interaction: "Interaction") -> None:
        """Handle the submission."""
        ...


type _ViewKey = tuple[str, int | None]
"""A custom ID and the message it is on (`None`: any message)."""


@final
class ViewStore(ViewRegistry):
    """Keeps views and modals, and routes their interactions to them."""

    __slots__ = ("_modals", "_views")

    def __init__(self) -> None:
        """Create an empty store."""
        self._views: dict[_ViewKey, DispatchableView] = {}
        self._modals: dict[tuple[int, str], SubmittableModal] = {}

    @override
    def store(self, view: ComponentView, *, message_id: int | None) -> None:
        """Route interactions with `view`'s custom IDs on `message_id` (any message, for `None`)."""
        if not isinstance(view, DispatchableView):
            return
        for custom_id in view.custom_ids():
            self._views[(custom_id, message_id)] = view

    def store_modal(self, modal: SubmittableModal, *, user_id: int) -> None:
        """Route `user_id`'s submission of `modal` to it."""
        self._modals[(user_id, modal.custom_id)] = modal

    def remove(self, view: DispatchableView) -> None:
        """Stop routing to `view`."""
        for key in [key for key, stored in self._views.items() if stored is view]:
            del self._views[key]

    @property
    def persistent_views(self) -> list[DispatchableView]:
        """The views stored for any message."""
        found: list[DispatchableView] = []
        for (_, message_id), view in self._views.items():
            if message_id is None and view.is_persistent() and view not in found:
                found.append(view)
        return found

    async def dispatch_component(
        self, interaction: "Interaction", custom_id: str, message_id: int | None
    ) -> bool:
        """Run the view that owns `custom_id` on that message. Returns whether one did."""
        view = self._views.get((custom_id, message_id)) or self._views.get((custom_id, None))
        if view is None:
            return False
        if view.is_finished():
            self.remove(view)
            return False
        await view.dispatch(interaction, custom_id)
        if view.is_finished():
            self.remove(view)
        return True

    async def dispatch_modal(self, interaction: "Interaction", custom_id: str, user_id: int) -> bool:
        """Run the modal `user_id` submitted. Returns whether one was waiting."""
        modal = self._modals.pop((user_id, custom_id), None)
        if modal is None or modal.is_finished():
            return False
        await modal.dispatch(interaction)
        return True
