import msgspec

from shoal.core.codec import encode_json
from shoal.payloads import TextInputStyle
from shoal.ui.modal import Modal
from shoal.ui.text_input import TextInput


def test_a_text_input_added_to_a_modal_is_shown_under_its_own_label() -> None:
    field = TextInput(
        label="Bio",
        style=TextInputStyle.PARAGRAPH,
        custom_id="bio",
        placeholder="Tell us",
        default="Hi",
        required=False,
        min_length=2,
        max_length=200,
        description="Shown on your profile",
    )
    rendered = {
        "type": 4,
        "custom_id": "bio",
        "style": 2,
        "min_length": 2,
        "max_length": 200,
        "required": False,
        "value": "Hi",
        "placeholder": "Tell us",
    }
    assert msgspec.json.decode(encode_json(field.to_component())) == rendered
    form = Modal(title="Profile", custom_id="profile").add_item(field)
    assert msgspec.json.decode(encode_json(form.to_modal()))["components"] == [
        {"type": 18, "label": "Bio", "description": "Shown on your profile", "component": rendered}
    ]
    assert field.value == "Hi"
    assert repr(field) == "<TextInput label='Bio' custom_id='bio'>"


def test_the_value_is_empty_until_typed_without_a_default() -> None:
    assert TextInput(label="x").value == ""
