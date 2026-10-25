"""Open enums: Discord enums that accept values Shoal does not know about yet.

Discord adds channel types, message types and guild features without bumping the API version. A closed
enum would make decoding fail the day that happens. These bases turn an unknown value into a
pseudo-member named `UNKNOWN_<value>` instead, so the payload still decodes, the value round-trips
unchanged and `is_known` lets callers branch on it. Each pseudo-member is stored in the enum's value
map, so later lookups of the same value find it directly: identity comparisons keep working and
repeated decodes allocate nothing.
"""

from enum import IntEnum, StrEnum
from typing import Self, override


class DiscordIntEnum(IntEnum):
    """An integer enum that tolerates values Discord adds later."""

    @classmethod
    @override
    def _missing_(cls, value: object) -> Self | None:
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        member = int.__new__(cls, value)
        member._name_ = f"UNKNOWN_{value}"
        member._value_ = value
        cls._value2member_map_[value] = member
        return member

    @property
    def is_known(self) -> bool:
        """Whether the value is documented and declared on this enum."""
        return self._name_ in type(self).__members__


class DiscordStrEnum(StrEnum):
    """A string enum that tolerates values Discord adds later."""

    @classmethod
    @override
    def _missing_(cls, value: object) -> Self | None:
        if not isinstance(value, str):
            return None
        member = str.__new__(cls, value)
        member._name_ = f"UNKNOWN_{value.upper()}"
        member._value_ = value
        cls._value2member_map_[value] = member
        return member

    @property
    def is_known(self) -> bool:
        """Whether the value is documented and declared on this enum."""
        return self._name_ in type(self).__members__
