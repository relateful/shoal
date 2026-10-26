"""What else a modal can ask for: files, a single choice, several choices, or a yes or no.

    class Report(ui.Modal, title="Report a bug"):
        screenshot = ui.Label("Screenshot", ui.FileUpload(file_types=["image"]))
        severity = ui.Label("Severity", ui.RadioGroup(options=[...]))
        public = ui.Label("Make it public", ui.Checkbox())

Each goes in a `ui.Label`, as Discord requires.

Discord: https://docs.discord.com/developers/components/reference#file-upload
"""

from collections.abc import Sequence
from typing import override

from msgspec import UNSET, UnsetType

from shoal.client.interaction import Interaction
from shoal.core.snowflake import Snowflake
from shoal.models.base import unset_if_none
from shoal.payloads.components import (
    CHECKBOX_GROUP_MAX_OPTIONS,
    FILE_UPLOAD_MAX_FILE_TYPES,
    FILE_UPLOAD_MAX_FILES,
    GROUP_OPTION_TEXT_MAX_LENGTH,
    RADIO_GROUP_MAX_OPTIONS,
    RADIO_GROUP_MIN_OPTIONS,
    CheckboxGroupOption,
    RadioGroupOption,
)
from shoal.payloads.components import Checkbox as CheckboxPayload
from shoal.payloads.components import CheckboxGroup as CheckboxGroupPayload
from shoal.payloads.components import FileUpload as FileUploadPayload
from shoal.payloads.components import RadioGroup as RadioGroupPayload
from shoal.payloads.interactions import ResolvedData
from shoal.payloads.message import Attachment
from shoal.ui.item import InteractiveItem, check_count, check_length


def check_choices(
    item: object, *, min_values: int | None, max_values: int | None, high: int, required: bool
) -> None:
    """Refuse a `min_values` and `max_values` Discord would refuse, for an input allowing `high`.

    Raises:
        ValueError: One is out of range, `min_values` is above `max_values`, or a required input
            allows no choice.
    """
    low = 0 if min_values is None else min_values
    top = high if max_values is None else max_values
    if not 0 <= low <= top <= high or top < 1:
        msg = f"{item!r}: needs 0 <= min_values <= max_values <= {high}, max_values >= 1; not {low}, {top}"
        raise ValueError(msg)
    if required and min_values == 0:
        msg = f"{item!r}: a required input needs min_values of at least 1 (or leave it unset)"
        raise ValueError(msg)


def _check_options(
    item: object, options: Sequence[RadioGroupOption | CheckboxGroupOption], low: int, high: int
) -> None:
    check_count(item, "options", len(options), low, high)
    for option in options:
        check_length(item, "an option's label", option.label, GROUP_OPTION_TEXT_MAX_LENGTH)
        check_length(item, "an option's value", option.value, GROUP_OPTION_TEXT_MAX_LENGTH)
        description = option.description if isinstance(option.description, str) else None
        check_length(item, "an option's description", description, GROUP_OPTION_TEXT_MAX_LENGTH)


class FileUpload(InteractiveItem):
    """Lets the user upload files; `values` holds them once the modal is submitted.

    Discord: https://docs.discord.com/developers/components/reference#file-upload
    """

    __slots__ = ("_resolved", "_values", "file_types", "max_values", "min_values", "required")

    def __init__(
        self,
        *,
        custom_id: str | None = None,
        min_values: int | None = None,
        max_values: int | None = None,
        required: bool = True,
        file_types: Sequence[str] = (),
        id: int | None = None,
    ) -> None:
        """A file upload taking `min_values` to `max_values` files (Discord's default: one).

        `file_types` limits what can be picked: `image`, `video`, `audio`, or extensions such as
        `.pdf`; only the extension is checked.
        """
        super().__init__(custom_id=custom_id, id=id)
        self.min_values: int | None = min_values
        self.max_values: int | None = max_values
        self.required: bool = required
        self.file_types: list[str] = list(file_types)
        self._values: list[str] = []
        self._resolved: ResolvedData | None = None

    @property
    def values(self) -> list[Attachment]:
        """The files uploaded."""
        attachments = (
            self._resolved.attachments
            if self._resolved is not None and not isinstance(self._resolved.attachments, UnsetType)
            else {}
        )
        return [attachments[Snowflake(raw)] for raw in self._values if Snowflake(raw) in attachments]

    @override
    def refresh(self, interaction: Interaction, values: Sequence[str], resolved: ResolvedData | None) -> None:
        self._values = list(values)
        self._resolved = resolved

    @override
    def validate(self) -> None:
        super().validate()
        check_choices(
            self,
            min_values=self.min_values,
            max_values=self.max_values,
            high=FILE_UPLOAD_MAX_FILES,
            required=self.required,
        )
        check_count(self, "file types", len(self.file_types), 0, FILE_UPLOAD_MAX_FILE_TYPES)

    @override
    def to_component(self) -> FileUploadPayload:
        """The file upload as Discord takes it."""
        return FileUploadPayload(
            id=unset_if_none(self.id),
            custom_id=self.custom_id,
            min_values=unset_if_none(self.min_values),
            max_values=unset_if_none(self.max_values),
            required=self.required,
            file_types=self.file_types or UNSET,
        )

    @override
    def __repr__(self) -> str:
        return f"<FileUpload custom_id={self.custom_id!r}>"


class RadioGroup(InteractiveItem):
    """A single choice between two to ten options; `value` holds the chosen option's value.

    Discord: https://docs.discord.com/developers/components/reference#radio-group
    """

    __slots__ = ("_value", "options", "required")

    def __init__(
        self,
        *,
        options: Sequence[RadioGroupOption] = (),
        custom_id: str | None = None,
        required: bool = True,
        id: int | None = None,
    ) -> None:
        """A radio group of `options` (add more with `add_option`)."""
        super().__init__(custom_id=custom_id, id=id)
        self.options: list[RadioGroupOption] = list(options)
        self.required: bool = required
        self._value: str | None = None

    @property
    def value(self) -> str | None:
        """The value of the option chosen, or `None` if none was."""
        return self._value

    def add_option(
        self, *, label: str, value: str | None = None, description: str | None = None, default: bool = False
    ) -> None:
        """Add an option; its value is its label when not given."""
        self.options.append(
            RadioGroupOption(
                label=label,
                value=value if value is not None else label,
                description=unset_if_none(description),
                default=default or UNSET,
            )
        )

    @override
    def refresh(self, interaction: Interaction, values: Sequence[str], resolved: ResolvedData | None) -> None:
        self._value = values[0] if values else None

    @override
    def validate(self) -> None:
        super().validate()
        _check_options(self, self.options, RADIO_GROUP_MIN_OPTIONS, RADIO_GROUP_MAX_OPTIONS)

    @override
    def to_component(self) -> RadioGroupPayload:
        """The radio group as Discord takes it."""
        return RadioGroupPayload(
            id=unset_if_none(self.id), custom_id=self.custom_id, options=self.options, required=self.required
        )

    @override
    def __repr__(self) -> str:
        return f"<RadioGroup custom_id={self.custom_id!r} options={len(self.options)}>"


class CheckboxGroup(InteractiveItem):
    """One to ten checkboxes; `values` holds the values of those checked.

    Discord: https://docs.discord.com/developers/components/reference#checkbox-group
    """

    __slots__ = ("_values", "max_values", "min_values", "options", "required")

    def __init__(
        self,
        *,
        options: Sequence[CheckboxGroupOption] = (),
        custom_id: str | None = None,
        min_values: int | None = None,
        max_values: int | None = None,
        required: bool = True,
        id: int | None = None,
    ) -> None:
        """A checkbox group of `options` (add more with `add_option`)."""
        super().__init__(custom_id=custom_id, id=id)
        self.options: list[CheckboxGroupOption] = list(options)
        self.min_values: int | None = min_values
        self.max_values: int | None = max_values
        self.required: bool = required
        self._values: list[str] = []

    @property
    def values(self) -> list[str]:
        """The values of the options checked."""
        return list(self._values)

    def add_option(
        self, *, label: str, value: str | None = None, description: str | None = None, default: bool = False
    ) -> None:
        """Add an option; its value is its label when not given."""
        self.options.append(
            CheckboxGroupOption(
                label=label,
                value=value if value is not None else label,
                description=unset_if_none(description),
                default=default or UNSET,
            )
        )

    @override
    def refresh(self, interaction: Interaction, values: Sequence[str], resolved: ResolvedData | None) -> None:
        self._values = list(values)

    @override
    def validate(self) -> None:
        super().validate()
        _check_options(self, self.options, 1, CHECKBOX_GROUP_MAX_OPTIONS)
        check_choices(
            self,
            min_values=self.min_values,
            max_values=self.max_values,
            high=CHECKBOX_GROUP_MAX_OPTIONS,
            required=self.required,
        )

    @override
    def to_component(self) -> CheckboxGroupPayload:
        """The checkbox group as Discord takes it."""
        return CheckboxGroupPayload(
            id=unset_if_none(self.id),
            custom_id=self.custom_id,
            options=self.options,
            min_values=unset_if_none(self.min_values),
            max_values=unset_if_none(self.max_values),
            required=self.required,
        )

    @override
    def __repr__(self) -> str:
        return f"<CheckboxGroup custom_id={self.custom_id!r} options={len(self.options)}>"


class Checkbox(InteractiveItem):
    """A single yes-or-no checkbox; `value` holds whether it was checked.

    Discord cannot make a checkbox required; a `CheckboxGroup` with one option can be.

    Discord: https://docs.discord.com/developers/components/reference#checkbox
    """

    __slots__ = ("_value", "default")

    def __init__(self, *, custom_id: str | None = None, default: bool = False, id: int | None = None) -> None:
        """A checkbox, checked to begin with when `default` is set."""
        super().__init__(custom_id=custom_id, id=id)
        self.default: bool = default
        self._value: bool | None = None

    @property
    def value(self) -> bool:
        """Whether it was checked (`default` until the modal is submitted)."""
        return self.default if self._value is None else self._value

    @override
    def refresh(self, interaction: Interaction, values: Sequence[str], resolved: ResolvedData | None) -> None:
        self._value = bool(values)

    @override
    def to_component(self) -> CheckboxPayload:
        """The checkbox as Discord takes it."""
        return CheckboxPayload(
            id=unset_if_none(self.id), custom_id=self.custom_id, default=self.default or UNSET
        )

    @override
    def __repr__(self) -> str:
        return f"<Checkbox custom_id={self.custom_id!r}>"
