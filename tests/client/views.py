from shoal.client.views import PENDING_MODALS_PER_USER, ViewStore
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


async def test_a_view_is_forgotten_when_it_finishes() -> None:
    client, _ = await started()
    store = ViewStore()
    view = PersistentView()
    store.store(view, message_id=None)
    store.store(view, message_id=77)
    interaction = await client.process_interaction(payload(component("persistent:ok")))
    view.stop()
    assert not await store.dispatch_component(interaction, "persistent:ok", 77)
    assert not await store.dispatch_component(interaction, "persistent:ok", None)
    assert store.persistent_views == []
    assert view.received == []


async def test_forgetting_a_view_leaves_a_newer_view_with_the_same_custom_id() -> None:
    client, _ = await started()
    store = ViewStore()
    old, new = PersistentView(), PersistentView()
    store.store(old, message_id=None)
    store.store(new, message_id=None)
    old.stop()
    interaction = await client.process_interaction(payload(component("persistent:ok")))
    assert await store.dispatch_component(interaction, "persistent:ok", None)
    assert new.received == [(interaction, "persistent:ok")]
    assert store.persistent_views == [new]


async def test_a_view_that_finished_before_it_was_stored_is_not_kept() -> None:
    client, _ = await started()
    store = ViewStore()
    view = PersistentView()
    view.stop()
    store.store(view, message_id=None)
    interaction = await client.process_interaction(payload(component("persistent:ok")))
    assert not await store.dispatch_component(interaction, "persistent:ok", None)
    assert store.persistent_views == []


async def test_storing_a_view_again_routes_both_messages_until_it_finishes() -> None:
    client, _ = await started()
    store = ViewStore()
    view = PersistentView(persistent=False)
    for _ in range(3):
        store.store(view, message_id=1)
    store.store(view, message_id=2)
    interaction = await client.process_interaction(payload(component("persistent:ok")))
    assert await store.dispatch_component(interaction, "persistent:ok", 1)
    assert await store.dispatch_component(interaction, "persistent:ok", 2)
    view.stop()
    assert not await store.dispatch_component(interaction, "persistent:ok", 1)
    assert not await store.dispatch_component(interaction, "persistent:ok", 2)


async def test_opening_the_same_modal_again_keeps_it_waiting() -> None:
    store = ViewStore()
    modal = RecordingModal()
    store.store_modal(modal, user_id=ALICE)
    store.store_modal(modal, user_id=ALICE)
    assert not modal.is_finished()


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
    finished.stop()
    store.store_modal(finished, user_id=ALICE)
    assert not await store.dispatch_modal(interaction, "form", ALICE)


async def test_opening_too_many_modals_stops_the_oldest() -> None:
    store = ViewStore()
    modals = [RecordingModal(f"form-{index}") for index in range(PENDING_MODALS_PER_USER + 1)]
    for modal in modals:
        store.store_modal(modal, user_id=ALICE)
    store.store_modal(RecordingModal("form-0"), user_id=BOB)
    assert modals[0].is_finished()
    assert not any(modal.is_finished() for modal in modals[1:])


async def test_reopening_a_modal_replaces_the_waiting_one() -> None:
    client, _ = await started()
    store = ViewStore()
    first, second = RecordingModal(), RecordingModal()
    store.store_modal(first, user_id=ALICE)
    store.store_modal(second, user_id=ALICE)
    first.stop()
    interaction = await client.process_interaction(payload(component("x")))
    assert await store.dispatch_modal(interaction, "form", ALICE)
    assert second.submitted == [interaction]
    assert first.submitted == []
