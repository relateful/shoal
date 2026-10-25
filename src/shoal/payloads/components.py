"""Message and modal components: buttons, selects, text inputs and the Components V2 layout.

Every component is a struct tagged by its `type`, so building one never needs the number and
decoding picks the right class. Messages and modals take different top-level components, and each
layout takes its own children; the `*Child` and `*Component` unions encode those rules, so an invalid
layout is a type error.

**Receiving.** Discord adds component types over time (radio groups and checkboxes are recent), and a
strictly typed union would make a whole message fail to decode the day a new one appears. Components
in received payloads are therefore kept as plain JSON values (`RawComponent`), which also survive the
cache's msgpack snapshots unchanged, and `parse_components` turns them into these types, with an
`UnknownComponent` for anything newer than this version of Shoal.

Discord: https://docs.discord.com/developers/components/reference
"""

from collections.abc import Sequence

import msgspec
from msgspec import UNSET, UnsetType

from shoal.core.codec import JSONObject, PayloadDecodeError, convert
from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload
from shoal.payloads.channel import ChannelType
from shoal.payloads.emoji import PartialEmoji


class ComponentType(DiscordIntEnum):
    """What a component is.

    Discord: https://docs.discord.com/developers/components/reference#component-object-component-types
    """

    ACTION_ROW = 1
    BUTTON = 2
    STRING_SELECT = 3
    TEXT_INPUT = 4
    USER_SELECT = 5
    ROLE_SELECT = 6
    MENTIONABLE_SELECT = 7
    CHANNEL_SELECT = 8
    SECTION = 9
    TEXT_DISPLAY = 10
    THUMBNAIL = 11
    MEDIA_GALLERY = 12
    FILE = 13
    SEPARATOR = 14
    CONTAINER = 17
    LABEL = 18
    FILE_UPLOAD = 19
    RADIO_GROUP = 21
    CHECKBOX_GROUP = 22
    CHECKBOX = 23


class ButtonStyle(DiscordIntEnum):
    """How a button looks, and what it needs: `custom_id`, `url` or `sku_id`.

    Discord: https://docs.discord.com/developers/components/reference#button-button-styles
    """

    PRIMARY = 1
    SECONDARY = 2
    SUCCESS = 3
    DANGER = 4
    LINK = 5
    """Opens `url`; sends no interaction."""
    PREMIUM = 6
    """Buys `sku_id`; sends no interaction."""


class TextInputStyle(DiscordIntEnum):
    """Single-line or multi-line text input.

    Discord: https://docs.discord.com/developers/components/reference#text-input-text-input-styles
    """

    SHORT = 1
    PARAGRAPH = 2


class SeparatorSpacing(DiscordIntEnum):
    """How much padding a separator adds.

    Discord: https://docs.discord.com/developers/components/reference#separator-separator-structure
    """

    SMALL = 1
    LARGE = 2


class SelectDefaultValueType(DiscordStrEnum):
    """What a select menu's default value refers to.

    Discord: https://docs.discord.com/developers/components/reference#user-select-select-default-value-structure
    """

    CHANNEL = "channel"
    ROLE = "role"
    USER = "user"


class UnfurledMediaItemFlags(BaseFlags):
    """Facts Discord adds about a media item.

    Discord: https://docs.discord.com/developers/components/reference#unfurled-media-item-unfurled-media-item-flags
    """

    __slots__ = ()

    is_animated = flag(0)


class UnfurledMediaItem(Payload):
    """An image, video or file: a URL, or `attachment://<filename>` for a file sent with the message.

    Only `url` is sent; Discord fills in the rest when it returns the component.

    Discord: https://docs.discord.com/developers/components/reference#unfurled-media-item-unfurled-media-item-structure
    """

    url: str
    proxy_url: str | UnsetType = UNSET
    height: int | UnsetType | None = UNSET
    width: int | UnsetType | None = UNSET
    placeholder: str | UnsetType = UNSET
    """A thumbhash of the image, for showing while it loads."""
    placeholder_version: int | UnsetType = UNSET
    content_type: str | UnsetType = UNSET
    flags: UnfurledMediaItemFlags | UnsetType = UNSET
    attachment_id: Snowflake | UnsetType = UNSET


class SelectOption(Payload):
    """One option of a string select.

    Discord: https://docs.discord.com/developers/components/reference#string-select-select-option-structure
    """

    label: str
    value: str
    description: str | UnsetType = UNSET
    emoji: PartialEmoji | UnsetType = UNSET
    default: bool | UnsetType = UNSET


class SelectDefaultValue(Payload):
    """A user, role or channel a select menu starts with selected.

    Discord: https://docs.discord.com/developers/components/reference#user-select-select-default-value-structure
    """

    id: Snowflake
    type: SelectDefaultValueType


class MediaGalleryItem(Payload):
    """One image or video in a media gallery.

    Discord: https://docs.discord.com/developers/components/reference#media-gallery-media-gallery-item-structure
    """

    media: UnfurledMediaItem
    description: str | UnsetType | None = UNSET
    """Alt text, up to 1024 characters."""
    spoiler: bool | UnsetType = UNSET


class RadioGroupOption(Payload):
    """One choice of a radio group.

    Discord: https://docs.discord.com/developers/components/reference#radio-group-option-structure
    """

    value: str
    label: str
    description: str | UnsetType = UNSET
    default: bool | UnsetType = UNSET


class CheckboxGroupOption(Payload):
    """One checkbox of a checkbox group.

    Discord: https://docs.discord.com/developers/components/reference#checkbox-group-option-structure
    """

    value: str
    label: str
    description: str | UnsetType = UNSET
    default: bool | UnsetType = UNSET


class Button(Payload, tag=2, tag_field="type"):
    """A button. Interactive styles need `custom_id`, `LINK` needs `url`, `PREMIUM` needs `sku_id`.

    Discord: https://docs.discord.com/developers/components/reference#button
    """

    id: int | UnsetType = UNSET
    style: ButtonStyle
    label: str | UnsetType = UNSET
    """Up to 80 characters."""
    emoji: PartialEmoji | UnsetType = UNSET
    custom_id: str | UnsetType = UNSET
    sku_id: Snowflake | UnsetType = UNSET
    url: str | UnsetType = UNSET
    disabled: bool | UnsetType = UNSET


class StringSelect(Payload, tag=3, tag_field="type"):
    """A select menu with options the app defines.

    Discord: https://docs.discord.com/developers/components/reference#string-select
    """

    id: int | UnsetType = UNSET
    custom_id: str
    options: list[SelectOption]
    """At most 25."""
    placeholder: str | UnsetType = UNSET
    min_values: int | UnsetType = UNSET
    max_values: int | UnsetType = UNSET
    required: bool | UnsetType = UNSET
    """Modals only; ignored in messages."""
    disabled: bool | UnsetType = UNSET
    """Messages only; an error in modals."""


class TextInput(Payload, tag=4, tag_field="type"):
    """A text field in a modal. Put it in a `Label`; text inputs in action rows are deprecated.

    Discord: https://docs.discord.com/developers/components/reference#text-input
    """

    id: int | UnsetType = UNSET
    custom_id: str
    style: TextInputStyle
    min_length: int | UnsetType = UNSET
    max_length: int | UnsetType = UNSET
    required: bool | UnsetType = UNSET
    """Defaults to `True`."""
    value: str | UnsetType = UNSET
    """Pre-filled text."""
    placeholder: str | UnsetType = UNSET


class UserSelect(Payload, tag=5, tag_field="type"):
    """A select menu of users.

    Discord: https://docs.discord.com/developers/components/reference#user-select
    """

    id: int | UnsetType = UNSET
    custom_id: str
    placeholder: str | UnsetType = UNSET
    default_values: list[SelectDefaultValue] | UnsetType = UNSET
    min_values: int | UnsetType = UNSET
    max_values: int | UnsetType = UNSET
    required: bool | UnsetType = UNSET
    """Modals only; ignored in messages."""
    disabled: bool | UnsetType = UNSET
    """Messages only; an error in modals."""


class RoleSelect(Payload, tag=6, tag_field="type"):
    """A select menu of roles.

    Discord: https://docs.discord.com/developers/components/reference#role-select
    """

    id: int | UnsetType = UNSET
    custom_id: str
    placeholder: str | UnsetType = UNSET
    default_values: list[SelectDefaultValue] | UnsetType = UNSET
    min_values: int | UnsetType = UNSET
    max_values: int | UnsetType = UNSET
    required: bool | UnsetType = UNSET
    """Modals only; ignored in messages."""
    disabled: bool | UnsetType = UNSET
    """Messages only; an error in modals."""


class MentionableSelect(Payload, tag=7, tag_field="type"):
    """A select menu of users and roles.

    Discord: https://docs.discord.com/developers/components/reference#mentionable-select
    """

    id: int | UnsetType = UNSET
    custom_id: str
    placeholder: str | UnsetType = UNSET
    default_values: list[SelectDefaultValue] | UnsetType = UNSET
    min_values: int | UnsetType = UNSET
    max_values: int | UnsetType = UNSET
    required: bool | UnsetType = UNSET
    """Modals only; ignored in messages."""
    disabled: bool | UnsetType = UNSET
    """Messages only; an error in modals."""


class ChannelSelect(Payload, tag=8, tag_field="type"):
    """A select menu of channels.

    Discord: https://docs.discord.com/developers/components/reference#channel-select
    """

    id: int | UnsetType = UNSET
    custom_id: str
    channel_types: list[ChannelType] | UnsetType = UNSET
    placeholder: str | UnsetType = UNSET
    default_values: list[SelectDefaultValue] | UnsetType = UNSET
    min_values: int | UnsetType = UNSET
    max_values: int | UnsetType = UNSET
    required: bool | UnsetType = UNSET
    """Modals only; ignored in messages."""
    disabled: bool | UnsetType = UNSET
    """Messages only; an error in modals."""


class TextDisplay(Payload, tag=10, tag_field="type"):
    """Markdown text, like a message's content.

    Discord: https://docs.discord.com/developers/components/reference#text-display
    """

    id: int | UnsetType = UNSET
    content: str


class Thumbnail(Payload, tag=11, tag_field="type"):
    """A small image, used as a section's accessory.

    Discord: https://docs.discord.com/developers/components/reference#thumbnail
    """

    id: int | UnsetType = UNSET
    media: UnfurledMediaItem
    description: str | UnsetType | None = UNSET
    """Alt text, up to 1024 characters."""
    spoiler: bool | UnsetType = UNSET


class MediaGallery(Payload, tag=12, tag_field="type"):
    """One to ten images or videos in a grid.

    Discord: https://docs.discord.com/developers/components/reference#media-gallery
    """

    id: int | UnsetType = UNSET
    items: list[MediaGalleryItem]


class FileComponent(Payload, tag=13, tag_field="type"):
    """An attached file shown in the message. Discord calls it "File".

    `file.url` must be an `attachment://<filename>` reference. `name` and `size` are filled in by
    Discord when it returns the component; values sent are ignored.

    Discord: https://docs.discord.com/developers/components/reference#file
    """

    id: int | UnsetType = UNSET
    file: UnfurledMediaItem
    spoiler: bool | UnsetType = UNSET
    name: str | UnsetType = UNSET
    size: int | UnsetType = UNSET


class Separator(Payload, tag=14, tag_field="type"):
    """Vertical space between components, with or without a line.

    Discord: https://docs.discord.com/developers/components/reference#separator
    """

    id: int | UnsetType = UNSET
    divider: bool | UnsetType = UNSET
    """Defaults to `True`."""
    spacing: SeparatorSpacing | UnsetType = UNSET


class FileUpload(Payload, tag=19, tag_field="type"):
    """Lets the user upload files in a modal.

    Discord: https://docs.discord.com/developers/components/reference#file-upload
    """

    id: int | UnsetType = UNSET
    custom_id: str
    min_values: int | UnsetType = UNSET
    max_values: int | UnsetType = UNSET
    """At most 10."""
    required: bool | UnsetType = UNSET
    file_types: list[str] | UnsetType = UNSET
    """`image`, `video`, `audio`, or dot-prefixed extensions."""


class RadioGroup(Payload, tag=21, tag_field="type"):
    """A single choice between two to ten options, in a modal.

    Discord: https://docs.discord.com/developers/components/reference#radio-group
    """

    id: int | UnsetType = UNSET
    custom_id: str
    options: list[RadioGroupOption]
    required: bool | UnsetType = UNSET
    """Defaults to `True`."""


class CheckboxGroup(Payload, tag=22, tag_field="type"):
    """Several checkboxes, in a modal.

    Discord: https://docs.discord.com/developers/components/reference#checkbox-group
    """

    id: int | UnsetType = UNSET
    custom_id: str
    options: list[CheckboxGroupOption]
    min_values: int | UnsetType = UNSET
    max_values: int | UnsetType = UNSET
    required: bool | UnsetType = UNSET
    """Defaults to `True`."""


class Checkbox(Payload, tag=23, tag_field="type"):
    """A single yes-or-no checkbox, in a modal.

    Discord: https://docs.discord.com/developers/components/reference#checkbox
    """

    id: int | UnsetType = UNSET
    custom_id: str
    default: bool | UnsetType = UNSET


type ActionRowChild = (
    Button | StringSelect | UserSelect | RoleSelect | MentionableSelect | ChannelSelect | TextInput
)
"""What an action row holds: up to five buttons, or one select. Text inputs only in legacy modals.

Discord: https://docs.discord.com/developers/components/reference#action-row-action-row-child-components
"""


class ActionRow(Payload, tag=1, tag_field="type"):
    """A row of up to five buttons, or a single select menu.

    Discord: https://docs.discord.com/developers/components/reference#action-row
    """

    id: int | UnsetType = UNSET
    components: list[ActionRowChild]


type SectionAccessory = Button | Thumbnail
"""What sits beside a section's text.

Discord: https://docs.discord.com/developers/components/reference#section-section-accessory-components
"""


class Section(Payload, tag=9, tag_field="type"):
    """One to three text displays with a button or thumbnail beside them.

    Discord: https://docs.discord.com/developers/components/reference#section
    """

    id: int | UnsetType = UNSET
    components: list[TextDisplay]
    accessory: SectionAccessory


type ContainerChild = ActionRow | TextDisplay | Section | MediaGallery | Separator | FileComponent
"""What a container can hold.

Discord: https://docs.discord.com/developers/components/reference#container-container-child-components
"""


class Container(Payload, tag=17, tag_field="type"):
    """A visual box around other components, with an optional accent colour.

    Discord: https://docs.discord.com/developers/components/reference#container
    """

    id: int | UnsetType = UNSET
    components: list[ContainerChild]
    accent_color: int | UnsetType | None = UNSET
    """RGB from `0x000000` to `0xFFFFFF`."""
    spoiler: bool | UnsetType = UNSET


type LabelChild = (
    TextInput
    | StringSelect
    | UserSelect
    | RoleSelect
    | MentionableSelect
    | ChannelSelect
    | FileUpload
    | RadioGroup
    | CheckboxGroup
    | Checkbox
)
"""What a label can describe.

Discord: https://docs.discord.com/developers/components/reference#label-label-child-components
"""


class Label(Payload, tag=18, tag_field="type"):
    """A title and description for one modal input.

    Discord: https://docs.discord.com/developers/components/reference#label
    """

    id: int | UnsetType = UNSET
    label: str
    """Up to 45 characters."""
    description: str | UnsetType = UNSET
    component: LabelChild


type MessageComponent = (
    ActionRow | Section | TextDisplay | MediaGallery | FileComponent | Separator | Container
)
"""A top-level component of a message. Every type but `ActionRow` needs `MessageFlags.is_components_v2`.

Discord: https://docs.discord.com/developers/components/reference#component-object-component-types
"""

type ModalComponent = Label | TextDisplay | ActionRow
"""A top-level component of a modal. Action rows with text inputs are deprecated; use labels.

Discord: https://docs.discord.com/developers/components/reference#component-object-component-types
"""

type Component = (
    ActionRow
    | Button
    | StringSelect
    | TextInput
    | UserSelect
    | RoleSelect
    | MentionableSelect
    | ChannelSelect
    | Section
    | TextDisplay
    | Thumbnail
    | MediaGallery
    | FileComponent
    | Separator
    | Container
    | Label
    | FileUpload
    | RadioGroup
    | CheckboxGroup
    | Checkbox
)
"""Any component this version of Shoal knows.

Discord: https://docs.discord.com/developers/components/reference#component-object-component-types
"""


type RawComponent = JSONObject
"""A component as received: its JSON object, not yet checked against a component type."""


class _OneComponent(msgspec.Struct, gc=False):
    """Lets `convert` check one received component against the `Component` union."""

    component: Component


class UnknownComponent(Payload):
    """A component Shoal cannot decode: a newer type, or a known one containing a newer type.

    `data` is the component exactly as Discord sent it.

    Discord: https://docs.discord.com/developers/components/reference#component-object-component-types
    """

    type: int
    id: int | UnsetType = UNSET
    data: RawComponent


def parse_components(raw: Sequence[RawComponent]) -> list[Component | UnknownComponent]:
    """Decode received components, keeping any that cannot be decoded as `UnknownComponent`.

    A component is decoded with all of its children or not at all, so a container holding a newer
    component type comes back as one `UnknownComponent` with its full data.

    Raises:
        PayloadDecodeError: An entry is not a component at all (no integer `type`).
    """
    parsed: list[Component | UnknownComponent] = []
    for item in raw:
        try:
            parsed.append(convert({"component": item}, _OneComponent).component)
        except PayloadDecodeError:
            kind = item.get("type")
            if not isinstance(kind, int) or isinstance(kind, bool):
                raise
            identifier = item.get("id")
            parsed.append(
                UnknownComponent(
                    type=kind,
                    id=identifier
                    if isinstance(identifier, int) and not isinstance(identifier, bool)
                    else UNSET,
                    data=item,
                )
            )
    return parsed
