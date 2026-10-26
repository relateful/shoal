import asyncio
import logging
from typing import override

import msgspec
import pytest

from shoal.client.interaction import Interaction
from shoal.core.codec import encode_json
from shoal.models.sending import outgoing
from shoal.payloads import ActionRow, ButtonStyle, MessageFlags, SelectOption
from shoal.ui.action_row import ActionRow as ActionRowItem
from shoal.ui.button import Button, button
from shoal.ui.content import Separator, TextDisplay, Thumbnail
from shoal.ui.layout import Container, Section
from shoal.ui.select import Select, select
from shoal.ui.text_input import TextInput
from shoal.ui.view import LayoutView, View
from tests.support.calls import call_unchecked
from tests.support.client import started
from tests.support.fakes import settle
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


def test_decorated_methods_become_items_per_view() -> None:
    first, second = Counter(), Counter()
    assert [type(item) for item in first.children] == [Button, Select]
    assert first.children[0] is not second.children[0]
    assert first.children[0].view is first
    assert first.is_persistent()
    assert first.is_dispatchable()
    assert sorted(first.custom_ids()) == ["counter:add", "counter:pick"]
    assert repr(first) == "<Counter items=2 timeout=None>"


def test_a_subclass_can_drop_an_item_by_redefining_its_method() -> None:
    class Plain(Counter):
        @override
        async def add(self, interaction: Interaction, pressed: Button) -> None:
            del interaction, pressed

    assert [type(item) for item in Plain().children] == [Select]


def test_items_are_laid_out_in_rows() -> None:
    view = View()
    for index in range(6):
        view.add_item(Button(label=str(index)))
    view.add_item(Select(options=[SelectOption(label="only", value="only")]))
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
    with pytest.raises(TypeError, match="buttons and selects"):
        call_unchecked(View().add_item, TextInput(label="Name"))


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
    await client.process_interaction(payload(component("counter:pick", values=["a"])))
    await settle()
    assert view.count == 0
    # A refused interaction changes nothing: not even the select's values.
    [picker] = [child for child in view.children if isinstance(child, Select)]
    assert picker.values == []


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


@pytest.mark.parametrize(
    ("item", "problem"),
    [
        (Button(custom_id="x" * 101), "custom_id must be 1 to 100"),
        (Button(label="x" * 81), "label is 81 characters"),
        (Button(url="https://e.com/" + "x" * 512), "url is"),
        (Select(placeholder="x" * 151, options=[SelectOption(label="a", value="a")]), "placeholder"),
        (Select(options=[]), "1 to 25 options"),
        (Select(options=[SelectOption(label="x" * 101, value="a")]), "an option's label"),
        (Select(options=[SelectOption(label="a", value="a")], min_values=2, max_values=1), "min_values"),
        (Select(options=[SelectOption(label="a", value="a")], max_values=26), "max_values"),
    ],
)
def test_items_discord_would_refuse_are_refused_before_sending(item: Button | Select, problem: str) -> None:
    view = View().add_item(item)
    with pytest.raises(ValueError, match=problem):
        view.to_components()


def test_two_items_cannot_share_a_custom_id() -> None:
    view = View().add_item(Button(custom_id="same")).add_item(Button(custom_id="same"))
    with pytest.raises(ValueError, match="another item of the view has custom_id 'same'"):
        view.to_components()


class Status(LayoutView):
    heading = TextDisplay("## Status", id=1)
    details = Container(
        Section("All systems normal", accessory=Thumbnail("https://e.com/ok.png")),
        Separator(),
        accent_colour=0x57F287,
    )
    row = ActionRowItem()

    @row.button(label="Refresh", custom_id="status:refresh")
    async def refresh(self, interaction: Interaction, pressed: Button) -> None:
        del interaction, pressed


def test_a_layout_view_sends_its_items_with_the_components_v2_flag() -> None:
    view = Status(timeout=None)
    message = outgoing(view=view)
    assert isinstance(message.flags, MessageFlags)
    assert message.flags.is_components_v2
    assert [component["type"] for component in msgspec.json.decode(encode_json(message.components))] == [
        10,
        17,
        1,
    ]
    assert view.has_components_v2()
    assert view.is_persistent()
    assert view.custom_ids() == ["status:refresh"]
    assert view.find_item(1) is view.heading
    assert len(list(view.walk_children())) == 8


def test_a_layout_view_of_action_rows_only_is_an_ordinary_message() -> None:
    view = LayoutView().add_item(ActionRowItem(Button(custom_id="a")))
    message = outgoing("Pick one", view=view)
    assert message.flags is msgspec.UNSET
    for index in range(5):
        view.add_item(ActionRowItem(Button(custom_id=f"more{index}")))
    with pytest.raises(ValueError, match="only holds 5"):
        view.to_components()


def test_a_layout_view_holds_at_most_forty_components() -> None:
    view = LayoutView()
    for index in range(40):
        view.add_item(TextDisplay(str(index)))
    view.to_components()
    view.add_item(TextDisplay("one too many"))
    with pytest.raises(ValueError, match="at most 40 components, not 41"):
        view.to_components()


def test_component_ids_are_unique_but_zero_means_unset() -> None:
    LayoutView().add_item(TextDisplay("a", id=0)).add_item(TextDisplay("b", id=0)).to_components()
    twice = LayoutView().add_item(TextDisplay("a", id=4)).add_item(Container(TextDisplay("b", id=4)))
    with pytest.raises(ValueError, match="another item of the view has id 4"):
        twice.to_components()


def test_a_layout_view_takes_only_top_level_components() -> None:
    with pytest.raises(TypeError, match="put a button or a select in an ActionRow"):
        call_unchecked(LayoutView().add_item, Button())
    with pytest.raises(TypeError, match="go in an action row"):

        class Wrong(LayoutView):  # pyright: ignore[reportUnusedClass] - defining it is the test
            @button(label="x")
            async def stray(self, interaction: Interaction, pressed: Button) -> None:
                del interaction, pressed

    class Stray(LayoutView):
        thumbnail = Thumbnail("https://e.com/a.png")

    with pytest.raises(TypeError, match="cannot be at the top"):
        Stray()


def test_removing_from_a_layout_view_detaches_the_whole_item() -> None:
    view = Status()
    view.remove_item(view.details)
    assert view.details.view is None
    assert all(item.view is None for item in view.details.walk())
    view.clear_items()
    assert view.children == []
    assert view.heading.view is None


def test_an_item_declared_alone_and_in_a_container_is_one_object_per_view() -> None:
    class Shared(LayoutView):
        row = ActionRowItem(Button(custom_id="shared:go"))
        box = Container(TextDisplay("x"), row)

    view = Shared()
    assert view.children == [view.box]
    assert view.row.parent is view.box
    assert view.row is not Shared.row
    assert view.custom_ids() == ["shared:go"]


async def test_an_unknown_custom_id_or_a_stopped_view_does_not_dispatch() -> None:
    client, _ = await started()
    view = Status(timeout=None)
    interaction = await client.process_interaction(payload(component("nobody")))
    assert not await view.dispatch(interaction, "nobody")
    view.stop()
    assert not await view.dispatch(interaction, "status:refresh")


def test_an_item_id_can_be_set_later() -> None:
    text = TextDisplay("x")
    text.id = 7
    assert text.id == 7
