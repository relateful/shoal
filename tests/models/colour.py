import pytest

from shoal.core.codec import encode_json, encode_msgpack
from shoal.models.colour import Color, Colour
from shoal.models.embed import Embed


def test_parts_round_trip_through_rgb() -> None:
    colour = Colour.from_rgb(88, 101, 242)
    assert colour == 0x5865F2
    assert colour.to_rgb() == (88, 101, 242)
    assert (colour.r, colour.g, colour.b) == (88, 101, 242)
    assert colour.value == 0x5865F2
    assert type(colour.value) is int


def test_named_colours_and_the_color_spelling() -> None:
    assert Colour.blurple() == 0x5865F2
    assert Colour.default() == 0
    assert Color is Colour
    assert Colour.dark_gray() == Colour.dark_grey()


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("#5865F2", 0x5865F2),
        ("0x5865f2", 0x5865F2),
        ("5865F2", 0x5865F2),
        ("#fff", 0xFFFFFF),
        ("rgb(88, 101, 242)", 0x5865F2),
        ("rgb(100%, 0%, 0%)", 0xFF0000),
    ],
)
def test_from_str_reads_hex_and_rgb(text: str, value: int) -> None:
    assert Colour.from_str(text) == value


@pytest.mark.parametrize("text", ["blue", "#12345", "rgb(256, 0, 0)", "rgb(1.5, 0, 0)"])
def test_from_str_refuses_what_is_not_a_colour(text: str) -> None:
    with pytest.raises(ValueError, match="not a colour"):
        Colour.from_str(text)


@pytest.mark.parametrize("value", [-1, 0x1000000])
def test_refuses_values_outside_rrggbb(value: int) -> None:
    with pytest.raises(ValueError, match="between 0 and 0xFFFFFF"):
        Colour(value)


def test_from_hsv_and_seeded_random() -> None:
    assert Colour.from_hsv(0, 1, 1) == 0xFF0000
    assert Colour.random(seed="shoal") == Colour.random(seed="shoal")


def test_str_and_repr() -> None:
    assert str(Colour(0x00FF00)) == "#00ff00"
    assert repr(Colour(0x00FF00)) == "<Colour #00ff00>"


def test_encodes_as_a_plain_integer() -> None:
    embed = Embed(title="t", colour=Colour.red())
    assert b'"color":15158332' in encode_json(embed.to_payload())
    assert encode_msgpack(Colour(1)) == encode_msgpack(1)
    assert isinstance(embed.colour, Colour)
