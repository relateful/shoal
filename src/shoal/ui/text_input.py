"""Text inputs: what a modal asks the user to type.

    class Feedback(ui.Modal, title="Feedback"):
        name = ui.TextInput(label="Name")
        body = ui.TextInput(label="Your feedback", style=TextInputStyle.PARAGRAPH, max_length=1000)

Discord: https://docs.discord.com/developers/components/reference#text-input
"""

from collections.abc import Sequence
from typing import override

from shoal.client.interaction import Interaction
from shoal.models.base import unset_if_none
from shoal.payloads.components import (
    LABEL_DESCRIPTION_MAX_LENGTH,
    LABEL_MAX_LENGTH,
    TEXT_INPUT_MAX_LENGTH,
    TEXT_INPUT_PLACEHOLDER_MAX_LENGTH,
    Label,
    TextInputStyle,
)
from shoal.payloads.components import TextInput as TextInputPayload
from shoal.payloads.interactions import ResolvedData
from shoal.ui.item import Item, check_length


class TextInput(Item):
    """A text field in a modal; `value` holds what the user typed, once submitted.

    Discord shows it with a label above it (a Label component); `description` adds help text under
    the label.

    Discord: https://docs.discord.com/developers/components/reference#text-input
    """

    __slots__ = (
        "_value",
        "default",
        "description",
        "label",
        "max_length",
        "min_length",
        "placeholder",
        "required",
        "style",
    )

    def __init__(
        self,
        *,
        label: str,
        style: TextInputStyle = TextInputStyle.SHORT,
        custom_id: str | None = None,
        placeholder: str | None = None,
        default: str | None = None,
        required: bool = True,
        min_length: int | None = None,
        max_length: int | None = None,
        description: str | None = None,
        row: int | None = None,
    ) -> None:
        """A text input labelled `label` (up to 45 characters)."""
        super().__init__(custom_id=custom_id, row=row)
        self.label: str = label
        self.style: TextInputStyle = style
        self.placeholder: str | None = placeholder
        self.default: str | None = default
        self.required: bool = required
        self.min_length: int | None = min_length
        self.max_length: int | None = max_length
        self.description: str | None = description
        self._value: str | None = None

    @property
    def value(self) -> str:
        """What the user typed (the default until the modal is submitted)."""
        return self._value if self._value is not None else self.default or ""

    @override
    def refresh(self, interaction: Interaction, values: Sequence[str], resolved: ResolvedData | None) -> None:
        self._value = values[0] if values else ""

    @override
    def validate(self) -> None:
        super().validate()
        check_length(self, "label", self.label, LABEL_MAX_LENGTH)
        check_length(self, "description", self.description, LABEL_DESCRIPTION_MAX_LENGTH)
        check_length(self, "placeholder", self.placeholder, TEXT_INPUT_PLACEHOLDER_MAX_LENGTH)
        check_length(self, "default", self.default, TEXT_INPUT_MAX_LENGTH)
        low = self.min_length if self.min_length is not None else 0
        high = self.max_length if self.max_length is not None else TEXT_INPUT_MAX_LENGTH
        if not 0 <= low <= high <= TEXT_INPUT_MAX_LENGTH or high < 1:
            limit = TEXT_INPUT_MAX_LENGTH
            msg = f"{self!r}: needs 0 <= min_length <= max_length <= {limit}, not {low} and {high}"
            raise ValueError(msg)

    @override
    def to_component(self) -> Label:
        """The input, in its label, as Discord takes it."""
        field = TextInputPayload(
            custom_id=self.custom_id,
            style=self.style,
            min_length=unset_if_none(self.min_length),
            max_length=unset_if_none(self.max_length),
            required=self.required,
            value=unset_if_none(self.default),
            placeholder=unset_if_none(self.placeholder),
        )
        return Label(
            label=self.label,
            description=unset_if_none(self.description),
            component=field,
        )

    @override
    def __str__(self) -> str:
        return self.value

    @override
    def __repr__(self) -> str:
        return f"<TextInput label={self.label!r} custom_id={self.custom_id!r}>"
