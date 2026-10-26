"""Buttons, and the `@ui.button` decorator for buttons on a view.

    class Confirm(ui.View):
        @ui.button(label="Confirm", style=ButtonStyle.SUCCESS)
        async def confirm(self, interaction: Interaction, button: ui.Button) -> None:
            await interaction.response.send_message("Confirmed", ephemeral=True)
            self.stop()

Discord: https://docs.discord.com/developers/components/reference#button
"""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, override

from msgspec import UNSET

from shoal.client.interaction import Interaction
from shoal.core.snowflake import Snowflake
from shoal.models.emoji import Emoji
from shoal.payloads.components import Button as ButtonPayload
from shoal.payloads.components import ButtonStyle
from shoal.payloads.emoji import PartialEmoji
from shoal.ui.item import ITEM_FACTORY, Item

if TYPE_CHECKING:
    from shoal.ui.view import View

type EmojiLike = str | PartialEmoji | Emoji
"""An emoji on a component: a unicode emoji, or a custom emoji (its model or payload)."""


def partial_emoji(emoji: EmojiLike) -> PartialEmoji:
    """`emoji` as components take it."""
    if isinstance(emoji, str):
        return PartialEmoji(name=emoji)
    if isinstance(emoji, Emoji):
        return PartialEmoji(id=emoji.id, name=emoji.name, animated=emoji.animated)
    return emoji


class Button(Item):
    """A button. A link button (`url`) or a premium button (`sku_id`) sends no interaction.

    Discord: https://docs.discord.com/developers/components/reference#button
    """

    __slots__ = ("disabled", "emoji", "label", "sku_id", "style", "url")

    def __init__(
        self,
        *,
        style: ButtonStyle = ButtonStyle.SECONDARY,
        label: str | None = None,
        disabled: bool = False,
        custom_id: str | None = None,
        url: str | None = None,
        emoji: EmojiLike | None = None,
        row: int | None = None,
        sku_id: int | None = None,
    ) -> None:
        """A button; giving `url` makes it a link button, `sku_id` a premium button.

        Raises:
            ValueError: Both `url` and `custom_id` were given, or `row` is outside 0 to 4.
        """
        if url is not None and custom_id is not None:
            msg = "a link button cannot have a custom_id"
            raise ValueError(msg)
        super().__init__(custom_id=custom_id, row=row)
        self.style: ButtonStyle = (
            ButtonStyle.LINK if url is not None else ButtonStyle.PREMIUM if sku_id else style
        )
        self.label: str | None = label
        self.disabled: bool = disabled
        self.url: str | None = url
        self.emoji: PartialEmoji | None = partial_emoji(emoji) if emoji is not None else None
        self.sku_id: Snowflake | None = Snowflake(sku_id) if sku_id is not None else None

    @override
    def is_dispatchable(self) -> bool:
        return self.url is None and self.sku_id is None

    @override
    def to_component(self) -> ButtonPayload:
        """The button as Discord takes it."""
        dispatchable = self.is_dispatchable()
        return ButtonPayload(
            style=self.style,
            label=self.label if self.label is not None else UNSET,
            emoji=self.emoji if self.emoji is not None else UNSET,
            custom_id=self.custom_id if dispatchable else UNSET,
            sku_id=self.sku_id if self.sku_id is not None else UNSET,
            url=self.url if self.url is not None else UNSET,
            disabled=self.disabled or UNSET,
        )

    @override
    def __repr__(self) -> str:
        return f"<Button style={self.style.name} label={self.label!r} custom_id={self.custom_id!r}>"


type ButtonCallback[V: View] = Callable[[V, Interaction, Button], Awaitable[None]]
"""A view method decorated with `@ui.button`."""


def button[V: View](
    *,
    label: str | None = None,
    custom_id: str | None = None,
    disabled: bool = False,
    style: ButtonStyle = ButtonStyle.SECONDARY,
    emoji: EmojiLike | None = None,
    row: int | None = None,
) -> Callable[[ButtonCallback[V]], ButtonCallback[V]]:
    """Turn a view method into a button; the method runs when the button is pressed.

    The method takes `(self, interaction, button)`. Each view instance gets its own button.
    """

    def decorator(function: ButtonCallback[V]) -> ButtonCallback[V]:
        def make() -> Button:
            return Button(
                label=label, custom_id=custom_id, disabled=disabled, style=style, emoji=emoji, row=row
            )

        setattr(function, ITEM_FACTORY, make)
        return function

    return decorator
