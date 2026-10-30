"""Colours: an `int` of the form `0xRRGGBB`, with names for Discord's palette.

    embed = Embed(title="Done", colour=Colour.green())
    role_colour = Colour.from_str("#5865F2")

A `Colour` is an `int`, so it goes anywhere a colour is taken (embeds, roles), and colours read from
Discord (`Role.colour`, `Member.colour`, `Embed.colour`) are `Colour`s. `Color` is the same class.
"""

import colorsys
import random
import re
from typing import Final, Self, override

_HEX: Final = re.compile(r"(?:0x|#)?(?P<hex>[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})")
_RGB: Final = re.compile(r"rgb\(\s*(?P<r>[0-9.]+%?)\s*,\s*(?P<g>[0-9.]+%?)\s*,\s*(?P<b>[0-9.]+%?)\s*\)")
_MAX: Final = 255
_WHITE: Final = 0xFFFFFF


class Colour(int):
    """A colour as `0xRRGGBB`: `Colour(0x5865F2)`, `Colour.from_rgb(88, 101, 242)` or `Colour.blurple()`."""

    __slots__ = ()

    def __new__(cls, value: int = 0, /) -> Self:
        """Check the colour fits in `0xRRGGBB`.

        Raises:
            ValueError: `value` is not between 0 and `0xFFFFFF`.
        """
        if not 0 <= value <= _WHITE:
            msg = f"a colour is between 0 and 0xFFFFFF, not {value:#x}"
            raise ValueError(msg)
        return super().__new__(cls, value)

    @property
    def value(self) -> int:
        """The colour as a plain `int`."""
        return int(self)

    @property
    def r(self) -> int:
        """The red part, 0 to 255."""
        return (int(self) >> 16) & _MAX

    @property
    def g(self) -> int:
        """The green part, 0 to 255."""
        return (int(self) >> 8) & _MAX

    @property
    def b(self) -> int:
        """The blue part, 0 to 255."""
        return int(self) & _MAX

    def to_rgb(self) -> tuple[int, int, int]:
        """The red, green and blue parts, each 0 to 255."""
        return self.r, self.g, self.b

    @classmethod
    def from_rgb(cls, r: int, g: int, b: int) -> Self:
        """A colour from red, green and blue, each 0 to 255.

        Raises:
            ValueError: A part is outside 0 to 255.
        """
        for part in (r, g, b):
            if not 0 <= part <= _MAX:
                msg = f"each part of a colour is between 0 and 255, not {part}"
                raise ValueError(msg)
        return cls((r << 16) | (g << 8) | b)

    @classmethod
    def from_hsv(cls, h: float, s: float, v: float) -> Self:
        """A colour from hue, saturation and value, each 0 to 1."""
        red, green, blue = colorsys.hsv_to_rgb(h, s, v)
        return cls.from_rgb(round(red * _MAX), round(green * _MAX), round(blue * _MAX))

    @classmethod
    def from_str(cls, value: str) -> Self:
        """A colour from `#RRGGBB`, `0xRRGGBB`, `RRGGBB`, `#RGB` or `rgb(r, g, b)`.

        `rgb` takes 0 to 255 for each part, or percentages.

        Raises:
            ValueError: `value` is none of those.
        """
        text = value.strip()
        hex_match = _HEX.fullmatch(text)
        if hex_match is not None:
            digits = hex_match["hex"]
            return cls(int(digits if len(digits) == 6 else "".join(digit * 2 for digit in digits), 16))  # noqa: PLR2004 - RRGGBB
        rgb = _RGB.fullmatch(text)
        if rgb is None:
            msg = f"{value!r} is not a colour"
            raise ValueError(msg)
        parts: list[int] = []
        for part in (rgb["r"], rgb["g"], rgb["b"]):
            level = float(part[:-1]) * _MAX / 100 if part.endswith("%") else float(part)
            if not 0 <= level <= _MAX or (not part.endswith("%") and not level.is_integer()):
                msg = f"{value!r} is not a colour"
                raise ValueError(msg)
            parts.append(round(level))
        return cls.from_rgb(*parts)

    @classmethod
    def random(cls, *, seed: int | str | None = None) -> Self:
        """A random fully saturated, fully bright colour; the same `seed` gives the same colour."""
        rng = random.Random(seed)  # noqa: S311 - a colour, not a secret
        return cls.from_hsv(rng.random(), 1, 1)

    @classmethod
    def default(cls) -> Self:
        """No colour: 0, which Discord shows as its default."""
        return cls(0)

    @classmethod
    def blurple(cls) -> Self:
        """Discord's brand blurple, `0x5865F2`."""
        return cls(0x5865F2)

    @classmethod
    def og_blurple(cls) -> Self:
        """Discord's blurple before 2021, `0x7289DA`."""
        return cls(0x7289DA)

    @classmethod
    def greyple(cls) -> Self:
        """`0x99AAB5`."""
        return cls(0x99AAB5)

    @classmethod
    def brand_green(cls) -> Self:
        """Discord's brand green, `0x57F287`."""
        return cls(0x57F287)

    @classmethod
    def brand_red(cls) -> Self:
        """Discord's brand red, `0xED4245`."""
        return cls(0xED4245)

    @classmethod
    def yellow(cls) -> Self:
        """Discord's brand yellow, `0xFEE75C`."""
        return cls(0xFEE75C)

    @classmethod
    def fuchsia(cls) -> Self:
        """Discord's brand fuchsia, `0xEB459E`."""
        return cls(0xEB459E)

    @classmethod
    def teal(cls) -> Self:
        """`0x1ABC9C`."""
        return cls(0x1ABC9C)

    @classmethod
    def dark_teal(cls) -> Self:
        """`0x11806A`."""
        return cls(0x11806A)

    @classmethod
    def green(cls) -> Self:
        """`0x2ECC71`."""
        return cls(0x2ECC71)

    @classmethod
    def dark_green(cls) -> Self:
        """`0x1F8B4C`."""
        return cls(0x1F8B4C)

    @classmethod
    def blue(cls) -> Self:
        """`0x3498DB`."""
        return cls(0x3498DB)

    @classmethod
    def dark_blue(cls) -> Self:
        """`0x206694`."""
        return cls(0x206694)

    @classmethod
    def purple(cls) -> Self:
        """`0x9B59B6`."""
        return cls(0x9B59B6)

    @classmethod
    def dark_purple(cls) -> Self:
        """`0x71368A`."""
        return cls(0x71368A)

    @classmethod
    def magenta(cls) -> Self:
        """`0xE91E63`."""
        return cls(0xE91E63)

    @classmethod
    def dark_magenta(cls) -> Self:
        """`0xAD1457`."""
        return cls(0xAD1457)

    @classmethod
    def gold(cls) -> Self:
        """`0xF1C40F`."""
        return cls(0xF1C40F)

    @classmethod
    def dark_gold(cls) -> Self:
        """`0xC27C0E`."""
        return cls(0xC27C0E)

    @classmethod
    def orange(cls) -> Self:
        """`0xE67E22`."""
        return cls(0xE67E22)

    @classmethod
    def dark_orange(cls) -> Self:
        """`0xA84300`."""
        return cls(0xA84300)

    @classmethod
    def red(cls) -> Self:
        """`0xE74C3C`."""
        return cls(0xE74C3C)

    @classmethod
    def dark_red(cls) -> Self:
        """`0x992D22`."""
        return cls(0x992D22)

    @classmethod
    def lighter_grey(cls) -> Self:
        """`0x95A5A6`."""
        return cls(0x95A5A6)

    @classmethod
    def light_grey(cls) -> Self:
        """`0x979C9F`."""
        return cls(0x979C9F)

    @classmethod
    def dark_grey(cls) -> Self:
        """`0x607D8B`."""
        return cls(0x607D8B)

    @classmethod
    def darker_grey(cls) -> Self:
        """`0x546E7A`."""
        return cls(0x546E7A)

    @classmethod
    def lighter_gray(cls) -> Self:
        """The same as `lighter_grey`."""
        return cls.lighter_grey()

    @classmethod
    def light_gray(cls) -> Self:
        """The same as `light_grey`."""
        return cls.light_grey()

    @classmethod
    def dark_gray(cls) -> Self:
        """The same as `dark_grey`."""
        return cls.dark_grey()

    @classmethod
    def darker_gray(cls) -> Self:
        """The same as `darker_grey`."""
        return cls.darker_grey()

    @override
    def __str__(self) -> str:
        return f"#{int(self):06x}"

    @override
    def __repr__(self) -> str:
        return f"<Colour {self}>"


Color = Colour
