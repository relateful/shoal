"""Immutable integer bitfields for Discord flag sets (permissions, intents, message flags, ...).

Every Discord bitfield subclasses `BaseFlags` and declares one `flag` per documented bit. Reading
the attribute on an instance gives a `bool`; reading it on the class gives the bit's integer value,
so both styles work:

    perms = Permissions(manage_guild=True, send_messages=True)
    perms.manage_guild  # True
    Permissions(Permissions.manage_guild | Permissions.kick_members)

Bits Discord adds before Shoal knows about them are kept, never dropped, and reported by
`unknown_bits`.
"""

from collections.abc import Iterator
from typing import ClassVar, Self, final, overload, override

from shoal.core.snowflake import UINT64_MAX


@final
class flag:  # noqa: N801
    """One named bit of a `BaseFlags` subclass."""

    __slots__ = ("bit", "name")

    def __init__(self, shift: int) -> None:
        """Declare the bit `1 << shift`."""
        if not 0 <= shift < UINT64_MAX.bit_length():
            msg = f"flag shift must be between 0 and {UINT64_MAX.bit_length() - 1}, got {shift}"
            raise ValueError(msg)
        self.bit: int = 1 << shift
        self.name: str = ""

    def __set_name__(self, owner: type[object], name: str) -> None:
        self.name = name

    @overload
    def __get__(self, instance: None, owner: type[object]) -> int: ...

    @overload
    def __get__(self, instance: "BaseFlags", owner: type[object]) -> bool: ...

    def __get__(self, instance: "BaseFlags | None", owner: type[object]) -> int | bool:
        if instance is None:
            return self.bit
        return int(instance) & self.bit == self.bit


class BaseFlags(int):
    """An immutable set of Discord flags stored as an `int`.

    Subclasses set `WIRE_AS_STRING` when Discord serializes the field as a string (permissions).
    """

    __slots__ = ()

    WIRE_AS_STRING: ClassVar[bool] = False
    """Whether Discord sends this bitfield as a decimal string rather than a JSON integer."""

    known_flags: ClassVar[dict[str, int]] = {}
    """Every known flag name mapped to its bit, filled in by `__init_subclass__`."""

    known_mask: ClassVar[int] = 0
    """All known bits OR-ed together."""

    @override
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        known: dict[str, int] = {}
        for klass in reversed(cls.__mro__):
            for name, value in vars(klass).items():
                if isinstance(value, flag):
                    known[name] = value.bit
        cls.known_flags = known
        total = 0
        for bit in known.values():
            total |= bit
        cls.known_mask = total

    def __new__(cls, value: int | str = 0, /, **flags: bool) -> Self:
        """Create a flag set from a raw value, keyword flags, or both.

        Raises:
            TypeError: A keyword is not a known flag of this class.
            ValueError: The raw value is negative, not an unsigned 64-bit integer, or not decimal.
        """
        if isinstance(value, bool):
            msg = f"{cls.__name__} cannot be built from a bool"
            raise TypeError(msg)
        if isinstance(value, str):
            if not value.isascii() or not value.isdigit():
                msg = f"{cls.__name__} string must be decimal digits, got {value!r}"
                raise ValueError(msg)
            number = int(value)
        else:
            number = int(value)
        if not 0 <= number <= UINT64_MAX:
            msg = f"{cls.__name__} value {number} is outside the unsigned 64-bit range"
            raise ValueError(msg)
        for name, enabled in flags.items():
            bit = cls.known_flags.get(name)
            if bit is None:
                msg = f"{name!r} is not a valid {cls.__name__} flag"
                raise TypeError(msg)
            number = number | bit if enabled else number & ~bit
        return super().__new__(cls, number)

    @classmethod
    def none(cls) -> Self:
        """A flag set with every bit cleared."""
        return cls(0)

    @classmethod
    def all(cls) -> Self:
        """A flag set with every known bit enabled."""
        return cls(cls.known_mask)

    def with_flags(self, **flags: bool) -> Self:
        """Return a copy with the given flags turned on or off."""
        return type(self)(int(self), **flags)

    def has(self, other: int) -> bool:
        """Whether every bit set in `other` is also set here."""
        return int(self) & int(other) == int(other)

    @property
    def unknown_bits(self) -> int:
        """Bits that are set but not declared on this class (new Discord flags)."""
        return int(self) & ~self.known_mask

    def enabled(self) -> Iterator[str]:
        """Yield the names of the known flags that are set, in bit order."""
        for name, bit in sorted(self.known_flags.items(), key=lambda item: item[1]):
            if int(self) & bit == bit:
                yield name

    @override
    def __or__(self, other: int) -> Self:
        return type(self)(int(self) | int(other))

    @override
    def __ror__(self, other: int) -> Self:
        return type(self)(int(self) | int(other))

    @override
    def __and__(self, other: int) -> Self:
        return type(self)(int(self) & int(other))

    @override
    def __rand__(self, other: int) -> Self:
        return type(self)(int(self) & int(other))

    @override
    def __xor__(self, other: int) -> Self:
        return type(self)(int(self) ^ int(other))

    @override
    def __rxor__(self, other: int) -> Self:
        return type(self)(int(self) ^ int(other))

    @override
    def __invert__(self) -> Self:
        return type(self)(~int(self) & self.known_mask)

    def without(self, other: int) -> Self:
        """The bits set here and not in `other`."""
        return type(self)(int(self) & ~int(other))

    @override
    def __repr__(self) -> str:
        names = "|".join(self.enabled())
        unknown = self.unknown_bits
        if unknown:
            names = f"{names}|{unknown:#x}" if names else f"{unknown:#x}"
        return f"{type(self).__name__}({names or 0})"

    @override
    def __str__(self) -> str:
        return str(int(self))
