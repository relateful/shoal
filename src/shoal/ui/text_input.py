"""Text inputs: what a modal asks the user to type.

    class Feedback(ui.Modal, title="Feedback"):
        name = ui.TextInput(label="Name")
        body = ui.TextInput(label="Your feedback", style=TextInputStyle.PARAGRAPH, max_length=1000)

Discord: https://docs.discord.com/developers/components/reference#text-input
"""

from collections.abc import Sequence
from typing import override

from msgspec import UNSET

from shoal.client.interaction import Interaction
from shoal.payloads.components import Label, TextInputStyle
from shoal.payloads.components import TextInput as TextInputPayload
from shoal.payloads.interactions import ResolvedData
from shoal.ui.item import Item


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
    def to_component(self) -> Label:
        """The input, in its label, as Discord takes it."""
        field = TextInputPayload(
            custom_id=self.custom_id,
            style=self.style,
            min_length=self.min_length if self.min_length is not None else UNSET,
            max_length=self.max_length if self.max_length is not None else UNSET,
            required=self.required,
            value=self.default if self.default is not None else UNSET,
            placeholder=self.placeholder if self.placeholder is not None else UNSET,
        )
        return Label(
            label=self.label,
            description=self.description if self.description is not None else UNSET,
            component=field,
        )

    @override
    def __str__(self) -> str:
        return self.value

    @override
    def __repr__(self) -> str:
        return f"<TextInput label={self.label!r} custom_id={self.custom_id!r}>"
