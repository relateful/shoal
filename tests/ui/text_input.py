import msgspec

from shoal.core.codec import encode_json
from shoal.payloads import TextInputStyle
from shoal.ui.text_input import TextInput


def test_a_text_input_is_a_label_around_the_input() -> None:
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
    assert msgspec.json.decode(encode_json(field.to_component())) == {
        "type": 18,
        "label": "Bio",
        "description": "Shown on your profile",
        "component": {
            "type": 4,
            "custom_id": "bio",
            "style": 2,
            "min_length": 2,
            "max_length": 200,
            "required": False,
            "value": "Hi",
            "placeholder": "Tell us",
        },
    }
    assert field.value == "Hi"
    assert repr(field) == "<TextInput label='Bio' custom_id='bio'>"


def test_the_value_is_empty_until_typed_without_a_default() -> None:
    assert TextInput(label="x").value == ""
