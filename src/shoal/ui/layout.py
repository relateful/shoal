"""Sections and containers: the layout components of a Components V2 message.

    class Profile(ui.Container):
        about = ui.Section("## Ada", "Joined in 2015", accessory=ui.Thumbnail(avatar_url))
        row = ui.ActionRow()

        @row.button(label="Wave")
        async def wave(self, interaction: Interaction, button: ui.Button) -> None:
            await interaction.response.send_message("👋")

    class Card(ui.LayoutView):
        profile = Profile(accent_colour=0x5865F2)

Discord: https://docs.discord.com/developers/components/reference#container
"""

from typing import ClassVar, Self, override

from msgspec import UNSET

from shoal.models.base import unset_if_none
from shoal.payloads.components import CONTAINER_ACCENT_COLOR_MAX, SECTION_MAX_COMPONENTS
from shoal.payloads.components import Container as ContainerPayload
from shoal.payloads.components import Section as SectionPayload
from shoal.ui.action_row import ActionRow
from shoal.ui.button import Button
from shoal.ui.content import File, MediaGallery, Separator, TextDisplay, Thumbnail
from shoal.ui.item import Item, check_count, instantiate, item_templates

type Accessory = Button | Thumbnail
"""What sits beside a section's text."""


class Section(Item):
    """One to three text displays with a button or a thumbnail beside them.

    Discord: https://docs.discord.com/developers/components/reference#section
    """

    __slots__ = ("_accessory", "_texts")

    is_v2: ClassVar[bool] = True

    def __init__(self, *children: TextDisplay | str, accessory: Accessory, id: int | None = None) -> None:
        """A section of `children` (text displays, or strings for them) beside `accessory`.

        Raises:
            TypeError: The accessory is not a button or a thumbnail, or a child is not text.
        """
        super().__init__(id=id)
        self._texts: list[TextDisplay] = []
        self._accessory: Accessory = _accessory(accessory)
        self.adopt(accessory)
        for child in children:
            self.add_item(child)

    @property
    @override
    def children(self) -> list[Item]:
        """The text displays, then the accessory."""
        return [*self._texts, self._accessory]

    @property
    def texts(self) -> list[TextDisplay]:
        """The text displays, in order."""
        return list(self._texts)

    @property
    def accessory(self) -> Accessory:
        """The button or thumbnail beside the text."""
        return self._accessory

    @accessory.setter
    def accessory(self, value: Accessory) -> None:
        self.release(self._accessory)
        self._accessory = _accessory(value)
        self.adopt(value)

    def add_item(self, item: TextDisplay | str) -> Self:
        """Add a text display (or a string for one).

        Raises:
            TypeError: `item` is not a text display or a string.
        """
        text = TextDisplay(item) if isinstance(item, str) else _text(item)
        self._texts.append(text)
        self.adopt(text)
        return self

    def remove_item(self, item: TextDisplay) -> Self:
        """Remove a text display (nothing happens if it is not in the section)."""
        if item in self._texts:
            self._texts.remove(item)
            self.release(item)
        return self

    @override
    def validate(self) -> None:
        super().validate()
        check_count(self, "text displays", len(self._texts), 1, SECTION_MAX_COMPONENTS)

    @override
    def to_component(self) -> SectionPayload:
        """The section as Discord takes it."""
        return SectionPayload(
            id=unset_if_none(self.id),
            components=[text.to_component() for text in self._texts],
            accessory=self._accessory.to_component(),
        )

    @override
    def __repr__(self) -> str:
        return f"<Section texts={len(self._texts)} accessory={self._accessory!r}>"


type ContainerItem = ActionRow | TextDisplay | Section | MediaGallery | Separator | File
"""What a container holds."""


class Container(Item):
    """A box around other components, with an optional accent colour.

    A subclass can declare its items as class attributes; each instance gets its own copies.

    Discord: https://docs.discord.com/developers/components/reference#container
    """

    __slots__ = ("_children", "accent_colour", "spoiler")

    is_v2: ClassVar[bool] = True

    __container_items__: ClassVar[list[tuple[str, Item]]] = []

    @override
    def __init_subclass__(cls) -> None:
        """Remember the items declared on the class, base classes first."""
        super().__init_subclass__()
        cls.__container_items__ = item_templates(cls)

    def __init__(
        self,
        *children: ContainerItem,
        accent_colour: int | None = None,
        accent_color: int | None = None,
        spoiler: bool = False,
        id: int | None = None,
    ) -> None:
        """A container of the class's items, then `children`; `accent_color` is `accent_colour`.

        Raises:
            TypeError: An item declared on the class cannot go in a container.
        """
        super().__init__(id=id)
        self._children: list[ContainerItem] = []
        self.accent_colour: int | None = accent_colour if accent_colour is not None else accent_color
        self.spoiler: bool = spoiler
        for item in instantiate(self, type(self).__container_items__):
            self.add_item(_container_item(item))
        for child in children:
            self.add_item(child)

    @property
    def accent_color(self) -> int | None:
        """The same as `accent_colour`."""
        return self.accent_colour

    @accent_color.setter
    def accent_color(self, value: int | None) -> None:
        self.accent_colour = value

    @property
    @override
    def children(self) -> list[Item]:
        """The items, in order."""
        return list(self._children)

    def add_item(self, item: ContainerItem) -> Self:
        """Add an item.

        Raises:
            TypeError: `item` cannot go in a container.
        """
        item = _container_item(item)
        self._children.append(item)
        self.adopt(item)
        return self

    def remove_item(self, item: ContainerItem) -> Self:
        """Remove an item (nothing happens if it is not in the container)."""
        if item in self._children:
            self._children.remove(item)
            self.release(item)
        return self

    def clear_items(self) -> Self:
        """Remove every item."""
        for item in self._children:
            self.release(item)
        self._children.clear()
        return self

    @override
    def validate(self) -> None:
        super().validate()
        if self.accent_colour is not None and not 0 <= self.accent_colour <= CONTAINER_ACCENT_COLOR_MAX:
            msg = f"{self!r}: accent_colour must be from 0 to {CONTAINER_ACCENT_COLOR_MAX:#x}"
            raise ValueError(msg)

    @override
    def to_component(self) -> ContainerPayload:
        """The container as Discord takes it."""
        return ContainerPayload(
            id=unset_if_none(self.id),
            components=[child.to_component() for child in self._children],
            accent_color=unset_if_none(self.accent_colour),
            spoiler=self.spoiler or UNSET,
        )

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__} items={len(self._children)}>"


def _accessory(item: Item) -> Accessory:
    if not isinstance(item, Button | Thumbnail):
        msg = f"a section's accessory is a button or a thumbnail, not {item!r}"
        raise TypeError(msg)
    return item


def _text(item: Item) -> TextDisplay:
    if not isinstance(item, TextDisplay):
        msg = f"a section holds text displays, not {item!r}"
        raise TypeError(msg)
    return item


def _container_item(item: Item) -> ContainerItem:
    """`item`, checked to be something a container holds.

    Raises:
        TypeError: It is not.
    """
    if not isinstance(item, ActionRow | TextDisplay | Section | MediaGallery | Separator | File):
        msg = f"a container holds rows, text, sections, galleries, separators and files, not {item!r}"
        raise TypeError(msg)
    return item
