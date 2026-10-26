"""Routing component and modal interactions to the views and modals that sent them.

`shoal.ui.View` and `shoal.ui.Modal` implement the protocols here; the client keeps a `ViewStore`
and hands it every component and modal interaction. A view sent with a message is matched by
custom ID on that message; a persistent view (no timeout, every item with a fixed custom ID) added
with `Client.add_view` matches its custom IDs on any message, across restarts.

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding
"""

import logging
from collections.abc import Callable, Collection
from typing import TYPE_CHECKING, Final, Protocol, final, override, runtime_checkable

from shoal.models.state import ComponentView, ViewRegistry
from shoal.payloads.interactions import Modal

if TYPE_CHECKING:
    from shoal.client.interaction import Interaction

_log = logging.getLogger("shoal.client")

PENDING_MODALS_PER_USER: Final = 5
"""Modals a user can have open and unsubmitted at once; opening another stops the oldest."""


@runtime_checkable
class DispatchableView(ComponentView, Protocol):
    """A view the store can route interactions to: `ui.View`."""

    __slots__ = ()

    def custom_ids(self) -> Collection[str]:
        """The custom IDs of the view's interactive components."""
        ...

    def is_persistent(self) -> bool:
        """Whether the view outlives its message: no timeout, and every custom ID chosen by hand."""
        ...

    def is_finished(self) -> bool:
        """Whether the view stopped or timed out, so it no longer receives interactions."""
        ...

    def when_finished(self, callback: Callable[[], object], /) -> None:
        """Run `callback` once when the view stops or times out."""
        ...

    async def dispatch(self, interaction: "Interaction", custom_id: str) -> bool:
        """Run the callback of the component with `custom_id`; whether the view has one."""
        ...


@runtime_checkable
class SubmittableModal(Protocol):
    """A modal the store can route its submission to: `ui.Modal`."""

    __slots__ = ()

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

    def when_finished(self, callback: Callable[[], object], /) -> None:
        """Run `callback` once when the modal is submitted, stops or times out."""
        ...

    def stop(self) -> None:
        """Stop waiting for a submission."""
        ...

    async def dispatch(self, interaction: "Interaction") -> None:
        """Handle the submission."""
        ...


type _ViewKey = tuple[str, int | None]
"""A custom ID and the message it is on (`None`: any message)."""


@final
class ViewStore(ViewRegistry):
    """Keeps views and modals, and routes their interactions to them."""

    __slots__ = ("_keys", "_modals", "_pending_modals", "_views")

    def __init__(self) -> None:
        """Create an empty store."""
        self._views: dict[_ViewKey, DispatchableView] = {}
        self._keys: dict[int, tuple[DispatchableView, set[_ViewKey]]] = {}
        """Each stored view (by `id`) and its keys, so removing one never scans the store."""
        self._modals: dict[tuple[int, str], SubmittableModal] = {}
        self._pending_modals: dict[int, list[str]] = {}
        """Each user's waiting modals' custom IDs, oldest first."""

    @override
    def store(self, view: ComponentView, *, message_id: int | None) -> None:
        """Route interactions with `view`'s custom IDs on `message_id` (any message, for `None`).

        The view is forgotten when it stops or times out; one that already has is not stored.
        """
        if not isinstance(view, DispatchableView) or view.is_finished():
            return
        known = self._keys.get(id(view))
        if known is None:
            keys: set[_ViewKey] = set()
            known = (view, keys)
            self._keys[id(view)] = known
            view.when_finished(lambda: self.remove(view))
        for custom_id in view.custom_ids():
            key = (custom_id, message_id)
            self._views[key] = view
            known[1].add(key)

    def store_modal(self, modal: SubmittableModal, *, user_id: int) -> None:
        """Route `user_id`'s submission of `modal` to it.

        A user has at most `PENDING_MODALS_PER_USER` modals waiting; opening another stops the
        oldest, so modals people close without submitting never pile up.
        """
        key = (user_id, modal.custom_id)
        replaced = self._modals.get(key)
        if replaced is modal:
            return
        self._modals[key] = modal
        pending = self._pending_modals.setdefault(user_id, [])
        if replaced is None:
            pending.append(modal.custom_id)
        else:
            replaced.stop()
        modal.when_finished(lambda: self._forget_modal(key, modal))
        if len(pending) > PENDING_MODALS_PER_USER:
            self._modals[(user_id, pending[0])].stop()

    def _forget_modal(self, key: tuple[int, str], modal: SubmittableModal) -> None:
        if self._modals.get(key) is not modal:
            return
        del self._modals[key]
        pending = self._pending_modals[key[0]]
        pending.remove(key[1])
        if not pending:
            del self._pending_modals[key[0]]

    def remove(self, view: DispatchableView) -> None:
        """Stop routing to `view`."""
        known = self._keys.pop(id(view), None)
        if known is None:
            return
        for key in known[1]:
            if self._views.get(key) is view:
                del self._views[key]

    @property
    def persistent_views(self) -> list[DispatchableView]:
        """The views stored for any message."""
        return [
            view
            for view, keys in self._keys.values()
            if view.is_persistent() and any(message_id is None for _, message_id in keys)
        ]

    async def dispatch_component(
        self, interaction: "Interaction", custom_id: str, message_id: int | None
    ) -> bool:
        """Run the view that owns `custom_id` on that message. Returns whether one did."""
        view = self._views.get((custom_id, message_id)) or self._views.get((custom_id, None))
        if view is None:
            return False
        return await view.dispatch(interaction, custom_id)

    async def dispatch_modal(self, interaction: "Interaction", custom_id: str, user_id: int) -> bool:
        """Run the modal `user_id` submitted. Returns whether one was waiting."""
        modal = self._modals.get((user_id, custom_id))
        if modal is None or modal.is_finished():
            return False
        await modal.dispatch(interaction)
        return True
