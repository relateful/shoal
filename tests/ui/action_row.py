import msgspec
import pytest

from shoal.client.interaction import Interaction
from shoal.core.codec import encode_json
from shoal.payloads import ButtonStyle, SelectOption
from shoal.ui.action_row import ActionRow
from shoal.ui.button import Button, button
from shoal.ui.content import TextDisplay
from shoal.ui.layout import Container
from shoal.ui.select import RoleSelect, Select
from shoal.ui.view import LayoutView
from tests.support.calls import call_unchecked
from tests.support.client import started
from tests.support.fakes import settle
from tests.support.interactions import component, payload


def test_a_row_holds_five_buttons_or_one_select() -> None:
    row = ActionRow(*[Button(custom_id=str(index)) for index in range(5)], id=4)
    with pytest.raises(ValueError, match="no room"):
        row.add_item(Button())
    assert msgspec.json.decode(encode_json(row.to_component()))["id"] == 4
    with pytest.raises(ValueError, match="no room"):
        ActionRow(Button(), Select())
    with pytest.raises(TypeError, match="buttons and selects"):
        call_unchecked(ActionRow().add_item, TextDisplay("x"))


def test_removing_and_clearing_detach_the_items() -> None:
    first, second = Button(), Button()
    row = ActionRow(first, second)
    row.remove_item(first).remove_item(Button())
    assert row.children == [second]
    assert first.parent is None
    row.clear_items()
    assert row.children == []
    assert second.parent is None


class Votes(LayoutView):
    """Buttons decorated through a row declared on the view: `self` is the view."""

    row = ActionRow()
    picker = ActionRow()

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.votes: list[str] = []

    @row.button(label="Yes", custom_id="vote:yes", style=ButtonStyle.SUCCESS)
    async def yes(self, interaction: Interaction, pressed: Button) -> None:
        del interaction
        self.votes.append(pressed.custom_id)

    @picker.select(custom_id="vote:why", options=[SelectOption(label="Because", value="because")])
    async def why(self, interaction: Interaction, picked: Select) -> None:
        del interaction
        self.votes.extend(picked.values)


async def test_methods_decorated_through_a_row_run_on_the_view() -> None:
    client, _ = await started()
    view = Votes()
    client.add_view(view)
    await client.process_interaction(payload(component("vote:yes")))
    await client.process_interaction(payload(component("vote:why", values=["because"])))
    await settle()
    assert view.votes == ["vote:yes", "because"]


def test_each_view_gets_its_own_row_and_the_template_stays_empty() -> None:
    first, second = Votes(), Votes()
    assert first.row is not second.row
    assert first.row is not Votes.row
    assert Votes.row.children == []
    assert [type(item) for item in first.row.children] == [Button]
    assert [type(item) for item in first.picker.children] == [Select]
    assert first.row.children[0] is not second.row.children[0]
    assert first.row.parent is None
    assert first.row.view is first


class Controls(ActionRow):
    """A row subclass with its own buttons: `self` is the row."""

    def __init__(self) -> None:
        super().__init__()
        self.pressed = 0

    @button(label="Press", custom_id="controls:press")
    async def press(self, interaction: Interaction, pressed: Button) -> None:
        del interaction, pressed
        self.pressed += 1


class Panel(Container):
    """A container with a row whose method is defined on the container: `self` is the container."""

    title = TextDisplay("## Panel")
    row = ActionRow()

    def __init__(self) -> None:
        super().__init__()
        self.opened = 0

    @row.select(cls=RoleSelect, custom_id="panel:roles")
    async def roles(self, interaction: Interaction, picked: RoleSelect) -> None:
        del interaction, picked
        self.opened += 1


class Dashboard(LayoutView):
    controls = Controls()
    panel = Panel()


async def test_row_and_container_methods_run_on_the_object_that_defines_them() -> None:
    client, _ = await started()
    view = Dashboard(timeout=None)
    client.add_view(view)
    await client.process_interaction(payload(component("controls:press")))
    await client.process_interaction(payload(component("panel:roles", values=[])))
    await settle()
    assert view.controls.pressed == 1
    assert view.panel.opened == 1
    # The templates on the class saw nothing.
    assert Dashboard.controls.pressed == 0
    assert Dashboard.panel.opened == 0
    assert view.panel.title is not Dashboard.panel.title


def test_a_row_method_from_elsewhere_is_refused_when_the_row_joins_a_view() -> None:
    row = ActionRow()

    @row.button(label="Lost")
    async def lost(owner: object, interaction: Interaction, pressed: Button) -> None:
        del owner, interaction, pressed

    with pytest.raises(TypeError, match="is not a method of the row"):
        LayoutView().add_item(row)
