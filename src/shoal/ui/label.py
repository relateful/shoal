"""Labels: the title and help text above one input of a modal.

    class Order(ui.Modal, title="Order"):
        size = ui.Label("Size", ui.Select(options=[...]), description="Pick one")

Discord: https://docs.discord.com/developers/components/reference#label
"""

from typing import override

from shoal.models.base import unset_if_none
from shoal.payloads.components import LABEL_DESCRIPTION_MAX_LENGTH, LABEL_MAX_LENGTH
from shoal.payloads.components import Label as LabelPayload
from shoal.ui.inputs import Checkbox, CheckboxGroup, FileUpload, RadioGroup
from shoal.ui.item import Item, check_length
from shoal.ui.select import BaseSelect
from shoal.ui.text_input import TextInput

type LabelItem = TextInput | BaseSelect | FileUpload | RadioGroup | CheckboxGroup | Checkbox
"""What a label can describe."""


class Label(Item):
    """A title (and optional description) for one input of a modal.

    Discord: https://docs.discord.com/developers/components/reference#label
    """

    __slots__ = ("_component", "description", "text")

    def __init__(
        self, text: str, component: LabelItem, *, description: str | None = None, id: int | None = None
    ) -> None:
        """A label `text` (up to 45 characters) above `component`.

        Raises:
            TypeError: `component` cannot go in a label.
        """
        super().__init__(id=id)
        self.text: str = text
        self.description: str | None = description
        self._component: LabelItem = _label_item(component)
        self.adopt(component)

    @property
    def component(self) -> LabelItem:
        """The input the label is for."""
        return self._component

    @property
    @override
    def children(self) -> list[Item]:
        """The input."""
        return [self._component]

    @override
    def validate(self) -> None:
        super().validate()
        check_length(self, "text", self.text, LABEL_MAX_LENGTH)
        check_length(self, "description", self.description, LABEL_DESCRIPTION_MAX_LENGTH)
        component = self._component
        if isinstance(component, BaseSelect):
            if component.disabled:
                msg = f"{component!r}: a modal cannot have disabled components"
                raise ValueError(msg)
            if component.min_values == 0 and component.required is not False:
                msg = f"{component!r}: a required select in a modal needs min_values of at least 1"
                raise ValueError(msg)

    @override
    def to_component(self) -> LabelPayload:
        """The label, with its input, as Discord takes it."""
        return LabelPayload(
            id=unset_if_none(self.id),
            label=self.text,
            description=unset_if_none(self.description),
            component=self._component.to_component(),
        )

    @override
    def __repr__(self) -> str:
        return f"<Label text={self.text!r} component={self._component!r}>"


def _label_item(item: Item) -> LabelItem:
    if not isinstance(item, TextInput | BaseSelect | FileUpload | RadioGroup | CheckboxGroup | Checkbox):
        msg = f"a label holds a text input, a select, a file upload, radios or checkboxes, not {item!r}"
        raise TypeError(msg)
    return item
