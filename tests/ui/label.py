import msgspec
import pytest

from shoal.core.codec import encode_json
from shoal.payloads import SelectOption
from shoal.ui.content import TextDisplay
from shoal.ui.inputs import Checkbox
from shoal.ui.label import Label
from shoal.ui.select import Select, UserSelect
from shoal.ui.text_input import TextInput
from tests.support.calls import call_unchecked


def test_a_label_wraps_one_input() -> None:
    field = TextInput(custom_id="bio")
    label = Label("Bio", field, description="About you", id=5)
    label.validate()
    assert msgspec.json.decode(encode_json(label.to_component())) == {
        "type": 18,
        "id": 5,
        "label": "Bio",
        "description": "About you",
        "component": {"type": 4, "custom_id": "bio", "style": 1, "required": True},
    }
    assert label.component is field
    assert field.parent is label
    assert repr(label) == "<Label text='Bio' component=<TextInput label=None custom_id='bio'>>"


@pytest.mark.parametrize(
    ("label", "problem"),
    [
        (Label("x" * 46, Checkbox()), "text is 46"),
        (Label("a", Checkbox(), description="x" * 101), "description is 101"),
        (Label("a", Select(options=[SelectOption(label="a", value="a")], disabled=True)), "disabled"),
        (Label("a", UserSelect(min_values=0)), "required select"),
    ],
)
def test_labels_discord_would_refuse_are_refused(label: Label, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        label.validate()


def test_an_optional_select_may_allow_no_choice() -> None:
    Label("a", UserSelect(min_values=0, required=False)).validate()


def test_a_label_holds_inputs_only() -> None:
    with pytest.raises(TypeError, match="a label holds"):
        call_unchecked(Label, "a", TextDisplay("x"))
