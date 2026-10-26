import msgspec
import pytest

from shoal.core.codec import encode_json
from shoal.payloads import CheckboxGroupOption, RadioGroupOption
from shoal.ui.inputs import Checkbox, CheckboxGroup, FileUpload, RadioGroup
from shoal.ui.item import Item


def rendered(item: Item) -> object:
    return msgspec.json.decode(encode_json(item.to_component()))


def test_a_file_upload_renders_its_limits() -> None:
    upload = FileUpload(custom_id="shots", min_values=1, max_values=3, file_types=["image", ".pdf"], id=2)
    upload.validate()
    assert rendered(upload) == {
        "type": 19,
        "id": 2,
        "custom_id": "shots",
        "min_values": 1,
        "max_values": 3,
        "required": True,
        "file_types": ["image", ".pdf"],
    }
    assert upload.values == []
    assert repr(upload) == "<FileUpload custom_id='shots'>"


def test_a_radio_group_has_two_to_ten_options() -> None:
    group = RadioGroup(custom_id="size", options=[RadioGroupOption(value="s", label="Small")])
    with pytest.raises(ValueError, match="2 to 10 options"):
        group.validate()
    group.add_option(label="Large", description="Big", default=True)
    group.validate()
    assert rendered(group) == {
        "type": 21,
        "custom_id": "size",
        "options": [
            {"value": "s", "label": "Small"},
            {"value": "Large", "label": "Large", "description": "Big", "default": True},
        ],
        "required": True,
    }
    assert group.value is None
    assert repr(group) == "<RadioGroup custom_id='size' options=2>"


def test_a_checkbox_group_renders_and_checks_its_choices() -> None:
    group = CheckboxGroup(custom_id="toppings", max_values=2, required=False, min_values=0)
    group.add_option(label="Cheese")
    group.add_option(label="Olives", value="olive", description="Green", default=True)
    group.validate()
    assert rendered(group) == {
        "type": 22,
        "custom_id": "toppings",
        "options": [
            {"value": "Cheese", "label": "Cheese"},
            {"value": "olive", "label": "Olives", "description": "Green", "default": True},
        ],
        "min_values": 0,
        "max_values": 2,
        "required": False,
    }
    assert group.values == []
    assert repr(group) == "<CheckboxGroup custom_id='toppings' options=2>"


def test_a_checkbox_starts_at_its_default() -> None:
    box = Checkbox(custom_id="agree", default=True)
    assert box.value is True
    assert rendered(box) == {"type": 23, "custom_id": "agree", "default": True}
    assert rendered(Checkbox(custom_id="plain")) == {"type": 23, "custom_id": "plain"}
    assert repr(box) == "<Checkbox custom_id='agree'>"


@pytest.mark.parametrize(
    ("item", "problem"),
    [
        (FileUpload(max_values=11), "max_values <= 10"),
        (FileUpload(min_values=0), "required input needs min_values"),
        (FileUpload(min_values=3, max_values=2), "min_values <= max_values"),
        (FileUpload(file_types=["image"] * 11), "0 to 10 file types"),
        (CheckboxGroup(), "1 to 10 options"),
        (CheckboxGroup(options=[CheckboxGroupOption(value="v", label="x" * 101)]), "an option's label"),
        (
            CheckboxGroup(options=[CheckboxGroupOption(value="v", label="l")], min_values=0),
            "required input needs min_values",
        ),
        (
            RadioGroup(
                options=[
                    RadioGroupOption(value="a", label="a"),
                    RadioGroupOption(value="b", label="b", description="x" * 101),
                ]
            ),
            "an option's description",
        ),
    ],
)
def test_inputs_discord_would_refuse_are_refused(item: Item, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        item.validate()
