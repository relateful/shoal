"""Discord snowflake IDs.

Discord: https://docs.discord.com/developers/reference#snowflakes
"""

from datetime import UTC, datetime
from typing import Final, Self, override

DISCORD_EPOCH_MS: Final = 1_420_070_400_000
"""Milliseconds between the Unix epoch and the first second of 2015.

Discord: https://docs.discord.com/developers/reference#snowflakes
"""

UINT64_MAX: Final = (1 << 64) - 1
"""The largest unsigned 64-bit integer: the upper bound of snowflakes and of every Discord bitfield.

Discord: https://docs.discord.com/developers/reference#snowflakes
"""


def parse_uint64(value: int | str, what: str) -> int:
    """`value` as an unsigned 64-bit integer, from an int or the decimal string Discord sends.

    Raises:
        TypeError: `value` is a bool.
        ValueError: It is not decimal digits, or outside 0 to 2**64 - 1.
    """
    if isinstance(value, bool):
        msg = f"{what} cannot be a bool"
        raise TypeError(msg)
    if isinstance(value, str) and (not value.isascii() or not value.isdigit()):
        msg = f"{what} must be a decimal string, got {value!r}"
        raise ValueError(msg)
    number = int(value)
    if not 0 <= number <= UINT64_MAX:
        msg = f"{what} {number} is outside the unsigned 64-bit range"
        raise ValueError(msg)
    return number


class Snowflake(int):
    """A 64-bit Discord ID.

    Discord sends snowflakes as strings in JSON so 64-bit values survive every language. Shoal decodes
    them into this `int` subclass, so they compare, hash and sort like integers while exposing the
    fields packed inside them.

    Discord: https://docs.discord.com/developers/reference#snowflakes
    """

    __slots__ = ()

    def __new__(cls, value: int | str) -> Self:
        """Create a snowflake from an integer or the decimal string Discord sends.

        Raises:
            ValueError: The value is not a decimal integer between 0 and 2**64 - 1.
        """
        return super().__new__(cls, parse_uint64(value, "snowflake"))

    @classmethod
    def from_datetime(cls, moment: datetime, *, high: bool = False) -> Self:
        """Build the smallest (or largest) snowflake for a moment, for `before`/`after` pagination.

        Args:
            moment: A timezone-aware datetime at or after the Discord epoch.
            high: Fill the worker, process and increment bits so the ID sorts after every real
                snowflake created in that millisecond.

        Discord: https://docs.discord.com/developers/reference#snowflake-ids-in-pagination
        """
        if moment.tzinfo is None:
            msg = "moment must be timezone-aware"
            raise ValueError(msg)
        offset = int(moment.timestamp() * 1000) - DISCORD_EPOCH_MS
        if offset < 0:
            msg = "moment is before the Discord epoch (2015-01-01T00:00:00Z)"
            raise ValueError(msg)
        return cls((offset << 22) | ((1 << 22) - 1 if high else 0))

    @property
    def timestamp_ms(self) -> int:
        """Milliseconds since the Unix epoch at which the ID was generated."""
        return (self >> 22) + DISCORD_EPOCH_MS

    @property
    def created_at(self) -> datetime:
        """When the ID was generated, as an aware UTC datetime."""
        return datetime.fromtimestamp(self.timestamp_ms / 1000, tz=UTC)

    @property
    def worker_id(self) -> int:
        """The internal worker that generated the ID."""
        return (self & 0x3E0000) >> 17

    @property
    def process_id(self) -> int:
        """The internal process that generated the ID."""
        return (self & 0x1F000) >> 12

    @property
    def increment(self) -> int:
        """The per-process counter value."""
        return self & 0xFFF

    @override
    def __repr__(self) -> str:
        return f"Snowflake({int(self)})"

    @override
    def __str__(self) -> str:
        return str(int(self))
