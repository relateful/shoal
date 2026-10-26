import msgspec
import pytest

from shoal.core.codec import decode_json, encode_json
from shoal.core.snowflake import Snowflake
from shoal.models.emoji import Emoji
from shoal.payloads import ButtonStyle, PartialEmoji
from shoal.payloads import Emoji as EmojiPayload
from shoal.ui.button import Button
from tests.support.models import GUILD, World


def json(button: Button) -> object:
    return msgspec.json.decode(encode_json(button.to_component()))


def test_a_button_renders_what_was_set() -> None:
    button = Button(
        label="OK", style=ButtonStyle.SUCCESS, custom_id="ok", emoji="\N{THUMBS UP SIGN}", disabled=True
    )
    assert json(button) == {
        "type": 2,
        "style": 3,
        "label": "OK",
        "emoji": {"name": "\N{THUMBS UP SIGN}"},
        "custom_id": "ok",
        "disabled": True,
    }
    assert button.is_dispatchable()
    assert button.is_persistent()
    assert repr(button) == "<Button style=SUCCESS label='OK' custom_id='ok'>"


def test_link_and_premium_buttons_send_no_interaction() -> None:
    link = Button(label="Docs", url="https://example.com")
    assert link.style is ButtonStyle.LINK
    assert not link.is_dispatchable()
    assert link.is_persistent()
    assert json(link) == {"type": 2, "style": 5, "label": "Docs", "url": "https://example.com"}
    premium = Button(sku_id=5)
    assert premium.style is ButtonStyle.PREMIUM
    assert json(premium) == {"type": 2, "style": 6, "sku_id": "5"}
    with pytest.raises(ValueError, match="link button"):
        Button(url="https://example.com", custom_id="x")


def test_custom_ids_are_random_unless_given() -> None:
    first, second = Button(label="a"), Button(label="b")
    assert first.custom_id != second.custom_id
    assert len(first.custom_id) == 32
    assert not first.is_persistent()
    first.custom_id = "fixed"
    assert first.is_persistent()


def test_rows_are_checked() -> None:
    button = Button(row=4)
    assert button.row == 4
    with pytest.raises(ValueError, match="row"):
        Button(row=5)
    with pytest.raises(ValueError, match="row"):
        button.row = -1
    button.row = None
    assert button.row is None


def test_a_button_shows_a_custom_emoji_model() -> None:
    world = World()
    custom = Emoji(
        world.state,
        decode_json(encode_json({"id": "5", "name": "wave", "animated": True}), EmojiPayload),
        GUILD,
    )
    assert Button(label="Wave", emoji=custom).emoji == PartialEmoji(
        id=Snowflake(5), name="wave", animated=True
    )
