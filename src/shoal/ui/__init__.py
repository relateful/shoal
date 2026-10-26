"""Views, layouts, buttons, selects and modals.

    from shoal import ButtonStyle, ui

    class Confirm(ui.View):
        @ui.button(label="Confirm", style=ButtonStyle.SUCCESS)
        async def confirm(self, interaction, button): ...

A `View` puts buttons and selects in action rows under a message's content. A `LayoutView` is the
whole message in Components V2: text displays, sections, containers, media galleries, files and
separators, with action rows among them. A `Modal` asks for text, choices, files and checkboxes.

Discord: https://docs.discord.com/developers/components/reference
"""

from shoal.models.emoji import EmojiLike
from shoal.ui.action_row import ActionRow
from shoal.ui.button import Button, button
from shoal.ui.content import File, MediaGallery, Separator, TextDisplay, Thumbnail
from shoal.ui.inputs import Checkbox, CheckboxGroup, FileUpload, RadioGroup
from shoal.ui.item import InteractiveItem, Item
from shoal.ui.label import Label
from shoal.ui.layout import Container, Section
from shoal.ui.modal import Modal
from shoal.ui.select import (
    AnySelect,
    BaseSelect,
    ChannelSelect,
    MentionableSelect,
    RoleSelect,
    Select,
    SelectedChannel,
    UserSelect,
    select,
)
from shoal.ui.text_input import TextInput
from shoal.ui.view import BaseView, LayoutView, View

__all__ = [
    "ActionRow",
    "AnySelect",
    "BaseSelect",
    "BaseView",
    "Button",
    "ChannelSelect",
    "Checkbox",
    "CheckboxGroup",
    "Container",
    "EmojiLike",
    "File",
    "FileUpload",
    "InteractiveItem",
    "Item",
    "Label",
    "LayoutView",
    "MediaGallery",
    "MentionableSelect",
    "Modal",
    "RadioGroup",
    "RoleSelect",
    "Section",
    "Select",
    "SelectedChannel",
    "Separator",
    "TextDisplay",
    "TextInput",
    "Thumbnail",
    "UserSelect",
    "View",
    "button",
    "select",
]
