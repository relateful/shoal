import msgspec
import pytest

from shoal.core.codec import encode_json
from shoal.payloads import MediaGalleryItem, SeparatorSpacing, UnfurledMediaItem
from shoal.rest.files import File as Upload
from shoal.ui.content import File, MediaGallery, Separator, TextDisplay, Thumbnail
from shoal.ui.item import Item


def rendered(item: Item) -> object:
    return msgspec.json.decode(encode_json(item.to_component()))


def test_a_text_display_renders_its_markdown() -> None:
    text = TextDisplay("# Hello", id=3)
    assert rendered(text) == {"type": 10, "id": 3, "content": "# Hello"}
    assert text.is_v2
    assert repr(text) == "<TextDisplay content='# Hello'>"


def test_media_is_a_url_or_a_file_sent_with_the_message() -> None:
    assert rendered(Thumbnail("https://e.com/a.png", description="A cat", spoiler=True)) == {
        "type": 11,
        "media": {"url": "https://e.com/a.png"},
        "description": "A cat",
        "spoiler": True,
    }
    # A spoiler file is uploaded under a SPOILER_ name, and the component must refer to that name.
    hidden = Upload(filename="cat.png", data=b"x", spoiler=True)
    assert Thumbnail(hidden).media == "attachment://SPOILER_cat.png"
    assert Upload(filename="cat.png", data=b"x").uri == "attachment://cat.png"


def test_a_gallery_takes_urls_files_and_items() -> None:
    upload = Upload(filename="b.png", data=b"x")
    item = MediaGalleryItem(media=UnfurledMediaItem(url="https://e.com/c.png"), spoiler=True)
    gallery = MediaGallery("https://e.com/a.png", upload, item)
    gallery.add_item("https://e.com/d.png", description="Alt", spoiler=True)
    gallery.validate()
    assert rendered(gallery) == {
        "type": 12,
        "items": [
            {"media": {"url": "https://e.com/a.png"}},
            {"media": {"url": "attachment://b.png"}},
            {"media": {"url": "https://e.com/c.png"}, "spoiler": True},
            {"media": {"url": "https://e.com/d.png"}, "description": "Alt", "spoiler": True},
        ],
    }
    assert repr(gallery) == "<MediaGallery items=4>"


@pytest.mark.parametrize(
    ("item", "problem"),
    [
        (MediaGallery(), "1 to 10 items"),
        (MediaGallery(*["https://e.com/a.png"] * 11), "1 to 10 items"),
        (Thumbnail("https://e.com/a.png", description="x" * 1025), "description is 1025"),
        (File("https://e.com/a.pdf"), "attachment://"),
        (TextDisplay("x", id=-1), "id must not be negative"),
    ],
)
def test_content_discord_would_refuse_is_refused(item: Item, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        item.validate()


def test_a_gallery_item_alt_text_is_limited() -> None:
    gallery = MediaGallery()
    gallery.add_item("https://e.com/a.png", description="x" * 1025)
    with pytest.raises(ValueError, match="an item's description"):
        gallery.validate()


def test_a_file_component_shows_an_uploaded_file() -> None:
    shown = File(Upload(filename="report.pdf", data=b"x"), spoiler=True)
    shown.validate()
    assert rendered(shown) == {"type": 13, "file": {"url": "attachment://report.pdf"}, "spoiler": True}
    assert repr(shown) == "<File media='attachment://report.pdf'>"


def test_a_separator_draws_a_line_unless_invisible() -> None:
    assert rendered(Separator()) == {"type": 14, "divider": True, "spacing": 1}
    quiet = Separator(visible=False, spacing=SeparatorSpacing.LARGE)
    assert rendered(quiet) == {"type": 14, "divider": False, "spacing": 2}
    assert repr(quiet) == "<Separator visible=False spacing=LARGE>"
