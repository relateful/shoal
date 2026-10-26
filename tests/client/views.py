from typing import override

from shoal.client.interaction import Interaction
from shoal.client.views import ViewStore
from tests.support.client import started
from tests.support.interactions import PersistentView, RecordingModal, component, payload
from tests.support.models import ALICE, BOB, ROW_VIEW


async def test_a_view_on_a_message_only_answers_for_that_message() -> None:
    client, _ = await started()
    store = ViewStore()
    view = PersistentView(persistent=False, custom_id="vote")
    store.store(view, message_id=77)
    interaction = await client.process_interaction(payload(component("vote", message_id=88)))
    assert not await store.dispatch_component(interaction, "vote", 88)
    assert await store.dispatch_component(interaction, "vote", 77)
    assert [custom_id for _, custom_id in view.received] == ["vote"]


async def test_a_view_stored_for_any_message_answers_everywhere() -> None:
    client, _ = await started()
    store = ViewStore()
    view = PersistentView()
    store.store(view, message_id=None)
    interaction = await client.process_interaction(payload(component("persistent:ok", message_id=5)))
    assert await store.dispatch_component(interaction, "persistent:ok", 5)
    assert await store.dispatch_component(interaction, "persistent:ok", None)
    assert store.persistent_views == [view]


async def test_finished_views_are_dropped() -> None:
    client, _ = await started()
    store = ViewStore()
    view = PersistentView()
    store.store(view, message_id=None)
    interaction = await client.process_interaction(payload(component("persistent:ok")))
    view.finished = True
    assert not await store.dispatch_component(interaction, "persistent:ok", 77)
    assert store.persistent_views == []
    assert view.received == []


async def test_a_view_that_finishes_while_handling_is_dropped_after() -> None:
    client, _ = await started()
    store = ViewStore()

    class Once(PersistentView):
        @override
        async def dispatch(self, interaction: Interaction, custom_id: str) -> None:
            await super().dispatch(interaction, custom_id)
            self.finished = True

    once = Once()
    store.store(once, message_id=None)
    interaction = await client.process_interaction(payload(component("persistent:ok")))
    assert await store.dispatch_component(interaction, "persistent:ok", 77)
    assert not await store.dispatch_component(interaction, "persistent:ok", 77)


async def test_views_without_callbacks_are_not_kept() -> None:
    store = ViewStore()
    store.store(ROW_VIEW, message_id=5)
    assert store.persistent_views == []


async def test_modals_answer_once_for_the_user_who_opened_them() -> None:
    client, _ = await started()
    store = ViewStore()
    modal = RecordingModal()
    store.store_modal(modal, user_id=ALICE)
    interaction = await client.process_interaction(payload(component("x")))
    assert not await store.dispatch_modal(interaction, "form", BOB)
    assert await store.dispatch_modal(interaction, "form", ALICE)
    assert not await store.dispatch_modal(interaction, "form", ALICE)
    assert modal.submitted == [interaction]
    finished = RecordingModal()
    finished.finished = True
    store.store_modal(finished, user_id=ALICE)
    assert not await store.dispatch_modal(interaction, "form", ALICE)
