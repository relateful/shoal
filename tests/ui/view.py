import asyncio
import logging
from typing import override

import pytest

from shoal.client.interaction import Interaction
from shoal.payloads import ActionRow, ButtonStyle
from shoal.ui.button import Button, button
from shoal.ui.select import Select, select
from shoal.ui.text_input import TextInput
from shoal.ui.view import View
from tests.support.client import started
from tests.support.interactions import component, payload


class Counter(View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.count = 0
        self.pressed: list[str] = []

    @button(label="+1", custom_id="counter:add", style=ButtonStyle.PRIMARY)
    async def add(self, interaction: Interaction, pressed: Button) -> None:
        del interaction
        self.count += 1
        self.pressed.append(pressed.custom_id)

    @select(custom_id="counter:pick", options=[])
    async def pick(self, interaction: Interaction, chosen: Select) -> None:
        del interaction
        self.pressed.extend(chosen.values)


async def settle() -> None:
    for _ in range(10):
        await asyncio.sleep(0)


def test_decorated_methods_become_items_per_view() -> None:
    first, second = Counter(), Counter()
    assert [type(item) for item in first.children] == [Button, Select]
    assert first.children[0] is not second.children[0]
    assert first.children[0].view is first
    assert first.is_persistent()
    assert first.is_dispatchable()
    assert sorted(first.custom_ids()) == ["counter:add", "counter:pick"]
    assert repr(first) == "<Counter items=2 timeout=None>"


def test_items_are_laid_out_in_rows() -> None:
    view = View()
    for index in range(6):
        view.add_item(Button(label=str(index)))
    view.add_item(Select())
    rows = view.to_components()
    assert [len(row.components) for row in rows if isinstance(row, ActionRow)] == [5, 1, 1]
    pinned = View().add_item(Button(row=2)).add_item(Button())
    assert [len(row.components) for row in pinned.to_components() if isinstance(row, ActionRow)] == [1, 1]


def test_a_full_view_or_row_refuses_more() -> None:
    view = View()
    for _ in range(25):
        view.add_item(Button())
    with pytest.raises(ValueError, match="at most 25"):
        view.add_item(Button())
    crowded = View().add_item(Select(row=0))
    with pytest.raises(ValueError, match="row 0 has no room"):
        crowded.add_item(Button(row=0))
    selects = View()
    for _ in range(5):
        selects.add_item(Select())
    with pytest.raises(ValueError, match="no row has room"):
        selects.add_item(Button())


def test_items_can_be_removed() -> None:
    view = Counter()
    first = view.children[0]
    view.remove_item(first).remove_item(first)
    assert first.view is None
    assert len(view.children) == 1
    view.clear_items()
    assert view.children == []
    assert not view.is_dispatchable()


def test_text_inputs_belong_in_modals() -> None:
    view = View().add_item(TextInput(label="Name"))
    with pytest.raises(TypeError, match="modal"):
        view.to_components()


async def test_presses_run_the_decorated_method() -> None:
    client, _ = await started()
    view = Counter()
    client.add_view(view)
    await client.process_interaction(payload(component("counter:add")))
    await client.process_interaction(payload(component("counter:pick", values=["a", "b"])))
    await settle()
    assert view.count == 1
    assert view.pressed == ["counter:add", "a", "b"]


async def test_interaction_check_can_refuse() -> None:
    class Private(Counter):
        @override
        async def interaction_check(self, interaction: Interaction) -> bool:
            del interaction
            return False

    client, _ = await started()
    view = Private()
    client.add_view(view)
    await client.process_interaction(payload(component("counter:add")))
    await settle()
    assert view.count == 0


async def test_callback_errors_reach_on_error(caplog: pytest.LogCaptureFixture) -> None:
    class Broken(View):
        def __init__(self) -> None:
            super().__init__(timeout=None)
            self.errors: list[str] = []

        @button(custom_id="broken")
        async def explode(self, interaction: Interaction, pressed: Button) -> None:
            del interaction, pressed
            msg = "boom"
            raise RuntimeError(msg)

    client, _ = await started()
    view = Broken()
    client.add_view(view)
    with caplog.at_level(logging.ERROR, logger="shoal.ui"):
        await client.process_interaction(payload(component("broken")))
        await settle()
    assert "raised" in caplog.text


async def test_an_assigned_callback_runs() -> None:
    client, _ = await started()
    pressed: list[Interaction] = []

    async def on_press(interaction: Interaction) -> None:
        pressed.append(interaction)

    item = Button(custom_id="assigned")
    # `item.callback = on_press`, which checkers reject on a method; the same assignment.
    vars(item)["callback"] = on_press
    view = View(timeout=None).add_item(item)
    client.add_view(view)
    await client.process_interaction(payload(component("assigned")))
    await settle()
    assert len(pressed) == 1


async def test_stop_and_wait() -> None:
    view = Counter()
    waiting = asyncio.create_task(view.wait())
    await asyncio.sleep(0)
    view.stop()
    view.stop()
    assert await waiting is False
    assert view.is_finished()
    assert await view.wait() is False


async def test_a_view_times_out_after_its_last_use() -> None:
    timed_out: list[bool] = []

    class Short(View):
        @override
        async def on_timeout(self) -> None:
            timed_out.append(True)

    view = Short(timeout=0.02)
    view.add_item(Button())
    view.to_components()
    assert await view.wait() is True
    await settle()
    assert timed_out == [True]
    assert view.is_finished()


async def test_a_failing_timeout_handler_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    class Failing(View):
        @override
        async def on_timeout(self) -> None:
            msg = "late"
            raise RuntimeError(msg)

    view = Failing(timeout=0.01)
    with caplog.at_level(logging.ERROR, logger="shoal.ui"):
        view.to_components()
        await view.wait()
        await settle()
    assert "on_timeout raised" in caplog.text


async def test_the_timeout_can_change_while_running() -> None:
    view = View(timeout=10)
    view.to_components()
    view.timeout = 0.01
    assert view.timeout == 0.01
    assert await view.wait() is True
