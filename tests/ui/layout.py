import msgspec
import pytest

from shoal.core.codec import encode_json
from shoal.ui.action_row import ActionRow
from shoal.ui.button import Button
from shoal.ui.content import Separator, TextDisplay, Thumbnail
from shoal.ui.item import Item
from shoal.ui.layout import Container, Section
from tests.support.calls import call_unchecked


def rendered(item: Item) -> object:
    return msgspec.json.decode(encode_json(item.to_component()))


def test_a_section_puts_text_beside_an_accessory() -> None:
    section = Section("Line one", TextDisplay("Line two"), accessory=Thumbnail("https://e.com/a.png"))
    section.validate()
    assert rendered(section) == {
        "type": 9,
        "components": [{"type": 10, "content": "Line one"}, {"type": 10, "content": "Line two"}],
        "accessory": {"type": 11, "media": {"url": "https://e.com/a.png"}},
    }
    assert [text.content for text in section.texts] == ["Line one", "Line two"]
    assert all(child.parent is section for child in section.children)
    assert section.count() == 4


def test_a_section_accessory_can_be_swapped() -> None:
    old = Thumbnail("https://e.com/a.png")
    section = Section("x", accessory=old)
    new = Button(label="Open", custom_id="open")
    section.accessory = new
    assert section.accessory is new
    assert new.parent is section
    assert old.parent is None
    section.remove_item(section.texts[0])
    with pytest.raises(ValueError, match="1 to 3 text displays"):
        section.validate()


def test_a_section_holds_one_to_three_texts_and_a_button_or_thumbnail() -> None:
    with pytest.raises(ValueError, match="1 to 3 text displays"):
        Section("a", "b", "c", "d", accessory=Button()).validate()
    with pytest.raises(TypeError, match="button or a thumbnail"):
        call_unchecked(Section, "a", accessory=TextDisplay("x"))
    with pytest.raises(TypeError, match="text displays"):
        call_unchecked(Section("a", accessory=Button()).add_item, Separator())


def test_a_container_renders_its_items_and_accent() -> None:
    box = Container(TextDisplay("Hi"), Separator(), accent_color=0x5865F2, spoiler=True, id=9)
    box.validate()
    assert rendered(box) == {
        "type": 17,
        "id": 9,
        "components": [{"type": 10, "content": "Hi"}, {"type": 14, "divider": True, "spacing": 1}],
        "accent_color": 0x5865F2,
        "spoiler": True,
    }
    assert box.accent_colour == box.accent_color == 0x5865F2
    box.accent_color = None
    assert rendered(box) == {
        "type": 17,
        "id": 9,
        "components": [{"type": 10, "content": "Hi"}, {"type": 14, "divider": True, "spacing": 1}],
        "spoiler": True,
    }


def test_a_container_refuses_what_discord_would() -> None:
    with pytest.raises(ValueError, match="accent_colour"):
        Container(accent_colour=0x1000000).validate()
    with pytest.raises(TypeError, match="a container holds"):
        call_unchecked(Container().add_item, Button())


def test_a_container_subclass_copies_its_items_for_each_instance() -> None:
    class Card(Container):
        heading = TextDisplay("## Card")
        row = ActionRow(Button(custom_id="card:open"))

    first, second = Card(), Card()
    assert first.heading is not second.heading
    assert first.heading is not Card.heading
    assert first.children == [first.heading, first.row]
    assert first.row.children[0] is not second.row.children[0]
    removed = first.remove_item(first.heading)
    assert removed.children == [first.row]
    first.clear_items()
    assert first.children == []
    assert first.row.parent is None


def test_items_declared_on_a_container_must_fit_in_one() -> None:
    class Wrong(Container):
        stray = Button()

    with pytest.raises(TypeError, match="a container holds"):
        Wrong()
