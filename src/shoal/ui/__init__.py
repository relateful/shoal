"""Views, buttons, selects and modals.

    from shoal import ui

    class Confirm(ui.View):
        @ui.button(label="Confirm", style=ButtonStyle.SUCCESS)
        async def confirm(self, interaction, button): ...

Discord: https://docs.discord.com/developers/components/reference
"""

from shoal.ui.button import Button, EmojiLike, button
from shoal.ui.item import Item
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
from shoal.ui.view import View

__all__ = [
    "AnySelect",
    "BaseSelect",
    "Button",
    "ChannelSelect",
    "EmojiLike",
    "Item",
    "MentionableSelect",
    "Modal",
    "RoleSelect",
    "Select",
    "SelectedChannel",
    "TextInput",
    "UserSelect",
    "View",
    "button",
    "select",
]
